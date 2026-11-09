"""
RSI-oversold + averaging portfolio backtest.
Shared cash pool: Rs 10,00,000. Max concurrent positions capped (real capital rotation).

Entry: RSI(14) crosses from >=30 down to <30 (fresh oversold signal), no open
       position on that stock, cash available -> buy tranche 1.
Averaging: if RSI dips further to <20 while position open and not yet averaged,
       OR price falls -10% from first entry -> add tranche 2 (if cash allows).
Exit (profit): RSI recovers back above 60 -> sell all, book profit.
Hard stop: price falls -20% from ORIGINAL entry -> exit at a loss (real risk cap).
"""
import json

cache = json.load(open('/home/ec2-user/angel_algo/data/candle_cache_rsi30.json'))

def compute_rsi_series(closes, n=14):
    rsis = [None] * len(closes)
    gains = []; losses = []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i-1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
        if i >= n:
            avg_gain = sum(gains[-n:]) / n
            avg_loss = sum(losses[-n:]) / n
            if avg_loss == 0:
                rsis[i] = 100
            else:
                rs = avg_gain / avg_loss
                rsis[i] = 100 - 100 / (1 + rs)
    return rsis

TOTAL_CAPITAL = 1_000_000
MAX_POSITIONS = 15
SLOT = TOTAL_CAPITAL / MAX_POSITIONS
AVG_PRICE_DD = 0.10   # -10% triggers averaging (if RSI also still weak)
AVG_RSI_TRIGGER = 20
HARD_STOP_DD = 0.20
EXIT_RSI = 60

stock_data = {}
all_dates = set()
for sym, candles in cache.items():
    if not candles or len(candles) < 30:
        continue
    closes = [c['close'] for c in candles]
    rsis = compute_rsi_series(closes)
    stock_data[sym] = {'candles': candles, 'rsi': rsis, 'idx_by_date': {c['date']: i for i, c in enumerate(candles)}}
    for c in candles:
        all_dates.add(c['date'])

timeline = sorted(all_dates)

cash = TOTAL_CAPITAL
open_positions = {}
trades_log = []
equity_curve = []

for date in timeline:
    # manage open positions
    for sym in list(open_positions.keys()):
        sd = stock_data[sym]
        if date not in sd['idx_by_date']:
            continue
        i = sd['idx_by_date'][date]
        c = sd['candles'][i]
        r = sd['rsi'][i]
        p = open_positions[sym]

        # hard stop
        if c['low'] <= p['hard_stop']:
            exit_price = p['hard_stop']
            proceeds = p['shares'] * exit_price
            cash += proceeds
            trades_log.append({'symbol': sym, 'entry_date': p['entry_date'], 'exit_date': date,
                                'entry_price': round(p['avg_price'], 2), 'exit_price': round(exit_price, 2),
                                'invested': round(p['invested'], 1), 'pnl_rs': round(proceeds - p['invested'], 1),
                                'pnl_pct': round((proceeds - p['invested']) / p['invested'] * 100, 2),
                                'averaged': p['averaged'], 'reason': 'hard_stop'})
            del open_positions[sym]
            continue

        # averaging trigger
        if not p['averaged'] and r is not None and r < AVG_RSI_TRIGGER and c['low'] <= p['entry_price'] * (1 - AVG_PRICE_DD) and cash >= SLOT:
            add_amount = SLOT
            add_price = c['close']
            add_shares = add_amount / add_price
            cash -= add_amount
            new_shares = p['shares'] + add_shares
            new_invested = p['invested'] + add_amount
            p['shares'] = new_shares
            p['invested'] = new_invested
            p['avg_price'] = new_invested / new_shares
            p['averaged'] = True

        # exit on RSI recovery
        if r is not None and r >= EXIT_RSI:
            exit_price = c['close']
            proceeds = p['shares'] * exit_price
            cash += proceeds
            trades_log.append({'symbol': sym, 'entry_date': p['entry_date'], 'exit_date': date,
                                'entry_price': round(p['avg_price'], 2), 'exit_price': round(exit_price, 2),
                                'invested': round(p['invested'], 1), 'pnl_rs': round(proceeds - p['invested'], 1),
                                'pnl_pct': round((proceeds - p['invested']) / p['invested'] * 100, 2),
                                'averaged': p['averaged'], 'reason': 'rsi_exit'})
            del open_positions[sym]

    # new entries
    if len(open_positions) < MAX_POSITIONS and cash >= SLOT:
        for sym, sd in stock_data.items():
            if sym in open_positions:
                continue
            if len(open_positions) >= MAX_POSITIONS or cash < SLOT:
                break
            if date not in sd['idx_by_date']:
                continue
            i = sd['idx_by_date'][date]
            if i == 0:
                continue
            r = sd['rsi'][i]
            r_prev = sd['rsi'][i-1]
            if r is None or r_prev is None:
                continue
            if r_prev >= 30 and r < 30:
                entry_price = sd['candles'][i]['close']
                shares = SLOT / entry_price
                cash -= SLOT
                open_positions[sym] = {
                    'entry_date': date, 'entry_price': entry_price, 'avg_price': entry_price,
                    'shares': shares, 'invested': SLOT, 'averaged': False,
                    'hard_stop': entry_price * (1 - HARD_STOP_DD),
                }

    mtm = 0
    for sym, p in open_positions.items():
        sd = stock_data[sym]
        if date in sd['idx_by_date']:
            i = sd['idx_by_date'][date]
            mtm += p['shares'] * sd['candles'][i]['close']
        else:
            mtm += p['invested']
    equity_curve.append({'date': date, 'equity': round(cash + mtm, 1), 'cash': round(cash, 1), 'open_positions': len(open_positions)})

# close remaining
last_date = timeline[-1]
for sym, p in list(open_positions.items()):
    sd = stock_data[sym]
    last_close = sd['candles'][-1]['close']
    proceeds = p['shares'] * last_close
    cash += proceeds
    trades_log.append({'symbol': sym, 'entry_date': p['entry_date'], 'exit_date': last_date,
                        'entry_price': round(p['avg_price'], 2), 'exit_price': round(last_close, 2),
                        'invested': round(p['invested'], 1), 'pnl_rs': round(proceeds - p['invested'], 1),
                        'pnl_pct': round((proceeds - p['invested']) / p['invested'] * 100, 2),
                        'averaged': p['averaged'], 'reason': 'open_at_end'})

final_equity = cash
print("===JSON_START===")
print(json.dumps({
    'total_capital': TOTAL_CAPITAL, 'max_positions': MAX_POSITIONS, 'slot': SLOT,
    'final_equity': round(final_equity, 1),
    'trades': trades_log,
    'equity_sample': equity_curve[::20]
}, indent=2))
print("===JSON_END===")
