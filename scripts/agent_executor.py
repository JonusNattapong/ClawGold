"""
Agent Executor Module — Enhanced Automation
============================================
Unified interface for AI CLI tools with **real CLI flag support** discovered
from actual ``--help`` output (2025-07).

Supported tools:
  • OpenCode 1.2.15 — ``run --format json``, ``--model``, ``--file``, agents, MCP, GitHub
  • Gemini  0.30.1  — ``-p`` headless, ``--output-format json``, skills, extensions, sandbox
  • Codex   0.104.0 — ``exec --json``, ``review``, ``--search`` (web!), full-auto, sandbox
  • Claude  2.1.47  — ``-p``, ``--output-format json``, ``--json-schema`` (native!), budget ctrl

Features:
  - Smart routing: auto-picks the best tool per TaskCategory
  - Structured output: native JSON schema validation via Claude
  - Web search: live internet queries via Codex ``--search``
  - Code review: ``codex review --uncommitted``
  - Full-auto mode: Gemini ``--yolo`` / Codex ``--full-auto``
  - Model selection: ``--model`` on every tool
  - Caching, metrics, history DB, LiteLLM fallback

Usage::

    executor = AgentExecutor()
    result   = executor.run("claude", "Analyze XAUUSD", output_mode="json")
    signal   = executor.get_trade_signal("XAUUSD H4 analysis")
    news     = executor.web_search("gold price drivers today")
    review   = executor.code_review(uncommitted=True)
    best     = executor.run_smart("Market outlook", TaskCategory.RESEARCH)
"""

import json
import re
import time
import hashlib
import sqlite3
import subprocess
import shutil
from contextlib import contextmanager
from typing import List, Dict, Optional, Any, Tuple, Callable
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from enum import Enum

from logger import get_logger
from llm_client import get_llm_client
from rich_logger import get_rich_logger

logger = get_logger(__name__)
rich_logger = get_rich_logger()


class AgentTool(Enum):
    """Supported AI CLI tools — based on real installed CLIs."""
    OPENCODE = "opencode"     # opencode 1.2.15 — run --format json, agent, mcp, github
    GEMINI = "gemini"         # gemini 0.30.1  — -p headless, --output-format json, skills, extensions
    CODEX = "codex"           # codex 0.104.0  — exec --json, review, --search, sandbox
    CLAUDE = "claude"         # claude 2.1.47  — -p print, --output-format json, --json-schema


class TaskCategory(Enum):
    """Task categories for smart routing."""
    RESEARCH = "research"              # Market research, news gathering
    TECHNICAL_ANALYSIS = "technical"   # Chart / TA / pattern analysis
    STRATEGY = "strategy"              # Trade plan generation
    RISK_ASSESSMENT = "risk"           # Risk analysis
    CODE_REVIEW = "code_review"        # Review trading code / strategies
    WEB_SEARCH = "web_search"          # Live web search for real-time data
    STRUCTURED_OUTPUT = "structured"   # When we need validated JSON output
    GENERAL = "general"                # Generic question / task
    MULTI_STEP = "multi_step"          # Complex multi-step reasoning
    FAST_ANSWER = "fast"               # Quick simple answer


# ─────────────────────────────────────────────────────────────────────────────
# CLI invocation patterns — ALL flags from real `--help` output (2026-03-04)
# ─────────────────────────────────────────────────────────────────────────────

TOOL_COMMANDS = {
    # ── OpenCode 1.2.15 ──────────────────────────────────────────────────
    AgentTool.OPENCODE: {
        'check': ['opencode', '--version'],
        'binary': 'opencode',
        # opencode run [message..] --format json --model X --file F --agent A
        'run': lambda prompt, **kw: _build_opencode_cmd(prompt, **kw),
        'server': lambda port: ['opencode', 'serve', '--port', str(port)],
        'stream': True,
        'mcp': True,
        'json_output': True,        # --format json
        'model_select': True,       # --model provider/model
        'file_attach': True,        # --file path
        'agents': True,             # opencode agent create/list
        'resume': True,             # --continue / --session
        'stats': True,              # opencode stats
        'github': True,             # opencode github / opencode pr
        'install': 'npm install -g opencode-ai',
        'timeout': 180,
        'strengths': [
            'code analysis', 'multi-step reasoning', 'file editing',
            'agent management', 'session continuity', 'github integration',
        ],
        'best_for': [TaskCategory.MULTI_STEP, TaskCategory.CODE_REVIEW,
                     TaskCategory.STRATEGY, TaskCategory.GENERAL],
        'priority': 30,
    },
    # ── Gemini CLI 0.30.1 ────────────────────────────────────────────────
    AgentTool.GEMINI: {
        'check': ['gemini', '--version'],
        'binary': 'gemini',
        # gemini -p "<prompt>" --output-format json --model X --sandbox --yolo
        'run': lambda prompt, **kw: _build_gemini_cmd(prompt, **kw),
        'stream': True,
        'mcp': True,
        'json_output': True,        # --output-format json | stream-json
        'model_select': True,       # --model
        'sandbox': True,            # --sandbox
        'full_auto': True,          # --yolo
        'skills': True,             # gemini skills list/install/enable
        'extensions': True,         # gemini extensions list/install
        'resume': True,             # --resume
        'install': 'npm install -g @google/gemini-cli',
        'timeout': 180,
        'strengths': [
            'web knowledge', 'real-time reasoning', 'long context',
            'multilingual', 'extension ecosystem', 'skill framework',
            'sandbox execution', 'yolo auto-approve',
        ],
        'best_for': [TaskCategory.RESEARCH, TaskCategory.WEB_SEARCH,
                     TaskCategory.GENERAL, TaskCategory.FAST_ANSWER],
        'priority': 20,
    },
    # ── Codex CLI 0.104.0 ────────────────────────────────────────────────
    AgentTool.CODEX: {
        'check': ['codex', '--version'],
        'binary': 'codex',
        # codex exec "<prompt>" --json --search --full-auto --model X --sandbox S
        'run': lambda prompt, **kw: _build_codex_cmd(prompt, **kw),
        # codex review [--uncommitted|--base branch]
        'review': lambda **kw: _build_codex_review_cmd(**kw),
        'stream': True,
        'mcp': True,
        'json_output': True,        # --json (JSONL events)
        'model_select': True,       # --model
        'sandbox': True,            # --sandbox read-only|workspace-write|danger-full-access
        'web_search': True,         # --search (live web search!)
        'code_review': True,        # codex review --uncommitted
        'file_attach': True,        # --image for images
        'full_auto': True,          # --full-auto
        'resume': True,             # codex exec resume
        'install': 'npm install -g @openai/codex',
        'timeout': 240,
        'strengths': [
            'code generation', 'code review', 'web search',
            'sandbox execution', 'shell commands', 'full-auto mode',
            'structured JSONL output', 'image input',
        ],
        'best_for': [TaskCategory.CODE_REVIEW, TaskCategory.WEB_SEARCH,
                     TaskCategory.STRUCTURED_OUTPUT, TaskCategory.TECHNICAL_ANALYSIS],
        'priority': 25,
    },
    # ── Claude Code 2.1.47 ───────────────────────────────────────────────
    AgentTool.CLAUDE: {
        'check': ['claude', '--version'],
        'binary': 'claude',
        # claude -p "<prompt>" --output-format json --model X --system-prompt S
        #   --json-schema '{...}' --max-budget-usd N --allowed-tools "Read"
        'run': lambda prompt, **kw: _build_claude_cmd(prompt, **kw),
        'stream': True,
        'mcp': True,
        'json_output': True,        # --output-format json | stream-json
        'model_select': True,       # --model
        'system_prompt': True,      # --system-prompt  (NATIVE!)
        'json_schema': True,        # --json-schema    (NATIVE!)
        'budget_control': True,     # --max-budget-usd
        'tool_restrict': True,      # --allowed-tools / --disallowed-tools
        'resume': True,             # --resume / --continue
        'install': 'npm install -g @anthropic-ai/claude-code',
        'timeout': 180,
        'strengths': [
            'structured JSON validation', 'system prompt injection',
            'budget control', 'tool restriction', 'agentic workflow',
            'multi-step file operations', 'precise instruction following',
        ],
        'best_for': [TaskCategory.STRUCTURED_OUTPUT, TaskCategory.STRATEGY,
                     TaskCategory.RISK_ASSESSMENT, TaskCategory.MULTI_STEP],
        'priority': 25,
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# CLI Command Builders (real flags from --help)
# ─────────────────────────────────────────────────────────────────────────────

def _build_opencode_cmd(prompt: str, *, output_mode: str = "text",
                        model: str = "", files: list = None,
                        **_extra) -> List[str]:
    """opencode run [message..] --format json --model X --file F"""
    cmd = ['opencode', 'run']
    if output_mode in ('json', 'stream'):
        cmd += ['--format', 'json']
    if model:
        cmd += ['--model', model]
    for f in (files or []):
        cmd += ['--file', f]
    cmd.append(prompt)
    return cmd


def _build_gemini_cmd(prompt: str, *, output_mode: str = "text",
                      model: str = "", sandbox: bool = False,
                      full_auto: bool = False, **_extra) -> List[str]:
    """gemini -p "<prompt>" --output-format json --model X --sandbox --yolo"""
    cmd = ['gemini']
    if output_mode == 'json':
        cmd += ['--output-format', 'json']
    elif output_mode == 'stream':
        cmd += ['--output-format', 'stream-json']
    if model:
        cmd += ['--model', model]
    if sandbox:
        cmd += ['--sandbox']
    if full_auto:
        cmd += ['--yolo']
    cmd += ['-p', prompt]
    return cmd


def _build_codex_cmd(prompt: str, *, output_mode: str = "text",
                     model: str = "", web_search: bool = False,
                     full_auto: bool = False, sandbox: bool = False,
                     cwd: str = "", **_extra) -> List[str]:
    """codex exec "<prompt>" --json --search --full-auto --model X"""
    cmd = ['codex', 'exec']
    if output_mode in ('json', 'stream'):
        cmd += ['--json']
    if model:
        cmd += ['--model', model]
    if web_search:
        cmd += ['--search']
    if full_auto:
        cmd += ['--full-auto']
    elif sandbox:
        cmd += ['--sandbox', 'read-only']
    if cwd:
        cmd += ['--cd', cwd]
    cmd.append(prompt)
    return cmd


def _build_codex_review_cmd(*, uncommitted: bool = True,
                            base: str = "", custom_prompt: str = "",
                            **_extra) -> List[str]:
    """codex review [--uncommitted|--base branch] [prompt]"""
    cmd = ['codex', 'review']
    if uncommitted:
        cmd.append('--uncommitted')
    if base:
        cmd += ['--base', base]
    if custom_prompt:
        cmd.append(custom_prompt)
    return cmd


def _build_claude_cmd(prompt: str, *, output_mode: str = "text",
                      model: str = "", system_prompt: str = "",
                      json_schema: dict = None, sandbox: bool = False,
                      max_budget: float = 0, allowed_tools: list = None,
                      **_extra) -> List[str]:
    """claude -p "<prompt>" --output-format json --model X --system-prompt S --json-schema '{...}'"""
    cmd = ['claude', '-p']
    if output_mode == 'json':
        cmd += ['--output-format', 'json']
    elif output_mode == 'stream':
        cmd += ['--output-format', 'stream-json']
    if model:
        cmd += ['--model', model]
    if system_prompt:
        cmd += ['--system-prompt', system_prompt]
    if json_schema:
        cmd += ['--json-schema', json.dumps(json_schema)]
    if max_budget > 0:
        cmd += ['--max-budget-usd', str(max_budget)]
    if allowed_tools:
        cmd += ['--allowed-tools', ','.join(allowed_tools)]
    if sandbox:
        cmd += ['--allowed-tools', 'Read']
    # One-shot: don't persist session
    cmd += ['--no-session-persistence']
    cmd.append(prompt)
    return cmd


# ─────────────────────────────────────────────────────────────────────────────
# JSON Schema Templates — for validated structured output (claude --json-schema)
# ─────────────────────────────────────────────────────────────────────────────

TRADE_SIGNAL_SCHEMA = {
    "type": "object",
    "properties": {
        "direction": {"type": "string", "enum": ["BUY", "SELL", "HOLD"]},
        "confidence": {"type": "number", "minimum": 0, "maximum": 100},
        "entry_price": {"type": "number"},
        "stop_loss": {"type": "number"},
        "take_profit": {"type": "number"},
        "risk_reward": {"type": "number"},
        "rationale": {"type": "string"},
        "timeframe": {"type": "string"},
    },
    "required": ["direction", "confidence", "rationale"],
}

SENTIMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "sentiment": {"type": "string", "enum": ["BULLISH", "BEARISH", "NEUTRAL"]},
        "confidence": {"type": "number", "minimum": 0, "maximum": 100},
        "key_drivers": {"type": "array", "items": {"type": "string"}},
        "risk_factors": {"type": "array", "items": {"type": "string"}},
        "price_impact": {"type": "string"},
    },
    "required": ["sentiment", "confidence", "key_drivers"],
}

RISK_ASSESSMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "risk_score": {"type": "number", "minimum": 1, "maximum": 10},
        "status": {"type": "string", "enum": ["HEALTHY", "CAUTION", "DANGER"]},
        "warnings": {"type": "array", "items": {"type": "string"}},
        "recommended_position_size": {"type": "number"},
        "max_daily_risk_pct": {"type": "number"},
        "recommendations": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["risk_score", "status", "warnings"],
}


@dataclass
class AgentResult:
    """Result from an AI agent execution."""
    tool: str
    task: str
    response: str
    success: bool
    execution_time: float
    error: Optional[str] = None
    cached: bool = False
    output_mode: str = "text"           # text | json | stream
    parsed_json: Optional[Any] = None   # Parsed JSON when output_mode=json
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict:
        d = asdict(self)
        return d

    def get_json(self) -> Optional[Any]:
        """Return parsed JSON response. Tries to parse if not yet parsed."""
        if self.parsed_json is not None:
            return self.parsed_json
        if self.response:
            try:
                self.parsed_json = json.loads(self.response)
                return self.parsed_json
            except (json.JSONDecodeError, TypeError):
                return _extract_json_from_text(self.response)
        return None


def _extract_json_from_text(text: str) -> Optional[Any]:
    """Extract a JSON object from text that may contain markdown fences etc."""
    # Try ```json ... ``` blocks
    m = re.search(r'```(?:json)?\s*\n(.*?)\n```', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except (json.JSONDecodeError, TypeError):
            pass
    # Try first top-level { ... }
    for i, ch in enumerate(text):
        if ch == '{':
            depth = 0
            for j in range(i, len(text)):
                if text[j] == '{':
                    depth += 1
                elif text[j] == '}':
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[i:j+1])
                        except (json.JSONDecodeError, TypeError):
                            break
            break
    return None


@dataclass
class AgentCapability:
    """Describes what an agent tool can do (from real CLI --help)."""
    tool: AgentTool
    available: bool
    version: Optional[str] = None
    path: Optional[str] = None
    strengths: List[str] = field(default_factory=list)
    best_for: List[TaskCategory] = field(default_factory=list)
    avg_response_time: float = 0.0
    success_rate: float = 0.0
    total_calls: int = 0
    priority: int = 50                 # Lower = preferred when tied
    # Capabilities (all from real --help flags)
    supports_streaming: bool = False
    supports_mcp: bool = False
    supports_sandbox: bool = False
    supports_extensions: bool = False
    supports_json_output: bool = False  # --output-format json / --json
    supports_web_search: bool = False   # codex --search
    supports_code_review: bool = False  # codex review
    supports_json_schema: bool = False  # claude --json-schema
    supports_system_prompt: bool = False # claude --system-prompt
    supports_model_select: bool = False  # --model on all
    supports_full_auto: bool = False     # gemini --yolo / codex --full-auto
    supports_file_attach: bool = False   # opencode --file / codex --image
    supports_skills: bool = False        # gemini skills
    supports_agents: bool = False        # opencode agent
    supports_resume: bool = False        # --resume / --continue
    supports_budget: bool = False        # claude --max-budget-usd
    # Detected at runtime
    mcp_servers: List[str] = field(default_factory=list)
    detected_skills: List[str] = field(default_factory=list)
    detected_extensions: List[str] = field(default_factory=list)
    last_checked: str = field(default_factory=lambda: datetime.now().isoformat())


class AgentExecutor:
    """
    Unified executor for AI CLI agents.
    
    Manages tool discovery, execution, caching, metrics, and fallback logic.
    Each AI CLI tool is treated as an autonomous agent that can handle
    natural-language tasks without any model training.
    """

    def __init__(self, cache_dir: str = "data/agent_cache",
                 cache_ttl_hours: int = 4,
                 db_path: str = "data/agent_history.db", **kwargs):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_ttl = cache_ttl_hours
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Tracing initialization
        try:
            from scripts.langfuse_tracer import get_tracer
            config = kwargs.get('config', {})
            enabled = config.get("agent", {}).get("langfuse", {}).get("enabled", False)
            self.tracer = get_tracer(enabled=enabled)
        except Exception:
            self.tracer = None

        if not self.tracer or not hasattr(self.tracer, 'trace_agent_run'):
            class MockTracer:
                def trace_agent_run(self, *args, **kwargs):
                    class MockMeta:
                        def __init__(self): self.success = True
                        def __enter__(self): return self
                        def __exit__(self, *args, **kwargs): pass
                    return MockMeta()
            self.tracer = MockTracer()

        # Discover available tools
        self._available_tools: Dict[AgentTool, AgentCapability] = {}
        self._discover_tools()

        # Metrics
        self._metrics: Dict[str, Dict[str, Any]] = {}
        for tool in AgentTool:
            self._metrics[tool.value] = {
                'calls': 0, 'successes': 0, 'failures': 0,
                'total_time': 0.0, 'avg_time': 0.0,
            }

        # Init history DB
        self._init_db()

    @contextmanager
    def _connect(self):
        """Context manager that properly closes the SQLite connection."""
        conn = sqlite3.connect(str(self.db_path))
        try:
            yield conn
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Tool Discovery
    # ------------------------------------------------------------------

    def _discover_tools(self):
        """
        Discover available AI CLI tools via shutil.which() + actual CLI invocation.
        Detects installed tools and their capabilities.
        """
        for tool in AgentTool:
            check_cmd = TOOL_COMMANDS[tool]['check']
            cli_name = check_cmd[0]
            
            # Try to locate the CLI tool
            cli_path = shutil.which(cli_name)
            
            if not cli_path:
                # Tool not found
                cap = AgentCapability(
                    tool=tool,
                    available=False,
                    path=None,
                    version=None,
                )
                logger.debug(f"Tool not found in PATH: {cli_name}")
            else:
                # Tool found — try to get version
                version = "unknown"
                try:
                    version_output = subprocess.run(
                        check_cmd,
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if version_output.returncode == 0:
                        version = version_output.stdout.strip()
                        if not version:
                            version = "installed"
                except Exception as e:
                    version = "detected"  # At least we found it
                
                # Build capabilities based on real TOOL_COMMANDS config
                tc = TOOL_COMMANDS[tool]
                best_for = tc.get('best_for', [])
                cap = AgentCapability(
                    tool=tool,
                    available=True,
                    path=cli_path,
                    version=version,
                    strengths=tc.get('strengths', []),
                    best_for=best_for,
                    priority=tc.get('priority', 50),
                    supports_streaming=tc.get('stream', False),
                    supports_mcp=tc.get('mcp', False),
                    supports_sandbox=tc.get('sandbox', False),
                    supports_extensions=tc.get('extensions', False),
                    supports_json_output=tc.get('json_output', False),
                    supports_web_search=tc.get('web_search', False),
                    supports_code_review=tc.get('code_review', False),
                    supports_json_schema=tc.get('json_schema', False),
                    supports_system_prompt=tc.get('system_prompt', False),
                    supports_model_select=tc.get('model_select', False),
                    supports_full_auto=tc.get('full_auto', False),
                    supports_file_attach=tc.get('file_attach', False),
                    supports_skills=tc.get('skills', False),
                    supports_agents=tc.get('agents', False),
                    supports_resume=tc.get('resume', False),
                    supports_budget=tc.get('budget_control', False),
                )
                flags = []
                if cap.supports_json_output: flags.append("json")
                if cap.supports_web_search:  flags.append("web-search")
                if cap.supports_json_schema: flags.append("json-schema")
                if cap.supports_full_auto:   flags.append("full-auto")
                if cap.supports_mcp:         flags.append("mcp")
                logger.info(f"Found {cli_name} {version} [{', '.join(flags)}]")
            
            self._available_tools[tool] = cap

        # Report available tools count
        available_count = sum(1 for c in self._available_tools.values() if c.available)
        available_names = [c.tool.value for c in self._available_tools.values() if c.available]
        if available_count > 0:
            logger.info(f"Found {available_count} AI CLI tools: {', '.join(available_names)}")
        else:
            logger.warning("No AI CLI tools detected. Falling back to LiteLLM.")

    @staticmethod
    def _tool_strengths(tool: AgentTool) -> List[str]:
        """Return known strengths for each tool from TOOL_COMMANDS config."""
        tool_config = TOOL_COMMANDS.get(tool, {})
        return tool_config.get('strengths', [])

    def get_available_tools(self) -> List[AgentCapability]:
        """Return list of available AI tools."""
        return [c for c in self._available_tools.values() if c.available]

    def get_all_tools(self) -> List[AgentCapability]:
        """Return all tools with availability status."""
        caps = list(self._available_tools.values())
        # Attach runtime metrics
        for cap in caps:
            m = self._metrics[cap.tool.value]
            cap.total_calls = m['calls']
            cap.avg_response_time = m['avg_time']
            cap.success_rate = (
                m['successes'] / m['calls'] * 100 if m['calls'] > 0 else 0
            )
        return caps

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def run(self, tool: str, task: str, *,
            use_cache: bool = True,
            timeout: Optional[int] = None,
            system_prompt: str = "",
            use_cli: bool = True,
            output_mode: str = "text",
            model: str = "",
            json_schema: Optional[dict] = None,
            files: Optional[List[str]] = None,
            web_search: bool = False,
            full_auto: bool = False,
            sandbox: bool = False,
            max_budget: float = 0,
            allowed_tools: Optional[List[str]] = None) -> AgentResult:
        """
        Run a task on a specific AI agent tool.

        Args:
            tool: Tool name (opencode, gemini, codex, claude)
            task: Natural-language task / prompt
            use_cache: Whether to check cache first
            timeout: Override default timeout (seconds)
            system_prompt: Optional system instruction prepended to task
            use_cli: If True, use actual CLI; if False, use LiteLLM fallback
            output_mode: "text" | "json" | "stream" — request structured output
            model: Override model (e.g. "o3", "gemini-2.5-pro")
            json_schema: JSON schema dict for claude --json-schema
            files: File paths to attach (opencode --file, codex --image)
            web_search: Enable live web search (codex --search)
            full_auto: Enable auto-approve (gemini --yolo, codex --full-auto)
            sandbox: Run in sandbox mode
            max_budget: Budget cap in USD (claude --max-budget-usd)
            allowed_tools: Restrict tools (claude --allowed-tools)

        Returns:
            AgentResult with optional parsed_json when output_mode="json"
        """
        agent_tool = self._resolve_tool(tool)
        if agent_tool is None:
            return AgentResult(
                tool=tool, task=task, response="",
                success=False, execution_time=0,
                error=f"Unknown tool: {tool}. Available: {[t.value for t in AgentTool]}",
            )

        cap = self._available_tools[agent_tool]
        
        # Check cache
        if use_cache:
            cached = self._get_cache(tool, task)
            if cached:
                logger.info(f"[AgentExecutor] Cache hit: {tool} — {task[:50]}…")
                return cached

        # Build prompt
        full_prompt = self._build_prompt(task, system_prompt)
        exec_timeout = timeout or TOOL_COMMANDS[agent_tool]['timeout']
        start = time.time()

        # Try actual CLI first if available and requested
        if use_cli and cap.available and cap.path:
            cli_kwargs = dict(
                output_mode=output_mode, model=model,
                json_schema=json_schema, files=files or [],
                web_search=web_search, full_auto=full_auto,
                sandbox=sandbox, max_budget=max_budget,
                allowed_tools=allowed_tools or [],
                system_prompt=system_prompt if cap.supports_system_prompt else "",
            )
            result = self._run_cli(agent_tool, full_prompt, exec_timeout, **cli_kwargs)
            if result.success:
                elapsed = time.time() - start
                result.execution_time = elapsed
                result.output_mode = output_mode
                # Auto-parse JSON when requested
                if output_mode == "json":
                    result.get_json()
                self._update_metrics(tool, True, elapsed)
                self._set_cache(tool, task, result)
                self._record_history(result)
                self.tracer.trace_agent_run(
                    tool, full_prompt, result.response, elapsed, success=True
                )
                rich_logger.success(f"[OK] {tool}: {task[:40]}... ({elapsed:.1f}s)")
                return result
            else:
                rich_logger.warning(f"[{tool}] CLI failed: {result.error}, trying LiteLLM fallback...")
        elif not cap.available:
            # Tool not installed — skip LiteLLM, return clear error
            return AgentResult(
                tool=tool, task=task, response="",
                success=False, execution_time=0,
                error=f"{tool} not installed (not found in PATH).",
            )

        # Fallback to LiteLLM
        return self._run_litellm_fallback(agent_tool, full_prompt, task, exec_timeout, start)

    def _run_cli(self, tool: AgentTool, prompt: str, timeout: int,
                 **cli_kwargs) -> AgentResult:
        """Execute CLI tool using real flags from TOOL_COMMANDS builders."""
        tool_config = TOOL_COMMANDS[tool]

        try:
            # Use the builder lambda which knows all real CLI flags
            run_fn = tool_config['run']
            cmd = run_fn(prompt, **cli_kwargs)

            logger.debug(f"[CLI] Executing: {' '.join(cmd)}")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=None,
            )

            if result.returncode == 0:
                response_text = result.stdout.strip()
                ar = AgentResult(
                    tool=tool.value,
                    task=prompt[:100],
                    response=response_text,
                    success=True,
                    execution_time=0,
                    output_mode=cli_kwargs.get('output_mode', 'text'),
                )
                # Auto-parse JSON output
                if cli_kwargs.get('output_mode') == 'json':
                    ar.get_json()
                return ar
            else:
                error_msg = result.stderr.strip() or f"Exit code {result.returncode}"
                return AgentResult(
                    tool=tool.value,
                    task=prompt[:100],
                    response="",
                    success=False,
                    execution_time=0,
                    error=error_msg,
                )
        
        except subprocess.TimeoutExpired:
            return AgentResult(
                tool=tool.value,
                task=prompt[:100],
                response="",
                success=False,
                execution_time=timeout,
                error=f"CLI timeout after {timeout}s",
            )
        except FileNotFoundError:
            return AgentResult(
                tool=tool.value,
                task=prompt[:100],
                response="",
                success=False,
                execution_time=0,
                error=f"CLI tool not found: {tool.value}",
            )
        except Exception as e:
            return AgentResult(
                tool=tool.value,
                task=prompt[:100],
                response="",
                success=False,
                execution_time=0,
                error=f"CLI execution error: {str(e)}",
            )

    def _run_litellm_fallback(self, tool: AgentTool, prompt: str, task: str,
                              timeout: int, start_time: float) -> AgentResult:
        """Fallback to LiteLLM when CLI is not available."""
        try:
            client = get_llm_client()
            llm_response = client.call(
                provider=tool.value,
                prompt=prompt,
                timeout=timeout
            )
            elapsed = time.time() - start_time

            if llm_response.success:
                result = AgentResult(
                    tool=tool.value, task=task, response=llm_response.content,
                    success=True, execution_time=elapsed,
                )
                self._update_metrics(tool.value, True, elapsed)
                self._record_history(result)
                self.tracer.trace_agent_run(
                    tool.value, prompt, llm_response.content, elapsed, success=True
                )
                rich_logger.info(f"[OK] {tool.value} (LiteLLM fallback): {task[:40]}... ({elapsed:.1f}s)")
                return result
            else:
                error_msg = llm_response.error or "Unknown error"
                result = AgentResult(
                    tool=tool.value, task=task, response="",
                    success=False, execution_time=elapsed, error=error_msg,
                )
                self._update_metrics(tool.value, False, elapsed)
                self._record_history(result)
                return result
        
        except Exception as e:
            elapsed = time.time() - start_time
            result = AgentResult(
                tool=tool.value, task=task, response="",
                success=False, execution_time=elapsed, error=str(e),
            )
            self._update_metrics(tool.value, False, elapsed)
            self._record_history(result)
            return result

    def run_best(self, task: str, *,
                 use_cache: bool = True,
                 system_prompt: str = "") -> AgentResult:
        """
        Run task on the best available tool (highest success rate first).
        Falls back to next best on failure.
        """
        ranked = self._rank_tools()
        if not ranked:
            return AgentResult(
                tool="none", task=task, response="",
                success=False, execution_time=0,
                error="No AI CLI tools available on this system.",
            )

        for tool_enum in ranked:
            result = self.run(
                tool_enum.value, task,
                use_cache=use_cache, system_prompt=system_prompt,
            )
            if result.success:
                return result
            rich_logger.warning(f"[AgentExecutor] {tool_enum.value} failed, trying next…")

        return result  # Return last failure

    def run_parallel(self, task: str, *,
                     tools: Optional[List[str]] = None,
                     use_cache: bool = True,
                     system_prompt: str = "") -> List[AgentResult]:
        """
        Run task on multiple tools in parallel.

        Args:
            task: Natural-language task
            tools: List of tool names (default: all available)
            system_prompt: Optional system instruction
        """
        if tools:
            tool_list = [t for t in tools if self._resolve_tool(t) and
                         self._available_tools[self._resolve_tool(t)].available]
        else:
            tool_list = [c.tool.value for c in self.get_available_tools()]

        if not tool_list:
            return [AgentResult(
                tool="none", task=task, response="",
                success=False, execution_time=0,
                error="No AI CLI tools available.",
            )]

        results = []
        with ThreadPoolExecutor(max_workers=len(tool_list)) as pool:
            futures = {
                pool.submit(
                    self.run, t, task,
                    use_cache=use_cache, system_prompt=system_prompt,
                ): t
                for t in tool_list
            }
            for future in as_completed(futures):
                try:
                    results.append(future.result())
                except Exception as e:
                    results.append(AgentResult(
                        tool=futures[future], task=task, response="",
                        success=False, execution_time=0, error=str(e),
                    ))
        return results

    def consensus(self, task: str, *,
                  tools: Optional[List[str]] = None,
                  system_prompt: str = "") -> Dict[str, Any]:
        """
        Run task on all tools and build a consensus answer.

        Returns dict with individual results + consensus summary.
        """
        results = self.run_parallel(task, tools=tools, system_prompt=system_prompt)
        successful = [r for r in results if r.success]
        failed = [r for r in results if not r.success]

        if not successful:
            return {
                'success': False,
                'error': 'All agent tools failed',
                'failures': [{'tool': r.tool, 'error': r.error} for r in failed],
            }

        # Sentiment extraction (simple keyword approach)
        sentiments = {}
        for r in successful:
            s = self._extract_sentiment(r.response)
            sentiments[s] = sentiments.get(s, 0) + 1

        consensus_sent = max(sentiments, key=sentiments.get) if sentiments else 'neutral'

        combined = "\n\n".join(
            f"=== {r.tool.upper()} ===\n{r.response}" for r in successful
        )

        return {
            'success': True,
            'task': task,
            'consensus_sentiment': consensus_sent,
            'sentiment_distribution': sentiments,
            'agreement': sentiments.get(consensus_sent, 0) / len(successful),
            'tools_used': [r.tool for r in successful],
            'tools_failed': [r.tool for r in failed],
            'execution_times': {r.tool: r.execution_time for r in successful},
            'combined_response': combined,
            'individual_results': [r.to_dict() for r in successful],
            'timestamp': datetime.now().isoformat(),
        }

    # ------------------------------------------------------------------
    # Advanced Features — Streaming, MCP, Server Mode, Skill Detection
    # ------------------------------------------------------------------

    def get_capabilities_report(self) -> Dict[str, Any]:
        """Generate detailed capability report of all tools (from real --help flags)."""
        report = {
            'timestamp': datetime.now().isoformat(),
            'tools': {},
            'summary': {
                'total_available': 0,
                'with_mcp': 0,
                'with_streaming': 0,
                'with_sandbox': 0,
                'with_json_output': 0,
                'with_web_search': 0,
                'with_json_schema': 0,
                'with_full_auto': 0,
                'with_code_review': 0,
            },
            'smart_routing': {},
        }

        for cap in self.get_all_tools():
            tool_info = {
                'available': cap.available,
                'version': cap.version,
                'path': cap.path,
                'strengths': cap.strengths,
                'best_for': [c.value for c in cap.best_for],
                'priority': cap.priority,
                'success_rate': f"{cap.success_rate:.1f}%",
                'avg_response_time': f"{cap.avg_response_time:.2f}s",
                'total_calls': cap.total_calls,
                'capabilities': {
                    'streaming': cap.supports_streaming,
                    'mcp': cap.supports_mcp,
                    'sandbox': cap.supports_sandbox,
                    'extensions': cap.supports_extensions,
                    'json_output': cap.supports_json_output,
                    'web_search': cap.supports_web_search,
                    'code_review': cap.supports_code_review,
                    'json_schema': cap.supports_json_schema,
                    'system_prompt': cap.supports_system_prompt,
                    'model_select': cap.supports_model_select,
                    'full_auto': cap.supports_full_auto,
                    'file_attach': cap.supports_file_attach,
                    'skills': cap.supports_skills,
                    'agents': cap.supports_agents,
                    'resume': cap.supports_resume,
                    'budget_control': cap.supports_budget,
                },
                'mcp_servers': cap.mcp_servers,
                'detected_skills': cap.detected_skills,
                'detected_extensions': cap.detected_extensions,
            }
            report['tools'][cap.tool.value] = tool_info

            if cap.available:
                s = report['summary']
                s['total_available'] += 1
                if cap.supports_mcp:         s['with_mcp'] += 1
                if cap.supports_streaming:   s['with_streaming'] += 1
                if cap.supports_sandbox:     s['with_sandbox'] += 1
                if cap.supports_json_output: s['with_json_output'] += 1
                if cap.supports_web_search:  s['with_web_search'] += 1
                if cap.supports_json_schema: s['with_json_schema'] += 1
                if cap.supports_full_auto:   s['with_full_auto'] += 1
                if cap.supports_code_review: s['with_code_review'] += 1

        # Build smart-routing table: category -> best tool
        for cat in TaskCategory:
            best = self._route_for_category(cat)
            report['smart_routing'][cat.value] = best.value if best else None

        return report

    def detect_skills(self) -> Dict[str, Any]:
        """Auto-detect available skills/extensions/MCP from all CLI tools."""
        skills = {
            'timestamp': datetime.now().isoformat(),
            'tools': {}
        }

        for tool in AgentTool:
            cap = self._available_tools[tool]
            if not cap.available:
                continue

            tool_skills: Dict[str, list] = {
                'detected': [],
                'mcp_servers': [],
                'extensions': [],
                'skills': [],
            }

            # Detect MCP servers if supported
            if cap.supports_mcp:
                mcp_cmd = None
                if tool == AgentTool.OPENCODE:
                    mcp_cmd = ['opencode', 'mcp', 'list']
                elif tool == AgentTool.GEMINI:
                    mcp_cmd = ['gemini', 'mcp', 'list']
                elif tool == AgentTool.CODEX:
                    mcp_cmd = ['codex', 'mcp', 'list']
                elif tool == AgentTool.CLAUDE:
                    mcp_cmd = ['claude', 'mcp', 'list']

                if mcp_cmd:
                    try:
                        result = subprocess.run(
                            mcp_cmd, capture_output=True, text=True, timeout=10
                        )
                        if result.returncode == 0 and result.stdout.strip():
                            servers = [l.strip() for l in result.stdout.strip().split('\n') if l.strip()]
                            tool_skills['mcp_servers'] = servers
                            cap.mcp_servers = servers
                    except Exception as e:
                        logger.debug(f"Could not detect MCP servers for {tool.value}: {e}")

            # Detect Gemini skills
            if cap.supports_skills and tool == AgentTool.GEMINI:
                try:
                    result = subprocess.run(
                        ['gemini', 'skills', 'list'],
                        capture_output=True, text=True, timeout=10
                    )
                    if result.returncode == 0 and result.stdout.strip():
                        skill_list = [l.strip() for l in result.stdout.strip().split('\n') if l.strip()]
                        tool_skills['skills'] = skill_list
                        cap.detected_skills = skill_list
                except Exception as e:
                    logger.debug(f"Could not detect skills for gemini: {e}")

            # Detect Gemini extensions
            if cap.supports_extensions and tool == AgentTool.GEMINI:
                try:
                    result = subprocess.run(
                        ['gemini', 'extensions', 'list'],
                        capture_output=True, text=True, timeout=10
                    )
                    if result.returncode == 0 and result.stdout.strip():
                        ext_list = [l.strip() for l in result.stdout.strip().split('\n') if l.strip()]
                        tool_skills['extensions'] = ext_list
                        cap.detected_extensions = ext_list
                except Exception as e:
                    logger.debug(f"Could not detect extensions for gemini: {e}")

            # Detect OpenCode agents
            if cap.supports_agents and tool == AgentTool.OPENCODE:
                try:
                    result = subprocess.run(
                        ['opencode', 'agent', 'list'],
                        capture_output=True, text=True, timeout=10
                    )
                    if result.returncode == 0 and result.stdout.strip():
                        agents = [l.strip() for l in result.stdout.strip().split('\n') if l.strip()]
                        tool_skills['detected'] = agents
                except Exception as e:
                    logger.debug(f"Could not detect agents for opencode: {e}")

            skills['tools'][tool.value] = tool_skills

        return skills

    def start_server(self, tool: str, port: int = 0) -> Dict[str, Any]:
        """
        Start a CLI tool in server mode (for local integration).
        Returns server info including URL.
        """
        agent_tool = self._resolve_tool(tool)
        if not agent_tool:
            return {'success': False, 'error': f'Unknown tool: {tool}'}
        
        cap = self._available_tools[agent_tool]
        if not cap.available:
            return {'success': False, 'error': f'{tool} not installed'}
        
        tool_config = TOOL_COMMANDS[agent_tool]
        if 'server' not in tool_config:
            return {'success': False, 'error': f'{tool} does not support server mode'}
        
        try:
            server_cmd = tool_config['server'](port)
            proc = subprocess.Popen(
                server_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            
            # Give server time to start
            time.sleep(2)
            
            if proc.poll() is not None:  # Process exited
                stderr = proc.stderr.read() if proc.stderr else ""
                return {
                    'success': False,
                    'error': f'Server exited: {stderr}',
                    'pid': None,
                }
            
            # Try to get actual port if 0 was specified
            actual_port = port if port > 0 else None
            
            return {
                'success': True,
                'tool': tool,
                'pid': proc.pid,
                'port': actual_port or port,
                'url': f'http://127.0.0.1:{actual_port or port}',
                'command': ' '.join(server_cmd),
            }
        
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def run_with_streaming(self, tool: str, task: str, 
                          callback: Optional[callable] = None) -> AgentResult:
        """
        Run task with streaming output (if tool supports it).
        Callback is called with each output chunk.
        """
        agent_tool = self._resolve_tool(tool)
        if not agent_tool:
            return AgentResult(
                tool=tool, task=task, response="",
                success=False, execution_time=0,
                error=f"Unknown tool: {tool}",
            )
        
        cap = self._available_tools[agent_tool]
        if not cap.available:
            return AgentResult(
                tool=tool, task=task, response="",
                success=False, execution_time=0,
                error=f"{tool} not available",
            )
        
        if not cap.supports_streaming:
            # Fall back to regular run
            result = self.run(tool, task, use_cache=False)
            if callback:
                callback(result.response)
            return result
        
        try:
            tool_config = TOOL_COMMANDS[agent_tool]
            run_fn = tool_config['run']
            cmd = run_fn(task)
            
            start = time.time()
            full_response = ""
            
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            
            # Stream stdout
            for line in proc.stdout:
                full_response += line
                if callback:
                    callback(line)
            
            proc.wait(timeout=TOOL_COMMANDS[agent_tool]['timeout'])
            elapsed = time.time() - start
            
            if proc.returncode == 0:
                result = AgentResult(
                    tool=tool, task=task, response=full_response.strip(),
                    success=True, execution_time=elapsed,
                )
                self._update_metrics(tool, True, elapsed)
                self._record_history(result)
                return result
            else:
                stderr = proc.stderr.read() if proc.stderr else ""
                return AgentResult(
                    tool=tool, task=task, response="",
                    success=False, execution_time=elapsed,
                    error=stderr or f"Exit code {proc.returncode}",
                )
        
        except Exception as e:
            return AgentResult(
                tool=tool, task=task, response="",
                success=False, execution_time=0,
                error=f"Streaming error: {str(e)}",
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_tool(self, name: str) -> Optional[AgentTool]:
        """Resolve string name to AgentTool enum."""
        name_lower = name.lower().strip()
        for tool in AgentTool:
            if tool.value == name_lower:
                return tool
        # Aliases for convenience
        aliases = {
            'open': AgentTool.OPENCODE,
            'oc': AgentTool.OPENCODE,
            'gem': AgentTool.GEMINI,
            'google': AgentTool.GEMINI,
            'cdx': AgentTool.CODEX,
            'openai': AgentTool.CODEX,
            'claude-code': AgentTool.CLAUDE,
            'cc': AgentTool.CLAUDE,
            'anthropic': AgentTool.CLAUDE,
        }
        return aliases.get(name_lower)

    def _rank_tools(self) -> List[AgentTool]:
        """Rank available tools by success rate, priority, then speed."""
        available = [c for c in self._available_tools.values() if c.available]
        if not available:
            return []

        def score(cap: AgentCapability) -> float:
            m = self._metrics[cap.tool.value]
            sr = m['successes'] / m['calls'] if m['calls'] > 0 else 0.5
            speed = 1.0 / (m['avg_time'] + 0.1) if m['avg_time'] > 0 else 1.0
            priority_bonus = (100 - cap.priority) / 100.0  # lower priority = higher bonus
            return sr * 0.5 + speed * 0.2 + priority_bonus * 0.3

        available.sort(key=score, reverse=True)
        return [c.tool for c in available]

    @staticmethod
    def _build_prompt(task: str, system_prompt: str) -> str:
        if system_prompt:
            return f"{system_prompt}\n\n{task}"
        return task

    @staticmethod
    def _extract_sentiment(text: str) -> str:
        t = text.lower()
        bull = sum(1 for w in ['bullish', 'buy', 'uptrend', 'positive', 'growth',
                                'increase', 'rally', 'surge'] if w in t)
        bear = sum(1 for w in ['bearish', 'sell', 'downtrend', 'negative', 'decline',
                                'decrease', 'drop', 'crash'] if w in t)
        if bull > bear:
            return 'bullish'
        elif bear > bull:
            return 'bearish'
        return 'neutral'

    # ------------------------------------------------------------------
    # Caching
    # ------------------------------------------------------------------

    def _cache_key(self, tool: str, task: str) -> str:
        h = hashlib.sha256(f"{tool}:{task}".encode()).hexdigest()[:16]
        return h

    def _get_cache(self, tool: str, task: str) -> Optional[AgentResult]:
        key = self._cache_key(tool, task)
        path = self.cache_dir / f"{key}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            ts = datetime.fromisoformat(data['timestamp'])
            if datetime.now() - ts > timedelta(hours=self.cache_ttl):
                path.unlink(missing_ok=True)
                return None
            return AgentResult(
                tool=data['tool'], task=data['task'],
                response=data['response'], success=True,
                execution_time=0, cached=True,
                timestamp=data['timestamp'],
            )
        except Exception:
            return None

    def _set_cache(self, tool: str, task: str, result: AgentResult):
        key = self._cache_key(tool, task)
        path = self.cache_dir / f"{key}.json"
        try:
            path.write_text(json.dumps(result.to_dict(), ensure_ascii=False), encoding='utf-8')
        except Exception as e:
            rich_logger.debug(f"Cache write failed: {e}")

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def _update_metrics(self, tool: str, success: bool, elapsed: float):
        m = self._metrics.get(tool)
        if not m:
            return
        m['calls'] += 1
        if success:
            m['successes'] += 1
        else:
            m['failures'] += 1
        m['total_time'] += elapsed
        m['avg_time'] = m['total_time'] / m['calls']

    def get_metrics(self) -> Dict[str, Dict]:
        out = {}
        for tool, m in self._metrics.items():
            calls = m['calls']
            out[tool] = {
                'total_calls': calls,
                'successes': m['successes'],
                'failures': m['failures'],
                'success_rate': f"{m['successes'] / calls * 100:.1f}%" if calls else "N/A",
                'avg_response_time': f"{m['avg_time']:.1f}s",
            }
        return out

    # ------------------------------------------------------------------
    # History DB
    # ------------------------------------------------------------------

    def _init_db(self):
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS agent_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tool TEXT NOT NULL,
                    task TEXT NOT NULL,
                    response TEXT,
                    success INTEGER,
                    execution_time REAL,
                    error TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
        finally:
            conn.close()

    def _load_metrics(self):
        """Load historical metrics from DB."""
        try:
            with self._connect() as conn:
                rows = conn.execute("""
                    SELECT tool, 
                           COUNT(*) as calls,
                           SUM(CASE WHEN success=1 THEN 1 ELSE 0 END) as successes,
                           AVG(execution_time) as avg_time
                    FROM agent_history
                    GROUP BY tool
                """).fetchall()
                for tool, calls, successes, avg_time in rows:
                    if tool in self._metrics:
                        self._metrics[tool]['calls'] = calls
                        self._metrics[tool]['successes'] = successes
                        self._metrics[tool]['failures'] = calls - successes
                        self._metrics[tool]['avg_time'] = avg_time or 0
                        self._metrics[tool]['total_time'] = (avg_time or 0) * calls
        except Exception as e:
            rich_logger.debug(f"Could not load metrics: {e}")

    def _record_history(self, result: AgentResult):
        try:
            with self._connect() as conn:
                conn.execute("""
                    INSERT INTO agent_history (tool, task, response, success, execution_time, error)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    result.tool,
                    result.task,
                    result.response[:5000] if result.response else None,
                    1 if result.success else 0,
                    result.execution_time,
                    result.error,
                ))
                conn.commit()
        except Exception as e:
            rich_logger.debug(f"History write failed: {e}")

    def get_history(self, limit: int = 20) -> List[Dict]:
        """Get recent execution history."""
        try:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute("""
                    SELECT * FROM agent_history
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (limit,)).fetchall()
                return [dict(r) for r in rows]
        except Exception:
            return []

    def run_stateful_daily_flow(self, symbol: str = "XAUUSD",
                                preferred_tool: Optional[str] = None,
                                use_consensus: bool = False) -> Dict[str, Any]:
        """
        Run SubAgent daily routine with LangGraph stateful orchestration.
        """
        from sub_agent import SubAgentOrchestrator

        orch = SubAgentOrchestrator(
            preferred_tool=preferred_tool,
            use_consensus=use_consensus,
            use_langgraph=True,
        )
        return orch.daily_routine(symbol=symbol, tool=preferred_tool)

    # ==================================================================
    # Smart Routing — auto-pick the best tool per task category
    # ==================================================================

    def _route_for_category(self, category: TaskCategory) -> Optional[AgentTool]:
        """Pick the best available tool for a task category."""
        candidates = []
        for cap in self._available_tools.values():
            if not cap.available:
                continue
            if category in cap.best_for:
                candidates.append(cap)
        if not candidates:
            # Fallback: any available tool
            available = [c for c in self._available_tools.values() if c.available]
            return available[0].tool if available else None
        # Sort by priority (lower = better), then success rate
        candidates.sort(key=lambda c: (c.priority, -c.success_rate))
        return candidates[0].tool

    def run_smart(self, task: str, category: TaskCategory = TaskCategory.GENERAL,
                  **kwargs) -> AgentResult:
        """
        Smart execution — auto-route task to the best tool for the category.

        Automatically enables optimal flags per category:
          - STRUCTURED_OUTPUT → output_mode="json", json_schema if available
          - WEB_SEARCH → web_search=True on Codex
          - CODE_REVIEW → uses codex review
          - RESEARCH → prefers Gemini/Codex with web search

        Extra kwargs are forwarded to run().
        """
        best_tool = self._route_for_category(category)
        if not best_tool:
            return AgentResult(
                tool="none", task=task, response="",
                success=False, execution_time=0,
                error="No suitable tool available for this category.",
            )

        cap = self._available_tools[best_tool]

        # Auto-set optimal flags per category
        if category == TaskCategory.STRUCTURED_OUTPUT:
            kwargs.setdefault('output_mode', 'json')
        elif category == TaskCategory.WEB_SEARCH and cap.supports_web_search:
            kwargs.setdefault('web_search', True)
        elif category == TaskCategory.RESEARCH:
            # Prefer web search if available
            if cap.supports_web_search:
                kwargs.setdefault('web_search', True)

        logger.info(f"[SmartRoute] {category.value} -> {best_tool.value}")
        return self.run(best_tool.value, task, **kwargs)

    # ==================================================================
    # Structured Output — trade signals, sentiment, risk via JSON schema
    # ==================================================================

    def get_trade_signal(self, prompt: str, *,
                         symbol: str = "XAUUSD",
                         tool: Optional[str] = None) -> AgentResult:
        """
        Get a validated trade signal with native JSON schema (claude --json-schema).

        Returns AgentResult with parsed_json containing:
            direction, confidence, entry_price, stop_loss, take_profit, rationale
        """
        full_prompt = (
            f"You are a gold trading analyst. Analyze {symbol} and provide a precise "
            f"trade signal based on current market conditions.\n\n{prompt}\n\n"
            f"Respond ONLY with valid JSON matching the required schema."
        )

        # Prefer Claude for json_schema, fallback to json output on others
        target = tool or self._best_tool_for('json_schema', 'json_output')
        if not target:
            return self.run_smart(full_prompt, TaskCategory.STRUCTURED_OUTPUT,
                                  output_mode="json")

        cap = self._available_tools.get(self._resolve_tool(target))
        if cap and cap.supports_json_schema:
            return self.run(target, full_prompt,
                            output_mode="json",
                            json_schema=TRADE_SIGNAL_SCHEMA)
        else:
            return self.run(target, full_prompt, output_mode="json")

    def get_sentiment(self, query: str, *,
                      tool: Optional[str] = None) -> AgentResult:
        """
        Get validated sentiment analysis with JSON schema.

        Returns AgentResult with parsed_json containing:
            sentiment, confidence, key_drivers, risk_factors, price_impact
        """
        full_prompt = (
            f"You are a gold market sentiment analyst. Analyze the following and "
            f"provide structured sentiment assessment.\n\n{query}\n\n"
            f"Respond ONLY with valid JSON matching the required schema."
        )

        target = tool or self._best_tool_for('json_schema', 'json_output')
        if not target:
            return self.run_smart(full_prompt, TaskCategory.STRUCTURED_OUTPUT,
                                  output_mode="json")

        cap = self._available_tools.get(self._resolve_tool(target))
        if cap and cap.supports_json_schema:
            return self.run(target, full_prompt,
                            output_mode="json",
                            json_schema=SENTIMENT_SCHEMA)
        else:
            return self.run(target, full_prompt, output_mode="json")

    def get_risk_assessment(self, portfolio_info: str, *,
                            tool: Optional[str] = None) -> AgentResult:
        """
        Get validated risk assessment with JSON schema.

        Returns AgentResult with parsed_json containing:
            risk_score, status, warnings, recommendations
        """
        full_prompt = (
            f"You are a quantitative risk analyst for gold trading. Assess:\n\n"
            f"{portfolio_info}\n\n"
            f"Respond ONLY with valid JSON matching the required schema."
        )

        target = tool or self._best_tool_for('json_schema', 'json_output')
        if not target:
            return self.run_smart(full_prompt, TaskCategory.RISK_ASSESSMENT,
                                  output_mode="json")

        cap = self._available_tools.get(self._resolve_tool(target))
        if cap and cap.supports_json_schema:
            return self.run(target, full_prompt,
                            output_mode="json",
                            json_schema=RISK_ASSESSMENT_SCHEMA)
        else:
            return self.run(target, full_prompt, output_mode="json")

    # ==================================================================
    # Web Search — live internet queries via Codex --search
    # ==================================================================

    def web_search(self, query: str, *,
                   tool: Optional[str] = None) -> AgentResult:
        """
        Live web search using Codex ``--search`` flag.

        Falls back to regular run if no web-search capable tool available.
        """
        target = tool or self._best_tool_for('web_search')
        if not target:
            logger.warning("[WebSearch] No tool with web search, using regular run")
            return self.run_smart(query, TaskCategory.WEB_SEARCH)

        return self.run(target, query, web_search=True, output_mode="json")

    # ==================================================================
    # Code Review — automated via Codex review
    # ==================================================================

    def code_review(self, *, uncommitted: bool = True,
                    base: str = "", custom_prompt: str = "",
                    tool: Optional[str] = None) -> AgentResult:
        """
        Run automated code review via ``codex review``.

        Args:
            uncommitted: Review uncommitted changes (default)
            base: Compare against a branch
            custom_prompt: Additional review instructions
        """
        target_name = tool or self._best_tool_for('code_review')
        if not target_name:
            return AgentResult(
                tool="none", task="code_review", response="",
                success=False, execution_time=0,
                error="No tool supports code review (need Codex).",
            )

        agent_tool = self._resolve_tool(target_name)
        tc = TOOL_COMMANDS.get(agent_tool, {})

        if 'review' not in tc:
            return AgentResult(
                tool=target_name, task="code_review", response="",
                success=False, execution_time=0,
                error=f"{target_name} does not support review mode.",
            )

        try:
            cmd = tc['review'](uncommitted=uncommitted, base=base,
                               custom_prompt=custom_prompt)
            logger.info(f"[CodeReview] Running: {' '.join(cmd)}")

            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=tc.get('timeout', 180),
            )

            return AgentResult(
                tool=target_name,
                task="code_review",
                response=result.stdout.strip(),
                success=result.returncode == 0,
                execution_time=0,
                error=result.stderr.strip() if result.returncode != 0 else None,
            )
        except Exception as e:
            return AgentResult(
                tool=target_name, task="code_review", response="",
                success=False, execution_time=0, error=str(e),
            )

    # ==================================================================
    # Full-Auto Mode — gemini --yolo / codex --full-auto
    # ==================================================================

    def run_full_auto(self, task: str, *,
                      tool: Optional[str] = None) -> AgentResult:
        """
        Run in full-auto mode (auto-approve all tool calls).

        Uses gemini --yolo or codex --full-auto.  Be cautious!
        """
        target = tool or self._best_tool_for('full_auto')
        if not target:
            logger.warning("[FullAuto] No tool supports full-auto, running normally")
            return self.run_smart(task, TaskCategory.MULTI_STEP)

        return self.run(target, task, full_auto=True, output_mode="json")

    # ==================================================================
    # Full Analysis Pipeline — multi-step structured workflow
    # ==================================================================

    def full_analysis_pipeline(self, symbol: str = "XAUUSD") -> Dict[str, Any]:
        """
        Run a comprehensive analysis pipeline using the best tool for each step:

        1. Web search for latest news  (Codex --search)
        2. Sentiment analysis          (Claude --json-schema)
        3. Trade signal generation      (Claude --json-schema)
        4. Risk assessment              (Claude --json-schema)

        Returns dict with all step results + parsed JSON.
        """
        pipeline: Dict[str, Any] = {
            'symbol': symbol,
            'timestamp': datetime.now().isoformat(),
            'steps': {},
        }

        # Step 1: Live news
        logger.info("[Pipeline] Step 1/4: Web search for news...")
        news = self.web_search(f"Latest {symbol} gold market news and price drivers today")
        pipeline['steps']['news'] = news.to_dict()

        # Step 2: Sentiment from news
        logger.info("[Pipeline] Step 2/4: Sentiment analysis...")
        news_text = news.response[:2000] if news.success else f"No news available for {symbol}"
        sentiment = self.get_sentiment(
            f"Based on this context:\n{news_text}\n\nAnalyze {symbol} sentiment."
        )
        pipeline['steps']['sentiment'] = sentiment.to_dict()

        # Step 3: Trade signal
        logger.info("[Pipeline] Step 3/4: Trade signal generation...")
        context = ""
        if sentiment.parsed_json:
            context = f"Sentiment: {sentiment.parsed_json.get('sentiment', 'unknown')}\n"
        signal = self.get_trade_signal(
            f"{context}Generate a trade signal for {symbol} based on current conditions.",
            symbol=symbol,
        )
        pipeline['steps']['signal'] = signal.to_dict()

        # Step 4: Risk assessment
        logger.info("[Pipeline] Step 4/4: Risk assessment...")
        risk_info = f"Symbol: {symbol}\n"
        if signal.parsed_json:
            risk_info += f"Proposed trade: {signal.parsed_json.get('direction', 'N/A')}\n"
            risk_info += f"Confidence: {signal.parsed_json.get('confidence', 'N/A')}%\n"
        risk = self.get_risk_assessment(risk_info)
        pipeline['steps']['risk'] = risk.to_dict()

        # Compile summary
        pipeline['success'] = any(
            pipeline['steps'][s].get('success', False)
            for s in pipeline['steps']
        )
        pipeline['parsed'] = {
            'sentiment': sentiment.parsed_json,
            'signal': signal.parsed_json,
            'risk': risk.parsed_json,
        }

        logger.info("[Pipeline] Analysis complete")
        return pipeline

    # ==================================================================
    # Research & Validate — consensus with structured validation
    # ==================================================================

    def research_and_validate(self, query: str, *,
                              min_agreement: float = 0.6) -> Dict[str, Any]:
        """
        Research a topic, then validate with structured sentiment.

        1. Consensus research across all tools
        2. Structured sentiment validation via JSON schema
        3. Returns combined report with agreement score
        """
        # Step 1: Multi-tool consensus
        consensus = self.consensus(query)

        # Step 2: Validate with structured output
        if consensus.get('success'):
            combined = consensus.get('combined_response', '')[:3000]
            validation = self.get_sentiment(
                f"Validate this research and provide structured assessment:\n\n{combined}"
            )
        else:
            validation = AgentResult(
                tool="none", task="validation", response="",
                success=False, execution_time=0, error="Consensus failed",
            )

        return {
            'query': query,
            'consensus': consensus,
            'validation': validation.to_dict() if isinstance(validation, AgentResult) else {},
            'validated_sentiment': validation.parsed_json if isinstance(validation, AgentResult) else None,
            'agreement': consensus.get('agreement', 0),
            'meets_threshold': consensus.get('agreement', 0) >= min_agreement,
            'timestamp': datetime.now().isoformat(),
        }

    # ------------------------------------------------------------------
    # Internal: find best tool by capability flag
    # ------------------------------------------------------------------

    def _best_tool_for(self, *capability_flags: str) -> Optional[str]:
        """Find the best available tool that supports given capability flags."""
        for flag in capability_flags:
            for cap in self._available_tools.values():
                if not cap.available:
                    continue
                attr_name = f"supports_{flag}"
                if hasattr(cap, attr_name) and getattr(cap, attr_name):
                    return cap.tool.value
        return None
