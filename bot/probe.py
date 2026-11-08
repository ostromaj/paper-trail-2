import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from data import _cnbc_bars, _session, resample, _hm
from clock import date_str
for sym in ["NVDA", "AAPL", "QQQ", "TSLA"]:
    ones = _cnbc_bars(sym, "1D"); five = _cnbc_bars(sym, "5D")
    print(sym, "1D n", len(ones or []), "5D n", len(five or []))
    if ones:
        print("  1D first", [(_hm(b["t"]), b["t"] % 60) for b in ones[:4]], "last", _hm(ones[-1]["t"]), date_str(ones[-1]["t"]))
        s = _session(ones); r = resample(s, 300)
        print("  session", len(s), "resampled", len(r), [_hm(b["t"]) for b in r[:3]])
    if five:
        gaps = sorted({five[i+1]["t"] - five[i]["t"] for i in range(len(five)-1)})[:6]
        print("  5D gaps", gaps, "first", _hm(five[0]["t"]), "per-day", {d: sum(1 for b in five if date_str(b["t"]) == d) for d in sorted({date_str(b["t"]) for b in five})})
