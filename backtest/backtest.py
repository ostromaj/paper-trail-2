"""Backtest: replay saved price history through the REAL bot engine and score it honestly.

    python3 backtest/backtest.py --history history/bars.json.gz --out backtest.json
    python3 backtest/backtest.py --synthetic            # made-up prices, just to test the harness

What it does
  * Steps through time the way the live bot does (every 5 minutes in market hours, every
    15 minutes otherwise), calling the same engine.cycle() the live bot uses, with the same
    rules, sizing, stops, and costs from bot/config.py. The engine only ever sees bars that
    had already finished, so it can't peek at the future.
  * Runs each test three times: with no costs, with normal costs, and with double costs.
    A rule that only works with zero costs doesn't work.
  * Compares against simply buying and holding (SPY for the full test, Bitcoin for crypto).
  * Writes a JSON summary the dashboard shows, and prints a plain-English report.

Limits (also shown on the dashboard): the live bot checks every minute with 1-minute prices;
this checks every 5 minutes with 5-minute bars, so entries/exits land a little differently.
Stock history is only as long as the archive (it grows by a few days each run of the
"Backtest" workflow). Short tests prove very little either way.
"""
import argparse
import json
import math
import os
import sys
import time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "bot"))
sys.path.insert(0, HERE)

import config as C  # noqa: E402
import engine  # noqa: E402
from clock import NY, date_str, hm, is_trading_day, nice_datetime, close_hm  # noqa: E402
from market import HistoricalMarket, load_history  # noqa: E402

COST_LEVELS = [("none", 0.0), ("normal", 1.0), ("double", 2.0)]
BASE_COSTS = {k: getattr(C, k) for k in ("STOCK_SLIPPAGE", "STOCK_FEE", "CRYPTO_SLIPPAGE", "CRYPTO_FEE")}


def set_costs(mult):
    for k, v in BASE_COSTS.items():
        setattr(C, k, v * mult)


def check_times(start, end, stocks):
    """The moments the bot would check, 20 seconds after each bar closes."""
    t = start - start % 300 + 300 + 20
    out = []
    while t <= end:
        d = datetime.fromtimestamp(t, NY)
        session = stocks and is_trading_day(d.date()) and "09:30" <= hm(t) <= "16:05"
        if session or (t - 20) % 900 == 0:
            out.append(t)
        t += 300
    return out


def thin(points, n=400):
    if len(points) <= n:
        return points
    step = len(points) / n
    out = [points[int(i * step)] for i in range(n)]
    return out + [points[-1]] if out[-1] is not points[-1] else out


def bh_series(bars, times, secs):
    """$100 bought at the first price and held, valued at each time (bars: list of dicts)."""
    if not bars:
        return {}
    import bisect
    ts = [b["t"] for b in bars]
    first = None
    out = {}
    for t in times:
        i = bisect.bisect_right(ts, t - secs) - 1
        if i < 0:
            continue
        px = bars[i]["c"]
        if first is None:
            first = bars[max(i, 0)]["c"]
        out[t] = 100 * px / first
    return out


def t_stat(pnls):
    """How many 'standard errors' the average trade is from zero. Around 2+ starts to look like
    more than luck; under 1 is indistinguishable from coin flips."""
    n = len(pnls)
    if n < 3:
        return None
    m = sum(pnls) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in pnls) / (n - 1))
    return round(m / (sd / math.sqrt(n)), 2) if sd > 0 else None


def run_once(hist, start, end, stocks, crypto, mult, bh_bars):
    set_costs(mult)
    m = HistoricalMarket(hist, stocks=stocks, crypto=crypto)
    times = check_times(start, end, stocks)
    m.t = times[0]
    st = engine.new_state(m.t)
    bh = bh_series(bh_bars, times, 300 if stocks else 900)
    curve = []
    for t in times:
        m.t = t
        st = engine.cycle(st, m)
        curve.append([t, round(engine.equity(st), 4), round(bh[t], 4) if t in bh else None])
    # close anything still open at the last price, so the result is all cash
    for p in list(st["positions"]):
        px = st["prices"].get(p["symbol"], {}).get("price", p["entry_price"])
        engine.close_position(st, p, px, m.t, "Backtest ended")
    st["stats"] = engine.compute_stats(st)
    s = st["stats"]
    sells = [t for t in st["trades"] if t["action"] == "SELL"]
    pnls = [t["pnl"] for t in sells]
    final_bh = curve[-1][2]
    eq = [c[1] for c in curve]
    out = {
        "cost_level": mult,
        "final_equity": round(engine.equity(st), 2),
        "return_pct": round(engine.equity(st) - 100, 2),
        "trades": len(sells),
        "win_rate": s["win_rate"],
        "profit_factor": s["profit_factor"],
        "avg_trade": s["expectancy"],
        "t_stat": t_stat(pnls),
        "costs": s["costs"],
        "max_drawdown_pct": engine.max_drawdown(eq),
        "bh_return_pct": round(final_bh - 100, 2) if final_bh else None,
        "bh_max_drawdown_pct": engine.max_drawdown([c[2] for c in curve]) if final_bh else None,
        "by_strategy": s["by_strategy"],
    }
    if mult == 1.0:
        out["curve"] = thin(curve)
        out["recent_trades"] = [
            {k: t.get(k) for k in ("decided_at", "symbol", "strategy", "pnl", "pnl_pct", "held_minutes", "reason", "costs")}
            for t in sells[-40:]]
    return out


def verdict(normal, none):
    n = normal["trades"]
    if n < 30:
        return ("too-few", f"Only {n} trade{'s' if n != 1 else ''} in this test. You need roughly 30 or more before "
                           "the results mean much, so treat this as a first look, not a verdict.")
    r, bh = normal["return_pct"], normal["bh_return_pct"]
    ts = normal["t_stat"] or 0
    if r <= 0 and none["return_pct"] > 0:
        return ("costs-eat-it", f"Makes a little before costs ({none['return_pct']:+.2f}%) but loses after them "
                                f"({r:+.2f}%). The costs eat the edge.")
    if r <= 0:
        return ("no-edge", f"Loses money even before costs ({none['return_pct']:+.2f}%). No edge here.")
    if bh is not None and r < bh:
        return ("trails-bh", f"Makes money after costs ({r:+.2f}%) but less than just holding ({bh:+.2f}%).")
    if ts < 2:
        return ("maybe-luck", f"Beats holding after costs ({r:+.2f}% vs {bh:+.2f}%), but the trade-by-trade results "
                              f"are noisy (t = {ts}); that could still be luck.")
    return ("promising", f"Beats holding after costs ({r:+.2f}% vs {bh:+.2f}%) with fairly consistent trades "
                         f"(t = {ts}). Promising, but keep testing on new data.")


def run_scope(name, label, hist, stocks, crypto, bh_sym, bh_frame):
    if stocks:
        s5 = hist["5m"]
        days = sorted({date_str(b["t"]) for bars in s5.values() for b in bars})
        if len(days) < 2:
            return None
        first = min(b["t"] for bars in s5.values() for b in bars if date_str(b["t"]) == days[1])
        start = first - 2.5 * 3600  # 7:00 AM on the second day (the first day is warm-up)
        end = max(b["t"] for bars in s5.values() for b in bars) + 600
    else:
        c15 = hist["15m"]
        if not c15:
            return None
        start = max(bars[0]["t"] for bars in c15.values()) + 210 * 900  # indicator warm-up
        end = min(bars[-1]["t"] for bars in c15.values()) + 900
        if end - start < 2 * 86400:
            return None
    t0 = time.time()
    bh_bars = hist[bh_frame].get(bh_sym, [])
    runs = {lvl: run_once(hist, int(start), int(end), stocks, crypto, mult, bh_bars) for lvl, mult in COST_LEVELS}
    set_costs(1.0)
    v_key, v_text = verdict(runs["normal"], runs["none"])
    days = round((end - start) / 86400, 1)
    print(f"[{label}] {nice_datetime(start)} -> {nice_datetime(end)} ({days} days) in {time.time() - t0:.0f}s")
    for lvl, _ in COST_LEVELS:
        r = runs[lvl]
        print(f"   costs {lvl:6s}: {r['return_pct']:+6.2f}%  {r['trades']:3d} trades  win {r['win_rate']}%  "
              f"PF {r['profit_factor']}  maxDD {r['max_drawdown_pct']}%  t {r['t_stat']}  "
              f"| hold {bh_sym}: {r['bh_return_pct']}%")
    print("   verdict:", v_text)
    return {"name": name, "label": label, "start": int(start), "end": int(end),
            "start_text": nice_datetime(start), "end_text": nice_datetime(end), "days": days,
            "bh_symbol": bh_sym, "verdict": v_key, "verdict_text": v_text, "runs": runs}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--history", default="history/bars.json.gz")
    ap.add_argument("--out", default="backtest.json")
    ap.add_argument("--synthetic", action="store_true", help="use made-up prices (tests the harness only)")
    ap.add_argument("--days", type=int, default=30, help="synthetic only: trading days to generate")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    if args.synthetic:
        from synth import make_history
        hist = make_history(args.days, args.seed)
    else:
        hist = load_history(args.history)
    scopes = [s for s in (
        run_scope("all", "All five rules (stocks + crypto)", hist, True, True, C.BENCHMARK, "5m"),
        run_scope("crypto", "Crypto rules alone, longer history", hist, False, True, "BTC-USD", "15m"),
    ) if s]
    out = {
        "generated": int(time.time()), "generated_text": nice_datetime(time.time()),
        "synthetic": bool(args.synthetic),
        "costs": {k: v for k, v in BASE_COSTS.items()},
        "history": {f: {s: len(b) for s, b in hist[f].items()} for f in hist},
        "notes": ["Checks every 5 minutes on 5-minute bars (live bot: every minute).",
                  "Same rules, sizing, stops and costs as the live bot (bot/config.py).",
                  "Open trades are closed at the last price when the test ends."],
        "scopes": scopes,
    }
    with open(args.out, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    print("wrote", args.out)


if __name__ == "__main__":
    main()
