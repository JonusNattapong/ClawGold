# Quick Start Guide

Get up and running with ClawGold in 5 minutes.

## Prerequisites

Before starting, ensure you have:

- [ ] Windows OS (MT5 requirement)
- [ ] Python 3.10 or higher
- [ ] MetaTrader 5 installed
- [ ] MT5 demo/live account

## Installation

### Step 1: Clone Repository

```bash
git clone https://github.com/OpenKrab/ClawGold.git
cd ClawGold
```

### Step 2: Create Virtual Environment

```bash
python -m venv .venv
.venv\Scripts\activate  # Windows
```

### Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 4: Configure MT5

Edit `config.yaml`:

```yaml
mt5:
  login: YOUR_LOGIN_NUMBER
  password: YOUR_PASSWORD
  server: YOUR_SERVER_NAME  # e.g., MetaQuotes-Demo
```

Or use environment variables:

```bash
set MT5_LOGIN=12345678
set MT5_PASSWORD=your_password
set MT5_SERVER=MetaQuotes-Demo
```

### Step 5: Validate Setup

```bash
python claw.py validate
```

Expected output:
```
[VALIDATE] Validating configuration...
[OK] Configuration is valid!
```

## First Commands

### Check Account Balance

```bash
python claw.py balance
```

Output:
```
========================================
Account Balance:         10000.00 USD
Account Equity:          10000.00 USD
Used Margin:                0.00 USD
Free Margin:             10000.00 USD
Profit/Loss:                0.00 USD
Margin Level:               0.00%
========================================
```

### Get Current Price

```bash
python claw.py price
```

Output:
```
========================================
XAUUSD Price
========================================
Bid:      5117.970 USD
Ask:      5118.130 USD
Spread:      0.160 USD
Time:   1772575103
========================================
```

### Execute First Trade (Demo Recommended)

```bash
# Buy 0.01 lots
python claw.py trade BUY 0.01

# Or sell
python claw.py trade SELL 0.01
```

## Daily Workflow

### Morning Analysis

```bash
# Multi-timeframe analysis
python claw.py analyze

# Get news sentiment
python claw.py news signal XAUUSD
```

### During Trading

```bash
# Monitor positions with alerts
python claw.py monitor --profit-alert 50 --loss-alert 25

# Check positions
python claw.py positions
```

### End of Day

```bash
# Close all positions
python claw.py close --all

# View news stats
python claw.py news stats
```

## AI News Research Setup

### Install AI CLI Tools (Optional)

```bash
# OpenCode
npm install -g opencode
# Usage: opencode run "<prompt>"

# Gemini
npm install -g @google/gemini-cli
# Usage: gemini "<prompt>"

# KiloCode - download from https://kilo.ai
# Usage: kilo run "<prompt>"
```

### Test AI Research

```bash
python claw.py news research XAUUSD --query "gold price outlook today"
```

Expected output after 1-2 minutes:
```
[NEWS RESEARCH] Researching XAUUSD...
Query: gold price outlook today
This may take 1-2 minutes while AI tools process...

============================================================
Research Results: XAUUSD
============================================================

Cached News Items: 0

[AI Analysis]
  Tools Used: opencode, kilocode, gemini
  Consensus: BULLISH
  Agreement: 67%
  Avg Confidence: 78%

  Sentiment Distribution:
    - bullish: 2
    - neutral: 1
```

## Common Tasks

### Apply Trailing Stop

```bash
# Get position ticket first
python claw.py positions

# Apply trailing stop
python claw.py trailing-stop 12345678 --activation 20 --distance 10
```

### Grid Trading

```bash
python claw.py grid --levels 5 --grid-size 10 --volume 0.01
```

### Breakout Detection

```bash
# Detect only
python claw.py breakout --symbol XAUUSD

# Detect and auto-trade
python claw.py breakout --symbol XAUUSD --execute --volume 0.01
```

## Troubleshooting

### "MT5 initialize failed"

1. Check MT5 credentials in config.yaml
2. Verify MT5 terminal is installed at `C:\Program Files\MetaTrader 5\terminal64.exe`
3. Try logging into MT5 manually first

### "AI tool not found"

Install the missing tool or use `--no-ai` flag:
```bash
python claw.py news research XAUUSD --no-ai
```

### "Permission denied"

Run terminal as Administrator or check file permissions.

## Next Steps

- Read [ARCHITECTURE.md](ARCHITECTURE.md) for system design
- Check [API_REFERENCE.md](API_REFERENCE.md) for detailed API
- See [CONTRIBUTING.md](../CONTRIBUTING.md) to contribute

## Safety Tips

⚠️ **Always start with:**
1. Demo account testing
2. Small position sizes (0.01 lots)
3. Stop losses on every trade
4. Daily loss limits configured

---

**Happy Trading! 🦞**
