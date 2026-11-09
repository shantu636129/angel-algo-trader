#!/usr/bin/env python3
"""
Multi-Strategy Live Tick Alert
==============================
Runs 5 pure price-action strategies on live NIFTY ticks.
Sends Telegram when one or more strategies fire.
Extra emphasis when 2+ strategies agree (confluence).

Strategies (no regular indicators):
  S1 Weakness MR     : Open − running Low ≥ 40 pts
  S2 Deep Sell-off   : Open − running Low ≥ 100 pts
  S3 Gap-Down Bounce : Gap ≤ −50 pts vs prev close + recovery ≥ 30 pts
  S4 Early Momentum  : First 30-min high − Open ≥ 40 pts
  S5 Range Break     : First 60-min range ≤ 50 pts then break above range high +20

Run:
  python3 strategies/multi_strategy_alert.py
  python3 strategies/multi_strategy_alert.py --force
"""

import argparse
import json
import signal
import sys
import threading
import time
from datetime import datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo
IST = ZoneInfo("Asia/Kolkata")
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.auth import AngelAuth
from core.telegram_alert import TelegramAlert
from core.websocket_stream import AngelWebSocketStream
from core.historical_data import AngelCandleData

STATE_FILE = ROOT / "data" / "multi_strategy_state.json"
NIFTY_TOKEN = "99926000"
LOG = "[MULTI]"

# Runtime
_state = {
    "day": None,
    "open": None,
    "low": None,
    "high": None,
    "ltp": None,
    "prev_close": None,
    "tick_count": 0,
    "first30_high": None,
    "first30_done": False,
    "range60_high": None,
    "range60_low": None,
    "range60_done": False,
    "fired_today": set(),   # strategy names already alerted today
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
    now = now or now_ist()
    if now.weekday() >= 5:
        return False
    t = now.time()
    return dtime(9, 20) <= t <= dtime(12, 30)


def load_state():
    if STATE_FILE.exists():
        try:
            d = json.loads(STATE_FILE.read_text())
            d["fired_today"] = set(d.get("fired_today", []))
            return d
        except Exception:
            pass
    return {"last_date": None, "fired_today": set(), "prev_close": None}


def save_state(data):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    out = dict(data)
    out["fired_today"] = list(out.get("fired_today", []))
    STATE_FILE.write_text(json.dumps(out, indent=2, default=str))


def get_prev_close(candle_api):
    """Fetch previous trading day close from candles."""
    try:
        today = now_ist().date()
        for i in range(1, 6):
            d = today - timedelta(days=i)
            if d.weekday() >= 5:
                continue
            ds = d.strftime("%Y-%m-%d")
            candles = candle_api.get_candle_data(
                exchange="NSE",
                symboltoken=NIFTY_TOKEN,
                interval="ONE_DAY",
                fromdate=f"{ds} 09:15",
                todate=f"{ds} 15:30",
            )
            if candles:
                c = candles[-1]
                if isinstance(c, dict):
                    return float(c["close"])
                return float(c[4])
    except Exception as e:
        print(f"{LOG} prev_close fetch error: {e}")
    return None


def get_today_session_levels(candle_api):
    """Fetch today's true open / high / low from 1-min or 5-min candles (critical if script starts mid-session)."""
    try:
        today = now_ist().strftime("%Y-%m-%d")
        for interval in ("FIVE_MINUTE", "ONE_MINUTE"):
            candles = candle_api.get_candle_data(
                exchange="NSE",
                symboltoken=NIFTY_TOKEN,
                interval=interval,
                fromdate=f"{today} 09:15",
                todate=f"{today} 15:30",
            )
            if not candles:
                continue
            opens, highs, lows, closes = [], [], [], []
            for c in candles:
                if isinstance(c, dict):
                    opens.append(float(c["open"]))
                    highs.append(float(c["high"]))
                    lows.append(float(c["low"]))
                    closes.append(float(c["close"]))
                else:
                    opens.append(float(c[1]))
                    highs.append(float(c[2]))
                    lows.append(float(c[3]))
                    closes.append(float(c[4]))
            if opens:
                return {
                    "open": opens[0],
                    "high": max(highs),
                    "low": min(lows),
                    "ltp": closes[-1],
                    "n": len(opens),
                }
    except Exception as e:
        print(f"{LOG} today session levels error: {e}")
    return None


def find_strikes(spot):
    atm = round(spot / 50) * 50
    return [atm - 50, atm, atm + 50, atm + 100]


def evaluate_strategies(st, now):
    """Return list of newly triggered strategy names."""
    if st["open"] is None or st["ltp"] is None:
        return []

    drop = st["open"] - st["low"]
    rise = st["high"] - st["open"]
    gap = (st["open"] - st["prev_close"]) if st["prev_close"] else 0

    triggers = []

    # S1
    if drop >= 40:
        triggers.append("S1_Weakness_MR")

    # S2
    if drop >= 100:
        triggers.append("S2_Deep_Selloff")

    # S3
    if st["prev_close"] and gap <= -50 and rise >= 30:
        triggers.append("S3_GapDown_Bounce")

    # S4 — only after first 30 min window has data
    if st["first30_done"] and st["first30_high"] is not None:
        if (st["first30_high"] - st["open"]) >= 40:
            triggers.append("S4_Early_Momentum")

    # S5 — only after 60 min range is set
    if st["range60_done"] and st["range60_high"] is not None:
        rng = st["range60_high"] - st["range60_low"]
        if rng <= 50 and st["ltp"] > st["range60_high"] + 20:
            triggers.append("S5_Range_Break")

    # Only new ones not already alerted today
    new = [t for t in triggers if t not in st["fired_today"]]
    return new


def send_alert(st, new_strats):
    tg = TelegramAlert()
    now = now_ist()
    drop = st["open"] - st["low"]
    rise = st["high"] - st["open"]
    gap = (st["open"] - st["prev_close"]) if st["prev_close"] else 0
    strikes = find_strikes(st["ltp"])

    n = len(new_strats) + len(st["fired_today"])
    confluence = n >= 2

    header = "🔥 *MULTI-STRATEGY CONFLUENCE*" if confluence else "🟢 *STRATEGY ALERT*"

    lines = [
        header + " (LIVE TICK)",
        f"Time: `{now.strftime('%H:%M:%S')}` IST",
        "",
        f"*NIFTY* Open `{st['open']:.1f}`  LTP `{st['ltp']:.1f}`",
        f"Day Low `{st['low']:.1f}`  Day High `{st['high']:.1f}`",
        f"Drop from open: `{drop:.1f}` pts | Rise: `{rise:.1f}` pts",
    ]
    if st["prev_close"]:
        lines.append(f"Gap vs prev close: `{gap:+.1f}` pts")

    lines += ["", "*Triggered strategies:*"]
    labels = {
        "S1_Weakness_MR": "S1 Weakness Mean-Reversion (≥40 pt drop)",
        "S2_Deep_Selloff": "S2 Deep Sell-off (≥100 pt drop)",
        "S3_GapDown_Bounce": "S3 Gap-Down Bounce (gap≤-50 + recovery)",
        "S4_Early_Momentum": "S4 Early Momentum (first 30m ≥+40 pts)",
        "S5_Range_Break": "S5 Opening Range Break (tight range → up)",
    }
    for s in sorted(set(list(st["fired_today"]) + new_strats)):
        mark = "🆕" if s in new_strats else "✓"
        lines.append(f"  {mark} {labels.get(s, s)}")

    lines += [
        "",
        "*Suggested CE strikes:*",
    ]
    for s in strikes:
        lines.append(f"  • `{int(s)}` CE")

    lines += [
        "",
        "_Alert only — trade at your own risk._",
    ]

    msg = "\n".join(lines)
    print(f"\n{LOG} SENDING:\n{msg}\n")
    ok = tg.send(msg, parse_mode="Markdown")
    print(f"{LOG} Telegram {'OK' if ok else 'FAILED'}")
    return ok


def on_tick(tick):
    if tick.get("token") != NIFTY_TOKEN:
        return
    ltp = tick.get("ltp")
    if ltp is None:
        return

    now = now_ist()
    today = now.strftime("%Y-%m-%d")
    t = now.time()

    with _lock:
        # New day reset
        if _state["day"] != today:
            _state["day"] = today
            _state["open"] = ltp
            _state["low"] = ltp
            _state["high"] = ltp
            _state["ltp"] = ltp
            _state["tick_count"] = 0
            _state["first30_high"] = ltp
            _state["first30_done"] = False
            _state["range60_high"] = ltp
            _state["range60_low"] = ltp
            _state["range60_done"] = False
            _state["fired_today"] = set()
            print(f"{LOG} New day. Open={ltp:.1f}")

        _state["tick_count"] += 1
        _state["ltp"] = ltp
        if ltp < _state["low"]:
            _state["low"] = ltp
        if ltp > _state["high"]:
            _state["high"] = ltp

        # Track first 30 min high (until 09:45)
        if t <= dtime(9, 45):
            if _state["first30_high"] is None or ltp > _state["first30_high"]:
                _state["first30_high"] = ltp
        else:
            _state["first30_done"] = True

        # Track first 60 min range (until 10:15)
        if t <= dtime(10, 15):
            if _state["range60_high"] is None or ltp > _state["range60_high"]:
                _state["range60_high"] = ltp
            if _state["range60_low"] is None or ltp < _state["range60_low"]:
                _state["range60_low"] = ltp
        else:
            _state["range60_done"] = True

        if _state["tick_count"] % 60 == 1:
            drop = _state["open"] - _state["low"]
            print(f"{LOG} Tick#{_state['tick_count']} LTP={ltp:.1f} Open={_state['open']:.1f} "
                  f"Low={_state['low']:.1f} High={_state['high']:.1f} Drop={drop:.1f}")

        if not is_alert_window(now):
            return

        new = evaluate_strategies(_state, now)
        if not new:
            return

        print(f"{LOG} ⚡ NEW triggers: {new}")
        # snapshot for alert thread
        snap = {k: (set(v) if isinstance(v, set) else v) for k, v in _state.items()}
        for s in new:
            _state["fired_today"].add(s)

        # persist
        pers = load_state()
        pers["last_date"] = today
        pers["fired_today"] = _state["fired_today"]
        pers["prev_close"] = _state["prev_close"]
        save_state(pers)

        threading.Thread(target=send_alert, args=(snap, new), daemon=True).start()


def run_live(force=False):
    print(f"{LOG} Starting MULTI-STRATEGY live tick alert...")

    auth = AngelAuth()
    if not auth.login():
        print(f"{LOG} Login failed")
        return
    if not auth.feed_token:
        print(f"{LOG} No feed_token")
        return
    print(f"{LOG} Login OK")

    # Previous close + today's true OHLC (so mid-session start is correct)
    candle_api = AngelCandleData(auth.smart_api)
    prev = get_prev_close(candle_api)
    if prev:
        _state["prev_close"] = prev
        print(f"{LOG} Prev close = {prev:.1f}")
    else:
        pers = load_state()
        _state["prev_close"] = pers.get("prev_close")
        print(f"{LOG} Prev close (fallback) = {_state['prev_close']}")

    levels = get_today_session_levels(candle_api)
    if levels:
        today = now_ist().strftime("%Y-%m-%d")
        _state["day"] = today
        _state["open"] = levels["open"]
        _state["high"] = levels["high"]
        _state["low"] = levels["low"]
        _state["ltp"] = levels["ltp"]
        # Approximate first30 / range60 if we started late
        t = now_ist().time()
        if t > dtime(9, 45):
            _state["first30_high"] = levels["high"]
            _state["first30_done"] = True
        if t > dtime(10, 15):
            _state["range60_high"] = levels["high"]
            _state["range60_low"] = levels["low"]
            _state["range60_done"] = True
        drop = levels["open"] - levels["low"]
        print(f"{LOG} Seeded from candles: Open={levels['open']:.1f} High={levels['high']:.1f} "
              f"Low={levels['low']:.1f} LTP={levels['ltp']:.1f} Drop={drop:.1f} ({levels['n']} bars)")
    else:
        print(f"{LOG} Could not seed today OHLC from candles — will use first live tick as open")

    def _on_open():
        print(f"{LOG} WS open — subscribing NIFTY LTP...")
        stream.subscribe("LTP", {"NSE": [NIFTY_TOKEN]})
        print(f"{LOG} ✅ Live. Alert window 09:20–12:30 | 5 strategies active")

    stream = AngelWebSocketStream(
        auth.smart_api, auth.feed_token,
        on_tick=on_tick, on_open=_on_open,
    )

    def handle_sig(sig, frame):
        print(f"\n{LOG} Shutting down...")
        _stop.set()
        stream.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_sig)
    signal.signal(signal.SIGTERM, handle_sig)

    stream.connect(threaded=True)

    try:
        while not _stop.is_set():
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        stream.close()
        print(f"{LOG} Stopped.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    run_live(force=args.force)

if __name__ == "__main__":
    main()
