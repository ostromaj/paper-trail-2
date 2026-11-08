"""The five trading rules. Each one returns a checklist so the dashboard can show
exactly which conditions are met before a trade happens.

Stocks/ETFs (5-minute bars, long only, all sold the same day):
  ORB   - Opening-Range Breakout (Zarattini & Aziz, 2023)
  VWAP  - VWAP trend (Zarattini & Aziz, 2023)
  LATE  - Last-half-hour momentum (Gao, Han, Li & Zhou, 2018)
Crypto (15-minute bars, trades 24/7):
  CBRK  - Breakout to a new 24-hour high in an uptrend (crypto time-series momentum)
  CDIP  - Oversold dip-buy inside an uptrend (short-term mean reversion)
"""
import config as C
from clock import close_hm, date_str, hm, in_window, shift_for_early_close
from indicators import atr, ema, rsi, vwap

STRATEGY_NAMES = {
    "ORB": "Opening-Range Breakout",
    "VWAP": "VWAP Trend",
    "LATE": "Late-Day Momentum",
    "CBRK": "Crypto Breakout",
    "CDIP": "Crypto Dip-Buy",
}


def _check(label, ok, detail=""):
    return {"label": label, "ok": bool(ok), "detail": detail}


def _money(x):
    return f"${x:,.2f}" if x >= 1 else f"${x:,.4f}"


def _candidate(symbol, name, kind, key, checks, ready, price, **extra):
    c = {
        "symbol": symbol, "name": name, "kind": kind,
        "strategy": key, "strategy_name": STRATEGY_NAMES[key],
        "checks": checks, "met": sum(ch["ok"] for ch in checks), "total": len(checks),
        "ready": bool(ready), "price": price,
        "stop": None, "target": None, "trigger": "", "exit_plan": "", "indicators": {},
    }
    c.update(extra)
    return c


def split_days(bars, now, bar_secs):
    """Completed bars grouped by New York date (oldest day first)."""
    days = {}
    for b in bars:
        if b["t"] + bar_secs <= now:
            days.setdefault(date_str(b["t"]), []).append(b)
    return [days[k] for k in sorted(days)]


def _bar_at(day, hhmm):
    """Close of the last completed bar that ends at or before hh:mm."""
    best = None
    for b in day:
        if hm(b["t"] + 300) <= hhmm:
            best = b
    return best


# ----------------------------------------------------------------------------------
def evaluate_stock(symbol, data, daily, now, traded_today):
    """daily = {"atr": 14-day ATR, "prev_close": yesterday's official close} (either may be missing)."""
    daily = daily or {}
    daily_atr = daily.get("atr")
    name, kind = C.STOCKS[symbol]
    price = data["price"]
    days = split_days(data["bars"], now, 300)
    if not days or date_str(days[-1][0]["t"]) != date_str(now) or price is None:
        return []
    today, prior = days[-1], days[:-1]
    first = today[0]
    if hm(first["t"]) != "09:30":
        return []
    out = []
    v_now = vwap(today)
    all_closes = [b["c"] for d in days for b in d]
    e9, e21 = ema(all_closes, 9)[-1], ema(all_closes, 21)[-1]
    r = rsi(all_closes, 14)[-1]
    a = daily_atr or price * 0.02
    base_ind = {"VWAP": round(v_now, 2), "EMA 9": round(e9, 2), "EMA 21": round(e21, 2),
                "RSI": round(r, 1) if r else None, "Daily ATR": round(a, 2)}

    # --- ORB -----------------------------------------------------------------
    if symbol in C.ORB_SYMBOLS:
        or_hi, or_lo = first["h"], first["l"]
        prior_first = data.get("open_vols") or [d[0]["v"] for d in prior if d][-4:]
        rvol = first["v"] / (sum(prior_first) / len(prior_first)) if prior_first and sum(prior_first) else 1.0
        checks = [
            _check("Opening 5-min candle was green", first["c"] > first["o"],
                   f"opened {_money(first['o'])}, closed {_money(first['c'])}"),
            _check("Heavy opening volume (1.2x normal or more)", rvol >= 1.2, f"{rvol:.1f}x normal"),
            _check(f"Price above the opening high {_money(or_hi)}", price > or_hi, f"now {_money(price)}"),
            _check(f"Price above VWAP {_money(v_now)}", price > v_now, f"now {_money(price)}"),
        ]
        window = in_window(now, C.ORB_WINDOW) and ("ORB", symbol) not in traded_today
        ready = window and all(c["ok"] for c in checks)
        stop = max(or_lo, price - 0.2 * a)
        stop = min(stop, price * (1 - 0.0025))
        out.append(_candidate(
            symbol, name, kind, "ORB", checks, ready, price, stop=stop, in_window=window,
            trigger=f"Buys if {symbol} trades above {_money(or_hi)} before 11:00 AM",
            exit_plan="Hold until 3:50 PM ET unless the stop hits. The stop moves up as the trade profits.",
            indicators={**base_ind, "Opening high": round(or_hi, 2), "Opening low": round(or_lo, 2),
                        "Opening volume": f"{rvol:.1f}x"},
        ))

    # --- VWAP trend ----------------------------------------------------------
    if symbol in C.VWAP_SYMBOLS:
        last = today[-1]
        checks = [
            _check(f"Price above VWAP {_money(v_now)}", price > v_now * 1.0005, f"now {_money(price)}"),
            _check("Last 5-min candle closed above VWAP", last["c"] > v_now, f"closed {_money(last['c'])}"),
            _check("Short-term trend up (9 EMA over 21 EMA)", e9 > e21, f"{e9:.2f} vs {e21:.2f}"),
            _check("Momentum healthy (RSI 50 to 70)", r is not None and 50 <= r <= 70,
                   f"RSI {r:.0f}" if r else "n/a"),
        ]
        end = shift_for_early_close(now, C.VWAP_WINDOW[1])
        window = C.VWAP_WINDOW[0] <= hm(now) < end and ("VWAP", symbol) not in traded_today
        ready = window and all(c["ok"] for c in checks)
        stop = min(v_now - 0.1 * a, price * (1 - 0.0025))
        out.append(_candidate(
            symbol, name, kind, "VWAP", checks, ready, price, stop=stop, in_window=window, vwap=v_now,
            trigger=f"Buys if {symbol} holds above VWAP ({_money(v_now)}) with the trend up",
            exit_plan="Sell when a 5-min candle closes below VWAP, if the stop hits, or at 3:50 PM ET.",
            indicators=base_ind,
        ))

    # --- Late-day momentum ---------------------------------------------------
    if symbol in C.LATE_MOMENTUM_SYMBOLS and (prior or daily.get("prev_close")):
        prev_close = daily.get("prev_close") or prior[-1][-1]["c"]
        b10 = _bar_at(today, "10:00")
        b1500, b1530 = _bar_at(today, "15:00"), _bar_at(today, "15:30")
        r1 = (b10["c"] / prev_close - 1) if b10 else None
        r12 = (b1530["c"] / b1500["c"] - 1) if (b1500 and b1530 and hm(now) >= "15:30") else None
        checks = [
            _check("First half-hour was up (yesterday's close to 10:00 AM)", r1 is not None and r1 > 0,
                   f"{r1 * 100:+.2f}%" if r1 is not None else "waiting for 10:00 AM"),
            _check("3:00 to 3:30 PM was up", r12 is not None and r12 > 0,
                   f"{r12 * 100:+.2f}%" if r12 is not None else "waiting for 3:30 PM"),
        ]
        early = close_hm(now) == "13:00"
        window = (not early) and in_window(now, C.LATE_WINDOW) and ("LATE", symbol) not in traded_today
        ready = window and all(c["ok"] for c in checks)
        out.append(_candidate(
            symbol, name, kind, "LATE", checks, ready, price, stop=price * (1 - 0.004), in_window=window,
            trigger="Buys SPY around 3:30 PM if the morning and the 3:00 to 3:30 stretch were both up",
            exit_plan="Sell at 3:55 PM ET (just before the close).",
            indicators={"Prev close": round(prev_close, 2)},
        ))
    return out


# ----------------------------------------------------------------------------------
def evaluate_crypto(symbol, data, now, cooldowns):
    name, kind = C.CRYPTO[symbol]
    price = data["price"]
    bars = [b for b in data["bars"] if b["t"] + 900 <= now]
    if len(bars) < 210 or not price:
        return []
    closes = [b["c"] for b in bars]
    e50, e200 = ema(closes, 50)[-1], ema(closes, 200)[-1]
    rs = rsi(closes, 14)
    a = atr(bars[-80:], 14)
    last = bars[-1]
    hi24 = max(b["h"] for b in bars[-97:-1])
    vavg = sum(b["v"] for b in bars[-21:-1]) / 20
    vmult = last["v"] / vavg if vavg else 0
    lo3d = min(b["l"] for b in bars[-288:-4])
    up = e50 > e200
    cool = cooldowns.get(symbol, 0) > now
    ind = {"EMA 50": round(e50, 2), "EMA 200": round(e200, 2), "RSI": round(rs[-1], 1),
           "ATR (15m)": round(a, 2), "24h high": round(hi24, 2)}
    out = []

    checks = [
        _check("Uptrend (50 EMA above 200 EMA, 15-min chart)", up, f"{e50:,.2f} vs {e200:,.2f}"),
        _check(f"15-min candle closed above the 24-hour high {_money(hi24)}", last["c"] > hi24,
               f"closed {_money(last['c'])}"),
        _check("Volume surge (1.5x normal or more)", vmult >= 1.5, f"{vmult:.1f}x normal"),
        _check("Not overheated (RSI under 80)", rs[-1] < 80, f"RSI {rs[-1]:.0f}"),
    ]
    stop_d = max(2 * a, price * 0.012)
    out.append(_candidate(
        symbol, name, kind, "CBRK", checks, (not cool) and all(c["ok"] for c in checks), price,
        stop=price - stop_d, in_window=not cool, atr=a,
        trigger=f"Buys if a 15-min candle closes above {_money(hi24)} on strong volume",
        exit_plan=f"Trailing stop 2.5x ATR below the highest price; sell after {C.CRYPTO_BREAKOUT_MAX_HOURS} hours max.",
        indicators=ind,
    ))

    dipped = min(x for x in rs[-5:-1] if x is not None) < 30
    checks = [
        _check("Uptrend (50 EMA above 200 EMA, 15-min chart)", up, f"{e50:,.2f} vs {e200:,.2f}"),
        _check("RSI dipped under 30 in the last hour (oversold)", dipped,
               f"lowest RSI {min(x for x in rs[-5:-1] if x is not None):.0f}"),
        _check("RSI turned back up above 30", rs[-1] >= 30 and rs[-1] > rs[-2], f"RSI {rs[-1]:.0f}"),
        _check(f"Holding above the 3-day low {_money(lo3d)}", price > lo3d, f"now {_money(price)}"),
    ]
    stop_d = max(1.5 * a, price * 0.010)
    tgt_d = max(2.0 * a, price * 0.016)
    out.append(_candidate(
        symbol, name, kind, "CDIP", checks, (not cool) and all(c["ok"] for c in checks), price,
        stop=price - stop_d, target=price + tgt_d, in_window=not cool, atr=a,
        trigger=f"Buys if {name} gets oversold (RSI under 30) and bounces while the uptrend holds",
        exit_plan=f"Sell at the target or stop, or after {C.CRYPTO_DIP_MAX_HOURS} hours max.",
        indicators=ind,
    ))
    return out
