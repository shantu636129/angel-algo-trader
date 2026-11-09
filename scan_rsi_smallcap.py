import json, time, io, contextlib
from core.auth import AngelAuth
from core.historical_data import AngelCandleData

candidates = json.load(open('/home/ec2-user/angel_algo/data/smallcap_quality_candidates.json'))
# dedupe
seen = set()
uniq = []
for c in candidates:
    if c['symbol'] not in seen:
        seen.add(c['symbol'])
        uniq.append(c)
candidates = uniq
print('unique candidates:', len(candidates))

def rsi(vals, n=14):
    gains = []; losses = []
    for i in range(1, len(vals)):
        diff = vals[i] - vals[i-1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    if len(gains) < n:
        return None
    avg_gain = sum(gains[-n:]) / n
    avg_loss = sum(losses[-n:]) / n
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)

auth = AngelAuth()
auth.login()
cd = AngelCandleData(auth.smart_api)

results = []
for c in candidates:
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cd.get_candle_data('NSE', c['token'], 'ONE_DAY', '2026-06-01 09:15', '2026-08-01 15:30')
        lines = buf.getvalue().splitlines()
        closes = []
        for l in lines:
            if '| O' in l:
                parts = l.split('|')
                ohlc = parts[1].strip().split()
                closes.append(float(ohlc[7]))
        if len(closes) < 15:
            continue
        r = rsi(closes)
        if r is not None:
            results.append({'symbol': c['symbol'], 'token': c['token'], 'mc_cr': c['mc_cr'],
                             'rsi': round(r, 1), 'last_close': closes[-1]})
    except Exception as e:
        pass
    time.sleep(0.28)

auth.logout_session()
results.sort(key=lambda x: x['rsi'])
print("===JSON_START===")
print(json.dumps(results, indent=2))
print("===JSON_END===")
