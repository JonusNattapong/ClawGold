"""
Position Monitor
================
Monitors open positions and sends alerts based on P/L thresholds.
"""

import time
from typing import Optional, Callable
from mt5_manager import MT5Manager
from logger import get_logger

try:
    from notifier import get_notifier, PositionAlert
    NOTIFIER_AVAILABLE = True
except ImportError:
    NOTIFIER_AVAILABLE = False

logger = get_logger(__name__)


class PositionMonitor:
    """
    Monitors positions and triggers alerts.
    
    Usage:
        monitor = PositionMonitor(profit_alert=100, loss_alert=50)
        monitor.run()  # Blocks and monitors
    """
    
    def __init__(self, 
                 profit_alert: float = 100.0,
                 loss_alert: float = 50.0,
                 interval: int = 5,
                 on_alert: Optional[Callable] = None,
                 enable_telegram: bool = True):
        """
        Initialize position monitor.
        
        Args:
            profit_alert: Alert when total profit reaches this amount
            loss_alert: Alert when total loss reaches this amount
            interval: Check interval in seconds
            on_alert: Optional callback function for alerts
            enable_telegram: Enable Telegram notifications
        """
        self.profit_alert = profit_alert
        self.loss_alert = loss_alert
        self.interval = interval
        self.on_alert = on_alert or self._default_alert
        self.running = False
        self.last_alert_state = None
        self.enable_telegram = enable_telegram and NOTIFIER_AVAILABLE
        self._notifier = None
        self._last_telegram_alert_time = 0
        self._telegram_cooldown = 300  # 5 minutes between Telegram alerts
        
        if self.enable_telegram:
            try:
                self._notifier = get_notifier()
                if not self._notifier.enabled:
                    self.enable_telegram = False
                    logger.warning("Telegram notifier not configured")
            except Exception as e:
                logger.error(f"Failed to initialize Telegram notifier: {e}")
                self.enable_telegram = False
    
    def _default_alert(self, message: str, level: str = "info"):
        """Default alert handler - prints to console."""
        if level == "profit":
            print(f"\n[PROFIT ALERT] {message}")
        elif level == "loss":
            print(f"\n[LOSS ALERT] {message}")
        elif level == "margin":
            print(f"\n[MARGIN WARNING] {message}")
        else:
            print(f"\n[INFO] {message}")
    
    def _check_positions(self, positions: list, account_info: dict):
        """Check positions and trigger alerts."""
        if not positions:
            if self.last_alert_state != "no_positions":
                print(f"\n[NO POSITIONS] No open positions. Waiting...")
                self.last_alert_state = "no_positions"
            return
        
        total_profit = sum(p.get('profit', 0) + p.get('swap', 0) for p in positions)
        margin_level = account_info.get('margin_level', 0)
        symbol = positions[0].get('symbol', 'N/A')
        pos_count = len(positions)
        
        # Check profit alert
        if total_profit >= self.profit_alert:
            self.on_alert(
                f"Total P/L: +${total_profit:.2f} (Alert threshold: ${self.profit_alert})",
                "profit"
            )
            self.last_alert_state = "profit"
            self._send_telegram_alert(positions, total_profit, "profit")
        
        # Check loss alert
        elif total_profit <= -self.loss_alert:
            self.on_alert(
                f"Total P/L: ${total_profit:.2f} (Alert threshold: -${self.loss_alert})",
                "loss"
            )
            self.last_alert_state = "loss"
            self._send_telegram_alert(positions, total_profit, "loss")
        
        # Check margin level
        elif margin_level < 150 and margin_level > 0:
            self.on_alert(
                f"Margin level: {margin_level:.2f}%",
                "margin"
            )
            self.last_alert_state = "margin"
            self._send_telegram_alert(positions, total_profit, "margin_call")
        
        else:
            self.last_alert_state = "normal"
        
        # Print status line
        print(f"\r[STATUS] {symbol} | Positions: {pos_count} | P/L: ${total_profit:+.2f} | "
              f"Margin: {margin_level:.1f}% | Checking...", end="", flush=True)
    
    def _send_telegram_alert(self, positions: list, total_pnl: float, alert_type: str):
        """Send Telegram alert if cooldown has passed."""
        if not self.enable_telegram or not self._notifier:
            return
        
        current_time = time.time()
        if current_time - self._last_telegram_alert_time < self._telegram_cooldown:
            return
        
        try:
            # Get largest position for alert details
            largest_pos = max(positions, key=lambda p: abs(p.get('profit', 0)))
            
            pos_type = "BUY" if largest_pos.get('type') == 0 else "SELL"
            open_price = largest_pos.get('price_open', 0)
            current_price = largest_pos.get('price_current', 0)
            volume = largest_pos.get('volume', 0)
            symbol = largest_pos.get('symbol', 'XAUUSD')
            
            # Calculate PnL percentage
            pnl_percent = 0
            if open_price > 0:
                pnl_percent = ((current_price - open_price) / open_price) * 100
                if pos_type == "SELL":
                    pnl_percent = -pnl_percent
            
            alert = PositionAlert(
                symbol=symbol,
                position_type=pos_type,
                volume=volume,
                open_price=open_price,
                current_price=current_price,
                pnl=total_pnl,
                pnl_percent=pnl_percent,
                alert_type=alert_type
            )
            
            self._notifier.send_position_alert(alert)
            self._last_telegram_alert_time = current_time
            logger.info(f"Telegram alert sent: {alert_type}")
            
        except Exception as e:
            logger.error(f"Failed to send Telegram alert: {e}")
    
    def run(self):
        """Run the monitor loop."""
        self.running = True
        
        with MT5Manager() as mt5:
            while self.running:
                try:
                    positions = mt5.get_positions()
                    account = mt5.get_account_info()
                    
                    if account:
                        self._check_positions(positions, account)
                    
                    time.sleep(self.interval)
                    
                except Exception as e:
                    logger.error(f"Monitor error: {e}")
                    time.sleep(self.interval)
    
    def stop(self):
        """Stop the monitor."""
        self.running = False
        print("\n")
