# Paper Trail 2

A **$100 pretend day-trading portfolio** run by a bot, with plain-English instructions for every trade.

**Dashboard:** https://ostromaj.github.io/paper-trail-2/

## What it does

- On market days a GitHub Action checks 11 stocks/ETFs and 3 cryptocurrencies every minute, from 7:00 AM until just after the close. Nights and weekends it checks crypto now and then.
- Phone alerts (ntfy app) for every buy, sell, and stop move.
- Five research-based rules each have a checklist. When every box on a checklist is checked, the bot buys.
- Every trade is logged with the exact time it was decided, the price, why, and step-by-step instructions anyone can copy.
- Stocks are always sold the same day (by 3:50 PM ET). Crypto trades have stops, targets, and time limits.
- Realistic costs are charged even though the money is pretend (0.05% slippage each way on stocks; 0.40% fee + 0.05% slippage each way on crypto), and the dashboard shows the total.
- Every result is compared with simply buying SPY and holding it.

## The rules

| Rule | Market | Based on |
|---|---|---|
| Opening-Range Breakout | Stocks & ETFs | Zarattini & Aziz (2023), *Can Day Trading Really Be Profitable?* |
| VWAP Trend | SPY, QQQ | Zarattini & Aziz (2023), *VWAP: The Holy Grail for Day Trading Systems* |
| Late-Day Momentum | SPY | Gao, Han, Li & Zhou (2018), *Market Intraday Momentum*, JFE |
| Crypto Breakout | BTC, ETH, SOL | Bitcoin intraday time-series momentum research |
| Crypto Dip-Buy | BTC, ETH, SOL | Short-term mean reversion in Bitcoin |

Settings (risk per trade, symbols, times) live in `bot/config.py`.

## Honest test (backtest)

Live results from a handful of trades can't tell skill from luck, so there's a backtest that
replays saved prices through the **same engine** the live bot uses (same rules, sizing, stops
and costs), checking only bars that had already finished (no peeking ahead).

- `backtest/archive.py` saves prices from the same free feeds (CNBC 5-minute stock bars,
  Coinbase 15-minute crypto). The free stock feed only goes back ~5 days, so stock history
  grows a little every market day; crypto goes back 90 days on the first run.
- `backtest/backtest.py` replays the archive at **no costs, normal costs and double costs**
  and compares with just buying and holding (SPY, and Bitcoin for the crypto-only test).
  It prints a plain-English verdict and writes `backtest.json` for the dashboard.
- The **Backtest** workflow runs both after every market day (or from the Actions tab) and
  keeps the archive and results on the `history` branch.
- Offline check of the harness on made-up prices: `python3 backtest/backtest.py --synthetic`.

## Tests

    python3 tests/test_engine.py    # unit tests (costs, stats, buy-and-hold, backtest harness)
    python3 tests/sim.py            # full engine on simulated prices; writes the demo data

## Reset

The **Reset** button on the dashboard (or Actions → *Reset portfolio to $100* → Run workflow → type `RESET`) archives the current run, with its full trade log, into **Past runs**, then starts fresh at $100.

## How it's built

- `bot/` — plain Python, no packages or API keys. Prices from CNBC (stocks, Nasdaq as backup) and Coinbase (crypto).
- `index.html` — the dashboard (GitHub Pages). It reads `dashboard.json` from the `data` branch.
- `tests/sim.py` — runs the bot against simulated prices to check the logic. Open `index.html?demo=1` to see the dashboard with that test data (and `tests/sim_backtest.json`, made-up backtest results).

**Pretend money. Not financial advice.** Most real day traders lose money.
