"""
Continuous news-watch loop. There is no cron on this box, so this is meant
to run as a persistent background process:

    cd /home/ec2-user/angel_algo
    nohup python3 scripts_adhoc/news_watch_loop.py >> logs/news_watch.log 2>&1 &
    disown
"""
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.news_alert import NewsWatcher
from core.telegram_alert import TelegramAlert

WATCHLIST = ["SBIN-EQ", "INFY-EQ", "RELIANCE-EQ"]
POLL_SECONDS = 900  # 15 min


def main():
    telegram = TelegramAlert()
    watcher = NewsWatcher(WATCHLIST, telegram=telegram)

    primed = watcher.prime()
    print(f"[NEWS-LOOP] Primed {primed} existing headline(s) silently", flush=True)

    print(f"[NEWS-LOOP] Watching {WATCHLIST} every {POLL_SECONDS}s", flush=True)
    telegram.send(
        f"\U0001F7E2 News watcher started \u2014 {len(WATCHLIST)} symbols, every {POLL_SECONDS // 60} min",
        parse_mode=None,
    )

    while True:
        try:
            n = watcher.run_once()
            if n:
                print(f"[NEWS-LOOP] {datetime.now()} \u2014 {n} new alert(s) sent", flush=True)
        except Exception as e:
            print(f"[NEWS-LOOP] \u274c {e}", flush=True)
            telegram.send_error_alert("news_watch_loop", str(e))
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
