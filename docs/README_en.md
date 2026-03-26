# Crypto Trading Bot Pro

**Automated Cryptocurrency Futures Trading System for Binance**

> Trade smarter, not harder. Let data-driven strategies work for you 24/7.

---

## Pricing

| Plan | Price | Includes |
|------|-------|----------|
| **Basic** | $19 | Trend Following Strategy, Backtesting Engine, Telegram Alerts |
| **Pro** | $39 | Everything in Basic + Grid Trading Strategy, Real-time Dashboard, Priority Support |

---

## Features

### 1. Trend Following Strategy

The core engine uses a multi-indicator, multi-timeframe approach to identify high-probability trend entries.

- **Primary timeframe:** 15-minute candles with 1-hour confirmation
- **Entry logic:** MACD crossover filtered by RSI conditions and volume confirmation
- **Exit logic:** ATR-based dynamic stop loss (1.8x ATR) and take profit (2.5x ATR), yielding a **1.39 risk-to-reward ratio**
- Automatically adapts to current market volatility — no manual adjustment needed

### 2. Grid Trading Strategy *(Pro only)*

When the market is ranging and trend strategies sit idle, the grid engine takes over.

- Automatically detects support and resistance zones
- Places a grid of buy and sell orders within the identified range
- **ADX-based strategy switching** — the bot detects whether the market is trending or ranging and selects the optimal strategy automatically

### 3. Risk Management

Capital preservation is built into every layer of the system.

| Rule | Default Value |
|------|---------------|
| Max risk per trade | 2% of account |
| Max drawdown protection | 12% — bot pauses trading |
| Daily loss limit | 5% — no new trades for the day |
| Consecutive loss detection | Auto-reduces position size after losing streaks |

### 4. Backtesting Engine

Never go live blind. Test any strategy against 30+ days of real historical data before risking a single dollar.

- Detailed trade-by-trade logs
- Performance metrics: win rate, profit factor, max drawdown, Sharpe ratio
- Compare multiple parameter sets quickly

### 5. Telegram Notifications

Get real-time alerts on your phone for every trade event:

- Entry and exit signals
- Stop loss and take profit triggers
- Daily performance summaries
- System warnings and errors

### 6. Real-time Dashboard *(Pro only)*

A clean terminal-based UI that shows everything at a glance:

- Account balance and equity curve
- Open positions with live P&L
- Market analysis indicators
- Recent trade history

---

## Backtest Results (30 Days)

All results based on $1,000 starting capital with default settings.

| Pair | Net Profit | Win Rate | Max Drawdown | Profit Factor |
|------|-----------|----------|--------------|---------------|
| BTC/USDT | **+$183.08** | 65.5% | 11.6% | 2.75 |
| ETH/USDT | **+$17.44** | 46.7% | — | — |
| **Combined (all pairs)** | **+$41.55** | — | — | — |

> **Note:** Past performance does not guarantee future results. Backtest results are based on historical data and do not account for slippage, partial fills, or exchange outages. Always start with small capital and validate with paper trading.

---

## Quick Start

### Requirements

- Python 3.10 or higher
- A Binance Futures account with API key and secret
- Minimum **$100 USDT** recommended in your futures wallet

### Installation

```bash
# 1. Clone or extract the project
cd crypto-trading-bot

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set up your environment variables
cp .env.example .env
# Open .env and fill in your Binance API key, secret, and Telegram token

# 4. Edit the configuration file
# Open config.yaml and adjust settings to your preferences

# 5. Run a backtest first (always recommended)
python run_backtest.py

# 6. Start live trading
python main.py
```

---

## Configuration Guide

### Environment Variables (`.env`)

| Variable | Description |
|----------|-------------|
| `BINANCE_API_KEY` | Your Binance API key |
| `BINANCE_API_SECRET` | Your Binance API secret |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token (from @BotFather) |
| `TELEGRAM_CHAT_ID` | Your Telegram chat ID for notifications |

### Strategy Settings (`config.yaml`)

Key parameters you may want to adjust:

- **Trading pairs** — which symbols to trade (e.g., BTC/USDT, ETH/USDT)
- **Leverage** — default leverage for futures positions
- **Risk per trade** — percentage of account to risk per trade (default: 2%)
- **Max drawdown** — threshold to pause all trading (default: 12%)
- **Daily loss limit** — maximum daily loss before stopping (default: 5%)
- **Strategy selection** — trend only, grid only, or auto-switch

---

## Usage

### Run a Backtest

```bash
python run_backtest.py
```

Review the output to understand strategy performance on historical data before going live.

### Start Live Trading

```bash
python main.py
```

The bot will connect to Binance, begin monitoring the configured pairs, and execute trades automatically based on the active strategy.

### Monitor via Telegram

Once configured, you will receive Telegram messages for every trade entry, exit, and daily summary. No need to watch the screen.

### Dashboard (Pro)

The dashboard launches automatically when you start the bot. It displays account status, open positions, and market indicators in your terminal.

---

## FAQ

**Q: Do I need to keep my computer running 24/7?**
A: Yes, the bot needs to run continuously to monitor the market. A VPS (Virtual Private Server) is recommended for uninterrupted operation.

**Q: Can I use this on Binance Testnet first?**
A: Yes. Set the testnet flag in your configuration to trade with simulated funds before going live.

**Q: What happens if my internet disconnects?**
A: The bot places stop loss orders on the exchange, so your positions are protected even if the bot goes offline. When it reconnects, it will sync and resume.

**Q: Can I trade spot markets instead of futures?**
A: This bot is designed specifically for USDT perpetual futures on Binance. Spot trading is not supported.

**Q: How much capital do I need?**
A: A minimum of $100 USDT is recommended. The 2% risk-per-trade rule means each trade risks $2 at that level. More capital allows the bot to take properly sized positions.

**Q: Will I definitely make money?**
A: No. Trading involves significant risk. The bot provides a systematic, disciplined approach, but no system guarantees profits. Market conditions change, and losses are a normal part of trading.

**Q: What is the difference between Basic and Pro?**
A: Basic includes the trend following strategy, backtesting engine, and Telegram alerts. Pro adds the grid trading strategy for ranging markets, the real-time terminal dashboard, and priority support.

---

## Risk Disclaimer

**IMPORTANT — READ CAREFULLY**

Cryptocurrency futures trading carries a high level of risk and may not be suitable for all investors. The high degree of leverage available in futures trading can work against you as well as for you. Before deciding to trade cryptocurrency futures, you should carefully consider your investment objectives, level of experience, and risk appetite.

**There is a possibility that you could sustain a loss of some or all of your initial investment.** You should not invest money that you cannot afford to lose. You should be aware of all the risks associated with cryptocurrency futures trading and seek advice from an independent financial advisor if you have any doubts.

This software is provided as a tool to assist with trading decisions. **Past performance, including backtest results, is not indicative of future results.** The developers and sellers of this software are not responsible for any financial losses incurred through its use.

By purchasing and using this software, you acknowledge that:

1. You understand the risks involved in cryptocurrency futures trading.
2. You are solely responsible for your own trading decisions and outcomes.
3. Backtest results do not guarantee live trading performance.
4. You will not hold the developers liable for any losses.

**Always start with small amounts and test thoroughly before committing significant capital.**

---

## Support

- **Pro users:** Priority email support with 24-hour response time
- **Basic users:** Community support via GitHub Issues
- **Documentation:** See the `/docs` folder for detailed guides

For questions or issues, contact us through the Gumroad product page.

---

*Built for traders who value discipline over emotion.*
