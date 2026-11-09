#!/usr/bin/env python3
"""
Background loop for Option A auto paper trading.
- Every 15 min during market hours: run hit tracker (mark +2% HIT)
- If top2_today.txt exists with SYMBOL1,SYMBOL2 and no entry yet today, run auto entry

Start: nohup python3 run_auto_loop.py >> /tmp/auto_loop.log 2>&1 &
"""

import os
import sys
import time
import subprocess
from datetime import datetime
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
BASE = os.path.dirname(os.path.abspath(__file__))
TOP2_FILE = os.path.join(BASE, "top2_today.txt")

def now_ist():
    return datetime.now(IST)

def market_hours():
    n = now_ist()
    if n.weekday() >= 5:
        return False
    mins = n.hour * 60 + n.minute
    return (9 * 60 + 15) <= mins <= (15 * 60 + 30)

def run(script, args=None):
    cmd = [sys.executable, os.path.join(BASE, script)]
    if args:
        cmd.extend(args)
    try:
        subprocess.run(cmd, cwd=BASE, timeout=120)
    except Exception as e:
        print(f"Error running {script}: {e}")

def try_auto_entry():
    if not os.path.exists(TOP2_FILE):
        return
    try:
        with open(TOP2_FILE) as f:
            line = f.read().strip().upper()
        if not line or line == "NONE":
            return
        parts = [p.strip() for p in line.replace("TOP2_SYMBOLS:", "").split(",") if p.strip()]
        if len(parts) < 1:
            return
        # Only enter once per day – auto_paper_entry skips duplicates
        run("auto_paper_entry.py", parts[:2])
    except Exception as e:
        print(f"auto entry error: {e}")

def main():
    print("Auto loop started", now_ist())
    while True:
        try:
            n = now_ist()
            if market_hours():
                # Near open: try entry from top2_today.txt
                if n.hour == 9 and 15 <= n.minute <= 45:
                    try_auto_entry()
                run("auto_hit_tracker.py")
            time.sleep(900)  # 15 minutes
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Loop error: {e}")
            time.sleep(60)

if __name__ == "__main__":
    main()
