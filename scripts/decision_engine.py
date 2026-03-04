"""
Decision Engine Module
======================
Intelligent decision making system that analyzes data from all modules
and makes optimal trading decisions.

Usage:
    from decision_engine import DecisionEngine, Decision
    
    engine = DecisionEngine()
    decision = engine.evaluate_trade_opportunity(
        signal=ai_signal,
        market_condition=market_state,
        economic_events=calendar_events,
        account_state=account_info
    )
    
    if decision.action == "EXECUTE":
        execute_trade(decision.parameters)
"""

import json
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from logger import get_logger

try:
    from agent_executor import AgentExecutor
    from sub_agent import SubAgentOrchestrator
    AGENT_AVAILABLE = True
except ImportError:
    AGENT_AVAILABLE = False

logger = get_logger(__name__)


class DecisionAction(Enum):
    """Possible decision actions."""
    EXECUTE = "execute"
    WAIT = "wait"
    SKIP = "skip"
    MODIFY = "modify"
    CLOSE = "close"
    REVERSE = "reverse"


@dataclass
class Decision:
    """Decision data structure."""
    action: DecisionAction
    confidence: float  # 0.0 to 1.0
    reason: str
    parameters: Dict[str, Any]
    risk_score: float  # 0.0 to 1.0, higher is riskier
    expected_outcome: str
    alternatives: List[str]
    timestamp: datetime


class DecisionEngine:
    """
    Intelligent decision engine for trading operations.
    
    Considers:
    - Market conditions
    - Economic calendar events
    - Account state and risk limits
    - Recent trade performance
    - News sentiment
    - AI signals
    """
    
    # Decision thresholds
    MIN_CONFIDENCE = 0.6
    MAX_RISK_SCORE = 0.7
    MIN_PROFIT_PROBABILITY = 0.55
    
    # Risk multipliers by condition
    RISK_MULTIPLIERS = {
        'high_impact_news_approaching': 0.5,
        'weekend': 0.3,
        'low_liquidity': 0.6,
        'high_volatility': 0.7,
        'trending': 1.0,
        'ranging': 0.8,
        'normal': 1.0
    }
    
    def __init__(self):
        """Initialize decision engine."""
        self.decision_history: List[Decision] = []
        self.rules = self._load_rules()
        
        # Initialize AI Orchestrator for complex validation
        self.orchestrator = None
        if AGENT_AVAILABLE:
            try:
                self.orchestrator = SubAgentOrchestrator()
            except Exception:
                pass
        
        logger.info("DecisionEngine initialized with AI Orchestrator")
    
    def validate_with_ai_consensus(self, signal: Dict[str, Any], market_context: str) -> bool:
        """
        Validate a technical signal using AI Consensus (OpenCode, Gemini, etc.)
        This replaces the simple threshold check with deep reasoning.
        """
        if not self.orchestrator:
            return True # If AI is down, let existing logic handle it
            
        print(f"DEBUG: Running AI Consensus for {signal.get('direction')} signal...")
        
        # We use the Analyst role to synthesize a consensus
        consensus = self.orchestrator.get_consensus(
            f"Validate this {signal.get('direction')} signal for XAUUSD. Signal data: {json.dumps(signal)}"
        )
        
        if consensus.get('combined_sentiment') == 'neutral':
            logger.info("AI Consensus: NEUTRAL - Skipping trade")
            return False
            
        # Ensure direction matches
        ai_dir = consensus.get('combined_sentiment', '').upper()
        if ai_dir != signal.get('direction', '').upper():
            logger.warning(f"AI Consensus ({ai_dir}) DISAGREES with technical signal ({signal.get('direction')})")
            return False
            
        return True
    
    def _load_rules(self) -> Dict[str, Any]:
        """Load decision rules."""
        return {
            'entry': {
                'min_confidence': 0.6,
                'max_daily_loss': 500,
                'max_positions': 5,
                'min_time_between_trades': 300  # 5 minutes
            },
            'exit': {
                'trailing_activation': 0.5,  # % profit to activate trailing
                'breakeven_activation': 0.3,  # % profit to move to breakeven
            },
            'risk': {
                'max_risk_per_trade': 0.02,
                'max_correlated_positions': 2,
                'news_buffer_minutes': 30
            }
        }
    
    def evaluate_trade_opportunity(self,
                                   signal: Dict[str, Any],
                                   market_data: Optional[Dict] = None,
                                   account_data: Optional[Dict] = None) -> Decision:
        """
        Evaluate a trade opportunity and make a decision.
        
        Args:
            signal: Trading signal from AI or strategy
            market_data: Current market conditions
            account_data: Account state
            
        Returns:
            Decision object with action and parameters
        """
        logger.info("Evaluating trade opportunity...")
        
        factors = []
        confidence = signal.get('confidence', 0.5)
        risk_score = 0.3  # Base risk
        
        # Factor 1: Signal Quality
        signal_direction = signal.get('direction', 'neutral')
        signal_strength = signal.get('strength', 1)
        
        if confidence < self.MIN_CONFIDENCE:
            return self._create_decision(
                DecisionAction.SKIP,
                confidence,
                "Signal confidence too low",
                risk_score,
                ["Wait for higher confidence signal"]
            )
        
        factors.append(f"Signal confidence: {confidence:.1%}")
        
        # Factor 2: Market Condition Check
        if market_data:
            condition = market_data.get('condition', 'normal')
            volatility = market_data.get('volatility', 0)
            
            if volatility > 0.5:  # High volatility
                risk_score += 0.2
                factors.append("High volatility detected")
            
            if condition in ['volatile', 'choppy']:
                confidence *= 0.8
                factors.append("Unfavorable market condition")
        
        # Factor 3: Economic Calendar Check
        if self._is_high_impact_event_approaching():
            risk_score += 0.3
            confidence *= 0.7
            factors.append("High impact event approaching")
        
        # Factor 4: Account State
        if account_data:
            daily_pnl = account_data.get('daily_pnl', 0)
            max_daily_loss = self.rules['entry']['max_daily_loss']
            
            if daily_pnl < -max_daily_loss:
                return self._create_decision(
                    DecisionAction.SKIP,
                    confidence,
                    "Daily loss limit reached",
                    risk_score,
                    ["Stop trading for today"]
                )
            
            open_positions = account_data.get('open_positions', 0)
            max_positions = self.rules['entry']['max_positions']
            
            if open_positions >= max_positions:
                return self._create_decision(
                    DecisionAction.SKIP,
                    confidence,
                    "Maximum positions reached",
                    risk_score,
                    ["Close existing positions first"]
                )
            
            if open_positions > 0:
                # Check correlation
                existing_direction = self._get_existing_position_direction()
                if existing_direction == signal_direction:
                    risk_score += 0.1
                    factors.append("Adding to existing position")
        
        # Factor 5: Recent Performance
        recent_performance = self._get_recent_performance()
        if recent_performance and recent_performance['win_rate'] < 0.4:
            confidence *= 0.8
            factors.append("Recent performance below threshold")
        
        # Factor 6: Time-based Rules
        if self._is_low_liquidity_time():
            risk_score += 0.15
            factors.append("Low liquidity period")
        
        # Final Decision
        if risk_score > self.MAX_RISK_SCORE:
            return self._create_decision(
                DecisionAction.WAIT,
                confidence,
                f"Risk score too high: {risk_score:.2f}",
                risk_score,
                factors
            )
        
        if confidence >= self.MIN_CONFIDENCE and risk_score <= self.MAX_RISK_SCORE:
            # Determine optimal parameters
            params = self._calculate_optimal_parameters(
                signal, market_data, risk_score
            )
            
            return self._create_decision(
                DecisionAction.EXECUTE,
                confidence,
                f"Favorable conditions - {signal_direction.upper()} signal",
                risk_score,
                factors,
                params
            )
        
        return self._create_decision(
            DecisionAction.WAIT,
            confidence,
            "Conditions not optimal",
            risk_score,
            factors
        )
    
    def evaluate_exit(self,
                     position: Dict[str, Any],
                     current_price: float,
                     market_data: Optional[Dict] = None) -> Decision:
        """
        Evaluate whether to close a position.
        
        Args:
            position: Current position data
            current_price: Current market price
            market_data: Market conditions
            
        Returns:
            Decision for exit action
        """
        entry_price = position.get('entry_price', 0)
        action = position.get('action', 'BUY')
        open_pnl = position.get('pnl', 0)
        
        # Calculate profit percentage
        if action == 'BUY':
            profit_pct = (current_price - entry_price) / entry_price
        else:
            profit_pct = (entry_price - current_price) / entry_price
        
        factors = []
        
        # Check trailing stop activation
        trailing_activation = self.rules['exit']['trailing_activation']
        if profit_pct >= trailing_activation:
            return self._create_decision(
                DecisionAction.MODIFY,
                0.8,
                f"Activate trailing stop at {profit_pct:.1%} profit",
                0.3,
                factors,
                {'action': 'activate_trailing', 'profit_pct': profit_pct}
            )
        
        # Check breakeven activation
        breakeven_activation = self.rules['exit']['breakeven_activation']
        if profit_pct >= breakeven_activation:
            return self._create_decision(
                DecisionAction.MODIFY,
                0.7,
                f"Move stop to breakeven at {profit_pct:.1%} profit",
                0.2,
                factors,
                {'action': 'move_breakeven'}
            )
        
        # Check market reversal
        if market_data:
            trend = market_data.get('trend', 'neutral')
            if (action == 'BUY' and trend == 'bearish') or (action == 'SELL' and trend == 'bullish'):
                return self._create_decision(
                    DecisionAction.CLOSE,
                    0.6,
                    "Market trend reversal detected",
                    0.4,
                    factors + ["Trend against position"]
                )
        
        # Hold position
        return self._create_decision(
            DecisionAction.WAIT,
            0.5,
            f"Hold position - PnL: {open_pnl:.2f} ({profit_pct:.2%})",
            0.5,
            factors
        )
    
    def _create_decision(self,
                        action: DecisionAction,
                        confidence: float,
                        reason: str,
                        risk_score: float,
                        factors: List[str],
                        parameters: Optional[Dict] = None) -> Decision:
        """Create a decision object."""
        decision = Decision(
            action=action,
            confidence=confidence,
            reason=reason,
            parameters=parameters or {},
            risk_score=risk_score,
            expected_outcome=self._predict_outcome(action, confidence, risk_score),
            alternatives=self._generate_alternatives(action, factors),
            timestamp=datetime.now()
        )
        
        # Store in history
        self.decision_history.append(decision)
        if len(self.decision_history) > 100:
            self.decision_history = self.decision_history[-100:]
        
        logger.info(f"Decision: {action.value} - {reason} (confidence: {confidence:.1%})")
        
        return decision
    
    def _calculate_optimal_parameters(self,
                                     signal: Dict[str, Any],
                                     market_data: Optional[Dict],
                                     risk_score: float) -> Dict[str, Any]:
        """Calculate optimal trade parameters."""
        params = {
            'direction': signal.get('direction', 'buy'),
            'volume': self._calculate_position_size(risk_score),
            'entry_price': signal.get('entry_price'),
            'stop_loss': signal.get('stop_loss'),
            'take_profit': signal.get('take_profit'),
            'trailing_stop': False,
            'strategy': signal.get('strategy', 'ai_signal')
        }
        
        # Adjust for market conditions
        if market_data:
            volatility = market_data.get('volatility', 0)
            if volatility > 0.3:
                # Wider stops in volatile markets
                if params['stop_loss']:
                    params['stop_loss'] *= 1.5
                if params['take_profit']:
                    params['take_profit'] *= 1.5
        
        return params
    
    def _calculate_position_size(self, risk_score: float) -> float:
        """Calculate optimal position size based on risk."""
        base_size = 0.1  # Base lot size
        max_risk = self.rules['risk']['max_risk_per_trade']
        
        # Reduce size for higher risk
        risk_factor = 1 - (risk_score * 0.5)
        
        return round(base_size * risk_factor, 2)
    
    def _is_high_impact_event_approaching(self) -> bool:
        """Check if high impact event is approaching."""
        try:
            from economic_calendar import EconomicCalendar
            calendar = EconomicCalendar()
            events = calendar.get_upcoming_high_impact_events(minutes=60)
            return len(events) > 0
        except:
            return False
    
    def _is_low_liquidity_time(self) -> bool:
        """Check if current time is low liquidity."""
        now = datetime.now()
        hour = now.hour
        
        # Low liquidity: weekends, late Friday, early Monday, major holidays
        if now.weekday() >= 5:  # Weekend
            return True
        if hour < 5 or hour > 22:
            return True
        
        return False
    
    def _get_existing_position_direction(self) -> Optional[str]:
        """Get direction of existing positions."""
        if not self.state:
            return None
        
        positions = self.state.get_all_positions()
        if positions:
            return positions[0].action
        return None
    
    def _get_recent_performance(self) -> Optional[Dict[str, Any]]:
        """Get recent trading performance."""
        # This would integrate with trade journal
        return None
    
    def _predict_outcome(self, action: DecisionAction, 
                        confidence: float, risk_score: float) -> str:
        """Predict expected outcome of decision."""
        if action == DecisionAction.EXECUTE:
            expected_return = confidence * (1 - risk_score)
            if expected_return > 0.5:
                return f"Positive expected return: {expected_return:.1%}"
            else:
                return f"Moderate expected return: {expected_return:.1%}"
        elif action == DecisionAction.SKIP:
            return "Avoiding potential loss"
        elif action == DecisionAction.WAIT:
            return "Awaiting better conditions"
        else:
            return "Managing risk"
    
    def _generate_alternatives(self, action: DecisionAction, 
                              factors: List[str]) -> List[str]:
        """Generate alternative actions."""
        alternatives = []
        
        if action == DecisionAction.SKIP:
            alternatives.append("Wait for next signal")
            alternatives.append("Reduce position size")
            alternatives.append("Widen stop loss")
        elif action == DecisionAction.WAIT:
            alternatives.append("Monitor for 15 minutes")
            alternatives.append("Set price alert")
        elif action == DecisionAction.EXECUTE:
            alternatives.append("Scale in gradually")
            alternatives.append("Use tighter stop loss")
        
        return alternatives
    
    def get_decision_stats(self) -> Dict[str, Any]:
        """Get decision engine statistics."""
        if not self.decision_history:
            return {}
        
        total = len(self.decision_history)
        actions = {}
        for d in self.decision_history:
            actions[d.action.value] = actions.get(d.action.value, 0) + 1
        
        avg_confidence = sum(d.confidence for d in self.decision_history) / total
        avg_risk = sum(d.risk_score for d in self.decision_history) / total
        
        return {
            'total_decisions': total,
            'action_distribution': actions,
            'average_confidence': avg_confidence,
            'average_risk_score': avg_risk,
            'recent_decisions': [
                {
                    'action': d.action.value,
                    'confidence': d.confidence,
                    'reason': d.reason[:50]
                }
                for d in self.decision_history[-5:]
            ]
        }


if __name__ == "__main__":
    # Test decision engine
    print("Testing DecisionEngine...")
    
    engine = DecisionEngine()
    
    # Test trade evaluation
    signal = {
        'direction': 'buy',
        'confidence': 0.75,
        'strength': 2,
        'entry_price': 2950.0,
        'stop_loss': 2940.0,
        'take_profit': 2970.0,
        'strategy': 'ai_research'
    }
    
    market = {
        'condition': 'trending',
        'volatility': 0.2,
        'trend': 'bullish'
    }
    
    account = {
        'daily_pnl': 100,
        'open_positions': 1
    }
    
    decision = engine.evaluate_trade_opportunity(signal, market, account)
    
    print(f"\nDecision: {decision.action.value}")
    print(f"Confidence: {decision.confidence:.1%}")
    print(f"Risk Score: {decision.risk_score:.2f}")
    print(f"Reason: {decision.reason}")
    print(f"Expected Outcome: {decision.expected_outcome}")
    
    if decision.parameters:
        print(f"\nParameters:")
        for k, v in decision.parameters.items():
            print(f"  {k}: {v}")
    
    print("\nTest completed!")
