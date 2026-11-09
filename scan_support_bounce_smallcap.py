"""
scan_support_bounce_smallcap.py — Scans the Nifty Smallcap 250 universe for
NMDC-style "support bounce on volume" setups: a stock dips to (or through)
a recent support level intraday, then closes strongly off its low on
above-average volume — a same-day reversal signal, distinct from the
weekly cup/trendline patterns in strategies/pattern_scan_smallcap.py.

A symbol qualifies when, on the most recent trading day:
  1. Today's low is at/near (within --near-support-pct) the lowest low of
     the prior --lookback trading days (i.e. it tested or undercut support).
  2. Today's close sits in the top --close-position fraction of today's
     high-low range (a strong reversal candle, not a weak drift-up).
  3. Today's volume is >= --min-vol-ratio times the average volume of the
     prior --lookback trading days (confirms buyers showed up).

Each hit gets a 0-100 composite score (see score_bounce()) blending how far
into support price probed, how strong the close-off-low reversal was, and
how far above-average the volume spike was.

Usage:
  python3 scan_support_bounce_smallcap.py                      # full run
  python3 scan_support_bounce_smallcap.py --limit 15            # smoke test
  python3 scan_support_bounce_smallcap.py --min-vol-ratio 2.0   # stricter
  python3 scan_support_bounce_smallcap.py --force-run           # ignore market-hours gate
  python3 scan_support_bounce_smallcap.py --no-telegram         # scan only, no alerts

Intended to be run once per trading day after the close (can be wired to a
systemd timer the same way pattern_scan_smallcap.py is).
"""

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.auth import AngelAuth
from core.historical_data import AngelCandleData
from core.telegram_alert import TelegramAlert
from utils.token_lookup import find_token
from utils.market_hours import is_trading_day, now_ist

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UNIVERSE_CSV = os.path.join(BASE_DIR, "data", "nifty_smallcap_250_list.csv")
STATE_PATH = os.path.join(BASE_DIR, "data", "support_bounce_state.json")
REPORT_PATH = os.path.join(BASE_DIR, "data", "support_bounce_last_report.json")
LOG_PATH = os.path.join(BASE_DIR, "logs", "support_bounce_scan.log")

REALERT_COOLDOWN_DAYS = 3  # bounce setups are short-lived, re-alert sooner than the weekly scan


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


def should_alert(state, symbol, score, today):
    prior = state.get(symbol)
    if not prior:
        return True
    last_date = datetime.strptime(prior["date"], "%Y-%m-%d")
    days_since = (today - last_date).days
    return days_since >= REALERT_COOLDOWN_DAYS


def score_bounce(support_probe_pct, close_position, vol_ratio):
    """
    0-100 composite score.
      support_probe_pct: how far today's low pushed through/near the prior
        support low, as a fraction of that support level (0 = sat right on
        it, negative = undercut it — undercutting scores slightly higher,
        it's a stronger "shakeout" bounce).
      close_position: 0-1, where today's close sits within today's H-L range
        (1.0 = closed at the high).
      vol_ratio: today's volume / average volume over the lookback window.
    """
    # Undercutting support (probe <= 0) is the strongest signal; capped so a
    # huge crash-and-recover doesn't dominate the score.
    probe_score = max(0.0, min(1.0, (0.03 - support_probe_pct) / 0.03))
    close_score = max(0.0, min(1.0, close_position))
    vol_score = max(0.0, min(1.0, (vol_ratio - 1.0) / 2.0))  # 1x->0, 3x+->1
    composite = 100 * (0.35 * probe_score + 0.40 * close_score + 0.25 * vol_score)
    return round(composite, 1)


def scan_symbol(candles, lookback, near_support_pct, close_position_min, min_vol_ratio,
                 max_undercut_pct=None, max_vol_ratio=None):
    """
    candles: list of dicts [{timestamp, open, high, low, close, volume}, ...]
    oldest-first, at least lookback+1 bars.
    Returns a hit dict or None.

    max_undercut_pct: if set (e.g. 0.03), rejects days where today's low
        undercut prior support by more than this fraction. Deep undercuts on
        heavy volume tend to be capitulation/breakdown days that keep
        falling, not genuine "buyers defended the line" bounces — backtest
        data showed losers averaged a much deeper undercut (-1.3%) than
        winners (-0.6%), so this filters out that failure mode.
    max_vol_ratio: if set (e.g. 5.0), rejects days where volume spiked more
        than this multiple of the lookback average — extreme volume often
        marks panic selling rather than accumulation.
    """
    if not candles or len(candles) < lookback + 1:
        return None

    today = candles[-1]
    prior = candles[-(lookback + 1):-1]

    prior_low = min(c["low"] for c in prior)
    prior_avg_vol = sum(c["volume"] for c in prior) / len(prior)
    if prior_avg_vol <= 0:
        return None

    day_range = today["high"] - today["low"]
    if day_range <= 0:
        return None

    close_position = (today["close"] - today["low"]) / day_range
    vol_ratio = today["volume"] / prior_avg_vol
    support_probe_pct = (today["low"] - prior_low) / prior_low  # <=0 means undercut

    tested_support = support_probe_pct <= near_support_pct
    not_too_deep = max_undercut_pct is None or support_probe_pct >= -max_undercut_pct
    strong_close = close_position >= close_position_min
    volume_confirmed = vol_ratio >= min_vol_ratio
    not_panic_volume = max_vol_ratio is None or vol_ratio <= max_vol_ratio

    if not (tested_support and not_too_deep and strong_close and volume_confirmed and not_panic_volume):
        return None

    return {
        "last_close": today["close"],
        "today_low": today["low"],
        "today_high": today["high"],
        "prior_support": round(prior_low, 2),
        "support_probe_pct": round(support_probe_pct * 100, 2),
        "close_position": round(close_position, 2),
        "vol_ratio": round(vol_ratio, 2),
        "today_volume": today["volume"],
        "avg_volume": round(prior_avg_vol, 0),
        "score": score_bounce(support_probe_pct, close_position, vol_ratio),
        "date": today["timestamp"][:10],
    }


def format_alert(symbol, hit):
    lines = [
        f"🔄 SUPPORT BOUNCE — {symbol}",
        f"Score: {hit['score']}/100",
        f"Close: ₹{hit['last_close']}  (day: ₹{hit['today_low']} - ₹{hit['today_high']})",
        f"Prior support ({hit['date']}): ₹{hit['prior_support']}  (probe {hit['support_probe_pct']}%)",
        f"Close position in range: {int(hit['close_position']*100)}%",
        f"Volume: {hit['vol_ratio']}x avg ({hit['today_volume']:,} vs {int(hit['avg_volume']):,})",
    ]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="only scan first N symbols (smoke test)")
    ap.add_argument("--lookback", type=int, default=20, help="trading days used for support level + avg volume")
    ap.add_argument("--near-support-pct", type=float, default=0.015,
                     help="today's low must be within this fraction of prior support to qualify (0.015 = 1.5%% above, or any amount below)")
    ap.add_argument("--close-position-min", type=float, default=0.65,
                     help="min fraction of today's H-L range the close must sit in (0.65 = top 35%%)")
    ap.add_argument("--min-vol-ratio", type=float, default=1.5, help="min today-volume / lookback-avg-volume")
    ap.add_argument("--max-undercut-pct", type=float, default=None,
                     help="reject if today's low undercut prior support by more than this fraction (e.g. 0.03 = 3%%). Backtest showed deep undercuts tend to be capitulation, not genuine bounces.")
    ap.add_argument("--max-vol-ratio", type=float, default=None,
                     help="reject if volume spiked more than this multiple of the lookback average (e.g. 5.0). Extreme spikes often mark panic selling, not accumulation.")
    ap.add_argument("--min-score", type=float, default=50.0)
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
    log(f"Scanning {len(universe)} symbols from Nifty Smallcap 250 for support-bounce setups "
        f"(lookback={args.lookback}d, min_vol_ratio={args.min_vol_ratio}x)...")

    auth = AngelAuth()
    if not auth.login():
        log("❌ Broker login failed — aborting scan.")
        telegram.send_error_alert("scan_support_bounce_smallcap", "Angel One login failed, scan aborted.")
        return

    cd = AngelCandleData(auth.smart_api)

    todate = datetime.now()
    fromdate = todate - timedelta(days=args.lookback * 3)  # padding for weekends/holidays
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
            hit = scan_symbol(
                candles,
                lookback=args.lookback,
                near_support_pct=args.near_support_pct,
                close_position_min=args.close_position_min,
                min_vol_ratio=args.min_vol_ratio,
                max_undercut_pct=args.max_undercut_pct,
                max_vol_ratio=args.max_vol_ratio,
            )
            if hit and hit["score"] >= args.min_score:
                all_hits.append({"symbol": symbol, **hit})
                if should_alert(state, symbol, hit["score"], today):
                    new_alerts.append((symbol, hit))
                    state[symbol] = {"date": today_s, "score": hit["score"]}
        except Exception as e:
            errors += 1
            log(f"  [{i}/{len(universe)}] {symbol}: ERROR {e}")
        if i % 25 == 0:
            log(f"  ...{i}/{len(universe)} scanned, {len(all_hits)} hits so far")

    auth.logout_session()

    save_state(state)
    all_hits.sort(key=lambda h: -h["score"])
    with open(REPORT_PATH, "w") as f:
        json.dump({"run_at": today.isoformat(), "hits": all_hits}, f, indent=2, default=str)

    log(f"Scan complete: {len(all_hits)} total qualifying hits, {len(new_alerts)} new, {errors} errors.")
    for h in all_hits:
        log(f"  {h['symbol']:<15} score={h['score']:<5} close={h['last_close']:<8} "
            f"vol={h['vol_ratio']}x  close_pos={h['close_position']}")

    if not args.no_telegram:
        if new_alerts:
            for symbol, hit in sorted(new_alerts, key=lambda t: -t[1]["score"]):
                telegram.send(format_alert(symbol, hit), parse_mode=None)
        summary = (
            f"🔄 Support Bounce Scan — {len(new_alerts)} new hit(s), "
            f"{len(all_hits)} total \u2265 {args.min_score} this run."
        )
        telegram.send(summary, parse_mode=None, disable_notification=(len(new_alerts) == 0))


if __name__ == "__main__":
    main()
