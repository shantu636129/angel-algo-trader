#!/usr/bin/env python3
"""
Paper Trading Live LTP Helper
Usage: python live_ltp_helper.py SYMBOL1 SYMBOL2
Fetches last traded price from Angel One for the two top stocks.
"""

import sys
import json
from core.auth import AngelAuth
from core.market_data import AngelMarketData

def get_ltp(symbols):
    auth = AngelAuth()
    if not auth.login():
        print("Login failed")
        return
    md = AngelMarketData(auth.smart_api)

    # Load symbol-token map from quality universe if available
    token_map = {}
    try:
        with open("data/midcap_quality_candidates.json") as f:
            for s in json.load(f):
                token_map[s.get("symbol", "").upper()] = str(s.get("token", ""))
        with open("data/fundamental_quality_universe.json") as f:
            for s in json.load(f):
                token_map[s.get("symbol", "").upper()] = str(s.get("token", ""))
    except Exception:
        pass

    results = []
    for sym in symbols:
        sym = sym.upper().strip()
        token = token_map.get(sym)
        if not token:
            # fallback: try search
            print(f"{sym}: token not found in local universe – please enter LTP manually in UI")
            continue
        try:
            q = md.get_ltp("NSE", token)
            ltp = q.get("ltp") or q.get("last_price") or q
            print(f"{sym}: LTP = {ltp}")
            results.append({"symbol": sym, "ltp": ltp})
        except Exception as e:
            print(f"{sym}: error fetching LTP – {e}")

    auth.logout_session()
    return results

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python live_ltp_helper.py SYMBOL1 [SYMBOL2]")
        sys.exit(1)
    get_ltp(sys.argv[1:])
