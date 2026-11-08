"""Plain-Python technical indicators. Bars are dicts: t (unix secs), o, h, l, c, v."""


def ema(values, n):
    """Exponential moving average. Returns a list the same length as values."""
    if not values:
        return []
    k = 2 / (n + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def rsi(closes, n=14):
    """Wilder's RSI. Returns a list (None until enough data)."""
    out = [None] * len(closes)
    if len(closes) <= n:
        return out
    gains = losses = 0.0
    for i in range(1, n + 1):
        d = closes[i] - closes[i - 1]
        gains += max(d, 0)
        losses += max(-d, 0)
    avg_g, avg_l = gains / n, losses / n
    out[n] = 100 if avg_l == 0 else 100 - 100 / (1 + avg_g / avg_l)
    for i in range(n + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        avg_g = (avg_g * (n - 1) + max(d, 0)) / n
        avg_l = (avg_l * (n - 1) + max(-d, 0)) / n
        out[i] = 100 if avg_l == 0 else 100 - 100 / (1 + avg_g / avg_l)
    return out


def atr(bars, n=14):
    """Wilder's Average True Range of the latest bar (a single number)."""
    if len(bars) < 2:
        return None
    trs = []
    for i in range(1, len(bars)):
        h, l, pc = bars[i]["h"], bars[i]["l"], bars[i - 1]["c"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    if len(trs) < n:
        return sum(trs) / len(trs)
    val = sum(trs[:n]) / n
    for tr in trs[n:]:
        val = (val * (n - 1) + tr) / n
    return val


def vwap(bars):
    """Volume-weighted average price over the given bars."""
    pv = vol = 0.0
    for b in bars:
        typical = (b["h"] + b["l"] + b["c"]) / 3
        pv += typical * b["v"]
        vol += b["v"]
    if vol == 0:
        return bars[-1]["c"] if bars else None
    return pv / vol
