from datetime import datetime

import requests
from config import settings
from utils.rate_limiter import rate_limited


class _BaseHistorical:
    """Shared header-building logic, matching AngelMarketData / AngelInsights."""

    BASE_URL = "https://apiconnect.angelone.in"

    VALID_EXCHANGES = ("NSE", "NFO", "BSE", "BFO", "MCX")
    VALID_INTERVALS = (
        "ONE_MINUTE", "THREE_MINUTE", "FIVE_MINUTE", "TEN_MINUTE",
        "FIFTEEN_MINUTE", "THIRTY_MINUTE", "ONE_HOUR", "ONE_DAY",
    )

    # Max days permitted per request, per Angel One docs
    MAX_DAYS = {
        "ONE_MINUTE": 30,
        "THREE_MINUTE": 60,
        "FIVE_MINUTE": 100,
        "TEN_MINUTE": 100,
        "FIFTEEN_MINUTE": 200,
        "THIRTY_MINUTE": 200,
        "ONE_HOUR": 400,
        "ONE_DAY": 2000,
    }

    DATE_FMT = "%Y-%m-%d %H:%M"

    def __init__(self, smart_api):
        self.smart_api = smart_api

    def _build_headers(self):
        jwt_token = getattr(self.smart_api, "access_token", None) or getattr(
            self.smart_api, "jwt_token", None
        )

        return {
            "Authorization": f"Bearer {jwt_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-PrivateKey": settings.API_KEY,
            "X-SourceID": "WEB",
            "X-ClientLocalIP": getattr(settings, "CLIENT_LOCAL_IP", "127.0.0.1"),
            "X-ClientPublicIP": getattr(settings, "CLIENT_PUBLIC_IP", "127.0.0.1"),
            "X-MACAddress": getattr(settings, "MAC_ADDRESS", "00:00:00:00:00:00"),
            "X-UserType": "USER",
        }

    def _validate(self, exchange, interval, fromdate, todate):
        if exchange not in self.VALID_EXCHANGES:
            return f"Invalid exchange '{exchange}'. Must be one of {self.VALID_EXCHANGES}."

        if interval not in self.VALID_INTERVALS:
            return f"Invalid interval '{interval}'. Must be one of {self.VALID_INTERVALS}."

        try:
            dt_from = datetime.strptime(fromdate, self.DATE_FMT)
            dt_to = datetime.strptime(todate, self.DATE_FMT)
        except ValueError:
            return f"fromdate/todate must be in '{self.DATE_FMT}' format, e.g. '2023-09-06 11:15'."

        if dt_to <= dt_from:
            return "todate must be after fromdate."

        span_days = (dt_to - dt_from).days + 1
        max_days = self.MAX_DAYS[interval]
        if span_days > max_days:
            return (
                f"Requested span is {span_days} day(s), but '{interval}' "
                f"allows a maximum of {max_days} day(s) per request."
            )

        return None


class AngelCandleData(_BaseHistorical):
    """
    Historical Candle Data API — OHLCV candles for stocks/indices/F&O
    across NSE, NFO, BSE, BFO, MCX.

    Endpoint: POST /rest/secure/angelbroking/historical/v1/getCandleData
    Rate limit: 3 req/sec, 150/min, 5000/hr
    """

    ENDPOINT = "/rest/secure/angelbroking/historical/v1/getCandleData"

    @rate_limited("historical")  # 3 req/sec, 150/min, 5000/hr
    def get_candle_data(self, exchange, symboltoken, interval, fromdate, todate, verbose=True):
        """
        exchange: NSE / NFO / BSE / BFO / MCX
        symboltoken: scrip master token, e.g. "3045"
        interval: ONE_MINUTE / THREE_MINUTE / FIVE_MINUTE / TEN_MINUTE /
                  FIFTEEN_MINUTE / THIRTY_MINUTE / ONE_HOUR / ONE_DAY
        fromdate / todate: "yyyy-MM-dd hh:mm", e.g. "2023-09-06 11:15"
        verbose: if False, suppresses the per-candle print (use False for bulk/
                 backtest calls across many symbols; the per-candle dump is only
                 useful for a single manual lookup)

        Returns a list of dicts [{timestamp, open, high, low, close, volume}, ...]
        or None on failure.
        """
        err = self._validate(exchange, interval, fromdate, todate)
        if err:
            print(f"[CANDLE] ❌ {err}")
            return None

        try:
            payload = {
                "exchange": exchange,
                "symboltoken": str(symboltoken),
                "interval": interval,
                "fromdate": fromdate,
                "todate": todate,
            }
            headers = self._build_headers()

            response = requests.post(
                f"{self.BASE_URL}{self.ENDPOINT}",
                json=payload,
                headers=headers,
                timeout=15,
            )
            result = response.json()

            if result and result.get("status"):
                raw = result.get("data", [])
                candles = [
                    {
                        "timestamp": row[0],
                        "open": row[1],
                        "high": row[2],
                        "low": row[3],
                        "close": row[4],
                        "volume": row[5],
                    }
                    for row in raw
                ]

                if verbose:
                    print(f"[CANDLE] ✅ {exchange}:{symboltoken} {interval} — {len(candles)} candle(s)")
                    for c in candles:
                        print(
                            f"         {c['timestamp']} | O {c['open']} H {c['high']} "
                            f"L {c['low']} C {c['close']} | Vol {c['volume']}"
                        )

                return candles
            else:
                msg = result.get("message") if result else "No response"
                err = result.get("errorcode") if result else ""
                print(f"[CANDLE] ❌ Fetch Failed [{err}]: {msg}")
                return None

        except Exception as e:
            print(f"[CANDLE] ❌ Exception in get_candle_data: {e}")
            return None


class AngelOIData(_BaseHistorical):
    """
    Historical OI Data API — Open Interest time series for live F&O contracts.

    Endpoint: POST /rest/secure/angelbroking/historical/v1/getOIData
    NFO/BFO/MCX only (OI doesn't exist for plain cash equity/indices).
    Rate limit: 3 req/sec, 150/min, 5000/hr (shares "historical" bucket with candle data)
    """

    ENDPOINT = "/rest/secure/angelbroking/historical/v1/getOIData"
    VALID_EXCHANGES = ("NFO", "BFO", "MCX")

    @rate_limited("historical")  # 3 req/sec, 150/min, 5000/hr
    def get_oi_data(self, exchange, symboltoken, interval, fromdate, todate):
        """
        exchange: NFO / BFO / MCX (F&O segments only)
        symboltoken: scrip master token for the specific contract, e.g. "46823"
        interval: same interval constants as candle data
        fromdate / todate: "yyyy-MM-dd hh:mm"

        Returns a list of dicts [{time, oi}, ...] or None on failure.
        """
        err = self._validate(exchange, interval, fromdate, todate)
        if err:
            print(f"[OI DATA] ❌ {err}")
            return None

        try:
            payload = {
                "exchange": exchange,
                "symboltoken": str(symboltoken),
                "interval": interval,
                "fromdate": fromdate,
                "todate": todate,
            }
            headers = self._build_headers()

            response = requests.post(
                f"{self.BASE_URL}{self.ENDPOINT}",
                json=payload,
                headers=headers,
                timeout=15,
            )
            result = response.json()

            if result and result.get("status"):
                data = result.get("data", [])
                print(f"[OI DATA] ✅ {exchange}:{symboltoken} {interval} — {len(data)} point(s)")
                for item in data:
                    print(f"         {item.get('time')} | OI {item.get('oi')}")

                return data
            else:
                msg = result.get("message") if result else "No response"
                err = result.get("errorcode") if result else ""
                print(f"[OI DATA] ❌ Fetch Failed [{err}]: {msg}")
                return None

        except Exception as e:
            print(f"[OI DATA] ❌ Exception in get_oi_data: {e}")
            return None
