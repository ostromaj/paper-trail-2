"""Made-up price history in the archive format, for testing the backtest harness offline.
Random walks: they have NO edge to find, so a good harness should show roughly zero before
costs and a loss after them. Never treat synthetic results as evidence about the strategy."""
import math
import random
import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bot"))

import config as C  # noqa: E402
from clock import NY, is_trading_day  # noqa: E402

BASE = {"SPY": 680, "QQQ": 610, "IWM": 245, "AAPL": 270, "MSFT": 510, "NVDA": 190, "AMZN": 240,
        "META": 720, "GOOGL": 280, "TSLA": 430, "AMD": 240}
COINS = {"BTC-USD": 104000, "ETH-USD": 3500, "SOL-USD": 165}


def _walk(rng, p, t0, n, step, vol):
    bars, drift = [], 0.0
    for k in range(n):
        drift = 0.9 * drift + rng.gauss(0, vol / 30)  # tiny, short-lived trends
        o = p
        c = p * math.exp(drift + rng.gauss(0, vol))
        h = max(o, c) * (1 + abs(rng.gauss(0, vol / 2)))
        lo = min(o, c) * (1 - abs(rng.gauss(0, vol / 2)))
        v = abs(rng.gauss(1000, 300)) * (3 if abs(c / o - 1) > 2 * vol else 1)
        bars.append({"t": int(t0 + k * step), "o": o, "h": h, "l": lo, "c": c, "v": v})
        p = c
    return bars


def make_history(days=30, seed=7, end=datetime(2026, 11, 6, tzinfo=NY)):
    rng = random.Random(seed)
    # trading days ending at `end`, plus 20 earlier ones for daily-only warm-up
    d, tdays = end.date(), []
    while len(tdays) < days + 20:
        if is_trading_day(d):
            tdays.append(d)
        d -= timedelta(days=1)
    tdays.reverse()
    hist = {"5m": {}, "1d": {}, "15m": {}}
    for sym, p in BASE.items():
        five, daily = [], []
        for i, day in enumerate(tdays):
            t0 = datetime(day.year, day.month, day.day, 9, 30, tzinfo=NY).timestamp()
            bars = _walk(rng, p, t0, 78, 300, 0.0012)
            bars[0]["v"] *= rng.choice([0.8, 1.5, 2.5])
            daily.append({"t": int(t0), "o": bars[0]["o"], "h": max(b["h"] for b in bars),
                          "l": min(b["l"] for b in bars), "c": bars[-1]["c"], "v": sum(b["v"] for b in bars)})
            if i >= 20:
                five += bars
            p = bars[-1]["c"] * (1 + rng.gauss(0, 0.004))
        hist["5m"][sym], hist["1d"][sym] = five, daily
    first = datetime(tdays[20].year, tdays[20].month, tdays[20].day, tzinfo=NY).timestamp() - 4 * 86400
    last = datetime(end.year, end.month, end.day, tzinfo=NY).timestamp() + 86400
    n = int((last - first) / 900)
    for sym, p in COINS.items():
        hist["15m"][sym] = _walk(rng, p, first - first % 900, n, 900, 0.004)
    return hist
