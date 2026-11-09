"""
pattern_scan_smallcap.py - Scans the Nifty Smallcap 250 universe for two
chart patterns (rounding_bottom / trendline_breakout, see strategies/patterns.py)
using daily candles from Angel One, resampled to weekly, and sends a Telegram
alert for each new qualifying hit.

Usage:
  python3 strategies/pattern_scan_smallcap.py                 # full run
  python3 strategies/pattern_scan_smallcap.py --limit 15       # smoke test
  python3 strategies/pattern_scan_smallcap.py --min-score 70   # stricter
  python3 strategies/pattern_scan_smallcap.py --force-run      # ignore market-hours gate

Intended to be run once per trading day after the close via the
pattern-scan.timer systemd unit (weekly-candle patterns don't need
intraday polling).
"""

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime, timedelta

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.auth import AngelAuth
from core.historical_data import AngelCandleData
from core.telegram_alert import TelegramAlert
from utils.token_lookup import find_token
from utils.market_hours import is_trading_day, now_ist
from strategies.patterns import scan_symbol

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UNIVERSE_CSV = os.path.join(BASE_DIR, "data", "nifty_smallcap_250_list.csv")
STATE_PATH = os.path.join(BASE_DIR, "data", "pattern_scan_state.json")
REPORT_PATH = os.path.join(BASE_DIR, "data", "pattern_scan_last_report.json")
LOG_PATH = os.path.join(BASE_DIR, "logs", "pattern_scan.log")

REALERT_COOLDOWN_DAYS = 7
REALERT_SCORE_JUMP = 8  # re-alert sooner if score jumps by this much


def log(msg):
    line = f"[{datetime.now().isoformat(timespec='seconds')}] {msg}"
    print(line)
    try:
        with open(LOG_PATH, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def load_universe():
    rows = []
    with open(UNIVERSE_CSV) as f:
        for r in csv.DictReader(f):
            sym = r["Symbol"].strip()
            if sym:
                rows.append(sym)
    # dedupe, preserve order
    seen = set()
    out = []
    for s in rows:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def resolve_token(symbol):
    hits = find_token(symbol=f"{symbol}-EQ", exch_seg="NSE", limit=1)
    if hits:
        return hits[0]["token"]
    hits = find_token(name=symbol, exch_seg="NSE", limit=1)
    if hits:
        return hits[0]["token"]
    return None


def candles_to_df(candles):
    df = pd.DataFrame(candles)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True).dt.tz_localize(None)
    df = df.set_index("timestamp")[["open", "high", "low", "close", "volume"]]
    df = df.astype(float)
    return df


def load_state():
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH) as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_state(state):
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


def should_alert(state, key, score, today):
    prior = state.get(key)
    if not prior:
        return True
    last_date = datetime.strptime(prior["date"], "%Y-%m-%d")
    days_since = (today - last_date).days
    if days_since >= REALERT_COOLDOWN_DAYS:
        return True
    if score - prior.get("score", 0) >= REALERT_SCORE_JUMP:
        return True
    return False


PATTERN_LABELS = {
    "rounding_bottom": "🥣 Rounding Bottom / Cup",
    "trendline_breakout": "📐 Descending Trendline Breakout",
}


def format_alert(symbol, hit):
    label = PATTERN_LABELS.get(hit["pattern"], hit["pattern"])
    lines = [
        f"📊 PATTERN SCAN — {symbol}",
        label,
        f"Score: {hit['score']}/100",
        f"Last Close: ₹{hit['last_close']}",
        f"Resistance: ₹{hit['resistance']}",
        f"Support: ₹{hit['support']}",
        f"Measured-move Target: ₹{hit['target']}",
        f"Volume vs avg: {hit['vol_ratio']}x",
        f"(weekly candles, {hit['window']}-bar window)",
    ]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="only scan first N symbols (smoke test)")
    ap.add_argument("--min-score", type=float, default=60.0)
    ap.add_argument("--force-run", action="store_true", help="ignore the trading-day gate")
    ap.add_argument("--no-telegram", action="store_true", help="scan only, don't send alerts")
    args = ap.parse_args()

    if not args.force_run and not is_trading_day():
        log(f"Not a trading day ({now_ist().date()}) — skipping. Use --force-run to override.")
        return

    telegram = TelegramAlert()
    universe = load_universe()
    if args.limit:
        universe = universe[: args.limit]
    log(f"Scanning {len(universe)} symbols from Nifty Smallcap 250 universe...")

    auth = AngelAuth()
    if not auth.login():
        log("❌ Broker login failed — aborting scan.")
        telegram.send_error_alert("pattern_scan_smallcap", "Angel One login failed, scan aborted.")
        return

    cd = AngelCandleData(auth.smart_api)

    todate = datetime.now()
    fromdate = todate - timedelta(days=700)  # ~2 years of daily bars -> ~100wk
    fromdate_s = fromdate.strftime("%Y-%m-%d 09:15")
    todate_s = todate.strftime("%Y-%m-%d 15:30")

    state = load_state()
    today = datetime.now()
    today_s = today.strftime("%Y-%m-%d")

    all_hits = []
    new_alerts = []
    errors = 0

    for i, symbol in enumerate(universe, 1):
        token = resolve_token(symbol)
        if not token:
            log(f"  [{i}/{len(universe)}] {symbol}: token not found, skipping")
            continue
        try:
            candles = cd.get_candle_data("NSE", token, "ONE_DAY", fromdate_s, todate_s, verbose=False)
            if not candles or len(candles) < 60:
                continue
            df = candles_to_df(candles)
            hits = scan_symbol(df)
            for hit in hits:
                if hit["score"] < args.min_score:
                    continue
                all_hits.append({"symbol": symbol, **hit})
                key = f"{symbol}:{hit['pattern']}"
                if should_alert(state, key, hit["score"], today):
                    new_alerts.append((symbol, hit))
                    state[key] = {"date": today_s, "score": hit["score"]}
        except Exception as e:
            errors += 1
            log(f"  [{i}/{len(universe)}] {symbol}: ERROR {e}")
        if i % 25 == 0:
            log(f"  ...{i}/{len(universe)} scanned, {len(all_hits)} hits so far")

    auth.logout_session()

    save_state(state)
    with open(REPORT_PATH, "w") as f:
        json.dump({"run_at": today.isoformat(), "hits": all_hits}, f, indent=2, default=str)

    log(f"Scan complete: {len(all_hits)} total qualifying hits, {len(new_alerts)} new, {errors} errors.")

    if not args.no_telegram:
        if new_alerts:
            for symbol, hit in sorted(new_alerts, key=lambda t: -t[1]["score"]):
                telegram.send(format_alert(symbol, hit), parse_mode=None)
                time.sleep(0.5)
        summary = (
            f"🔎 Pattern Scan — {len(new_alerts)} new hit(s), "
            f"{len(all_hits)} total \u2265 {args.min_score} this run."
        )
        telegram.send(summary, parse_mode=None, disable_notification=(len(new_alerts) == 0))


if __name__ == "__main__":
    main()
