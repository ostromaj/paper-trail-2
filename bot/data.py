"""Free market data with no API keys.

Stocks/ETFs: Yahoo Finance chart endpoint (5-minute and daily bars).
Crypto: Coinbase Exchange public candles (15-minute), Yahoo as a backup.
Every function returns None instead of crashing, so one bad feed never stops the bot.
"""
import json
import time
import urllib.request

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"


def _get_json(url, tries=3):
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.loads(r.read().decode())
        except Exception as e:  # network hiccup, 429, etc.
            last = e
            time.sleep(1.5 * (attempt + 1))
    print(f"  data fetch failed: {url[:90]} ({last})")
    return None


def _yahoo_chart(symbol, rng, interval):
    for host in ("query1", "query2"):
        url = (f"https://{host}.finance.yahoo.com/v8/finance/chart/{symbol}"
               f"?range={rng}&interval={interval}&includePrePost=false")
        js = _get_json(url, tries=2)
        try:
            res = js["chart"]["result"][0]
        except (TypeError, KeyError, IndexError):
            continue
        q = res["indicators"]["quote"][0]
        bars = []
        for i, t in enumerate(res.get("timestamp") or []):
            o, h, l, c, v = (q[k][i] for k in ("open", "high", "low", "close", "volume"))
            if None in (o, h, l, c):
                continue
            bars.append({"t": int(t), "o": o, "h": h, "l": l, "c": c, "v": v or 0})
        meta = res.get("meta", {})
        return {
            "bars": bars,
            "price": meta.get("regularMarketPrice") or (bars[-1]["c"] if bars else None),
            "prev_close": meta.get("chartPreviousClose"),
        }
    return None


class LiveMarket:
    """The real data source used on GitHub Actions."""

    def now(self):
        return time.time()

    def stock_intraday(self, symbol):
        return _yahoo_chart(symbol, "5d", "5m")

    def stock_daily(self, symbol):
        return _yahoo_chart(symbol, "2mo", "1d")

    def crypto(self, symbol):
        js = _get_json(f"https://api.exchange.coinbase.com/products/{symbol}/candles?granularity=900")
        if isinstance(js, list) and js:
            bars = [{"t": int(r[0]), "l": r[1], "h": r[2], "o": r[3], "c": r[4], "v": r[5]} for r in js]
            bars.sort(key=lambda b: b["t"])
            return {"bars": bars, "price": bars[-1]["c"], "source": "Coinbase"}
        y = _yahoo_chart(symbol, "5d", "15m")
        if y and y["bars"]:
            y["source"] = "Yahoo"
            return y
        return None
