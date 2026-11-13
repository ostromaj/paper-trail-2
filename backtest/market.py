"""A pretend market that replays saved price bars, so the real engine can be run over the past.

History file format (gzipped JSON):
  {"5m":  {"SPY": [[t, o, h, l, c, v], ...], ...},   regular-session 5-minute stock bars
   "1d":  {"SPY": [[t, o, h, l, c, v], ...], ...},   daily stock bars (t = 9:30 AM ET that day)
   "15m": {"BTC-USD": [[t, o, h, l, c, v], ...]}}     15-minute crypto bars
t is unix seconds at the START of the bar.
"""
import bisect
import gzip
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bot"))

from clock import date_str, hm  # noqa: E402

KEYS = ("t", "o", "h", "l", "c", "v")


def load_history(path):
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt") as f:
        raw = json.load(f)
    out = {}
    for frame in ("5m", "1d", "15m"):
        out[frame] = {}
        for sym, rows in (raw.get(frame) or {}).items():
            rows = sorted({int(r[0]): r for r in rows}.values(), key=lambda r: r[0])
            out[frame][sym] = [dict(zip(KEYS, (int(r[0]),) + tuple(float(x) for x in r[1:6]))) for r in rows]
    return out


def save_history(hist, path):
    raw = {frame: {sym: [[b["t"], b["o"], b["h"], b["l"], b["c"], b["v"]] for b in bars]
                   for sym, bars in syms.items()} for frame, syms in hist.items()}
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "wt") as f:
        json.dump(raw, f, separators=(",", ":"))


def merge_history(old, new):
    """Adds new bars to old ones (new wins on the same timestamp)."""
    out = {}
    for frame in ("5m", "1d", "15m"):
        out[frame] = {}
        for sym in set(old.get(frame, {})) | set(new.get(frame, {})):
            by_t = {b["t"]: b for b in old.get(frame, {}).get(sym, [])}
            by_t.update({b["t"]: b for b in new.get(frame, {}).get(sym, [])})
            out[frame][sym] = [by_t[t] for t in sorted(by_t)]
    return out


class HistoricalMarket:
    """Same interface the engine uses for live data (now / stock_intraday / stock_daily / crypto),
    but it only ever shows bars that had fully finished by `self.t`. No peeking at the future."""

    def __init__(self, hist, stocks=True, crypto=True):
        self.t = 0
        self.s5 = hist["5m"] if stocks else {}
        self.d1 = hist["1d"] if stocks else {}
        self.c15 = hist["15m"] if crypto else {}
        self._ts = {id(b): [x["t"] for x in b] for b in list(self.s5.values()) + list(self.d1.values()) + list(self.c15.values())}

    def now(self):
        return self.t

    def _upto(self, bars, secs):
        """Bars that finished at or before now."""
        i = bisect.bisect_right(self._ts[id(bars)], self.t - secs)
        return bars, i

    def stock_intraday(self, sym):
        bars = self.s5.get(sym)
        if not bars:
            return None
        bars, i = self._upto(bars, 300)
        if not i:
            return None
        ts = self._ts[id(bars)]
        j = bisect.bisect_left(ts, self.t - 8 * 86400)  # like the live 5-day feed (+ today)
        window = bars[j:i]
        today = date_str(self.t)
        days = {}
        for b in window:
            d = date_str(b["t"])
            if d != today:
                days.setdefault(d, []).append(b)
        open_vols = [d[0]["v"] for _, d in sorted(days.items()) if hm(d[0]["t"]) <= "09:33"][-4:]
        return {"bars": window, "price": window[-1]["c"], "open_vols": open_vols}

    def stock_daily(self, sym):
        bars = self.d1.get(sym)
        if not bars:
            return None
        ts = self._ts[id(bars)]
        i = bisect.bisect_right(ts, self.t)
        # today's daily bar is not finished; the engine ignores today's anyway
        window = [b for b in bars[max(0, i - 40):i] if date_str(b["t"]) < date_str(self.t)]
        if not window:
            return None
        return {"bars": window, "price": window[-1]["c"]}

    def crypto(self, sym):
        bars = self.c15.get(sym)
        if not bars:
            return None
        bars, i = self._upto(bars, 900)
        if not i:
            return None
        window = bars[max(0, i - 300):i]  # Coinbase gives the latest 300 candles
        return {"bars": window, "price": window[-1]["c"]}
