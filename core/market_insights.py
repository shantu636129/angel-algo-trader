import requests
from config import settings


class _BaseInsight:
    """Shared header-building logic, matching AngelMarketData / AngelOptionGreeks."""

    BASE_URL = "https://apiconnect.angelone.in"

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


class AngelGainersLosers(_BaseInsight):
    """
    Top Gainers/Losers API — % OI or % Price gainers/losers in the
    derivatives (options) segment for a given expiry bucket.

    Endpoint: POST /rest/secure/angelbroking/marketData/v1/gainersLosers
    NSE only.
    """

    ENDPOINT = "/rest/secure/angelbroking/marketData/v1/gainersLosers"
    VALID_DATATYPES = ("PercOIGainers", "PercOILosers", "PercPriceGainers", "PercPriceLosers")
    VALID_EXPIRYTYPES = ("NEAR", "NEXT", "FAR")

    def get_gainers_losers(self, datatype="PercOIGainers", expirytype="NEAR"):
        """
        datatype: PercOIGainers / PercOILosers / PercPriceGainers / PercPriceLosers
        expirytype: NEAR / NEXT / FAR

        Returns the list of gainer/loser dicts, or None on failure.
        """
        if datatype not in self.VALID_DATATYPES:
            print(f"[GAINERS/LOSERS] ❌ Invalid datatype '{datatype}'. Must be one of {self.VALID_DATATYPES}.")
            return None
        if expirytype not in self.VALID_EXPIRYTYPES:
            print(f"[GAINERS/LOSERS] ❌ Invalid expirytype '{expirytype}'. Must be one of {self.VALID_EXPIRYTYPES}.")
            return None

        try:
            payload = {"datatype": datatype, "expirytype": expirytype}
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
                print(f"[GAINERS/LOSERS] ✅ {datatype} ({expirytype}) — {len(data)} contracts")

                for item in data:
                    print(
                        f"         {item.get('tradingSymbol')} | "
                        f"Chg {item.get('percentChange')}% | "
                        f"OI {item.get('opnInterest')} | "
                        f"ΔOI {item.get('netChangeOpnInterest')}"
                    )

                return data
            else:
                msg = result.get("message") if result else "No response"
                err = result.get("errorcode") if result else ""
                print(f"[GAINERS/LOSERS] ❌ Fetch Failed [{err}]: {msg}")
                return None

        except Exception as e:
            print(f"[GAINERS/LOSERS] ❌ Exception in get_gainers_losers: {e}")
            return None


class AngelPCR(_BaseInsight):
    """
    PCR (Put-Call Ratio) API — cumulative Put/Call OI ratio per underlying,
    across all strikes, for options contracts.

    Endpoint: GET /rest/secure/angelbroking/marketData/v1/putCallRatio
    NSE only.
    """

    ENDPOINT = "/rest/secure/angelbroking/marketData/v1/putCallRatio"

    def get_pcr(self, symbol_filter=None):
        """
        symbol_filter: optional substring (e.g. "NIFTY") to filter results
                       client-side. Pass None to get the full list.

        Returns the list of {pcr, tradingSymbol} dicts, or None on failure.
        """
        try:
            headers = self._build_headers()

            response = requests.get(
                f"{self.BASE_URL}{self.ENDPOINT}",
                headers=headers,
                timeout=10,
            )
            result = response.json()

            if result and result.get("status"):
                data = result.get("data", [])

                if symbol_filter:
                    data = [d for d in data if symbol_filter.upper() in d.get("tradingSymbol", "").upper()]

                print(f"[PCR] ✅ Retrieved PCR — {len(data)} instrument(s)")
                for item in data:
                    print(f"         {item.get('tradingSymbol')} | PCR {item.get('pcr')}")

                return data
            else:
                msg = result.get("message") if result else "No response"
                err = result.get("errorcode") if result else ""
                print(f"[PCR] ❌ Fetch Failed [{err}]: {msg}")
                return None

        except Exception as e:
            print(f"[PCR] ❌ Exception in get_pcr: {e}")
            return None


class AngelOIBuildup(_BaseInsight):
    """
    OI Buildup API — Long Built Up / Short Built Up / Short Covering /
    Long Unwinding classification per underlying's options contracts.

    Endpoint: POST /rest/secure/angelbroking/marketData/v1/OIBuildup
    NSE only.
    """

    ENDPOINT = "/rest/secure/angelbroking/marketData/v1/OIBuildup"
    VALID_DATATYPES = ("Long Built Up", "Short Built Up", "Short Covering", "Long Unwinding")
    VALID_EXPIRYTYPES = ("NEAR", "NEXT", "FAR")

    def get_oi_buildup(self, datatype="Long Built Up", expirytype="NEAR"):
        """
        datatype: "Long Built Up" / "Short Built Up" / "Short Covering" / "Long Unwinding"
                  (note: single spaces, exactly as shown)
        expirytype: NEAR / NEXT / FAR

        Returns the list of OI-buildup dicts, or None on failure.
        """
        if datatype not in self.VALID_DATATYPES:
            print(f"[OI BUILDUP] ❌ Invalid datatype '{datatype}'. Must be one of {self.VALID_DATATYPES}.")
            return None
        if expirytype not in self.VALID_EXPIRYTYPES:
            print(f"[OI BUILDUP] ❌ Invalid expirytype '{expirytype}'. Must be one of {self.VALID_EXPIRYTYPES}.")
            return None

        try:
            payload = {"expirytype": expirytype, "datatype": datatype}
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
                print(f"[OI BUILDUP] ✅ {datatype} ({expirytype}) — {len(data)} contracts")

                for item in data:
                    print(
                        f"         {item.get('tradingSymbol')} | LTP ₹{item.get('ltp')} | "
                        f"Chg {item.get('percentChange')}% | "
                        f"OI {item.get('opnInterest')} | ΔOI {item.get('netChangeOpnInterest')}"
                    )

                return data
            else:
                msg = result.get("message") if result else "No response"
                err = result.get("errorcode") if result else ""
                print(f"[OI BUILDUP] ❌ Fetch Failed [{err}]: {msg}")
                return None

        except Exception as e:
            print(f"[OI BUILDUP] ❌ Exception in get_oi_buildup: {e}")
            return None
