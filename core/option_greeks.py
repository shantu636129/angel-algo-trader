import requests
from config import settings
from utils.rate_limiter import rate_limited


class AngelOptionGreeks:
    """
    Option Greeks API — Delta, Gamma, Theta, Vega, and Implied Volatility
    for all strike prices of an underlying's option chain, for a given expiry.

    Endpoint: POST /rest/secure/angelbroking/marketData/v1/optionGreek
    Note: Available for NSE underlyings only.
    Rate limit: 1 request/second
    """

    BASE_URL = "https://apiconnect.angelone.in"
    ENDPOINT = "/rest/secure/angelbroking/marketData/v1/optionGreek"

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

    @rate_limited("option_greek")  # 1 req/sec
    def get_option_greeks(self, name, expiry_date):
        """
        Fetches option Greeks for every strike price of an underlying's
        option chain at a given expiry.

        name: Underlying stock/index name, e.g. "TCS", "NIFTY"
        expiry_date: Expiry in "DDMMMYYYY" format, e.g. "25JAN2024"

        Returns the list of per-strike Greek dicts, or None on failure.
        """
        try:
            payload = {"name": name, "expirydate": expiry_date}
            headers = self._build_headers()

            response = requests.post(
                f"{self.BASE_URL}{self.ENDPOINT}",
                json=payload,
                headers=headers,
                timeout=10,
            )
            result = response.json()

            if result and result.get("status"):
                data = result.get("data", [])
                print(f"[GREEKS] ✅ Retrieved Greeks for {name} ({expiry_date}) — {len(data)} strikes")

                for item in data:
                    print(
                        f"         {item.get('strikePrice')} {item.get('optionType')} | "
                        f"Δ {item.get('delta')} | Γ {item.get('gamma')} | "
                        f"Θ {item.get('theta')} | ν {item.get('vega')} | "
                        f"IV {item.get('impliedVolatility')}% | Vol {item.get('tradeVolume')}"
                    )

                return data
            else:
                msg = result.get("message") if result else "No response"
                err = result.get("errorcode") if result else ""
                print(f"[GREEKS] ❌ Option Greeks Fetch Failed [{err}]: {msg}")
                return None

        except Exception as e:
            print(f"[GREEKS] ❌ Exception in get_option_greeks: {e}")
            return None
