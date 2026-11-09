#!/bin/bash
# Full auto paper flow helper
# Usage:
#   ./daily_flow.sh set SYM1 SYM2   # after 8:15 news
#   ./daily_flow.sh enter           # at 9:15 open entry
#   ./daily_flow.sh check           # LTP / target hit
#   ./daily_flow.sh status

set -e
cd /home/ec2-user/angel_algo/paper_trading
export PYTHONPATH=/home/ec2-user/angel_algo:${PYTHONPATH:-}

CMD=${1:-status}

case "$CMD" in
  set)
    shift
    python3 auto_paper.py set "$@"
    ;;
  enter)
    python3 auto_paper.py enter
    ;;
  check)
    python3 auto_paper.py check
    ;;
  status)
    curl -s http://127.0.0.1:8081/health || echo 'UI down'
    echo
    python3 -c "import json; print('picks', json.load(open('today_picks.json')) if __import__('os').path.exists('today_picks.json') else {})"
    python3 -c "import json; h=json.load(open('trade_history.json')) if __import__('os').path.exists('trade_history.json') else []; print('history', len(h), 'last', h[-1] if h else None)"
    ;;
  *)
    echo "Usage: $0 set SYM1 SYM2 | enter | check | status"
    exit 1
    ;;
esac
