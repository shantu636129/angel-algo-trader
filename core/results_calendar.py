import requests
import time


class NSEResultsCalendar:
    """
    Wraps NSE India's public (unauthenticated, but bot-protected) event
    calendar endpoint to get UPCOMING corporate events (mostly board
    meetings for financial results).

    Endpoint: GET https://www.nseindia.com/api/event-calendar
    This is NSE's own site API (not Angel One's), so it needs browser-like
    headers and a warm-up hit to the homepage to pick up cookies, or NSE
    returns 403.

    NOTE: this endpoint is forward-looking / near-term only (the next
    couple of weeks of scheduled board meetings). NSE's historical
    results-filing endpoints (corporate-results, corporate-announcements
    with date-range params) are behind stronger bot protection and time
    out on server-side requests without a real browser session — so this
    class is for LIVE watchlisting only, not historical backtesting.
    For backtesting the "reacts to a news/earnings-style shock" edge, use
    strategies/pead_drift.py instead, which detects the shock directly
    from price/volume in the historical candles (no calendar dependency).
    """

    BASE_URL = "https://www.nseindia.com"
    ENDPOINT = "/api/event-calendar"

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
    }

    def __init__(self):
        self.session = requests.Session()
        self._warmed_up = False

    def _warm_up(self):
        """Hits the NSE homepage first so the session picks up required cookies."""
        try:
            self.session.get(self.BASE_URL, headers=self.HEADERS, timeout=15)
            self._warmed_up = True
        except Exception as e:
            print(f"[RESULTS CALENDAR] ⚠️ Warm-up request failed: {e}")

    def get_upcoming_events(self, symbol_filter=None, purpose_filter="Financial Results"):
        """
        symbol_filter: optional single NSE symbol (e.g. "BAJFINANCE") to filter to.
        purpose_filter: substring match on the 'purpose' field (default: results only).
                        Pass None to get all event types (AGM, dividend, results, etc.)

        Returns a list of dicts: {symbol, company, purpose, bm_desc, date}, or None on failure.
        """
        if not self._warmed_up:
            self._warm_up()

        try:
            response = self.session.get(
                f"{self.BASE_URL}{self.ENDPOINT}",
                headers=self.HEADERS,
                timeout=15,
            )
            if response.status_code != 200:
                print(f"[RESULTS CALENDAR] ❌ Fetch failed: HTTP {response.status_code}")
                return None

            data = response.json()
            if symbol_filter:
                data = [d for d in data if d.get("symbol", "").upper() == symbol_filter.upper()]
            if purpose_filter:
                data = [d for d in data if purpose_filter.lower() in d.get("purpose", "").lower()]

            print(f"[RESULTS CALENDAR] ✅ {len(data)} upcoming event(s)"
                  f"{' for ' + symbol_filter if symbol_filter else ''}")
            for item in data[:30]:
                print(f"         {item.get('date')} | {item.get('symbol'):<12} {item.get('purpose')}")

            return data

        except Exception as e:
            print(f"[RESULTS CALENDAR] ❌ Exception in get_upcoming_events: {e}")
            return None
