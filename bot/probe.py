"""Diagnostic: inspect CNBC chart bar format from GitHub Actions."""
import json, urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
NY = ZoneInfo("America/New_York")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15"
def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=15) as r:
        return json.loads(r.read())
for rng in ["1D", "5D", "1M", "3M"]:
    js = get(f"https://ts-api.cnbc.com/harmony/app/charts/{rng}.json?symbol=SPY")
    bars = js["barData"]["priceBars"]
    print(rng, "keys:", list(js["barData"].keys()), "n bars:", len(bars))
    print("  bar keys:", list(bars[0].keys()))
    for b in bars[:2] + bars[-3:]:
        t = int(b["tradeTimeinMills"]) / 1000
        print("  ", b["tradeTime"], "->", datetime.fromtimestamp(t, NY).strftime("%Y-%m-%d %H:%M %Z"), b["open"], b["high"], b["low"], b["close"], b["volume"])
    ts = [int(b["tradeTimeinMills"]) for b in bars]
    gaps = sorted({(ts[i+1]-ts[i])//60000 for i in range(min(50, len(ts)-1))})
    print("  gaps(min):", gaps[:8])
    days = {}
    for b in bars:
        d = datetime.fromtimestamp(int(b["tradeTimeinMills"]) / 1000, NY)
        days.setdefault(d.strftime("%a %m-%d"), []).append(d.strftime("%H:%M"))
    print("  days:", {k: (v[0], v[-1], len(v)) for k, v in list(days.items())[-6:]})
q = get("https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol?symbols=SPY|BTC.CM=&requestMethod=itv&noform=1&partnerId=2&fund=1&exthrs=1&output=json")
for x in q["FormattedQuoteResult"]["FormattedQuote"]:
    print("quote:", {k: x.get(k) for k in ("symbol", "last", "last_time", "previous_day_closing", "curmktstatus", "volume")})
