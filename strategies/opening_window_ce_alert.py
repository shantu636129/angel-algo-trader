#!/usr/bin/env python3
"""
Opening-Window ATM/near-ATM Call Mean-Reversion Alert  — LIVE TICK VERSION
===========================================================================
Uses Angel One WebSocket Streaming 2.0 for true tick-by-tick NIFTY LTP.

Strategy (validated on real 1-min data):
  - Monitor first 30-150 min of the session (09:20 – 12:30 IST).
  - Trigger when NIFTY shows early weakness (Open − running Day Low ≥ 40 pts).
  - Suggest nearest liquid weekly ATM / near-ATM CEs.
  - Targets: +12-18 % on premium (first target).
  - No hard SL. Alert only.

How it works:
  1. Logs in → gets feed_token
  2. Connects to WebSocket smart-stream
  3. Subscribes to NIFTY 50 index LTP (token 99926000)
  4. On every tick: updates day Open (first tick of day) and running Low
  5. As soon as Open − Low ≥ 40 pts inside the alert window → sends Telegram
  6. Anti-spam: one primary alert per day (or on significantly deeper weakness)

Run:
  python3 strategies/opening_window_ce_alert.py          # live tick mode (default)
  python3 strategies/opening_window_ce_alert.py --force  # force even outside hours
"""

import argparse
import json
import signal
import sys
import threading
import time
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo
IST = ZoneInfo("Asia/Kolkata")
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.auth import AngelAuth
from core.telegram_alert import TelegramAlert
from core.websocket_stream import AngelWebSocketStream

STATE_FILE = ROOT / "data" / "opening_window_ce_state.json"
NIFTY_TOKEN = "99926000"          # Nifty 50 AMXIDX
WEAKNESS_THRESHOLD = 40.0         # points
LOG_PREFIX = "[OW-CE-LIVE]"

# Runtime state (updated by ticks)
_state = {
    "day": None,
    "open": None,
    "low": None,
    "ltp": None,
    "tick_count": 0,
    "alerted_today": False,
    "last_drop": 0.0,
}
_lock = threading.Lock()
_stop = threading.Event()


def now_ist():
    return datetime.now(IST)



def is_market_hours(now=None):
    now = now or now_ist()
    if now.weekday() >= 5:
        return False
    t = now.time()
    return dtime(9, 15) <= t <= dtime(15, 30)


def is_alert_window(now=None):
    """Only fire on weekdays inside the validated opening window."""
    now = now or now_ist()
    if now.weekday() >= 5:  # Sat/Sun
        return False
    t = now.time()
    return dtime(9, 20) <= t <= dtime(12, 30)


def load_persisted_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"last_alert_date": None, "last_drop": 0.0, "alerts_today": 0}


def save_persisted_state(data):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(data, indent=2, default=str))


def find_nearest_weekly_ce_strikes(spot):
    atm = round(spot / 50) * 50
    return [atm - 50, atm, atm + 50, atm + 100]


def send_alert(spot_open, spot_low, spot_ltp, drop):
    tg = TelegramAlert()
    now = now_ist()
    strikes = find_nearest_weekly_ce_strikes(spot_ltp)

    lines = [
        "🟢 *OPENING-WINDOW CE ALERT* (LIVE TICK)",
        f"Time: `{now.strftime('%H:%M:%S')}` IST",
        "",
        f"*NIFTY* Open `{spot_open:.1f}` → Low `{spot_low:.1f}` (drop `{drop:.1f}` pts)",
        f"Current LTP: `{spot_ltp:.1f}`",
        "",
        "*Suggested CE strikes (nearest weekly):*",
    ]
    for s in strikes:
        lines.append(f"  • `{int(s)}` CE")

    lines += [
        "",
        "*Strategy rules (validated):*",
        "• Buy ATM / slightly OTM weekly Call",
        "• First target ≈ +12-18 % on premium",
        "• Trail / book higher if momentum continues",
        "• No hard SL (mean-reversion edge)",
        "",
        "_Edge = opening-window bounce after early selling._",
        "_This is an alert only — trade at your own risk._",
    ]

    message = "\n".join(lines)
    print(f"\n{LOG_PREFIX} SENDING ALERT:\n{message}\n")
    ok = tg.send(message, parse_mode="Markdown")
    if ok:
        print(f"{LOG_PREFIX} ✅ Telegram alert sent")
        persisted = load_persisted_state()
        persisted["last_alert_date"] = now.strftime("%Y-%m-%d")
        persisted["last_drop"] = drop
        persisted["alerts_today"] = persisted.get("alerts_today", 0) + 1
        save_persisted_state(persisted)
    else:
        print(f"{LOG_PREFIX} ❌ Telegram send failed")
    return ok


def on_tick(tick):
    """Called on every live LTP tick from WebSocket."""
    if tick.get("token") != NIFTY_TOKEN:
        return

    ltp = tick.get("ltp")
    if ltp is None:
        return

    now = now_ist()
    today = now.strftime("%Y-%m-%d")

    with _lock:
        # New day → reset
        if _state["day"] != today:
            _state["day"] = today
            _state["open"] = ltp
            _state["low"] = ltp
            _state["ltp"] = ltp
            _state["tick_count"] = 0
            _state["alerted_today"] = False
            _state["last_drop"] = 0.0
            print(f"{LOG_PREFIX} New day started. Open set to {ltp:.1f}")

        _state["tick_count"] += 1
        _state["ltp"] = ltp

        # Update running low
        if ltp < _state["low"]:
            _state["low"] = ltp

        drop = _state["open"] - _state["low"]

        # Periodic status (every ~60 ticks ≈ 1 min depending on activity)
        if _state["tick_count"] % 60 == 1:
            print(f"{LOG_PREFIX} Tick #{_state['tick_count']}  LTP={ltp:.1f}  "
                  f"Open={_state['open']:.1f}  Low={_state['low']:.1f}  Drop={drop:.1f}")

        # Check trigger conditions
        if not is_alert_window(now):
            return

        if drop < WEAKNESS_THRESHOLD:
            return

        # Anti-spam logic
        persisted = load_persisted_state()
        already = persisted.get("last_alert_date") == today
        if already:
            # Allow second alert only if drop deepened by another 30+ pts
            if drop < persisted.get("last_drop", 0) + 30:
                return

        # Fire!
        print(f"{LOG_PREFIX} ⚡ CONDITION MET  Drop={drop:.1f} pts")
        _state["alerted_today"] = True
        _state["last_drop"] = drop

        # Send outside the lock to avoid blocking ticks
        threading.Thread(
            target=send_alert,
            args=(_state["open"], _state["low"], _state["ltp"], drop),
            daemon=True,
        ).start()


def on_ws_error(error):
    print(f"{LOG_PREFIX} WS error: {error}")


def on_ws_close():
    print(f"{LOG_PREFIX} WS closed")


def run_live(force=False):
    print(f"{LOG_PREFIX} Starting LIVE TICK mode...")

    if not force and not is_market_hours():
        print(f"{LOG_PREFIX} Outside market hours. Use --force to run anyway (will wait for ticks).")
        # Still allow running so it is ready at 09:15

    auth = AngelAuth()
    if not auth.login():
        print(f"{LOG_PREFIX} ❌ Login failed")
        return

    if not auth.feed_token:
        print(f"{LOG_PREFIX} ❌ No feed_token")
        return

    print(f"{LOG_PREFIX} Login OK, feed_token received")

    def _on_open():
        print(f"{LOG_PREFIX} WebSocket open — subscribing to NIFTY 50 LTP (token {NIFTY_TOKEN})...")
        stream.subscribe("LTP", {"NSE": [NIFTY_TOKEN]})
        print(f"{LOG_PREFIX} ✅ Live stream active. Waiting for ticks...")
        print(f"{LOG_PREFIX} Alert window: 09:20 – 12:30 IST | Threshold: {WEAKNESS_THRESHOLD} pts")

    stream = AngelWebSocketStream(
        auth.smart_api,
        auth.feed_token,
        on_tick=on_tick,
        on_error=on_ws_error,
        on_close=on_ws_close,
        on_open=_on_open,
    )

    def handle_signal(sig, frame):
        print(f"\n{LOG_PREFIX} Shutting down...")
        _stop.set()
        stream.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    stream.connect(threaded=True)

    # Keep main thread alive
    try:
        while not _stop.is_set():
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        stream.close()
        print(f"{LOG_PREFIX} Stopped.")


def main():
    parser = argparse.ArgumentParser(description="Opening-window CE alert — LIVE TICK")
    parser.add_argument("--force", action="store_true", help="Run even outside market hours")
    args = parser.parse_args()
    run_live(force=args.force)


if __name__ == "__main__":
    main()
