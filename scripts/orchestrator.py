"""
Intelligent Orchestrator Module
===============================
Central coordination system that brings all modules together to work
intelligently as a unified trading system.

Usage:
    from orchestrator import TradingOrchestrator
    
    orchestrator = TradingOrchestrator()
    orchestrator.start()
    
    # System now runs autonomously, coordinating all modules
    # - Monitors market conditions
    # - Checks economic calendar
    # - Analyzes news sentiment
    # - Makes intelligent decisions
    # - Executes trades automatically
"""

import threading
import time
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum, auto

from logger import get_logger

# Core imports
try:
    from event_bus import EventBus, EventTypes, subscribe, publish
    from state_manager import StateManager
    from decision_engine import DecisionEngine, DecisionAction
    EVENT_BUS_AVAILABLE = True
except ImportError:
    EVENT_BUS_AVAILABLE = False
    logger = get_logger(__name__)
    logger.warning("EventBus/StateManager not available")

# Module imports
try:
    from economic_calendar import EconomicCalendar
    CALENDAR_AVAILABLE = True
except ImportError:
    CALENDAR_AVAILABLE = False

try:
    from advanced_orders import OrderManager
    ORDERS_AVAILABLE = True
except ImportError:
    ORDERS_AVAILABLE = False

try:
    from adaptive_learning import AdaptiveLearning
    LEARNING_AVAILABLE = True
except ImportError:
    LEARNING_AVAILABLE = False

try:
    from news_aggregator import NewsAggregator
    NEWS_AVAILABLE = True
except ImportError:
    NEWS_AVAILABLE = False

try:
    from mt5_manager import MT5Manager
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False

try:
    from notifier import notify_system, notify_trade
    NOTIFIER_AVAILABLE = True
except ImportError:
    NOTIFIER_AVAILABLE = False

logger = get_logger(__name__)


class SystemMode(Enum):
    """System operation modes."""
    MANUAL = auto()      # Human makes all decisions
    SEMI_AUTO = auto()   # AI suggests, human approves
    AUTO = auto()        # Fully autonomous operation
    PAUSED = auto()      # System paused


@dataclass
class SystemStatus:
    """Current system status."""
    mode: SystemMode
    is_running: bool
    last_update: datetime
    active_modules: List[str]
    errors: List[str]
    performance_score: float


class TradingOrchestrator:
    """
    Intelligent orchestrator that coordinates all trading modules.
    
    Responsibilities:
    1. Initialize and manage all modules
    2. Coordinate data flow between modules
    3. Make intelligent decisions based on all inputs
    4. Execute automated workflows
    5. Monitor system health
    6. Handle errors gracefully
    7. Learn and adapt from performance
    """
    
    def __init__(self, mode: SystemMode = SystemMode.SEMI_AUTO):
        """
        Initialize the orchestrator.
        
        Args:
            mode: System operation mode
        """
        self.mode = mode
        self.status = SystemStatus(
            mode=mode,
            is_running=False,
            last_update=datetime.now(),
            active_modules=[],
            errors=[],
            performance_score=0.5
        )
        
        # Core components
        self.event_bus = EventBus() if EVENT_BUS_AVAILABLE else None
        self.state = StateManager() if EVENT_BUS_AVAILABLE else None
        self.decision_engine = DecisionEngine()
        
        # Module instances
        self.calendar: Optional[EconomicCalendar] = None
        self.order_manager: Optional[Any] = None
        self.learner: Optional[Any] = None
        self.news: Optional[Any] = None
        self.mt5: Optional[Any] = None
        
        # Worker threads
        self._workers: Dict[str, threading.Thread] = {}
        self._stop_event = threading.Event()
        
        # Event handlers
        self._handlers = {}
        
        logger.info(f"TradingOrchestrator initialized in {mode.name} mode")
    
    def start(self):
        """Start the orchestrator and all modules."""
        logger.info("Starting TradingOrchestrator...")
        
        self.status.is_running = True
        self._stop_event.clear()
        
        # Start event bus
        if self.event_bus:
            self.event_bus.start()
            self.status.active_modules.append("event_bus")
        
        # Initialize and start modules
        self._init_modules()
        
        # Register event handlers
        self._register_handlers()
        
        # Start worker threads
        self._start_workers()
        
        # Publish system start event
        self._publish_event(EventTypes.TRADING_RESUMED, {
            'mode': self.mode.name,
            'active_modules': self.status.active_modules
        })
        
        logger.info("TradingOrchestrator started successfully")
        
        if NOTIFIER_AVAILABLE:
            notify_system(
                f"🚀 Trading Orchestrator Started\n"
                f"Mode: {self.mode.name}\n"
                f"Active Modules: {', '.join(self.status.active_modules)}",
                level="info"
            )
    
    def stop(self):
        """Stop the orchestrator and all modules."""
        logger.info("Stopping TradingOrchestrator...")
        
        self._stop_event.set()
        self.status.is_running = False
        
        # Stop worker threads
        for name, thread in self._workers.items():
            thread.join(timeout=5)
            logger.debug(f"Worker {name} stopped")
        
        # Stop event bus
        if self.event_bus:
            self.event_bus.stop()
        
        # Stop order manager monitoring
        if self.order_manager and hasattr(self.order_manager, 'stop_monitoring'):
            self.order_manager.stop_monitoring()
        
        self.status.active_modules = []
        
        logger.info("TradingOrchestrator stopped")
        
        if NOTIFIER_AVAILABLE:
            notify_system("Trading Orchestrator Stopped", level="info")
    
    def _init_modules(self):
        """Initialize all trading modules."""
        # Economic Calendar
        if CALENDAR_AVAILABLE:
            try:
                self.calendar = EconomicCalendar()
                self.status.active_modules.append("economic_calendar")
                logger.info("EconomicCalendar initialized")
            except Exception as e:
                logger.error(f"Failed to initialize EconomicCalendar: {e}")
        
        # Order Manager
        if ORDERS_AVAILABLE:
            try:
                self.order_manager = OrderManager()
                self.status.active_modules.append("order_manager")
                logger.info("OrderManager initialized")
            except Exception as e:
                logger.error(f"Failed to initialize OrderManager: {e}")
        
        # Adaptive Learning
        if LEARNING_AVAILABLE:
            try:
                self.learner = AdaptiveLearning()
                self.status.active_modules.append("adaptive_learning")
                logger.info("AdaptiveLearning initialized")
            except Exception as e:
                logger.error(f"Failed to initialize AdaptiveLearning: {e}")
        
        # News Aggregator
        if NEWS_AVAILABLE:
            try:
                self.news = NewsAggregator()
                self.status.active_modules.append("news_aggregator")
                logger.info("NewsAggregator initialized")
            except Exception as e:
                logger.error(f"Failed to initialize NewsAggregator: {e}")
    
    def _register_handlers(self):
        """Register event handlers."""
        if not self.event_bus:
            return
        
        handlers = {
            EventTypes.TRADE_EXECUTED: self._on_trade_executed,
            EventTypes.TRADE_CLOSED: self._on_trade_closed,
            EventTypes.SIGNAL_GENERATED: self._on_signal_generated,
            EventTypes.MARKET_CONDITION_CHANGED: self._on_market_condition_changed,
            EventTypes.ECONOMIC_EVENT_UPCOMING: self._on_economic_event,
            EventTypes.ERROR_OCCURRED: self._on_error,
        }
        
        for event_type, handler in handlers.items():
            subscribe(event_type, handler)
            self._handlers[event_type] = handler
    
    def _start_workers(self):
        """Start background worker threads."""
        workers = {
            'market_monitor': self._market_monitor_worker,
            'decision_loop': self._decision_loop_worker,
            'learning_loop': self._learning_loop_worker,
            'health_check': self._health_check_worker,
        }
        
        for name, target in workers.items():
            thread = threading.Thread(target=target, name=name, daemon=True)
            thread.start()
            self._workers[name] = thread
            logger.info(f"Started worker: {name}")
    
    # Worker Threads
    def _market_monitor_worker(self):
        """Monitor market conditions and publish updates."""
        while not self._stop_event.is_set():
            try:
                if self.state and MT5_AVAILABLE:
                    # Update market data
                    with MT5Manager() as mt5:
                        symbol = mt5.config.get('trading', {}).get('symbol', 'XAUUSD')
                        tick = mt5.get_tick(symbol)
                        
                        if tick:
                            self.state.update_market_data(symbol, {
                                'bid': tick['bid'],
                                'ask': tick['ask'],
                                'spread': tick['ask'] - tick['bid'],
                                'timestamp': datetime.now().isoformat()
                            })
                
                # Check economic calendar
                if self.calendar:
                    if self.calendar.should_pause_trading():
                        if self.state and self.state.is_trading_enabled():
                            self.state.disable_trading("High impact event approaching")
                            self._publish_event(EventTypes.TRADING_PAUSED, {
                                'reason': 'economic_event',
                                'resume_time': self.calendar.pause_until.isoformat() if self.calendar.pause_until else None
                            })
                    else:
                        if self.state and not self.state.is_trading_enabled():
                            self.state.enable_trading("High impact event passed")
                            self._publish_event(EventTypes.TRADING_RESUMED, {
                                'reason': 'economic_event_ended'
                            })
                
                time.sleep(5)  # Check every 5 seconds
                
            except Exception as e:
                logger.error(f"Error in market monitor: {e}")
                time.sleep(10)
    
    def _decision_loop_worker(self):
        """Main decision making loop."""
        while not self._stop_event.is_set():
            try:
                if self.mode == SystemMode.MANUAL:
                    time.sleep(10)
                    continue
                
                if self.state and not self.state.is_trading_enabled():
                    logger.debug("Trading disabled, skipping decision loop")
                    time.sleep(30)
                    continue
                
                # Get latest data
                symbol = 'XAUUSD'
                market_data = self._get_market_data(symbol)
                account_data = self._get_account_data()
                
                # Check for news signals
                if self.news:
                    signal = self._check_news_signal(symbol)
                    if signal:
                        decision = self.decision_engine.evaluate_trade_opportunity(
                            signal, market_data, account_data
                        )
                        
                        if decision.action == DecisionAction.EXECUTE:
                            if self.mode == SystemMode.AUTO:
                                self._execute_decision(decision)
                            elif self.mode == SystemMode.SEMI_AUTO:
                                self._notify_decision(decision)
                
                # Check existing positions for exits
                if self.state:
                    positions = self.state.get_all_positions()
                    for position in positions:
                        current_price = self._get_current_price(position.symbol)
                        if current_price:
                            decision = self.decision_engine.evaluate_exit(
                                position.__dict__, current_price, market_data
                            )
                            
                            if decision.action in [DecisionAction.CLOSE, DecisionAction.MODIFY]:
                                self._execute_exit_decision(position, decision)
                
                time.sleep(10)  # Decision interval
                
            except Exception as e:
                logger.error(f"Error in decision loop: {e}")
                time.sleep(30)
    
    def _learning_loop_worker(self):
        """Continuous learning and adaptation loop."""
        while not self._stop_event.is_set():
            try:
                if self.learner:
                    # Analyze performance periodically
                    analysis = self.learner.analyze_performance(days=7)
                    
                    if 'error' not in analysis:
                        win_rate = analysis.get('win_rate', 0)
                        
                        # Adapt parameters based on performance
                        if win_rate < 0.4:
                            logger.warning("Low win rate detected - adjusting strategy")
                            self._publish_event(EventTypes.PARAMETERS_UPDATED, {
                                'reason': 'poor_performance',
                                'win_rate': win_rate
                            })
                        elif win_rate > 0.6:
                            logger.info("Good performance - can optimize further")
                    
                    # Detect market condition
                    price_data = self._get_recent_prices('XAUUSD', 50)
                    if price_data and len(price_data) >= 20:
                        condition = self.learner.detect_market_condition(price_data)
                        
                        # Update system state
                        if self.state:
                            self.state.update_market_data('XAUUSD', {
                                'condition': condition.regime,
                                'volatility': condition.volatility,
                                'trend_strength': condition.trend_strength
                            })
                        
                        # Publish condition change
                        self._publish_event(EventTypes.MARKET_CONDITION_CHANGED, {
                            'condition': condition.regime,
                            'volatility': condition.volatility
                        })
                
                # Run every 5 minutes
                time.sleep(300)
                
            except Exception as e:
                logger.error(f"Error in learning loop: {e}")
                time.sleep(300)
    
    def _health_check_worker(self):
        """Monitor system health."""
        while not self._stop_event.is_set():
            try:
                # Check if all workers are alive
                for name, thread in self._workers.items():
                    if not thread.is_alive():
                        logger.error(f"Worker {name} died!")
                        self.status.errors.append(f"Worker {name} stopped")
                
                # Check MT5 connection
                if MT5_AVAILABLE:
                    try:
                        with MT5Manager() as mt5:
                            if not mt5.connected:
                                logger.warning("MT5 connection issue detected")
                    except:
                        pass
                
                # Update status
                self.status.last_update = datetime.now()
                
                time.sleep(60)  # Check every minute
                
            except Exception as e:
                logger.error(f"Error in health check: {e}")
                time.sleep(60)
    
    # Event Handlers
    def _on_trade_executed(self, event):
        """Handle trade execution event."""
        data = event.data
        logger.info(f"Trade executed: {data}")
        
        # Update state
        if self.state:
            self.state.update_position(data.get('ticket'), data)
        
        # Learn from trade
        if self.learner:
            self.learner.learn_from_trade(data)
    
    def _on_trade_closed(self, event):
        """Handle trade close event."""
        data = event.data
        ticket = data.get('ticket')
        
        # Remove from state
        if self.state and ticket:
            self.state.remove_position(ticket)
        
        # Analyze closed trade
        pnl = data.get('realized_pnl', 0)
        if pnl > 0:
            logger.info(f"Winning trade closed: +{pnl:.2f}")
        else:
            logger.info(f"Losing trade closed: {pnl:.2f}")
    
    def _on_signal_generated(self, event):
        """Handle new signal event."""
        signal = event.data
        logger.info(f"Signal generated: {signal}")
        
        # In AUTO mode, evaluate immediately
        if self.mode == SystemMode.AUTO:
            market_data = self._get_market_data(signal.get('symbol', 'XAUUSD'))
            account_data = self._get_account_data()
            
            decision = self.decision_engine.evaluate_trade_opportunity(
                signal, market_data, account_data
            )
            
            if decision.action == DecisionAction.EXECUTE:
                self._execute_decision(decision)
    
    def _on_market_condition_changed(self, event):
        """Handle market condition change."""
        condition = event.data.get('condition')
        logger.info(f"Market condition changed to: {condition}")
        
        # Adapt strategy parameters
        if self.learner and condition:
            params = self.learner.get_adaptive_params(condition)
            logger.info(f"Loaded adaptive params for {condition}: {params}")
    
    def _on_economic_event(self, event):
        """Handle upcoming economic event."""
        data = event.data
        logger.warning(f"Economic event approaching: {data}")
        
        # Auto-pause if configured
        if self.state:
            self.state.disable_trading(f"Economic event: {data.get('title', 'Unknown')}")
    
    def _on_error(self, event):
        """Handle system error."""
        error = event.data
        logger.error(f"System error: {error}")
        self.status.errors.append(str(error))
        
        if len(self.status.errors) > 10:
            self.status.errors = self.status.errors[-10:]
    
    # Helper Methods
    def _publish_event(self, event_type: EventTypes, data: Dict[str, Any]):
        """Publish event to bus."""
        if self.event_bus:
            publish(event_type, data, source="orchestrator")
    
    def _get_market_data(self, symbol: str) -> Dict[str, Any]:
        """Get current market data."""
        if self.state:
            market = self.state.get_market_data(symbol)
            if market:
                return {
                    'condition': market.condition,
                    'trend': market.trend,
                    'volatility': market.volatility,
                    'bid': market.bid,
                    'ask': market.ask
                }
        return {}
    
    def _get_account_data(self) -> Dict[str, Any]:
        """Get account data."""
        if self.state:
            info = self.state.get_account_info()
            if info:
                positions = self.state.get_all_positions()
                return {
                    'balance': info.get('balance', 0),
                    'equity': info.get('equity', 0),
                    'daily_pnl': info.get('profit', 0),
                    'open_positions': len(positions)
                }
        return {}
    
    def _get_current_price(self, symbol: str) -> Optional[float]:
        """Get current price for symbol."""
        if self.state:
            market = self.state.get_market_data(symbol)
            if market:
                return (market.bid + market.ask) / 2
        return None
    
    def _get_recent_prices(self, symbol: str, count: int) -> List[float]:
        """Get recent price history."""
        # This would integrate with historical data
        return []
    
    def _check_news_signal(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Check for news-based trading signals."""
        if not self.news:
            return None
        
        try:
            results = self.news.research_symbol(symbol, use_ai=True)
            signal = results.get('trading_signal', {})
            
            if signal.get('direction') in ['buy', 'sell']:
                return {
                    'direction': signal['direction'].upper(),
                    'confidence': signal.get('confidence', 0.5),
                    'strength': signal.get('strength', 1),
                    'strategy': 'news_sentiment'
                }
        except Exception as e:
            logger.error(f"Error checking news signal: {e}")
        
        return None
    
    def _execute_decision(self, decision):
        """Execute a trade decision."""
        params = decision.parameters
        logger.info(f"Executing decision: {params}")
        
        if MT5_AVAILABLE:
            try:
                with MT5Manager() as mt5:
                    result = mt5.execute_trade(
                        action=params['direction'],
                        volume=params['volume']
                    )
                    
                    if result.get('success'):
                        logger.info(f"Trade executed: {result}")
                        
                        # Set SL/TP if specified
                        if params.get('stop_loss') or params.get('take_profit'):
                            ticket = result.get('order')
                            mt5.modify_position(
                                ticket=ticket,
                                sl=params.get('stop_loss'),
                                tp=params.get('take_profit')
                            )
                    else:
                        logger.error(f"Trade failed: {result.get('error')}")
                        
            except Exception as e:
                logger.error(f"Error executing trade: {e}")
    
    def _notify_decision(self, decision):
        """Notify user of decision in semi-auto mode."""
        if NOTIFIER_AVAILABLE:
            msg = (
                f"📊 Trade Recommendation\n\n"
                f"Action: {decision.parameters.get('direction', 'N/A')}\n"
                f"Confidence: {decision.confidence:.1%}\n"
                f"Volume: {decision.parameters.get('volume', 0)}\n"
                f"Risk Score: {decision.risk_score:.2f}\n\n"
                f"Reason: {decision.reason}\n\n"
                f"Execute with: claw trade {decision.parameters.get('direction', 'BUY')} "
                f"{decision.parameters.get('volume', 0.1)}"
            )
            notify_system(msg, level="info")
    
    def _execute_exit_decision(self, position, decision):
        """Execute exit decision for a position."""
        if decision.action == DecisionAction.CLOSE:
            if MT5_AVAILABLE:
                try:
                    with MT5Manager() as mt5:
                        result = mt5.close_position(position.ticket)
                        
                        if result.get('success'):
                            logger.info(f"Position {position.ticket} closed")
                        else:
                            logger.error(f"Failed to close position: {result.get('error')}")
                            
                except Exception as e:
                    logger.error(f"Error closing position: {e}")
        
        elif decision.action == DecisionAction.MODIFY:
            action = decision.parameters.get('action')
            
            if action == 'activate_trailing' and self.order_manager:
                # Apply trailing stop
                pass  # Implementation depends on order manager
    
    # Public API
    def get_status(self) -> Dict[str, Any]:
        """Get current system status."""
        return {
            'mode': self.mode.name,
            'is_running': self.status.is_running,
            'active_modules': self.status.active_modules,
            'last_update': self.status.last_update.isoformat(),
            'errors': self.status.errors[-5:],
            'workers': {name: thread.is_alive() for name, thread in self._workers.items()}
        }
    
    def set_mode(self, mode: SystemMode):
        """Change system mode."""
        old_mode = self.mode
        self.mode = mode
        self.status.mode = mode
        
        logger.info(f"Mode changed from {old_mode.name} to {mode.name}")
        
        if NOTIFIER_AVAILABLE:
            notify_system(f"System mode changed to: {mode.name}", level="info")
    
    def get_decision_stats(self) -> Dict[str, Any]:
        """Get decision engine statistics."""
        return self.decision_engine.get_decision_stats()


# Convenience function
def get_orchestrator(mode: SystemMode = SystemMode.SEMI_AUTO) -> TradingOrchestrator:
    """Get or create orchestrator instance."""
    return TradingOrchestrator(mode)


if __name__ == "__main__":
    # Test orchestrator
    print("Testing TradingOrchestrator...")
    
    orchestrator = TradingOrchestrator(mode=SystemMode.SEMI_AUTO)
    
    print(f"Status: {orchestrator.get_status()}")
    print(f"Decision Stats: {orchestrator.get_decision_stats()}")
    
    print("\nTest completed!")
