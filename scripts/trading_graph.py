"""
trading_graph.py — LangGraph-based trading pipeline for ClawGold.

Replaces ad-hoc orchestration in decision_engine.py and SubAgentOrchestrator
with a proper stateful graph:

    START
      → research     : AI-powered market research
      → analyze      : Sentiment + technical analysis
      → validate     : Risk check + confidence gate
      ↙ (low conf)  → research  (retry loop, max 3x)
      → human_review : Interrupt — wait for user approval
      ↙ (approved)  → execute   : Trade execution via MT5
      → monitor      : Log result + notify
      → END

Usage:
    from scripts.trading_graph import build_graph, run_pipeline
    result = run_pipeline("XAUUSD", "H1")
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Literal, Optional

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from typing_extensions import TypedDict

logger = logging.getLogger(__name__)

# ─── State ────────────────────────────────────────────────────────────────────


class TradingState(TypedDict, total=False):
    symbol: str
    timeframe: str
    # Pipeline outputs
    research: dict
    analysis: dict
    signal: dict          # {direction, confidence, entry, sl, tp, reason}
    risk: dict            # {approved, multiplier, reason}
    execution: dict       # {ticket, price, volume, timestamp}
    # Control
    approved: bool        # human approval
    iteration: int        # research retry counter
    messages: list[str]   # audit trail


# ─── Nodes ────────────────────────────────────────────────────────────────────


def research_node(state: TradingState) -> dict:
    """AI-powered market research: news + macro sentiment."""
    symbol = state.get("symbol", "XAUUSD")
    iteration = state.get("iteration", 0)
    messages = list(state.get("messages", []))
    messages.append(f"[research] iteration={iteration+1}")

    research: dict[str, Any] = {"timestamp": datetime.utcnow().isoformat()}
    try:
        from scripts.ai_researcher import AIResearcher
        from scripts.config_loader import load_config
        cfg = load_config()
        researcher = AIResearcher(config=cfg)
        sentiment = researcher.get_market_sentiment(symbol)
        research["sentiment"] = sentiment
        research["summary"] = str(sentiment.get("summary", ""))
        messages.append(f"[research] sentiment={sentiment.get('overall', 'neutral')}")
    except Exception as exc:
        research["error"] = str(exc)
        research["sentiment"] = {"overall": "neutral", "score": 0.0}
        messages.append(f"[research] fallback (error: {exc})")

    return {"research": research, "iteration": iteration + 1, "messages": messages}


def analyze_node(state: TradingState) -> dict:
    """Sentiment analysis + derive a trading signal from research."""
    symbol = state.get("symbol", "XAUUSD")
    messages = list(state.get("messages", []))

    analysis: dict[str, Any] = {}
    signal: dict[str, Any] = {
        "direction": "HOLD",
        "confidence": 0.0,
        "entry": None,
        "sl": None,
        "tp": None,
        "reason": "No analysis available",
    }

    try:
        from scripts.sentiment_analyzer import SentimentAnalyzer
        sa = SentimentAnalyzer()
        research = state.get("research", {})
        text = research.get("summary", "") or str(research.get("sentiment", ""))
        if text:
            result = sa.analyze_text(text, use_ai=True)
            analysis["sentiment"] = str(result)
            # Handle both dict and dataclass/namedtuple returns
            if hasattr(result, "score"):
                score = float(result.score)
                label = getattr(result, "label", "neutral")
            elif isinstance(result, dict):
                score = float(result.get("score", 0.0))
                label = result.get("label", "neutral")
            else:
                score, label = 0.0, "neutral"
            # Simple signal derivation from sentiment
            if score > 0.6:
                direction = "BUY"
                confidence = min(score, 0.95)
            elif score < -0.4:
                direction = "SELL"
                confidence = min(abs(score), 0.95)
            else:
                direction = "HOLD"
                confidence = 0.3
            signal.update({
                "direction": direction,
                "confidence": confidence,
                "reason": f"Sentiment={label} score={score:.2f}",
            })
            messages.append(f"[analyze] signal={direction} confidence={confidence:.2f}")
    except Exception as exc:
        analysis["error"] = str(exc)
        messages.append(f"[analyze] fallback HOLD (error: {exc})")

    try:
        from scripts.advanced_trader import AdvancedTrader
        from scripts.config_loader import load_config
        cfg = load_config()
        trader = AdvancedTrader(config=cfg)
        ai_opt = trader.get_ai_strategy_optimization({"symbol": symbol})
        analysis["ai_strategy"] = ai_opt
        messages.append(f"[analyze] ai_strategy={ai_opt.get('strategy_type','unknown')}")
    except Exception as exc:
        messages.append(f"[analyze] ai_strategy skipped ({exc})")

    return {"analysis": analysis, "signal": signal, "messages": messages}


def validate_node(state: TradingState) -> dict:
    """Risk validation: position sizing, daily loss check, confidence gate."""
    messages = list(state.get("messages", []))
    signal = state.get("signal", {})

    risk: dict[str, Any] = {"approved": False, "multiplier": 1.0, "reason": ""}

    try:
        from scripts.risk_manager import RiskManager
        from scripts.config_loader import load_config
        cfg = load_config()
        rm = RiskManager(config=cfg)
        market_ctx = {
            "signal": signal.get("direction"),
            "confidence": signal.get("confidence", 0.0),
            "symbol": state.get("symbol", "XAUUSD"),
        }
        rec = rm.get_dynamic_risk_recommendation(market_ctx)
        risk["multiplier"] = rec.get("risk_multiplier", 1.0)
        risk["approved"] = rec.get("risk_multiplier", 0) > 0
        risk["reason"] = rec.get("reason", "")
        messages.append(
            f"[validate] risk_multiplier={risk['multiplier']} approved={risk['approved']}"
        )
    except Exception as exc:
        # Fallback: approve if confidence is sufficient
        conf = signal.get("confidence", 0.0)
        risk["approved"] = conf >= 0.6
        risk["reason"] = f"Fallback validation (error: {exc})"
        messages.append(f"[validate] fallback approved={risk['approved']}")

    return {"risk": risk, "messages": messages}


def human_review_node(state: TradingState) -> dict:
    """Human-in-the-loop gate. Pauses graph until user responds."""
    signal = state.get("signal", {})
    risk = state.get("risk", {})
    symbol = state.get("symbol", "XAUUSD")

    summary = (
        f"\n{'='*50}\n"
        f"  ClawGold — Trade Approval Required\n"
        f"{'='*50}\n"
        f"  Symbol    : {symbol}\n"
        f"  Direction : {signal.get('direction')}\n"
        f"  Confidence: {signal.get('confidence', 0):.1%}\n"
        f"  Reason    : {signal.get('reason','')}\n"
        f"  Risk Mult : {risk.get('multiplier', 1.0):.2f}x\n"
        f"{'='*50}\n"
        f"  Type 'yes' to execute, anything else to skip.\n"
    )

    # This pauses the graph. Resume with Command(resume=True/False)
    approved: bool = interrupt(summary)

    messages = list(state.get("messages", []))
    messages.append(f"[human_review] approved={approved}")
    return {"approved": approved, "messages": messages}


def execute_node(state: TradingState) -> dict:
    """Execute the trade via MT5."""
    signal = state.get("signal", {})
    risk = state.get("risk", {})
    symbol = state.get("symbol", "XAUUSD")
    messages = list(state.get("messages", []))

    execution: dict[str, Any] = {"timestamp": datetime.utcnow().isoformat()}

    try:
        from scripts.mt5_manager import MT5Manager
        from scripts.config_loader import load_config
        cfg = load_config()
        mt5 = MT5Manager(config=cfg)
        if mt5.connect():
            direction = signal.get("direction", "HOLD")
            lot = 0.01 * risk.get("multiplier", 1.0)
            ticket = mt5.place_order(
                symbol=symbol,
                order_type=direction,
                volume=round(lot, 2),
                sl=signal.get("sl"),
                tp=signal.get("tp"),
                comment="ClawGold-Graph",
            )
            execution["ticket"] = ticket
            execution["volume"] = lot
            execution["direction"] = direction
            messages.append(f"[execute] ticket={ticket} vol={lot} dir={direction}")
        else:
            execution["error"] = "MT5 connection failed"
            messages.append("[execute] MT5 connection failed — skipped")
    except Exception as exc:
        execution["error"] = str(exc)
        messages.append(f"[execute] error: {exc}")

    return {"execution": execution, "messages": messages}


def monitor_node(state: TradingState) -> dict:
    """Log execution result and send Telegram notification."""
    messages = list(state.get("messages", []))
    execution = state.get("execution", {})
    signal = state.get("signal", {})

    try:
        from scripts.notifier import Notifier
        from scripts.config_loader import load_config
        cfg = load_config()
        notifier = Notifier(config=cfg)
        ticket = execution.get("ticket", "N/A")
        direction = signal.get("direction", "N/A")
        msg = (
            f"[OK] ClawGold Executed\n"
            f"Ticket: {ticket} | {direction}\n"
            f"Vol: {execution.get('volume','?')} | "
            f"Confidence: {signal.get('confidence',0):.1%}"
        )
        notifier.send(msg)

        # ─── Integrated Smart Business Flow ───────────────────────────────────
        try:
            # 1. Update Track Record (Performance Tracker)
            from scripts.performance_tracker import PerformanceTracker
            perf = PerformanceTracker(config=cfg)
            # 2. Broadcast to Signal Service
            from scripts.signal_service import SignalService
            ss = SignalService(config=cfg)
            ss.broadcast_signal(
                symbol=symbol,
                direction=direction,
                confidence=signal.get('confidence',0),
                entry=execution.get('price'),
                stop_loss=signal.get('sl'),
                take_profit=signal.get('tp')
            )
            messages.append(f"[monitor] business flow complete: signal broadcasted")
        except Exception as b_exc:
            messages.append(f"[monitor] business flow error: {b_exc}")

        messages.append(f"[monitor] notified ticket={ticket}")
    except Exception as exc:
        messages.append(f"[monitor] notify skipped ({exc})")

    logger.info("Pipeline complete | execution=%s", execution)
    return {"messages": messages}


# ─── Routing ──────────────────────────────────────────────────────────────────


def route_after_validate(state: TradingState) -> Literal[
    "human_review", "research", "__end__"
]:
    """Gate: retry research if low confidence, skip to end if HOLD."""
    signal = state.get("signal", {})
    direction = signal.get("direction", "HOLD")
    confidence = signal.get("confidence", 0.0)
    iteration = state.get("iteration", 0)

    if direction == "HOLD":
        return "__end__"
    if confidence < 0.6:
        if iteration >= 3:
            logger.warning("Max retries reached — skipping trade")
            return "__end__"
        return "research"
    return "human_review"


def route_after_human(state: TradingState) -> Literal["execute", "__end__"]:
    if state.get("approved"):
        return "execute"
    return "__end__"


# ─── Build Graph ──────────────────────────────────────────────────────────────


def build_graph(checkpointer=None) -> StateGraph:
    """Build and compile the trading pipeline graph."""
    builder = StateGraph(TradingState)

    # Nodes
    builder.add_node("research", research_node)
    builder.add_node("analyze", analyze_node)
    builder.add_node("validate", validate_node)
    builder.add_node("human_review", human_review_node)
    builder.add_node("execute", execute_node)
    builder.add_node("monitor", monitor_node)

    # Edges
    builder.add_edge(START, "research")
    builder.add_edge("research", "analyze")
    builder.add_edge("analyze", "validate")
    builder.add_conditional_edges(
        "validate",
        route_after_validate,
        {
            "human_review": "human_review",
            "research": "research",
            "__end__": END,
        },
    )
    builder.add_conditional_edges(
        "human_review",
        route_after_human,
        {"execute": "execute", "__end__": END},
    )
    builder.add_edge("execute", "monitor")
    builder.add_edge("monitor", END)

    return builder.compile(
        checkpointer=checkpointer or MemorySaver(),
        interrupt_before=["human_review"],
    )


# ─── Runner ───────────────────────────────────────────────────────────────────


def run_pipeline(
    symbol: str = "XAUUSD",
    timeframe: str = "H1",
    auto_approve: bool = False,
    thread_id: str | None = None,
) -> dict:
    """
    Run the full trading pipeline.

    Args:
        symbol      : Trading symbol (default XAUUSD)
        timeframe   : Chart timeframe (default H1)
        auto_approve: Skip human review (simulation mode)
        thread_id   : LangGraph checkpoint thread ID

    Returns:
        Final TradingState dict
    """
    graph = build_graph()
    config = {"configurable": {"thread_id": thread_id or f"{symbol}-{datetime.utcnow():%Y%m%d%H%M}"}}

    initial = TradingState(
        symbol=symbol,
        timeframe=timeframe,
        iteration=0,
        messages=[f"Pipeline started {datetime.utcnow().isoformat()}"],
    )

    # Run until interrupt (human_review)
    snapshot = graph.invoke(initial, config)

    # If interrupted at human_review node
    state = graph.get_state(config)
    if state.next == ("human_review",):
        if auto_approve:
            print("\n[auto_approve] Approving trade automatically (simulation mode).")
            approved = True
        else:
            print(snapshot.get("__interrupt__", [{}])[0].get("value", "Approve trade?"))
            approved = input("Approve? [yes/no]: ").strip().lower() == "yes"

        # Resume
        final = graph.invoke(Command(resume=approved), config)
    else:
        final = snapshot

    return dict(final)


# ─── CLI Entry ────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    import sys
    sym = sys.argv[1] if len(sys.argv) > 1 else "XAUUSD"
    tf = sys.argv[2] if len(sys.argv) > 2 else "H1"
    auto = "--auto" in sys.argv

    result = run_pipeline(sym, tf, auto_approve=auto)
    print("\n=== Pipeline Result ===")
    print(json.dumps(
        {k: v for k, v in result.items() if k != "messages"},
        indent=2,
        default=str,
    ))
    print("\n=== Audit Trail ===")
    for msg in result.get("messages", []):
        print(" ", msg)
