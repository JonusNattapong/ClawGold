"""
SubAgent Orchestrator — Enhanced with Smart Routing
====================================================
High-level orchestrator that dispatches domain-specific tasks to AI CLI agents.
Now leverages real CLI capabilities discovered from ``--help`` output:

  - Smart routing: auto-picks best tool per role/task category
  - Structured output: JSON schema validation for trade signals & risk
  - Web search: live internet queries for research roles
  - Full-auto mode: for unattended batch workflows

Roles:
  - researcher: Market research + news analysis (→ Gemini/Codex web search)
  - analyst: Technical analysis (→ OpenCode/Codex)
  - strategist: Trading plan generation (→ Claude structured output)
  - monitor: Position review + risk assessment (→ Claude JSON schema)
  - executor: Trade decision support (always requires human confirmation)

Usage::

    from sub_agent import SubAgentOrchestrator

    orch = SubAgentOrchestrator()
    signal  = orch.get_trade_signal("XAUUSD H4 breakout setup")
    outlook = orch.research_with_web("gold price drivers", web_search=True)
    daily   = orch.daily_routine()
"""

import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from logger import get_logger
from agent_executor import AgentExecutor, AgentResult, TaskCategory
from agent_graph import AgentLangGraphOrchestrator

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Prompt Templates — the domain knowledge that makes agents effective
# ---------------------------------------------------------------------------

PROMPTS = {
    # --- Researcher ---
    'market_research': """You are a senior gold (XAUUSD) market analyst.

Research the following query and provide a structured report:

QUERY: {query}

Respond in this exact format:
## Summary
(2-3 sentence overview)

## Key Findings
- Finding 1
- Finding 2
- Finding 3

## Market Drivers
- Driver 1 (impact: high/medium/low)
- Driver 2

## Sentiment Assessment
Direction: BULLISH / BEARISH / NEUTRAL
Confidence: 0-100%
Timeframe: short-term / medium-term

## Risk Factors
- Risk 1
- Risk 2

## Trading Implications
(Specific, actionable insights for XAUUSD traders)

Be concise, data-driven, and factual.""",

    # --- Analyst ---
    'technical_analysis': """You are an expert technical analyst specializing in XAUUSD (Gold).

Analyze the current technical picture for {symbol}:

Current Price: {price}
Timeframe Focus: {timeframe}
{extra_context}

Provide analysis in this format:
## Technical Overview
(Current trend, key levels, pattern)

## Support & Resistance
- S1: (price) — reason
- S2: (price) — reason
- R1: (price) — reason
- R2: (price) — reason

## Indicators
- Trend: (up/down/sideways)
- Momentum: (strong/weak/diverging)
- Volume: (high/normal/low)

## Patterns
(Any chart patterns or formations)

## Trade Setups
1. Setup name — Entry/SL/TP/Risk:Reward
2. Setup name — Entry/SL/TP/Risk:Reward

## Bias
Direction: BUY / SELL / NEUTRAL
Confidence: 0-100%""",

    # --- Strategist ---
    'trading_plan': """You are a professional XAUUSD trading strategist.

Generate a detailed trading plan for today based on:

Symbol: {symbol}
Account Balance: {balance}
Open Positions: {positions}
Risk Per Trade: {risk_per_trade}
Market Condition: {market_condition}
Recent Performance: {performance_summary}

Create a structured trading plan:

## Daily Trading Plan — {date}

### Market Assessment
(Current market regime and key themes)

### Today's Key Events
(Economic events that could impact gold)

### Trade Setups (ordered by priority)
1. **Setup Name**
   - Direction: BUY/SELL
   - Entry: (price or condition)
   - Stop Loss: (price)
   - Take Profit: (price)
   - Risk:Reward: (ratio)
   - Confidence: (0-100%)
   - Rationale: (why)

2. **Setup Name**
   ...

### Risk Rules for Today
- Max trades: (number)
- Max daily loss: ${max_loss}
- Position sizing: (lots per trade)

### What to Avoid
(Situations to stay out of)

### End-of-Day Review Checklist
- [ ] Did I follow the plan?
- [ ] Did I respect risk limits?
- [ ] What can I improve?""",

    # --- Position Reviewer ---
    'position_review': """You are a risk management specialist reviewing open trading positions.

Current open positions:
{positions_detail}

Account Info:
- Balance: {balance}
- Equity: {equity}
- Margin Level: {margin_level}%
- Total P/L: {total_pnl}

Provide a comprehensive review:

## Position Assessment
(For each position — is it still valid? Should we adjust?)

## Risk Exposure
- Total risk: (amount and %)
- Correlation risk: (are positions correlated?)
- Event risk: (upcoming events that could impact)

## Recommendations
1. (Action item with specific levels)
2. (Action item)

## Overall Portfolio Health
Score: (1-10)
Status: HEALTHY / CAUTION / DANGER""",

    # --- Risk Assessor ---
    'risk_assessment': """You are a quantitative risk analyst for a gold trading operation.

Assess the risk profile:

Portfolio: {portfolio_summary}
Recent Trades (last 7 days): {recent_trades}
Win Rate: {win_rate}
Profit Factor: {profit_factor}
Max Drawdown: {max_drawdown}

Provide risk analysis:

## Risk Score
Overall: (1-10, 10 = highest risk)

## Key Risk Metrics
- Value at Risk (VaR): estimated daily
- Position concentration: (single asset?)
- Leverage utilization: (margin usage %)
- Win/Loss streak: (current streak)

## Risk Warnings
(Any immediate concerns)

## Recommendations
1. (Specific risk reduction action)
2. (Parameter adjustment suggestion)

## Optimal Position Size
For next trade: (suggested lots) based on Kelly Criterion or similar""",

    # --- General task ---
    'general': """You are an AI trading assistant for ClawGold (XAUUSD trading system).

{task}

Provide a clear, structured, actionable response.
Focus on practical trading insights for gold markets.""",

    # --- Daily Summary ---
    'daily_summary': """You are the chief analyst for a gold trading desk.

Compile a daily summary report:

Date: {date}

## Today's Market Data
- XAUUSD Price: {price}
- Daily Change: {change}
- Open Positions: {positions_count}
- Daily P/L: {daily_pnl}

## Recent Trading Activity
{recent_activity}

## AI Research Consensus
{research_consensus}

Provide a concise daily report:

## 🦞 ClawGold Daily Report — {date}

### Market Summary
(What happened today in gold)

### Performance
(Trading results and portfolio status)

### Outlook
(What to expect tomorrow)

### Action Items
1. (What to do before market open)
2. (Positions to adjust)
3. (Research to conduct)""",

    # --- News Digest ---
    'news_digest': """You are a financial news analyst specializing in gold and commodities.

Research and compile a news digest about:
{topics}

Focus on:
1. Events that directly impact XAUUSD price
2. Central bank decisions (Fed, ECB, BOJ)
3. Geopolitical risks affecting safe-haven demand
4. USD strength/weakness drivers
5. Real yields and inflation expectations

Provide structured output:

## Gold News Digest

### Headlines (most impactful first)
1. **Headline** — Impact: HIGH/MED/LOW — Sentiment: BULLISH/BEARISH

### Key Themes
- Theme 1: (explanation)
- Theme 2: (explanation)

### Market Impact Assessment
Net sentiment: BULLISH / BEARISH / NEUTRAL
Confidence: 0-100%
Expected price impact: (direction and magnitude)""",
}


@dataclass
class SubAgentTask:
    """Tracks a sub-agent task execution."""
    role: str
    task_type: str
    prompt: str
    tool_preference: Optional[str] = None
    result: Optional[AgentResult] = None
    consensus: Optional[Dict] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class SubAgentOrchestrator:
    """
    Orchestrates AI CLI tools as sub-agents for trading tasks.
    
    Roles:
        - researcher: Market research and news analysis
        - analyst: Technical analysis and pattern recognition
        - strategist: Trading plan and strategy generation
        - monitor: Position review and risk assessment
        - executor: Trade decision support (always requires human confirmation)
    """

    def __init__(self, preferred_tool: Optional[str] = None,
                 use_consensus: bool = False,
                 use_langgraph: bool = True):
        """
        Args:
            preferred_tool: Default tool to use (None = auto-select best)
            use_consensus: Run all tools and use consensus (slower but more robust)
            use_langgraph: Use LangGraph for orchestration
        """
        # Centralized executor from config_loader
        try:
            from scripts.config_loader import get_agent_executor
            self.executor = get_agent_executor()
        except ImportError:
            self.executor = AgentExecutor()

        self.preferred_tool = preferred_tool
        self.use_consensus = use_consensus
        self.use_langgraph = use_langgraph
        self._task_log: List[SubAgentTask] = []
        
        # Initialize tracer
        class MockSubTracer:
            def trace_execution(self, *args, **kwargs):
                class MockMeta:
                    def __init__(self): self.success = True; self.tool = "none"
                    def __enter__(self): return self
                    def __exit__(self, *args, **kwargs): pass
                return MockMeta()
        
        try:
            from scripts.langfuse_tracer import get_tracer
            self.tracer = get_tracer(enabled=False)
            if not hasattr(self.tracer, 'trace_execution'):
                self.tracer = MockSubTracer()
        except Exception:
            self.tracer = MockSubTracer()

        self.graph = AgentLangGraphOrchestrator(self)

    # ------------------------------------------------------------------
    # Core dispatch
    # ------------------------------------------------------------------

    def _dispatch(self, role: str, task_type: str, prompt: str,
                  tool: Optional[str] = None,
                  output_mode: str = "text",
                  json_schema: Optional[dict] = None,
                  web_search: bool = False,
                  category: Optional[TaskCategory] = None) -> Dict[str, Any]:
        """
        Dispatch a task to AI agent(s) with enhanced CLI flag support.

        Args:
            role: Sub-agent role name
            task_type: Type identifier for logging
            prompt: Full prompt text
            tool: Force specific tool (None = auto-select)
            output_mode: "text" | "json" | "stream"
            json_schema: JSON schema dict for claude --json-schema
            web_search: Enable web search (codex --search)
            category: TaskCategory for smart routing

        Returns standardized result dict.
        """
        task = SubAgentTask(
            role=role, task_type=task_type, prompt=prompt,
            tool_preference=tool or self.preferred_tool,
            started_at=datetime.now().isoformat(),
        )

        run_kwargs = {}
        if output_mode != "text":
            run_kwargs['output_mode'] = output_mode
        if json_schema:
            run_kwargs['json_schema'] = json_schema
        if web_search:
            run_kwargs['web_search'] = web_search

        with self.tracer.trace_execution(role, task_type, {"prompt": prompt[:100]}) as trace_meta:
            if self.use_consensus:
                consensus = self.executor.consensus(prompt)
                task.consensus = consensus
                task.completed_at = datetime.now().isoformat()
                self._task_log.append(task)

                result = {
                    'role': role,
                    'task_type': task_type,
                    'mode': 'consensus',
                    'success': consensus['success'],
                    'response': consensus.get('combined_response', ''),
                    'sentiment': consensus.get('consensus_sentiment'),
                    'agreement': consensus.get('agreement'),
                    'tools_used': consensus.get('tools_used', []),
                    'timestamp': datetime.now().isoformat(),
                    'raw': consensus,
                }
                trace_meta.success = consensus['success']
                return result
            else:
                use_tool = tool or self.preferred_tool
                if use_tool:
                    result_obj = self.executor.run(use_tool, prompt, **run_kwargs)
                elif category:
                    # Use smart routing when category is provided
                    result_obj = self.executor.run_smart(prompt, category, **run_kwargs)
                else:
                    result_obj = self.executor.run_best(prompt)

                task.result = result_obj
                task.completed_at = datetime.now().isoformat()
                self._task_log.append(task)

                result = {
                    'role': role,
                    'task_type': task_type,
                    'mode': 'single' if use_tool else ('smart' if category else 'best'),
                    'success': result_obj.success,
                    'response': result_obj.response,
                    'tool_used': result_obj.tool,
                    'execution_time': result_obj.execution_time,
                    'error': result_obj.error,
                    'cached': result_obj.cached,
                    'output_mode': result_obj.output_mode,
                    'parsed_json': result_obj.parsed_json,
                    'timestamp': datetime.now().isoformat(),
                }
                trace_meta.success = result_obj.success
                trace_meta.tool = result_obj.tool
                return result

    # ------------------------------------------------------------------
    # Sub-Agent Roles
    # ------------------------------------------------------------------

    def research(self, query: str, tool: Optional[str] = None,
                 web_search: bool = False) -> Dict[str, Any]:
        """
        Researcher sub-agent — market research and information gathering.

        Args:
            query: Research question (e.g., "What is driving gold price today?")
            tool: Specific tool to use (default: auto → smart route to RESEARCH)
            web_search: Enable live web search via Codex --search
        """
        prompt = PROMPTS['market_research'].format(query=query)
        return self._dispatch('researcher', 'market_research', prompt, tool,
                              web_search=web_search,
                              category=TaskCategory.RESEARCH)

    def analyze(self, symbol: str = "XAUUSD", price: str = "current",
                timeframe: str = "H4", extra_context: str = "",
                tool: Optional[str] = None) -> Dict[str, Any]:
        """Analyst sub-agent — technical analysis (→ smart route to TA)."""
        prompt = PROMPTS['technical_analysis'].format(
            symbol=symbol, price=price,
            timeframe=timeframe, extra_context=extra_context,
        )
        return self._dispatch('analyst', 'technical_analysis', prompt, tool,
                              category=TaskCategory.TECHNICAL_ANALYSIS)

    def plan(self, symbol: str = "XAUUSD",
             balance: float = 10000, positions: str = "None",
             risk_per_trade: float = 0.01,
             market_condition: str = "unknown",
             performance_summary: str = "No data yet",
             max_loss: float = 500,
             tool: Optional[str] = None) -> Dict[str, Any]:
        """Strategist sub-agent — generate trading plan (→ smart route to STRATEGY)."""
        prompt = PROMPTS['trading_plan'].format(
            symbol=symbol, balance=balance, positions=positions,
            risk_per_trade=risk_per_trade,
            market_condition=market_condition,
            performance_summary=performance_summary,
            date=datetime.now().strftime("%Y-%m-%d"),
            max_loss=max_loss,
        )
        return self._dispatch('strategist', 'trading_plan', prompt, tool,
                              category=TaskCategory.STRATEGY)

    def review_positions(self, positions_detail: str = "No open positions",
                         balance: float = 10000, equity: float = 10000,
                         margin_level: float = 0, total_pnl: float = 0,
                         tool: Optional[str] = None) -> Dict[str, Any]:
        """Monitor sub-agent — review open positions."""
        prompt = PROMPTS['position_review'].format(
            positions_detail=positions_detail,
            balance=balance, equity=equity,
            margin_level=margin_level, total_pnl=total_pnl,
        )
        return self._dispatch('monitor', 'position_review', prompt, tool)

    def assess_risk(self, portfolio_summary: str = "",
                    recent_trades: str = "None",
                    win_rate: float = 0, profit_factor: float = 0,
                    max_drawdown: float = 0,
                    tool: Optional[str] = None) -> Dict[str, Any]:
        """Risk sub-agent — risk assessment (→ smart route to RISK_ASSESSMENT)."""
        prompt = PROMPTS['risk_assessment'].format(
            portfolio_summary=portfolio_summary,
            recent_trades=recent_trades,
            win_rate=f"{win_rate:.1%}",
            profit_factor=f"{profit_factor:.2f}",
            max_drawdown=f"{max_drawdown:.1%}",
        )
        return self._dispatch('monitor', 'risk_assessment', prompt, tool,
                              category=TaskCategory.RISK_ASSESSMENT)

    def news_digest(self, topics: str = "XAUUSD gold price drivers today, Fed policy, geopolitics",
                    tool: Optional[str] = None,
                    web_search: bool = True) -> Dict[str, Any]:
        """Researcher sub-agent — news digest (→ web search by default)."""
        prompt = PROMPTS['news_digest'].format(topics=topics)
        return self._dispatch('researcher', 'news_digest', prompt, tool,
                              web_search=web_search,
                              category=TaskCategory.RESEARCH)

    def ask(self, task: str, tool: Optional[str] = None) -> Dict[str, Any]:
        """General sub-agent — free-form task."""
        prompt = PROMPTS['general'].format(task=task)
        return self._dispatch('general', 'general', prompt, tool,
                              category=TaskCategory.GENERAL)

    def daily_summary(self, price: str = "N/A", change: str = "N/A",
                      positions_count: int = 0, daily_pnl: float = 0,
                      recent_activity: str = "No trades today",
                      research_consensus: str = "No research yet",
                      tool: Optional[str] = None) -> Dict[str, Any]:
        """Daily summary report."""
        prompt = PROMPTS['daily_summary'].format(
            date=datetime.now().strftime("%Y-%m-%d"),
            price=price, change=change,
            positions_count=positions_count,
            daily_pnl=daily_pnl,
            recent_activity=recent_activity,
            research_consensus=research_consensus,
        )
        return self._dispatch('strategist', 'daily_summary', prompt, tool,
                              category=TaskCategory.STRATEGY)

    # ------------------------------------------------------------------
    # Enhanced Sub-Agent Methods (use real CLI features)
    # ------------------------------------------------------------------

    def get_trade_signal(self, context: str = "",
                         symbol: str = "XAUUSD",
                         tool: Optional[str] = None) -> Dict[str, Any]:
        """
        Get structured trade signal via JSON schema validation.

        Uses Claude --json-schema for native validation when available.
        Returns parsed_json with: direction, confidence, entry, SL, TP, rationale.
        """
        result = self.executor.get_trade_signal(
            f"{context}\nProvide a precise trade signal for {symbol}.",
            symbol=symbol, tool=tool,
        )
        return {
            'role': 'strategist',
            'task_type': 'trade_signal',
            'mode': 'structured',
            'success': result.success,
            'response': result.response,
            'tool_used': result.tool,
            'execution_time': result.execution_time,
            'signal': result.parsed_json,
            'timestamp': datetime.now().isoformat(),
        }

    def get_risk_report(self, portfolio_info: str = "",
                        tool: Optional[str] = None) -> Dict[str, Any]:
        """
        Get structured risk assessment via JSON schema validation.

        Returns parsed_json with: risk_score, status, warnings, recommendations.
        """
        result = self.executor.get_risk_assessment(portfolio_info, tool=tool)
        return {
            'role': 'monitor',
            'task_type': 'risk_report',
            'mode': 'structured',
            'success': result.success,
            'response': result.response,
            'tool_used': result.tool,
            'execution_time': result.execution_time,
            'risk': result.parsed_json,
            'timestamp': datetime.now().isoformat(),
        }

    def research_with_web(self, query: str,
                          tool: Optional[str] = None) -> Dict[str, Any]:
        """
        Research using live web search (Codex --search).

        Best for real-time market news and price data.
        """
        result = self.executor.web_search(query, tool=tool)
        return {
            'role': 'researcher',
            'task_type': 'web_research',
            'mode': 'web_search',
            'success': result.success,
            'response': result.response,
            'tool_used': result.tool,
            'execution_time': result.execution_time,
            'parsed_json': result.parsed_json,
            'timestamp': datetime.now().isoformat(),
        }

    def full_pipeline(self, symbol: str = "XAUUSD") -> Dict[str, Any]:
        """
        Run the full analysis pipeline from AgentExecutor:
        1. Web search for news  (Codex --search)
        2. Sentiment analysis   (Claude --json-schema)
        3. Trade signal          (Claude --json-schema)
        4. Risk assessment       (Claude --json-schema)

        Returns all parsed structured data.
        """
        logger.info(f"[SubAgent] Running full pipeline for {symbol}...")
        pipeline = self.executor.full_analysis_pipeline(symbol)
        return {
            'role': 'pipeline',
            'task_type': 'full_analysis',
            'mode': 'pipeline',
            'success': pipeline.get('success', False),
            'symbol': symbol,
            'parsed': pipeline.get('parsed', {}),
            'steps': {k: v.get('success', False) for k, v in pipeline.get('steps', {}).items()},
            'timestamp': datetime.now().isoformat(),
            'raw': pipeline,
        }

    # ------------------------------------------------------------------
    # Composite workflows
    # ------------------------------------------------------------------

    def daily_routine(self, symbol: str = "XAUUSD",
                      tool: Optional[str] = None) -> Dict[str, Any]:
        """
        🔄 Full daily routine — runs multiple sub-agents sequentially:
        1. News digest
        2. Technical analysis
        3. Trading plan generation
        4. Position review (if positions open)
        5. Risk assessment
        6. Daily summary compilation
        
        Returns complete daily report.
        """
        logger.info("[SubAgent] Starting daily routine...")

        if self.use_langgraph and self.graph.is_available():
            logger.info("[SubAgent] Running daily routine with LangGraph")
            return self.graph.run_daily_routine(symbol=symbol, tool=tool)

        report: Dict[str, Any] = {
            'date': datetime.now().strftime("%Y-%m-%d"),
            'symbol': symbol,
            'steps': {},
            'started_at': datetime.now().isoformat(),
        }

        # Step 1: News Digest
        logger.info("[SubAgent] Step 1/5: News Digest")
        news = self.news_digest(tool=tool)
        report['steps']['news_digest'] = news

        # Step 2: Technical Analysis
        logger.info("[SubAgent] Step 2/5: Technical Analysis")
        analysis = self.analyze(symbol=symbol, tool=tool)
        report['steps']['technical_analysis'] = analysis

        # Step 3: Trading Plan
        logger.info("[SubAgent] Step 3/5: Trading Plan")
        plan = self.plan(
            symbol=symbol,
            market_condition=news.get('sentiment', 'unknown'),
            tool=tool,
        )
        report['steps']['trading_plan'] = plan

        # Step 4: Risk Assessment
        logger.info("[SubAgent] Step 4/5: Risk Assessment")
        risk = self.assess_risk(tool=tool)
        report['steps']['risk_assessment'] = risk

        # Step 5: Compile Summary
        logger.info("[SubAgent] Step 5/5: Daily Summary")
        news_snippet = (news.get('response', '')[:200] + "...")
        summary = self.daily_summary(
            research_consensus=news_snippet,
            tool=tool,
        )
        report['steps']['daily_summary'] = summary

        report['completed_at'] = datetime.now().isoformat()
        report['success'] = all(
            s.get('success', False) for s in report['steps'].values()
        )

        logger.info("[SubAgent] Daily routine complete")
        return report

    def quick_outlook(self, symbol: str = "XAUUSD",
                      tool: Optional[str] = None) -> Dict[str, Any]:
        """Quick outlook — fast consensus from all agents on market direction."""
        query = (
            f"What is the current outlook for {symbol} (Gold)? "
            f"Give a one-paragraph summary with direction (BUY/SELL/HOLD), "
            f"confidence (0-100%), and top 3 reasons."
        )
        if self.use_consensus or not tool:
            return self.executor.consensus(query)
        return self._dispatch('researcher', 'quick_outlook', query, tool)

    # ------------------------------------------------------------------
    # Task management
    # ------------------------------------------------------------------

    def get_task_log(self) -> List[Dict]:
        """Get log of all tasks dispatched in this session."""
        return [
            {
                'role': t.role,
                'task_type': t.task_type,
                'tool': t.tool_preference or 'auto',
                'started_at': t.started_at,
                'completed_at': t.completed_at,
                'success': (t.result.success if t.result else
                            t.consensus.get('success') if t.consensus else None),
            }
            for t in self._task_log
        ]

    def get_available_roles(self) -> List[Dict[str, str]]:
        """List available sub-agent roles."""
        return [
            {'role': 'researcher', 'description': 'Market research & news gathering',
             'commands': ['research', 'news_digest']},
            {'role': 'analyst', 'description': 'Technical analysis & pattern recognition',
             'commands': ['analyze']},
            {'role': 'strategist', 'description': 'Trading plan & strategy generation',
             'commands': ['plan', 'daily_summary']},
            {'role': 'monitor', 'description': 'Position review & risk assessment',
             'commands': ['review_positions', 'assess_risk']},
            {'role': 'general', 'description': 'Free-form AI assistant',
             'commands': ['ask']},
        ]
