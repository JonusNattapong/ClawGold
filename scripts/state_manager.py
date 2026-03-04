"""
State Manager Module
====================
Centralized state management for all trading data and system state.
Provides consistent data access across all modules.

Usage:
    from state_manager import StateManager, TradingState
    
    state = StateManager()
    state.update_position(symbol='XAUUSD', data={'volume': 0.5, 'pnl': 100})
    
    current_price = state.get_market_data('XAUUSD', 'price')
    trading_status = state.get_system_state('trading_enabled')
"""

import json
import sqlite3
import threading
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from contextlib import contextmanager

from logger import get_logger

logger = get_logger(__name__)


@dataclass
class PositionState:
    """Position state data."""
    ticket: int
    symbol: str
    action: str
    volume: float
    entry_price: float
    current_price: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    pnl: float = 0.0
    pnl_percent: float = 0.0
    swap: float = 0.0
    open_time: Optional[datetime] = None
    strategy: str = "manual"
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class MarketState:
    """Market state data."""
    symbol: str
    bid: float
    ask: float
    spread: float
    timestamp: datetime
    trend: str = "neutral"  # bullish, bearish, neutral
    volatility: float = 0.0
    volume_24h: float = 0.0
    condition: str = "normal"  # trending, ranging, volatile, breakout


@dataclass
class SystemState:
    """System state data."""
    trading_enabled: bool = True
    auto_trading: bool = False
    risk_level: str = "normal"  # conservative, normal, aggressive
    mode: str = "manual"  # manual, semi-auto, auto
    last_update: Optional[datetime] = None
    errors: List[str] = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []


class StateManager:
    """
    Centralized state manager for the trading system.
    Thread-safe singleton for consistent state across modules.
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls, db_path: str = "data/system_state.db"):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, db_path: str = "data/system_state.db"):
        if self._initialized:
            return
            
        self._initialized = True
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # In-memory state cache
        self._positions: Dict[int, PositionState] = {}
        self._market_data: Dict[str, MarketState] = {}
        self._system_state = SystemState()
        self._signals: List[Dict[str, Any]] = []
        self._orders: Dict[int, Dict[str, Any]] = {}
        self._account_info: Optional[Dict[str, Any]] = None
        
        # Locks for thread safety
        self._position_lock = threading.RLock()
        self._market_lock = threading.RLock()
        self._system_lock = threading.RLock()
        
        self._init_db()
        self._load_state()
        
        logger.info("StateManager initialized")
    
    def _init_db(self):
        """Initialize database tables."""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()
            
            # Positions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS state_positions (
                    ticket INTEGER PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    action TEXT NOT NULL,
                    volume REAL,
                    entry_price REAL,
                    current_price REAL,
                    stop_loss REAL,
                    take_profit REAL,
                    pnl REAL,
                    strategy TEXT,
                    data TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Market data table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS state_market (
                    symbol TEXT PRIMARY KEY,
                    bid REAL,
                    ask REAL,
                    spread REAL,
                    trend TEXT,
                    volatility REAL,
                    condition TEXT,
                    data TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # System state table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS state_system (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            conn.commit()
    
    def _load_state(self):
        """Load state from database."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                # Load positions
                cursor.execute("SELECT * FROM state_positions")
                for row in cursor.fetchall():
                    data = json.loads(row['data']) if row['data'] else {}
                    self._positions[row['ticket']] = PositionState(
                        ticket=row['ticket'],
                        symbol=row['symbol'],
                        action=row['action'],
                        volume=row['volume'],
                        entry_price=row['entry_price'],
                        current_price=row['current_price'],
                        stop_loss=row['stop_loss'],
                        take_profit=row['take_profit'],
                        pnl=row['pnl'] or 0,
                        strategy=row['strategy'] or 'manual',
                        metadata=data
                    )
                
                # Load system state
                cursor.execute("SELECT * FROM state_system")
                for row in cursor.fetchall():
                    if row['key'] == 'trading_enabled':
                        self._system_state.trading_enabled = row['value'] == 'true'
                    elif row['key'] == 'auto_trading':
                        self._system_state.auto_trading = row['value'] == 'true'
                    elif row['key'] == 'risk_level':
                        self._system_state.risk_level = row['value']
                
                logger.info(f"Loaded {len(self._positions)} positions from database")
                
        except Exception as e:
            logger.error(f"Error loading state: {e}")
    
    # Position Management
    def update_position(self, ticket: int, data: Dict[str, Any]):
        """Update or create position state."""
        with self._position_lock:
            if ticket in self._positions:
                # Update existing
                pos = self._positions[ticket]
                for key, value in data.items():
                    if hasattr(pos, key):
                        setattr(pos, key, value)
                pos.metadata.update(data.get('metadata', {}))
            else:
                # Create new
                self._positions[ticket] = PositionState(
                    ticket=ticket,
                    symbol=data.get('symbol', 'XAUUSD'),
                    action=data.get('action', 'BUY'),
                    volume=data.get('volume', 0),
                    entry_price=data.get('entry_price', 0),
                    current_price=data.get('current_price', 0),
                    stop_loss=data.get('stop_loss'),
                    take_profit=data.get('take_profit'),
                    pnl=data.get('pnl', 0),
                    strategy=data.get('strategy', 'manual'),
                    metadata=data.get('metadata', {})
                )
            
            self._save_position(ticket)
    
    def remove_position(self, ticket: int):
        """Remove position from state."""
        with self._position_lock:
            if ticket in self._positions:
                del self._positions[ticket]
                
                with sqlite3.connect(str(self.db_path)) as conn:
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM state_positions WHERE ticket = ?", (ticket,))
                    conn.commit()
    
    def get_position(self, ticket: int) -> Optional[PositionState]:
        """Get position by ticket."""
        with self._position_lock:
            return self._positions.get(ticket)
    
    def get_all_positions(self) -> List[PositionState]:
        """Get all positions."""
        with self._position_lock:
            return list(self._positions.values())
    
    def get_positions_by_symbol(self, symbol: str) -> List[PositionState]:
        """Get positions for a symbol."""
        with self._position_lock:
            return [p for p in self._positions.values() if p.symbol == symbol]
    
    def get_total_pnl(self) -> float:
        """Get total PnL across all positions."""
        with self._position_lock:
            return sum(p.pnl for p in self._positions.values())
    
    def _save_position(self, ticket: int):
        """Save position to database."""
        pos = self._positions[ticket]
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO state_positions 
                (ticket, symbol, action, volume, entry_price, current_price, 
                 stop_loss, take_profit, pnl, strategy, data, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                pos.ticket, pos.symbol, pos.action, pos.volume, pos.entry_price,
                pos.current_price, pos.stop_loss, pos.take_profit, pos.pnl,
                pos.strategy, json.dumps(pos.metadata)
            ))
            conn.commit()
    
    # Market Data Management
    def update_market_data(self, symbol: str, data: Dict[str, Any]):
        """Update market data for a symbol."""
        with self._market_lock:
            self._market_data[symbol] = MarketState(
                symbol=symbol,
                bid=data.get('bid', 0),
                ask=data.get('ask', 0),
                spread=data.get('spread', 0),
                timestamp=datetime.now(),
                trend=data.get('trend', 'neutral'),
                volatility=data.get('volatility', 0),
                volume_24h=data.get('volume_24h', 0),
                condition=data.get('condition', 'normal')
            )
            
            self._save_market_data(symbol)
    
    def get_market_data(self, symbol: str, field: Optional[str] = None) -> Any:
        """Get market data for a symbol."""
        with self._market_lock:
            market = self._market_data.get(symbol)
            if not market:
                return None
            
            if field:
                return getattr(market, field, None)
            return market
    
    def _save_market_data(self, symbol: str):
        """Save market data to database."""
        market = self._market_data[symbol]
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO state_market 
                (symbol, bid, ask, spread, trend, volatility, condition, data, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                symbol, market.bid, market.ask, market.spread, market.trend,
                market.volatility, market.condition, json.dumps({})
            ))
            conn.commit()
    
    # System State Management
    def set_system_state(self, key: str, value: Any):
        """Set system state value."""
        with self._system_lock:
            if hasattr(self._system_state, key):
                setattr(self._system_state, key, value)
            
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO state_system (key, value, updated_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                """, (key, str(value)))
                conn.commit()
    
    def get_system_state(self, key: str) -> Any:
        """Get system state value."""
        with self._system_lock:
            return getattr(self._system_state, key, None)
    
    def is_trading_enabled(self) -> bool:
        """Check if trading is enabled."""
        return self._system_state.trading_enabled
    
    def disable_trading(self, reason: str = ""):
        """Disable trading."""
        self._system_state.trading_enabled = False
        self.set_system_state('trading_enabled', False)
        logger.warning(f"Trading disabled: {reason}")
    
    def enable_trading(self, reason: str = ""):
        """Enable trading."""
        self._system_state.trading_enabled = True
        self.set_system_state('trading_enabled', True)
        logger.info(f"Trading enabled: {reason}")
    
    # Signal Management
    def add_signal(self, signal: Dict[str, Any]):
        """Add trading signal."""
        signal['timestamp'] = datetime.now().isoformat()
        self._signals.append(signal)
        
        # Keep only recent signals
        if len(self._signals) > 100:
            self._signals = self._signals[-100:]
    
    def get_recent_signals(self, count: int = 10) -> List[Dict[str, Any]]:
        """Get recent signals."""
        return self._signals[-count:]
    
    # Account Info
    def update_account_info(self, info: Dict[str, Any]):
        """Update account information."""
        self._account_info = info
        self._account_info['last_update'] = datetime.now().isoformat()
    
    def get_account_info(self) -> Optional[Dict[str, Any]]:
        """Get account information."""
        return self._account_info
    
    # State Summary
    def get_state_summary(self) -> Dict[str, Any]:
        """Get complete state summary."""
        with self._position_lock, self._market_lock, self._system_lock:
            return {
                'timestamp': datetime.now().isoformat(),
                'system': {
                    'trading_enabled': self._system_state.trading_enabled,
                    'auto_trading': self._system_state.auto_trading,
                    'risk_level': self._system_state.risk_level,
                    'mode': self._system_state.mode
                },
                'positions': {
                    'count': len(self._positions),
                    'total_pnl': self.get_total_pnl(),
                    'positions': [asdict(p) for p in self._positions.values()]
                },
                'market': {
                    symbol: {
                        'bid': m.bid,
                        'ask': m.ask,
                        'spread': m.spread,
                        'trend': m.trend,
                        'condition': m.condition
                    } for symbol, m in self._market_data.items()
                },
                'account': self._account_info,
                'recent_signals': self._signals[-5:]
            }


# Global state manager instance
state_manager = StateManager()


if __name__ == "__main__":
    # Test state manager
    print("Testing StateManager...")
    
    sm = StateManager()
    
    # Test positions
    sm.update_position(12345, {
        'symbol': 'XAUUSD',
        'action': 'BUY',
        'volume': 0.5,
        'entry_price': 2950.0,
        'current_price': 2955.0,
        'pnl': 250.0,
        'strategy': 'trend_following'
    })
    
    # Test market data
    sm.update_market_data('XAUUSD', {
        'bid': 2954.5,
        'ask': 2955.0,
        'spread': 0.5,
        'trend': 'bullish',
        'condition': 'trending'
    })
    
    # Test system state
    sm.set_system_state('trading_enabled', True)
    
    # Get summary
    summary = sm.get_state_summary()
    print(f"\nPositions: {summary['positions']['count']}")
    print(f"Total PnL: {summary['positions']['total_pnl']}")
    print(f"Trading Enabled: {summary['system']['trading_enabled']}")
    
    print("\nTest completed!")
