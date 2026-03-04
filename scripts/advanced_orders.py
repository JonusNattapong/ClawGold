"""
Advanced Order Types Module
===========================
Implements OCO (One Cancels Other), Pending Orders, and Bracket Orders
for sophisticated trading strategies.

Usage:
    from advanced_orders import OrderManager, BracketOrder, OCOOrder
    
    # Bracket Order (Entry + SL + TP)
    bracket = BracketOrder(
        symbol="XAUUSD",
        action="BUY",
        volume=0.5,
        entry_price=2950.00,
        stop_loss=2940.00,
        take_profit=2970.00
    )
    
    # OCO Order
    oco = OCOOrder(
        symbol="XAUUSD",
        volume=0.5,
        price_buy=2945.00,
        price_sell=2955.00
    )
"""

import time
import threading
from typing import Optional, Dict, List, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

from logger import get_logger

try:
    from mt5_manager import MT5Manager
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False

try:
    from notifier import notify_trade, notify_system
    NOTIFIER_AVAILABLE = True
except ImportError:
    NOTIFIER_AVAILABLE = False

logger = get_logger(__name__)


class OrderType(Enum):
    """Order type enumeration."""
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderStatus(Enum):
    """Order status enumeration."""
    PENDING = "pending"
    OPEN = "open"
    CLOSED = "closed"
    CANCELLED = "cancelled"
    ERROR = "error"


@dataclass
class Order:
    """Base order class."""
    symbol: str
    action: str  # BUY or SELL
    volume: float
    order_type: OrderType = OrderType.MARKET
    price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    ticket: Optional[int] = None
    status: OrderStatus = OrderStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    executed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BracketOrder:
    """
    Bracket Order: Entry + Stop Loss + Take Profit
    All three orders placed simultaneously.
    """
    symbol: str
    action: str  # BUY or SELL
    volume: float
    entry_price: Optional[float] = None  # None for market order
    stop_loss: float = 0.0
    take_profit: float = 0.0
    entry_ticket: Optional[int] = None
    sl_ticket: Optional[int] = None
    tp_ticket: Optional[int] = None
    status: str = "pending"
    
    def validate(self) -> tuple[bool, str]:
        """Validate bracket order parameters."""
        if self.volume <= 0:
            return False, "Volume must be positive"
        
        if self.action.upper() not in ['BUY', 'SELL']:
            return False, "Action must be BUY or SELL"
        
        if self.stop_loss <= 0 or self.take_profit <= 0:
            return False, "Stop loss and take profit must be set"
        
        # Validate price levels
        if self.action.upper() == 'BUY':
            if self.stop_loss >= (self.entry_price or 0):
                return False, "For BUY: stop loss must be below entry"
            if self.take_profit <= (self.entry_price or 0):
                return False, "For BUY: take profit must be above entry"
        else:  # SELL
            if self.stop_loss <= (self.entry_price or float('inf')):
                return False, "For SELL: stop loss must be above entry"
            if self.take_profit >= (self.entry_price or 0):
                return False, "For SELL: take profit must be below entry"
        
        return True, "Valid"


@dataclass
class OCOOrder:
    """
    OCO (One Cancels Other) Order
    Two pending orders where executing one cancels the other.
    Useful for trading breakouts in either direction.
    """
    symbol: str
    volume: float
    price_buy: float  # Buy stop/limit price
    price_sell: float  # Sell stop/limit price
    stop_loss_points: float = 50.0
    take_profit_points: float = 100.0
    buy_ticket: Optional[int] = None
    sell_ticket: Optional[int] = None
    executed_ticket: Optional[int] = None
    status: str = "pending"
    
    def validate(self) -> tuple[bool, str]:
        """Validate OCO order parameters."""
        if self.volume <= 0:
            return False, "Volume must be positive"
        
        if self.price_buy >= self.price_sell:
            return False, "Buy price must be below sell price for OCO"
        
        return True, "Valid"


@dataclass
class PendingOrder:
    """
    Pending Order (Limit or Stop)
    Order that executes when price reaches specified level.
    """
    symbol: str
    action: str  # BUY or SELL
    volume: float
    order_type: str  # LIMIT or STOP
    price: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    expiration: Optional[datetime] = None
    ticket: Optional[int] = None
    status: str = "pending"
    
    def validate(self, current_price: float) -> tuple[bool, str]:
        """Validate pending order against current price."""
        if self.volume <= 0:
            return False, "Volume must be positive"
        
        if self.order_type.upper() not in ['LIMIT', 'STOP']:
            return False, "Order type must be LIMIT or STOP"
        
        if self.action.upper() not in ['BUY', 'SELL']:
            return False, "Action must be BUY or SELL"
        
        # Validate price placement
        if self.order_type.upper() == 'LIMIT':
            if self.action.upper() == 'BUY' and self.price >= current_price:
                return False, "BUY LIMIT must be below current price"
            if self.action.upper() == 'SELL' and self.price <= current_price:
                return False, "SELL LIMIT must be above current price"
        
        elif self.order_type.upper() == 'STOP':
            if self.action.upper() == 'BUY' and self.price <= current_price:
                return False, "BUY STOP must be above current price"
            if self.action.upper() == 'SELL' and self.price >= current_price:
                return False, "SELL STOP must be below current price"
        
        return True, "Valid"


class OrderManager:
    """
    Manages advanced order types and their execution.
    """
    
    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize Order Manager.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config or {}
        self.active_brackets: Dict[str, BracketOrder] = {}
        self.active_ocos: Dict[str, OCOOrder] = {}
        self.active_pendings: Dict[str, PendingOrder] = {}
        self._monitor_thread: Optional[threading.Thread] = None
        self._stop_monitoring = threading.Event()
        
    def _get_mt5(self) -> Optional[MT5Manager]:
        """Get MT5 manager instance."""
        if not MT5_AVAILABLE:
            return None
        return MT5Manager()
    
    def place_bracket_order(self, bracket: BracketOrder) -> Dict[str, Any]:
        """
        Place a bracket order (entry + SL + TP).
        
        Args:
            bracket: BracketOrder configuration
            
        Returns:
            Result dictionary with status and ticket numbers
        """
        # Validate
        valid, message = bracket.validate()
        if not valid:
            return {'success': False, 'error': message}
        
        if not MT5_AVAILABLE:
            return {'success': False, 'error': 'MT5 not available'}
        
        try:
            with self._get_mt5() as mt5:
                symbol = bracket.symbol
                action = bracket.action.upper()
                
                # Step 1: Place entry order
                if bracket.entry_price:
                    # Pending order entry
                    entry_type = 'LIMIT' if action == 'BUY' else 'STOP'
                    entry_result = mt5.place_pending_order(
                        symbol=symbol,
                        action=action,
                        volume=bracket.volume,
                        order_type=entry_type,
                        price=bracket.entry_price
                    )
                else:
                    # Market order entry
                    entry_result = mt5.execute_trade(action, bracket.volume)
                
                if not entry_result.get('success'):
                    return {'success': False, 'error': f"Entry failed: {entry_result.get('error')}"}
                
                bracket.entry_ticket = entry_result.get('order')
                
                # Step 2: If market order, modify position with SL/TP
                if not bracket.entry_price:
                    modify_result = mt5.modify_position(
                        ticket=bracket.entry_ticket,
                        sl=bracket.stop_loss,
                        tp=bracket.take_profit
                    )
                    
                    if not modify_result.get('success'):
                        logger.warning(f"Failed to set SL/TP: {modify_result.get('error')}")
                
                bracket.status = "open"
                self.active_brackets[str(bracket.entry_ticket)] = bracket
                
                # Send notification
                if NOTIFIER_AVAILABLE:
                    notify_trade(
                        action=action,
                        symbol=symbol,
                        volume=bracket.volume,
                        price=bracket.entry_price or entry_result.get('price', 0),
                        sl=bracket.stop_loss,
                        tp=bracket.take_profit
                    )
                
                return {
                    'success': True,
                    'entry_ticket': bracket.entry_ticket,
                    'stop_loss': bracket.stop_loss,
                    'take_profit': bracket.take_profit,
                    'message': 'Bracket order placed successfully'
                }
                
        except Exception as e:
            logger.error(f"Error placing bracket order: {e}")
            return {'success': False, 'error': str(e)}
    
    def place_oco_order(self, oco: OCOOrder) -> Dict[str, Any]:
        """
        Place OCO (One Cancels Other) order.
        
        Args:
            oco: OCOOrder configuration
            
        Returns:
            Result dictionary
        """
        # Validate
        valid, message = oco.validate()
        if not valid:
            return {'success': False, 'error': message}
        
        if not MT5_AVAILABLE:
            return {'success': False, 'error': 'MT5 not available'}
        
        try:
            with self._get_mt5() as mt5:
                symbol = oco.symbol
                
                # Place BUY STOP order
                buy_sl = oco.price_buy - oco.stop_loss_points
                buy_tp = oco.price_buy + oco.take_profit_points
                
                buy_result = mt5.place_pending_order(
                    symbol=symbol,
                    action='BUY',
                    volume=oco.volume,
                    order_type='STOP',
                    price=oco.price_buy,
                    sl=buy_sl,
                    tp=buy_tp
                )
                
                if not buy_result.get('success'):
                    return {'success': False, 'error': f"BUY order failed: {buy_result.get('error')}"}
                
                oco.buy_ticket = buy_result.get('order')
                
                # Place SELL STOP order
                sell_sl = oco.price_sell + oco.stop_loss_points
                sell_tp = oco.price_sell - oco.take_profit_points
                
                sell_result = mt5.place_pending_order(
                    symbol=symbol,
                    action='SELL',
                    volume=oco.volume,
                    order_type='STOP',
                    price=oco.price_sell,
                    sl=sell_sl,
                    tp=sell_tp
                )
                
                if not sell_result.get('success'):
                    # Cancel buy order if sell fails
                    mt5.cancel_order(oco.buy_ticket)
                    return {'success': False, 'error': f"SELL order failed: {sell_result.get('error')}"}
                
                oco.sell_ticket = sell_result.get('order')
                oco.status = "open"
                
                # Store OCO for monitoring
                oco_id = f"{oco.buy_ticket}_{oco.sell_ticket}"
                self.active_ocos[oco_id] = oco
                
                # Start monitoring thread if not running
                self._start_oco_monitoring()
                
                return {
                    'success': True,
                    'buy_ticket': oco.buy_ticket,
                    'sell_ticket': oco.sell_ticket,
                    'oco_id': oco_id,
                    'message': 'OCO order placed successfully'
                }
                
        except Exception as e:
            logger.error(f"Error placing OCO order: {e}")
            return {'success': False, 'error': str(e)}
    
    def place_pending_order(self, order: PendingOrder) -> Dict[str, Any]:
        """
        Place a pending order (Limit or Stop).
        
        Args:
            order: PendingOrder configuration
            
        Returns:
            Result dictionary
        """
        if not MT5_AVAILABLE:
            return {'success': False, 'error': 'MT5 not available'}
        
        try:
            with self._get_mt5() as mt5:
                # Get current price for validation
                tick = mt5.get_tick(order.symbol)
                if not tick:
                    return {'success': False, 'error': 'Failed to get current price'}
                
                current_price = (tick['bid'] + tick['ask']) / 2
                
                # Validate
                valid, message = order.validate(current_price)
                if not valid:
                    return {'success': False, 'error': message}
                
                # Place order
                result = mt5.place_pending_order(
                    symbol=order.symbol,
                    action=order.action.upper(),
                    volume=order.volume,
                    order_type=order.order_type.upper(),
                    price=order.price,
                    sl=order.stop_loss,
                    tp=order.take_profit,
                    expiration=order.expiration
                )
                
                if result.get('success'):
                    order.ticket = result.get('order')
                    order.status = "open"
                    self.active_pendings[str(order.ticket)] = order
                    
                    return {
                        'success': True,
                        'ticket': order.ticket,
                        'message': f"{order.order_type} order placed at {order.price}"
                    }
                else:
                    return {'success': False, 'error': result.get('error')}
                    
        except Exception as e:
            logger.error(f"Error placing pending order: {e}")
            return {'success': False, 'error': str(e)}
    
    def cancel_order(self, ticket: int) -> Dict[str, Any]:
        """Cancel a pending order."""
        if not MT5_AVAILABLE:
            return {'success': False, 'error': 'MT5 not available'}
        
        try:
            with self._get_mt5() as mt5:
                result = mt5.cancel_order(ticket)
                
                # Remove from active orders
                if str(ticket) in self.active_pendings:
                    del self.active_pendings[str(ticket)]
                
                return result
        except Exception as e:
            logger.error(f"Error canceling order: {e}")
            return {'success': False, 'error': str(e)}
    
    def _start_oco_monitoring(self):
        """Start OCO monitoring thread."""
        if self._monitor_thread is None or not self._monitor_thread.is_alive():
            self._stop_monitoring.clear()
            self._monitor_thread = threading.Thread(target=self._monitor_ocos)
            self._monitor_thread.daemon = True
            self._monitor_thread.start()
            logger.info("OCO monitoring started")
    
    def _monitor_ocos(self):
        """Monitor OCO orders and cancel opposite order when one executes."""
        while not self._stop_monitoring.is_set():
            try:
                if not self.active_ocos:
                    time.sleep(5)
                    continue
                
                with self._get_mt5() as mt5:
                    for oco_id, oco in list(self.active_ocos.items()):
                        if oco.status != "open":
                            continue
                        
                        # Check if buy order executed
                        buy_executed = not mt5.is_order_pending(oco.buy_ticket)
                        # Check if sell order executed
                        sell_executed = not mt5.is_order_pending(oco.sell_ticket)
                        
                        if buy_executed and not sell_executed:
                            # Buy executed, cancel sell
                            mt5.cancel_order(oco.sell_ticket)
                            oco.executed_ticket = oco.buy_ticket
                            oco.status = "executed_buy"
                            logger.info(f"OCO {oco_id}: Buy executed, Sell cancelled")
                            
                            if NOTIFIER_AVAILABLE:
                                notify_trade("BUY", oco.symbol, oco.volume, oco.price_buy)
                        
                        elif sell_executed and not buy_executed:
                            # Sell executed, cancel buy
                            mt5.cancel_order(oco.buy_ticket)
                            oco.executed_ticket = oco.sell_ticket
                            oco.status = "executed_sell"
                            logger.info(f"OCO {oco_id}: Sell executed, Buy cancelled")
                            
                            if NOTIFIER_AVAILABLE:
                                notify_trade("SELL", oco.symbol, oco.volume, oco.price_sell)
                        
                        elif buy_executed and sell_executed:
                            # Both executed (rare edge case)
                            oco.status = "both_executed"
                            logger.warning(f"OCO {oco_id}: Both orders executed!")
                
                time.sleep(2)  # Check every 2 seconds
                
            except Exception as e:
                logger.error(f"Error in OCO monitoring: {e}")
                time.sleep(5)
    
    def stop_monitoring(self):
        """Stop OCO monitoring."""
        self._stop_monitoring.set()
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
            logger.info("OCO monitoring stopped")
    
    def get_active_orders(self) -> Dict[str, List[Dict]]:
        """Get all active orders summary."""
        return {
            'brackets': [b.__dict__ for b in self.active_brackets.values()],
            'ocos': [o.__dict__ for o in self.active_ocos.values()],
            'pendings': [p.__dict__ for p in self.active_pendings.values()]
        }


if __name__ == "__main__":
    # Test advanced orders
    manager = OrderManager()
    
    # Test Bracket Order
    print("Testing Bracket Order:")
    bracket = BracketOrder(
        symbol="XAUUSD",
        action="BUY",
        volume=0.1,
        entry_price=2950.00,
        stop_loss=2940.00,
        take_profit=2970.00
    )
    valid, msg = bracket.validate()
    print(f"  Valid: {valid}, Message: {msg}")
    
    # Test OCO Order
    print("\nTesting OCO Order:")
    oco = OCOOrder(
        symbol="XAUUSD",
        volume=0.1,
        price_buy=2945.00,
        price_sell=2955.00,
        stop_loss_points=50,
        take_profit_points=100
    )
    valid, msg = oco.validate()
    print(f"  Valid: {valid}, Message: {msg}")
    
    # Test Pending Order
    print("\nTesting Pending Order:")
    pending = PendingOrder(
        symbol="XAUUSD",
        action="BUY",
        volume=0.1,
        order_type="LIMIT",
        price=2940.00,
        stop_loss=2930.00,
        take_profit=2960.00
    )
    valid, msg = pending.validate(current_price=2950.00)
    print(f"  Valid: {valid}, Message: {msg}")
