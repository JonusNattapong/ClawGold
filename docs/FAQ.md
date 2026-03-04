# Frequently Asked Questions (FAQ)

## General Questions

### What is ClawGold?

ClawGold is an AI-powered XAUUSD (Gold) trading system that combines:
- MetaTrader 5 integration for live trading
- Multi-AI research aggregation (OpenCode, KiloCode, Gemini)
- Sentiment analysis from news and research
- Advanced trading strategies (trailing stops, grid trading, breakout detection)
- Risk management and position monitoring

### Is ClawGold free to use?

Yes, ClawGold is open-source under the MIT License. However:
- You need your own MT5 account (may have spreads/commissions)
- AI CLI tools may have their own pricing
- Trading involves financial risk

### Do I need programming experience?

Basic command-line knowledge is helpful but not required. The CLI is designed to be user-friendly with clear commands and helpful error messages.

## Installation & Setup

### Which operating systems are supported?

Currently **Windows only** due to MetaTrader 5 requirements. MT5 does not run natively on Linux or macOS.

### Do I need a real MT5 account?

No, you can start with a **demo account** from any MT5 broker. This is recommended for testing.

### Python version requirements?

Python **3.10 or higher** is required for proper type hint support and modern language features.

### How do I install AI CLI tools?

**OpenCode:**
```bash
npm install -g opencode
# Usage: opencode run "<prompt>"
```

**Gemini:**
```bash
npm install -g @google/gemini-cli
# Usage: gemini "<prompt>"
```

**KiloCode:**
Download from https://kilo.ai (may require license)
# Usage: kilo run "<prompt>"

### Can I use ClawGold without AI tools?

Yes! All trading functionality works without AI tools. The news research features will be limited to cached data, but technical analysis and trading execution work independently.

## Trading Questions

### Is live trading safe?

⚠️ **Trading Warning:**
- Always start with a **demo account**
- Test strategies thoroughly before live trading
- Never trade with money you can't afford to lose
- Use proper risk management (stop losses, position limits)

### What is the minimum account balance?

There's no hard minimum, but we recommend:
- **Demo:** Any amount for testing
- **Live:** At least $1,000 for proper risk management
- Always use appropriate position sizes (0.01 lots recommended for small accounts)

### Which brokers are supported?

Any broker that provides **MetaTrader 5**. Popular options:
- MetaQuotes Demo (built-in)
- Exness
- IC Markets
- Pepperstone
- XM

### Can I trade other symbols besides XAUUSD?

The system is optimized for XAUUSD, but you can modify the `symbol` in `config.yaml` to trade other instruments. Note that different symbols have different:
- Contract sizes
- Margin requirements
- Volatility patterns

### How does the risk manager work?

The risk manager enforces these limits:
- **Position size limit:** Max 1.0 lot per trade
- **Daily loss limit:** Auto-stop at $500 loss
- **Max positions:** Limit 5 concurrent trades
- **Risk per trade:** Default 1% of account
- **Margin protection:** Alert below 150% margin level

## AI News Research

### How long does AI research take?

Typically **1-2 minutes** for all 3 AI tools running in parallel. Time varies based on:
- AI tool response speed
- Query complexity
- Network latency

### Why use multiple AI tools?

Each AI tool has different strengths:
- **OpenCode:** Technical analysis focus
- **KiloCode:** Market sentiment expertise
- **Gemini:** Fundamental analysis

By combining them, we get a more comprehensive view and can identify consensus.

### What is the consensus algorithm?

The algorithm:
1. Collects sentiment from each AI response
2. Counts bullish/bearish/neutral classifications
3. Calculates agreement percentage
4. Weights by confidence scores
5. Generates final consensus signal

### How does caching work?

AI research results are cached for **6 hours** by default. This prevents:
- Repeated expensive AI calls
- Rate limiting from AI providers
- Slow responses for common queries

### Can I adjust the cache TTL?

Yes, modify in `scripts/ai_researcher.py`:
```python
def __init__(self, cache_db=None, cache_ttl_hours=6):  # Change this
```

## Technical Questions

### Where is my data stored?

All data is stored **locally** in:
- `data/news.db` - News and AI research
- `data/clawgold.db` - Trading data
- `logs/` - Log files

No data is sent to external servers (except AI tool queries).

### How do I backup my data?

Simply copy the `data/` directory:
```bash
cp -r data/ backup/data-$(date +%Y%m%d)
```

### Can I run ClawGold on a VPS?

Yes, but MT5 requires Windows. Options:
1. Windows VPS (AWS, Azure, etc.)
2. Use Wine on Linux VPS (experimental)
3. Run locally and use for analysis only

### How do I update ClawGold?

```bash
git pull origin main
pip install -r requirements.txt
```

Always backup your `config.yaml` and `data/` directory before updating.

## Troubleshooting

### "MT5 initialize failed" error

**Solutions:**
1. Check credentials in `config.yaml`
2. Verify MT5 is installed at default path
3. Try logging into MT5 manually first
4. Check Windows Defender/antivirus isn't blocking

### AI tools return "not found"

**Check installation:**
```bash
which opencode  # or 'where opencode' on Windows
which gemini
```

If not found, reinstall or add to PATH.

### Database is locked

**Fix:**
```bash
# Remove lock file
rm data/*.db-journal

# Or restart terminal
```

### Positions not showing

**Check:**
1. MT5 terminal is running
2. You're logged into the correct account
3. Symbol matches (XAUUSD vs GOLD)
4. Try refreshing: `python claw.py positions`

### Slow performance

**Optimizations:**
- Use `--no-ai` for faster news queries
- Reduce monitor interval: `--interval 10`
- Clean old data: `python claw.py news cleanup --days 7`

## Configuration

### Can I use environment variables?

Yes! Supported variables:
```bash
MT5_LOGIN=12345678
MT5_PASSWORD=password
MT5_SERVER=MetaQuotes-Demo
TRADING_MODE=simulation
RISK_PER_TRADE=0.01
```

### How do I switch to simulation mode?

Edit `config.yaml`:
```yaml
trading:
  mode: simulation
```

Or set environment variable:
```bash
set TRADING_MODE=simulation
```

### Can I have multiple config profiles?

Create separate config files:
```bash
config-demo.yaml
config-live.yaml
```

Then specify when running:
```bash
# (Requires code modification to support --config flag)
```

## Strategies

### What is grid trading?

Grid trading places multiple buy/sell orders at set intervals around a price. When price moves, orders execute and create a "grid" of positions.

**Best for:** Ranging markets

### What is trailing stop?

A trailing stop automatically adjusts your stop-loss as price moves in your favor, locking in profits while allowing room for fluctuation.

**Example:**
- Entry: $5100
- Trailing distance: $10
- Price rises to $5120 → Stop moves to $5110
- Price drops to $5110 → Position closes with $10 profit

### What is breakout detection?

Identifies when price breaks above resistance or below support levels with volume confirmation.

**Best for:** Trending markets, news events

### Can I create custom strategies?

Yes! See [CONTRIBUTING.md](../CONTRIBUTING.md) for strategy development guidelines.

## Contributing

### How can I contribute?

- Report bugs via GitHub Issues
- Submit Pull Requests
- Improve documentation
- Share trading strategies
- Test and provide feedback

### What's the coding style?

- PEP 8 compliance
- Type hints for public functions
- Maximum line length: 100 characters
- Docstrings for all public APIs

### Where can I get help?

- GitHub Issues for bugs
- GitHub Discussions for questions
- Email: maintainer@clawgold.dev

---

**Didn't find your answer?** Open an issue on GitHub!
