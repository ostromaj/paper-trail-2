"""Checks the live data feeds and replays the most recent trading day's real
5-minute bars through the stock rules.  python3 bot/selftest.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import config as C  # noqa: E402
import strategies as S  # noqa: E402
from clock import date_str, nice_datetime  # noqa: E402
from data import LiveMarket  # noqa: E402
from indicators import atr  # noqa: E402

m = LiveMarket()
ok = True
for sym in ["SPY", "NVDA"]:
    d = m.stock_intraday(sym)
    dd = m.stock_daily(sym)
    if not d or not d["bars"] or not dd:
        print(f"FAIL {sym}: no Yahoo data")
        ok = False
        continue
    last_day = date_str(d["bars"][-1]["t"])
    day_bars = [b for b in d["bars"] if date_str(b["t"]) == last_day]
    prior_daily = [b for b in dd["bars"] if date_str(b["t"]) < last_day]
    daily = {"atr": atr(prior_daily[-30:], 14), "prev_close": prior_daily[-1]["c"]}
    print(f"OK   {sym} via {d['source']}: {len(d['bars'])} 5-min bars, last day {last_day} ({len(day_bars)} bars, "
          f"first {nice_datetime(day_bars[0]['t'])}, last {nice_datetime(day_bars[-1]['t'])}), price {d['price']}, "
          f"daily ATR {daily['atr']:.2f}, prev close {daily['prev_close']}, open vols {[round(v) for v in d['open_vols']]}")
    fired = set()
    for b in day_bars:
        now = b["t"] + 300
        sub = {"bars": [x for x in d["bars"] if x["t"] + 300 <= now], "price": b["c"]}
        sub["open_vols"] = d["open_vols"]
        for c in S.evaluate_stock(sym, sub, daily, now, fired):
            if c["ready"]:
                fired.add((c["strategy"], sym))
                print(f"     replay: {c['strategy_name']} would BUY at {nice_datetime(now)} @ {c['price']:.2f}, stop {c['stop']:.2f}")
    if not fired:
        print("     replay: no setups fired that day (normal on many days)")
for sym in C.CRYPTO:
    d = m.crypto(sym)
    print(("OK  " if d else "FAIL"), sym, f"{len(d['bars'])} bars via {d.get('source')}, price {d['price']}" if d else "")
    ok = ok and bool(d)
sys.exit(0 if ok else 1)
