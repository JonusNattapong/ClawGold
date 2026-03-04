# ClawGold Agent System Documentation

## Overview

ClawGold's **Agent System** is a Sub-Agent orchestration framework that dispatches trading tasks to external AI CLI tools (OpenCode, KiloCode, Gemini, Codex) as autonomous agents. **No model training required** — all intelligence comes from pre-trained AI via CLI commands.

The system includes:
- **Agent Executor** — Unified interface for running CLI tools with caching, metrics, and fallback
- **Sub-Agent Orchestrator** — Role-based dispatch (researcher, analyst, strategist, monitor)
- **Agent Scheduler** — Background automation for daily/periodic tasks
- **Langfuse Integration** — LLM observability, cost tracking, and quality evaluation

---

## Architecture

```
User/CLI
   ↓
SubAgent Orchestrator (high-level roles)
   ↓
AgentExecutor (unified CLI execution)
   ├─ Tool Discovery (shutil.which)
   ├─ Prompt Builder
   ├─ Subprocess Manager
   ├─ Cache (JSON files + SQLite TTL)
   ├─ History DB (SQLite)
   ├─ Metrics Tracking
   ├─ Cost Estimation
   └─ Langfuse Tracing
   ↓
AI CLI Tools (opencode, kilocode, gemini, codex)
```

---

## Core Components

### 1. AgentExecutor (`scripts/agent_executor.py`)

Low-level unified interface for all AI CLI tools.

**Key Features:**
- **Tool Discovery** — Auto-detects installed tools via `shutil.which()`
- **Caching** — JSON file cache with configurable TTL
- **History DB** — SQLite record of all executions (tool, prompt, response, time, error)
- **Metrics** — Per-tool success rate, avg response time, total calls
- **Fallback Chain** — `run_best()` tries tools in order of success rate
- **Parallel Execution** — `run_parallel()` and `consensus()` for multi-tool aggregation
- **Langfuse Tracing** — Records every execution for observability

**Usage:**
```python
from scripts.agent_executor import AgentExecutor

executor = AgentExecutor(
    cache_dir="data/agent_cache",
    cache_ttl_hours=4,
    db_path="data/agent_history.db",
    langfuse_enabled=True,  # Optional
    langfuse_api_key="pk_..."  # From env or config
)

# Run on specific tool
result = executor.run("gemini", "Analyze XAUUSD trends")
print(result.response, result.execution_time, result.success)

# Auto-select best tool
result = executor.run_best("What drives gold price today?")

# Get consensus from multiple tools
consensus = executor.consensus("XAUUSD outlook")
print(consensus['combined_response'], consensus['agreement'])
```

**CLI Tool Commands:**
| Tool | Command | Purpose |
|------|---------|---------|
| OpenCode | `opencode run "<prompt>"` | General analysis |
| KiloCode | `kilo run "<prompt>"` | Market analysis |
| Gemini | `gemini "<prompt>"` | Reasoning, summaries |
| Codex | `codex exec "<prompt>"` | Code generation |

### 2. SubAgentOrchestrator (`scripts/sub_agent.py`)

High-level orchestrator with domain-specific roles.

**5 Sub-Agent Roles:**
1. **Researcher** — Market research, news analysis, information gathering
2. **Analyst** — Technical analysis, pattern recognition, chart reading
3. **Strategist** — Trading plan generation, strategy design
4. **Monitor** — Position review, risk assessment
5. **General** — Custom queries without role template

**Key Methods:**
```python
from scripts.sub_agent import SubAgentOrchestrator

orch = SubAgentOrchestrator(
    preferred_tool="gemini",  # Optional
    use_consensus=False,
    langfuse_enabled=True,
    langfuse_api_key="pk_..."
)

# Research
report = orch.research("Fed impact on gold prices")

# Analysis
analysis = orch.analyze("XAUUSD technical setup", price=2950.50, timeframe="H1")

# Planning
plan = orch.plan(symbol="XAUUSD")

# Position review
review = orch.review_positions(positions_json="...")

# Risk assessment
risk = orch.assess_risk(balance=10000, equity=9500, margin_level=500)

# News digest
news = orch.news_digest(query="gold market news")

# Daily routine (5-step workflow)
daily = orch.daily_routine()

# Quick consensus
outlook = orch.quick_outlook("XAUUSD short-term outlook")
```

**Task Log:**
All dispatched tasks are logged in `orch._task_log` with timestamps, roles, and results.

```python
for task in orch._task_log:
    print(task.role, task.task_type, task.completed_at, task.result.success)
```

### 3. AgentScheduler (`scripts/agent_scheduler.py`)

Background scheduler for automated periodic tasks.

**Schedule Types:**
- `DAILY` — At specific time (e.g., "07:00")
- `INTERVAL` — Every N seconds (e.g., 600 = every 10 min)
- `CRON` — Weekday + time (e.g., "MON,FRI 09:00")

**Default Tasks (7):**
| Task | Schedule | Purpose |
|------|----------|---------|
| `morning_research` | Daily 07:00 | Pre-market analysis |
| `morning_plan` | Daily 07:30 | Trading plan |
| `midday_analysis` | Daily 12:00 | Midday review |
| `position_check` | Every 10min | Monitor positions |
| `afternoon_risk` | Daily 15:00 | Risk assessment |
| `daily_summary` | Daily 17:00 | End-of-day summary |
| `evening_research` | Daily 20:00 | After-hours analysis |

**Usage:**
```python
from scripts.agent_scheduler import AgentScheduler

scheduler = AgentScheduler(db_path="data/agent_scheduler.db")

# Add custom task
scheduler.add_task(
    name="weekly_review",
    schedule_type="daily",
    schedule_value="09:00",
    task_type="research",
    task_params={"query": "Weekly XAUUSD review"}
)

# Enable/disable
scheduler.enable_task("morning_research")
scheduler.disable_task("evening_research")

# List all
print(scheduler.list_tasks())

# View log
print(scheduler.get_log(limit=20))

# Start background daemon
scheduler.start(blocking=False)  # or blocking=True

# Stop
scheduler.stop()
```

### 4. LangfuseTracer (`scripts/langfuse_tracer.py`)

LLM observability integration for tracing, cost tracking, and evaluation.

**What Gets Traced:**
- Agent tool executions (prompts, responses, latency)
- Token count estimation
- Cost calculation (configurable rates)
- Success/failure status
- Execution history

**Usage:**
```python
from scripts.langfuse_tracer import get_tracer

tracer = get_tracer(
    api_key="pk_...",  # From config or env LANGFUSE_PUBLIC_KEY
    project_name="clawgold-agents",
    enabled=True
)

# Trace a single execution
with tracer.trace_execution("research", "gold outlook") as trace:
    result = agent.run("gemini", prompt)
    trace.success = result.success

# Manual recording
tracer.trace_agent_run(
    tool="gemini",
    prompt="What drives gold?",
    response="Gold responds to...",
    execution_time=2.3,
    success=True
)

# Score an execution
tracer.score_execution(
    trace_id="some-trace-id",
    score=0.92,  # 0-1
    comment="Accurate analysis"
)

# Flush to Langfuse
tracer.flush()
```

### 5. AI-Enhanced Subsystems

The ClawGold system prioritizes AI-driven reasoning over static pattern matching in several key areas:

1.  **Sentiment Analysis** (`sentiment_analyzer.py`):
    *   **Logic**: `analyze_text(use_ai=True)` uses **Gemini/KiloCode** to interpret news context, sarcasm, and macro-economic nuances.
    
2.  **Risk Management** (`risk_manager.py`):
    *   **Logic**: `get_dynamic_risk_recommendation()` asks **Analyst sub-agents** to adjust risk multipliers (0.5x - 1.5x) based on impending news or unusual volatility.

3.  **Decision Engine** (`decision_engine.py`):
    *   **Logic**: `validate_with_ai_consensus()` triggers a multi-agent consensus (OpenCode + Gemini + Codex) to confirm if a technical signal aligns with current macro/fundamental reality.

---

## CLI Integration

All agents are accessible via the main CLI in `claw.py`:

```bash
# Run a task on specific tool
python claw.py agent run gemini "Analyze XAUUSD"
python claw.py agent run opencode "Trading plan for XAUUSD"

# Sub-agent roles
python claw.py agent research "Fed interest rate outlook"
python claw.py agent analyze "XAUUSD support/resistance"
python claw.py agent plan --symbol XAUUSD
python claw.py agent review         # Review positions
python claw.py agent risk           # Risk assessment
python claw.py agent news "gold market sentiment"
python claw.py agent daily          # Full daily routine
python claw.py agent outlook        # Consensus outlook

# Utilities
python claw.py agent tools          # List available CLI tools
python claw.py agent history        # Show execution history (last 20)
python claw.py agent metrics        # Per-tool performance metrics

# Scheduler
python claw.py agent schedule start    # Start background daemon
python claw.py agent schedule status   # Show all tasks
python claw.py agent schedule log      # View execution log
python claw.py agent schedule add --name weekly_review --type daily --value "09:00" --task research --params '{"query":"..."}'
python claw.py agent schedule remove --name custom_task
python claw.py agent schedule toggle --name morning_research --state on
```

---

## Configuration

### `config.yaml` — Agent Settings

```yaml
agent:
  # Tool preferences
  preferred_tools:
    - gemini      # Try first
    - opencode
    - kilocode
    - codex       # Fallback

  # Cache settings
  cache:
    enabled: true
    ttl_hours: 4
    dir: "data/agent_cache"

  # Execution defaults
  execution:
    timeout: 120           # seconds per CLI call
    max_parallel: 3        # concurrent tools for consensus
    consensus_tools: 3     # how many tools for agreement

  # Scheduler
  scheduler:
    enabled: false         # Set true to auto-start daemon
    db_path: "data/agent_scheduler.db"
    tasks:
      morning_research:
        time: "07:00"
        enabled: true
      # ... more tasks

  # Langfuse observability
  langfuse:
    enabled: false
    api_key: ""            # Or env LANGFUSE_PUBLIC_KEY
    secret_key: ""         # Or env LANGFUSE_SECRET_KEY
    project_name: "clawgold"
    
    trace:
      agent_execution: true
      orchestrator_dispatch: true
      daily_routine: true
    
    cost_tracking:
      enabled: true
      rates:
        gemini:
          input: 0.00075
          output: 0.003
        opencode:
          input: 0.001
          output: 0.004
```

---

## Data Storage

### Execution History (`data/agent_history.db`)
SQLite database with agent execution records.

**Tables:**
- `agent_history` — Individual tool runs (tool, task, response, success, time, error)

**Query Examples:**
```sql
-- Recent 10 executions
SELECT * FROM agent_history ORDER BY created_at DESC LIMIT 10;

-- Success rate by tool
SELECT tool, 
       COUNT(*) as calls,
       SUM(CASE WHEN success=1 THEN 1 ELSE 0 END) as successes,
       ROUND(100.0 * SUM(CASE WHEN success=1 THEN 1 ELSE 0 END) / COUNT(*), 1) as success_rate
FROM agent_history
GROUP BY tool;

-- Average response time by tool
SELECT tool, AVG(execution_time) as avg_time FROM agent_history GROUP BY tool;
```

### Cache (`data/agent_cache/`)
JSON files with **task hash** as filename. Each file contains:
```json
{
  "task": "...",
  "response": "...",
  "cached_at": "2026-03-04T10:30:00",
  "expires_at": "2026-03-04T14:30:00"
}
```

Cache TTL is configurable (default 4 hours). Stale entries are auto-skipped.

### Scheduler State (`data/agent_scheduler.db`)
SQLite database for task persistence.

**Tables:**
- `scheduled_tasks` — Task definitions (name, schedule, enabled, last_run, run_count)
- `schedule_log` — Execution log (task_name, success, response_preview, error, time)

---

## Examples

### Example 1: Morning Market Analysis

```python
from scripts.sub_agent import SubAgentOrchestrator

orch = SubAgentOrchestrator(preferred_tool="gemini")

# 1. Research
research = orch.research("Gold market drivers today: Fed statements, DXY, yields")
print(f"Research: {research['response'][:200]}...")

# 2. Technical Analysis
analysis = orch.analyze("XAUUSD H1 chart", price=2950.50, timeframe="H1")
print(f"Analysis: {analysis['response'][:200]}...")

# 3. Trading Plan
plan = orch.plan(symbol="XAUUSD")
print(f"Plan: {plan['response'][:200]}...")

# 4. Risk Assessment
risk = orch.assess_risk(balance=10000, equity=9500, margin_level=500)
print(f"Risk: {risk['response'][:200]}...")
```

### Example 2: Consensus Decision

```python
executor = AgentExecutor()

# Get opinion from multiple tools
consensus = executor.consensus("Should I buy XAUUSD now?")

print(f"Consensus: {consensus['consensus_sentiment']}")
print(f"Agreement: {consensus['agreement']}%")
print(f"Tools used: {', '.join(consensus['tools_used'])}")
print(f"Response: {consensus['combined_response'][:300]}...")
```

### Example 3: Automated Daily Routine

```bash
# Start scheduler
python claw.py agent schedule start

# Or run once
python claw.py agent daily
```

This runs a 5-step workflow:
1. Morning research (market drivers, news)
2. Trading plan generation
3. Technical analysis
4. Position review (if any open)
5. Risk assessment summary

### Example 4: Position Monitoring

```python
from scripts.sub_agent import SubAgentOrchestrator

orch = SubAgentOrchestrator()

# Review open positions
positions_json = """
[
  {"ticket": 123456, "symbol": "XAUUSD", "type": "BUY", "volume": 0.1, "open_price": 2940, "current_price": 2950, "pnl": 100},
  {"ticket": 123457, "symbol": "XAUUSD", "type": "SELL", "volume": 0.05, "open_price": 2960, "current_price": 2950, "pnl": 50}
]
"""

review = orch.review_positions(positions_json)
print(review['response'])
```

---

## Debugging & Troubleshooting

### Check Available Tools
```bash
python claw.py agent tools
# Output:
#   Available AI CLI tools:
#   - opencode (available, success_rate: 95.2%)
#   - kilocode (available, success_rate: 92.1%)
#   - gemini (available, success_rate: 98.5%)
#   - codex (not installed)
```

### View Execution History
```bash
python claw.py agent history
# Shows last 20 executions with tool, task, success, time
```

### Check Performance Metrics
```bash
python claw.py agent metrics
# Shows per-tool: total_calls, successes, failures, success_rate, avg_response_time
```

### View Scheduler Log
```bash
python claw.py agent schedule log
# Shows recent scheduled task executions
```

### Enable Verbose Logging
```bash
# Logs go to: logs/trades.log (configured in config.yaml)
tail -f logs/trades.log | grep agent_executor
```

### Test Individual Tool
```python
from scripts.agent_executor import AgentExecutor

executor = AgentExecutor()
result = executor.run("gemini", "Test prompt")
print(f"Success: {result.success}")
print(f"Response: {result.response}")
print(f"Error: {result.error}")
print(f"Time: {result.execution_time}s")
```

---

## Langfuse Observability

### Setup

1. **Get API keys** from [langfuse.com](https://langfuse.com)
2. **Set in config.yaml** or environment:
   ```bash
   export LANGFUSE_PUBLIC_KEY="pk_..."
   export LANGFUSE_SECRET_KEY="sk_..."
   ```
3. **Enable in config:**
   ```yaml
   agent:
     langfuse:
       enabled: true
   ```

### Dashboard Insights

In Langfuse web UI:
- **Traces** — Every agent execution with input/output
- **Costs** — Aggregated by tool, shows cost trends
- **Performance** — Success rate, latency trends
- **Evaluations** — Custom quality scores you add

### Manual Scoring

```python
from scripts.langfuse_tracer import get_tracer

tracer = get_tracer()
tracer.score_execution(
    trace_id="abc123",
    score=0.85,
    comment="Good forecast, minor timing issue"
)
```

---

## Best Practices

1. **Use Consensus for Important Decisions**
   ```python
   # For trading decisions, use consensus
   consensus = executor.consensus("XAUUSD buy signal confirmation?")
   if consensus['agreement'] > 70:
       # Proceed with trade
   ```

2. **Cache Appropriate Queries**
   - Market outlook queries (4-hour TTL is fine)
   - Technical analysis (can cache for session)
   - News queries (should not cache — needs freshness)

3. **Monitor Tool Performance**
   ```bash
   # Check metrics regularly
   python claw.py agent metrics
   # Gemini: 98% success → use as primary
   # Codex: 60% success → use as fallback only
   ```

4. **Schedule Lightweight Tasks Frequently**
   - Position check: every 10 minutes ✓
   - Daily research: once at 07:00 ✓
   - Consensus outlook: only when needed ✗ (too slow)

5. **Set Reasonable Timeouts**
   - CLI tools: 120-180 seconds default
   - Parallel requests: add margin to default
   - Consensus: multiply single timeout × tool count

6. **Review Langfuse Regularly**
   - What tools fail most?
   - Which queries are most expensive?
   - Can you optimize expensive queries?

---

## API Reference

### AgentExecutor

```python
class AgentExecutor:
    def run(tool: str, task: str, use_cache: bool = True, 
            timeout: Optional[int] = None) -> AgentResult
    
    def run_best(task: str, use_cache: bool = True) -> AgentResult
    
    def run_parallel(task: str, tools: Optional[List[str]] = None) -> List[AgentResult]
    
    def consensus(task: str, tools: Optional[List[str]] = None) -> Dict
    
    def get_available_tools() -> List[AgentCapability]
    
    def get_history(limit: int = 20) -> List[Dict]
    
    def get_metrics() -> Dict[str, Dict]
```

### SubAgentOrchestrator

```python
class SubAgentOrchestrator:
    def research(query: str, tool: Optional[str] = None) -> Dict
    
    def analyze(query: str, price: Optional[float] = None, 
                timeframe: Optional[str] = None) -> Dict
    
    def plan(symbol: str = "XAUUSD", tool: Optional[str] = None) -> Dict
    
    def review_positions(positions_json: str) -> Dict
    
    def assess_risk(balance: float, equity: float, margin_level: float) -> Dict
    
    def news_digest(query: str) -> Dict
    
    def ask(query: str, tool: Optional[str] = None) -> Dict
    
    def daily_routine() -> Dict
    
    def quick_outlook(query: str) -> Dict
    
    def get_available_roles() -> List[str]
    
    def get_task_log() -> List[SubAgentTask]
```

### AgentScheduler

```python
class AgentScheduler:
    def add_task(name: str, schedule_type: str, schedule_value: str,
                 task_type: str, task_params: Optional[Dict] = None) -> ScheduledTask
    
    def remove_task(name: str) -> bool
    
    def enable_task(name: str) -> bool
    
    def disable_task(name: str) -> bool
    
    def list_tasks() -> List[Dict]
    
    def get_log(limit: int = 20) -> List[Dict]
    
    def start(blocking: bool = True) -> None
    
    def stop() -> None
```

---

## Related Files

- **Main CLI** — [`claw.py`](claw.py)
- **Config** — [`config.yaml`](config.yaml)
- **Tests** — [`test/test_agent_system.py`](test/test_agent_system.py) (27 tests)
- **Prompts** — [`templates/prompts/agent_*.txt`](templates/prompts/)
- **Architecture** — [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)

