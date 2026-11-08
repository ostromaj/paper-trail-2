"""Entry point.  python3 bot/run.py --state dashboard.json [--reset]"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))

import engine  # noqa: E402
from data import LiveMarket  # noqa: E402


def load(path, now):
    try:
        with open(path) as f:
            st = json.load(f)
        if st.get("version") == 1:
            return st
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    print("No saved portfolio found. Starting fresh with $100.")
    return engine.new_state(now)


def save(state, path):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, separators=(",", ":"))
    os.replace(tmp, path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", default="dashboard.json")
    ap.add_argument("--reset", action="store_true")
    args = ap.parse_args()
    market = LiveMarket()
    now = market.now()
    state = load(args.state, now)
    if args.reset:
        state = engine.reset(state, now)
        print(f"Reset done. Now on run #{state['run_number']}.")
    else:
        t0 = time.time()
        state = engine.cycle(state, market)
        s = state["stats"]
        print(f"Cycle done in {time.time() - t0:.1f}s. Equity ${s['equity']:.2f} ({s['return_pct']:+.2f}%), "
              f"{len(state['positions'])} open, {s['trades_closed']} closed trades.")
        for e in state["errors"]:
            print("  warning:", e)
        for a in state["activity"][:3]:
            print("  ", a["time"], a["text"])
    save(state, args.state)


if __name__ == "__main__":
    main()
