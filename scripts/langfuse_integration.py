"""
Langfuse Integration Module
=============================
Enterprise-grade observability for AI execution, cost tracking, and quality evaluation.

Provides:
- Automatic LLM call tracing with token counts and costs
- Cost aggregation per provider/model
- Quality evaluation tracking
- Session-based conversation history
- Custom attributes and metadata

Usage:
    from langfuse_integration import get_langfuse_client
    
    lf = get_langfuse_client()
    with lf.trace_execution("trade_analysis", metadata={"symbol": "XAUUSD"}):
        result = run_analysis()
        lf.log_result(result, quality_score=0.95)
"""

import os
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from datetime import datetime
from logger import get_logger

try:
    from langfuse import Langfuse
    LANGFUSE_AVAILABLE = True
except ImportError:
    LANGFUSE_AVAILABLE = False

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────
# Langfuse Configuration
# ─────────────────────────────────────────────────────

@dataclass
class LangfuseConfig:
    """Langfuse configuration."""
    enabled: bool = True
    public_key: str = ""
    secret_key: str = ""
    host: str = "https://cloud.langfuse.com"
    debug: bool = False
    
    @classmethod
    def from_env(cls) -> 'LangfuseConfig':
        """Load configuration from environment variables."""
        return cls(
            enabled=os.getenv('LANGFUSE_ENABLED', 'true').lower() == 'true',
            public_key=os.getenv('LANGFUSE_PUBLIC_KEY', ''),
            secret_key=os.getenv('LANGFUSE_SECRET_KEY', ''),
            host=os.getenv('LANGFUSE_HOST', 'https://cloud.langfuse.com'),
            debug=os.getenv('LANGFUSE_DEBUG', 'false').lower() == 'true',
        )


# ─────────────────────────────────────────────────────
# Execution Trace Context Manager
# ─────────────────────────────────────────────────────

class ExecutionTrace:
    """Context manager for tracing execution with Langfuse."""
    
    def __init__(
        self,
        name: str,
        lf_client: 'Langfuse',
        metadata: Optional[Dict[str, Any]] = None,
        public: bool = False,
    ):
        self.name = name
        self.lf_client = lf_client
        self.metadata = metadata or {}
        self.public = public
        self.trace = None
        self.start_time = None
    
    def __enter__(self):
        """Start trace."""
        self.start_time = datetime.now()
        
        if LANGFUSE_AVAILABLE and self.lf_client:
            self.trace = self.lf_client.trace(
                name=self.name,
                metadata=self.metadata,
                public=self.public,
            )
            logger.debug(f"Trace started: {self.name}")
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """End trace with status."""
        if not self.trace:
            return
        
        duration = (datetime.now() - self.start_time).total_seconds()
        
        status = "error" if exc_type else "success"
        self.trace.update(
            output={"duration_ms": duration * 1000, "status": status},
        )
        
        if exc_type:
            logger.warning(f"Trace error: {exc_type.__name__}: {exc_val}")
        else:
            logger.debug(f"Trace completed: {self.name} ({duration:.2f}s)")


# ─────────────────────────────────────────────────────
# Langfuse Client Wrapper
# ─────────────────────────────────────────────────────

class LangfuseIntegration:
    """
    Enterprise observability client wrapping Langfuse SDK.
    
    Manages LLM tracing, cost tracking, and quality evaluation.
    """
    
    def __init__(self, config: Optional[LangfuseConfig] = None):
        self.config = config or LangfuseConfig.from_env()
        self.lf = None
        self.session_id = None
        self.execution_history: List[Dict[str, Any]] = []
        
        self._initialize()
    
    def _initialize(self):
        """Initialize Langfuse client if credentials available."""
        if not self.config.enabled:
            logger.info("[Langfuse] Disabled (LANGFUSE_ENABLED=false)")
            return
        
        if not LANGFUSE_AVAILABLE:
            logger.warning("[Langfuse] Package not installed (pip install langfuse)")
            self.config.enabled = False
            return
        
        if not self.config.public_key or not self.config.secret_key:
            logger.warning("[Langfuse] Credentials missing (set LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY)")
            self.config.enabled = False
            return
        
        try:
            self.lf = Langfuse(
                public_key=self.config.public_key,
                secret_key=self.config.secret_key,
                host=self.config.host,
                debug=self.config.debug,
            )
            self.session_id = f"gold_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            logger.info(f"[Langfuse] Connected: {self.session_id}")
        except Exception as e:
            logger.error(f"[Langfuse] Connection failed: {e}")
            self.config.enabled = False
    
    # ─────────────────────────────────────────────────
    # Execution Tracing
    # ─────────────────────────────────────────────────
    
    def trace_execution(
        self,
        name: str,
        metadata: Optional[Dict[str, Any]] = None,
        public: bool = False,
    ) -> ExecutionTrace:
        """
        Create execution trace context manager.
        
        Args:
            name: Trace name (e.g., "daily_analysis")
            metadata: Custom metadata dict
            public: Whether to make trace public
        
        Returns:
            ExecutionTrace context manager
        """
        return ExecutionTrace(
            name=name,
            lf_client=self.lf if self.config.enabled else None,
            metadata={
                "session": self.session_id,
                **(metadata or {})
            },
            public=public,
        )
    
    def log_llm_call(
        self,
        provider: str,
        model: str,
        prompt: str,
        response: str,
        tokens_in: int = 0,
        tokens_out: int = 0,
        cost: float = 0.0,
        latency_ms: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Log LLM provider call.
        
        Args:
            provider: AI provider (opencode, gemini, etc.)
            model: Model name
            prompt: Input prompt
            response: Generated response
            tokens_in: Input tokens
            tokens_out: Output tokens
            cost: Estimated cost in USD
            latency_ms: Request latency in milliseconds
        
        Returns:
            Log entry dict
        """
        entry = {
            "timestamp": datetime.now().isoformat(),
            "provider": provider,
            "model": model,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost": cost,
            "latency_ms": latency_ms,
        }
        
        self.execution_history.append(entry)
        
        if self.config.enabled and self.lf:
            try:
                self.lf.generation(
                    name=f"{provider}/{model}",
                    input=prompt[:1000],  # Truncate for storage
                    output=response[:1000],
                    model=model,
                    usage={
                        "input": tokens_in,
                        "output": tokens_out,
                        "total": tokens_in + tokens_out,
                    },
                    metadata={
                        "session": self.session_id,
                        "provider": provider,
                        "cost_usd": cost,
                        "latency_ms": latency_ms,
                    },
                )
            except Exception as e:
                logger.warning(f"Failed to log LLM call: {e}")
        
        return entry
    
    def log_quality_score(
        self,
        trace_name: str,
        score: float,
        comment: str = "",
    ):
        """
        Log quality evaluation score.
        
        Args:
            trace_name: Name of trace to score
            score: Quality score (0-1)
            comment: Optional comment
        """
        if self.config.enabled and self.lf:
            try:
                self.lf.score(
                    trace_id=trace_name,
                    name="quality",
                    value=score,
                    comment=comment,
                )
                logger.debug(f"Quality score logged: {trace_name} = {score:.2%}")
            except Exception as e:
                logger.warning(f"Failed to log quality score: {e}")
    
    # ─────────────────────────────────────────────────
    # Cost & Usage Analytics
    # ─────────────────────────────────────────────────
    
    def get_cost_summary(self) -> Dict[str, Any]:
        """
        Get cost summary from execution history.
        
        Returns:
            Dict with total_cost, cost_by_provider, call_count
        """
        total_cost = sum(e.get('cost', 0) for e in self.execution_history)
        
        by_provider = {}
        for entry in self.execution_history:
            provider = entry.get('provider', 'unknown')
            if provider not in by_provider:
                by_provider[provider] = {'cost': 0, 'calls': 0}
            by_provider[provider]['cost'] += entry.get('cost', 0)
            by_provider[provider]['calls'] += 1
        
        return {
            'total_cost': total_cost,
            'cost_by_provider': by_provider,
            'total_calls': len(self.execution_history),
            'avg_latency_ms': (
                sum(e.get('latency_ms', 0) for e in self.execution_history) 
                / len(self.execution_history) if self.execution_history else 0
            ),
        }
    
    def get_execution_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent execution history."""
        return self.execution_history[-limit:]
    
    # ─────────────────────────────────────────────────
    # Session Management
    # ─────────────────────────────────────────────────
    
    def flush(self):
        """Flush pending events to Langfuse."""
        if self.config.enabled and self.lf:
            try:
                self.lf.flush()
                logger.info("[Langfuse] Flushed pending events")
            except Exception as e:
                logger.warning(f"Failed to flush Langfuse: {e}")
    
    def get_dashboard_url(self) -> str:
        """Get link to Langfuse dashboard for this session."""
        if self.config.enabled:
            return f"{self.config.host}/trace/{self.session_id}"
        return ""


# ─────────────────────────────────────────────────────
# Singleton factory
# ─────────────────────────────────────────────────────

_langfuse_instance: Optional[LangfuseIntegration] = None


def get_langfuse_client(config: Optional[LangfuseConfig] = None) -> LangfuseIntegration:
    """
    Get or create singleton LangfuseIntegration instance.
    
    Args:
        config: Optional LangfuseConfig (uses env vars if None)
    
    Returns:
        LangfuseIntegration singleton
    """
    global _langfuse_instance
    if _langfuse_instance is None:
        _langfuse_instance = LangfuseIntegration(config)
    return _langfuse_instance
