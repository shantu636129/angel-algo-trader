"""
quote_cli.py — Reusable command-line tool for live market data, option Greeks,
top gainers/losers, PCR, OI buildup, historical candles, and historical OI.

Usage:
    python3 quote_cli.py --token 3045 --exchange NSE --mode FULL
    python3 quote_cli.py --symbol SBIN-EQ --exchange NSE --mode LTP
    python3 quote_cli.py --search RELIANCE            # find tokens by name
    python3 quote_cli.py --search NIFTY --exch-seg NFO --contains 24250CE
    python3 quote_cli.py --greeks --underlying TCS --expiry 25AUG2026
    python3 quote_cli.py --greeks --underlying TCS --expiry 25AUG2026 --strike 2400 --option-type CE
    python3 quote_cli.py --gainers-losers --datatype PercOIGainers --expirytype NEAR
    python3 quote_cli.py --pcr --symbol NIFTY
    python3 quote_cli.py --oi-buildup --datatype "Long Built Up" --expirytype NEAR
    python3 quote_cli.py --candles --token 99926000 --exchange NSE --interval ONE_HOUR \\
        --fromdate "2023-09-06 09:15" --todate "2023-09-06 15:30"
    python3 quote_cli.py --candles --symbol RELIANCE-EQ --exchange NSE --interval ONE_DAY \\
        --fromdate "2026-06-01 09:15" --todate "2026-07-30 15:30"
    python3 quote_cli.py --oi-history --token 46823 --exchange NFO --interval THREE_MINUTE \\
        --fromdate "2023-09-06 11:15" --todate "2023-09-06 12:00"

Modes: LTP, OHLC, FULL (default: FULL)
Greeks, Gainers/Losers, PCR, OI Buildup: NSE only.
Candles: NSE, NFO, BSE, BFO, MCX. OI History: NFO, BFO, MCX only.

Note on --symbol lookups: the scrip master's 'symbol' field (e.g. 'ZENTEC-EQ')
often differs from its 'name' field (e.g. 'ZENTEC'). --symbol tries an exact
match against 'symbol' first, then 'name', then falls back to a substring
match on 'symbol' — so either form works.
"""

import sys
import argparse
from core.auth import AngelAuth
from core.market_data import AngelMarketData
from core.option_greeks import AngelOptionGreeks
from core.market_insights import AngelGainersLosers, AngelPCR, AngelOIBuildup
from core.historical_data import AngelCandleData, AngelOIData
from utils.token_lookup import find_token, find_token_by_lookup


def resolve_token(args):
    """Figures out the token to query, either given directly or via lookup."""
    if args.token:
        return args.token, args.exchange or "NSE"

    if args.symbol:
        matches = find_token_by_lookup(args.symbol, exch_seg=args.exchange, limit=5)
        if not matches:
            print(f"❌ No token found for symbol '{args.symbol}' on {args.exchange or 'any exchange'}.")
            sys.exit(1)
        if len(matches) > 1:
            print(f"⚠️  Multiple matches for '{args.symbol}', using the first:")
            for m in matches:
                print(f"    {m.get('symbol')} | token {m.get('token')} | {m.get('exch_seg')}")
        chosen = matches[0]
        return chosen.get("token"), chosen.get("exch_seg")

    print("❌ Provide either --token (with --exchange) or --symbol.")
    sys.exit(1)


def run_greeks(args):
    if not args.underlying or not args.expiry:
        print("❌ --greeks requires both --underlying and --expiry (e.g. --expiry 25AUG2026).")
        sys.exit(1)

    auth = AngelAuth()
    if not auth.login():
        print("❌ Login failed.")
        sys.exit(1)

    greeks = AngelOptionGreeks(auth.smart_api)
    data = greeks.get_option_greeks(args.underlying, args.expiry)

    # Optional client-side filter to a single strike/option type
    if data and (args.strike or args.option_type):
        filtered = [
            d for d in data
            if (not args.strike or float(d.get("strikePrice", 0)) == float(args.strike))
            and (not args.option_type or d.get("optionType") == args.option_type.upper())
        ]
        if filtered:
            print(f"\nFiltered result ({len(filtered)} match(es)):")
            for item in filtered:
                print(f"  {item}")
        else:
            print("\nNo strikes matched the given --strike/--option-type filter.")

    auth.logout_session()


def run_gainers_losers(args):
    auth = AngelAuth()
    if not auth.login():
        print("❌ Login failed.")
        sys.exit(1)

    gl = AngelGainersLosers(auth.smart_api)
    gl.get_gainers_losers(datatype=args.datatype or "PercOIGainers", expirytype=args.expirytype or "NEAR")

    auth.logout_session()


def run_pcr(args):
    auth = AngelAuth()
    if not auth.login():
        print("❌ Login failed.")
        sys.exit(1)

    pcr = AngelPCR(auth.smart_api)
    pcr.get_pcr(symbol_filter=args.symbol)

    auth.logout_session()


def run_oi_buildup(args):
    auth = AngelAuth()
    if not auth.login():
        print("❌ Login failed.")
        sys.exit(1)

    oib = AngelOIBuildup(auth.smart_api)
    oib.get_oi_buildup(datatype=args.datatype or "Long Built Up", expirytype=args.expirytype or "NEAR")

    auth.logout_session()


def run_candles(args):
    if not args.interval or not args.fromdate or not args.todate:
        print("❌ --candles requires --interval, --fromdate, and --todate (format: 'yyyy-MM-dd hh:mm').")
        sys.exit(1)

    token, exchange = resolve_token(args)

    auth = AngelAuth()
    if not auth.login():
        print("❌ Login failed.")
        sys.exit(1)

    candles = AngelCandleData(auth.smart_api)
    candles.get_candle_data(exchange, token, args.interval, args.fromdate, args.todate)

    auth.logout_session()


def run_oi_history(args):
    if not args.interval or not args.fromdate or not args.todate:
        print("❌ --oi-history requires --interval, --fromdate, and --todate (format: 'yyyy-MM-dd hh:mm').")
        sys.exit(1)

    token, exchange = resolve_token(args)

    auth = AngelAuth()
    if not auth.login():
        print("❌ Login failed.")
        sys.exit(1)

    oi = AngelOIData(auth.smart_api)
    oi.get_oi_data(exchange, token, args.interval, args.fromdate, args.todate)

    auth.logout_session()


def main():
    parser = argparse.ArgumentParser(
        description="Fetch live quotes, search the scrip master, option Greeks, "
                     "top gainers/losers, PCR, OI buildup, historical candles, or historical OI."
    )
    parser.add_argument("--token", help="Symbol token, e.g. 3045")
    parser.add_argument("--symbol", help="Instrument name to look up (quote/candles/oi-history mode), or a filter substring (PCR mode), e.g. SBIN-EQ, NIFTY")
    parser.add_argument("--exchange", help="Exchange for the token/quote, e.g. NSE, BSE, NFO, BFO, MCX")
    parser.add_argument("--mode", default="FULL", choices=["LTP", "OHLC", "FULL"], help="Quote mode")
    parser.add_argument("--search", help="Search the scrip master by instrument name (no API call)")
    parser.add_argument("--exch-seg", dest="exch_seg", help="Filter search by exchange segment")
    parser.add_argument("--contains", help="Filter search by substring in the symbol field")

    # Option Greeks args
    parser.add_argument("--greeks", action="store_true", help="Fetch option Greeks instead of a quote")
    parser.add_argument("--underlying", help="Underlying stock/index name for Greeks, e.g. TCS, NIFTY")
    parser.add_argument("--expiry", help="Expiry date for Greeks, format DDMMMYYYY e.g. 25AUG2026")
    parser.add_argument("--strike", help="Optional: filter Greeks output to a single strike price")
    parser.add_argument("--option-type", dest="option_type", choices=["CE", "PE"], help="Optional: filter Greeks output to CE or PE")

    # Top Gainers/Losers args
    parser.add_argument("--gainers-losers", action="store_true", help="Fetch top OI/Price gainers or losers")
    parser.add_argument(
        "--datatype",
        help="For --gainers-losers: PercOIGainers/PercOILosers/PercPriceGainers/PercPriceLosers. "
             "For --oi-buildup: 'Long Built Up'/'Short Built Up'/'Short Covering'/'Long Unwinding'",
    )
    parser.add_argument("--expirytype", choices=["NEAR", "NEXT", "FAR"], help="Expiry bucket for gainers/losers or OI buildup (default NEAR)")

    # PCR args
    parser.add_argument("--pcr", action="store_true", help="Fetch Put-Call Ratio (use --symbol to filter, e.g. --symbol NIFTY)")

    # OI Buildup args
    parser.add_argument("--oi-buildup", action="store_true", help="Fetch OI Buildup classification (Long/Short Built Up, Short Covering, Long Unwinding)")

    # Historical Candle Data args
    parser.add_argument("--candles", action="store_true", help="Fetch historical OHLCV candle data (needs --token/--symbol, --exchange, --interval, --fromdate, --todate)")

    # Historical OI Data args
    parser.add_argument("--oi-history", action="store_true", help="Fetch historical OI time series (NFO/BFO/MCX only; needs --token/--symbol, --exchange, --interval, --fromdate, --todate)")

    # Shared historical args (candles + oi-history)
    parser.add_argument("--interval", help="ONE_MINUTE/THREE_MINUTE/FIVE_MINUTE/TEN_MINUTE/FIFTEEN_MINUTE/THIRTY_MINUTE/ONE_HOUR/ONE_DAY")
    parser.add_argument("--fromdate", help="Start date/time, format 'yyyy-MM-dd hh:mm', e.g. '2023-09-06 09:15'")
    parser.add_argument("--todate", help="End date/time, format 'yyyy-MM-dd hh:mm', e.g. '2023-09-06 15:30'")

    args = parser.parse_args()

    # --- Option Greeks mode ---
    if args.greeks:
        run_greeks(args)
        return

    # --- Top Gainers/Losers mode ---
    if args.gainers_losers:
        run_gainers_losers(args)
        return

    # --- PCR mode ---
    if args.pcr:
        run_pcr(args)
        return

    # --- OI Buildup mode ---
    if args.oi_buildup:
        run_oi_buildup(args)
        return

    # --- Historical Candle Data mode ---
    if args.candles:
        run_candles(args)
        return

    # --- Historical OI Data mode ---
    if args.oi_history:
        run_oi_history(args)
        return

    # --- Search-only mode: no login/API call needed ---
    if args.search:
        matches = find_token(name=args.search, exch_seg=args.exch_seg, symbol_contains=args.contains, limit=20)
        if not matches:
            print(f"No matches found for '{args.search}'.")
            return
        print(f"Found {len(matches)} match(es):")
        for m in matches:
            print(f"  {m.get('symbol'):<25} token={m.get('token'):<8} exch={m.get('exch_seg'):<5} expiry={m.get('expiry')}")
        return

    # --- Quote mode: needs a live login ---
    token, exchange = resolve_token(args)

    auth = AngelAuth()
    if not auth.login():
        print("❌ Login failed.")
        sys.exit(1)

    quote = AngelMarketData(auth.smart_api)
    quote.get_quote(args.mode, {exchange: [token]})

    auth.logout_session()


if __name__ == "__main__":
    main()
