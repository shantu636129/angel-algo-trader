#!/usr/bin/env python3
"""
Auto Paper Trading - Option A
1. Load today's Top 2 picks from today_picks.json
2. Fetch OPENING price at 9:15 from Angel One (prefer day open)
3. Create paper trades (entry=open, target=+2%, no SL)
4. Optionally mark HIT when LTP >= target
"""

import json
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

BASE = os.path.dirname(os.path.abspath(__file__))
PICKS_PATH = os.path.join(BASE, "today_picks.json")
HISTORY_PATH = os.path.join(BASE, "trade_history.json")
IST = ZoneInfo("Asia/Kolkata")

def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def get_prices(symbols):
    """Fetch LTP from Angel One. Returns {symbol: ltp}."""
    prices = {}
    try:
        sys.path.insert(0, "/home/ec2-user/angel_algo")
        from core.auth import AngelAuth
        from core.market_data import AngelMarketData

        auth = AngelAuth()
        if not auth.login():
            print("Angel One login failed")
            return prices

        md = AngelMarketData(auth.smart_api)
        # Resolve tokens from full scrip master (all NSE symbols)
        sys.path.insert(0, "/home/ec2-user/angel_algo")
        from utils.token_lookup import find_token_by_lookup

        tokens = []
        sym_by_token = {}
        for sym in symbols:
            sym = sym.upper().strip()
            if not sym or sym == "NONE":
                continue
            rows = find_token_by_lookup(sym, exch_seg="NSE", limit=5)
            # prefer EQ cash
            row = None
            # Prefer equity: -EQ, then -SM (SME), then first match
            for r in rows:
                syms = str(r.get("symbol", ""))
                if syms.endswith("-EQ"):
                    row = r
                    break
            if not row:
                for r in rows:
                    if str(r.get("symbol", "")).endswith("-SM"):
                        row = r
                        break
            if not row and rows:
                row = rows[0]
            if not row:
                print(f"{sym}: token not found in scrip master")
                continue
            token = str(row.get("token"))
            tokens.append(token)
            sym_by_token[token] = sym
            print(f"{sym}: token={token} ({row.get('symbol')})")

        if tokens:
            try:
                # Prefer OHLC for open at 9:15; LTP otherwise
                data = md.get_quote("OHLC", {"NSE": tokens})
                if not data:
                    data = md.get_quote("LTP", {"NSE": tokens})
                fetched = (data or {}).get("fetched") or []
                for row in fetched:
                    tok = str(row.get("symbolToken", ""))
                    sym = sym_by_token.get(tok)
                    if not sym:
                        ts = str(row.get("tradingSymbol", "")).replace("-EQ", "")
                        sym = ts.upper()
                    open_px = row.get("open") or row.get("opn")
                    ltp = row.get("ltp") or row.get("close")
                    # Prefer LTP for live monitor; keep open for optional entry
                    px = float(ltp) if ltp is not None else (float(open_px) if open_px is not None else None)
                    if px is not None:
                        prices[sym] = px
                        if open_px is not None:
                            prices[sym + "_OPEN"] = float(open_px)
                        print(f"{sym}: LTP={px} open={open_px}")
            except Exception as e:
                print(f"quote error: {e}")

        try:
            auth.logout_session()
        except Exception:
            pass
    except Exception as e:
        print(f"Price fetch error: {e}")
    return prices

def already_entered_today(history, symbol):
    today = datetime.now(IST).strftime("%Y-%m-%d")
    for t in history:
        if t.get("date") == today and t.get("symbol") == symbol.upper() and t.get("auto"):
            return True
    return False

def auto_enter():
    picks = load_json(PICKS_PATH, {})
    symbols = picks.get("top2") or picks.get("symbols") or []
    if not symbols:
        print("No Top 2 picks in today_picks.json")
        return {"ok": False, "error": "no_picks"}

    symbols = [s.upper().strip() for s in symbols[:2] if s and str(s).upper().strip() not in ("NONE", "")]
    print(f"Auto-entering Top 2: {symbols}")

    prices = get_prices(symbols)
    history = load_json(HISTORY_PATH, [])
    created = []

    for i, sym in enumerate(symbols, 1):
        if already_entered_today(history, sym):
            print(f"{sym}: already entered today – skip")
            continue
        day_open = prices.get(sym + "_OPEN")
        ltp = prices.get(sym)
        if not day_open or day_open <= 0:
            print(f"{sym}: no day open – skip")
            continue
        if ltp is None or ltp <= 0:
            print(f"{sym}: no LTP – skip")
            continue

        # RULE: enter only when LTP <= day's open (at or below open)
        if float(ltp) > float(day_open):
            print(f"{sym}: WAIT – LTP {ltp} > open {day_open} (need LTP <= open)")
            continue

        entry = float(ltp)  # fill at/below open
        target = round(entry * 1.02, 2)
        trade = {
            "id": len(history) + 1,
            "date": datetime.now(IST).strftime("%Y-%m-%d"),
            "time": datetime.now(IST).strftime("%H:%M:%S"),
            "rank": i,
            "symbol": sym,
            "entry": entry,
            "day_open": float(day_open),
            "target": target,
            "exit_ltp": entry,
            "pnl_pct": 0.0,
            "status": "OPEN",
            "auto": True,
            "notes": "Entry when LTP <= day open",
        }
        history.append(trade)
        created.append(trade)
        print(f"ENTERED #{i} {sym} @ {entry} (open={day_open}) target {target}")

    save_json(HISTORY_PATH, history)
    return {"ok": True, "created": created, "total": len(history)}

def check_targets():
    history = load_json(HISTORY_PATH, [])
    today = datetime.now(IST).strftime("%Y-%m-%d")
    open_trades = [t for t in history if t.get("date") == today and t.get("status") == "OPEN"]
    if not open_trades:
        print("No open trades today")
        return {"ok": True, "updated": 0}

    symbols = list({t["symbol"] for t in open_trades})
    prices = get_prices(symbols)
    updated = 0

    for t in history:
        if t.get("date") != today or t.get("status") != "OPEN":
            continue
        ltp = prices.get(t["symbol"])
        if not ltp:
            continue
        t["exit_ltp"] = ltp
        t["pnl_pct"] = round(((ltp - t["entry"]) / t["entry"]) * 100, 2)
        if ltp >= t["target"]:
            t["status"] = "HIT"
            t["pnl_pct"] = 2.0
            t["exit_ltp"] = t["target"]
            t["hit_time"] = datetime.now(IST).strftime("%H:%M:%S")
            updated += 1
            print(f"HIT {t['symbol']} @ {ltp}")

    save_json(HISTORY_PATH, history)
    return {"ok": True, "updated": updated}

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "enter"
    if cmd == "enter":
        print(json.dumps(auto_enter(), indent=2))
    elif cmd == "check":
        print(json.dumps(check_targets(), indent=2))
    elif cmd == "set":
        # python auto_paper.py set SYM1 SYM2
        syms = [s.upper() for s in sys.argv[2:4]]
        save_json(PICKS_PATH, {
            "date": datetime.now(IST).strftime("%Y-%m-%d"),
            "top2": syms,
            "source": "manual",
        })
        print(f"Saved picks: {syms}")
    else:
        print("Usage: auto_paper.py enter|check|set SYM1 SYM2")
