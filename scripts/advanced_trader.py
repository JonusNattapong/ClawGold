"""
Advanced Trading Strategies
===========================
 sophisticated trading algorithms including trailing stops,
grid trading, martingale, and breakout detection.
"""

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from typing import Optional, List, Dict, Tuple, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import time
import json
from pathlib import Path

import MetaTrader5 as mt5_lib
from mt5_manager import MT5Manager
from risk_manager import RiskManager
from logger import get_logger

try:
    from agent_executor import AgentExecutor, AgentTool
    AGENT_AVAILABLE = True
except ImportError:
    AGENT_AVAILABLE = False

logger = get_logger(__name__)


class StrategyType(Enum):
    """Trading strategy types."""
    TRAILING_STOP = "trailing_stop"
    GRID = "grid"
    BREAKOUT = "breakout"
    SCALPING = "scalping"
    MARTINGALE = "martingale"


@dataclass
class TradeLevel:
    """Grid trading level."""
    price: float
    volume: float
    order_type: str  # "buy" or "sell"
    activated: bool = False
    ticket: Optional[int] = None


@dataclass
class TrailingStopConfig:
    """Trailing stop configuration."""
    activation_profit: float = 10.0  # Points to activate
    trailing_distance: float = 5.0   # Points to trail
    step_size: float = 1.0           # Minimum step to move stop


@dataclass
class GridConfig:
    """Grid trading configuration."""
    levels: int = 5
    grid_size: float = 10.0          # Points between levels
    volume_per_level: float = 0.1
    take_profit: float = 20.0
    stop_loss: float = 50.0


@dataclass
class BreakoutConfig:
    """Breakout detection configuration."""
    lookback_period: int = 20
    breakout_threshold: float = 0.5  # Percentage
    volume_multiplier: float = 1.5
    confirmation_bars: int = 2


class AdvancedTrader:
    """
    Advanced trading system with multiple strategies.
    
    Usage:
        trader = AdvancedTrader(config)
        
        # Trailing stop
        trader.apply_trailing_stop(position_ticket, TrailingStopConfig())
        
        # Grid trading
        trader.start_grid_trading(GridConfig(), current_price)
        
        # Breakout detection
        if trader.detect_breakout(symbol, BreakoutConfig()):
            trader.execute_breakout_trade(symbol, "buy")
    """
    
    def __init__(self, config: dict):
        self.config = config
        self.risk_manager = RiskManager(config)
        self.active_strategies: Dict[str, Dict] = {}
        self.trailing_stops: Dict[int, Dict] = {}
        self.grid_levels: List[TradeLevel] = []
        self.running = False

        # AI Agent integration for strategy optimization
        self.agent_executor = None
        if AGENT_AVAILABLE:
            try:
                self.agent_executor = AgentExecutor(config)
            except Exception:
                pass

    def get_ai_strategy_optimization(self, market_data: pd.DataFrame) -> Dict[str, Any]:
        """
        Send recent OHLCV data to AI for real-time strategy adjustment.
        """
        if not self.agent_executor:
            return {}

        # Convert simple data to string for the prompt
        data_summary = market_data.tail(20).to_json()
        
        prompt = f"""
        As an expert gold trader, analyze the following recent OHLCV data (JSON) for XAUUSD.
        Determine the optimal strategy type and parameters.
        
        Data: {data_summary}
        
        Available Strategies: TRAILING_STOP, GRID, BREAKOUT, SCALPING, MARTINGALE
        
        Respond ONLY with a JSON result:
        - "recommended_strategy": string
        - "logic_reasoning": string
        - "confidence": float (0-1)
        - "suggested_parameters": dict (matching the config for the strategy)
        """
        
        try:
            result = self.agent_executor.run_best(prompt, task_name="strategy_optimization")
            if result.get('success'):
                content = result.get('output', '')
                if "```json" in content: content = content.split("```json")[1].split("```")[0].strip()
                return json.loads(content)
        except Exception as e:
            logger.error(f"AI Strategy Optimization failed: {e}")
            
        return {}
    
    def apply_trailing_stop(self, ticket: int, config: TrailingStopConfig) -> bool:
        """
        Apply trailing stop to an existing position.
        
        Args:
            ticket: Position ticket number
            config: Trailing stop configuration
        
        Returns:
            True if trailing stop activated
        """
        with MT5Manager() as mt5:
            positions = mt5.get_positions()
            position = None
            
            for pos in positions:
                if pos['ticket'] == ticket:
                    position = pos
                    break
            
            if not position:
                logger.error(f"Position {ticket} not found")
                return False
            
            # Store trailing stop info
            self.trailing_stops[ticket] = {
                'config': config,
                'highest_profit': 0,
                'current_stop': position.get('sl', 0),
                'position': position
            }
            
            logger.info(f"Trailing stop applied to position {ticket}")
            return True
    
    def update_trailing_stops(self):
        """Update all trailing stops. Call this periodically."""
        with MT5Manager() as mt5:
            for ticket, ts_info in list(self.trailing_stops.items()):
                position = None
                positions = mt5.get_positions()
                
                for pos in positions:
                    if pos['ticket'] == ticket:
                        position = pos
                        break
                
                if not position:
                    # Position closed
                    del self.trailing_stops[ticket]
                    continue
                
                config = ts_info['config']
                current_profit = position['profit']
                
                # Check if activation threshold reached
                if current_profit >= config.activation_profit:
                    if current_profit > ts_info['highest_profit']:
                        ts_info['highest_profit'] = current_profit
                        
                        # Calculate new stop loss
                        if position['type'] == 0:  # BUY
                            new_stop = position['price_open'] + (current_profit - config.trailing_distance)
                            if new_stop > ts_info['current_stop']:
                                self._modify_stop_loss(mt5, ticket, new_stop)
                                ts_info['current_stop'] = new_stop
                        else:  # SELL
                            new_stop = position['price_open'] - (current_profit - config.trailing_distance)
                            if new_stop < ts_info['current_stop'] or ts_info['current_stop'] == 0:
                                self._modify_stop_loss(mt5, ticket, new_stop)
                                ts_info['current_stop'] = new_stop
    
    def _modify_stop_loss(self, mt5, ticket: int, new_sl: float):
        """Modify position stop loss."""
        request = {
            'action': mt5_lib.TRADE_ACTION_SLTP,
            'position': ticket,
            'sl': new_sl,
            'tp': 0  # Keep existing TP
        }
        
        result = mt5.order_send(request)
        if result and result.retcode == mt5_lib.TRADE_RETCODE_DONE:
            logger.info(f"Updated stop loss for {ticket} to {new_sl}")
        else:
            logger.error(f"Failed to update stop loss: {result}")
    
    def start_grid_trading(self, config: GridConfig, center_price: float, 
                           direction: str = "both") -> List[TradeLevel]:
        """
        Initialize grid trading levels.
        
        Args:
            config: Grid configuration
            center_price: Center price for grid
            direction: "buy", "sell", or "both"
        
        Returns:
            List of trade levels
        """
        self.grid_levels = []
        
        if direction in ["buy", "both"]:
            for i in range(config.levels):
                level_price = center_price - (config.grid_size * (i + 1))
                level = TradeLevel(
                    price=level_price,
                    volume=config.volume_per_level,
                    order_type="buy"
                )
                self.grid_levels.append(level)
        
        if direction in ["sell", "both"]:
            for i in range(config.levels):
                level_price = center_price + (config.grid_size * (i + 1))
                level = TradeLevel(
                    price=level_price,
                    volume=config.volume_per_level,
                    order_type="sell"
                )
                self.grid_levels.append(level)
        
        logger.info(f"Grid trading initialized with {len(self.grid_levels)} levels")
        return self.grid_levels
    
    def execute_grid_orders(self):
        """Execute pending grid orders based on current price."""
        with MT5Manager() as mt5:
            symbol = self.config['trading']['symbol']
            tick = mt5.get_tick(symbol)
            
            if not tick:
                return
            
            current_price = tick['bid']
            
            for level in self.grid_levels:
                if level.activated:
                    continue
                
                # Check if price reached level
                if level.order_type == "buy" and current_price <= level.price:
                    result = mt5.execute_trade("BUY", level.volume)
                    if result['success']:
                        level.activated = True
                        level.ticket = result['order']
                        logger.info(f"Grid buy order executed at {level.price}")
                
                elif level.order_type == "sell" and current_price >= level.price:
                    result = mt5.execute_trade("SELL", level.volume)
                    if result['success']:
                        level.activated = True
                        level.ticket = result['order']
                        logger.info(f"Grid sell order executed at {level.price}")
    
    def detect_breakout(self, symbol: str, config: BreakoutConfig) -> Tuple[bool, str]:
        """
        Detect price breakout patterns.
        
        Args:
            symbol: Trading symbol
            config: Breakout configuration
        
        Returns:
            Tuple of (is_breakout, direction)
        """
        with MT5Manager() as mt5:
            rates = mt5.get_rates(symbol, mt5_lib.TIMEFRAME_H1, config.lookback_period + 10)
            
            if not rates or len(rates) < config.lookback_period:
                return False, ""
            
            df = pd.DataFrame(rates)
            
            # Calculate support and resistance
            high = df['high'].max()
            low = df['low'].min()
            range_size = high - low
            
            # Current price
            current = df['close'].iloc[-1]
            current_high = df['high'].iloc[-1]
            current_low = df['low'].iloc[-1]
            
            # Volume check
            avg_volume = df['tick_volume'].mean()
            current_volume = df['tick_volume'].iloc[-1]
            
            volume_ok = current_volume >= avg_volume * config.volume_multiplier
            
            # Check for breakout
            breakout_up = current_high > high * (1 - config.breakout_threshold / 100)
            breakout_down = current_low < low * (1 + config.breakout_threshold / 100)
            
            # Confirmation bars
            if breakout_up and volume_ok:
                # Check confirmation
                confirm_count = 0
                for i in range(1, min(config.confirmation_bars + 1, len(df))):
                    if df['close'].iloc[-i] > high * 0.995:
                        confirm_count += 1
                
                if confirm_count >= config.confirmation_bars - 1:
                    logger.info(f"Breakout UP detected on {symbol}")
                    return True, "buy"
            
            if breakout_down and volume_ok:
                confirm_count = 0
                for i in range(1, min(config.confirmation_bars + 1, len(df))):
                    if df['close'].iloc[-i] < low * 1.005:
                        confirm_count += 1
                
                if confirm_count >= config.confirmation_bars - 1:
                    logger.info(f"Breakout DOWN detected on {symbol}")
                    return True, "sell"
            
            return False, ""
    
    def execute_breakout_trade(self, symbol: str, direction: str, 
                               volume: float = 0.1) -> Dict:
        """Execute breakout trade with risk management."""
        with MT5Manager() as mt5:
            # Validate with risk manager
            can_trade, reason = self.risk_manager.can_trade(symbol, direction, volume)
            
            if not can_trade:
                logger.warning(f"Breakout trade rejected: {reason}")
                return {'success': False, 'error': reason}
            
            # Execute trade
            result = mt5.execute_trade(direction.upper(), volume)
            
            if result['success']:
                # Apply trailing stop
                self.apply_trailing_stop(
                    result['order'],
                    TrailingStopConfig(activation_profit=15, trailing_distance=10)
                )
                
                logger.info(f"Breakout {direction} trade executed: {result}")
            
            return result
    
    def run_scalping_strategy(self, symbol: str, duration_minutes: int = 30,
                              profit_target: float = 5.0, 
                              max_loss: float = 3.0) -> Dict:
        """
        Run scalping strategy for specified duration.
        
        Args:
            symbol: Trading symbol
            duration_minutes: How long to run
            profit_target: Profit target in points
            max_loss: Maximum loss in points
        
        Returns:
            Trading results summary
        """
        logger.info(f"Starting scalping strategy for {duration_minutes} minutes")
        
        start_time = datetime.now()
        trades = []
        total_profit = 0
        
        with MT5Manager() as mt5:
            while (datetime.now() - start_time).seconds < duration_minutes * 60:
                tick = mt5.get_tick(symbol)
                if not tick:
                    time.sleep(1)
                    continue
                
                # Simple scalping logic based on spread
                spread = tick['ask'] - tick['bid']
                
                if spread < 0.5:  # Low spread opportunity
                    # Check for quick momentum
                    rates = mt5.get_rates(symbol, mt5_lib.TIMEFRAME_M1, 3)
                    if rates and len(rates) >= 3:
                        momentum = rates[-1]['close'] - rates[-3]['open']
                        
                        if momentum > 0.2:  # Upward momentum
                            result = mt5.execute_trade("BUY", 0.01)
                            if result['success']:
                                trades.append(result)
                        elif momentum < -0.2:  # Downward momentum
                            result = mt5.execute_trade("SELL", 0.01)
                            if result['success']:
                                trades.append(result)
                
                # Check profit/loss limits
                positions = mt5.get_positions(symbol)
                current_pnl = sum(p['profit'] for p in positions)
                
                if current_pnl >= profit_target or current_pnl <= -max_loss:
                    # Close all positions
                    for pos in positions:
                        mt5.close_position(pos['ticket'])
                    total_profit += current_pnl
                    break
                
                time.sleep(5)
        
        return {
            'trades_executed': len(trades),
            'total_profit': total_profit,
            'duration': duration_minutes
        }
    
    def multi_timeframe_analysis(self, symbol: str) -> Dict:
        """
        Analyze multiple timeframes for confluence.
        
        Returns:
            Analysis results with trend alignment score
        """
        with MT5Manager() as mt5:
            timeframes = [
                (mt5_lib.TIMEFRAME_M15, "M15"),
                (mt5_lib.TIMEFRAME_H1, "H1"),
                (mt5_lib.TIMEFRAME_H4, "H4"),
                (mt5_lib.TIMEFRAME_D1, "D1")
            ]
            
            signals = {}
            
            for tf, name in timeframes:
                rates = mt5.get_rates(symbol, tf, 50)
                if rates is None or len(rates) == 0:
                    continue
                
                df = pd.DataFrame(rates)
                
                # Calculate EMAs
                df['ema_20'] = df['close'].ewm(span=20).mean()
                df['ema_50'] = df['close'].ewm(span=50).mean()
                
                current = df.iloc[-1]
                
                # Determine signal
                if current['close'] > current['ema_20'] > current['ema_50']:
                    signal = "bullish"
                elif current['close'] < current['ema_20'] < current['ema_50']:
                    signal = "bearish"
                else:
                    signal = "neutral"
                
                signals[name] = {
                    'signal': signal,
                    'price': current['close'],
                    'ema_20': current['ema_20'],
                    'ema_50': current['ema_50']
                }
            
            # Calculate confluence score
            bullish_count = sum(1 for s in signals.values() if s['signal'] == 'bullish')
            bearish_count = sum(1 for s in signals.values() if s['signal'] == 'bearish')
            
            if bullish_count >= 3:
                overall = "strong_buy"
            elif bullish_count >= 2:
                overall = "buy"
            elif bearish_count >= 3:
                overall = "strong_sell"
            elif bearish_count >= 2:
                overall = "sell"
            else:
                overall = "neutral"
            
            return {
                'timeframes': signals,
                'overall_signal': overall,
                'confluence_score': (bullish_count - bearish_count) / len(signals) if signals else 0
            }
