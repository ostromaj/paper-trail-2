"""New York market-hours helpers."""
from datetime import datetime, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

from config import HOLIDAYS, EARLY_CLOSES

NY = ZoneInfo("America/New_York")


def ny(ts):
    return datetime.fromtimestamp(ts, NY)


@lru_cache(maxsize=65536)  # the same bar times get formatted over and over
def hm(ts):
    return ny(ts).strftime("%H:%M")


@lru_cache(maxsize=65536)
def date_str(ts):
    return ny(ts).strftime("%Y-%m-%d")


def nice_time(ts):
    """'10:05:12 AM ET' style."""
    return ny(ts).strftime("%-I:%M:%S %p ET")


def nice_datetime(ts):
    return ny(ts).strftime("%a %b %-d, %-I:%M %p ET")


def is_trading_day(d):
    """d is a date object."""
    return d.weekday() < 5 and d.strftime("%Y-%m-%d") not in HOLIDAYS


def close_hm(ts):
    return "13:00" if date_str(ts) in EARLY_CLOSES else "16:00"


def stock_market_open(ts):
    d = ny(ts)
    if not is_trading_day(d.date()):
        return False
    return "09:30" <= d.strftime("%H:%M") < close_hm(ts)


def in_window(ts, window):
    return window[0] <= hm(ts) < window[1]


def shift_for_early_close(ts, t):
    """On early-close days, pull afternoon times 3 hours earlier (4:00 PM -> 1:00 PM)."""
    if close_hm(ts) == "16:00" or t < "12:00":
        return t
    h, m = map(int, t.split(":"))
    return f"{h - 3:02d}:{m:02d}"


def next_open(ts):
    d = ny(ts)
    cand = d.replace(hour=9, minute=30, second=0, microsecond=0)
    if d >= cand:
        cand += timedelta(days=1)
    while not is_trading_day(cand.date()):
        cand += timedelta(days=1)
    return cand.timestamp()


def market_label(ts):
    if stock_market_open(ts):
        c = "1:00 PM" if close_hm(ts) == "13:00" else "4:00 PM"
        return {"open": True, "label": f"Stock market open · closes {c} ET"}
    nxt = ny(next_open(ts))
    return {"open": False, "label": f"Stock market closed · opens {nxt.strftime('%a %-I:%M %p')} ET",
            "next_open": nxt.timestamp()}
