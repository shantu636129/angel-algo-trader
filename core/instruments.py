import json
import os

import requests
from config import settings


class AngelInstruments:
    """
    Instrument Master & Scrip Utility APIs - scrip master refresh, search scrip,
    intraday-eligible scrip lists, and cautionary scrip messages.

    Note: LTP quotes via the order-service endpoint
    (POST /order-service/rest/secure/angelbroking/order/v1/getLtpData) are
    already covered by AngelOrderManager.get_ltp() in core/order_manager.py,
    which wraps the same call via smart_api.ltpData() - no need to duplicate here.
    """

    BASE_URL = "https://apiconnect.angelone.in"
    SCRIP_MASTER_URL = "https://margincalculator.angelone.in/OpenAPI_File/files/OpenAPIScripMaster.json"

    SCRIP_MASTER_PATH = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data",
        "scrip_master.json",
    )

    # Raw feed uses lowercase segment codes (nse_cm, nse_fo, ...); the rest of
    # this codebase (utils/token_lookup.py) expects the short uppercase form
    # already used in data/scrip_master.json, so normalize on refresh.
    EXCH_SEG_NORMALIZE = {
        "nse_cm": "NSE",
        "nse_fo": "NFO",
        "bse_cm": "BSE",
        "bse_fo": "BFO",
        "mcx_fo": "MCX",
        "ncd_fo": "NCD",
        "cde_fo": "CDS",
    }

    VALID_EXCHANGES = ("NSE", "NFO", "BSE", "BFO", "MCX")

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

    def refresh_scrip_master(self, save_path=None):
        """
        Downloads the full instrument master (no auth required) and overwrites
        the local cache used by utils/token_lookup.py. Segment codes are
        normalized (e.g. 'nse_cm' -> 'NSE') to match the existing cache format.

        Returns the number of instruments saved, or None on failure.
        """
        save_path = save_path or self.SCRIP_MASTER_PATH

        try:
            response = requests.get(self.SCRIP_MASTER_URL, timeout=60)
            response.raise_for_status()
            raw = response.json()

            for entry in raw:
                seg = entry.get("exch_seg", "")
                entry["exch_seg"] = self.EXCH_SEG_NORMALIZE.get(seg, seg.upper())

            with open(save_path, "w") as f:
                json.dump(raw, f)

            print(f"[INSTRUMENTS] ✅ Scrip master refreshed - {len(raw)} instruments saved to {save_path}")
            return len(raw)

        except Exception as e:
            print(f"[INSTRUMENTS] ❌ Exception in refresh_scrip_master: {e}")
            return None

    def search_scrip(self, exchange, searchscrip):
        """
        Looks up all trading-symbol variants for a scrip name via the live API
        (as opposed to the local scrip master cache in utils/token_lookup.py).

        exchange: NSE / NFO / BSE / BFO / MCX
        searchscrip: instrument name to search, e.g. "SBIN"

        Returns a list of dicts [{exchange, tradingsymbol, symboltoken}, ...]
        or None on failure. Only one scrip name is permitted per request
        (per Angel One docs).
        """
        if exchange not in self.VALID_EXCHANGES:
            print(f"[INSTRUMENTS] ❌ Invalid exchange '{exchange}'. Must be one of {self.VALID_EXCHANGES}.")
            return None

        try:
            payload = {"exchange": exchange, "searchscrip": searchscrip}
            headers = self._build_headers()

            response = requests.post(
                f"{self.BASE_URL}/rest/secure/angelbroking/order/v1/searchScrip",
                json=payload,
                headers=headers,
                timeout=15,
            )
            result = response.json()

            if result and result.get("status"):
                data = result.get("data", [])
                print(f"[INSTRUMENTS] ✅ Search '{searchscrip}' on {exchange} - {len(data)} match(es)")
                for item in data:
                    print(f"         {item.get('tradingsymbol'):<15} token {item.get('symboltoken')}")
                return data
            else:
                msg = result.get("message") if result else "No response"
                err = result.get("errorcode") if result else ""
                print(f"[INSTRUMENTS] ❌ Search Scrip Failed [{err}]: {msg}")
                return None

        except Exception as e:
            print(f"[INSTRUMENTS] ❌ Exception in search_scrip: {e}")
            return None

    def _get_intraday_scrips(self, endpoint, label):
        try:
            headers = self._build_headers()
            response = requests.get(
                f"{self.BASE_URL}{endpoint}",
                headers=headers,
                timeout=15,
            )
            result = response.json()

            if result and result.get("status"):
                data = result.get("data", [])
                print(f"[INSTRUMENTS] ✅ {label} Intraday Scrips - {len(data)} instrument(s)")
                for item in data:
                    print(f"         {item.get('SymbolName'):<15} multiplier {item.get('Multiplier')}")
                return data
            else:
                msg = result.get("message") if result else "No response"
                err = result.get("errorcode") if result else ""
                print(f"[INSTRUMENTS] ❌ {label} Intraday Fetch Failed [{err}]: {msg}")
                return None

        except Exception as e:
            print(f"[INSTRUMENTS] ❌ Exception fetching {label} intraday scrips: {e}")
            return None

    def get_nse_intraday_scrips(self):
        """NSE scrips allowed for intraday trading, with their margin multipliers."""
        return self._get_intraday_scrips("/rest/secure/angelbroking/marketData/v1/nseIntraday", "NSE")

    def get_bse_intraday_scrips(self):
        """BSE scrips allowed for intraday trading, with their margin multipliers."""
        return self._get_intraday_scrips("/rest/secure/angelbroking/marketData/v1/bseIntraday", "BSE")

    def get_cautionary_scrips(self):
        """
        Fetches scrips currently under exchange cautionary/surveillance messages
        (e.g. ASM/GSM stages, trade-for-trade settlement).
        """
        try:
            payload = {"scripconsent": "yes"}
            headers = self._build_headers()

            # Note: this is a GET request with a JSON body (confirmed against
            # the live API) - Angel One's docs table lists it as GET while the
            # prose/JS sample implies POST; GET with a body is correct here.
            response = requests.get(
                f"{self.BASE_URL}/rest/secure/angelbroking/securities/v1/cautionaryScrips",
                json=payload,
                headers=headers,
                timeout=15,
            )
            result = response.json()

            if result and result.get("status"):
                data = result.get("data", [])
                print(f"[INSTRUMENTS] ✅ Cautionary Scrips - {len(data)} flagged instrument(s)")
                for item in data:
                    print(f"         {item.get('symbol'):<15} token {item.get('token')} - {item.get('message')}")
                return data
            else:
                msg = result.get("message") if result else "No response"
                err = result.get("errorcode") if result else ""
                print(f"[INSTRUMENTS] ❌ Cautionary Scrips Fetch Failed [{err}]: {msg}")
                return None

        except Exception as e:
            print(f"[INSTRUMENTS] ❌ Exception in get_cautionary_scrips: {e}")
            return None
