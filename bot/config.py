"""Settings for Paper Trail 2. Change numbers here, not in the logic files."""

STARTING_CASH = 100.00

# ---- What the bot is allowed to trade -------------------------------------
STOCKS = {
    # symbol: (friendly name, kind)
    "SPY": ("S&P 500 ETF", "etf"),
    "QQQ": ("Nasdaq-100 ETF", "etf"),
    "IWM": ("Russell 2000 ETF", "etf"),
    "AAPL": ("Apple", "stock"),
    "MSFT": ("Microsoft", "stock"),
    "NVDA": ("Nvidia", "stock"),
    "AMZN": ("Amazon", "stock"),
    "META": ("Meta", "stock"),
    "GOOGL": ("Alphabet", "stock"),
    "TSLA": ("Tesla", "stock"),
    "AMD": ("AMD", "stock"),
}
CRYPTO = {
    "BTC-USD": ("Bitcoin", "crypto"),
    "ETH-USD": ("Ethereum", "crypto"),
    "SOL-USD": ("Solana", "crypto"),
}

# The yardstick: what if the $100 had just bought this and held it?
BENCHMARK = "SPY"

# Which stock strategies look at which symbols
ORB_SYMBOLS = list(STOCKS)               # opening-range breakout: everything
VWAP_SYMBOLS = ["SPY", "QQQ"]            # VWAP trend: the two big index ETFs
LATE_MOMENTUM_SYMBOLS = ["SPY"]          # last-half-hour momentum: SPY only

# ---- Money rules -------------------------------------------------------------
RISK_PER_TRADE = 0.015      # lose at most ~1.5% of the account if a stop is hit
MAX_POSITION_PCT = 0.50     # one trade may use up to 50% of the account (room for two at once)
MAX_OPEN_POSITIONS = 3
# Keep crypto from taking over: it trades 24/7 and could otherwise tie up the
# cash the stock rules need at 9:30.
CRYPTO_MAX_PCT = 0.25       # all crypto together: at most 25% of the account
MAX_CRYPTO_POSITIONS = 1    # one coin at a time
MIN_TRADE_DOLLARS = 1.00
DAILY_LOSS_LIMIT = 0.05     # down 5% on the day -> no new trades until tomorrow

# ---- Realistic costs (paper trades still pay these) ---------------------------
# Slippage = getting a slightly worse price than the one the bot saw when it decided.
# A market order placed a minute after a signal on 1-minute data rarely fills at the exact
# quote, so 0.05% each way is a fair, slightly conservative guess for big liquid names.
STOCK_SLIPPAGE = 0.0005     # 0.05% worse fill each way
STOCK_FEE = 0.0             # commission-free broker
CRYPTO_SLIPPAGE = 0.0005    # 0.05% worse fill each way
CRYPTO_FEE = 0.004          # 0.40% each way (typical small-account crypto fee/spread)

# ---- Timing (New York time) ------------------------------------------------------
ORB_WINDOW = ("09:35", "11:00")
VWAP_WINDOW = ("10:00", "15:15")
LATE_WINDOW = ("15:30", "15:45")
STOCK_FLATTEN_AT = "15:50"          # day trades: everything sold before the close
LATE_EXIT_AT = "15:55"
STOCK_COOLDOWN_MIN = 30
CRYPTO_COOLDOWN_MIN = 120
CRYPTO_BREAKOUT_MAX_HOURS = 24
CRYPTO_DIP_MAX_HOURS = 12

# If a follower sees a trade late and the price has run this far past the
# decision price, they should skip it.
CHASE_LIMIT = 0.005

# NYSE full-day holidays and early (1:00 PM) closes
HOLIDAYS = {
    "2026-11-26", "2026-12-25",
    "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31",
    "2027-06-18", "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24",
}
EARLY_CLOSES = {"2026-11-27", "2026-12-24", "2027-11-26"}

# Keep the saved file small
MAX_EQUITY_POINTS = 2500

# ---- Phone alerts (ntfy app) ----------------------------------------------------------
# Subscribe to this topic in the ntfy app. A GitHub secret named NTFY_TOPIC overrides it.
NTFY_TOPIC = "papertrail2-678499f24ef1"
NOTIFY_ACTIONS = ["BUY", "SELL", "MOVE STOP"]   # remove any you don't want pinged about
