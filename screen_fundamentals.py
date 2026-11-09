"""
screen_fundamentals.py — walks the Nifty Total Market universe, fetches
current fundamentals for each stock via Yahoo Finance, applies a
quality/growth filter, and writes a filtered universe file in the SAME
format as data/nifty_total_market_750.json — so it's a drop-in replacement
for the --universe input of the existing backtest/live-scan scripts.

Resumable/incremental, same pattern as the other long-running scripts here.

IMPORTANT: this reflects TODAY's fundamentals only. Use the output for LIVE
/ forward trading decisions. Do not use it to filter a historical backtest
universe (see core/fundamentals.py docstring for why that would be
lookahead bias).

Writes:
  - data/fundamental_quality_universe.json   (same shape as nifty_total_market_750.json)
  - data/fundamental_screen_report.csv       (every stock's ratios + pass/fail + reasons)
  - data/fundamental_screen_checkpoint.json

Usage:
    python3 screen_fundamentals.py
    python3 screen_fundamentals.py --limit 50
    python3 screen_fundamentals.py --resume
    python3 screen_fundamentals.py --min-earnings-growth 0.15 --min-revenue-growth 0.10 --max-debt-to-equity 150
"""

import argparse
import csv
import json
import os

from core.fundamentals import NSEFundamentals

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UNIVERSE_PATH = os.path.join(BASE_DIR, "data", "nifty_total_market_750.json")
OUTPUT_UNIVERSE_PATH = os.path.join(BASE_DIR, "data", "fundamental_quality_universe.json")
REPORT_PATH = os.path.join(BASE_DIR, "data", "fundamental_screen_report.csv")
CHECKPOINT_PATH = os.path.join(BASE_DIR, "data", "fundamental_screen_checkpoint.json")

REPORT_FIELDS = [
    "symbol", "token", "passed", "reasons", "sector", "market_cap", "trailing_pe",
    "price_to_book", "return_on_equity", "debt_to_equity", "earnings_growth",
    "revenue_growth", "profit_margins", "current_price",
]


def load_universe(limit=None):
    with open(UNIVERSE_PATH) as f:
        universe = json.load(f)
    return universe[:limit] if limit else universe


def load_checkpoint():
    if os.path.exists(CHECKPOINT_PATH):
        with open(CHECKPOINT_PATH) as f:
            return json.load(f)
    return {"done_symbols": [], "passed": []}


def save_checkpoint(state):
    with open(CHECKPOINT_PATH, "w") as f:
        json.dump(state, f)


def append_report_row(row, first_write):
    mode = "w" if first_write else "a"
    with open(REPORT_PATH, mode, newline="") as f:
        writer = csv.DictWriter(f, fieldnames=REPORT_FIELDS)
        if first_write:
            writer.writeheader()
        writer.writerow(row)


def run(limit=None, resume=False, min_earnings_growth=0.15, min_revenue_growth=0.10,
        max_debt_to_equity=150, min_profit_margin=0.05, max_pe=None):
    universe = load_universe(limit)
    state = load_checkpoint() if resume else {"done_symbols": [], "passed": []}
    done_set = set(state["done_symbols"])
    remaining = [s for s in universe if s["symbol"] not in done_set]

    print(f"Universe: {len(universe)} symbols | Already done: {len(done_set)} | Remaining: {len(remaining)}")

    if not remaining:
        print("Nothing to do. Delete data/fundamental_screen_checkpoint.json to start fresh.")
        finalize(state, universe)
        return

    fetcher = NSEFundamentals(rate_limit_sleep=0.3)
    first_write = not os.path.exists(REPORT_PATH)

    for idx, stock in enumerate(remaining, 1):
        symbol = stock["symbol"]
        token = stock["token"]

        fundamentals = fetcher.get_fundamentals(symbol)
        passed, reasons = fetcher.passes_quality_filter(
            fundamentals,
            min_earnings_growth=min_earnings_growth,
            min_revenue_growth=min_revenue_growth,
            max_debt_to_equity=max_debt_to_equity,
            min_profit_margin=min_profit_margin,
            max_pe=max_pe,
        )

        row = {
            "symbol": symbol,
            "token": token,
            "passed": passed,
            "reasons": "; ".join(reasons),
            "sector": (fundamentals or {}).get("sector"),
            "market_cap": (fundamentals or {}).get("market_cap"),
            "trailing_pe": (fundamentals or {}).get("trailing_pe"),
            "price_to_book": (fundamentals or {}).get("price_to_book"),
            "return_on_equity": (fundamentals or {}).get("return_on_equity"),
            "debt_to_equity": (fundamentals or {}).get("debt_to_equity"),
            "earnings_growth": (fundamentals or {}).get("earnings_growth"),
            "revenue_growth": (fundamentals or {}).get("revenue_growth"),
            "profit_margins": (fundamentals or {}).get("profit_margins"),
            "current_price": (fundamentals or {}).get("current_price"),
        }
        append_report_row(row, first_write)
        first_write = False

        status = "✅ PASS" if passed else "❌ fail"
        print(f"[{idx}/{len(remaining)}] {symbol:<15} {status}  {'; '.join(reasons) if reasons else ''}")

        state["done_symbols"].append(symbol)
        if passed:
            state["passed"].append({"symbol": symbol, "token": token})

        if idx % 25 == 0 or idx == len(remaining):
            save_checkpoint(state)

    save_checkpoint(state)
    finalize(state, universe)


def finalize(state, universe):
    with open(OUTPUT_UNIVERSE_PATH, "w") as f:
        json.dump(state["passed"], f, indent=2)

    print("\n" + "=" * 60)
    print("FUNDAMENTAL SCREEN COMPLETE")
    print("=" * 60)
    print(f"Scanned: {len(state['done_symbols'])} / {len(universe)}")
    print(f"Passed quality filter: {len(state['passed'])}")
    print(f"Quality universe saved -> {OUTPUT_UNIVERSE_PATH}")
    print(f"Full report (every stock) -> {REPORT_PATH}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Screen the Nifty Total Market universe by fundamentals.")
    parser.add_argument("--limit", type=int, default=None, help="Only screen the first N symbols.")
    parser.add_argument("--resume", action="store_true", help="Skip symbols already in the checkpoint.")
    parser.add_argument("--min-earnings-growth", type=float, default=0.15)
    parser.add_argument("--min-revenue-growth", type=float, default=0.10)
    parser.add_argument("--max-debt-to-equity", type=float, default=150)
    parser.add_argument("--min-profit-margin", type=float, default=0.05)
    parser.add_argument("--max-pe", type=float, default=None)
    args = parser.parse_args()

    run(
        limit=args.limit,
        resume=args.resume,
        min_earnings_growth=args.min_earnings_growth,
        min_revenue_growth=args.min_revenue_growth,
        max_debt_to_equity=args.max_debt_to_equity,
        min_profit_margin=args.min_profit_margin,
        max_pe=args.max_pe,
    )
