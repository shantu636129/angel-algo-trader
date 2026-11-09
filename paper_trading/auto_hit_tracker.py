#!/usr/bin/env python3
"""
Auto Hit Tracker - Option A
Polls OPEN paper trades, fetches LTP, marks HIT when LTP >= entry * 1.02
No stop loss. Run every few minutes during market hours.
"""

import json
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

IST = ZoneInfo("Asia/Kolkata")
HISTORY_PATH = os.path.join(os.path.dirname(__file__), "trade_history.json")

def load_history():
    if not os.path.exists(HISTORY_PATH):
        return []
    try:
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_history(data):
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def fetch_ltps(symbols):
    prices = {}
    try:
        from core.auth import AngelAuth
        from core.market_data import AngelMarketData
        auth = AngelAuth()
        if not auth.login():
            return prices
        md = AngelMarketData(auth.smart_api)
        token_map = {}
        for path in [
            os.path.join(ROOT, "data", "midcap_quality_candidates.json"),
            os.path.join(ROOT, "data", "fundamental_quality_universe.json"),
        ]:
            if os.path.exists(path):
                try:
                    with open(path) as f:
                        for s in json.load(f):
                            sym = str(s.get("symbol", "")).upper()
                            tok = str(s.get("token", ""))
                            if sym and tok:
                                token_map[sym] = tok
                except Exception:
                    pass
        for sym in symbols:
            token = token_map.get(sym)
            if not token:
                continue
            try:
                q = md.get_ltp("NSE", token)
                ltp = q.get("ltp") if isinstance(q, dict) else q
                if ltp:
                    prices[sym] = float(ltp)
            except Exception:
                pass
        try:
            auth.logout_session()
        except Exception:
            pass
    except Exception as e:
        print(f"LTP fetch error: {e}")
    return prices

def main():
    history = load_history()
    open_trades = [t for t in history if t.get("status") == "OPEN"]
    if not open_trades:
        print("No OPEN paper trades.")
        return

    symbols = list({t["symbol"] for t in open_trades})
    prices = fetch_ltps(symbols)
    updated = 0
    now = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")

    for t in history:
        if t.get("status") != "OPEN":
            continue
        sym = t["symbol"]
        entry = float(t["entry"])
        target = float(t.get("target") or entry * 1.02)
        ltp = prices.get(sym)
        if ltp is None:
            continue
        pnl = round(((ltp - entry) / entry) * 100, 2)
        t["exit_ltp"] = ltp
        t["pnl_pct"] = pnl
        t["updated_at"] = now
        if ltp >= target:
            t["status"] = "HIT"
            t["exit_ltp"] = ltp
            t["pnl_pct"] = pnl
            t["notes"] = (t.get("notes") or "") + f" | AUTO HIT at {now}"
            print(f"HIT: {sym} entry={entry} ltp={ltp} pnl={pnl}%")
            updated += 1
        else:
            print(f"OPEN: {sym} entry={entry} ltp={ltp} pnl={pnl}% (target={target})")

    save_history(history)
    print(f"Done. Hits marked: {updated}")

if __name__ == "__main__":
    main()
