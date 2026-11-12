"""The paper portfolio and one decision cycle.

`cycle(state, market)` runs once a minute on market days (GitHub Actions):
  1. get prices        2. manage open trades (stops, targets, time exits)
  3. check every rule  4. buy anything that meets every condition
  5. save a watchlist of trades that are close to triggering
"""
import config as C
import strategies as S
from clock import (close_hm, date_str, hm, market_label, nice_datetime, nice_time,
                   shift_for_early_close, stock_market_open)
from indicators import atr, vwap

PRIORITY = {"ORB": 0, "LATE": 1, "VWAP": 2, "CBRK": 3, "CDIP": 4}


# ----------------------------------------------------------------------------- state
def new_state(now, run_number=1, past_runs=None):
    return {
        "version": 1,
        "run_number": run_number,
        "run_started": now,
        "starting_cash": C.STARTING_CASH,
        "cash": C.STARTING_CASH,
        "positions": [],
        "trades": [],
        "equity_curve": [[int(now), C.STARTING_CASH]],
        "activity": [],
        "watchlist": [],
        "cooldowns": {},
        "traded_today": {"date": date_str(now), "keys": []},
        "day": {"date": date_str(now), "start_equity": C.STARTING_CASH},
        "atr_cache": {"date": None, "values": {}},
        "next_id": 1,
        "prices": {},
        "past_runs": past_runs or [],
        "last_run": None,
        "errors": [],
    }


def equity(state):
    total = state["cash"]
    for p in state["positions"]:
        px = state["prices"].get(p["symbol"], {}).get("price", p["entry_price"])
        total += p["qty"] * px
    return total


def _log(state, now, text):
    state["activity"].insert(0, {"t": int(now), "time": nice_time(now), "text": text})
    del state["activity"][80:]


def _money(x):
    return f"${x:,.4f}" if 0 < abs(x) < 0.1 else f"${x:,.2f}"


def _round_price(x):
    return round(x, 2) if x >= 1 else round(x, 6)


# ----------------------------------------------------------------------------- instructions
def buy_steps(c, amount, stop, target, exit_plan):
    sym, name = c["symbol"], c["name"]
    if c["kind"] == "crypto":
        coin = sym.split("-")[0]
        steps = [
            f"Open a crypto app (Coinbase, Kraken, Robinhood, Cash App...).",
            f"Buy {_money(amount)} of {name} ({coin}). Order type: Market.",
            f"Set a price alert at {_money(stop)}. If {coin} drops to it, sell all of it.",
        ]
        if target:
            steps.append(f"Set a second alert at {_money(target)}. If {coin} reaches it, sell all of it (take the profit).")
        steps.append(exit_plan)
    else:
        steps = [
            "Open a stock app that lets you buy in dollars (fractional shares): Robinhood, Fidelity, Schwab, Webull...",
            f"Search {sym} ({name}). Tap Buy and choose to buy in dollars.",
            f"Enter {_money(amount)}. Order type: Market. Submit.",
            f"Place a Stop (sell) order for all your {sym} at {_money(stop)}. "
            f"If your app won't allow a stop on fractional shares, set a price alert at {_money(stop)} and sell when it rings.",
            exit_plan,
        ]
    return steps


def sell_steps(p, why):
    sym = p["symbol"]
    label = sym.split("-")[0] if p["kind"] == "crypto" else sym
    return [
        f"Cancel any stop order or alert you set for {label}.",
        f"Sell ALL of your {label} now. Order type: Market.",
    ]


# ----------------------------------------------------------------------------- trades
def _record(state, now, **kw):
    t = {"id": state["next_id"], "decided_at": int(now), "decided_at_text": nice_datetime(now)}
    t.update(kw)
    state["next_id"] += 1
    state["trades"].append(t)
    return t


def crypto_exposure(state):
    return sum(p["qty"] * state["prices"].get(p["symbol"], {}).get("price", p["entry_price"])
               for p in state["positions"] if p["kind"] == "crypto")


def plan_size(state, kind, entry, stop):
    """Dollar amount for a trade: risk-based, capped by cash and (for crypto) the crypto budget."""
    eq = equity(state)
    dist = (entry - stop) / entry if entry else 0
    if dist <= 0:
        return 0.0
    dollars = min(eq * C.RISK_PER_TRADE / dist, eq * C.MAX_POSITION_PCT, state["cash"])
    if kind == "crypto":
        dollars = min(dollars, max(eq * C.CRYPTO_MAX_PCT - crypto_exposure(state), 0))
    return int(dollars * 100) / 100


def open_position(state, c, now):
    price = c["price"]
    stop = c["stop"]
    dollars = plan_size(state, c["kind"], price, stop)
    if dollars < C.MIN_TRADE_DOLLARS:
        why = "the crypto budget (25% of the account) is used up" if c["kind"] == "crypto" else "there's no free cash"
        key = f"{date_str(now)}:{c['strategy']}:{c['symbol']}"
        logged = state.setdefault("skip_logged", [])
        if key not in logged:  # say it once per setup per day, not every minute
            _log(state, now, f"{c['symbol']} {c['strategy_name']} was ready, but {why}. Skipped.")
            logged.append(key)
            del logged[:-60]
        return None
    if c["kind"] == "crypto":
        fee = dollars * C.CRYPTO_FEE
        fill = price * (1 + C.CRYPTO_SLIPPAGE)
        qty = (dollars - fee) / fill
        hours = C.CRYPTO_BREAKOUT_MAX_HOURS if c["strategy"] == "CBRK" else C.CRYPTO_DIP_MAX_HOURS
        exit_by = now + hours * 3600
    else:
        fee = dollars * C.STOCK_FEE
        fill = price * (1 + C.STOCK_SLIPPAGE)
        qty = (dollars - fee) / fill
        exit_by = None
    slip = qty * (fill - price)  # dollars lost to a worse fill than the decision price
    state["cash"] = round(state["cash"] - dollars, 6)
    stop, target = _round_price(stop), (_round_price(c["target"]) if c.get("target") else None)
    pos = {
        "id": state["next_id"], "symbol": c["symbol"], "name": c["name"], "kind": c["kind"],
        "strategy": c["strategy"], "strategy_name": c["strategy_name"],
        "qty": qty, "entry_price": fill, "entry_time": int(now), "cost": dollars,
        "stop": stop, "initial_stop": stop, "target": target,
        "risk": fill - stop, "highest": price, "exit_by": exit_by,
        "atr": c.get("atr"), "checked_through": int(now), "exit_plan": c["exit_plan"],
        "entry_costs": round(fee + slip, 6),
    }
    state["positions"].append(pos)
    met = "; ".join(ch["label"] for ch in c["checks"])
    _record(
        state, now, action="BUY", symbol=c["symbol"], name=c["name"], kind=c["kind"],
        strategy=c["strategy"], strategy_name=c["strategy_name"], position_id=pos["id"],
        price=_round_price(price), fill_price=fill, qty=qty, amount=dollars, fee=round(fee, 4),
        slippage=round(slip, 4), stop=stop, target=target, out_text=c.get("out_text", ""),
        reason=f"All {c['total']} conditions met: {met}.",
        checks=c["checks"], indicators=c["indicators"],
        steps=buy_steps(c, dollars, stop, target, c["exit_plan"]),
        skip_if=f"Skip it if the price is already above {_money(price * (1 + C.CHASE_LIMIT))} when you see this.",
    )
    if c["kind"] != "crypto":
        state["traded_today"]["keys"].append([c["strategy"], c["symbol"]])
    _log(state, now, f"BUY {_money(dollars)} of {c['symbol']} ({c['strategy_name']}) at {_money(price)}.")
    return pos


def close_position(state, p, price, now, why, when_text=None):
    if p["kind"] == "crypto":
        fill = price * (1 - C.CRYPTO_SLIPPAGE)
        gross = p["qty"] * fill
        fee = gross * C.CRYPTO_FEE
    else:
        fill = price * (1 - C.STOCK_SLIPPAGE)
        gross = p["qty"] * fill
        fee = gross * C.STOCK_FEE
    slip = p["qty"] * (price - fill)
    proceeds = gross - fee
    pnl = proceeds - p["cost"]
    state["cash"] = round(state["cash"] + proceeds, 6)
    state["positions"] = [x for x in state["positions"] if x["id"] != p["id"]]
    _record(
        state, now, action="SELL", symbol=p["symbol"], name=p["name"], kind=p["kind"],
        strategy=p["strategy"], strategy_name=p["strategy_name"], position_id=p["id"],
        price=_round_price(price), fill_price=fill, qty=p["qty"], amount=round(proceeds, 4),
        fee=round(fee, 4), slippage=round(slip, 4), costs=round(p.get("entry_costs", 0) + fee + slip, 4),
        pnl=round(pnl, 4), pnl_pct=round(pnl / p["cost"] * 100, 2),
        entry_price=p["entry_price"], entry_time=p["entry_time"], held_minutes=int((now - p["entry_time"]) / 60),
        reason=why + (f" ({when_text})" if when_text else ""), steps=sell_steps(p, why),
    )
    cd = C.CRYPTO_COOLDOWN_MIN if p["kind"] == "crypto" else C.STOCK_COOLDOWN_MIN
    state["cooldowns"][p["symbol"]] = now + cd * 60
    word = "profit" if pnl >= 0 else "loss"
    _log(state, now, f"SELL {p['symbol']} at {_money(price)}: {why}. {word.title()} ${abs(pnl):.2f}.")


def move_stop(state, p, new_stop, now, why):
    new_stop = _round_price(new_stop)
    if new_stop <= p["stop"] * 1.0005:
        return
    p["stop"] = new_stop
    label = p["symbol"].split("-")[0] if p["kind"] == "crypto" else p["symbol"]
    _record(
        state, now, action="MOVE STOP", symbol=p["symbol"], name=p["name"], kind=p["kind"],
        strategy=p["strategy"], strategy_name=p["strategy_name"], position_id=p["id"],
        price=_round_price(state["prices"].get(p["symbol"], {}).get("price", 0)), stop=new_stop,
        reason=why,
        steps=[f"Cancel your old stop (or alert) for {label}.",
               f"Set a new stop (or alert) at {_money(new_stop)}. If {label} drops to it, sell all of it."],
    )
    _log(state, now, f"Moved {p['symbol']} stop up to {_money(new_stop)} ({why}).")


# ----------------------------------------------------------------------------- managing trades
def _bar_secs(p):
    return 900 if p["kind"] == "crypto" else 300


def manage_positions(state, now, stock_data, crypto_data):
    for p in list(state["positions"]):
        data = (crypto_data if p["kind"] == "crypto" else stock_data).get(p["symbol"])
        if not data:
            continue
        secs = _bar_secs(p)
        price = data["price"]
        new_bars = [b for b in data["bars"]
                    if b["t"] >= p["entry_time"] - (p["entry_time"] % secs) + secs
                    and b["t"] + secs <= now and b["t"] + secs > p["checked_through"]]
        closed = False
        for b in new_bars:
            if b["l"] <= p["stop"]:
                close_position(state, p, min(p["stop"], b["o"]), now, "Stop-loss hit",
                               f"around {nice_time(b['t'] + secs)}")
                closed = True
                break
            if p["target"] and b["h"] >= p["target"]:
                close_position(state, p, max(p["target"], b["o"]), now, "Profit target hit",
                               f"around {nice_time(b['t'] + secs)}")
                closed = True
                break
            p["highest"] = max(p["highest"], b["h"])
            p["checked_through"] = b["t"] + secs
        if closed:
            continue
        p["highest"] = max(p["highest"], price)

        # live price checks
        if price <= p["stop"]:
            close_position(state, p, price, now, "Stop-loss hit")
            continue
        if p["target"] and price >= p["target"]:
            close_position(state, p, price, now, "Profit target hit")
            continue

        if p["kind"] == "crypto":
            if now >= p["exit_by"]:
                close_position(state, p, price, now, "Time limit reached for this trade")
                continue
            if p["strategy"] == "CBRK":
                a = atr([b for b in data["bars"] if b["t"] + 900 <= now][-80:], 14) or p["atr"]
                trail = p["highest"] - 2.5 * a
                # only bother followers when the stop can move up by a meaningful step
                if trail >= p["stop"] + max(0.75 * a, p["stop"] * 0.006):
                    move_stop(state, p, trail, now, "trailing stop follows the price up")
            continue

        # ---- stocks ----
        entry_day = date_str(p["entry_time"])
        if date_str(now) != entry_day or not stock_market_open(now):
            day_bars = [b for b in data["bars"] if date_str(b["t"]) == entry_day]
            px = day_bars[-1]["c"] if day_bars else price
            close_position(state, p, px, now, "Day trade closed at the market close")
            continue
        flatten = shift_for_early_close(now, C.STOCK_FLATTEN_AT)
        late_exit = shift_for_early_close(now, C.LATE_EXIT_AT)
        if p["strategy"] == "LATE" and hm(now) >= late_exit:
            close_position(state, p, price, now, "End-of-day exit (3:55 PM)")
            continue
        if p["strategy"] != "LATE" and hm(now) >= flatten:
            close_position(state, p, price, now, "End-of-day exit, no overnight holds")
            continue
        if p["strategy"] == "VWAP":
            today = [b for b in data["bars"] if date_str(b["t"]) == date_str(now) and b["t"] + 300 <= now]
            last = today[-1] if today else None
            if last and last["t"] >= p["entry_time"] - 300 and last["c"] < vwap(today):
                close_position(state, p, price, now, "5-min candle closed below VWAP, trend over")
                continue
        r = p["risk"]
        if r > 0 and p["highest"] >= p["entry_price"] + 2 * r:
            move_stop(state, p, p["entry_price"] + r, now, "up 2x risk, locking in profit")
        elif r > 0 and p["highest"] >= p["entry_price"] + r:
            move_stop(state, p, p["entry_price"], now, "up 1x risk, stop moved to break-even")


# ----------------------------------------------------------------------------- stats
def _streaks(sells):
    """(current streak, longest win streak, longest losing streak). Current is +n for n wins in a row, -n for losses."""
    cur = best_w = best_l = 0
    for t in sells:
        if t["pnl"] > 0:
            cur = cur + 1 if cur > 0 else 1
        else:
            cur = cur - 1 if cur < 0 else -1
        best_w, best_l = max(best_w, cur), max(best_l, -cur)
    return cur, best_w, best_l


def _group_stats(sells):
    wins = [t for t in sells if t["pnl"] > 0]
    gross_w = sum(t["pnl"] for t in wins)
    gross_l = -sum(t["pnl"] for t in sells if t["pnl"] <= 0)
    return {
        "trades": len(sells), "wins": len(wins),
        "win_rate": round(len(wins) / len(sells) * 100, 1) if sells else None,
        "pnl": round(sum(t["pnl"] for t in sells), 4),
        "costs": round(sum(t.get("costs", t.get("fee", 0)) for t in sells), 4),
        # profit factor: dollars won per dollar lost (above 1 = making money)
        "profit_factor": round(gross_w / gross_l, 2) if gross_l > 0 else None,
        "avg_pnl": round(sum(t["pnl"] for t in sells) / len(sells), 4) if sells else None,
    }


def max_drawdown(values):
    """Largest drop from a running high, as a negative percent (0 if it never dipped)."""
    peak, mdd = None, 0.0
    for v in values:
        if v is None:
            continue
        peak = v if peak is None else max(peak, v)
        if peak:
            mdd = min(mdd, v / peak - 1)
    return round(mdd * 100, 2)


def compute_stats(state):
    sells = [t for t in state["trades"] if t["action"] == "SELL"]
    wins = [t for t in sells if t["pnl"] > 0]
    losses = [t for t in sells if t["pnl"] <= 0]
    eq = equity(state)
    curve = [p[1] for p in state["equity_curve"]] + [eq]
    peak = max(curve)
    cur, best_w, best_l = _streaks(sells)
    g = _group_stats(sells)
    by_strategy = {}
    for key in S.STRATEGY_NAMES:
        ss = [t for t in sells if t["strategy"] == key]
        if ss:
            by_strategy[key] = _group_stats(ss) | {"name": S.STRATEGY_NAMES[key]}
    bh = benchmark_value(state)
    ret = (eq / state["starting_cash"] - 1) * 100
    bh_ret = (bh / state["starting_cash"] - 1) * 100 if bh else None
    entry_costs_open = sum(p.get("entry_costs", 0) for p in state["positions"])
    return {
        "equity": round(eq, 4),
        "return_pct": round(ret, 3),
        "day_pnl": round(eq - state["day"]["start_equity"], 4),
        "trades_closed": len(sells),
        "wins": len(wins), "losses": len(losses),
        "win_rate": g["win_rate"],
        "avg_win": round(sum(t["pnl"] for t in wins) / len(wins), 4) if wins else None,
        "avg_loss": round(sum(t["pnl"] for t in losses) / len(losses), 4) if losses else None,
        "best": max((t["pnl"] for t in sells), default=None),
        "worst": min((t["pnl"] for t in sells), default=None),
        "fees": round(sum(t.get("fee", 0) for t in state["trades"]), 4),
        "slippage": round(sum(t.get("slippage", 0) for t in state["trades"]), 4),
        # everything trading cost this run: fees + worse-than-quoted fills (incl. open trades)
        "costs": round(g["costs"] + entry_costs_open, 4),
        "profit_factor": g["profit_factor"],
        "expectancy": g["avg_pnl"],
        "max_drawdown_pct": max_drawdown(curve),
        "peak_equity": round(peak, 4),
        "from_peak_pct": round((eq / peak - 1) * 100, 2) if peak else 0,
        "streak": cur, "best_win_streak": best_w, "worst_loss_streak": best_l,
        "by_strategy": by_strategy,
        "bh_symbol": (state.get("benchmark") or {}).get("symbol"),
        "bh_equity": round(bh, 4) if bh else None,
        "bh_return_pct": round(bh_ret, 3) if bh_ret is not None else None,
        "vs_bh_pct": round(ret - bh_ret, 3) if bh_ret is not None else None,
        "bh_max_drawdown_pct": max_drawdown([p[2] if len(p) > 2 else None for p in state["equity_curve"]] + [bh]) if bh else None,
    }


# ----------------------------------------------------------------------------- buy-and-hold yardstick
def benchmark_value(state):
    """What the $100 would be worth if it had simply bought SPY at the start of the run and held."""
    b = state.get("benchmark")
    if not b or not b.get("start_price"):
        return None
    px = state["prices"].get(b["symbol"], {}).get("price") or b.get("last_price")
    return state["starting_cash"] * px / b["start_price"] if px else None


def update_benchmark(state, market, now, stock_data):
    """Sets the buy-and-hold start price once (the first SPY price seen in this run; for runs that
    started before this existed, SPY's opening price on the run's first market day), and keeps the
    latest SPY price so the yardstick survives nights and weekends."""
    sym = C.BENCHMARK
    b = state.get("benchmark")
    if not b:
        start_px = None
        today = date_str(now)
        tried = state.get("benchmark_tried") == today
        if not tried and state["run_started"] < now - 3600 and hasattr(market, "stock_daily"):
            state["benchmark_tried"] = today  # at most one extra download a day
            d = market.stock_daily(sym)
            first_day = date_str(state["run_started"])
            after = [x for x in (d or {}).get("bars", []) if date_str(x["t"]) >= first_day]
            if after:
                start_px = after[0]["o"]
                # back-fill the existing curve with daily closes so the comparison covers the
                # whole run (approximate: daily prices, not minute-by-minute)
                closes = {date_str(x["t"]): x["c"] for x in d["bars"]}
                for pt in state["equity_curve"]:
                    day = date_str(pt[0])
                    if hm(pt[0]) >= close_hm(pt[0]) and day in closes:
                        px = closes[day]
                    else:
                        prev = [k for k in closes if first_day <= k < day]
                        px = closes[max(prev)] if prev else start_px
                    if len(pt) == 2:
                        pt.append(round(state["starting_cash"] * px / start_px, 4))
        if not start_px and sym in stock_data and stock_data[sym].get("price"):
            start_px = stock_data[sym]["price"]
        if not start_px:
            return
        b = state["benchmark"] = {"symbol": sym, "start_price": start_px, "start_t": int(now),
                                  "last_price": start_px}
    if sym in stock_data and stock_data[sym].get("price"):
        b["last_price"] = stock_data[sym]["price"]
        state["prices"][sym] = {"price": stock_data[sym]["price"], "t": int(now)}


def _thin_curve(curve, limit):
    """Keep the newest half of the points as-is and thin out the older half.
    (Bug fix: the old version used floor division, so the step was always 1 and the
    curve never actually shrank. It grew by a point every minute forever.)"""
    if len(curve) <= limit:
        return curve
    keep = limit // 2
    old, recent = curve[:-keep], curve[-keep:]
    step = -(-len(old) // (limit - keep))  # ceiling division
    thinned = old[::step]
    if thinned[-1] is not old[-1]:
        thinned.append(old[-1])
    return thinned[-(limit - keep):] + recent


# ----------------------------------------------------------------------------- the cycle
def cycle(state, market):
    now = market.now()
    today = date_str(now)
    state["errors"] = []
    mkt_open = stock_market_open(now)
    held_stocks = {p["symbol"] for p in state["positions"] if p["kind"] != "crypto"}

    # 1. prices
    want = set(C.STOCKS) if mkt_open else held_stocks
    need_daily = mkt_open and state["atr_cache"]["date"] != today
    if hasattr(market, "prefetch"):
        market.prefetch(sorted(want), list(C.CRYPTO), need_daily)
    crypto_data = {}
    for sym in C.CRYPTO:
        d = market.crypto(sym)
        if d:
            crypto_data[sym] = d
        else:
            state["errors"].append(f"No data for {sym} this run")
    stock_data = {}
    for sym in sorted(want):
        d = market.stock_intraday(sym)
        if d and d["bars"]:
            stock_data[sym] = d
        else:
            state["errors"].append(f"No data for {sym} this run")
    if need_daily:
        vals = {}
        for sym in C.STOCKS:
            d = market.stock_daily(sym)
            if d and d["bars"]:
                bars = [b for b in d["bars"] if date_str(b["t"]) < today]
                if bars:
                    vals[sym] = {"atr": atr(bars[-30:], 14), "prev_close": bars[-1]["c"]}
        if vals:
            state["atr_cache"] = {"date": today, "values": vals}
    for sym, d in list(crypto_data.items()) + list(stock_data.items()):
        if d.get("price"):
            state["prices"][sym] = {"price": d["price"], "t": int(now)}

    update_benchmark(state, market, now, stock_data)

    # 2. new day bookkeeping
    if state["day"]["date"] != today:
        state["day"] = {"date": today, "start_equity": equity(state)}
    if state["traded_today"]["date"] != today:
        state["traded_today"] = {"date": today, "keys": []}

    # 3. manage open trades
    manage_positions(state, now, stock_data, crypto_data)

    # 4. evaluate every rule
    traded = {tuple(k) for k in state["traded_today"]["keys"]}
    cands = []
    if mkt_open:
        for sym, d in stock_data.items():
            try:
                cands += S.evaluate_stock(sym, d, state["atr_cache"]["values"].get(sym), now, traded)
            except Exception as e:
                state["errors"].append(f"{sym}: {e}")
    for sym, d in crypto_data.items():
        try:
            cands += S.evaluate_crypto(sym, d, now, state["cooldowns"])
        except Exception as e:
            state["errors"].append(f"{sym}: {e}")

    # 5. trade
    eq = equity(state)
    halted = eq < state["day"]["start_equity"] * (1 - C.DAILY_LOSS_LIMIT)
    held = {p["symbol"] for p in state["positions"]}
    bought = 0
    ready = sorted([c for c in cands if c["ready"]], key=lambda c: PRIORITY[c["strategy"]])
    for c in ready:
        if halted:
            key = f"{today}:halted"
            logged = state.setdefault("skip_logged", [])
            if key not in logged:  # once a day, not every minute
                _log(state, now, f"{c['symbol']} {c['strategy_name']} was ready, but the daily loss limit is hit. "
                                 "No new trades today.")
                logged.append(key)
            break
        if c["symbol"] in held or len(state["positions"]) >= C.MAX_OPEN_POSITIONS:
            continue
        if c["kind"] == "crypto" and sum(p["kind"] == "crypto" for p in state["positions"]) >= C.MAX_CRYPTO_POSITIONS:
            continue
        if state["cooldowns"].get(c["symbol"], 0) > now:
            continue
        if open_position(state, c, now):
            held.add(c["symbol"])
            bought += 1

    # 6. watchlist = trades that are close to happening
    watch = []
    for c in cands:
        if c["symbol"] in held:
            status = "holding"
        elif c["ready"]:
            status = "ready"
        elif not c.get("in_window", True):
            status = "off-hours"
        elif c["met"] >= c["total"] - 1:
            status = "close"
        else:
            status = "watching"
        entry, stop, target = c["entry"], c["stop"], c.get("target")
        amount = plan_size(state, c["kind"], entry, stop) if status not in ("holding",) else 0
        plan = {
            "entry": _round_price(entry), "entry_text": c["entry_text"],
            "stop": _round_price(stop), "stop_pct": round((stop / entry - 1) * 100, 2),
            "target": _round_price(target) if target else None,
            "target_pct": round((target / entry - 1) * 100, 2) if target else None,
            "out_text": c["out_text"], "amount": amount,
            "risk_dollars": round(amount * (entry - stop) / entry, 2) if entry else 0,
        }
        if c["kind"] == "crypto" and amount < C.MIN_TRADE_DOLLARS:
            plan["note"] = "Crypto budget is full (25% of the account), so this one would be skipped right now."
        watch.append({k: c[k] for k in ("symbol", "name", "kind", "strategy", "strategy_name", "checks",
                                         "met", "total", "trigger", "indicators")}
                     | {"status": status, "price": _round_price(c["price"]),
                        "progress": round(c["met"] / c["total"], 2), "plan": plan})
    order = {"ready": 0, "close": 1, "watching": 2, "holding": 3, "off-hours": 4}
    # stocks first at equal status, so crypto doesn't crowd the list
    watch.sort(key=lambda w: (order[w["status"]], w["kind"] == "crypto", -w["progress"], PRIORITY[w["strategy"]]))
    state["watchlist"] = watch

    # 7. bookkeeping
    eq = equity(state)
    bh = benchmark_value(state)
    state["equity_curve"].append([int(now), round(eq, 4)] + ([round(bh, 4)] if bh else []))
    state["equity_curve"] = _thin_curve(state["equity_curve"], C.MAX_EQUITY_POINTS)
    state["stats"] = compute_stats(state)
    state["market"] = market_label(now) | {"close": close_hm(now)}
    state["halted"] = halted
    state["last_run"] = int(now)
    state["last_run_text"] = nice_datetime(now)
    n = len(stock_data) + len(crypto_data)
    if not bought and not any(a["t"] == int(now) for a in state["activity"]):
        close_n = sum(1 for w in watch if w["status"] == "close")
        text = f"Checked {n} markets. No trade" + (f", {close_n} setup(s) one condition away." if close_n else ".")
        top = state["activity"][0] if state["activity"] else None
        if top and top.get("kind") == "check":  # keep the feed readable: one rolling "still checking" line
            top.update(t=int(now), time=nice_time(now), text=text, count=top.get("count", 1) + 1)
        else:
            _log(state, now, text)
            state["activity"][0]["kind"] = "check"
    return state


# ----------------------------------------------------------------------------- reset
def reset(state, now):
    """Close everything at the last known prices, archive the run, start over at $100."""
    for p in list(state["positions"]):
        px = state["prices"].get(p["symbol"], {}).get("price", p["entry_price"])
        close_position(state, p, px, now, "Closed because the portfolio was reset")
    bh = benchmark_value(state)
    state["equity_curve"].append([int(now), round(equity(state), 4)] + ([round(bh, 4)] if bh else []))
    st = compute_stats(state)
    archive = {
        "run_number": state["run_number"],
        "started": state["run_started"], "ended": int(now),
        "started_text": nice_datetime(state["run_started"]), "ended_text": nice_datetime(now),
        "starting_cash": state["starting_cash"], "final_equity": round(equity(state), 2),
        "stats": st, "trades": state["trades"],
        "equity_curve": _thin_curve(state["equity_curve"], 300),
    }
    past = [archive] + state.get("past_runs", [])
    fresh = new_state(now, state["run_number"] + 1, past[:25])
    fresh["atr_cache"] = state.get("atr_cache", fresh["atr_cache"])
    fresh["prices"] = state.get("prices", {})
    _log(fresh, now, f"Portfolio reset. Run #{state['run_number']} ended at {_money(archive['final_equity'])}. "
                     f"Starting run #{fresh['run_number']} with $100.00.")
    fresh["stats"] = compute_stats(fresh)
    fresh["market"] = market_label(now) | {"close": close_hm(now)}
    fresh["last_run"] = int(now)
    fresh["last_run_text"] = nice_datetime(now)
    return fresh
