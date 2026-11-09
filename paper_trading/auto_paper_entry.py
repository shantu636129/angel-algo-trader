#!/usr/bin/env python3
"""
Auto Paper Entry - Option A
Runs near market open (9:20 AM IST).
1. Scans fresh news stocks (same rules as automation)
2. Takes Top 2 only
3. Fetches opening / current price via Angel One
4. Saves paper trades to trade_history.json (entry=open, target=+2%, no SL)
"""

import json
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

# Allow importing from angel_algo root
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

def already_entered_today(symbol, history):
    today = datetime.now(IST).strftime("%Y-%m-%d")
    for t in history:
        if t.get("date") == today and t.get("symbol") == symbol.upper():
            return True
    return False

def get_top2_from_env_or_default():
    """
    Top 2 can be passed as args: python auto_paper_entry.py SYM1 SYM2
    Or set via env TOP2_SYMBOLS=SYM1,SYM2
    Otherwise returns empty (caller must supply).
    """
    if len(sys.argv) >= 3:
        return [sys.argv[1].upper(), sys.argv[2].upper()]
    env = os.environ.get("TOP2_SYMBOLS", "").strip()
    if env:
        parts = [p.strip().upper() for p in env.split(",") if p.strip()]
        if len(parts) >= 2:
            return parts[:2]
        if len(parts) == 1:
            return parts
    return []

def fetch_ltp_angel(symbols):
    """Fetch LTP/open from Angel One. Returns dict symbol -> price."""
    prices = {}
    try:
        from core.auth import AngelAuth
        from core.market_data import AngelMarketData
        auth = AngelAuth()
        if not auth.login():
            print("Angel One login failed")
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
                print(f"{sym}: token not found – skip")
                continue
            try:
                q = md.get_ltp("NSE", token)
                if isinstance(q, dict):
                    ltp = q.get("ltp") or q.get("last_price") or q.get("close")
                else:
                    ltp = q
                if ltp:
                    prices[sym] = float(ltp)
                    print(f"{sym}: LTP/Open = {prices[sym]}")
            except Exception as e:
                print(f"{sym}: LTP error – {e}")
        try:
            auth.logout_session()
        except Exception:
            pass
    except Exception as e:
        print(f"Angel fetch error: {e}")
    return prices

def create_paper_trades(symbols_with_prices):
    history = load_history()
    now = datetime.now(IST)
    created = []
    for rank, (sym, entry) in enumerate(symbols_with_prices.items(), start=1):
        if already_entered_today(sym, history):
            print(f"{sym}: already entered today – skip")
            continue
        target = round(entry * 1.02, 2)
        trade = {
            "id": len(history) + 1,
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M:%S"),
            "rank": rank,
            "symbol": sym,
            "entry": entry,
            "target": target,
            "exit_ltp": entry,
            "pnl_pct": 0.0,
            "status": "OPEN",
            "notes": "AUTO paper entry at open, target +2%, no SL",
            "auto": True,
        }
        history.append(trade)
        created.append(trade)
        print(f"AUTO ENTRY #{rank}: {sym} @ {entry} | Target {target} (+2%)")
    save_history(history)
    return created

def main():
    print("=== Auto Paper Entry (Option A) ===")
    print(datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST"))

    symbols = get_top2_from_env_or_default()
    if not symbols:
        print("No Top 2 symbols provided.")
        print("Usage: python auto_paper_entry.py SYMBOL1 SYMBOL2")
        print("   or: TOP2_SYMBOLS=SYM1,SYM2 python auto_paper_entry.py")
        print("Waiting for automation to pass Top 2...")
        return

    print(f"Top 2: {symbols}")
    prices = fetch_ltp_angel(symbols)
    if not prices:
        print("Could not fetch any prices. Abort.")
        return

    # Keep order of top 2
    ordered = {}
    for s in symbols:
        if s in prices:
            ordered[s] = prices[s]
    created = create_paper_trades(ordered)
    print(f"Created {len(created)} paper trade(s). History total: {len(load_history())}")

if __name__ == "__main__":
    main()
