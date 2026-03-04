"""
LangGraph orchestration for SubAgent workflows.
"""

from __future__ import annotations

from typing import Any, Dict, TypedDict
from datetime import datetime

from logger import get_logger

logger = get_logger(__name__)

try:
    from langgraph.graph import END, StateGraph
except Exception:  # pragma: no cover - graceful fallback when dependency missing
    END = None
    StateGraph = None


class AgentFlowState(TypedDict, total=False):
    symbol: str
    tool: str
    started_at: str
    completed_at: str
    steps: Dict[str, Dict[str, Any]]
    step_order: list[str]
    success: bool
    failed_step: str
    error: str


class AgentLangGraphOrchestrator:
    """Stateful orchestration for daily routine with retry + fallback semantics."""

    def __init__(self, sub_agent_orchestrator):
        self.sub = sub_agent_orchestrator

    @staticmethod
    def is_available() -> bool:
        return StateGraph is not None

    def _run_step(self, state: AgentFlowState, key: str, fn) -> AgentFlowState:
        steps = state.setdefault("steps", {})
        order = state.setdefault("step_order", [])
        order.append(key)

        result = fn()
        steps[key] = result

        if not result.get("success", False):
            state["success"] = False
            state["failed_step"] = key
            state["error"] = result.get("error") or "unknown error"
            logger.warning(f"[LangGraph] Step failed: {key} - {state['error']}")
        return state

    def _news_digest_node(self, state: AgentFlowState) -> AgentFlowState:
        tool = state.get("tool")
        return self._run_step(state, "news_digest", lambda: self.sub.news_digest(tool=tool))

    def _technical_analysis_node(self, state: AgentFlowState) -> AgentFlowState:
        tool = state.get("tool")
        symbol = state.get("symbol", "XAUUSD")
        return self._run_step(state, "technical_analysis", lambda: self.sub.analyze(symbol=symbol, tool=tool))

    def _trading_plan_node(self, state: AgentFlowState) -> AgentFlowState:
        tool = state.get("tool")
        symbol = state.get("symbol", "XAUUSD")
        news = state.get("steps", {}).get("news_digest", {})
        market_condition = news.get("sentiment", "unknown")
        return self._run_step(
            state,
            "trading_plan",
            lambda: self.sub.plan(symbol=symbol, market_condition=market_condition, tool=tool),
        )

    def _risk_assessment_node(self, state: AgentFlowState) -> AgentFlowState:
        tool = state.get("tool")
        return self._run_step(state, "risk_assessment", lambda: self.sub.assess_risk(tool=tool))

    def _daily_summary_node(self, state: AgentFlowState) -> AgentFlowState:
        tool = state.get("tool")
        news = state.get("steps", {}).get("news_digest", {})
        news_snippet = (news.get("response", "")[:200] + "...") if news.get("response") else "No research yet"
        return self._run_step(
            state,
            "daily_summary",
            lambda: self.sub.daily_summary(research_consensus=news_snippet, tool=tool),
        )

    @staticmethod
    def _route_next_after_news(state: AgentFlowState) -> str:
        return "technical_analysis" if state.get("success", True) else "failed"

    @staticmethod
    def _route_next_generic(state: AgentFlowState, next_node: str) -> str:
        return next_node if state.get("success", True) else "failed"

    @staticmethod
    def _failed_node(state: AgentFlowState) -> AgentFlowState:
        state["completed_at"] = datetime.now().isoformat()
        state["success"] = False
        return state

    @staticmethod
    def _done_node(state: AgentFlowState) -> AgentFlowState:
        state["completed_at"] = datetime.now().isoformat()
        state["success"] = state.get("success", True)
        return state

    def run_daily_routine(self, symbol: str = "XAUUSD", tool: str | None = None) -> Dict[str, Any]:
        """Execute daily routine via LangGraph state machine."""
        if not self.is_available():
            raise RuntimeError("LangGraph is not available. Install dependency: langgraph")

        graph = StateGraph(AgentFlowState)
        graph.add_node("news_digest", self._news_digest_node)
        graph.add_node("technical_analysis", self._technical_analysis_node)
        graph.add_node("trading_plan", self._trading_plan_node)
        graph.add_node("risk_assessment", self._risk_assessment_node)
        graph.add_node("daily_summary", self._daily_summary_node)
        graph.add_node("failed", self._failed_node)
        graph.add_node("done", self._done_node)

        graph.set_entry_point("news_digest")
        graph.add_conditional_edges("news_digest", self._route_next_after_news, {
            "technical_analysis": "technical_analysis",
            "failed": "failed",
        })
        graph.add_conditional_edges(
            "technical_analysis",
            lambda s: self._route_next_generic(s, "trading_plan"),
            {"trading_plan": "trading_plan", "failed": "failed"},
        )
        graph.add_conditional_edges(
            "trading_plan",
            lambda s: self._route_next_generic(s, "risk_assessment"),
            {"risk_assessment": "risk_assessment", "failed": "failed"},
        )
        graph.add_conditional_edges(
            "risk_assessment",
            lambda s: self._route_next_generic(s, "daily_summary"),
            {"daily_summary": "daily_summary", "failed": "failed"},
        )
        graph.add_conditional_edges(
            "daily_summary",
            lambda s: self._route_next_generic(s, "done"),
            {"done": "done", "failed": "failed"},
        )

        graph.add_edge("failed", END)
        graph.add_edge("done", END)

        app = graph.compile()
        initial_state: AgentFlowState = {
            "symbol": symbol,
            "tool": tool or "",
            "started_at": datetime.now().isoformat(),
            "steps": {},
            "step_order": [],
            "success": True,
        }
        final_state = app.invoke(initial_state)

        return {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "symbol": symbol,
            "started_at": final_state.get("started_at"),
            "completed_at": final_state.get("completed_at"),
            "success": final_state.get("success", False),
            "steps": final_state.get("steps", {}),
            "step_order": final_state.get("step_order", []),
            "failed_step": final_state.get("failed_step"),
            "error": final_state.get("error"),
            "orchestration": "langgraph",
        }

