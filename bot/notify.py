"""Phone alerts through ntfy (free app, no account): https://ntfy.sh

run.py writes the new trades to notify.json; cycle.sh calls this AFTER the portfolio is
safely saved, so a phone never gets an alert for a trade that didn't stick.

python3 bot/notify.py notify.json     send alerts for the trades in the file
python3 bot/notify.py --test          send a test alert
"""
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(__file__))

import config as C  # noqa: E402

DASHBOARD = "https://ostromaj.github.io/paper-trail-2/"


def topic():
    return os.environ.get("NTFY_TOPIC") or C.NTFY_TOPIC


def _money(x):
    if x is None:
        return "--"
    return f"${x:,.4f}" if 0 < abs(x) < 0.1 else f"${x:,.2f}"


def _name(t):
    return t["symbol"].split("-")[0] if t["kind"] == "crypto" else t["symbol"]


def _exit_text(t):
    if t["kind"] == "crypto":
        return "trailing stop" if t["strategy"] == "CBRK" else "12 hr max"
    return "sell by 3:55 PM" if t["strategy"] == "LATE" else "sell by 3:50 PM"


def format_trade(t):
    """Returns (title, body, priority, tags)."""
    when = t["decided_at_text"].split(", ", 1)[-1]
    if t["action"] == "BUY":
        title = f"BUY {_money(t['amount'])} of {_name(t)}"
        ex = _exit_text(t)
        out = f"Target {_money(t['target'])}" if t.get("target") else ex[0].upper() + ex[1:]
        body = (f"In {_money(t['price'])} · Stop {_money(t['stop'])} · {out}\n"
                f"{t['strategy_name']} · decided {when}\n{t.get('skip_if', '')}")
        return title, body, "high", "chart_with_upwards_trend"
    if t["action"] == "SELL":
        pnl = t.get("pnl") or 0
        title = f"SELL all {_name(t)} ({'+' if pnl >= 0 else '-'}${abs(pnl):.2f})"
        body = f"{t['reason']}\nAt {_money(t['price'])} · decided {when}"
        return title, body, "high", "white_check_mark" if pnl >= 0 else "small_red_triangle_down"
    title = f"Move {_name(t)} stop to {_money(t['stop'])}"
    body = f"{t['reason'][0].upper() + t['reason'][1:]} · decided {when}"
    return title, body, "default", "arrow_up"


def send(title, body, priority="default", tags=""):
    req = urllib.request.Request(
        f"https://ntfy.sh/{topic()}", data=body.encode(), method="POST",
        headers={"Title": title.encode("utf-8").decode("latin-1", "ignore"),
                 "Priority": priority, "Tags": tags, "Click": DASHBOARD + "#now"},
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.status


def main():
    if not C.NOTIFY_ACTIONS or not topic():
        return
    if sys.argv[1:] == ["--test"]:
        print("test alert:", send("Paper Trail 2 is connected",
                                   "You'll get a ping here whenever the bot buys, sells, or moves a stop.",
                                   "default", "bell"))
        return
    path = sys.argv[1] if len(sys.argv) > 1 else "notify.json"
    try:
        with open(path) as f:
            trades = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return
    for t in trades:
        if t["action"] not in C.NOTIFY_ACTIONS:
            continue
        try:
            title, body, pri, tags = format_trade(t)
            send(title, body, pri, tags)
            print("alert sent:", title)
        except Exception as e:  # an alert failing must never break trading
            print("alert failed:", e)


if __name__ == "__main__":
    main()
