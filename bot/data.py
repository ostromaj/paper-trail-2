"""Free market data with no API keys (all reachable from GitHub Actions).

Stocks/ETFs: CNBC chart feed. Today's 1-minute bars are rolled into clean 5-minute bars;
             the previous days come from the 5-day feed; daily bars give ATR and the
             official previous close. Nasdaq's 1-minute feed is the backup for today.
             (Yahoo Finance blocks GitHub's servers, so it isn't used.)
Crypto:      Coinbase Exchange public 15-minute candles, CNBC as the backup.
Every function returns None instead of crashing, so one bad feed never stops the bot.
"""
import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from clock import NY, close_hm, date_str

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15"
CNBC = "https://ts-api.cnbc.com/harmony/app/charts/{rng}.json?symbol={sym}"
CNBC_CRYPTO = {"BTC-USD": "BTC.CM=", "ETH-USD": "ETH.CM=", "SOL-USD": "SOL.CM="}


def _get_json(url, headers=None, tries=3):
    last = None
    for attempt in range(tries):
        try:
            h = {"User-Agent": UA, "Accept": "application/json"}
            h.update(headers or {})
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=15) as r:
                return json.loads(r.read().decode())
        except Exception as e:  # network hiccup, rate limit, etc.
            last = e
            time.sleep(1.5 * (attempt + 1))
    print(f"  data fetch failed: {url[:90]} ({last})")
    return None


def _hm(t):
    return datetime.fromtimestamp(t, NY).strftime("%H:%M")


def resample(bars, secs):
    """Roll small bars up into `secs`-long bars aligned to the clock."""
    out = {}
    for b in bars:
        k = b["t"] - b["t"] % secs
        if k not in out:
            out[k] = {"t": k, "o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"], "v": b["v"]}
        else:
            o = out[k]
            o["h"], o["l"], o["c"], o["v"] = max(o["h"], b["h"]), min(o["l"], b["l"]), b["c"], o["v"] + b["v"]
    return [out[k] for k in sorted(out)]


def _cnbc_bars(sym, rng):
    js = _get_json(CNBC.format(rng=rng, sym=sym))
    try:
        raw = js["barData"]["priceBars"]
    except (TypeError, KeyError):
        return None
    bars = []
    for b in raw:
        try:
            bars.append({"t": int(b["tradeTimeinMills"]) // 1000, "o": float(b["open"]), "h": float(b["high"]),
                         "l": float(b["low"]), "c": float(b["close"]), "v": float(b.get("volume") or 0)})
        except (TypeError, ValueError, KeyError):
            continue
    return bars or None


def _session(bars, start="09:30"):
    """Keep only regular-session bars (handles 1:00 PM early closes)."""
    return [b for b in bars if start <= _hm(b["t"]) < close_hm(b["t"])]


def _nasdaq_today(sym):
    kind = "etf" if sym in ("SPY", "QQQ", "IWM") else "stocks"
    js = _get_json(f"https://api.nasdaq.com/api/quote/{sym}/chart?assetclass={kind}&charttype=rs",
                   {"Origin": "https://www.nasdaq.com", "Referer": "https://www.nasdaq.com/"})
    try:
        pts = js["data"]["chart"]
    except (TypeError, KeyError):
        return None
    ones, last_w = [], None
    for p in pts:
        try:
            # Nasdaq's x is New York wall-clock time written as if it were UTC
            wall = datetime.fromtimestamp(p["x"] / 1000, timezone.utc)
            t = int(wall.replace(tzinfo=NY).timestamp())
            px = float(p["y"])
            w = float(p.get("w") or 0)
        except (TypeError, ValueError, KeyError):
            continue
        v = max(w - last_w, 0) if last_w is not None and w >= last_w else w
        last_w = w
        ones.append({"t": t, "o": px, "h": px, "l": px, "c": px, "v": v})
    return ones or None


class LiveMarket:
    """The real data source used on GitHub Actions."""

    def __init__(self):
        self._cache = {}

    def now(self):
        return time.time()

    def prefetch(self, stock_syms, crypto_syms, want_daily):
        """Download everything in parallel (keeps each run short)."""
        jobs = [("i", s) for s in stock_syms] + [("c", s) for s in crypto_syms]
        jobs += [("d", s) for s in (stock_syms if want_daily else [])]

        def work(job):
            kind, s = job
            fn = {"i": self._stock_intraday, "c": self._crypto, "d": self._stock_daily}[kind]
            return job, fn(s)

        with ThreadPoolExecutor(max_workers=8) as ex:
            for job, res in ex.map(work, jobs):
                self._cache[job] = res

    def stock_intraday(self, sym):
        if ("i", sym) not in self._cache:
            self._cache[("i", sym)] = self._stock_intraday(sym)
        return self._cache[("i", sym)]

    def stock_daily(self, sym):
        if ("d", sym) not in self._cache:
            self._cache[("d", sym)] = self._stock_daily(sym)
        return self._cache[("d", sym)]

    def crypto(self, sym):
        if ("c", sym) not in self._cache:
            self._cache[("c", sym)] = self._crypto(sym)
        return self._cache[("c", sym)]

    # ---- implementations ----
    def _stock_intraday(self, sym):
        five = _cnbc_bars(sym, "5D") or []
        ones = _cnbc_bars(sym, "1D")
        source = "CNBC"
        if not ones:
            ones = _nasdaq_today(sym)
            source = "Nasdaq"
        if not ones and not five:
            return None
        # Some stocks trade overnight/weekends on other venues, so the "latest day" is the
        # latest REGULAR session found, never just the newest timestamp.
        today = resample(_session(ones), 300) if ones else []
        five_s = _session(five, "09:28")
        if not today and five_s:  # fall back to the 5-day feed's own bars for the latest day
            last = date_str(five_s[-1]["t"])
            today = [b for b in five_s if date_str(b["t"]) == last]
        if not today:
            return None
        latest_day = date_str(today[-1]["t"])
        prior = [b for b in five_s if date_str(b["t"]) < latest_day]
        days = {}
        for b in prior:
            days.setdefault(date_str(b["t"]), []).append(b)
        open_vols = [d[0]["v"] for _, d in sorted(days.items()) if _hm(d[0]["t"]) <= "09:33"]
        price = (ones or five)[-1]["c"]
        return {"bars": prior + today, "price": price, "open_vols": open_vols[-4:], "source": source}

    def _stock_daily(self, sym):
        bars = _cnbc_bars(sym, "1M")
        if not bars:
            return None
        for b in bars:  # CNBC stamps daily bars at midnight; move to the open so dates line up
            b["t"] += 9 * 3600 + 1800
        return {"bars": bars[-40:], "price": bars[-1]["c"]}

    def _crypto(self, sym):
        js = _get_json(f"https://api.exchange.coinbase.com/products/{sym}/candles?granularity=900")
        if isinstance(js, list) and js:
            bars = [{"t": int(r[0]), "l": r[1], "h": r[2], "o": r[3], "c": r[4], "v": r[5]} for r in js]
            bars.sort(key=lambda b: b["t"])
            return {"bars": bars, "price": bars[-1]["c"], "source": "Coinbase"}
        five = _cnbc_bars(CNBC_CRYPTO[sym], "5D")
        if five:
            bars = resample(five, 900)
            return {"bars": bars, "price": five[-1]["c"], "source": "CNBC"}
        return None
