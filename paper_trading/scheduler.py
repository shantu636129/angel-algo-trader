#!/usr/bin/env python3
"""
Background scheduler for auto paper trading (no crontab needed).
- 9:15 IST Mon-Fri: auto enter Top 2 from today_picks.json
- Every 15 min 9:30-15:15 IST: check targets
Run: nohup python3 scheduler.py >> /tmp/paper_scheduler.log 2>&1 &
"""

import time
import subprocess
import os
from datetime import datetime
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
BASE = os.path.dirname(os.path.abspath(__file__))
ENTERED_FLAG = os.path.join(BASE, ".entered_date")

def now_ist():
    return datetime.now(IST)

def log(msg):
    print(f"[{now_ist().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)

def run_cmd(args):
    try:
        r = subprocess.run(
            args, cwd=BASE, capture_output=True, text=True, timeout=90
        )
        out = (r.stdout or "") + (r.stderr or "")
        log(out.strip()[:500] if out else f"exit={r.returncode}")
        return r.returncode == 0
    except Exception as e:
        log(f"error: {e}")
        return False

def already_entered_today():
    d = now_ist().strftime("%Y-%m-%d")
    if os.path.exists(ENTERED_FLAG):
        with open(ENTERED_FLAG) as f:
            return f.read().strip() == d
    return False

def mark_entered():
    with open(ENTERED_FLAG, "w") as f:
        f.write(now_ist().strftime("%Y-%m-%d"))

def main():
    log("Scheduler started (9:15 enter + periodic check)")
    last_check_slot = None
    while True:
        n = now_ist()
        wd = n.weekday()  # 0=Mon
        if wd <= 4:  # Mon-Fri
            # Entry window 9:15 - 9:25
            if ((n.hour == 9 and n.minute >= 15) or (10 <= n.hour <= 14) or (n.hour == 15 and n.minute <= 15)):
                log("Running auto enter...")
                run_cmd(["python3", "auto_paper.py", "enter"])
                log("Enter attempt finished (per-symbol skip if already filled or LTP>open)")

            # Check slots every 15 min from 9:30 to 15:15
            if (n.hour == 9 and n.minute >= 30) or (10 <= n.hour <= 14) or (n.hour == 15 and n.minute <= 15):
                slot = (n.hour, n.minute // 15)
                if slot != last_check_slot and n.minute % 15 <= 1:
                    last_check_slot = slot
                    log("Running target check...")
                    run_cmd(["python3", "auto_paper.py", "check"])

        time.sleep(20)

if __name__ == "__main__":
    main()
