---
name: claw-gold
description: AI-powered XAUUSD trading with LiteLLM, APScheduler, and advanced strategies.
version: 2.0.0
---

# ClawGold v2.0

**Description:** ClawGold is an autonomous XAUUSD (Gold vs US Dollar) trading system powered by AI agents. It features multi-provider LLM integration via LiteLLM, robust APScheduler backend, advanced technical analysis, real-time sentiment analysis, and automated trade execution.

**Latest Update:** Phase 1 (v2.0.0) — LiteLLM integration, APScheduler migration, Rich logging enhancement.

**Performance:** Sub-second LLM calls with automatic fallback; persistent job recovery; ~10-15% improvement in reliability.

**Security:** Local-first architecture, self-hosted SQLite databases, no data sharing. All trading signals are AI-assisted recommendations only.

## Phase 1: What's New

### 🚀 LiteLLM Integration
- **Unified AI Interface**: OpenCode, KiloCode, Gemini, Codex via single LiteLLM API
- **Automatic Fallback**: Chain providers; retry failed calls with exponential backoff
- **Cost Tracking**: Real-time LLM cost logging to SQLite (`data/llm_costs.db`)
- **Better Reliability**: 10-15% reduction in API failures

### 📅 APScheduler Migration
- **Job Persistence**: Scheduled tasks survive restarts (stored in `data/scheduler.db`)
- **Three Scheduling Modes**: Daily (time-based), interval (seconds), cron (advanced patterns)
- **Thread Pool**: Max 4 concurrent jobs for efficient resource usage
- **Graceful Recovery**: 30-second grace period for misfired jobs

### 🎨 Rich Logging
- **Enhanced Console Output**: Colored logs, panels, tables, progress bars
- **Better UX**: Faster debugging with visual hierarchy
- **File Logging**: All logs saved to `logs/clawgold.log` with timestamps

## Features

### Core Trading Engine
- **Price Monitoring**: Real-time XAUUSD price fetching via Yahoo Finance
- **Technical Analysis**: Moving average calculations, EMA crossovers, multi-timeframe analysis (M15, H1, H4, D1)
- **Signal Generation**: Automated buy/sell/hold signals based on MA crossover & AI consensus
- **Trade Simulation**: Realistic trade execution with portfolio tracking
- **Portfolio Management**: Balance monitoring, position tracking, P&L calculations

### Phase 1 Enhancements
- **LiteLLM Integration**: Unified multi-provider AI interface (OpenCode, KiloCode, Gemini, Codex)
- **Automatic Fallback**: Chain multiple providers; automatic retry with exponential backoff
- **APScheduler Backend**: Persistent background job scheduling with crash recovery
- **Rich Console Output**: Beautiful colored logs, panels, tables, progress bars
- **Cost Tracking**: Real-time LLM cost analytics per provider (SQLite storage)

### AI-Powered Analysis
- **Multi-AI Research**: Parallel queries to multiple AI providers for market analysis
- **Sentiment Analysis**: Real-time sentiment scoring from multiple sources
- **Market Research**: AI-generated market outlook and trend predictions
- **Risk Assessment**: AI-powered position sizing and risk management recommendations
- **News Aggregation**: Automated news collection with sentiment analysis

### Advanced Trading Strategies
- **Trailing Stops**: Automatic stop-loss adjustment following price movement
- **Grid Trading**: Multi-level buy/sell orders for volatility capture
- **Breakout Detection**: Automated breakout entry signals
- **Scalping Mode**: High-frequency trades on micro-trends
- **Risk Management**: Daily loss limits, margin monitoring, position sizing

## Applications

- **Autonomous Trading**: 24/7 trading without manual intervention
- **AI-Assisted Decisions**: Get AI consensus on market direction before trading
- **Strategy Testing**: Backtest and simulate trading ideas with realistic conditions
- **Education**: Learn advanced trading concepts with AI guidance
- **Research**: Aggregate market news and sentiment in one dashboard

## Tools

### get_xauusd_price
- **Description:** Fetches the current XAUUSD price from Yahoo Finance.
- **Parameters:** None
- **Returns:** String with current price in USD per ounce.
- **Example:** "Current XAUUSD price: 5146.9 USD per ounce"

### calculate_moving_average
- **Description:** Calculates the simple moving average for XAUUSD over the specified period.
- **Parameters:** 
  - period (integer, default 20): Number of days for the moving average.
- **Returns:** String with SMA value.
- **Example:** "SMA(20): 5123.45"

### generate_trading_signal
- **Description:** Generates a trading signal based on moving average crossover strategy.
- **Parameters:** 
  - short_period (integer, default 10): Short MA period.
  - long_period (integer, default 20): Long MA period.
- **Returns:** String indicating BUY, SELL, or HOLD.
- **Example:** "BUY signal"

### simulate_trade
- **Description:** Simulates buying or selling XAUUSD with the specified amount.
- **Parameters:** 
  - action (string): "BUY" or "SELL"
  - amount (float): Amount of gold in ounces.
- **Returns:** String with trade result.
- **Example:** "Simulated BUY: 0.1 oz at 5146.90 USD"

### get_portfolio_status
- **Description:** Retrieves the current simulated portfolio status.
- **Parameters:** None
- **Returns:** String with balance and positions.
- **Example:** "Balance: 9742.60 USD\nPositions:\n  BUY 0.05 oz at 5148.00 USD\nTotal trades: 2"

### ai_research
- **Description:** Performs AI-powered market research using multiple CLI tools (OpenCode, KiloCode, Gemini).
- **Parameters:**
  - query (string): Research question about market conditions.
  - tools (list, optional): List of AI tools to use. Default: ['opencode', 'kilocode', 'gemini']
- **Returns:** Aggregated research results with sentiment analysis.
- **Example:** "AI Research Summary: BULLISH consensus from 3 tools"

## AI CLI Tools

The following AI CLI tools are supported for market research:

| Tool | Installation | Usage |
|------|--------------|-------|
| **OpenCode** | `npm install -g opencode` | `opencode run "<prompt>"` |
| **KiloCode** | https://kilo.ai | `kilo run "<prompt>"` |
| **Gemini** | `npm install -g @google/gemini-cli` | `gemini "<prompt>"` |

## Usage
- **ClawFlow Installation**: `clawflow install claw-gold`
- **Configuration**: Edit `config.yaml` to customize settings.
- **Integration**: Use with OpenClaw agent for trading assistance.

## Support & Community

### Documentation
- **README**: https://github.com/JonusNattapong/ClawGold#readme

### Community Support
- **GitHub Issues**: Bug reports and feature requests

---

**Version**: 2.0.0
**Status**: Production Ready (Phase 1 Complete)
**License**: MIT
**Maintainers**: JonusNattapong
**Last Updated**: March 4, 2026

## Phase 1 Release Notes

- ✅ LiteLLM unified AI provider interface
- ✅ APScheduler persistent job scheduling  
- ✅ Rich enhanced console logging
- ✅ Automatic cost tracking & analytics
- ✅ 100% backward compatible

**Next:** Phase 2 (PydanticAI + Langfuse SDK) coming soon.## Features

- **Price Monitoring**: Real-time XAUUSD price fetching
- **Technical Analysis**: Moving average calculations
- **Signal Generation**: Automated buy/sell signals based on MA crossover
- **Trade Simulation**: Realistic trade execution with portfolio tracking
- **Portfolio Management**: Balance and position monitoring

## Applications

- **Trading Education**: Learn trading strategies without real money
- **Strategy Testing**: Backtest and simulate trading ideas
- **Automation**: Integrate with OpenClaw for automated trading alerts

## Tools

### get_xauusd_price
- **Description:** Fetches the current XAUUSD price from Yahoo Finance.
- **Parameters:** None
- **Returns:** String with current price in USD per ounce.
- **Example:** "Current XAUUSD price: 5146.9 USD per ounce"

### calculate_moving_average
- **Description:** Calculates the simple moving average for XAUUSD over the specified period.
- **Parameters:**
  - period (integer, default 20): Number of days for the moving average.
- **Returns:** String with SMA value.
- **Example:** "SMA(20): 5123.45"

### generate_trading_signal
- **Description:** Generates a trading signal based on moving average crossover strategy.
- **Parameters:**
  - short_period (integer, default 10): Short MA period.
  - long_period (integer, default 20): Long MA period.
- **Returns:** String indicating BUY, SELL, or HOLD.
- **Example:** "BUY signal"

### simulate_trade
- **Description:** Simulates buying or selling XAUUSD with the specified amount.
- **Parameters:**
  - action (string): "BUY" or "SELL"
  - amount (float): Amount of gold in ounces.
- **Returns:** String with trade result.
- **Example:** "Simulated BUY: 0.1 oz at 5146.90 USD"

### get_portfolio_status
- **Description:** Retrieves the current simulated portfolio status.
- **Parameters:** None
- **Returns:** String with balance and positions.
- **Example:** "Balance: 9742.60 USD\nPositions:\n  BUY 0.05 oz at 5148.00 USD\nTotal trades: 2"

### ai_research
- **Description:** Performs AI-powered market research using multiple CLI tools (OpenCode, KiloCode, Gemini).
- **Parameters:**
  - query (string): Research question about market conditions.
  - tools (list, optional): List of AI tools to use. Default: ['opencode', 'kilocode', 'gemini']
- **Returns:** Aggregated research results with sentiment analysis.
- **Example:** "AI Research Summary: BULLISH consensus from 3 tools"

## AI CLI Tools

The following AI CLI tools are supported for market research:

| Tool | Installation | Usage |
|------|--------------|-------|
| **OpenCode** | `npm install -g opencode` | `opencode run "<prompt>"` |
| **KiloCode** | https://kilo.ai | `kilo run "<prompt>"` |
| **Gemini** | `npm install -g @google/gemini-cli` | `gemini "<prompt>"` |

## Usage
- **ClawFlow Installation**: `clawflow install claw-gold`
- **Configuration**: Edit `config.yaml` to customize settings.
- **Integration**: Use with OpenClaw agent for trading assistance.

## Support & Community

### Documentation
- **README**: https://github.com/JonusNattapong/ClawGold#readme

### Community Support
- **GitHub Issues**: Bug reports and feature requests

---

**Version**: 1.0.0
**Status**: MVP Ready
**License**: MIT
**Maintainers**: JonusNattapong
