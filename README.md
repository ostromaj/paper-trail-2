# Paper Trail 2

A **$100 pretend day-trading portfolio** run by a bot, with plain-English instructions for every trade.

**Dashboard:** https://ostromaj.github.io/paper-trail-2/

## What it does

- About every 5 minutes, a GitHub Action checks 11 stocks/ETFs (during market hours) and 3 cryptocurrencies (24/7).
- Five research-based rules each have a checklist. When every box on a checklist is checked, the bot buys.
- Every trade is logged with the exact time it was decided, the price, why, and step-by-step instructions anyone can copy.
- Stocks are always sold the same day (by 3:50 PM ET). Crypto trades have stops, targets, and time limits.
- Realistic costs are charged even though the money is pretend.

## The rules

| Rule | Market | Based on |
|---|---|---|
| Opening-Range Breakout | Stocks & ETFs | Zarattini & Aziz (2023), *Can Day Trading Really Be Profitable?* |
| VWAP Trend | SPY, QQQ | Zarattini & Aziz (2023), *VWAP: The Holy Grail for Day Trading Systems* |
| Late-Day Momentum | SPY | Gao, Han, Li & Zhou (2018), *Market Intraday Momentum*, JFE |
| Crypto Breakout | BTC, ETH, SOL | Bitcoin intraday time-series momentum research |
| Crypto Dip-Buy | BTC, ETH, SOL | Short-term mean reversion in Bitcoin |

Settings (risk per trade, symbols, times) live in `bot/config.py`.

## Reset

The **Reset** button on the dashboard (or Actions → *Reset portfolio to $100* → Run workflow → type `RESET`) archives the current run, with its full trade log, into **Past runs**, then starts fresh at $100.

## How it's built

- `bot/` — plain Python, no packages or API keys. Prices from Yahoo Finance (stocks) and Coinbase (crypto).
- `index.html` — the dashboard (GitHub Pages). It reads `dashboard.json` from the `data` branch.
- `tests/sim.py` — runs the bot against simulated prices to check the logic. Open `index.html?demo=1` to see the dashboard with that test data.

**Pretend money. Not financial advice.** Most real day traders lose money.
