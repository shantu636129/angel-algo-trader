"""
order_stream_cli.py - Command-line tool for live order status updates via
WebSocket Order Status API (wss://tns.angelone.in/smart-order-update).

Usage:
    python3 order_stream_cli.py
    python3 order_stream_cli.py --duration 120

--duration: seconds to stream before disconnecting (default: run until Ctrl+C)

Note: max 3 concurrent connections per client code, per Angel One docs.
"""

import sys
import time
import argparse
from core.auth import AngelAuth
from core.order_update_stream import AngelOrderUpdateStream


def main():
    parser = argparse.ArgumentParser(description="Stream live order status updates.")
    parser.add_argument("--duration", type=int, help="Seconds to stream before disconnecting (default: run until Ctrl+C)")
    args = parser.parse_args()

    auth = AngelAuth()
    if not auth.login():
        print("Login failed.")
        sys.exit(1)

    stream = AngelOrderUpdateStream(auth.smart_api)
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
