import json
import threading

import websocket
from core.webhook import OrderPostbackPayload


class AngelOrderUpdateStream:
    """
    WebSocket Order Status API - real-time order status updates,
    equivalent in content to the Postback/Webhook payload but delivered
    over a persistent WebSocket connection.

    Docs: Websocket Order Status
    URL: wss://tns.angelone.in/smart-order-update

    Note: max 3 concurrent connections per client code.

    Usage:
        auth = AngelAuth()
        auth.login()

        def handle_update(order_status, payload):
            print(order_status, payload.orderid, payload.orderstatus)

        stream = AngelOrderUpdateStream(auth.smart_api, on_update=handle_update)
        stream.connect()                      # blocks; runs in current thread
        # or: stream.connect(threaded=True)    # runs in a background thread
    """

    WS_URL = "wss://tns.angelone.in/smart-order-update"
    HEARTBEAT_INTERVAL_SEC = 10

    ORDER_STATUS_CODES = {
        "AB00": "after-successful connection",
        "AB01": "open",
        "AB02": "cancelled",
        "AB03": "rejected",
        "AB04": "modified",
        "AB05": "complete",
        "AB06": "after market order req received",
        "AB07": "cancelled after market order",
        "AB08": "modify after market order req received",
        "AB09": "open pending",
        "AB10": "trigger pending",
        "AB11": "modify pending",
    }

    HTTP_ERROR_CODES = {
        401: "Invalid AUTHORIZATION_TOKEN.",
        403: "AUTHORIZATION_TOKEN expired.",
        429: "Connection limit exceeded (max 3 per client code).",
    }

    def __init__(self, smart_api, on_update=None, on_error=None, on_close=None, on_open=None):
        """
        smart_api: an authenticated SmartConnect instance (from AngelAuth.smart_api),
                   used to read the session's access_token/jwt_token.
        on_update(order_status, OrderPostbackPayload): called for every order update.
        on_error(dict): called with {"code", "message"} on auth/connection-limit errors.
        on_close(): called when the connection closes.
        on_open(): called once the connection is established.
        """
        self.smart_api = smart_api

        self.on_update = on_update or self._default_on_update
        self.on_error = on_error or self._default_on_error
        self.on_close = on_close
        self.on_open = on_open

        self.ws = None
        self._ws_thread = None
        self._heartbeat_thread = None
        self._stop_heartbeat = threading.Event()

    def _headers(self):
        jwt_token = getattr(self.smart_api, "access_token", None) or getattr(
            self.smart_api, "jwt_token", None
        )
        return [f"Authorization: Bearer {jwt_token}"]

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
                    print(f"[ORDER-WS] ⚠️ Heartbeat send failed: {e}")

        self._heartbeat_thread = threading.Thread(target=_beat, daemon=True)
        self._heartbeat_thread.start()

    def _handle_open(self, ws):
        print("[ORDER-WS] ✅ Connected to smart-order-update.")
        self._start_heartbeat()
        if self.on_open:
            self.on_open()

    def _handle_message(self, ws, message):
        if not isinstance(message, str):
            return

        if message == "pong":
            return

        try:
            payload = json.loads(message)
        except (ValueError, TypeError):
            return

        status_code = payload.get("status-code")
        order_status = payload.get("order-status")
        error_message = payload.get("error-message")

        if status_code and status_code != "200":
            self.on_error({"code": status_code, "message": error_message or "Unknown error"})
            return

        order_data = payload.get("orderData") or {}
        try:
            parsed = OrderPostbackPayload(**order_data)
        except Exception:
            parsed = order_data  # fall back to raw dict if fields don't validate

        self.on_update(order_status, parsed)

    def _handle_ws_error(self, ws, error):
        # Handshake failures (401/403/429) surface here via websocket-client's
        # WebSocketBadStatusException, which carries an HTTP status code.
        status_code = getattr(error, "status_code", None)
        if status_code in self.HTTP_ERROR_CODES:
            self.on_error({"code": status_code, "message": self.HTTP_ERROR_CODES[status_code]})
        else:
            print(f"[ORDER-WS] ❌ Connection error: {error}")

    def _handle_close(self, ws, close_status_code, close_msg):
        self._stop_heartbeat.set()
        print(f"[ORDER-WS] 🔌 Connection closed [{close_status_code}]: {close_msg}")
        if self.on_close:
            self.on_close()

    @staticmethod
    def _default_on_update(order_status, payload):
        label = AngelOrderUpdateStream.ORDER_STATUS_CODES.get(order_status, order_status)
        if isinstance(payload, OrderPostbackPayload) and payload.orderid:
            print(
                f"[ORDER-WS] {order_status} ({label}) — Order {payload.orderid} "
                f"| {payload.tradingsymbol} | {payload.orderstatus} "
                f"| Filled {payload.filledshares}/{payload.quantity}"
            )
        else:
            print(f"[ORDER-WS] {order_status} ({label})")

    @staticmethod
    def _default_on_error(err):
        print(f"[ORDER-WS] ❌ Error [{err.get('code')}]: {err.get('message')}")
