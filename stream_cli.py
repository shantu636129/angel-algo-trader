"""
stream_cli.py - Command-line tool for live WebSocket Streaming 2.0 ticks.

Usage:
    python3 stream_cli.py --symbol ZENTEC-EQ --exchange NSE --mode LTP
    python3 stream_cli.py --token 3045 --exchange NSE --mode QUOTE
    python3 stream_cli.py --symbol RELIANCE-EQ --exchange NSE --token 881 --token 3045 --mode LTP
    python3 stream_cli.py --symbol ZENTEC-EQ --exchange NSE --mode SNAPQUOTE --duration 60

Modes: LTP, QUOTE, SNAPQUOTE (default: LTP)
--duration: seconds to stream before disconnecting (default: run until Ctrl+C)

Multiple instruments can be streamed at once by repeating --token or --symbol.
"""

import sys
import time
import argparse
from core.auth import AngelAuth
from core.websocket_stream import AngelWebSocketStream
from utils.token_lookup import find_token_by_lookup


def resolve_tokens(args):
    """Returns a dict like {"NSE": ["3045", "881"], ...} from --token/--symbol args."""
    exchange_tokens = {}

    for tok in args.token or []:
        exch = (args.exchange or "NSE").upper()
        exchange_tokens.setdefault(exch, []).append(tok)

    for sym in args.symbol or []:
        matches = find_token_by_lookup(sym, exch_seg=args.exchange, limit=5)
        if not matches:
            print("No token found for symbol '" + sym + "' on " + (args.exchange or "any exchange") + ".")
            sys.exit(1)
        chosen = matches[0]
        if len(matches) > 1:
            print("Multiple matches for '" + sym + "', using: " + str(chosen.get("symbol")))
        exchange_tokens.setdefault(chosen.get("exch_seg"), []).append(chosen.get("token"))

    if not exchange_tokens:
        print("Provide at least one --token or --symbol.")
        sys.exit(1)

    return exchange_tokens


def main():
    parser = argparse.ArgumentParser(description="Stream live ticks via WebSocket Streaming 2.0.")
    parser.add_argument("--token", action="append", help="Symbol token (repeatable), e.g. --token 3045")
    parser.add_argument("--symbol", action="append", help="Instrument name to look up (repeatable), e.g. --symbol ZENTEC-EQ")
    parser.add_argument("--exchange", default="NSE", help="Exchange for --token entries / lookup filter for --symbol (default NSE)")
    parser.add_argument("--mode", default="LTP", choices=["LTP", "QUOTE", "SNAPQUOTE"], help="Subscription mode (default LTP)")
    parser.add_argument("--duration", type=int, help="Seconds to stream before disconnecting (default: run until Ctrl+C)")
    args = parser.parse_args()

    exchange_tokens = resolve_tokens(args)

    auth = AngelAuth()
    if not auth.login():
        print("Login failed.")
        sys.exit(1)

    stream = AngelWebSocketStream(auth.smart_api, auth.feed_token)

    def on_open():
        stream.subscribe(args.mode, exchange_tokens)

    stream.on_open = on_open
    stream.connect(threaded=True)

    try:
        if args.duration:
            time.sleep(args.duration)
        else:
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        print("Stopping stream...")
        stream.close()
        auth.logout_session()


if __name__ == "__main__":
    main()
