"""
Telegram Notifier Module
========================
Sends notifications to Telegram for trading signals, position alerts,
and system events.

Usage:
    from notifier import TelegramNotifier
    
    notifier = TelegramNotifier()
    notifier.send_signal(symbol="XAUUSD", signal="BUY", confidence=0.85)
    notifier.send_position_alert(position, pnl, threshold)
    notifier.send_daily_summary(account_info)
"""

import os
import requests
from typing import Optional, Dict, Any, List
from datetime import datetime
from dataclasses import dataclass

from logger import get_logger

logger = get_logger(__name__)


@dataclass
class TradingSignal:
    """Trading signal data structure."""
    symbol: str
    action: str  # BUY, SELL, HOLD
    confidence: float
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    reason: Optional[str] = None


@dataclass
class PositionAlert:
    """Position alert data structure."""
    symbol: str
    position_type: str  # BUY or SELL
    volume: float
    open_price: float
    current_price: float
    pnl: float
    pnl_percent: float
    alert_type: str  # profit, loss, trailing_stop, etc.


class TelegramNotifier:
    """
    Telegram notification handler for ClawGold trading system.
    
    Requires:
        - TELEGRAM_BOT_TOKEN: Bot token from @BotFather
        - TELEGRAM_CHAT_ID: Chat ID or channel ID (e.g., -1002197548947)
    """
    
    def __init__(self, bot_token: Optional[str] = None, chat_id: Optional[str] = None):
        """
        Initialize Telegram notifier.
        
        Args:
            bot_token: Telegram bot token (or from TELEGRAM_BOT_TOKEN env)
            chat_id: Telegram chat/channel ID (or from TELEGRAM_CHAT_ID env)
        """
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID", "-1002197548947")
        self.enabled = bool(self.bot_token and self.chat_id)
        
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}" if self.bot_token else None
        
        if not self.enabled:
            logger.warning("Telegram notifier disabled: Missing bot token or chat ID")
        else:
            logger.info(f"Telegram notifier initialized for chat: {self.chat_id}")
    
    def _send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """
        Send message to Telegram.
        
        Args:
            text: Message text (HTML formatted)
            parse_mode: Parse mode (HTML, Markdown, MarkdownV2)
            
        Returns:
            True if sent successfully, False otherwise
        """
        if not self.enabled:
            logger.debug("Telegram notifier disabled, skipping message")
            return False
        
        try:
            url = f"{self.api_url}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True
            }
            
            response = requests.post(url, json=payload, timeout=30)
            response.raise_for_status()
            
            logger.debug(f"Telegram message sent successfully")
            return True
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending Telegram message: {e}")
            return False
    
    def send_signal(self, signal: TradingSignal) -> bool:
        """
        Send trading signal notification.
        
        Args:
            signal: TradingSignal object with signal details
            
        Returns:
            True if sent successfully
        """
        # Determine emoji based on action
        action_emoji = {
            "BUY": "🟢",
            "SELL": "🔴", 
            "HOLD": "🟡"
        }.get(signal.action.upper(), "⚪")
        
        # Confidence bar
        confidence_bars = int(signal.confidence * 10)
        confidence_bar = "█" * confidence_bars + "░" * (10 - confidence_bars)
        
        message = f"""
<b>{action_emoji} TRADING SIGNAL: {signal.action.upper()}</b>

<b>Symbol:</b> <code>{signal.symbol}</code>
<b>Confidence:</b> {signal.confidence:.0%} {confidence_bar}
"""
        
        if signal.entry_price:
            message += f"<b>Entry Price:</b> <code>{signal.entry_price:,.2f}</code>\n"
        if signal.stop_loss:
            message += f"<b>Stop Loss:</b> <code>{signal.stop_loss:,.2f}</code>\n"
        if signal.take_profit:
            message += f"<b>Take Profit:</b> <code>{signal.take_profit:,.2f}</code>\n"
        if signal.reason:
            message += f"\n<b>Reason:</b>\n{signal.reason}\n"
        
        message += f"\n<i>🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</i>"
        
        return self._send_message(message)
    
    def send_position_alert(self, alert: PositionAlert) -> bool:
        """
        Send position alert notification.
        
        Args:
            alert: PositionAlert object with alert details
            
        Returns:
            True if sent successfully
        """
        # Determine emoji based on P&L
        if alert.pnl > 0:
            pnl_emoji = "🟢"
        elif alert.pnl < 0:
            pnl_emoji = "🔴"
        else:
            pnl_emoji = "⚪"
        
        # Alert type emoji
        alert_emoji = {
            "profit": "💰",
            "loss": "⚠️",
            "trailing_stop": "🛡️",
            "tp_hit": "🎯",
            "sl_hit": "🛑",
            "margin_call": "🚨"
        }.get(alert.alert_type, "📊")
        
        message = f"""
<b>{alert_emoji} POSITION ALERT: {alert.alert_type.upper()}</b>

<b>Symbol:</b> <code>{alert.symbol}</code>
<b>Type:</b> {alert.position_type}
<b>Volume:</b> <code>{alert.volume:.2f}</code>

<b>Open Price:</b> <code>{alert.open_price:,.2f}</code>
<b>Current Price:</b> <code>{alert.current_price:,.2f}</code>

<b>P/L:</b> {pnl_emoji} <code>{alert.pnl:+.2f} USD ({alert.pnl_percent:+.2f}%)</code>

<i>🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</i>
"""
        
        return self._send_message(message)
    
    def send_trade_executed(self, symbol: str, action: str, volume: float, 
                           price: float, sl: Optional[float] = None, 
                           tp: Optional[float] = None) -> bool:
        """
        Send trade execution notification.
        
        Args:
            symbol: Trading symbol
            action: BUY or SELL
            volume: Trade volume
            price: Execution price
            sl: Stop loss price (optional)
            tp: Take profit price (optional)
            
        Returns:
            True if sent successfully
        """
        action_emoji = "🟢" if action.upper() == "BUY" else "🔴"
        
        message = f"""
<b>{action_emoji} TRADE EXECUTED: {action.upper()}</b>

<b>Symbol:</b> <code>{symbol}</code>
<b>Volume:</b> <code>{volume:.2f}</code>
<b>Price:</b> <code>{price:,.2f}</code>
"""
        if sl:
            message += f"<b>Stop Loss:</b> <code>{sl:,.2f}</code>\n"
        if tp:
            message += f"<b>Take Profit:</b> <code>{tp:,.2f}</code>\n"
        
        message += f"\n<i>🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</i>"
        
        return self._send_message(message)
    
    def send_daily_summary(self, account_info: Dict[str, Any], 
                          positions: List[Dict] = None) -> bool:
        """
        Send daily trading summary.
        
        Args:
            account_info: Dictionary with account balance, equity, etc.
            positions: List of open positions
            
        Returns:
            True if sent successfully
        """
        balance = account_info.get('balance', 0)
        equity = account_info.get('equity', 0)
        profit = account_info.get('profit', 0)
        margin_level = account_info.get('margin_level', 0)
        
        # Determine overall status emoji
        if profit > 0:
            status_emoji = "🟢"
        elif profit < 0:
            status_emoji = "🔴"
        else:
            status_emoji = "⚪"
        
        message = f"""
<b>📊 DAILY TRADING SUMMARY</b>

<b>Account Balance:</b> <code>{balance:,.2f} USD</code>
<b>Equity:</b> <code>{equity:,.2f} USD</code>
<b>Today's P/L:</b> {status_emoji} <code>{profit:+.2f} USD</code>
<b>Margin Level:</b> <code>{margin_level:.2f}%</code>
"""
        
        if positions:
            message += f"\n<b>Open Positions:</b> {len(positions)}\n"
            total_pnl = sum(p.get('profit', 0) + p.get('swap', 0) for p in positions)
            message += f"<b>Total Open P/L:</b> <code>{total_pnl:+.2f} USD</code>\n"
        
        message += f"\n<i>🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</i>"
        
        return self._send_message(message)
    
    def send_system_alert(self, message_text: str, level: str = "info") -> bool:
        """
        Send system-level alert.
        
        Args:
            message_text: Alert message
            level: Alert level (info, warning, error, critical)
            
        Returns:
            True if sent successfully
        """
        level_emoji = {
            "info": "ℹ️",
            "warning": "⚠️",
            "error": "❌",
            "critical": "🚨"
        }.get(level.lower(), "ℹ️")
        
        message = f"""
<b>{level_emoji} SYSTEM ALERT: {level.upper()}</b>

{message_text}

<i>🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</i>
"""
        return self._send_message(message)
    
    def send_news_alert(self, title: str, summary: str, sentiment: str,
                       impact: str = "medium") -> bool:
        """
        Send news-based alert.
        
        Args:
            title: News title
            summary: News summary
            sentiment: BULLISH, BEARISH, or NEUTRAL
            impact: high, medium, or low
            
        Returns:
            True if sent successfully
        """
        sentiment_emoji = {
            "BULLISH": "🟢📈",
            "BEARISH": "🔴📉",
            "NEUTRAL": "⚪➡️"
        }.get(sentiment.upper(), "⚪")
        
        impact_emoji = {
            "high": "🔴",
            "medium": "🟡",
            "low": "🟢"
        }.get(impact.lower(), "⚪")
        
        message = f"""
<b>📰 NEWS ALERT {impact_emoji} {impact.upper()} IMPACT</b>

<b>Sentiment:</b> {sentiment_emoji} {sentiment.upper()}

<b>{title}</b>

{summary}

<i>🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</i>
"""
        return self._send_message(message)


# Singleton instance for global use
_notifier_instance: Optional[TelegramNotifier] = None


def get_notifier() -> TelegramNotifier:
    """Get or create singleton notifier instance."""
    global _notifier_instance
    if _notifier_instance is None:
        _notifier_instance = TelegramNotifier()
    return _notifier_instance


def notify_signal(symbol: str, action: str, confidence: float, **kwargs) -> bool:
    """Quick function to send trading signal notification."""
    signal = TradingSignal(symbol=symbol, action=action, confidence=confidence, **kwargs)
    return get_notifier().send_signal(signal)


def notify_trade(action: str, symbol: str, volume: float, price: float, **kwargs) -> bool:
    """Quick function to send trade execution notification."""
    return get_notifier().send_trade_executed(symbol, action, volume, price, **kwargs)


def notify_alert(symbol: str, position_type: str, volume: float, open_price: float,
                current_price: float, pnl: float, pnl_percent: float, 
                alert_type: str) -> bool:
    """Quick function to send position alert."""
    alert = PositionAlert(
        symbol=symbol,
        position_type=position_type,
        volume=volume,
        open_price=open_price,
        current_price=current_price,
        pnl=pnl,
        pnl_percent=pnl_percent,
        alert_type=alert_type
    )
    return get_notifier().send_position_alert(alert)


def notify_system(message: str, level: str = "info") -> bool:
    """Quick function to send system alert."""
    return get_notifier().send_system_alert(message, level)


if __name__ == "__main__":
    # Test the notifier
    import os
    
    print("Testing Telegram Notifier...")
    print(f"Bot Token exists: {bool(os.getenv('TELEGRAM_BOT_TOKEN'))}")
    print(f"Chat ID: {os.getenv('TELEGRAM_CHAT_ID', '-1002197548947')}")
    
    notifier = TelegramNotifier()
    
    # Test signal
    test_signal = TradingSignal(
        symbol="XAUUSD",
        action="BUY",
        confidence=0.85,
        entry_price=2950.50,
        stop_loss=2940.00,
        take_profit=2970.00,
        reason="Strong bullish momentum detected. EMA crossover on H1 timeframe with positive news sentiment."
    )
    
    print("\nSending test signal...")
    result = notifier.send_signal(test_signal)
    print(f"Signal sent: {result}")
