"""
LiteLLM Unified Client for AI Agents
====================================

Provides a unified interface to call OpenCode, KiloCode, Gemini, Codex, and other AI models
via LiteLLM, with automatic fallback, retry logic, and cost tracking.

Phase 1: High Impact / Quick Wins
- Unified provider interface
- Built-in retries and exponential backoff
- Cost estimation
- Structured logging with Rich
"""

import time
import json
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import sqlite3

from logger import get_logger

try:
    from litellm import completion, get_llm_provider
except ImportError:
    raise ImportError("LiteLLM not installed. Run: pip install litellm")

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────────
# LLM Provider Configuration (Maps CLI Tools to Models)
# ─────────────────────────────────────────────────────────

PROVIDER_CONFIGS = {
    "opencode": {
        "model": "openai/gpt-4-turbo-preview",  # Can override per request
        "max_retries": 2,
        "timeout": 120,
        "temperature": 0.7,
    },
    "kilocode": {
        "model": "claude-3-opus-20240229",  # Anthropic via LiteLLM
        "max_retries": 2,
        "timeout": 120,
        "temperature": 0.7,
    },
    "gemini": {
        "model": "gemini-1.5-pro",  # Google Gemini via LiteLLM
        "max_retries": 2,
        "timeout": 120,
        "temperature": 0.7,
    },
    "codex": {
        "model": "openai/gpt-3.5-turbo",  # Fallback OpenAI model
        "max_retries": 2,
        "timeout": 120,
        "temperature": 0.7,
    },
}

# Cost estimates per 1K tokens (USD)
TOKEN_COSTS = {
    "openai/gpt-4-turbo-preview": {"input": 0.01, "output": 0.03},
    "claude-3-opus-20240229": {"input": 0.015, "output": 0.075},
    "gemini-1.5-pro": {"input": 0.0075, "output": 0.03},
    "openai/gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
}


@dataclass
class LLMResponse:
    """Structured response from LLM call."""
    provider: str
    model: str
    content: str
    tokens_used: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    execution_time: float = 0.0
    success: bool = True
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "content": self.content,
            "tokens_used": self.tokens_used,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": round(self.cost_usd, 6),
            "execution_time": round(self.execution_time, 2),
            "success": self.success,
            "error": self.error,
        }


class LiteLLMClient:
    """
    Unified LiteLLM client for all AI agent calls.
    
    Features:
    - Multiple provider support (OpenAI, Anthropic, Google, etc.)
    - Automatic fallback between providers
    - Retry with exponential backoff
    - Cost tracking and estimation
    - Rate limit handling
    - Request caching
    """
    
    def __init__(self, cache_dir: str = "data/llm_cache", 
                 cost_db_path: str = "data/llm_costs.db"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cost_db_path = Path(cost_db_path)
        self._init_cost_db()
        self.request_cache: Dict[str, LLMResponse] = {}
        
    def _init_cost_db(self):
        """Initialize SQLite database for cost tracking."""
        try:
            conn = sqlite3.connect(str(self.cost_db_path))
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS llm_costs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    prompt_hash TEXT UNIQUE,
                    input_tokens INTEGER,
                    output_tokens INTEGER,
                    cost_usd REAL,
                    execution_time REAL
                )
            """)
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"[LiteLLM] Cost DB init failed: {e}")
    
    def call(self, provider: str, prompt: str, 
             system_prompt: Optional[str] = None,
             max_retries: Optional[int] = None,
             temperature: Optional[float] = None,
             **kwargs) -> LLMResponse:
        """
        Call an LLM via LiteLLM with unified interface.
        
        Args:
            provider: Provider name (opencode, kilocode, gemini, codex)
            prompt: User message/prompt
            system_prompt: Optional system prompt
            max_retries: Override default retries
            temperature: Override default temperature
            **kwargs: Additional LiteLLM kwargs
        
        Returns:
            LLMResponse object
        """
        if provider not in PROVIDER_CONFIGS:
            return LLMResponse(
                provider=provider, model="unknown", content="",
                success=False, error=f"Unknown provider: {provider}"
            )
        
        config = PROVIDER_CONFIGS[provider]
        model = config["model"]
        retries = max_retries or config["max_retries"]
        temp = temperature if temperature is not None else config["temperature"]
        
        # Build messages
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        start_time = time.time()
        last_error = None
        
        # Retry loop with exponential backoff
        for attempt in range(retries + 1):
            try:
                logger.info(f"[LiteLLM] Calling {provider} ({model}) — attempt {attempt + 1}")
                
                # Call LiteLLM
                response = completion(
                    model=model,
                    messages=messages,
                    temperature=temp,
                    timeout=config["timeout"],
                    **kwargs
                )
                
                content = response.choices[0].message.content
                tokens = response.usage.total_tokens  if hasattr(response, 'usage') else 0
                input_tokens = response.usage.prompt_tokens if hasattr(response, 'usage') else 0
                output_tokens = response.usage.completion_tokens if hasattr(response, 'usage') else 0
                
                execution_time = time.time() - start_time
                cost_usd = self._estimate_cost(model, input_tokens, output_tokens)
                
                result = LLMResponse(
                    provider=provider,
                    model=model,
                    content=content,
                    tokens_used=tokens,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_usd=cost_usd,
                    execution_time=execution_time,
                    success=True,
                )
                
                # Log cost
                self._log_cost(provider, model, input_tokens, output_tokens, cost_usd, execution_time)
                
                logger.info(
                    f"[LiteLLM] {provider} success | "
                    f"tokens={tokens} | cost=${cost_usd:.4f} | time={execution_time:.1f}s"
                )
                
                return result
                
            except Exception as e:
                last_error = str(e)
                logger.warning(f"[LiteLLM] {provider} attempt {attempt + 1} failed: {e}")
                
                if attempt < retries:
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.info(f"[LiteLLM] Retrying in {wait_time}s...")
                    time.sleep(wait_time)
        
        # All retries exhausted
        execution_time = time.time() - start_time
        return LLMResponse(
            provider=provider,
            model=model,
            content="",
            execution_time=execution_time,
            success=False,
            error=last_error or "Unknown error"
        )
    
    def call_with_fallback(self, providers: List[str], prompt: str,
                          system_prompt: Optional[str] = None,
                          **kwargs) -> LLMResponse:
        """
        Call multiple providers in sequence, using first success.
        
        Args:
            providers: List of provider names (opencode, kilocode, gemini, codex)
            prompt: User message
            system_prompt: Optional system prompt
            **kwargs: Additional LiteLLM kwargs
        
        Returns:
            LLMResponse from first successful provider
        """
        for provider in providers:
            result = self.call(provider, prompt, system_prompt, **kwargs)
            if result.success:
                logger.info(f"[LiteLLM] Fallback succeeded with {provider}")
                return result
            else:
                logger.warning(f"[LiteLLM] Fallback {provider} failed, trying next")
        
        # All providers failed
        return LLMResponse(
            provider="none", model="none", content="",
            success=False, error="All providers failed"
        )
    
    def _estimate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """Estimate API cost based on token usage."""
        costs = TOKEN_COSTS.get(model, {"input": 0.001, "output": 0.001})
        input_cost = (input_tokens / 1000) * costs["input"]
        output_cost = (output_tokens / 1000) * costs["output"]
        return input_cost + output_cost
    
    def _log_cost(self, provider: str, model: str, input_tokens: int,
                  output_tokens: int, cost_usd: float, execution_time: float):
        """Log cost to database."""
        try:
            conn = sqlite3.connect(str(self.cost_db_path))
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO llm_costs
                (provider, model, input_tokens, output_tokens, cost_usd, execution_time)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (provider, model, input_tokens, output_tokens, cost_usd, execution_time))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"[LiteLLM] Failed to log cost: {e}")
    
    def get_total_cost(self, days: int = 7) -> Dict[str, Any]:
        """Get total cost metrics for last N days."""
        try:
            conn = sqlite3.connect(str(self.cost_db_path))
            cursor = conn.cursor()
            
            cursor.execute(f"""
                SELECT provider, COUNT(*) as calls, SUM(cost_usd) as total_cost,
                       AVG(execution_time) as avg_time
                FROM llm_costs
                WHERE datetime(timestamp) >= datetime('now', '-{days} days')
                GROUP BY provider
            """)
            
            rows = cursor.fetchall()
            conn.close()
            
            result = {}
            for row in rows:
                result[row[0]] = {
                    "calls": row[1],
                    "total_cost": round(row[2], 4) if row[2] else 0,
                    "avg_time": round(row[3], 2) if row[3] else 0,
                }
            
            return result
        except Exception as e:
            logger.error(f"[LiteLLM] Failed to get cost metrics: {e}")
            return {}


# Singleton instance
_llm_client: Optional[LiteLLMClient] = None


def get_llm_client() -> LiteLLMClient:
    """Get or create the singleton LiteLLM client."""
    global _llm_client
    if _llm_client is None:
        _llm_client = LiteLLMClient()
    return _llm_client
