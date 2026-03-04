# CLAUDE.md — ClawGold Development Guide

This file provides guidance to Claude Code and Copilot when working on the ClawGold XAUUSD trading system codebase.

## Project Overview

**ClawGold** is an AI-powered autonomous gold (XAUUSD) trading system with:
- **Multi-AI Agent System** — Dispatch tasks to OpenCode, KiloCode, Gemini, Codex via CLI (no model training)
- **Sub-Agent Orchestration** — 5 domain-specific roles (researcher, analyst, strategist, monitor, general)
- **Automated Scheduling** — Background daemon for daily/periodic trading workflows
- **LLM Observability** — Langfuse integration for tracing, cost tracking, quality evaluation
- **MetaTrader 5 Integration** — Direct Python MT5 API for trading execution
- **News & Sentiment Engine** — Multi-source research with AI consensus

**Repository:** `d:\Projects\Github\ClawGold`  
**Language:** Python 3.10+ (TypeScript ESM for future components)  
**Package Manager:** pip (standard Python)

---

## Development Commands

### Essential Setup & Build
```bash
# Install dependencies
pip install -r requirements.txt

# Run tests
python -m unittest discover -s test -p "test_*.py" -v

# Validate configuration
python claw.py validate

# Check balance (MT5 connection test)
python claw.py balance
```

### Testing
```bash
# All tests
python -m unittest discover -s test -p "test_*.py" -v

# Specific test file
python -m unittest test.test_agent_system -v

# With coverage
python -m coverage run -m unittest discover -s test && python -m coverage report

# Watch mode (rerun on changes)
while True; do python -m unittest discover -s test; sleep 2; done
```

### Development Workflow
```bash
# Start development
python claw.py agent tools      # List available AI CLI tools
python claw.py agent run gemini "Test prompt"

# Check logs
tail -f logs/trades.log

# Run a specific command
python claw.py agent daily      # Daily routine
python claw.py agent history    # View execution history
python claw.py agent metrics    # Per-tool performance

# Schedule debug
python claw.py agent schedule status
python claw.py agent schedule log
```

---

## High-Level Architecture

### Core Components

**1. Agent System** (`scripts/agent_*.py` — 3 modules)
- `agent_executor.py` — Unified CLI tool interface (tool discovery, execution, caching, metrics)
- `sub_agent.py` — Role-based orchestrator (5 roles: researcher, analyst, strategist, monitor, general)
- `agent_scheduler.py` — Background task scheduler (daily, interval, cron patterns)
- `langfuse_tracer.py` — LLM observability integration

**2. Trading Core** (`scripts/`)
- `mt5_manager.py` — MT5 connection handler
- `risk_manager.py` — Position sizing, daily loss limits, margin checks
- `advanced_trader.py` — Trading strategies (grid, breakout, scalping, etc.)
- `position_monitor.py` — Real-time position alerts

**3. News & Sentiment** (`scripts/`)
- `news_aggregator.py` — Multi-source news collection
- `news_db.py` — SQLite schema for news storage
- `ai_researcher.py` — AI tool integration (parallel requests)
- `sentiment_analyzer.py` — Keyword-based sentiment scoring

**4. CLI Surface** (`claw.py`)
- Commander-based CLI with subcommands
- ~2000 lines, integrates all components
- Agent commands: `claw.py agent <subcommand>`

**5. Supporting** (`scripts/`)
- `config_loader.py` — Load config.yaml with env overrides
- `config_validator.py` — TypeBox schema validation
- `trade_journal.py` — Trade analytics and journaling
- `logger.py` — Unified logging (~trades.log)
- `notifier.py` — Telegram notifications

### Data Flow

```
Market Event / Schedule Trigger
    ↓
SubAgent Orchestrator (pick role)
    ↓
AgentExecutor (dispatch to AI CLI tool)
    ├─ Tool Discovery
    ├─ Try Cache
    ├─ Execute subprocess
    ├─ Record History/Metrics
    └─ Trace to Langfuse
    ↓
AI CLI Tool Response
    ↓
Consensus/Analysis
    ↓
Trade Signal (BUY/SELL/HOLD)
    ↓
Risk Manager (position size, margin check)
    ↓
MT5 Execution
    ↓
Position Monitor → Telegram Alert
```

### Key Subsystems

**Session Model:**
- Single main session for CLI trading
- Sub-agent tasks are stateless (no session needed)

**Routing:**
- CLI agents route tasks based on role and preferred tool
- Fallback chain if tool unavailable

**Configuration:**
- JSON-based `config.yaml`
- Env var overrides (MT5_LOGIN, MT5_PASSWORD, etc.)
- Agent settings: preferred tools, cache TTL, scheduler config, Langfuse

**Security:**
- MT5 credentials in env vars or `.env` file
- Langfuse API keys in env or config (optional)
- Trade execution requires explicit confirmation (optional flag)

**Storage:**
- SQLite: `data/agent_history.db` (execution history)
- SQLite: `data/agent_scheduler.db` (task state)
- SQLite: `data/news.db` (news & sentiment)
- SQLite: `data/clawgold.db` (trade journal)
- JSON cache: `data/agent_cache/` (prompt responses)
- Logs: `logs/trades.log` (unified logging)

---

## Key Files & Entry Points

| File | Purpose | Lines |
|------|---------|-------|
| `claw.py` | Main CLI entry point | ~1971 |
| `scripts/agent_executor.py` | AI CLI executor (tool discovery, execution, cache, metrics) | ~641 |
| `scripts/sub_agent.py` | Sub-agent orchestrator (5 roles) | ~642 |
| `scripts/agent_scheduler.py` | Background scheduler | ~513 |
| `scripts/langfuse_tracer.py` | Langfuse observability | ~230 |
| `scripts/mt5_manager.py` | MT5 connection handler | ~400 |
| `scripts/ai_researcher.py` | AI tool integration | ~500 |
| `scripts/trade_journal.py` | Analytics engine | ~700 |
| `config.yaml` | Configuration file | ~140 |
| `test/test_agent_system.py` | 27 agent system tests | ~310 |
| `templates/prompts/agent_*.txt` | Role-specific prompt templates | 3 files |

### Critical Directories

```
ClawGold/
├── claw.py              # Main CLI
├── config.yaml          # Configuration
├── requirements.txt     # Dependencies
├── AGENT.md            # Agent system docs
├── CLAUDE.md           # This file
├── README.md           # Project overview
├── CHANGELOG.md        # Release notes
├── scripts/
│   ├── agent_*.py      # Agent system (4 files)
│   ├── mt5_manager.py
│   ├── risk_manager.py
│   ├── advanced_trader.py
│   ├── position_monitor.py
│   ├── trade_journal.py
│   ├── news_*.py
│   ├── sentiment_analyzer.py
│   ├── config_loader.py
│   ├── config_validator.py
│   ├── logger.py
│   └── notifier.py
├── data/               # SQLite & cache
│   ├── agent_history.db
│   ├── agent_scheduler.db
│   ├── news.db
│   ├── clawgold.db
│   └── agent_cache/
├── logs/
│   └── trades.log
├── templates/
│   └── prompts/
│       ├── agent_research.txt
│       ├── agent_trade_setup.txt
│       └── agent_macro_impact.txt
└── test/
    ├── test_agent_system.py
    └── ...
```

---

## Dependencies & Environment

### Core Dependencies
- `yfinance` — Market data
- `pandas`, `numpy` — Data processing
- `MetaTrader5` — Trading execution (Windows only)
- `PyYAML` — Configuration
- `requests`, `forex-python` — API calls
- `scikit-learn` — Sentiment analysis
- `langgraph` — Agent graph orchestration
- `langfuse` — LLM observability (optional)

### Development Tools
- `unittest` — Testing (built-in)
- `sqlite3` — Database (built-in)

### Environment Variables
```bash
# MT5 Credentials (prefer env vars over config.yaml)
export MT5_LOGIN=12345678
export MT5_PASSWORD=your_password
export MT5_SERVER=MetaQuotes-Demo

# Langfuse (optional, for observability)
export LANGFUSE_PUBLIC_KEY=pk_...
export LANGFUSE_SECRET_KEY=sk_...

# Telegram (optional, for notifications)
export TELEGRAM_BOT_TOKEN=...
export TELEGRAM_CHAT_ID=...

# Trading Settings
export TRADING_MODE=real          # or simulation
export RISK_PER_TRADE=0.01
```

---

## Code Style & Conventions

### Naming
- **Product/App:** "Moltbot" (capital M for brand)
- **CLI:** "moltbot" or "clawgold" (lowercase for commands)
- **Config:** `YAML` file (`config.yaml`)

### Type Safety
- Strict TypeScript mode (for future TS code)
- Optional type hints in Python (dataclasses used extensively)
- Use `from typing import ...` for type annotations

### File Size Guideline
- Target: ~700 lines per module
- Consider splitting if >1000 lines
- Keep helper functions in separate `*_helper.py` or `*_utils.py`

### Logging
```python
from logger import get_logger

logger = get_logger(__name__)

logger.info(f"Agent execution: {tool}")
logger.error(f"Failed to connect MT5: {error}")
```

### Testing
- Unit tests in `test/` directory
- Naming: `test_*.py` or `*_test.py`
- Use `unittest.TestCase` or `unittest.mock.patch`
- Aim for 70%+ coverage

### Git Conventions
- Branch: `feature/agent-system`, `fix/cache-bug`, etc.
- Commit: "Add agent scheduler with defaults" (imperative tense)
- PR: Describe what changed and why

---

## Common Development Tasks

### Add a New CLI Agent Command

1. **Add method to `SubAgentOrchestrator`** (`scripts/sub_agent.py`):
   ```python
   def my_new_command(self, param1: str) -> Dict[str, Any]:
       prompt = f"Your prompt template here: {param1}"
       return self._dispatch("analyst", "my_command", prompt)
   ```

2. **Add handler in `claw.py`**:
   ```python
   def cmd_agent_mynewcommand(args):
       from sub_agent import SubAgentOrchestrator
       orch = SubAgentOrchestrator()
       result = orch.my_new_command(args.param1)
       _print_agent_result(result)
   
   # Add to parser
   agent_subparsers.add_parser("mynew", help="Description...")
   ```

3. **Add to CLI routing**:
   ```python
   elif args.agent_command == "mynew":
       cmd_agent_mynewcommand(args)
   ```

### Add a New Trading Strategy

1. **Create strategy in `scripts/advanced_trader.py`**:
   ```python
   def strategy_my_new(self, symbol, timeframe, **kwargs):
       # Implement logic
       return {"signal": "BUY", "confidence": 0.85}
   ```

2. **Register in strategy list** (near top of `advanced_trader.py`)

3. **Reference in trading execution** (`claw.py` trade command)

### Integrate a New AI CLI Tool

1. **Add to `AgentTool` enum** (`scripts/agent_executor.py`):
   ```python
   class AgentTool(Enum):
       MY_TOOL = "mytool"
   ```

2. **Add command mapping** (in `TOOL_COMMANDS`):
   ```python
   AgentTool.MY_TOOL: {
       'check': ['mytool', '--version'],
       'run': lambda prompt: ['mytool', 'run', prompt],
       'install': 'pip install mytool-cli',
       'timeout': 180,
   }
   ```

3. **Add to config.yaml** preferred_tools list (if suitable)

4. **Test discovery** — AgentExecutor will auto-detect when available

### Add a Feature to Agent Scheduler

1. **Extend `ScheduledTask` dataclass** if new fields:
   ```python
   @dataclass
   class ScheduledTask:
       # Add field
       retry_on_failure: bool = False
   ```

2. **Update `_load_tasks()` and `_save_task()`** to handle persistence

3. **Update `_should_run_now()` or scheduler logic** in `start()` loop

4. **Add CLI command** for users to control

### Add Langfuse Monitoring to New Code

1. **Import tracer**:
   ```python
   from langfuse_tracer import get_tracer
   ```

2. **Initialize in class**:
   ```python
   self.tracer = get_tracer(enabled=True)
   ```

3. **Wrap executions**:
   ```python
   with self.tracer.trace_execution("operation", task_name) as trace:
       result = run_task()
       trace.success = result.success
   ```

---

## Common Issues & Solutions

### MT5 Connection Failed
```python
# Check
python claw.py balance

# Debug
python claw.py validate

# Ensure MT5 running on Windows
# Check creds in config.yaml or .env
```

### AI Tool Not Discovered
```bash
python claw.py agent tools
# Shows which are missing

# Install manually
npm install -g opencode      # OpenCode
npm install -g @google/gemini-cli  # Gemini
# KiloCode: https://kilo.ai
# Codex: https://codex.ai
```

### SQLite Database Locked
```bash
# Remove lock file
rm data/*.db-journal

# Or restart Python process
```

### Tests Timeout
- Increase timeout in test runner: `python -m unittest … --verbose --timeout 30`
- Check if subprocess calls are hanging

### Langfuse Not Tracing
- Verify API key: `export LANGFUSE_PUBLIC_KEY=pk_...`
- Check `config.yaml` — `agent.langfuse.enabled: true`
- Verify network connectivity to Langfuse API

---

## Performance Considerations

### Agent Execution
- **Single tool**: ~2-5 seconds (typical)
- **Consensus (3 tools)**: ~6-15 seconds
- **Cache hit**: < 100ms

### Database Queries
- Recent history (LIMIT 20): < 10ms
- Metrics aggregation: < 50ms
- Schedule status: < 10ms

### Background Scheduler
- Single-threaded (sequential task execution)
- Position check every 10 min: ~5 second window per check
- No blocking on long-running tasks (async in future?)

### Cost Tracking
- Token estimation: rough (1 token ≈ 4 chars)
- Costs per 1k tokens (configurable in config.yaml)
- Accumulated in Langfuse dashboard

---

## Release Checklist

When releasing a new version:

- [ ] Update `CHANGELOG.md` with features/fixes
- [ ] Update `README.md` if docs changed
- [ ] Update `AGENT.md` if agent system changed
- [ ] Run full test suite: `python -m unittest discover -s test -v`
- [ ] Verify no errors in `get_errors` on modified modules
- [ ] Test CLI: `python claw.py agent daily`
- [ ] Verify scheduler: `python claw.py agent schedule status`
- [ ] Check Langfuse integration (if enabled)
- [ ] Bump version in code or config if tracked
- [ ] Create git tag/release

---

## Documentation Links

- **Agent System** — [`AGENT.md`](AGENT.md)
- **README** — [`README.md`](README.md)
- **Architecture** — [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- **API Reference** — [`docs/API_REFERENCE.md`](docs/API_REFERENCE.md)
- **Quick Start** — [`docs/QUICKSTART.md`](docs/QUICKSTART.md)
- **Changelog** — [`CHANGELOG.md`](CHANGELOG.md)

---

## Tips for Working with This Codebase

1. **Always run tests before committing**
   ```bash
   python -m unittest discover -s test -v
   ```

2. **Check logs during development**
   ```bash
   tail -f logs/trades.log
   ```

3. **Validate config changes**
   ```bash
   python claw.py validate
   ```

4. **Review agent performance**
   ```bash
   python claw.py agent metrics
   ```

5. **Test new features on smaller time windows** (e.g., 1H data, not 1D)

6. **Use Langfuse dashboard** to identify slow/expensive queries

7. **Keep prompt templates** in `templates/prompts/` for easy iteration

8. **Write tests for new agent roles** before implementation

---

*ClawGold — Autonomous Gold Trading Powered by AI Sub-Agents 🦞*

