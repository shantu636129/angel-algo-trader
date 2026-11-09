import sys, os, json, time
sys.path.insert(0, "/home/ec2-user/angel_algo")
os.chdir("/home/ec2-user/angel_algo")
from core.fundamentals import NSEFundamentals

SYMBOLS = ["AARTIPHARM","AEROFLEX","AFCONS","AKUMS","ARE&M","AMBER","APLAPOLLO","AUBANK",
"AZAD","BALAMINES","BALUFORGE","BDL","BSE","CARYSIL","CLEAN","CONCOR","DIVISLAB",
"ENGINERSIN","GLENMARK","GRAPHITE","HEG","HFCL","HSCL","INDUSTOWER","INOXWIND","IPCALAB",
"LODHA","LTIM","OIL","PIDILITIND","SANDHAR","STLTECH","SUMICHEM","SYRMA","TATAMOTORS",
"TEJASNET","VOLTAS"]

nf = NSEFundamentals(rate_limit_sleep=0.2)
out = []
for s in SYMBOLS:
    d = nf.get_fundamentals(s)
    if d:
        out.append(d)
    else:
        out.append({"symbol": s, "error": "no data"})

with open("/home/ec2-user/angel_algo/data/_fundamentals_check.json", "w") as f:
    json.dump(out, f, indent=2)
print(json.dumps(out, indent=2))
