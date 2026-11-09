"""
analyze_selection.py - For each stock in the uploaded short-term-tips CSV,
pull ~40 days of daily candles ending on its entry date and compute the
technical features that were TRUE on the entry day, to find what the
analyst's stock-picking logic actually is (as opposed to the fixed
target/stop brackets already reverse-engineered).
"""
import csv
import json
import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, "/home/ec2-user/angel_algo")
os.chdir("/home/ec2-user/angel_algo")

from core.auth import AngelAuth
from core.historical_data import AngelCandleData
from utils.token_lookup import find_token

ROWS = """Aarti Pharmalabs Ltd|905.00|12 Aug
Aeroflex Industries Ltd|437.30|12 Aug
Afcons Infrastructure Ltd|276.00|12 Aug
Akums Drugs and Pharmaceuticals|760.00|12 Aug
Amara Raja Energy & Mobility Ltd|974.10|12 Aug
Amber Enterprises India Ltd|7056.00|10 Aug
APL Apollo Tubes Ltd|2072.00|14 Aug
AU Small Finance Bank Ltd|1077.50|12 Aug
Azad Engineering Ltd|2595.00|14 Aug
Balaji Amines Ltd|2087.10|11 Aug
Balu Forge Industries Ltd|498.00|14 Aug
Bharat Dynamics Ltd|1308.00|10 Aug
BSE Ltd|3477.00|07 Aug
Carysil Ltd|1208.00|07 Aug
Clean Science and Technology Ltd|800.10|07 Aug
Container Corporation of India Ltd|511.60|11 Aug
Divi's Laboratories Ltd|8390.00|11 Aug
Engineers India Ltd|245.00|13 Aug
Glenmark Pharmaceuticals Ltd|2269.00|10 Aug
Graphite India Ltd|710.00|04 Aug
HEG Ltd|685.00|13 Aug
HFCL Ltd|207.00|04 Aug
Himadri Speciality Chemical Ltd|764.70|12 Aug
Indus Towers Ltd|379.00|12 Aug
Inox Wind Ltd|74.15|10 Aug
IPCA Laboratories Ltd|1880.00|13 Aug
Lodha Developers Ltd|1216.00|11 Aug
LTIMindtree Ltd|4778.00|10 Aug
Oil India Ltd|454.00|10 Aug
Pidilite Industries Ltd|1650.00|05 Aug
Sandhar Technologies Ltd|621.00|11 Aug
Sterlite Technologies Ltd|644.00|12 Aug
Sumitomo Chemical India Ltd|560.00|10 Aug
Syrma SGS Technology Ltd|1487.30|10 Aug
Tata Motors|454.50|10 Aug
Tejas Networks Ltd|520.00|10 Aug
Voltas Ltd|1276.70|12 Aug
"""

SYMBOL_MAP = {
    "Aarti Pharmalabs Ltd": "AARTIPHARM", "Aeroflex Industries Ltd": "AEROFLEX",
    "Afcons Infrastructure Ltd": "AFCONS", "Akums Drugs and Pharmaceuticals": "AKUMS",
    "Amara Raja Energy & Mobility Ltd": "ARE&M", "Amber Enterprises India Ltd": "AMBER",
    "APL Apollo Tubes Ltd": "APLAPOLLO", "AU Small Finance Bank Ltd": "AUBANK",
    "Azad Engineering Ltd": "AZAD", "Balaji Amines Ltd": "BALAMINES",
    "Balu Forge Industries Ltd": "BALUFORGE", "Bharat Dynamics Ltd": "BDL",
    "BSE Ltd": "BSE", "Carysil Ltd": "CARYSIL",
    "Clean Science and Technology Ltd": "CLEAN", "Container Corporation of India Ltd": "CONCOR",
    "Divi's Laboratories Ltd": "DIVISLAB", "Engineers India Ltd": "ENGINERSIN",
    "Glenmark Pharmaceuticals Ltd": "GLENMARK", "Graphite India Ltd": "GRAPHITE",
    "HEG Ltd": "HEG", "HFCL Ltd": "HFCL",
    "Himadri Speciality Chemical Ltd": "HSCL", "Indus Towers Ltd": "INDUSTOWER",
    "Inox Wind Ltd": "INOXWIND", "IPCA Laboratories Ltd": "IPCALAB",
    "Lodha Developers Ltd": "LODHA",
    "LTIMindtree Ltd": "LTIM", "Oil India Ltd": "OIL",
    "Pidilite Industries Ltd": "PIDILITIND", "Sandhar Technologies Ltd": "SANDHAR",
    "Sterlite Technologies Ltd": "STLTECH", "Sumitomo Chemical India Ltd": "SUMICHEM",
    "Syrma SGS Technology Ltd": "SYRMA", "Tata Motors": "TATAMOTORS",
    "Tejas Networks Ltd": "TEJASNET", "Voltas Ltd": "VOLTAS",
}

MONTH2026 = {"04 Aug": "2026-08-04", "05 Aug": "2026-08-05", "07 Aug": "2026-08-07",
             "10 Aug": "2026-08-10", "11 Aug": "2026-08-11", "12 Aug": "2026-08-12",
             "13 Aug": "2026-08-13", "14 Aug": "2026-08-14"}


def resolve_token(symbol):
    hits = find_token(symbol=f"{symbol}-EQ", exch_seg="NSE", limit=1)
    if hits:
        return hits[0]["token"]
    hits = find_token(name=symbol, exch_seg="NSE", limit=1)
    if hits:
        return hits[0]["token"]
    return None


def rsi14(closes):
    if len(closes) < 15:
        return None
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [d for d in deltas[-14:] if d > 0]
    losses = [-d for d in deltas[-14:] if d < 0]
    avg_gain = sum(gains) / 14
    avg_loss = sum(losses) / 14
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 1)


def main():
    auth = AngelAuth()
    if not auth.login():
        print(json.dumps({"error": "login failed"}))
        return
    cd = AngelCandleData(auth.smart_api)

    results = []
    for line in ROWS.strip().split("\n"):
        name, entry_price, date_key = line.split("|")
        entry_price = float(entry_price)
        symbol = SYMBOL_MAP.get(name)
        entry_date = MONTH2026.get(date_key)
        if not symbol or not entry_date:
            continue
        token = resolve_token(symbol)
        if not token:
            results.append({"name": name, "error": "no token"})
            continue

        ed = datetime.strptime(entry_date, "%Y-%m-%d")
        fromdate = (ed - timedelta(days=70)).strftime("%Y-%m-%d 09:15")
        todate = ed.strftime("%Y-%m-%d 15:30")

        try:
            candles = cd.get_candle_data("NSE", token, "ONE_DAY", fromdate, todate, verbose=False)
        except Exception as e:
            results.append({"name": name, "error": str(e)})
            continue
        if not candles or len(candles) < 25:
            results.append({"name": name, "error": f"insufficient candles ({len(candles) if candles else 0})"})
            continue

        closes = [c["close"] for c in candles]
        vols = [c["volume"] for c in candles]
        today = candles[-1]
        prev = candles[-2]

        sma20 = sum(closes[-20:]) / 20
        sma50 = sum(closes[-50:]) / 50 if len(closes) >= 50 else None
        avgvol20 = sum(vols[-21:-1]) / 20
        high20 = max(c["high"] for c in candles[-21:-1])
        rsi_prior = rsi14(closes[:-1])

        gap_pct = round((today["open"] - prev["close"]) / prev["close"] * 100, 2)
        prior_chg_pct = round((prev["close"] - candles[-3]["close"]) / candles[-3]["close"] * 100, 2)
        vol_ratio = round(today["volume"] / avgvol20, 2) if avgvol20 else None
        dist_sma20 = round((prev["close"] - sma20) / sma20 * 100, 2)
        dist_sma50 = round((prev["close"] - sma50) / sma50 * 100, 2) if sma50 else None
        dist_20dhigh = round((entry_price - high20) / high20 * 100, 2)

        results.append({
            "name": name, "symbol": symbol, "entry_date": entry_date, "entry_price": entry_price,
            "gap_pct": gap_pct, "prior_day_chg_pct": prior_chg_pct, "vol_ratio_vs_20d": vol_ratio,
            "rsi14_prior_close": rsi_prior, "dist_from_20sma_pct": dist_sma20,
            "dist_from_50sma_pct": dist_sma50, "dist_from_20d_high_pct": dist_20dhigh,
        })

    auth.logout_session()
    out_path = "/home/ec2-user/angel_algo/data/_selection_analysis.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
