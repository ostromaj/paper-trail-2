"""Unit tests for the engine and the backtest harness. No packages needed:

    python3 tests/test_engine.py        (or: python3 -m pytest tests/)
"""
import os
import sys
from datetime import datetime

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "bot"))
sys.path.insert(0, os.path.join(ROOT, "backtest"))

import config as C  # noqa: E402
import engine  # noqa: E402
from clock import NY  # noqa: E402

MON_10AM = datetime(2026, 11, 9, 10, 0, tzinfo=NY).timestamp()


def _cand(symbol="SPY", kind="etf", price=100.0, stop=99.0, strategy="ORB", target=None):
    return {"symbol": symbol, "name": symbol, "kind": kind, "strategy": strategy,
            "strategy_name": "Test rule", "price": price, "stop": stop, "target": target,
            "checks": [{"label": "ok", "ok": True, "detail": ""}], "total": 1, "indicators": {},
            "exit_plan": "", "out_text": ""}


def test_thin_curve_actually_shrinks():
    curve = [[i, 100.0] for i in range(2501)]
    for i in range(3000):  # a couple of days of minute-by-minute appends
        curve.append([2501 + i, 100.0])
        curve = engine._thin_curve(curve, 2500)
    assert len(curve) <= 2500, len(curve)
    assert curve[-1][0] == 5500 and curve[0][0] < 100  # newest kept, oldest history still there


def test_stock_round_trip_costs_add_up():
    st = engine.new_state(MON_10AM)
    st["prices"]["SPY"] = {"price": 100.0}
    pos = engine.open_position(st, _cand(), MON_10AM)
    assert pos
    buy = st["trades"][-1]
    assert buy["slippage"] > 0
    engine.close_position(st, pos, 100.0, MON_10AM + 600, "test")
    sell = st["trades"][-1]
    # flat price: the whole loss is costs, and the reported costs match it
    assert sell["pnl"] < 0
    assert abs(-sell["pnl"] - sell["costs"]) < 1e-3, (sell["pnl"], sell["costs"])
    assert abs(st["cash"] - (100 + sell["pnl"])) < 1e-3
    s = engine.compute_stats(st)
    assert abs(s["costs"] - sell["costs"]) < 1e-6
    expected = buy["amount"] * 2 * C.STOCK_SLIPPAGE
    assert abs(sell["costs"] - expected) < 0.01


def test_crypto_costs_include_fee_and_slippage():
    st = engine.new_state(MON_10AM)
    pos = engine.open_position(st, _cand("BTC-USD", "crypto", 50000, 49000, "CDIP", 51000), MON_10AM)
    engine.close_position(st, pos, 50000, MON_10AM + 600, "test")
    sell = st["trades"][-1]
    per_side = C.CRYPTO_FEE + C.CRYPTO_SLIPPAGE
    assert abs(-sell["pnl"] / pos["cost"] - 2 * per_side) < 0.0005, sell["pnl"]


def test_streaks_and_strategy_breakdown():
    st = engine.new_state(MON_10AM)
    for pnl, strat in [(1, "ORB"), (2, "ORB"), (-1, "VWAP"), (-1, "ORB"), (-1, "VWAP")]:
        st["trades"].append({"action": "SELL", "pnl": pnl, "strategy": strat, "fee": 0, "costs": 0.1})
    s = engine.compute_stats(st)
    assert s["streak"] == -3 and s["best_win_streak"] == 2 and s["worst_loss_streak"] == 3
    assert s["by_strategy"]["ORB"]["trades"] == 3 and s["by_strategy"]["ORB"]["win_rate"] == 66.7
    assert s["profit_factor"] == 1.0


def test_max_drawdown():
    assert engine.max_drawdown([100, 110, 99, 120]) == -10.0
    assert engine.max_drawdown([100, None, 101]) == 0.0


class _Mkt:
    def __init__(self, daily):
        self.daily = daily

    def stock_daily(self, sym):
        return {"bars": self.daily}


def test_benchmark_backfills_old_runs_and_tracks_spy():
    start = MON_10AM - 2.5 * 3600  # Monday 7:30 AM
    st = engine.new_state(start)
    st["equity_curve"] += [[MON_10AM, 100.0], [MON_10AM + 86400, 101.0]]
    day = lambda d: datetime(2026, 11, d, 9, 30, tzinfo=NY).timestamp()  # noqa: E731
    daily = [{"t": day(6), "o": 95, "h": 96, "l": 94, "c": 95, "v": 1},
             {"t": day(9), "o": 100, "h": 101, "l": 99, "c": 102, "v": 1},
             {"t": day(10), "o": 102, "h": 105, "l": 101, "c": 104, "v": 1}]
    now = MON_10AM + 2 * 86400
    engine.update_benchmark(st, _Mkt(daily), now, {"SPY": {"price": 110.0, "bars": []}})
    b = st["benchmark"]
    assert b["start_price"] == 100  # Monday's open
    assert all(len(p) == 3 for p in st["equity_curve"])
    assert st["equity_curve"][-1][2] == 102.0  # Tuesday 10 AM -> Monday's close
    assert abs(engine.benchmark_value(st) - 110.0) < 1e-9
    s = engine.compute_stats(st)
    assert s["bh_return_pct"] == 10.0 and s["vs_bh_pct"] == -10.0


def test_halted_logs_once_a_day():
    import tests_sim_helpers as H
    st, m, restore = H.halted_state()
    try:
        for _ in range(5):
            st = engine.cycle(st, m)
            m.t += 60
    finally:
        restore()
    n = sum("daily loss limit" in a["text"] for a in st["activity"])
    assert n <= 1, n


def test_backtest_harness_runs_and_does_not_peek():
    import backtest
    import synth
    from market import HistoricalMarket
    hist = synth.make_history(3, 5)
    m = HistoricalMarket(hist)
    m.t = hist["5m"]["SPY"][100]["t"] + 20
    d = m.stock_intraday("SPY")
    assert all(b["t"] + 300 <= m.t for b in d["bars"])  # only finished bars
    c = m.crypto("BTC-USD")
    assert all(b["t"] + 900 <= m.t for b in c["bars"])
    scope = backtest.run_scope("all", "test", hist, True, True, "SPY", "5m")
    assert scope and set(scope["runs"]) == {"none", "normal", "double"}
    r0, r1, r2 = (scope["runs"][k]["return_pct"] for k in ("none", "normal", "double"))
    assert r0 >= r1 >= r2 or scope["runs"]["normal"]["trades"] == 0  # more costs never help
    assert scope["verdict_text"]


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("ok  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, "->", repr(e))
    sys.exit(1 if fails else 0)
