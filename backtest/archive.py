"""Builds up a local price archive for backtests, from the same free feeds the bot uses.

    python3 backtest/archive.py --history history/bars.json.gz [--crypto-days 90]

The free stock feed only goes back about 5 trading days at 5-minute detail, so stock history
grows a little every time this runs (the "Backtest" workflow runs it after each market day).
Crypto (Coinbase) can be fetched months back right away.
Needs internet access to CNBC and Coinbase (works on GitHub Actions).
"""
import argparse
import os
import sys
import time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "bot"))
sys.path.insert(0, HERE)

import config as C  # noqa: E402
from data import LiveMarket, _get_json  # noqa: E402
from market import load_history, merge_history, save_history  # noqa: E402


def coinbase_history(sym, days):
    """15-minute candles going back `days` (Coinbase returns at most 300 per request)."""
    end = int(time.time()) // 900 * 900
    start = end - days * 86400
    bars = {}
    t = start
    while t < end:
        t2 = min(t + 299 * 900, end)
        iso = lambda x: datetime.fromtimestamp(x, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: E731
        js = _get_json(f"https://api.exchange.coinbase.com/products/{sym}/candles?granularity=900"
                       f"&start={iso(t)}&end={iso(t2)}")
        for r in js if isinstance(js, list) else []:
            bars[int(r[0])] = {"t": int(r[0]), "l": r[1], "h": r[2], "o": r[3], "c": r[4], "v": r[5]}
        t = t2
        time.sleep(0.35)  # stay well under Coinbase's public rate limit
    return [bars[k] for k in sorted(bars)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--history", default="history/bars.json.gz")
    ap.add_argument("--crypto-days", type=int, default=90)
    args = ap.parse_args()
    old = load_history(args.history) if os.path.exists(args.history) else {"5m": {}, "1d": {}, "15m": {}}
    m = LiveMarket()
    new = {"5m": {}, "1d": {}, "15m": {}}
    now = time.time()
    for sym in C.STOCKS:
        d = m.stock_intraday(sym)
        if d and d["bars"]:
            # only finished bars (the newest one may still be forming during market hours)
            new["5m"][sym] = [b for b in d["bars"] if b["t"] + 300 <= now]
        dd = m.stock_daily(sym)
        if dd and dd["bars"]:
            new["1d"][sym] = dd["bars"][:-1] if dd["bars"][-1]["t"] > now - 7 * 3600 else dd["bars"]
        print(f"{sym}: {len(new['5m'].get(sym, []))} 5-min bars, {len(new['1d'].get(sym, []))} daily bars")
    for sym in C.CRYPTO:
        # first run: go back the full way; later runs: just the last few days
        have = old["15m"].get(sym)
        days = 4 if have and have[0]["t"] < now - (args.crypto_days - 5) * 86400 else args.crypto_days
        new["15m"][sym] = coinbase_history(sym, days)
        print(f"{sym}: {len(new['15m'][sym])} 15-min bars ({days} days)")
    hist = merge_history(old, new)
    os.makedirs(os.path.dirname(args.history) or ".", exist_ok=True)
    save_history(hist, args.history)
    for frame, syms in hist.items():
        n = {s: len(b) for s, b in syms.items()}
        print(f"archive {frame}: {sum(n.values())} bars across {len(n)} symbols")


if __name__ == "__main__":
    main()
