"""
Export 1m / 5m / 15m / 1h candles for the option contracts in the 28 Sep - 1 Oct 2026 alert list.
Uses the project's own AngelAuth + AngelCandleData (credentials come from config.settings).
Output: data/exports/alerts_oct2026/<SYMBOL>_<TF>.csv  and  <SYMBOL>.xlsx (one sheet per timeframe)
"""
import os, sys, csv, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.auth import AngelAuth
from core.historical_data import AngelCandleData

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "exports", "alerts_oct2026")
os.makedirs(OUT, exist_ok=True)

FROM = "2026-09-28 09:15"
TO = "2026-10-01 15:30"

# symbol, exchange, token, alert #s
CONTRACTS = [
    ("SENSEX26O0173000CE", "BFO", "887092", "1,3"),
    ("NIFTY06OCT2623000CE", "NFO", "40731", "2"),
    ("NIFTY06OCT2623100CE", "NFO", "40741", "4"),
    ("NIFTY06OCT2623050CE", "NFO", "40735", "5"),
    ("NIFTY06OCT2623200CE", "NFO", "40745", "6"),
    ("NIFTY06OCT2622700CE", "NFO", "40710", "7"),
    ("NIFTY06OCT2622650CE", "NFO", "40704", "8"),
    ("NIFTY06OCT2622750CE", "NFO", "40712", "9"),
    ("SENSEX26O0874000CE", "BFO", "889151", "10"),
    ("NIFTY06OCT2622600CE", "NFO", "40701", "11"),
]
TFS = [("1m", "ONE_MINUTE"), ("5m", "FIVE_MINUTE"), ("15m", "FIFTEEN_MINUTE"), ("1h", "ONE_HOUR")]

auth = AngelAuth()
if not auth.login():
    sys.exit("login failed")
api = AngelCandleData(auth.smart_api)

summary = []
data_all = {}
for sym, exch, tok, alerts in CONTRACTS:
    for tf, interval in TFS:
        candles = api.get_candle_data(exch, tok, interval, FROM, TO, verbose=False)
        n = len(candles) if candles else 0
        first = candles[0]["timestamp"] if n else ""
        last = candles[-1]["timestamp"] if n else ""
        summary.append({"symbol": sym, "alerts": alerts, "tf": tf, "rows": n, "first": first, "last": last})
        print(f"{sym} {tf}: {n} rows {first} -> {last}", flush=True)
        if n:
            data_all[(sym, tf)] = candles
            with open(os.path.join(OUT, f"{sym}_{tf}.csv"), "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["timestamp", "open", "high", "low", "close", "volume"])
                w.writeheader()
                w.writerows(candles)

with open(os.path.join(OUT, "_summary.json"), "w") as f:
    json.dump(summary, f, indent=1)

try:
    from openpyxl import Workbook
    for sym, *_ in CONTRACTS:
        wb = Workbook(); wb.remove(wb.active)
        for tf, _ in TFS:
            c = data_all.get((sym, tf))
            if not c:
                continue
            ws = wb.create_sheet(tf)
            ws.append(["timestamp", "open", "high", "low", "close", "volume"])
            for r in c:
                ws.append([r["timestamp"], r["open"], r["high"], r["low"], r["close"], r["volume"]])
        if wb.sheetnames:
            wb.save(os.path.join(OUT, f"{sym}.xlsx"))
    print("xlsx written")
except ImportError:
    print("openpyxl not installed - CSV only")

