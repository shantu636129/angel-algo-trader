import requests
from config import settings
from utils.rate_limiter import rate_limited


class AngelMarketData:
    """
    Live Market Data API — LTP, OHLC, and FULL mode quotes.

    Endpoint: POST /rest/secure/angelbroking/market/v1/quote/
    Docs: Live Market Data API (up to 50 tokens per request)
    Rate limit: 10 requests/second, 500/min, 5000/hr
    """

    BASE_URL = "https://apiconnect.angelone.in"
    ENDPOINT = "/rest/secure/angelbroking/market/v1/quote/"

    VALID_MODES = ("LTP", "OHLC", "FULL")

    def __init__(self, smart_api):
        self.smart_api = smart_api

    def _build_headers(self):
        """Builds required headers using the active session on smart_api."""
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

    @rate_limited("quote")  # 10 req/sec, 500/min, 5000/hr
    def get_quote(self, mode, exchange_tokens):
        """
        Fetches live market data.

        mode: "LTP", "OHLC", or "FULL"
        exchange_tokens: dict like {"NSE": ["3045", "881"], "NFO": ["58662"]}
            (max 50 tokens total across all exchanges)

        Returns the 'data' dict from the API response (fetched / unfetched
        lists) or None on failure.
        """
        try:
            mode = mode.upper()
            if mode not in self.VALID_MODES:
                print(f"[QUOTE] ❌ Invalid mode '{mode}'. Must be one of {self.VALID_MODES}.")
                return None

            total_tokens = sum(len(v) for v in exchange_tokens.values())
            if total_tokens == 0 or total_tokens > 50:
                print("[QUOTE] ❌ exchangeTokens must contain 1 to 50 tokens total.")
                return None

            payload = {"mode": mode, "exchangeTokens": exchange_tokens}
            headers = self._build_headers()

            response = requests.post(
                f"{self.BASE_URL}{self.ENDPOINT}",
                json=payload,
                headers=headers,
                timeout=10,
            )
            result = response.json()

            if result and result.get("status"):
                data = result.get("data", {})
                fetched = data.get("fetched", [])
                unfetched = data.get("unfetched", [])

                print(f"[QUOTE] ✅ {mode} Quote Retrieved — {len(fetched)} fetched, {len(unfetched)} unfetched")
                for item in fetched:
                    if mode == "LTP":
                        print(f"         {item.get('tradingSymbol')} ({item.get('exchange')}): LTP ₹{item.get('ltp')}")
                    elif mode == "OHLC":
                        print(
                            f"         {item.get('tradingSymbol')} ({item.get('exchange')}): "
                            f"LTP ₹{item.get('ltp')} | O ₹{item.get('open')} H ₹{item.get('high')} "
                            f"L ₹{item.get('low')} C ₹{item.get('close')}"
                        )
                    else:
                        print(
                            f"         {item.get('tradingSymbol')} ({item.get('exchange')}): "
                            f"LTP ₹{item.get('ltp')} | Vol {item.get('tradeVolume')} | "
                            f"OI {item.get('opnInterest')} | Chg {item.get('percentChange')}%"
                        )

                for item in unfetched:
                    print(f"         ⚠️ Unfetched [{item.get('exchange')}]: {item.get('message')}")

                return data
            else:
                msg = result.get("message") if result else "No response"
                err = result.get("errorcode") if result else ""
                print(f"[QUOTE] ❌ Quote Fetch Failed [{err}]: {msg}")
                return None

        except Exception as e:
            print(f"[QUOTE] ❌ Exception in get_quote: {e}")
            return None
