"""Which free stock data sources answer from GitHub Actions? (diagnostic)"""
import http.cookiejar, json, urllib.request
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15"
cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
def get(url, hdr=None):
    h = {"User-Agent": UA, "Accept": "*/*", "Accept-Language": "en-US,en;q=0.9"}
    h.update(hdr or {})
    try:
        with op.open(urllib.request.Request(url, headers=h), timeout=15) as r:
            b = r.read().decode(errors="replace"); return r.status, b
    except urllib.error.HTTPError as e:
        return e.code, e.read()[:200].decode(errors="replace")
    except Exception as e:
        return None, str(e)
def show(name, st, body):
    print(f"{name}: status {st} len {len(body)} :: {body[:160]!r}")
st, b = get("https://fc.yahoo.com"); show("yahoo cookie", st, b)
st, crumb = get("https://query2.finance.yahoo.com/v1/test/getcrumb"); show("yahoo crumb", st, crumb)
st, b = get(f"https://query2.finance.yahoo.com/v8/finance/chart/SPY?range=5d&interval=5m&crumb={crumb}"); show("yahoo chart+crumb q2", st, b)
st, b = get(f"https://query1.finance.yahoo.com/v8/finance/chart/SPY?range=5d&interval=5m&crumb={crumb}"); show("yahoo chart+crumb q1", st, b)
st, b = get("https://api.nasdaq.com/api/quote/SPY/chart?assetclass=etf&charttype=rs", {"Origin": "https://www.nasdaq.com", "Referer": "https://www.nasdaq.com/"}); show("nasdaq chart", st, b)
st, b = get("https://api.nasdaq.com/api/quote/NVDA/chart?assetclass=stocks&charttype=rs", {"Origin": "https://www.nasdaq.com", "Referer": "https://www.nasdaq.com/"}); show("nasdaq chart nvda", st, b)
st, b = get("https://stooq.com/q/d/l/?s=spy.us&i=5"); show("stooq 5m", st, b)
st, b = get("https://stooq.com/q/l/?s=spy.us&f=sd2t2ohlcv&h&e=csv"); show("stooq quote", st, b)
st, b = get("https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol?symbols=SPY&requestMethod=itv&noform=1&partnerId=2&fund=1&exthrs=1&output=json"); show("cnbc quote", st, b)
st, b = get("https://ts-api.cnbc.com/harmony/app/charts/1D.json?symbol=SPY"); show("cnbc 1D chart", st, b)
st, b = get("https://ts-api.cnbc.com/harmony/app/charts/5D.json?symbol=SPY"); show("cnbc 5D chart", st, b)
