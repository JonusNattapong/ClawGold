"""
MT5 Connection Manager
======================
Provides unified connection handling for MetaTrader 5 with automatic
cleanup and error handling.
"""

import MetaTrader5 as mt5
from pathlib import Path
from typing import Optional, Dict, List, Any
from dataclasses import dataclass
from logger import get_logger
try:
    from .config_loader import load_config, DEFAULT_MT5_TERMINAL_PATH
except ImportError:
    from config_loader import load_config, DEFAULT_MT5_TERMINAL_PATH

logger = get_logger(__name__)


@dataclass
class AccountInfo:
    """Account information data class."""
    balance: float
    equity: float
    margin: float
    margin_free: float
    profit: float
    margin_level: float
    currency: str


class MT5Manager:
    """
    Context manager for MT5 operations.
    
    Usage:
        with MT5Manager() as mt5:
            account = mt5.get_account_info()
            positions = mt5.get_positions()
    """
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or Path(__file__).parent.parent / "config.yaml"
        self.config = None
        self.connected = False
        
    def __enter__(self):
        """Initialize MT5 connection."""
        self._load_config()
        
        if self.config['trading']['mode'] != 'real':
            raise RuntimeError("MT5 connection requires real trading mode")
        
        # MT5 path
        path = self.config.get('mt5', {}).get('terminal_path', DEFAULT_MT5_TERMINAL_PATH)
        
        # Initialize
        initialized = mt5.initialize(
            path=path,
            login=self.config['mt5']['login'],
            server=self.config['mt5']['server'],
            password=self.config['mt5']['password']
        )
        
        if not initialized:
            error = mt5.last_error()
            logger.error(f"MT5 initialization failed: {error}")
            raise ConnectionError(f"Failed to connect to MT5: {error}")
        
        self.connected = True
        logger.info(f"Connected to MT5 - Server: {self.config['mt5']['server']}")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Clean up MT5 connection."""
        if self.connected:
            mt5.shutdown()
            logger.info("MT5 connection closed")
            self.connected = False
    
    def _load_config(self):
        """Load configuration from YAML."""
        try:
            self.config = load_config(str(self.config_path))
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            raise
    
    def get_account_info(self) -> Optional[Dict[str, Any]]:
        """Get account information."""
        info = mt5.account_info()
        if info is None:
            logger.error("Failed to get account info")
            return None
        
        return {
            'balance': info.balance,
            'equity': info.equity,
            'margin': info.margin,
            'margin_free': info.margin_free,
            'profit': info.profit,
            'margin_level': info.margin_level if info.margin_level else 0,
            'currency': info.currency
        }
    
    def get_positions(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get open positions."""
        kwargs = {'symbol': symbol} if symbol else {}
        positions = mt5.positions_get(**kwargs)
        
        if positions is None:
            return []
        
        result = []
        for pos in positions:
            result.append({
                'ticket': pos.ticket,
                'symbol': pos.symbol,
                'type': pos.type,  # 0 = BUY, 1 = SELL
                'volume': pos.volume,
                'price_open': pos.price_open,
                'price_current': pos.price_current,
                'profit': pos.profit,
                'swap': pos.swap,
                'comment': pos.comment,
                'time': pos.time
            })
        return result
    
    def get_tick(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get current tick data."""
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            logger.error(f"Failed to get tick for {symbol}")
            return None
        
        return {
            'bid': tick.bid,
            'ask': tick.ask,
            'last': tick.last,
            'time': tick.time,
            'volume': tick.volume,
            'flags': tick.flags
        }
    
    def get_rates(self, symbol: str, timeframe: int, count: int) -> Optional[List]:
        """Get historical rates."""
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
        if rates is None:
            logger.error(f"Failed to get rates for {symbol}")
            return None
        return rates
    
    def execute_trade(self, action: str, volume: float, 
                      deviation: int = 10) -> Dict[str, Any]:
        """Execute a market order."""
        symbol = self.config['trading']['symbol']
        tick = self.get_tick(symbol)
        
        if tick is None:
            return {'success': False, 'error': 'Failed to get price'}
        
        # Determine order type and price
        action = action.upper()
        if action == 'BUY':
            order_type = mt5.ORDER_TYPE_BUY
            price = tick['ask']
        elif action == 'SELL':
            order_type = mt5.ORDER_TYPE_SELL
            price = tick['bid']
        else:
            return {'success': False, 'error': f'Invalid action: {action}'}
        
        # Build order request
        request = {
            'action': mt5.TRADE_ACTION_DEAL,
            'symbol': symbol,
            'volume': volume,
            'type': order_type,
            'price': price,
            'deviation': deviation,
            'magic': 123456,
            'comment': 'ClawGold',
            'type_time': mt5.ORDER_TIME_GTC,
            'type_filling': mt5.ORDER_FILLING_IOC,
        }
        
        # Send order
        result = mt5.order_send(request)
        
        if result is None:
            error = mt5.last_error()
            logger.error(f"Order failed: {error}")
            return {'success': False, 'error': str(error)}
        
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"Order failed with retcode: {result.retcode}")
            return {'success': False, 'error': f'Retcode: {result.retcode}'}
        
        logger.info(f"Order executed: {action} {volume} lots at {price}")
        return {
            'success': True,
            'order': result.order,
            'volume': result.volume,
            'price': result.price,
            'bid': result.bid,
            'ask': result.ask,
            'comment': result.comment
        }
    
    def close_position(self, ticket: int) -> Dict[str, Any]:
        """Close a specific position."""
        position = None
        positions = mt5.positions_get()
        
        for pos in positions:
            if pos.ticket == ticket:
                position = pos
                break
        
        if position is None:
            return {'success': False, 'error': f'Position {ticket} not found'}
        
        symbol = position.symbol
        tick = self.get_tick(symbol)
        
        if tick is None:
            return {'success': False, 'error': 'Failed to get price'}
        
        # Reverse order type
        if position.type == mt5.POSITION_TYPE_BUY:
            order_type = mt5.ORDER_TYPE_SELL
            price = tick['bid']
        else:
            order_type = mt5.ORDER_TYPE_BUY
            price = tick['ask']
        
        request = {
            'action': mt5.TRADE_ACTION_DEAL,
            'symbol': symbol,
            'volume': position.volume,
            'type': order_type,
            'position': ticket,
            'price': price,
            'deviation': 10,
            'magic': 123456,
            'comment': 'ClawGold Close',
            'type_time': mt5.ORDER_TIME_GTC,
            'type_filling': mt5.ORDER_FILLING_IOC,
        }
        
        result = mt5.order_send(request)
        
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            error = mt5.last_error() if result is None else f"Retcode: {result.retcode}"
            return {'success': False, 'error': str(error)}
        
        profit = position.profit + position.swap
        logger.info(f"Position {ticket} closed with profit: {profit:.2f}")
        
        return {
            'success': True,
            'ticket': ticket,
            'profit': profit,
            'price': result.price
        }
    
    def close_all_positions(self) -> List[Dict[str, Any]]:
        """Close all open positions."""
        positions = self.get_positions()
        results = []
        
        for pos in positions:
            result = self.close_position(pos['ticket'])
            results.append(result)
        
        return results
