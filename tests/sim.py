"""Offline test: runs the real engine against made-up price data, one 5-minute step at a time.

python3 tests/sim.py            (prints a summary, writes tests/sim_dashboard.json)
"""
import json
import math
import os
import random
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bot"))

import config as C  # noqa: E402
import engine  # noqa: E402
from clock import NY, stock_market_open  # noqa: E402


class FakeMarket:
    """Random-walk prices with a little trend so the rules actually fire."""

    def __init__(self, start_ts, seed=7):
        self.rng = random.Random(seed)
        self.t = start_ts
        self.stock = {}
        self.coins = {}
        base = {"SPY": 680, "QQQ": 610, "IWM": 245, "AAPL": 270, "MSFT": 510, "NVDA": 190, "AMZN": 240,
                "META": 720, "GOOGL": 280, "TSLA": 430, "AMD": 240}
        for s, p in base.items():
            self.stock[s] = self._walk_stock(p, start_ts)
        for s, p in {"BTC-USD": 104000, "ETH-USD": 3500, "SOL-USD": 165}.items():
            self.coins[s] = self._walk(p, start_ts - 400 * 900, start_ts + 6 * 86400, 900, 0.004)

    def _walk(self, p, t0, t1, step, vol):
        bars, t, drift = [], t0 - t0 % step, 0.0
        while t < t1:
            drift = 0.97 * drift + self.rng.gauss(0, vol / 6)
            o = p
            c = p * math.exp(drift + self.rng.gauss(0, vol))
            h = max(o, c) * (1 + abs(self.rng.gauss(0, vol / 2)))
            l = min(o, c) * (1 - abs(self.rng.gauss(0, vol / 2)))
            v = abs(self.rng.gauss(1000, 300)) * (3 if abs(c / o - 1) > 2 * vol else 1)
            bars.append({"t": t, "o": o, "h": h, "l": l, "c": c, "v": v})
            p, t = c, t + step
        return bars

    def _walk_stock(self, p, start):
        bars = []
        d = datetime.fromtimestamp(start, NY).replace(hour=9, minute=30, second=0)
        for day_off in range(-5, 6):
            day = datetime.fromtimestamp(d.timestamp() + day_off * 86400, NY)
            if day.weekday() >= 5:
                continue
            day = day.replace(hour=9, minute=30)
            t0 = day.timestamp()
            day_bars = self._walk(p, t0, t0 + 390 * 60, 300, 0.0012)
            for i, b in enumerate(day_bars):
                if i == 0:
                    b["v"] *= self.rng.choice([0.8, 1.5, 2.5])
            bars += day_bars
            p = day_bars[-1]["c"] * (1 + self.rng.gauss(0, 0.004))
        return bars

    def now(self):
        return self.t

    def _visible(self, bars, step):
        vis = [dict(b) for b in bars if b["t"] <= self.t]
        if vis and vis[-1]["t"] + step > self.t:  # in-progress bar: partial
            frac = (self.t - vis[-1]["t"]) / step
            b = vis[-1]
            b["c"] = b["o"] + (b["c"] - b["o"]) * frac
            b["h"] = max(b["o"], b["c"])
            b["l"] = min(b["o"], b["c"])
        return vis

    def stock_intraday(self, sym):
        vis = self._visible(self.stock[sym], 300)
        recent = [b for b in vis if b["t"] > self.t - 6 * 86400]
        return {"bars": recent, "price": recent[-1]["c"] if recent else None}

    def stock_daily(self, sym):
        bars, day = [], {}
        for b in self.stock[sym]:
            k = datetime.fromtimestamp(b["t"], NY).date()
            day.setdefault(k, []).append(b)
        for k in sorted(day):
            ds = day[k]
            bars.append({"t": ds[0]["t"], "o": ds[0]["o"], "h": max(x["h"] for x in ds),
                         "l": min(x["l"] for x in ds), "c": ds[-1]["c"], "v": sum(x["v"] for x in ds)})
        return {"bars": bars, "price": bars[-1]["c"]}

    def crypto(self, sym):
        vis = self._visible(self.coins[sym], 900)[-300:]
        return {"bars": vis, "price": vis[-1]["c"]}


def main():
    start = datetime(2026, 11, 9, 0, 2, tzinfo=NY).timestamp()  # Monday
    for seed in (7, 11, 23):
        m = FakeMarket(start, seed)
        st = engine.new_state(start)
        steps = 0
        while m.t < start + 3 * 86400:
            st = engine.cycle(st, m)
            json.loads(json.dumps(st))  # must stay JSON-safe
            assert st["cash"] >= -1e-6, "cash went negative"
            assert len(st["positions"]) <= C.MAX_OPEN_POSITIONS
            for p in st["positions"]:
                if p["kind"] != "crypto":
                    assert stock_market_open(m.t), f"stock held after close: {p['symbol']}"
            m.t += 300 + (60 if steps % 7 == 0 else 0)  # GitHub runs are sometimes late
            steps += 1
        s = st["stats"]
        acts = {}
        for t in st["trades"]:
            acts[t["action"]] = acts.get(t["action"], 0) + 1
        strat = {}
        for t in st["trades"]:
            if t["action"] == "BUY":
                strat[t["strategy"]] = strat.get(t["strategy"], 0) + 1
        print(f"seed {seed}: {steps} cycles, equity ${s['equity']:.2f} ({s['return_pct']:+.2f}%), "
              f"actions {acts}, buys by strategy {strat}, win rate {s['win_rate']}, open {len(st['positions'])}, "
              f"errors {len(st['errors'])}")
        # reset keeps history
        before = len(st["trades"])
        st2 = engine.reset(st, m.t)
        assert st2["cash"] == 100 and not st2["positions"] and not st2["trades"]
        assert st2["past_runs"][0]["run_number"] == 1 and len(st2["past_runs"][0]["trades"]) >= before
        st2 = engine.cycle(st2, m)
        st3 = engine.reset(st2, m.t + 60)
        assert [r["run_number"] for r in st3["past_runs"]] == [2, 1]
    out = os.path.join(os.path.dirname(__file__), "sim_dashboard.json")
    with open(out, "w") as f:
        json.dump(st, f, separators=(",", ":"))
    print("sample state:", out, f"{os.path.getsize(out) / 1024:.0f} KB")


if __name__ == "__main__":
    main()
