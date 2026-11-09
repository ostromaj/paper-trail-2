"""Timing helper for the workflows.

python3 bot/window.py in-session   -> exit 0 if the all-day session loop should be running now
python3 bot/window.py sleep        -> prints seconds until the next check (every minute)
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))

from clock import close_hm, is_trading_day, ny  # noqa: E402

SESSION_START = "07:00"   # warm up early (crypto checks) so nothing is missed at 9:30
AFTER_CLOSE_MIN = 10      # keep going a few minutes after the bell to close any stock trades


def in_session(ts):
    d = ny(ts)
    if not is_trading_day(d.date()):
        return False
    h, m = map(int, close_hm(ts).split(":"))
    end = f"{h:02d}:{m + AFTER_CLOSE_MIN:02d}"
    return SESSION_START <= d.strftime("%H:%M") < end


def sleep_seconds(ts):
    """Check once a minute, 20 seconds past the minute (gives the data feeds time to post
    the candle that just closed)."""
    sec = int(ts) % 60
    wait = (20 - sec) % 60
    return wait if wait >= 10 else wait + 60


if __name__ == "__main__":
    now = time.time()
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "in-session":
        sys.exit(0 if in_session(now) else 1)
    if cmd == "sleep":
        print(sleep_seconds(now))
        sys.exit(0)
    print(__doc__)
    sys.exit(2)
