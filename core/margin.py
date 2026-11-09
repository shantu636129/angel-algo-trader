import requests
from config import settings
from utils.rate_limiter import rate_limited


class AngelMarginCalculator:
    """
    Margin Calculator for a basket of positions.

    Endpoint: POST /rest/secure/angelbroking/margin/v1/batch
    Docs: Margin Calculator API (real-time margin for up to 50 positions)
    Rate limit: 10 requests/second
    """

    BASE_URL = "https://apiconnect.angelone.in"
    ENDPOINT = "/rest/secure/angelbroking/margin/v1/batch"

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

    @rate_limited("margin")  # 10 req/sec, 500/min, 5000/hr
    def estimate_margin(self, positions):
        """
        Estimates total margin required for a basket of positions.

        positions: list of dicts, each with keys:
            exchange, qty, price, product_type, token, trade_type, order_type (optional, defaults to LIMIT)

        Returns the 'data' dict from the API response (totalMarginRequired,
        marginComponents) or None on failure.
        """
        try:
            if not positions or len(positions) > 50:
                print("[MARGIN] ❌ Positions list must contain 1 to 50 items.")
                return None

            formatted_positions = []
            for pos in positions:
                formatted_positions.append({
                    "exchange": pos.get("exchange", "NSE"),
                    "qty": int(pos.get("qty")),
                    "price": pos.get("price", 0),
                    "productType": pos.get("product_type", "INTRADAY"),
                    "token": str(pos.get("token")),
                    "tradeType": pos.get("trade_type", "BUY"),
                    "orderType": pos.get("order_type", "LIMIT"),
                })

            payload = {"positions": formatted_positions}
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
                components = data.get("marginComponents", {})

                print("[MARGIN] ✅ Margin Estimate Retrieved Successfully!")
                print(f"         Total Margin Required : ₹{data.get('totalMarginRequired')}")
                print(f"         Net Premium            : ₹{components.get('netPremium')}")
                print(f"         SPAN Margin             : ₹{components.get('spanMargin')}")
                print(f"         Margin Benefit          : ₹{components.get('marginBenefit')}")
                print(f"         Delivery Margin         : ₹{components.get('deliveryMargin')}")
                print(f"         Non-NFO Margin          : ₹{components.get('nonNFOMargin')}")
                print(f"         Total Options Premium   : ₹{components.get('totOptionsPremium')}")

                return data
            else:
                msg = result.get("message") if result else "No response"
                err = result.get("errorcode") if result else ""
                print(f"[MARGIN] ❌ Margin Estimate Failed [{err}]: {msg}")
                return None

        except Exception as e:
            print(f"[MARGIN] ❌ Exception in estimate_margin: {e}")
            return None
