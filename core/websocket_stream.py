import json
import random
import string
import struct
import threading
import time

import websocket
from config import settings


class AngelWebSocketStream:
    """
    WebSocket Streaming 2.0 - real-time LTP / Quote / SnapQuote tick feed.

    Docs: WebSocket Streaming 2.0
    URL: wss://smartapisocket.angelone.in/smart-stream

    Usage:
        auth = AngelAuth()
        auth.login()

        def handle_tick(tick):
            print(tick)

        stream = AngelWebSocketStream(auth.smart_api, auth.feed_token, on_tick=handle_tick)
        stream.connect()                                     # blocks; runs in current thread
        # or: stream.connect(threaded=True)                  # runs in a background thread

        stream.subscribe("LTP", {"NSE": ["3045", "881"]})
        stream.subscribe("QUOTE", {"NFO": ["58662"]})
        ...
        stream.unsubscribe("LTP", {"NSE": ["881"]})
        stream.close()
    """

    WS_URL = "wss://smartapisocket.angelone.in/smart-stream"

    EXCHANGE_MAP = {"NSE": 1, "NFO": 2, "BSE": 3, "BFO": 4, "MCX": 5}
    EXCHANGE_MAP_REVERSE = {v: k for k, v in EXCHANGE_MAP.items()}

    MODE_MAP = {"LTP": 1, "QUOTE": 2, "SNAPQUOTE": 3}
    MODE_MAP_REVERSE = {v: k for k, v in MODE_MAP.items()}

    ACTION_SUBSCRIBE = 1
    ACTION_UNSUBSCRIBE = 0

    HEARTBEAT_INTERVAL_SEC = 30
    MAX_TOKEN_QUOTA = 1000

    ERROR_CODES = {
        "E1001": "Invalid Request Payload.",
        "E1002": "Invalid Request. Subscription Limit Exceeded.",
    }

    def __init__(self, smart_api, feed_token, on_tick=None, on_error=None, on_close=None, on_open=None):
        """
        smart_api: an authenticated SmartConnect instance (from AngelAuth.smart_api),
                   used to read the session's access_token/jwt_token.
        feed_token: the feed token from AngelAuth.feed_token (login().feed_token),
                    required separately since it isn't stored on smart_api.
        on_tick(dict): called for every parsed tick.
        on_error(dict): called with errorCode/errorMessage/correlationID on server errors.
        on_close(): called when the connection closes.
        on_open(): called once the connection is established and ready for subs.
        """
        self.smart_api = smart_api
        self.feed_token = feed_token

        self.on_tick = on_tick or self._default_on_tick
        self.on_error = on_error or self._default_on_error
        self.on_close = on_close
        self.on_open = on_open

        self.ws = None
        self._ws_thread = None
        self._heartbeat_thread = None
        self._stop_heartbeat = threading.Event()
        self._subscribed_quota = 0

    def _headers(self):
        jwt_token = getattr(self.smart_api, "access_token", None) or getattr(
            self.smart_api, "jwt_token", None
        )
        return [
            "Authorization: Bearer " + str(jwt_token),
            "x-api-key: " + str(settings.API_KEY),
            "x-client-code: " + str(settings.CLIENT_CODE),
            "x-feed-token: " + str(self.feed_token),
        ]

    def connect(self, threaded=False):
        """
        Opens the WebSocket connection.

        threaded=False (default): blocks the calling thread (like run_forever()).
        threaded=True: runs the connection in a background daemon thread and
                        returns immediately.
        """
        self.ws = websocket.WebSocketApp(
            self.WS_URL,
            header=self._headers(),
            on_open=self._handle_open,
            on_message=self._handle_message,
            on_error=self._handle_ws_error,
            on_close=self._handle_close,
        )

        if threaded:
            self._ws_thread = threading.Thread(target=self.ws.run_forever, daemon=True)
            self._ws_thread.start()
        else:
            self.ws.run_forever()

    def close(self):
        """Stops the heartbeat and closes the connection."""
        self._stop_heartbeat.set()
        if self.ws:
            self.ws.close()

    def _start_heartbeat(self):
        self._stop_heartbeat.clear()

        def _beat():
            while not self._stop_heartbeat.wait(self.HEARTBEAT_INTERVAL_SEC):
                try:
                    if self.ws and self.ws.sock and self.ws.sock.connected:
                        self.ws.send("ping")
                except Exception as e:
                    print("[WS] Heartbeat send failed: " + str(e))

        self._heartbeat_thread = threading.Thread(target=_beat, daemon=True)
        self._heartbeat_thread.start()

    def _handle_open(self, ws):
        print("[WS] Connected to smart-stream.")
        self._start_heartbeat()
        if self.on_open:
            self.on_open()

    def _handle_message(self, ws, message):
        if isinstance(message, str):
            if message == "pong":
                return
            try:
                payload = json.loads(message)
                if "errorCode" in payload:
                    self.on_error(payload)
                    return
            except (ValueError, TypeError):
                pass
            return

        try:
            tick = self._parse_tick(message)
            if tick:
                self.on_tick(tick)
        except Exception as e:
            print("[WS] Exception parsing tick: " + str(e))

    def _handle_ws_error(self, ws, error):
        print("[WS] Connection error: " + str(error))

    def _handle_close(self, ws, close_status_code, close_msg):
        self._stop_heartbeat.set()
        print("[WS] Connection closed [" + str(close_status_code) + "]: " + str(close_msg))
        if self.on_close:
            self.on_close()

    @staticmethod
    def _correlation_id():
        return "".join(random.choices(string.ascii_letters + string.digits, k=10))

    def _build_token_list(self, exchange_tokens):
        token_list = []
        for exchange, tokens in exchange_tokens.items():
            exch_type = self.EXCHANGE_MAP.get(exchange.upper())
            if exch_type is None:
                print("[WS] Invalid exchange '" + str(exchange) + "'. Must be one of " + str(list(self.EXCHANGE_MAP)))
                continue
            token_list.append({"exchangeType": exch_type, "tokens": [str(t) for t in tokens]})
        return token_list

    def _send_request(self, action, mode, exchange_tokens, correlation_id=None):
        if not self.ws or not self.ws.sock or not self.ws.sock.connected:
            print("[WS] Not connected. Call connect() first.")
            return False

        mode_val = self.MODE_MAP.get(mode.upper()) if isinstance(mode, str) else mode
        if mode_val not in self.MODE_MAP_REVERSE:
            print("[WS] Invalid mode '" + str(mode) + "'. Must be one of " + str(list(self.MODE_MAP)))
            return False

        token_list = self._build_token_list(exchange_tokens)
        if not token_list:
            return False

        request = {
            "correlationID": correlation_id or self._correlation_id(),
            "action": action,
            "params": {"mode": mode_val, "tokenList": token_list},
        }

        total = sum(len(t["tokens"]) for t in token_list)
        if action == self.ACTION_SUBSCRIBE and self._subscribed_quota + total > self.MAX_TOKEN_QUOTA:
            print("[WS] Subscription would exceed quota (" + str(self._subscribed_quota + total) + "/" + str(self.MAX_TOKEN_QUOTA) + ").")
            return False

        self.ws.send(json.dumps(request))

        if action == self.ACTION_SUBSCRIBE:
            self._subscribed_quota += total
            print("[WS] Subscribed [" + self.MODE_MAP_REVERSE[mode_val] + "] - " + str(total) + " token(s).")
        else:
            self._subscribed_quota = max(0, self._subscribed_quota - total)
            print("[WS] Unsubscribed [" + self.MODE_MAP_REVERSE[mode_val] + "] - " + str(total) + " token(s).")

        return True

    def subscribe(self, mode, exchange_tokens, correlation_id=None):
        return self._send_request(self.ACTION_SUBSCRIBE, mode, exchange_tokens, correlation_id)

    def unsubscribe(self, mode, exchange_tokens, correlation_id=None):
        return self._send_request(self.ACTION_UNSUBSCRIBE, mode, exchange_tokens, correlation_id)

    def _parse_tick(self, data):
        """
        Parses a binary tick packet (little-endian) per the Response Contract.
        Packet size determines mode: 51 (LTP), 123 (Quote), 379 (SnapQuote).
        """
        if len(data) < 51:
            print("[WS] Unexpected short packet (" + str(len(data)) + " bytes), skipping.")
            return None

        subscription_mode = struct.unpack_from("<b", data, 0)[0]
        exchange_type = struct.unpack_from("<b", data, 1)[0]
        token_raw = data[2:27]
        token = token_raw.split(b"\x00")[0].decode("utf-8", errors="ignore")
        sequence_number = struct.unpack_from("<q", data, 27)[0]
        exchange_timestamp = struct.unpack_from("<q", data, 35)[0]
        ltp = struct.unpack_from("<q", data, 43)[0]

        tick = {
            "mode": self.MODE_MAP_REVERSE.get(subscription_mode, subscription_mode),
            "exchange": self.EXCHANGE_MAP_REVERSE.get(exchange_type, exchange_type),
            "token": token,
            "sequence_number": sequence_number,
            "exchange_timestamp": exchange_timestamp,
            "ltp": ltp / 100.0,
        }

        if len(data) < 123:
            return tick

        last_traded_qty = struct.unpack_from("<q", data, 51)[0]
        avg_traded_price = struct.unpack_from("<q", data, 59)[0]
        volume_traded = struct.unpack_from("<q", data, 67)[0]
        total_buy_qty = struct.unpack_from("<d", data, 75)[0]
        total_sell_qty = struct.unpack_from("<d", data, 83)[0]
        open_price = struct.unpack_from("<q", data, 91)[0]
        high_price = struct.unpack_from("<q", data, 99)[0]
        low_price = struct.unpack_from("<q", data, 107)[0]
        close_price = struct.unpack_from("<q", data, 115)[0]

        tick.update({
            "last_traded_qty": last_traded_qty,
            "avg_traded_price": avg_traded_price / 100.0,
            "volume_traded": volume_traded,
            "total_buy_qty": total_buy_qty,
            "total_sell_qty": total_sell_qty,
            "open": open_price / 100.0,
            "high": high_price / 100.0,
            "low": low_price / 100.0,
            "close": close_price / 100.0,
        })

        if len(data) < 379:
            return tick

        last_traded_timestamp = struct.unpack_from("<q", data, 123)[0]
        open_interest = struct.unpack_from("<q", data, 131)[0]

        best_five = []
        base = 147
        for i in range(10):
            offset = base + i * 20
            buy_sell_flag = struct.unpack_from("<h", data, offset)[0]
            qty = struct.unpack_from("<q", data, offset + 2)[0]
            price = struct.unpack_from("<q", data, offset + 10)[0]
            num_orders = struct.unpack_from("<h", data, offset + 18)[0]
            best_five.append({
                "side": "buy" if buy_sell_flag == 1 else "sell",
                "quantity": qty,
                "price": price / 100.0,
                "orders": num_orders,
            })

        upper_circuit = struct.unpack_from("<q", data, 347)[0]
        lower_circuit = struct.unpack_from("<q", data, 355)[0]
        week_52_high = struct.unpack_from("<q", data, 363)[0]
        week_52_low = struct.unpack_from("<q", data, 371)[0]

        tick.update({
            "last_traded_timestamp": last_traded_timestamp,
            "open_interest": open_interest,
            "best_five": best_five,
            "upper_circuit": upper_circuit / 100.0,
            "lower_circuit": lower_circuit / 100.0,
            "week_52_high": week_52_high / 100.0,
            "week_52_low": week_52_low / 100.0,
        })

        return tick

    @staticmethod
    def _default_on_tick(tick):
        print("[TICK] " + str(tick.get("exchange")) + ":" + str(tick.get("token")) + " (" + str(tick.get("mode")) + ") LTP " + str(tick.get("ltp")))

    @staticmethod
    def _default_on_error(payload):
        code = payload.get("errorCode")
        msg = payload.get("errorMessage") or AngelWebSocketStream.ERROR_CODES.get(code, "Unknown error")
        print("[WS] Server error [" + str(code) + "]: " + str(msg) + " (correlationID=" + str(payload.get("correlationID")) + ")")
