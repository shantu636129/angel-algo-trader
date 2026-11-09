"""
market_hours.py - NSE equity market hours + trading-day check (IST).

Used to gate any scheduled job (cron/systemd timer) so it's a no-op outside
market hours or on exchange holidays, rather than needing complex calendar
scheduling syntax at the OS level.

Holiday data source: data/nse_holidays_2026.json (weekday NSE/BSE equity
closures only - Saturday/Sunday holidays are already excluded by the
weekday check and don't need listing). Sourced from the official NSE/BSE
2026 holiday calendar (https://zerodha.com/marketintel/holiday-calendar/).
Update this file (or add a new year's file and point _HOLIDAYS_PATH at it)
each December for the following year.
"""

import json
import os
from datetime import datetime, time as dtime

try:
    from zoneinfo import ZoneInfo
    IST = ZoneInfo("Asia/Kolkata")
except ImportError:  # pragma: no cover - Python <3.9 fallback
    import pytz
    IST = pytz.timezone("Asia/Kolkata")

MARKET_OPEN = dtime(9, 15)
MARKET_CLOSE = dtime(15, 30)

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
_HOLIDAYS_PATH = os.path.join(_DATA_DIR, "nse_holidays_2026.json")

_holiday_cache = None


def _load_holidays():
    global _holiday_cache
    if _holiday_cache is not None:
        return _holiday_cache
    if not os.path.exists(_HOLIDAYS_PATH):
        print(f"[MARKET_HOURS] ⚠️ Holiday list not found at {_HOLIDAYS_PATH} — holiday checks disabled.")
        _holiday_cache = set()
        return _holiday_cache
    with open(_HOLIDAYS_PATH) as f:
        _holiday_cache = set(json.load(f))
    return _holiday_cache


def now_ist():
    """Current time in IST, timezone-aware."""
    return datetime.now(IST)


def is_trading_day(now=None):
    """Mon-Fri and not a listed exchange holiday. Does not check market hours."""
    now = now or now_ist()
    if now.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    return now.strftime("%Y-%m-%d") not in _load_holidays()


def is_market_open(now=None):
    """True only when it's a trading day AND within 09:15-15:30 IST."""
    now = now or now_ist()
    if not is_trading_day(now):
        return False
    return MARKET_OPEN <= now.time() <= MARKET_CLOSE


def market_status_reason(now=None):
    """Human-readable reason the market is/isn't open right now — for logging."""
    now = now or now_ist()
    if now.weekday() >= 5:
        return f"Weekend ({now.strftime('%A')})"
    if now.strftime("%Y-%m-%d") in _load_holidays():
        return f"Exchange holiday ({now.strftime('%Y-%m-%d')})"
    if now.time() < MARKET_OPEN:
        return f"Pre-market (opens {MARKET_OPEN.strftime('%H:%M')} IST)"
    if now.time() > MARKET_CLOSE:
        return f"Post-market (closed {MARKET_CLOSE.strftime('%H:%M')} IST)"
    return "Market open"
