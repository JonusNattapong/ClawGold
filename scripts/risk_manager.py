"""
Risk Manager
============
Manages trading risk limits and validates trades against risk rules.
"""

from typing import Tuple, Optional, Any, Dict
from dataclasses import dataclass
from logger import get_logger

try:
    from agent_executor import AgentExecutor
    AGENT_AVAILABLE = True
except ImportError:
    AGENT_AVAILABLE = False

logger = get_logger(__name__)


@dataclass
class RiskLimits:
    """Risk limit configuration."""
    max_positions: int = 5
    max_daily_loss: float = 500.0  # USD
    max_position_size: float = 1.0  # lots
    max_total_risk: float = 0.05  # 5% of account
    min_margin_level: float = 100.0  # %


class RiskManager:
    """
    Manages trading risk and validates trades.
    
    Usage:
        rm = RiskManager(config)
        can_trade, reason = rm.can_trade('XAUUSD', 'BUY', 0.1)
        if not can_trade:
            print(f"Trade rejected: {reason}")
    """
    
    def __init__(self, config: dict):
        self.config = config
        self.limits = RiskLimits()
        self._load_limits()
        
        # Initialize AI Agent support for dynamic risk adjustment
        self.agent_executor = None
        if AGENT_AVAILABLE:
            try:
                self.agent_executor = AgentExecutor(config)
            except Exception:
                pass

    def get_dynamic_risk_recommendation(self, market_context: str) -> Dict[str, Any]:
        """
        Ask AI to recommend risk parameters based on market context (macro/volatility).
        """
        if not self.agent_executor:
            return {"multiplier": 1.0, "reason": "AI not available"}
            
        prompt = f"""
        Analyze current XAUUSD market context and recommend a risk multiplier (0.5 to 1.5).
        If the market is high-risk (macro events, extreme volatility), reduce risk (< 1.0).
        If the market is stable/trending with clear signals, maintain or slightly increase risk.
        
        Market Context: {market_context}
        
        Respond ONLY with a JSON object:
        - "risk_multiplier": float (e.g. 0.8)
        - "max_position_size_override": float or null
        - "daily_loss_limit_adjustment": float (USD)
        - "reasoning": string
        """
        
        try:
            result = self.agent_executor.run_best(prompt, task_name="risk_optimization")
            if result.get('success'):
                # Extract JSON logic simplified for brevity here, mirroring sentiment_analyzer pattern
                import json
                content = result.get('output', '')
                if "```json" in content: content = content.split("```json")[1].split("```")[0].strip()
                data = json.loads(content)
                return data
        except Exception as e:
            logger.error(f"Failed to get AI risk recommendation: {e}")
            
        return {"multiplier": 1.0, "reason": "Fallback to static limits"}
    
    def _load_limits(self):
        """Load risk limits from config."""
        risk_config = self.config.get('risk', {})
        self.limits.max_positions = risk_config.get('max_positions', 5)
        self.limits.max_daily_loss = risk_config.get('max_daily_loss', 500.0)
        self.limits.max_position_size = risk_config.get('max_position_size', 1.0)
        self.limits.max_total_risk = risk_config.get('max_total_risk', 0.05)
        self.limits.min_margin_level = risk_config.get('min_margin_level', 100.0)
    
    def can_trade(self, symbol: str, action: str, volume: float,
                  account_info: dict = None, positions: list = None) -> Tuple[bool, str]:
        """
        Check if a trade should be allowed based on risk rules.
        
        Args:
            symbol: Trading symbol
            action: BUY or SELL
            volume: Trade volume in lots
            account_info: Current account information
            positions: List of current positions
        
        Returns:
            Tuple of (allowed: bool, reason: str)
        """
        # Check position size limit
        if volume > self.limits.max_position_size:
            return False, f"Volume {volume} exceeds max position size {self.limits.max_position_size}"
        
        # Check number of positions
        if positions and len(positions) >= self.limits.max_positions:
            return False, f"Max positions ({self.limits.max_positions}) reached"
        
        # Check margin level if account info provided
        if account_info:
            margin_level = account_info.get('margin_level', 0)
            if margin_level < self.limits.min_margin_level:
                return False, f"Margin level {margin_level:.2f}% below minimum {self.limits.min_margin_level}%"
        
        # Calculate risk for this trade
        risk_per_trade = self.config['trading'].get('risk_per_trade', 0.01)
        
        if account_info:
            balance = account_info.get('balance', 0)
            max_risk_amount = balance * risk_per_trade
            
            # Estimate trade risk (simplified: 1% move = $10 per 0.01 lot for XAUUSD)
            # Actually 1 lot XAUUSD ≈ $100 per $1 move
            # So 0.1 lot = $10 per $1 move
            estimated_risk = volume * 100  # Simplified risk estimate
            
            if estimated_risk > max_risk_amount:
                return False, f"Estimated risk ${estimated_risk:.2f} exceeds max ${max_risk_amount:.2f}"
        
        logger.info(f"Trade validated: {action} {volume} lots {symbol}")
        return True, "OK"
    
    def calculate_position_size(self, account_balance: float, 
                                 stop_loss_pips: float = 50) -> float:
        """
        Calculate recommended position size based on risk.
        
        Args:
            account_balance: Current account balance
            stop_loss_pips: Stop loss distance in pips
        
        Returns:
            Recommended volume in lots
        """
        risk_per_trade = self.config['trading'].get('risk_per_trade', 0.01)
        risk_amount = account_balance * risk_per_trade
        
        # XAUUSD: 1 pip = $0.01 for 1 lot
        # So for stop_loss_pips, risk per lot = stop_loss_pips * $10
        # (1 pip = $0.01, but in MT5 XAUUSD 1 pip is usually 0.01 = $1 for 0.01 lot)
        # Simplified: $1 per pip for 0.1 lot
        risk_per_lot = stop_loss_pips * 10  # $10 per pip for 1 lot
        
        if risk_per_lot == 0:
            return 0.01
        
        volume = risk_amount / risk_per_lot
        
        # Round to 2 decimal places
        volume = round(volume, 2)
        
        # Enforce limits
        volume = min(volume, self.limits.max_position_size)
        volume = max(volume, 0.01)  # Minimum 0.01 lot
        
        return volume
    
    def check_daily_loss(self, daily_pnl: float) -> Tuple[bool, str]:
        """
        Check if daily loss limit has been reached.
        
        Args:
            daily_pnl: Current daily profit/loss
        
        Returns:
            Tuple of (can_continue: bool, reason: str)
        """
        if daily_pnl < -self.limits.max_daily_loss:
            return False, f"Daily loss limit reached: ${abs(daily_pnl):.2f}"
        
        return True, "OK"
    
    def get_risk_summary(self, account_info: dict, positions: list) -> dict:
        """
        Generate risk summary for display.
        
        Args:
            account_info: Current account information
            positions: List of current positions
        
        Returns:
            Dictionary with risk metrics
        """
        balance = account_info.get('balance', 0)
        equity = account_info.get('equity', 0)
        margin = account_info.get('margin', 0)
        profit = account_info.get('profit', 0)
        margin_level = account_info.get('margin_level', 0)
        
        total_exposure = sum(p.get('volume', 0) for p in positions)
        
        return {
            'balance': balance,
            'equity': equity,
            'margin_used': margin,
            'margin_level': margin_level,
            'unrealized_pnl': profit,
            'total_positions': len(positions),
            'total_exposure': total_exposure,
            'risk_per_trade_pct': self.config['trading'].get('risk_per_trade', 0.01) * 100,
            'daily_loss_limit': self.limits.max_daily_loss,
            'max_position_size': self.limits.max_position_size,
            'margin_status': 'SAFE' if margin_level > 150 else 'WARNING' if margin_level > 100 else 'DANGER'
        }
