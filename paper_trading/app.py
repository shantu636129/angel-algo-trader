#!/usr/bin/env python3
"""
Paper Trading UI - FastAPI with history + auto paper + live SSE heartbeat stream
"""

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
from zoneinfo import ZoneInfo
import json
import os
import asyncio
import subprocess

app = FastAPI(title="News Momentum Paper Trading")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE = os.path.dirname(os.path.abspath(__file__))
HTML_PATH = os.path.join(BASE, "news_paper_trading.html")
HISTORY_PATH = os.path.join(BASE, "trade_history.json")
PICKS_PATH = os.path.join(BASE, "today_picks.json")
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

def fetch_ltps(symbols):
    """Best-effort LTP via auto_paper / Angel One."""
    if not symbols:
        return {}
    try:
        import sys
        if BASE not in sys.path:
            sys.path.insert(0, BASE)
        if "/home/ec2-user/angel_algo" not in sys.path:
            sys.path.insert(0, "/home/ec2-user/angel_algo")
        from auto_paper import get_prices
        raw = get_prices([s.upper() for s in symbols if s and s != "NONE"])
        # drop *_OPEN helper keys from display dict but keep them available
        return raw or {}
    except Exception as e:
        import traceback
        return {"_error": str(e), "_trace": traceback.format_exc()[-300:]}

@app.get("/", response_class=HTMLResponse)
async def home():
    with open(HTML_PATH, "r", encoding="utf-8") as f:
        return f.read()

@app.get("/health")
async def health():
    picks = load_json(PICKS_PATH, {})
    return {
        "status": "ok",
        "mode": "auto_paper_option_a",
        "entry_time": "09:15 IST opening price",
        "history_count": len(load_json(HISTORY_PATH, [])),
        "today_picks": picks.get("top2", []),
        "stream": "/api/stream",
    }

@app.get("/api/history")
async def get_history():
    return load_json(HISTORY_PATH, [])

@app.post("/api/history")
async def add_trade(request: Request):
    body = await request.json()
    history = load_json(HISTORY_PATH, [])
    trade = {
        "id": len(history) + 1,
        "date": body.get("date") or datetime.now(IST).strftime("%Y-%m-%d"),
        "time": body.get("time") or datetime.now(IST).strftime("%H:%M:%S"),
        "rank": body.get("rank"),
        "symbol": str(body.get("symbol", "")).upper(),
        "entry": float(body.get("entry", 0)),
        "target": float(body.get("target", 0)),
        "exit_ltp": float(body.get("exit_ltp")) if body.get("exit_ltp") is not None else None,
        "pnl_pct": float(body.get("pnl_pct")) if body.get("pnl_pct") is not None else None,
        "status": body.get("status", "OPEN"),
        "auto": bool(body.get("auto", False)),
        "notes": body.get("notes", ""),
    }
    history.append(trade)
    save_json(HISTORY_PATH, history)
    return {"ok": True, "trade": trade, "total": len(history)}

@app.put("/api/history/{trade_id}")
async def update_trade(trade_id: int, request: Request):
    body = await request.json()
    history = load_json(HISTORY_PATH, [])
    for t in history:
        if t.get("id") == trade_id:
            for k in ["exit_ltp", "pnl_pct", "status", "notes", "target", "entry"]:
                if k in body and body[k] is not None:
                    t[k] = body[k]
            t["updated_at"] = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
            save_json(HISTORY_PATH, history)
            return {"ok": True, "trade": t}
    return JSONResponse({"ok": False, "error": "not found"}, status_code=404)

@app.delete("/api/history")
async def clear_history():
    save_json(HISTORY_PATH, [])
    return {"ok": True, "total": 0}

@app.get("/api/picks")
async def get_picks():
    return load_json(PICKS_PATH, {})

@app.post("/api/picks")
async def set_picks(request: Request):
    body = await request.json()
    top2 = body.get("top2") or body.get("symbols") or []
    top2 = [str(s).upper().strip() for s in top2[:2]]
    data = {
        "date": datetime.now(IST).strftime("%Y-%m-%d"),
        "top2": top2,
        "all_listed": body.get("all_listed", []),
        "source": body.get("source", "api"),
        "set_at": datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S"),
    }
    save_json(PICKS_PATH, data)
    return {"ok": True, "picks": data}

@app.post("/api/auto-enter")
async def api_auto_enter():
    try:
        result = subprocess.run(
            ["python3", os.path.join(BASE, "auto_paper.py"), "enter"],
            capture_output=True, text=True, timeout=60, cwd=BASE
        )
        out = result.stdout.strip()
        try:
            return json.loads(out.split("\n")[-1] if out else "{}")
        except Exception:
            return {"ok": result.returncode == 0, "stdout": out, "stderr": result.stderr}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

@app.post("/api/check-targets")
async def api_check_targets():
    try:
        result = subprocess.run(
            ["python3", os.path.join(BASE, "auto_paper.py"), "check"],
            capture_output=True, text=True, timeout=60, cwd=BASE
        )
        out = result.stdout.strip()
        try:
            return json.loads(out.split("\n")[-1] if out else "{}")
        except Exception:
            return {"ok": result.returncode == 0, "stdout": out, "stderr": result.stderr}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

@app.get("/api/stream")
async def live_stream():
    """Server-Sent Events: heartbeat + live LTP for open trades / today's picks."""

    async def event_generator():
        beat = 0
        while True:
            beat += 1
            now = datetime.now(IST).strftime("%H:%M:%S")
            history = load_json(HISTORY_PATH, [])
            today = datetime.now(IST).strftime("%Y-%m-%d")
            picks = load_json(PICKS_PATH, {})

            open_trades = [t for t in history if t.get("date") == today and t.get("status") == "OPEN"]
            symbols = list({t["symbol"] for t in open_trades})
            for s in (picks.get("top2") or []):
                if s and s not in symbols and s != "NONE":
                    symbols.append(s.upper())

            prices = {}
            if symbols:
                try:
                    prices = await asyncio.get_event_loop().run_in_executor(None, fetch_ltps, symbols)
                except Exception as e:
                    prices = {"_error": str(e)}

            # Auto-update open trades PnL / HIT in history when possible
            err = prices.get("_error") if isinstance(prices, dict) else None
            if prices and not err:
                changed = False
                for tr in history:
                    if tr.get("date") != today or tr.get("status") != "OPEN":
                        continue
                    ltp = prices.get(tr["symbol"])
                    if ltp is None:
                        continue
                    ltp = float(ltp)
                    tr["exit_ltp"] = ltp
                    tr["pnl_pct"] = round(((ltp - float(tr["entry"])) / float(tr["entry"])) * 100, 2)
                    if ltp >= float(tr["target"]):
                        tr["status"] = "HIT"
                        tr["pnl_pct"] = 2.0
                        tr["exit_ltp"] = float(tr["target"])
                        tr["hit_time"] = now
                        tr["notes"] = ((tr.get("notes") or "") + " | heartbeat_exit").strip(" |")
                    changed = True
                if changed:
                    save_json(HISTORY_PATH, history)

            clean_prices = {
                k: v for k, v in (prices or {}).items()
                if not str(k).startswith("_") and not str(k).endswith("_OPEN")
            }
            payload = {
                "type": "tick",
                "beat": beat,
                "time": now,
                "prices": clean_prices,
                "price_error": err,
                "open_count": len([x for x in history if x.get("date") == today and x.get("status") == "OPEN"]),
                "picks": picks.get("top2", []),
                "history": [x for x in history if x.get("date") == today],
            }
            yield f"data: {json.dumps(payload)}\n\n"

            # Heartbeat every 1s feel; actual price poll ~3s to avoid API hammer
            await asyncio.sleep(2)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8081, reload=False)
