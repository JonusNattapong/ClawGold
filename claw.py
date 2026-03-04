#!/usr/bin/env python3
"""
ClawGold Unified CLI Entry Point
================================
Main command-line interface for ClawGold trading system.

Usage:
    python claw.py balance          # Check account balance
    python claw.py positions        # List open positions
    python claw.py price            # Get current XAUUSD price
    python claw.py trade BUY 0.1    # Execute trade
    python claw.py monitor          # Start position monitor
    python claw.py backtest         # Run backtest
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent / "scripts"))

from logger import get_logger
from config_loader import load_config

logger = get_logger(__name__)


def cmd_balance(args):
    """Check account balance."""
    from mt5_manager import MT5Manager

    with MT5Manager() as mt5:
        account = mt5.get_account_info()
        if account:
            print(f"\n{'='*40}")
            print(f"Account Balance:    {account['balance']:>12.2f} USD")
            print(f"Account Equity:     {account['equity']:>12.2f} USD")
            print(f"Used Margin:        {account['margin']:>12.2f} USD")
            print(f"Free Margin:        {account['margin_free']:>12.2f} USD")
            print(f"Profit/Loss:        {account['profit']:>12.2f} USD")
            print(f"Margin Level:       {account['margin_level']:>12.2f}%")
            print(f"{'='*40}\n")
        else:
            print("Failed to retrieve account information.")
            sys.exit(1)


def cmd_positions(args):
    """List open positions."""
    from mt5_manager import MT5Manager

    with MT5Manager() as mt5:
        symbol = args.symbol if args.symbol else mt5.config['trading']['symbol']
        positions = mt5.get_positions(symbol)
        
        if not positions:
            print(f"\nNo open positions for {symbol}.\n")
            return
        
        print(f"\n{'='*70}")
        print(f"Open Positions for {symbol}")
        print(f"{'='*70}")
        print(f"{'Type':<6} {'Volume':>10} {'Open Price':>12} {'Current':>12} {'P/L':>12} {'Swap':>10}")
        print(f"{'-'*70}")
        
        total_profit = 0
        for pos in positions:
            type_str = "BUY" if pos['type'] == 0 else "SELL"
            print(f"{type_str:<6} {pos['volume']:>10.2f} {pos['price_open']:>12.2f} "
                  f"{pos['price_current']:>12.2f} {pos['profit']:>12.2f} {pos['swap']:>10.2f}")
            total_profit += pos['profit'] + pos['swap']
        
        print(f"{'-'*70}")
        print(f"{'Total P/L:':<30} {total_profit:>39.2f} USD")
        print(f"{'='*70}\n")


def cmd_price(args):
    """Get current XAUUSD price."""
    from mt5_manager import MT5Manager

    with MT5Manager() as mt5:
        symbol = args.symbol if args.symbol else mt5.config['trading']['symbol']
        tick = mt5.get_tick(symbol)
        if tick:
            spread = tick['ask'] - tick['bid']
            print(f"\n{'='*40}")
            print(f"{symbol} Price")
            print(f"{'='*40}")
            print(f"Bid:    {tick['bid']:>10.3f} USD")
            print(f"Ask:    {tick['ask']:>10.3f} USD")
            print(f"Spread: {spread:>10.3f} USD")
            print(f"Time:   {tick['time']}")
            print(f"{'='*40}\n")
        else:
            print(f"Failed to get price for {symbol}.")
            sys.exit(1)


def cmd_trade(args):
    """Execute a trade."""
    from mt5_manager import MT5Manager
    from risk_manager import RiskManager
    from notifier import get_notifier
    from trade_journal import TradeJournal, JournalEntry

    with MT5Manager() as mt5:
        rm = RiskManager(mt5.config)
        notifier = get_notifier()
        journal = TradeJournal()
        
        # Validate trade with risk manager
        symbol = mt5.config['trading']['symbol']
        action = args.action.upper()
        volume = args.volume
        
        # Check risk limits
        can_trade, reason = rm.can_trade(symbol, action, volume)
        if not can_trade:
            print(f"\n❌ Trade rejected: {reason}\n")
            notifier.send_system_alert(f"Trade rejected: {reason}", level="warning")
            sys.exit(1)
        
        # Execute trade
        result = mt5.execute_trade(action, volume)
        if result['success']:
            account = mt5.get_account_info()
            snapshot = {
                'source': 'manual',
                'query': args.reason or f"{symbol} trade rationale",
                'summary': args.reason or 'Manual execution without explicit rationale',
                'consensus_sentiment': args.market_condition,
                'tools_used': ['manual'],
                'captured_at': datetime.now().isoformat()
            }

            journal.add_entry(JournalEntry(
                action=action,
                symbol=symbol,
                volume=result['volume'],
                price=result['price'],
                ticket=result.get('order'),
                strategy=args.strategy,
                market_condition=args.market_condition,
                reason=args.reason or '',
                ai_research_snapshot=snapshot,
                metadata={'source_command': 'trade'},
                account_equity=(account.get('equity') if account else None)
            ))

            print(f"\n✅ Trade executed successfully!")
            print(f"Order ID: {result['order']}")
            print(f"Volume:   {result['volume']:.2f} lots")
            print(f"Price:    {result['price']:.3f} USD")
            print(f"{'='*40}\n")
            
            # Send Telegram notification
            notifier.send_trade_executed(
                symbol=symbol,
                action=action,
                volume=result['volume'],
                price=result['price']
            )
        else:
            print(f"\n❌ Trade failed: {result['error']}\n")
            notifier.send_system_alert(f"Trade failed: {result['error']}", level="error")
            sys.exit(1)


def cmd_close(args):
    """Close position(s)."""
    from mt5_manager import MT5Manager
    from trade_journal import TradeJournal, JournalEntry

    with MT5Manager() as mt5:
        journal = TradeJournal()
        if args.all:
            results = mt5.close_all_positions()
            account = mt5.get_account_info()
            print(f"\n{'='*40}")
            print(f"Closed {len(results)} positions")
            for r in results:
                status = "✅" if r['success'] else "❌"
                print(f"{status} Position {r.get('ticket', 'N/A')}: {r.get('message', '')}")
                if r['success']:
                    journal.add_entry(JournalEntry(
                        action='CLOSE',
                        symbol=mt5.config['trading']['symbol'],
                        volume=0,
                        price=r.get('price', 0),
                        ticket=r.get('ticket'),
                        strategy=args.strategy,
                        market_condition=args.market_condition,
                        reason=args.reason or '',
                        realized_pnl=r.get('profit'),
                        metadata={'source_command': 'close --all'},
                        account_equity=(account.get('equity') if account else None)
                    ))
            print(f"{'='*40}\n")
        elif args.ticket:
            result = mt5.close_position(args.ticket)
            if result['success']:
                account = mt5.get_account_info()
                journal.add_entry(JournalEntry(
                    action='CLOSE',
                    symbol=mt5.config['trading']['symbol'],
                    volume=0,
                    price=result.get('price', 0),
                    ticket=args.ticket,
                    strategy=args.strategy,
                    market_condition=args.market_condition,
                    reason=args.reason or '',
                    realized_pnl=result.get('profit'),
                    metadata={'source_command': 'close --ticket'},
                    account_equity=(account.get('equity') if account else None)
                ))
                print(f"\n✅ Position {args.ticket} closed successfully")
                print(f"Profit: {result.get('profit', 0):.2f} USD\n")
            else:
                print(f"\n❌ Failed to close position: {result['error']}\n")
        else:
            print("\n❌ Please specify --all or --ticket <ticket_id>\n")
            sys.exit(1)


def cmd_monitor(args):
    """Start position monitor."""
    from position_monitor import PositionMonitor

    print("\n[MONITOR] Starting position monitor...")
    print("Press Ctrl+C to stop\n")
    
    monitor = PositionMonitor(
        profit_alert=args.profit_alert,
        loss_alert=args.loss_alert,
        interval=args.interval
    )
    try:
        monitor.run()
    except KeyboardInterrupt:
        print("\n\n[STOPPED] Monitor stopped.")


def cmd_backtest(args):
    """Run backtest."""
    print("\n[BACKTEST] Running backtest...")
    # Import and run backtest
    import backtest
    backtest.run(
        symbol=args.symbol,
        period=args.period,
        strategy=args.strategy
    )


def cmd_validate(args):
    """Validate configuration."""
    from config_validator import ConfigValidator

    print("\n[VALIDATE] Validating configuration...")
    validator = ConfigValidator()
    errors = validator.validate()
    
    if errors:
        print("\n[ERROR] Configuration errors found:")
        for error in errors:
            print(f"  • {error}")
        sys.exit(1)
    else:
        print("\n[OK] Configuration is valid!\n")


def cmd_trailing_stop(args):
    """Apply trailing stop to a position."""
    from advanced_trader import AdvancedTrader, TrailingStopConfig

    print(f"\n[TRAILING STOP] Applying to position {args.ticket}...")
    
    config = load_config(str(Path(__file__).parent / "config.yaml"))
    trader = AdvancedTrader(config)
    
    ts_config = TrailingStopConfig(
        activation_profit=args.activation,
        trailing_distance=args.distance,
        step_size=args.step
    )
    
    if trader.apply_trailing_stop(args.ticket, ts_config):
        print(f"[OK] Trailing stop applied to position {args.ticket}")
        print(f"  Activation: {args.activation} points")
        print(f"  Trail distance: {args.distance} points")
        print(f"  Step size: {args.step} points")
    else:
        print(f"[ERROR] Failed to apply trailing stop")
        sys.exit(1)


def cmd_grid(args):
    """Start grid trading."""
    from mt5_manager import MT5Manager
    from advanced_trader import AdvancedTrader, GridConfig

    print(f"\n[GRID TRADING] Initializing grid...")
    
    config = load_config(str(Path(__file__).parent / "config.yaml"))
    trader = AdvancedTrader(config)
    
    with MT5Manager() as mt5:
        symbol = config['trading']['symbol']
        tick = mt5.get_tick(symbol)
        if not tick:
            print("[ERROR] Failed to get current price")
            sys.exit(1)
        
        center_price = (tick['bid'] + tick['ask']) / 2
    
    grid_config = GridConfig(
        levels=args.levels,
        grid_size=args.grid_size,
        volume_per_level=args.volume,
        take_profit=args.take_profit,
        stop_loss=args.stop_loss
    )
    
    levels = trader.start_grid_trading(grid_config, center_price, args.direction)
    
    print(f"[OK] Grid initialized with {len(levels)} levels")
    print(f"  Center price: {center_price:.3f}")
    print(f"  Direction: {args.direction}")
    print(f"  Grid size: {args.grid_size} points")
    print(f"  Volume per level: {args.volume} lots")
    print(f"\nLevels:")
    for lvl in levels:
        status = "[ACTIVATED]" if lvl.activated else "[PENDING]"
        print(f"  {status} {lvl.order_type.upper()} @ {lvl.price:.3f} ({lvl.volume} lots)")


def cmd_breakout(args):
    """Run breakout detection and trading."""
    from advanced_trader import AdvancedTrader, BreakoutConfig

    print(f"\n[BREAKOUT] Analyzing {args.symbol}...")
    
    config = load_config(str(Path(__file__).parent / "config.yaml"))
    trader = AdvancedTrader(config)
    
    breakout_config = BreakoutConfig(
        lookback_period=args.lookback,
        breakout_threshold=args.threshold,
        volume_multiplier=args.volume_mult,
        confirmation_bars=args.confirmation
    )
    
    is_breakout, direction = trader.detect_breakout(args.symbol, breakout_config)
    
    if is_breakout:
        print(f"[ALERT] Breakout detected: {direction.upper()}")
        
        if args.execute:
            print(f"[EXECUTING] {direction.upper()} trade...")
            result = trader.execute_breakout_trade(args.symbol, direction, args.volume)
            
            if result['success']:
                print(f"[OK] Trade executed successfully")
                print(f"  Order ID: {result.get('order', 'N/A')}")
                print(f"  Volume: {result.get('volume', 0):.2f} lots")
                print(f"  Price: {result.get('price', 0):.3f}")
            else:
                print(f"[ERROR] Trade failed: {result.get('error', 'Unknown')}")
    else:
        print(f"[INFO] No breakout detected")


def cmd_analyze(args):
    """Multi-timeframe analysis."""
    from advanced_trader import AdvancedTrader

    print(f"\n[ANALYSIS] Multi-timeframe analysis for {args.symbol}...")
    
    config = load_config(str(Path(__file__).parent / "config.yaml"))
    trader = AdvancedTrader(config)
    
    analysis = trader.multi_timeframe_analysis(args.symbol)
    
    print(f"\n{'='*60}")
    print(f"Multi-Timeframe Analysis: {args.symbol}")
    print(f"{'='*60}")
    
    for tf, data in analysis['timeframes'].items():
        print(f"\n[{tf}]")
        print(f"  Signal: {data['signal'].upper()}")
        print(f"  Price: {data['price']:.3f}")
        print(f"  EMA 20: {data['ema_20']:.3f}")
        print(f"  EMA 50: {data['ema_50']:.3f}")
    
    print(f"\n{'='*60}")
    print(f"Overall Signal: {analysis['overall_signal'].upper()}")
    print(f"Confluence Score: {analysis['confluence_score']:.2f}")
    print(f"{'='*60}\n")


def cmd_scalp(args):
    """Run scalping strategy."""
    from advanced_trader import AdvancedTrader

    print(f"\n[SCALPING] Starting scalping strategy...")
    print(f"Duration: {args.duration} minutes")
    print(f"Profit target: {args.profit_target} points")
    print(f"Max loss: {args.max_loss} points")
    print(f"Press Ctrl+C to stop early\n")
    
    config = load_config(str(Path(__file__).parent / "config.yaml"))
    trader = AdvancedTrader(config)
    
    try:
        results = trader.run_scalping_strategy(
            args.symbol,
            duration_minutes=args.duration,
            profit_target=args.profit_target,
            max_loss=args.max_loss
        )
        
        print(f"\n{'='*40}")
        print(f"Scalping Results")
        print(f"{'='*40}")
        print(f"Trades executed: {results['trades_executed']}")
        print(f"Total P/L: {results['total_profit']:.2f} USD")
        print(f"Duration: {results['duration']} minutes")
        print(f"{'='*40}\n")
    except KeyboardInterrupt:
        print("\n[STOPPED] Scalping stopped by user")


def cmd_news_research(args):
    """Research symbol with AI tools."""
    from news_aggregator import NewsAggregator

    print(f"\n[NEWS RESEARCH] Researching {args.symbol}...")
    print(f"Query: {args.query or 'Default market analysis'}")
    print("This may take 1-2 minutes while AI tools process...\n")

    aggregator = NewsAggregator()

    results = aggregator.research_symbol(
        symbol=args.symbol,
        query=args.query,
        hours=args.hours,
        use_ai=not args.no_ai
    )

    print(f"\n{'='*70}")
    print(f"Research Results: {args.symbol}")
    print(f"{'='*70}")

    print(f"\nCached News Items: {len(results['cached_news'])}")

    if results['ai_analysis']:
        ai = results['ai_analysis']
        print(f"\n[AI Analysis]")
        print(f"  Tools Used: {', '.join(ai.get('tools_used', []))}")
        print(f"  Consensus: {ai.get('consensus_sentiment', 'N/A').upper()}")
        print(f"  Agreement: {ai.get('consensus_strength', 0):.0%}")
        print(f"  Avg Confidence: {(ai.get('average_confidence') or 0):.0%}")

        print(f"\n  Sentiment Distribution:")
        for sent, count in ai.get('sentiment_distribution', {}).items():
            print(f"    - {sent.capitalize()}: {count}")

    if results['sentiment']:
        sent = results['sentiment']
        print(f"\n[Overall Sentiment]")
        print(f"  Direction: {sent.get('dominant_sentiment', 'neutral').upper()}")
        print(f"  Score: {sent.get('average_score', 0):.2f}")
        print(f"  Confidence: {sent.get('average_confidence', 0):.2f}")
        print(f"  Top Keywords: {', '.join(sent.get('all_keywords', [])[:5])}")

    print(f"\n{'='*70}\n")


def cmd_news_sentiment(args):
    """Get sentiment analysis for symbol."""
    from news_aggregator import NewsAggregator

    print(f"\n[NEWS SENTIMENT] Analyzing {args.symbol}...")

    aggregator = NewsAggregator()

    if args.trend:
        print(f"\nSentiment Trend (last {args.hours} hours):")
        trend = aggregator.get_sentiment_trend(args.symbol, args.hours)

        print(f"\n  Current Trend: {trend.get('trend', 'unknown').upper()}")
        print(f"  Momentum: {trend.get('momentum', 0):.3f}")
        print(f"  Current Sentiment: {trend.get('current_sentiment', 0):.2f}")
        print(f"  Data Points: {trend.get('data_points', 0)}")

        if trend.get('history'):
            print(f"\n  History:")
            for h in trend['history'][-5:]:
                print(f"    {h['timestamp']}: {h['sentiment']:.2f} ({h['news_count']} news)")
    else:
        results = aggregator.research_symbol(args.symbol, use_ai=False)

        if results['sentiment']:
            sent = results['sentiment']
            print(f"\n{'='*60}")
            print(f"Sentiment Analysis: {args.symbol}")
            print(f"{'='*60}")
            print(f"  Direction: {sent.get('dominant_sentiment', 'neutral').upper()}")
            print(f"  Score: {sent.get('average_score', 0):.2f}")
            print(f"  Confidence: {sent.get('average_confidence', 0):.2f}")

            print(f"\n  Distribution:")
            for k, v in sent.get('sentiment_distribution', {}).items():
                print(f"    {k.capitalize()}: {v}")

            print(f"\n  Top Keywords:")
            for kw, count in sent.get('keyword_frequency', {}).items():
                print(f"    - {kw}: {count}")

            print(f"\n{'='*60}")


def cmd_news_signal(args):
    """Get trading signal from news analysis."""
    from news_aggregator import NewsAggregator
    from notifier import get_notifier, TradingSignal

    print(f"\n[NEWS SIGNAL] Generating trading signal for {args.symbol}...")
    print("Analyzing news sentiment with AI...\n")

    aggregator = NewsAggregator()
    notifier = get_notifier()

    results = aggregator.research_symbol(
        symbol=args.symbol,
        query=args.query,
        use_ai=True
    )

    signal = results.get('trading_signal', {})

    print(f"\n{'='*60}")
    print(f"Trading Signal: {args.symbol}")
    print(f"{'='*60}")

    direction = signal.get('direction', 'neutral').upper()
    confidence = signal.get('confidence', 0)
    strength = signal.get('strength', 0)
    rec = signal.get('recommendation', 'hold')

    print(f"\n  Signal: {direction}")
    print(f"  Confidence: {confidence:.0%}")
    print(f"  Strength: {strength}/3")
    print(f"  Recommendation: {rec.upper()}")

    factors = signal.get('factors', [])
    if factors:
        print(f"\n  Factors:")
        for f in factors:
            print(f"    - {f}")

    print(f"\n{'='*60}")

    # Send Telegram notification for signal
    if direction in ['BUY', 'SELL']:
        reason_text = "; ".join(factors) if factors else f"AI analysis shows {direction} opportunity"
        trading_signal = TradingSignal(
            symbol=args.symbol,
            action=direction,
            confidence=confidence,
            reason=reason_text[:500]  # Limit length
        )
        notifier.send_signal(trading_signal)

    # Warning for high confidence signals
    if confidence > 0.7:
        print(f"\n[!] High confidence signal detected!")
        print(f"    Consider taking action: {rec.upper()}")
    elif confidence < 0.3:
        print(f"\n[!] Low confidence - consider staying neutral")


def cmd_news_stats(args):
    """Show news database statistics."""
    from news_aggregator import NewsAggregator

    print(f"\n[NEWS STATS] Database Statistics")

    aggregator = NewsAggregator()
    stats = aggregator.get_stats()

    print(f"\n{'='*60}")
    print(f"News Database Statistics")
    print(f"{'='*60}")

    print(f"\n  Articles:          {stats.get('news_articles', 0):,}")
    print(f"  AI Research:       {stats.get('ai_research', 0):,}")
    print(f"  Market Events:     {stats.get('market_events', 0):,}")
    print(f"  Sentiment History: {stats.get('sentiment_history', 0):,}")

    print(f"\n{'='*60}\n")


def cmd_news_cleanup(args):
    """Clean old news data."""
    from news_aggregator import NewsAggregator

    print(f"\n[NEWS CLEANUP] Cleaning data older than {args.days} days...")

    aggregator = NewsAggregator()
    aggregator.cleanup_old_data(args.days)

    print(f"[OK] Cleanup complete")


def cmd_journal_add(args):
    """Add manual trade journal entry."""
    from trade_journal import TradeJournal, JournalEntry

    journal = TradeJournal()
    entry_id = journal.add_entry(JournalEntry(
        action=args.action,
        symbol=args.symbol,
        volume=args.volume,
        price=args.price,
        strategy=args.strategy,
        market_condition=args.market_condition,
        reason=args.reason,
        realized_pnl=args.pnl,
        ai_research_snapshot={
            'source': 'manual',
            'summary': args.ai_snapshot,
            'captured_at': datetime.now().isoformat()
        } if args.ai_snapshot else None,
    ))
    print(f"\n[OK] Trade journal entry created: {entry_id}\n")


def cmd_journal_analytics(args):
    """Show trade journal analytics."""
    from trade_journal import TradeJournal

    journal = TradeJournal()
    data = journal.get_analytics(days=args.days)

    print(f"\n{'='*70}")
    print(f"Trade Journal Analytics ({args.days} days)")
    print(f"{'='*70}")
    print(f"Total Entries: {data['total_entries']}")
    print(f"Closed Trades: {data['total_closed']}")
    print(f"Overall Win Rate: {data['overall_win_rate']:.2%}")

    print("\nWin Rate by Strategy")
    for key, value in data['win_rate_by_strategy'].items():
        print(f"  - {key}: {value['win_rate']:.2%} ({value['wins']}/{value['total']})")

    print("\nWin Rate by Time Bucket")
    for key, value in data['win_rate_by_time'].items():
        print(f"  - {key}: {value['win_rate']:.2%} ({value['wins']}/{value['total']})")

    print("\nWin Rate by Market Condition")
    for key, value in data['win_rate_by_market_condition'].items():
        print(f"  - {key}: {value['win_rate']:.2%} ({value['wins']}/{value['total']})")
    print(f"{'='*70}\n")


def cmd_journal_equity(args):
    """Show equity curve points."""
    from trade_journal import TradeJournal

    journal = TradeJournal()
    points = journal.get_equity_curve(days=args.days)

    print(f"\n{'='*70}")
    print(f"Equity Curve ({args.days} days)")
    print(f"{'='*70}")
    if not points:
        print("No equity data points found.")
    else:
        for p in points:
            print(f"{p['timestamp']} | Equity: {p['equity']:.2f} | {p['action']} {p['symbol']}")
    print(f"{'='*70}\n")


def cmd_notify_test(args):
    """Test Telegram notification."""
    from notifier import get_notifier, TradingSignal, PositionAlert

    print("\n[NOTIFY TEST] Testing Telegram notifications...")
    
    notifier = get_notifier()
    
    if not notifier.enabled:
        print("\n❌ Telegram notifier is disabled.")
        print("   Please set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in your .env file")
        sys.exit(1)
    
    print(f"Bot Token: {'*' * 10}...{notifier.bot_token[-4:] if notifier.bot_token else 'None'}")
    print(f"Chat ID: {notifier.chat_id}")
    print("\nSending test notifications...")
    
    # Test signal notification
    if args.type in ['all', 'signal']:
        print("  → Sending signal notification...")
        signal = TradingSignal(
            symbol="XAUUSD",
            action="BUY",
            confidence=0.85,
            entry_price=2950.50,
            stop_loss=2940.00,
            take_profit=2970.00,
            reason="Test signal - EMA crossover detected with bullish momentum"
        )
        result = notifier.send_signal(signal)
        print(f"    {'✅ Sent' if result else '❌ Failed'}")
    
    # Test trade notification
    if args.type in ['all', 'trade']:
        print("  → Sending trade notification...")
        result = notifier.send_trade_executed(
            symbol="XAUUSD",
            action="BUY",
            volume=0.5,
            price=2950.50,
            sl=2940.00,
            tp=2970.00
        )
        print(f"    {'✅ Sent' if result else '❌ Failed'}")
    
    # Test position alert
    if args.type in ['all', 'alert']:
        print("  → Sending position alert...")
        alert = PositionAlert(
            symbol="XAUUSD",
            position_type="BUY",
            volume=0.5,
            open_price=2940.00,
            current_price=2955.00,
            pnl=75.00,
            pnl_percent=0.51,
            alert_type="profit"
        )
        result = notifier.send_position_alert(alert)
        print(f"    {'✅ Sent' if result else '❌ Failed'}")
    
    # Test system alert
    if args.type in ['all', 'system']:
        print("  → Sending system alert...")
        result = notifier.send_system_alert(
            "This is a test system alert from ClawGold!",
            level="info"
        )
        print(f"    {'✅ Sent' if result else '❌ Failed'}")
    
    print("\n✅ Test complete!")


def cmd_notify_daily(args):
    """Send daily summary notification."""
    from mt5_manager import MT5Manager
    from notifier import get_notifier

    print("\n[NOTIFY DAILY] Sending daily summary...")
    
    notifier = get_notifier()
    
    if not notifier.enabled:
        print("\n❌ Telegram notifier is disabled.")
        sys.exit(1)
    
    with MT5Manager() as mt5:
        account = mt5.get_account_info()
        symbol = mt5.config['trading']['symbol']
        positions = mt5.get_positions(symbol)
        
        if account:
            result = notifier.send_daily_summary(account, positions)
            if result:
                print("✅ Daily summary sent successfully!")
            else:
                print("❌ Failed to send daily summary")
        else:
            print("❌ Failed to get account information")


def cmd_calendar_today(args):
    """Show today's economic events."""
    from economic_calendar import EconomicCalendar

    print("\n[CALENDAR] Today's Economic Events")
    print("="*70)
    
    calendar = EconomicCalendar()
    events = calendar.get_today_events()
    
    if not events:
        print("No events found. Try running 'calendar update' first.")
    else:
        for event in events:
            impact_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(event.impact, "⚪")
            print(f"{impact_emoji} {event.datetime.strftime('%H:%M')} | {event.currency} | {event.title}")
            if event.forecast or event.previous:
                print(f"   Forecast: {event.forecast or 'N/A'} | Previous: {event.previous or 'N/A'}")
    print("="*70)


def cmd_calendar_update(args):
    """Update economic calendar with AI."""
    from economic_calendar import EconomicCalendar

    print("\n[CALENDAR] Updating economic calendar with AI...")
    print("This may take 1-2 minutes...")
    
    calendar = EconomicCalendar()
    calendar.update_calendar()
    
    print("\n✅ Calendar updated successfully!")


def cmd_calendar_check(args):
    """Check if trading should be paused."""
    from economic_calendar import EconomicCalendar

    print("\n[CALENDAR] Checking trading status...")
    print("="*70)
    
    calendar = EconomicCalendar()
    
    if calendar.should_pause_trading():
        print("⚠️  TRADING IS PAUSED")
        if calendar.pause_until:
            print(f"   Will resume at: {calendar.pause_until.strftime('%Y-%m-%d %H:%M')}")
        
        # Show upcoming high impact events
        events = calendar.get_upcoming_high_impact_events(minutes=120)
        if events:
            print("\n   Upcoming high impact events:")
            for event in events:
                print(f"   - {event.title} at {event.datetime.strftime('%H:%M')}")
    else:
        print("✅ Trading is active")
        
        # Show next high impact event
        next_event = calendar.get_next_high_impact_event()
        if next_event:
            time_until = next_event.time_until()
            hours = int(time_until.total_seconds() // 3600)
            minutes = int((time_until.total_seconds() % 3600) // 60)
            print(f"\n   Next high impact event: {next_event.title}")
            print(f"   Time until event: {hours}h {minutes}m")
    
    print("="*70)


def cmd_order_bracket(args):
    """Place bracket order."""
    from advanced_orders import OrderManager, BracketOrder

    print(f"\n[ORDER] Placing Bracket Order...")
    print("="*70)
    
    bracket = BracketOrder(
        symbol="XAUUSD",  # Default symbol
        action=args.action.upper(),
        volume=args.volume,
        entry_price=args.entry,
        stop_loss=args.stop_loss,
        take_profit=args.take_profit
    )
    
    manager = OrderManager()
    result = manager.place_bracket_order(bracket)
    
    if result['success']:
        print("✅ Bracket order placed successfully!")
        print(f"   Entry Ticket: {result.get('entry_ticket')}")
        print(f"   Stop Loss: {result.get('stop_loss')}")
        print(f"   Take Profit: {result.get('take_profit')}")
    else:
        print(f"❌ Failed: {result.get('error')}")
    
    print("="*70)


def cmd_order_oco(args):
    """Place OCO order."""
    from advanced_orders import OrderManager, OCOOrder

    print(f"\n[ORDER] Placing OCO Order...")
    print("="*70)
    
    oco = OCOOrder(
        symbol="XAUUSD",
        volume=args.volume,
        price_buy=args.buy_price,
        price_sell=args.sell_price,
        stop_loss_points=args.stop_loss,
        take_profit_points=args.take_profit
    )
    
    manager = OrderManager()
    result = manager.place_oco_order(oco)
    
    if result['success']:
        print("✅ OCO order placed successfully!")
        print(f"   Buy Ticket: {result.get('buy_ticket')}")
        print(f"   Sell Ticket: {result.get('sell_ticket')}")
    else:
        print(f"❌ Failed: {result.get('error')}")
    
    print("="*70)


def cmd_order_pending(args):
    """Place pending order."""
    from advanced_orders import OrderManager, PendingOrder

    print(f"\n[ORDER] Placing Pending Order...")
    print("="*70)
    
    order = PendingOrder(
        symbol="XAUUSD",
        action=args.action.upper(),
        volume=args.volume,
        order_type=args.type,
        price=args.price,
        stop_loss=args.stop_loss,
        take_profit=args.take_profit
    )
    
    manager = OrderManager()
    result = manager.place_pending_order(order)
    
    if result['success']:
        print("✅ Pending order placed successfully!")
        print(f"   Ticket: {result.get('ticket')}")
        print(f"   Type: {args.type} at {args.price}")
    else:
        print(f"❌ Failed: {result.get('error')}")
    
    print("="*70)


def cmd_learn_analyze(args):
    """Analyze trading performance."""
    from adaptive_learning import AdaptiveLearning

    print(f"\n[LEARN] Analyzing trading performance ({args.days} days)...")
    print("="*70)
    
    learner = AdaptiveLearning()
    analysis = learner.analyze_performance(days=args.days)
    
    if 'error' in analysis:
        print(f"❌ Error: {analysis['error']}")
    else:
        print(f"Total Trades: {analysis.get('total_trades', 0)}")
        print(f"Win Rate: {analysis.get('win_rate', 0):.1%}")
        print(f"Profit Factor: {analysis.get('profit_factor', 0):.2f}")
        print(f"Expectancy: ${analysis.get('expectancy', 0):.2f}")
        print(f"Avg Profit: ${analysis.get('avg_profit', 0):.2f}")
        print(f"Avg Loss: ${analysis.get('avg_loss', 0):.2f}")
        
        print("\nRecommendations:")
        for rec in analysis.get('recommendations', []):
            print(f"  • {rec}")
    
    print("="*70)


def cmd_learn_strategy(args):
    """Generate optimized strategy."""
    from adaptive_learning import AdaptiveLearning

    print("\n[LEARN] Generating optimized strategy...")
    print("="*70)
    
    learner = AdaptiveLearning()
    strategy = learner.generate_optimized_strategy()
    
    if 'error' in strategy:
        print(f"❌ Error: {strategy['error']}")
    else:
        print(f"Strategy: {strategy.get('name')}")
        print(f"Base: {strategy.get('base_strategy')}")
        print(f"Optimal Market: {strategy.get('optimal_market_condition')}")
        print(f"\nParameters:")
        for key, value in strategy.get('parameters', {}).items():
            print(f"  {key}: {value}")
        print(f"\nExpected Performance:")
        perf = strategy.get('expected_performance', {})
        print(f"  Win Rate: {perf.get('win_rate', 0):.1%}")
        print(f"  Profit Factor: {perf.get('profit_factor', 0):.2f}")
    
    print("="*70)


def cmd_learn_params(args):
    """Get adaptive parameters."""
    from adaptive_learning import AdaptiveLearning

    print(f"\n[LEARN] Adaptive Parameters for {args.condition} market")
    print("="*70)
    
    learner = AdaptiveLearning()
    params = learner.get_adaptive_params(args.condition, args.strategy)
    
    print(f"Strategy: {args.strategy}")
    print(f"Condition: {args.condition}")
    print(f"\nParameters:")
    for key, value in params.items():
        print(f"  {key}: {value}")
    
    print("="*70)


def cmd_learn_summary(args):
    """Show learning summary."""
    from adaptive_learning import AdaptiveLearning

    print("\n[LEARN] Learning System Summary")
    print("="*70)
    
    learner = AdaptiveLearning()
    summary = learner.get_learning_summary()
    
    print(f"Patterns Learned: {summary.get('total_patterns_learned', 0)}")
    print(f"Market Conditions: {', '.join(summary.get('market_conditions_tracked', []))}")
    print(f"Optimized Strategies: {', '.join(summary.get('optimized_strategies', []))}")
    
    best_setup = summary.get('best_performing_setup')
    if best_setup:
        print(f"\nBest Setup: {best_setup['key']}")
        print(f"Fitness Score: {best_setup['score']:.4f}")
    
    recommendations = summary.get('recent_recommendations', [])
    if recommendations:
        print(f"\nRecent Recommendations:")
        for rec in recommendations[:5]:
            print(f"  • {rec}")
    
    print("="*70)


# ======================================================================
# Orchestrator Commands
# ======================================================================

def cmd_orch_start(args):
    """Start the orchestrator."""
    from orchestrator import TradingOrchestrator, SystemMode
    
    mode_map = {
        'manual': SystemMode.MANUAL,
        'semi': SystemMode.SEMI_AUTO,
        'auto': SystemMode.AUTO
    }
    mode = mode_map.get(args.mode, SystemMode.SEMI_AUTO)
    
    print(f"\n[ORCHESTRATOR] Starting in {mode.name} mode...")
    print("Press Ctrl+C to stop\n")
    
    orchestrator = TradingOrchestrator(mode=mode)
    
    try:
        orchestrator.start()
        
        # Keep running until interrupted
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n\n[ORCHESTRATOR] Stopping...")
        orchestrator.stop()
        print("[ORCHESTRATOR] Stopped.")


def cmd_orch_stop(args):
    """Stop the orchestrator (for daemon mode - placeholder)."""
    print("\n[ORCHESTRATOR] Stop command received.")
    print("Note: Use Ctrl+C when running in foreground mode.")


def cmd_orch_status(args):
    """Show orchestrator status."""
    from orchestrator import TradingOrchestrator
    
    print("\n[ORCHESTRATOR] System Status")
    print("="*70)
    
    # Create temporary instance to get status
    orchestrator = TradingOrchestrator()
    status = orchestrator.get_status()
    
    print(f"Mode: {status.get('mode', 'Unknown')}")
    print(f"Running: {'Yes' if status.get('is_running') else 'No'}")
    print(f"Last Update: {status.get('last_update', 'N/A')}")
    print(f"\nActive Modules:")
    for module in status.get('active_modules', []):
        print(f"  • {module}")
    
    workers = status.get('workers', {})
    if workers:
        print(f"\nWorkers:")
        for name, alive in workers.items():
            status_icon = "✅" if alive else "❌"
            print(f"  {status_icon} {name}")
    
    errors = status.get('errors', [])
    if errors:
        print(f"\nRecent Errors:")
        for error in errors[-3:]:
            print(f"  ⚠️  {error}")
    
    print("="*70)


def cmd_orch_mode(args):
    """Change orchestrator mode."""
    from orchestrator import TradingOrchestrator, SystemMode
    
    mode_map = {
        'manual': SystemMode.MANUAL,
        'semi': SystemMode.SEMI_AUTO,
        'auto': SystemMode.AUTO
    }
    mode = mode_map.get(args.mode)
    
    if not mode:
        print(f"\n❌ Invalid mode: {args.mode}")
        return
    
    print(f"\n[ORCHESTRATOR] Changing mode to {mode.name}...")
    
    orchestrator = TradingOrchestrator()
    orchestrator.set_mode(mode)
    
    print(f"✅ Mode changed to {mode.name}")
    
    if mode == SystemMode.MANUAL:
        print("   All decisions require manual approval")
    elif mode == SystemMode.SEMI_AUTO:
        print("   AI recommends, you approve")
    elif mode == SystemMode.AUTO:
        print("   Full autonomous trading enabled")


# ======================================================================
# Agent Sub-commands (SubAgent System)
# ======================================================================

def _print_agent_result(result, title="Agent Result"):
    """Pretty-print an agent result dict."""
    success = result.get('success', False)
    icon = "✅" if success else "❌"
    mode = result.get('mode', 'single')
    tool = result.get('tool_used') or ', '.join(result.get('tools_used', []))

    print(f"\n{'='*70}")
    print(f"{icon} {title}")
    print(f"{'='*70}")

    if tool:
        print(f"Tool(s): {tool}")
    if mode == 'consensus':
        print(f"Mode: Consensus ({result.get('agreement', 0):.0%} agreement)")
        if result.get('sentiment'):
            print(f"Sentiment: {result['sentiment'].upper()}")
    else:
        cached = " (cached)" if result.get('cached') else ""
        t = result.get('execution_time', 0)
        print(f"Time: {t:.1f}s{cached}")

    if result.get('error'):
        print(f"Error: {result['error']}")

    response = result.get('response', '')
    if response:
        print(f"\n{response}")

    print(f"\n{'='*70}\n")


def cmd_agent_run(args):
    """Run a free-form task on an AI agent."""
    from sub_agent import SubAgentOrchestrator

    task_text = ' '.join(args.task)
    print(f"\n🦞 [AGENT] Running task...")
    print(f"Task: {task_text}")
    if args.tool:
        print(f"Tool: {args.tool}")
    if args.consensus:
        print(f"Mode: Consensus (all tools)")
    print()

    orch = SubAgentOrchestrator(
        preferred_tool=args.tool,
        use_consensus=args.consensus,
    )
    result = orch.ask(task_text, tool=args.tool)
    _print_agent_result(result, "Agent Response")


def cmd_agent_research(args):
    """Run market research via AI agent."""
    from sub_agent import SubAgentOrchestrator

    query = ' '.join(args.query)
    print(f"\n🔍 [RESEARCH] Researching: {query}")
    print(f"Using: {'consensus' if args.consensus else args.tool or 'best available'}")
    print("Please wait...\n")

    orch = SubAgentOrchestrator(
        preferred_tool=args.tool,
        use_consensus=args.consensus,
    )
    result = orch.research(query, tool=args.tool)
    _print_agent_result(result, "Research Report")


def cmd_agent_analyze(args):
    """Run technical analysis via AI agent."""
    from sub_agent import SubAgentOrchestrator

    print(f"\n📊 [ANALYZE] Technical analysis for {args.symbol}")
    print(f"Timeframe: {args.timeframe}")
    print("Please wait...\n")

    orch = SubAgentOrchestrator(
        preferred_tool=args.tool,
        use_consensus=args.consensus,
    )
    result = orch.analyze(
        symbol=args.symbol,
        timeframe=args.timeframe,
        tool=args.tool,
    )
    _print_agent_result(result, f"Technical Analysis — {args.symbol} {args.timeframe}")


def cmd_agent_plan(args):
    """Generate a trading plan via AI agent."""
    from sub_agent import SubAgentOrchestrator

    print(f"\n📋 [PLAN] Generating trading plan for {args.symbol}...")
    print("Please wait...\n")

    config = load_config(str(Path(__file__).parent / "config.yaml"))
    balance = config.get('trading', {}).get('initial_balance', 10000)
    risk = config.get('trading', {}).get('risk_per_trade', 0.01)
    max_loss = config.get('risk', {}).get('max_daily_loss', 500)

    orch = SubAgentOrchestrator(
        preferred_tool=args.tool,
        use_consensus=args.consensus,
    )
    result = orch.plan(
        symbol=args.symbol,
        balance=balance,
        risk_per_trade=risk,
        market_condition=args.condition,
        max_loss=max_loss,
        tool=args.tool,
    )
    _print_agent_result(result, f"Trading Plan — {args.symbol}")


def cmd_agent_review(args):
    """Review open positions via AI agent."""
    from sub_agent import SubAgentOrchestrator

    print(f"\n🔎 [REVIEW] Reviewing positions...")

    # Try to get real position data from MT5
    positions_detail = "No open positions"
    balance = equity = margin_level = total_pnl = 0
    try:
        from mt5_manager import MT5Manager
        with MT5Manager() as mt5:
            account = mt5.get_account_info()
            if account:
                balance = account['balance']
                equity = account['equity']
                margin_level = account.get('margin_level', 0)
                total_pnl = account.get('profit', 0)

            positions = mt5.get_positions(mt5.config['trading']['symbol'])
            if positions:
                lines = []
                for p in positions:
                    ptype = "BUY" if p['type'] == 0 else "SELL"
                    lines.append(
                        f"  {ptype} {p['volume']:.2f} lots @ {p['price_open']:.2f} "
                        f"→ {p['price_current']:.2f} (P/L: {p['profit']:.2f})"
                    )
                positions_detail = "\n".join(lines)
    except Exception as e:
        print(f"  (Could not connect to MT5: {e})")

    print("Please wait...\n")

    orch = SubAgentOrchestrator(preferred_tool=args.tool, use_consensus=args.consensus)
    result = orch.review_positions(
        positions_detail=positions_detail,
        balance=balance, equity=equity,
        margin_level=margin_level, total_pnl=total_pnl,
        tool=args.tool,
    )
    _print_agent_result(result, "Position Review")


def cmd_agent_risk(args):
    """Run risk assessment via AI agent."""
    from sub_agent import SubAgentOrchestrator

    print(f"\n⚠️  [RISK] Running risk assessment...")

    # Try to pull real analytics
    win_rate = profit_factor = max_drawdown = 0.0
    recent_trades = "No trade history"
    portfolio = "No portfolio data"
    try:
        from trade_journal import TradeJournal
        journal = TradeJournal()
        analytics = journal.get_analytics(days=30)
        win_rate = analytics.get('overall_win_rate', 0)
        total = analytics.get('total_closed', 0)
        recent_trades = f"{total} trades in last 30 days, win rate {win_rate:.1%}"
    except Exception:
        pass

    print("Please wait...\n")

    orch = SubAgentOrchestrator(preferred_tool=args.tool, use_consensus=args.consensus)
    result = orch.assess_risk(
        portfolio_summary=portfolio,
        recent_trades=recent_trades,
        win_rate=win_rate,
        profit_factor=profit_factor,
        max_drawdown=max_drawdown,
        tool=args.tool,
    )
    _print_agent_result(result, "Risk Assessment")


def cmd_agent_news(args):
    """Get news digest via AI agent."""
    from sub_agent import SubAgentOrchestrator

    topics = ' '.join(args.topics) if args.topics else "XAUUSD gold price drivers today, Fed policy, geopolitics"
    print(f"\n📰 [NEWS] News digest...")
    print(f"Topics: {topics}")
    print("Please wait...\n")

    orch = SubAgentOrchestrator(preferred_tool=args.tool, use_consensus=args.consensus)
    result = orch.news_digest(topics=topics, tool=args.tool)
    _print_agent_result(result, "News Digest")


def cmd_agent_daily(args):
    """Run full daily routine (all sub-agents)."""
    from sub_agent import SubAgentOrchestrator

    print(f"\n🔄 [DAILY] Running full daily routine for {args.symbol}...")
    print("This will run: News → Analysis → Plan → Risk → Summary")
    print("Estimated time: 3-10 minutes\n")

    orch = SubAgentOrchestrator(preferred_tool=args.tool, use_consensus=args.consensus)
    report = orch.daily_routine(symbol=args.symbol, tool=args.tool)

    success = report.get('success', False)
    icon = "✅" if success else "⚠️"

    print(f"\n{'='*70}")
    print(f"{icon} Daily Routine Report — {report.get('date', 'today')}")
    print(f"{'='*70}")

    for step_name, step_result in report.get('steps', {}).items():
        s_icon = "✅" if step_result.get('success') else "❌"
        tool = step_result.get('tool_used') or ', '.join(step_result.get('tools_used', []))
        print(f"\n{s_icon} {step_name.replace('_', ' ').title()} [{tool}]")
        response = step_result.get('response', '')
        if response:
            # Print first 500 chars of each step
            preview = response[:500] + ("..." if len(response) > 500 else "")
            print(f"{preview}")

    print(f"\n{'='*70}")
    print(f"Started:   {report.get('started_at', 'N/A')}")
    print(f"Completed: {report.get('completed_at', 'N/A')}")
    print(f"{'='*70}\n")


def cmd_agent_outlook(args):
    """Quick market outlook from all agents."""
    from sub_agent import SubAgentOrchestrator

    print(f"\n⚡ [OUTLOOK] Quick market outlook for {args.symbol}...")
    print("Querying all available agents...\n")

    orch = SubAgentOrchestrator(use_consensus=True)
    result = orch.quick_outlook(symbol=args.symbol, tool=args.tool)

    if isinstance(result, dict) and 'combined_response' in result:
        # Consensus result
        print(f"{'='*70}")
        print(f"Quick Outlook — {args.symbol}")
        print(f"{'='*70}")
        print(f"Consensus: {result.get('consensus_sentiment', 'N/A').upper()}")
        print(f"Agreement: {result.get('agreement', 0):.0%}")
        print(f"Tools: {', '.join(result.get('tools_used', []))}")
        print(f"\n{result.get('combined_response', '')}")
        print(f"{'='*70}\n")
    else:
        _print_agent_result(result, f"Quick Outlook — {args.symbol}")


def cmd_agent_tools(args):
    """List available AI agent tools."""
    from agent_executor import AgentExecutor

    executor = AgentExecutor()
    tools = executor.get_all_tools()

    print(f"\n{'='*70}")
    print(f"🦞 ClawGold Agent Tools")
    print(f"{'='*70}")
    print(f"{'Tool':<12} {'Status':<12} {'Version':<20} {'Calls':<8} {'Success':<10} {'Avg Time':<10}")
    print(f"{'-'*70}")

    for cap in tools:
        status = "✅ Ready" if cap.available else "❌ N/A"
        version = (cap.version or "")[:18]
        sr = f"{cap.success_rate:.0f}%" if cap.total_calls > 0 else "—"
        avg = f"{cap.avg_response_time:.1f}s" if cap.total_calls > 0 else "—"
        print(f"{cap.tool.value:<12} {status:<12} {version:<20} {cap.total_calls:<8} {sr:<10} {avg:<10}")

    print(f"\n  Strengths:")
    for cap in tools:
        if cap.available and cap.strengths:
            print(f"  {cap.tool.value}: {', '.join(cap.strengths)}")

    print(f"\n{'='*70}\n")


def cmd_agent_history(args):
    """Show agent execution history."""
    from agent_executor import AgentExecutor

    executor = AgentExecutor()
    history = executor.get_history(limit=args.limit)

    print(f"\n{'='*70}")
    print(f"Agent Execution History (last {args.limit})")
    print(f"{'='*70}")

    if not history:
        print("No history yet.")
    else:
        for entry in history:
            icon = "✅" if entry.get('success') else "❌"
            tool = entry.get('tool', '?')
            task = (entry.get('task', '') or '')[:50]
            t = entry.get('execution_time', 0) or 0
            ts = entry.get('created_at', '')
            print(f"{icon} [{ts}] {tool:<12} {task:<50} ({t:.1f}s)")

    print(f"{'='*70}\n")


def cmd_agent_metrics(args):
    """Show agent tool metrics."""
    from agent_executor import AgentExecutor

    executor = AgentExecutor()
    metrics = executor.get_metrics()

    print(f"\n{'='*70}")
    print(f"Agent Tool Metrics")
    print(f"{'='*70}")

    for tool, m in metrics.items():
        print(f"\n  {tool}:")
        print(f"    Calls:    {m['total_calls']}")
        print(f"    Success:  {m['successes']} ({m['success_rate']})")
        print(f"    Failures: {m['failures']}")
        print(f"    Avg Time: {m['avg_response_time']}")

    print(f"\n{'='*70}\n")


def cmd_agent_schedule_start(args):
    """Start the agent scheduler."""
    from agent_scheduler import AgentScheduler

    print("\n🦞 Starting Agent Scheduler...")
    scheduler = AgentScheduler()
    scheduler.start(blocking=True)


def cmd_agent_schedule_status(args):
    """Show scheduler status and tasks."""
    from agent_scheduler import AgentScheduler

    scheduler = AgentScheduler()
    tasks = scheduler.list_tasks()

    print(f"\n{'='*70}")
    print(f"🦞 Agent Scheduler — Tasks")
    print(f"{'='*70}")
    print(f"{'Name':<25} {'Type':<10} {'Schedule':<15} {'Task':<20} {'Runs':<6} {'Status':<8}")
    print(f"{'-'*70}")

    for t in tasks:
        status = "✅ ON" if t['enabled'] else "⏸ OFF"
        print(f"{t['name']:<25} {t['type']:<10} {t['schedule']:<15} "
              f"{t['task']:<20} {t['run_count']:<6} {status:<8}")
        if t.get('last_run') and t['last_run'] != 'never':
            print(f"{'':>25} Last: {t['last_run']}")

    print(f"{'='*70}\n")


def cmd_agent_schedule_log(args):
    """Show scheduler execution log."""
    from agent_scheduler import AgentScheduler

    scheduler = AgentScheduler()
    log = scheduler.get_log(limit=args.limit)

    print(f"\n{'='*70}")
    print(f"Scheduler Log (last {args.limit})")
    print(f"{'='*70}")

    if not log:
        print("No log entries yet.")
    else:
        for entry in log:
            icon = "✅" if entry.get('success') else "❌"
            name = entry.get('task_name', '?')
            ts = entry.get('created_at', '')
            t = entry.get('execution_time', 0) or 0
            print(f"{icon} [{ts}] {name:<25} ({t:.1f}s)")
            if entry.get('error'):
                print(f"   Error: {entry['error']}")

    print(f"{'='*70}\n")


def cmd_agent_schedule_add(args):
    """Add a new scheduled task."""
    from agent_scheduler import AgentScheduler

    scheduler = AgentScheduler()
    task = scheduler.add_task(
        name=args.name,
        schedule_type=args.type,
        schedule_value=args.schedule,
        task_type=args.task_type,
        task_params=json.loads(args.params) if args.params else {},
    )
    print(f"\n✅ Added scheduled task: {task.name}")
    print(f"   Type: {task.schedule_type.value}")
    print(f"   Schedule: {task.schedule_value}")
    print(f"   Task: {task.task_type}\n")


def cmd_agent_schedule_remove(args):
    """Remove a scheduled task."""
    from agent_scheduler import AgentScheduler

    scheduler = AgentScheduler()
    if scheduler.remove_task(args.name):
        print(f"\n✅ Removed task: {args.name}\n")
    else:
        print(f"\n❌ Task not found: {args.name}\n")


def cmd_agent_schedule_toggle(args):
    """Enable or disable a scheduled task."""
    from agent_scheduler import AgentScheduler

    scheduler = AgentScheduler()
    if args.action == 'enable':
        ok = scheduler.enable_task(args.name)
    else:
        ok = scheduler.disable_task(args.name)

    if ok:
        print(f"\n✅ Task {args.name} {'enabled' if args.action == 'enable' else 'disabled'}\n")
    else:
        print(f"\n❌ Task not found: {args.name}\n")


# ═══════════════════════════════════════════════════════════════
# BUSINESS MODULE COMMANDS
# ═══════════════════════════════════════════════════════════════

def _get_signal_service():
    from signal_service import SignalService
    config = load_config()
    import os
    token = config.get('telegram', {}).get('bot_token') or os.getenv('TELEGRAM_BOT_TOKEN', '')
    return SignalService(config=config, bot_token=token)

def cmd_signal_add_subscriber(args):
    svc = _get_signal_service()
    ok = svc.add_subscriber(args.chat_id, args.name, args.tier, args.months, args.payment)
    if ok:
        print(f"\n✅ Subscriber '{args.name}' ({args.tier.upper()}) added for {args.months} month(s).\n")
    else:
        print(f"\n❌ Failed to add subscriber.\n")

def cmd_signal_remove_subscriber(args):
    svc = _get_signal_service()
    svc.remove_subscriber(args.chat_id)
    print(f"\n✅ Subscriber {args.chat_id} deactivated.\n")

def cmd_signal_broadcast(args):
    svc = _get_signal_service()
    count = svc.broadcast_signal(
        symbol=args.symbol,
        action=args.action,
        entry_price=args.price,
        stop_loss=args.sl,
        take_profit=args.tp,
        confidence=args.confidence,
    )
    print(f"\n✅ Signal broadcast to {count} subscriber(s).\n")

def cmd_signal_close(args):
    svc = _get_signal_service()
    ok = svc.close_signal(args.id, args.price, args.outcome)
    if ok:
        print(f"\n✅ Signal #{args.id} closed as {args.outcome} at {args.price:.2f}\n")
    else:
        print(f"\n❌ Signal #{args.id} not found.\n")

def cmd_signal_stats(args):
    svc = _get_signal_service()
    stats = svc.get_revenue_stats()
    sub = stats['subscribers']
    rev = stats['revenue']
    perf = stats['performance']
    print(f"\n{'═'*45}")
    print(f"  ClawGold Signal Service — Revenue Dashboard")
    print(f"{'═'*45}")
    print(f"  Subscribers:  Free={sub['free']}  Basic={sub['basic']}  Pro={sub['pro']}  VIP={sub['vip']}")
    print(f"  Total Active: {sub['total']}")
    print(f"{'─'*45}")
    print(f"  This Month Revenue:  ${rev['monthly_this_month']:,.2f}")
    print(f"  MRR (projected):     ${rev['mrr_projected']:,.2f}/month")
    print(f"  ARR (projected):     ${rev['arr_projected']:,.2f}/year")
    print(f"  All-Time Revenue:    ${rev['total_all_time']:,.2f}")
    print(f"{'─'*45}")
    print(f"  Signals Sent:        {perf['signals_sent']}")
    print(f"  Win Rate:            {perf['win_rate']:.1f}%  ({perf['total_wins']}W / {perf['total_losses']}L)")
    print(f"{'═'*45}\n")

def cmd_signal_reminders(args):
    svc = _get_signal_service()
    svc.send_renewal_reminders()
    print("\n✅ Renewal reminders sent.\n")

def cmd_signal_list(args):
    svc = _get_signal_service()
    subs = svc.get_active_subscribers()
    print(f"\n{'─'*60}")
    print(f"  Active Subscribers ({len(subs)} total)")
    print(f"{'─'*60}")
    print(f"  {'Name':<20} {'Tier':<8} {'Expires':<12} {'Signals':>8}")
    print(f"{'─'*60}")
    for s in subs:
        expires = s['expires_at'][:10] if s.get('expires_at') else 'unlimited'
        print(f"  {s['name']:<20} {s['tier'].upper():<8} {expires:<12} {s['signals_received']:>8}")
    print(f"{'─'*60}\n")


def _get_pamm():
    from pamm_manager import PAMMManager
    return PAMMManager()

def cmd_pamm_add_investor(args):
    pamm = _get_pamm()
    inv_id = pamm.add_investor(args.name, args.amount, args.email, args.contact)
    print(f"\n✅ Investor '{args.name}' (ID #{inv_id}) onboarded with ${args.amount:,.2f}\n")

def cmd_pamm_update_nav(args):
    pamm = _get_pamm()
    result = pamm.update_nav(args.nav, args.note)
    print(f"\n{'═'*50}")
    print(f"  Fund NAV Updated: ${result['total_nav']:,.2f}")
    print(f"  Change: ${result['change_from_prev']:+,.2f}")
    print(f"  ClawGold Fees This Period: ${result['total_clawgold_fee']:.2f}")
    print(f"     Performance Fee: ${result['total_perf_fee']:.2f}")
    print(f"     Management Fee:  ${result['total_mgmt_fee']:.2f}")
    print(f"{'─'*50}")
    print(f"  {'Investor':<20} {'Value':>10} {'Net P/L':>10} {'Return':>8}")
    print(f"{'─'*50}")
    for d in result['distributions']:
        print(f"  {d['investor']:<20} ${d['current_value']:>9,.2f} ${d['net_profit']:>+9,.2f} {d['return_pct']:>7.2f}%")
    print(f"{'═'*50}\n")

def cmd_pamm_statement(args):
    pamm = _get_pamm()
    stmts = pamm.generate_monthly_statement(args.month)
    month_label = args.month or datetime.now().strftime('%Y-%m')
    print(f"\n{'═'*60}")
    print(f"  Monthly Statement — {month_label}")
    print(f"{'─'*60}")
    for s in stmts:
        print(f"  Investor:    {s['investor']}")
        print(f"   Opening:    ${s['opening_nav']:,.2f}  →  Closing: ${s['closing_nav']:,.2f}")
        print(f"   Net Profit: ${s['net_profit']:+,.2f}  ({s['return_pct']:+.2f}%)")
        print(f"   Perf Fee:   ${s['performance_fee']:.2f}  |  Mgmt: ${s['management_fee']:.2f}")
        print(f"{'─'*60}")
    print()

def cmd_pamm_overview(args):
    pamm = _get_pamm()
    ov = pamm.get_fund_overview()
    f = ov['fund']
    inv = ov['investors']
    fees = ov['clawgold_revenue']
    print(f"\n{'═'*45}")
    print(f"  ClawGold PAMM Fund Overview")
    print(f"{'═'*45}")
    print(f"  Current NAV:     ${f['current_nav']:,.2f}")
    print(f"  Total Return:    {f['total_return']:+.2f}%")
    print(f"  As of:           {f['as_of_date']}")
    print(f"{'─'*45}")
    print(f"  Active Investors: {inv['active_count']}")
    print(f"  Total Capital:    ${inv['total_capital']:,.2f}")
    print(f"{'─'*45}")
    print(f"  ClawGold Revenue: ${fees['total_fees_earned']:,.2f}")
    print(f"  Fee Structure:    {fees['fee_structure']}")
    print(f"{'═'*45}\n")

def cmd_pamm_withdraw(args):
    pamm = _get_pamm()
    ok = pamm.record_withdrawal(args.id, args.amount)
    if ok:
        print(f"\n✅ Withdrawal of ${args.amount:,.2f} recorded for investor #{args.id}\n")
    else:
        print("\n❌ Insufficient capital or investor not found.\n")


def _get_perf_tracker():
    from performance_tracker import PerformanceTracker
    config = load_config()
    initial = config.get('trading', {}).get('initial_balance', 10000.0)
    return PerformanceTracker(initial_balance=initial)

def cmd_perf_stats(args):
    tracker = _get_perf_tracker()
    s = tracker.calculate_stats(args.days)
    label = f"Last {args.days} days" if args.days > 0 else "All-Time"
    print(f"\n{'═'*50}")
    print(f"  ClawGold Performance ({label})")
    print(f"{'═'*50}")
    print(f"  Net Profit:      ${s.net_profit:+,.2f}  ({s.total_return_pct:+.2f}%)")
    print(f"  Annual Return:   {s.annual_return_pct:+.2f}%")
    print(f"  Balance:         ${s.start_balance:,.2f}  →  ${s.current_balance:,.2f}")
    print(f"{'─'*50}")
    print(f"  Win Rate:        {s.win_rate:.1f}%  ({s.winning_trades}W / {s.losing_trades}L / {s.total_trades} total)")
    print(f"  Profit Factor:   {s.profit_factor:.2f}x")
    print(f"  Avg Win:         ${s.avg_win:.2f}   Avg Loss: -${s.avg_loss:.2f}")
    print(f"  Risk:Reward:     1:{s.risk_reward:.2f}")
    print(f"{'─'*50}")
    print(f"  Max Drawdown:    -{s.max_drawdown:.2f}%")
    print(f"  Sharpe Ratio:    {s.sharpe_ratio:.2f}")
    print(f"  Calmar Ratio:    {s.calmar_ratio:.2f}")
    print(f"  Best Month:      {s.best_month}   Worst: {s.worst_month}")
    print(f"{'═'*50}\n")

def cmd_perf_report(args):
    tracker = _get_perf_tracker()
    html = tracker.generate_html_report()
    with open(args.output, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"\n✅ HTML report saved to: {args.output}\n")

def cmd_perf_export(args):
    tracker = _get_perf_tracker()
    data = tracker.export_myfxbook()
    with open(args.output, 'w', encoding='utf-8') as f:
        import json
        json.dump(data, f, indent=2)
    print(f"\n✅ Export saved to: {args.output}  (format: {args.format})\n")

def cmd_perf_snapshot(args):
    tracker = _get_perf_tracker()
    tracker.record_equity_snapshot(args.balance, args.equity)
    print(f"\n✅ Equity snapshot recorded: Balance=${args.balance:,.2f}  Equity=${args.equity:,.2f}\n")


# ─── Graph command handlers ────────────────────────────────────────────────────

def cmd_graph_run(args):
    """Run the LangGraph trading pipeline."""
    from scripts.trading_graph import run_pipeline
    symbol = getattr(args, 'symbol', 'XAUUSD')
    timeframe = getattr(args, 'timeframe', 'H1')
    auto = getattr(args, 'auto', False)
    print(f"\n[*] Starting LangGraph pipeline: {symbol} {timeframe}")
    if auto:
        print("   [auto-approve mode -- skipping human review]")
    result = run_pipeline(symbol, timeframe, auto_approve=auto)
    print("\n=== Pipeline Result ===")
    import json
    print(json.dumps(
        {k: v for k, v in result.items() if k not in ('messages',)},
        indent=2, default=str
    ))
    print("\n=== Audit Trail ===")
    for msg in result.get('messages', []):
        print(' ', msg)
    print()


def cmd_graph_show(args):
    """Print a text representation of the graph nodes and edges."""
    from scripts.trading_graph import build_graph
    g = build_graph()
    print("\n=== ClawGold Trading Graph ===")
    print("""
  START
    └─► research      (AI market research)
          └─► analyze   (sentiment + strategy)
                └─► validate  (risk gate)
                      ├─► [low confidence, retry < 3] ──► research
                      ├─► [HOLD / max retries] ──────────► END
                      └─► [confident BUY/SELL] ──────────► human_review
                                └─► [approved] ──► execute ──► monitor ──► END
                                └─► [rejected] ──────────────────────────► END
""")
    print("Nodes:", list(g.nodes))
    print()


def main():
    parser = argparse.ArgumentParser(
        prog='claw',
        description='ClawGold - XAUUSD Trading System',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s balance                    # Check balance
  %(prog)s positions                  # List positions
  %(prog)s price                      # Get current price
  %(prog)s trade BUY 0.1              # Buy 0.1 lots
  %(prog)s close --all                # Close all positions
  %(prog)s monitor --profit-alert 50  # Alert on $50 profit
  %(prog)s validate                   # Check config

Notifications:
  %(prog)s notify test                # Test Telegram notifications
  %(prog)s notify daily               # Send daily summary

Advanced Trading:
  %(prog)s trailing-stop 12345        # Apply trailing stop
  %(prog)s grid --levels 5            # Start grid trading
  %(prog)s breakout --execute         # Detect & trade breakouts
  %(prog)s analyze                    # Multi-timeframe analysis
  %(prog)s scalp --duration 30        # Run scalping for 30 min

AI Agent System (SubAgent):
  %(prog)s agent run "analyze gold"   # Free-form AI task
  %(prog)s agent research "gold outlook" # Market research
  %(prog)s agent analyze              # Technical analysis
  %(prog)s agent plan                 # Generate trading plan
  %(prog)s agent review               # Review open positions
  %(prog)s agent risk                 # Risk assessment
  %(prog)s agent news                 # News digest
  %(prog)s agent daily                # Full daily routine (all sub-agents)
  %(prog)s agent outlook              # Quick consensus outlook
  %(prog)s agent tools                # List available AI CLI tools
  %(prog)s agent history              # Show execution history
  %(prog)s agent schedule start       # Start scheduler daemon
  %(prog)s agent schedule status      # Show scheduled tasks
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # balance command
    balance_parser = subparsers.add_parser('balance', help='Check account balance')
    balance_parser.set_defaults(func=cmd_balance)
    
    # positions command
    positions_parser = subparsers.add_parser('positions', help='List open positions')
    positions_parser.add_argument('--symbol', '-s', help='Symbol to check (default: from config)')
    positions_parser.set_defaults(func=cmd_positions)
    
    # price command
    price_parser = subparsers.add_parser('price', help='Get current price')
    price_parser.add_argument('--symbol', '-s', help='Symbol (default: XAUUSD)')
    price_parser.set_defaults(func=cmd_price)
    
    # trade command
    trade_parser = subparsers.add_parser('trade', help='Execute trade')
    trade_parser.add_argument('action', choices=['BUY', 'SELL', 'buy', 'sell'], help='Trade action')
    trade_parser.add_argument('volume', type=float, help='Volume in lots')
    trade_parser.add_argument('--strategy', default='manual',
                              help='Strategy label for journal analytics (default: manual)')
    trade_parser.add_argument('--market-condition', default='unknown',
                              help='Market condition label (e.g., trending, ranging, volatile)')
    trade_parser.add_argument('--reason', default='',
                              help='Trade rationale or setup reason')
    trade_parser.set_defaults(func=cmd_trade)
    
    # close command
    close_parser = subparsers.add_parser('close', help='Close position(s)')
    close_group = close_parser.add_mutually_exclusive_group(required=True)
    close_group.add_argument('--all', '-a', action='store_true', help='Close all positions')
    close_group.add_argument('--ticket', '-t', type=int, help='Close specific position by ticket')
    close_parser.add_argument('--strategy', default='manual',
                              help='Strategy label for journal analytics (default: manual)')
    close_parser.add_argument('--market-condition', default='unknown',
                              help='Market condition label (e.g., trending, ranging, volatile)')
    close_parser.add_argument('--reason', default='',
                              help='Close rationale or post-trade note')
    close_parser.set_defaults(func=cmd_close)
    
    # monitor command
    monitor_parser = subparsers.add_parser('monitor', help='Monitor positions')
    monitor_parser.add_argument('--profit-alert', '-p', type=float, default=100, 
                                help='Profit alert threshold in USD (default: 100)')
    monitor_parser.add_argument('--loss-alert', '-l', type=float, default=50,
                                help='Loss alert threshold in USD (default: 50)')
    monitor_parser.add_argument('--interval', '-i', type=int, default=5,
                                help='Check interval in seconds (default: 5)')
    monitor_parser.set_defaults(func=cmd_monitor)
    
    # backtest command
    backtest_parser = subparsers.add_parser('backtest', help='Run backtest')
    backtest_parser.add_argument('--symbol', '-s', default='XAUUSD', help='Symbol to backtest')
    backtest_parser.add_argument('--period', '-p', default='1y', help='Period (e.g., 1m, 3m, 1y)')
    backtest_parser.add_argument('--strategy', choices=['macd', 'ma_crossover'], 
                                  default='macd', help='Strategy to test')
    backtest_parser.set_defaults(func=cmd_backtest)
    
    # validate command
    validate_parser = subparsers.add_parser('validate', help='Validate configuration')
    validate_parser.set_defaults(func=cmd_validate)

    # trailing-stop command
    ts_parser = subparsers.add_parser('trailing-stop', help='Apply trailing stop to position')
    ts_parser.add_argument('ticket', type=int, help='Position ticket number')
    ts_parser.add_argument('--activation', '-a', type=float, default=10,
                           help='Activation profit in points (default: 10)')
    ts_parser.add_argument('--distance', '-d', type=float, default=5,
                           help='Trailing distance in points (default: 5)')
    ts_parser.add_argument('--step', '-s', type=float, default=1,
                           help='Step size in points (default: 1)')
    ts_parser.set_defaults(func=cmd_trailing_stop)

    # grid command
    grid_parser = subparsers.add_parser('grid', help='Start grid trading')
    grid_parser.add_argument('--levels', '-l', type=int, default=5,
                             help='Number of grid levels (default: 5)')
    grid_parser.add_argument('--grid-size', '-g', type=float, default=10,
                             help='Grid size in points (default: 10)')
    grid_parser.add_argument('--volume', '-v', type=float, default=0.1,
                             help='Volume per level in lots (default: 0.1)')
    grid_parser.add_argument('--direction', '-d', choices=['buy', 'sell', 'both'],
                             default='both', help='Grid direction (default: both)')
    grid_parser.add_argument('--take-profit', '-tp', type=float, default=20,
                             help='Take profit in points (default: 20)')
    grid_parser.add_argument('--stop-loss', '-sl', type=float, default=50,
                             help='Stop loss in points (default: 50)')
    grid_parser.set_defaults(func=cmd_grid)

    # breakout command
    breakout_parser = subparsers.add_parser('breakout', help='Detect and trade breakouts')
    breakout_parser.add_argument('--symbol', '-s', default='XAUUSD', help='Symbol to analyze')
    breakout_parser.add_argument('--lookback', '-l', type=int, default=20,
                                 help='Lookback period in bars (default: 20)')
    breakout_parser.add_argument('--threshold', '-t', type=float, default=0.5,
                                 help='Breakout threshold % (default: 0.5)')
    breakout_parser.add_argument('--volume-mult', '-vm', type=float, default=1.5,
                                 help='Volume multiplier threshold (default: 1.5)')
    breakout_parser.add_argument('--confirmation', '-c', type=int, default=2,
                                 help='Confirmation bars (default: 2)')
    breakout_parser.add_argument('--execute', '-e', action='store_true',
                                 help='Execute trade on breakout detection')
    breakout_parser.add_argument('--volume', '-v', type=float, default=0.1,
                                 help='Trade volume in lots (default: 0.1)')
    breakout_parser.set_defaults(func=cmd_breakout)

    # analyze command
    analyze_parser = subparsers.add_parser('analyze', help='Multi-timeframe analysis')
    analyze_parser.add_argument('--symbol', '-s', default='XAUUSD',
                                help='Symbol to analyze (default: XAUUSD)')
    analyze_parser.set_defaults(func=cmd_analyze)

    # scalp command
    scalp_parser = subparsers.add_parser('scalp', help='Run scalping strategy')
    scalp_parser.add_argument('--symbol', '-s', default='XAUUSD',
                              help='Symbol to trade (default: XAUUSD)')
    scalp_parser.add_argument('--duration', '-d', type=int, default=30,
                              help='Duration in minutes (default: 30)')
    scalp_parser.add_argument('--profit-target', '-pt', type=float, default=5,
                              help='Profit target in points (default: 5)')
    scalp_parser.add_argument('--max-loss', '-ml', type=float, default=3,
                              help='Max loss in points (default: 3)')
    scalp_parser.set_defaults(func=cmd_scalp)

    # news command
    news_parser = subparsers.add_parser('news', help='News research and analysis')
    news_subparsers = news_parser.add_subparsers(dest='news_command', help='News commands')

    # news research
    news_research_parser = news_subparsers.add_parser('research', help='Research symbol with AI tools')
    news_research_parser.add_argument('symbol', help='Symbol to research (e.g., XAUUSD)')
    news_research_parser.add_argument('--query', '-q', help='Custom search query')
    news_research_parser.add_argument('--hours', '-t', type=int, default=24,
                                      help='Lookback hours (default: 24)')
    news_research_parser.add_argument('--no-ai', action='store_true',
                                      help='Skip AI tools, use cached only')
    news_research_parser.set_defaults(func=cmd_news_research)

    # news sentiment
    news_sentiment_parser = news_subparsers.add_parser('sentiment', help='Get sentiment analysis')
    news_sentiment_parser.add_argument('symbol', help='Symbol to analyze')
    news_sentiment_parser.add_argument('--trend', action='store_true',
                                       help='Show sentiment trend over time')
    news_sentiment_parser.add_argument('--hours', '-t', type=int, default=72,
                                       help='Hours for trend (default: 72)')
    news_sentiment_parser.set_defaults(func=cmd_news_sentiment)

    # news signal
    news_signal_parser = news_subparsers.add_parser('signal', help='Get trading signal from news')
    news_signal_parser.add_argument('symbol', help='Symbol to analyze')
    news_signal_parser.add_argument('--query', '-q', help='Custom search query')
    news_signal_parser.set_defaults(func=cmd_news_signal)

    # news stats
    news_stats_parser = news_subparsers.add_parser('stats', help='Show news database statistics')
    news_stats_parser.set_defaults(func=cmd_news_stats)

    # news cleanup
    news_cleanup_parser = news_subparsers.add_parser('cleanup', help='Clean old news data')
    news_cleanup_parser.add_argument('--days', '-d', type=int, default=30,
                                     help='Delete data older than N days (default: 30)')
    news_cleanup_parser.set_defaults(func=cmd_news_cleanup)

    # notify command
    notify_parser = subparsers.add_parser('notify', help='Telegram notifications')
    notify_subparsers = notify_parser.add_subparsers(dest='notify_command', help='Notification commands')

    # notify test
    notify_test_parser = notify_subparsers.add_parser('test', help='Test Telegram notifications')
    notify_test_parser.add_argument('--type', '-t', 
                                    choices=['all', 'signal', 'trade', 'alert', 'system'],
                                    default='all',
                                    help='Type of notification to test (default: all)')
    notify_test_parser.set_defaults(func=cmd_notify_test)

    # notify daily
    notify_daily_parser = notify_subparsers.add_parser('daily', help='Send daily summary')
    notify_daily_parser.set_defaults(func=cmd_notify_daily)

    # journal command
    journal_parser = subparsers.add_parser('journal', help='Trade journal and analytics')
    journal_subparsers = journal_parser.add_subparsers(dest='journal_command', help='Journal commands')

    journal_add_parser = journal_subparsers.add_parser('add', help='Add manual journal entry')
    journal_add_parser.add_argument('action', choices=['BUY', 'SELL', 'CLOSE', 'buy', 'sell', 'close'])
    journal_add_parser.add_argument('--symbol', '-s', default='XAUUSD', help='Trade symbol')
    journal_add_parser.add_argument('--volume', '-v', type=float, default=0.0, help='Trade volume in lots')
    journal_add_parser.add_argument('--price', '-p', type=float, required=True, help='Executed price')
    journal_add_parser.add_argument('--strategy', default='manual', help='Strategy label')
    journal_add_parser.add_argument('--market-condition', default='unknown', help='Market condition label')
    journal_add_parser.add_argument('--reason', default='', help='Trade rationale')
    journal_add_parser.add_argument('--pnl', type=float, default=None, help='Realized PnL for closed trade')
    journal_add_parser.add_argument('--ai-snapshot', default='', help='AI research snapshot text')
    journal_add_parser.set_defaults(func=cmd_journal_add)

    journal_analytics_parser = journal_subparsers.add_parser('analytics', help='Show win rate analytics')
    journal_analytics_parser.add_argument('--days', '-d', type=int, default=90, help='Lookback days')
    journal_analytics_parser.set_defaults(func=cmd_journal_analytics)

    journal_equity_parser = journal_subparsers.add_parser('equity', help='Show equity curve points')
    journal_equity_parser.add_argument('--days', '-d', type=int, default=90, help='Lookback days')
    journal_equity_parser.set_defaults(func=cmd_journal_equity)

    # calendar command
    calendar_parser = subparsers.add_parser('calendar', help='Economic calendar')
    calendar_subparsers = calendar_parser.add_subparsers(dest='calendar_command', help='Calendar commands')

    # calendar today
    calendar_today_parser = calendar_subparsers.add_parser('today', help='Show today economic events')
    calendar_today_parser.set_defaults(func=cmd_calendar_today)

    # calendar update
    calendar_update_parser = calendar_subparsers.add_parser('update', help='Update calendar with AI')
    calendar_update_parser.set_defaults(func=cmd_calendar_update)

    # calendar check
    calendar_check_parser = calendar_subparsers.add_parser('check', help='Check if should pause trading')
    calendar_check_parser.set_defaults(func=cmd_calendar_check)

    # order command
    order_parser = subparsers.add_parser('order', help='Advanced order types')
    order_subparsers = order_parser.add_subparsers(dest='order_command', help='Order commands')

    # order bracket
    order_bracket_parser = order_subparsers.add_parser('bracket', help='Place bracket order (entry + SL + TP)')
    order_bracket_parser.add_argument('action', choices=['BUY', 'SELL', 'buy', 'sell'], help='Trade action')
    order_bracket_parser.add_argument('volume', type=float, help='Volume in lots')
    order_bracket_parser.add_argument('--entry', '-e', type=float, help='Entry price (omit for market order)')
    order_bracket_parser.add_argument('--stop-loss', '-sl', type=float, required=True, help='Stop loss price')
    order_bracket_parser.add_argument('--take-profit', '-tp', type=float, required=True, help='Take profit price')
    order_bracket_parser.set_defaults(func=cmd_order_bracket)

    # order oco
    order_oco_parser = order_subparsers.add_parser('oco', help='Place OCO (One Cancels Other) order')
    order_oco_parser.add_argument('volume', type=float, help='Volume in lots')
    order_oco_parser.add_argument('--buy-price', '-b', type=float, required=True, help='Buy stop price')
    order_oco_parser.add_argument('--sell-price', '-s', type=float, required=True, help='Sell stop price')
    order_oco_parser.add_argument('--stop-loss', '-sl', type=float, default=50, help='Stop loss in points (default: 50)')
    order_oco_parser.add_argument('--take-profit', '-tp', type=float, default=100, help='Take profit in points (default: 100)')
    order_oco_parser.set_defaults(func=cmd_order_oco)

    # order pending
    order_pending_parser = order_subparsers.add_parser('pending', help='Place pending order (Limit/Stop)')
    order_pending_parser.add_argument('action', choices=['BUY', 'SELL', 'buy', 'sell'], help='Trade action')
    order_pending_parser.add_argument('volume', type=float, help='Volume in lots')
    order_pending_parser.add_argument('price', type=float, help='Order price')
    order_pending_parser.add_argument('--type', '-t', choices=['LIMIT', 'STOP'], required=True, help='Order type')
    order_pending_parser.add_argument('--stop-loss', '-sl', type=float, help='Stop loss price')
    order_pending_parser.add_argument('--take-profit', '-tp', type=float, help='Take profit price')
    order_pending_parser.set_defaults(func=cmd_order_pending)

    # learn command
    learn_parser = subparsers.add_parser('learn', help='Adaptive learning system')
    learn_subparsers = learn_parser.add_subparsers(dest='learn_command', help='Learning commands')

    # learn analyze
    learn_analyze_parser = learn_subparsers.add_parser('analyze', help='Analyze trading performance')
    learn_analyze_parser.add_argument('--days', '-d', type=int, default=30, help='Days to analyze (default: 30)')
    learn_analyze_parser.set_defaults(func=cmd_learn_analyze)

    # learn strategy
    learn_strategy_parser = learn_subparsers.add_parser('strategy', help='Generate optimized strategy')
    learn_strategy_parser.set_defaults(func=cmd_learn_strategy)

    # learn params
    learn_params_parser = learn_subparsers.add_parser('params', help='Get adaptive parameters')
    learn_params_parser.add_argument('--condition', '-c', default='trending', 
                                     choices=['trending', 'ranging', 'volatile', 'breakout'],
                                     help='Market condition (default: trending)')
    learn_params_parser.add_argument('--strategy', '-s', default='default', help='Strategy name')
    learn_params_parser.set_defaults(func=cmd_learn_params)

    # learn summary
    learn_summary_parser = learn_subparsers.add_parser('summary', help='Show learning summary')
    learn_summary_parser.set_defaults(func=cmd_learn_summary)

    # ==================================================================
    # agent command — AI SubAgent System
    # ==================================================================
    agent_parser = subparsers.add_parser('agent', help='AI agent system (sub-agents via CLI tools)')
    agent_subparsers = agent_parser.add_subparsers(dest='agent_command', help='Agent commands')

    # Common args helper
    def _add_agent_common(p):
        p.add_argument('--tool', '-t', choices=['opencode', 'kilocode', 'gemini', 'codex'],
                        help='Force specific AI tool (default: auto-select best)')
        p.add_argument('--consensus', '-C', action='store_true',
                        help='Run on ALL tools and build consensus answer')

    # agent run <task>
    agent_run_parser = agent_subparsers.add_parser('run', help='Run free-form task on AI agent')
    agent_run_parser.add_argument('task', nargs='+', help='Task description in natural language')
    _add_agent_common(agent_run_parser)
    agent_run_parser.set_defaults(func=cmd_agent_run)

    # agent research <query>
    agent_research_parser = agent_subparsers.add_parser('research', help='Market research via AI')
    agent_research_parser.add_argument('query', nargs='+', help='Research question')
    _add_agent_common(agent_research_parser)
    agent_research_parser.set_defaults(func=cmd_agent_research)

    # agent analyze
    agent_analyze_parser = agent_subparsers.add_parser('analyze', help='Technical analysis via AI')
    agent_analyze_parser.add_argument('--symbol', '-s', default='XAUUSD', help='Symbol (default: XAUUSD)')
    agent_analyze_parser.add_argument('--timeframe', '-tf', default='H4',
                                      choices=['M5', 'M15', 'M30', 'H1', 'H4', 'D1', 'W1'],
                                      help='Timeframe (default: H4)')
    _add_agent_common(agent_analyze_parser)
    agent_analyze_parser.set_defaults(func=cmd_agent_analyze)

    # agent plan
    agent_plan_parser = agent_subparsers.add_parser('plan', help='Generate trading plan via AI')
    agent_plan_parser.add_argument('--symbol', '-s', default='XAUUSD', help='Symbol')
    agent_plan_parser.add_argument('--condition', '-c', default='unknown',
                                   help='Market condition (trending/ranging/volatile)')
    _add_agent_common(agent_plan_parser)
    agent_plan_parser.set_defaults(func=cmd_agent_plan)

    # agent review
    agent_review_parser = agent_subparsers.add_parser('review', help='Review open positions via AI')
    _add_agent_common(agent_review_parser)
    agent_review_parser.set_defaults(func=cmd_agent_review)

    # agent risk
    agent_risk_parser = agent_subparsers.add_parser('risk', help='Risk assessment via AI')
    _add_agent_common(agent_risk_parser)
    agent_risk_parser.set_defaults(func=cmd_agent_risk)

    # agent news
    agent_news_parser = agent_subparsers.add_parser('news', help='AI-powered news digest')
    agent_news_parser.add_argument('topics', nargs='*', help='Topics to research (default: gold/Fed/geopolitics)')
    _add_agent_common(agent_news_parser)
    agent_news_parser.set_defaults(func=cmd_agent_news)

    # agent daily
    agent_daily_parser = agent_subparsers.add_parser('daily', help='Run full daily routine (all sub-agents)')
    agent_daily_parser.add_argument('--symbol', '-s', default='XAUUSD', help='Symbol')
    _add_agent_common(agent_daily_parser)
    agent_daily_parser.set_defaults(func=cmd_agent_daily)

    # agent outlook
    agent_outlook_parser = agent_subparsers.add_parser('outlook', help='Quick consensus market outlook')
    agent_outlook_parser.add_argument('--symbol', '-s', default='XAUUSD', help='Symbol')
    agent_outlook_parser.add_argument('--tool', '-t', choices=['opencode', 'kilocode', 'gemini', 'codex'],
                                      help='Force specific tool (default: consensus)')
    agent_outlook_parser.set_defaults(func=cmd_agent_outlook)

    # agent tools
    agent_tools_parser = agent_subparsers.add_parser('tools', help='List available AI CLI tools')
    agent_tools_parser.set_defaults(func=cmd_agent_tools)

    # agent history
    agent_history_parser = agent_subparsers.add_parser('history', help='Show agent execution history')
    agent_history_parser.add_argument('--limit', '-n', type=int, default=20, help='Number of entries (default: 20)')
    agent_history_parser.set_defaults(func=cmd_agent_history)

    # agent metrics
    agent_metrics_parser = agent_subparsers.add_parser('metrics', help='Show agent tool metrics')
    agent_metrics_parser.set_defaults(func=cmd_agent_metrics)

    # agent schedule — sub-subcommands
    agent_sched_parser = agent_subparsers.add_parser('schedule', help='Automated task scheduler')
    agent_sched_sub = agent_sched_parser.add_subparsers(dest='schedule_command', help='Scheduler commands')

    # agent schedule start
    agent_sched_start = agent_sched_sub.add_parser('start', help='Start scheduler daemon')
    agent_sched_start.set_defaults(func=cmd_agent_schedule_start)

    # agent schedule status
    agent_sched_status = agent_sched_sub.add_parser('status', help='Show scheduled tasks')
    agent_sched_status.set_defaults(func=cmd_agent_schedule_status)

    # agent schedule log
    agent_sched_log = agent_sched_sub.add_parser('log', help='Show scheduler execution log')
    agent_sched_log.add_argument('--limit', '-n', type=int, default=20, help='Number of entries')
    agent_sched_log.set_defaults(func=cmd_agent_schedule_log)

    # agent schedule add
    agent_sched_add = agent_sched_sub.add_parser('add', help='Add a scheduled task')
    agent_sched_add.add_argument('name', help='Task name (unique identifier)')
    agent_sched_add.add_argument('--type', required=True, choices=['daily', 'interval', 'cron'],
                                  help='Schedule type')
    agent_sched_add.add_argument('--schedule', required=True,
                                  help='Schedule value (e.g., "07:00" for daily, "300" for interval)')
    agent_sched_add.add_argument('--task-type', required=True,
                                  help='Task type (news_digest, trading_plan, technical_analysis, etc.)')
    agent_sched_add.add_argument('--params', default=None,
                                  help='Task parameters as JSON string')
    agent_sched_add.set_defaults(func=cmd_agent_schedule_add)

    # agent schedule remove
    agent_sched_remove = agent_sched_sub.add_parser('remove', help='Remove a scheduled task')
    agent_sched_remove.add_argument('name', help='Task name to remove')
    agent_sched_remove.set_defaults(func=cmd_agent_schedule_remove)

    # agent schedule enable/disable
    agent_sched_toggle = agent_sched_sub.add_parser('toggle', help='Enable or disable a task')
    agent_sched_toggle.add_argument('action', choices=['enable', 'disable'], help='Enable or disable')
    agent_sched_toggle.add_argument('name', help='Task name')
    agent_sched_toggle.set_defaults(func=cmd_agent_schedule_toggle)

    # orchestrator command
    orch_parser = subparsers.add_parser('orchestrator', help='System orchestrator - coordinates all modules')
    orch_subparsers = orch_parser.add_subparsers(dest='orch_command', help='Orchestrator commands')

    # orchestrator start
    orch_start_parser = orch_subparsers.add_parser('start', help='Start orchestrator')
    orch_start_parser.add_argument('--mode', '-m', choices=['manual', 'semi', 'auto'], 
                                   default='semi', help='Operation mode (default: semi)')
    orch_start_parser.set_defaults(func=cmd_orch_start)

    # orchestrator stop
    orch_stop_parser = orch_subparsers.add_parser('stop', help='Stop orchestrator')
    orch_stop_parser.set_defaults(func=cmd_orch_stop)

    # orchestrator status
    orch_status_parser = orch_subparsers.add_parser('status', help='Show orchestrator status')
    orch_status_parser.set_defaults(func=cmd_orch_status)

    # orchestrator mode
    orch_mode_parser = orch_subparsers.add_parser('mode', help='Change operation mode')
    orch_mode_parser.add_argument('mode', choices=['manual', 'semi', 'auto'], help='New mode')
    orch_mode_parser.set_defaults(func=cmd_orch_mode)

    # ─────────────────────────────────────────────
    # BUSINESS: Signal Service
    # ─────────────────────────────────────────────
    signal_parser = subparsers.add_parser('signals', help='Telegram Signal Service — ขาย Signal รายเดือน')
    signal_sub = signal_parser.add_subparsers(dest='signal_command')

    sig_add = signal_sub.add_parser('add-subscriber', help='Add/upgrade a subscriber')
    sig_add.add_argument('--chat-id', required=True, help='Telegram chat ID')
    sig_add.add_argument('--name', required=True, help='Subscriber name')
    sig_add.add_argument('--tier', default='basic', choices=['free','basic','pro','vip'])
    sig_add.add_argument('--months', type=int, default=1)
    sig_add.add_argument('--payment', default='manual', help='Payment method')
    sig_add.set_defaults(func=cmd_signal_add_subscriber)

    sig_rm = signal_sub.add_parser('remove-subscriber', help='Deactivate a subscriber')
    sig_rm.add_argument('--chat-id', required=True)
    sig_rm.set_defaults(func=cmd_signal_remove_subscriber)

    sig_broadcast = signal_sub.add_parser('broadcast', help='Broadcast a trading signal')
    sig_broadcast.add_argument('--action', required=True, choices=['BUY','SELL','CLOSE'])
    sig_broadcast.add_argument('--price', type=float, required=True, help='Entry price')
    sig_broadcast.add_argument('--sl', type=float, default=None, help='Stop Loss')
    sig_broadcast.add_argument('--tp', type=float, default=None, help='Take Profit')
    sig_broadcast.add_argument('--confidence', type=float, default=0.75)
    sig_broadcast.add_argument('--symbol', default='XAUUSD')
    sig_broadcast.set_defaults(func=cmd_signal_broadcast)

    sig_close = signal_sub.add_parser('close-signal', help='Close/update signal outcome')
    sig_close.add_argument('--id', type=int, required=True, help='Signal ID')
    sig_close.add_argument('--price', type=float, required=True, help='Close price')
    sig_close.add_argument('--outcome', choices=['WIN','LOSS'], default='WIN')
    sig_close.set_defaults(func=cmd_signal_close)

    sig_stats = signal_sub.add_parser('stats', help='Revenue & subscriber stats')
    sig_stats.set_defaults(func=cmd_signal_stats)

    sig_remind = signal_sub.add_parser('reminders', help='Send renewal reminders')
    sig_remind.set_defaults(func=cmd_signal_reminders)

    sig_list = signal_sub.add_parser('list', help='List active subscribers')
    sig_list.set_defaults(func=cmd_signal_list)

    # ─────────────────────────────────────────────
    # BUSINESS: PAMM Manager
    # ─────────────────────────────────────────────
    pamm_parser = subparsers.add_parser('pamm', help='PAMM Investor Management — บริหารพอร์ตนักลงทุน')
    pamm_sub = pamm_parser.add_subparsers(dest='pamm_command')

    pamm_add = pamm_sub.add_parser('add-investor', help='Onboard new investor')
    pamm_add.add_argument('--name', required=True)
    pamm_add.add_argument('--amount', type=float, required=True, help='Initial capital (USD)')
    pamm_add.add_argument('--email', default='')
    pamm_add.add_argument('--contact', default='')
    pamm_add.set_defaults(func=cmd_pamm_add_investor)

    pamm_nav = pamm_sub.add_parser('update-nav', help='Update Fund NAV & distribute profit')
    pamm_nav.add_argument('--nav', type=float, required=True, help='Total fund NAV in USD')
    pamm_nav.add_argument('--note', default='')
    pamm_nav.set_defaults(func=cmd_pamm_update_nav)

    pamm_stmt = pamm_sub.add_parser('statement', help='Generate monthly statements')
    pamm_stmt.add_argument('--month', default=None, help='Month YYYY-MM (default: current)')
    pamm_stmt.set_defaults(func=cmd_pamm_statement)

    pamm_overview = pamm_sub.add_parser('overview', help='Fund overview dashboard')
    pamm_overview.set_defaults(func=cmd_pamm_overview)

    pamm_withdraw = pamm_sub.add_parser('withdraw', help='Record investor withdrawal')
    pamm_withdraw.add_argument('--id', type=int, required=True, help='Investor ID')
    pamm_withdraw.add_argument('--amount', type=float, required=True)
    pamm_withdraw.set_defaults(func=cmd_pamm_withdraw)

    # ─────────────────────────────────────────────
    # BUSINESS: Performance Tracker
    # ─────────────────────────────────────────────
    perf_parser = subparsers.add_parser('performance', help='Track Record & Performance Report')
    perf_sub = perf_parser.add_subparsers(dest='perf_command')

    perf_stats = perf_sub.add_parser('stats', help='Show performance statistics')
    perf_stats.add_argument('--days', type=int, default=0, help='Last N days (0=all-time)')
    perf_stats.set_defaults(func=cmd_perf_stats)

    perf_report = perf_sub.add_parser('report', help='Generate HTML track record report')
    perf_report.add_argument('--output', default='performance_report.html')
    perf_report.set_defaults(func=cmd_perf_report)

    perf_export = perf_sub.add_parser('export', help='Export for MyFXBook/ZuluTrade')
    perf_export.add_argument('--format', choices=['myfxbook', 'json'], default='json')
    perf_export.add_argument('--output', default='export.json')
    perf_export.set_defaults(func=cmd_perf_export)

    perf_equity = perf_sub.add_parser('snapshot', help='Record an equity snapshot')
    perf_equity.add_argument('--balance', type=float, required=True)
    perf_equity.add_argument('--equity', type=float, required=True)
    perf_equity.set_defaults(func=cmd_perf_snapshot)

    # ─── Graph (LangGraph pipeline) ─────────────────────────────────────────────
    graph_parser = subparsers.add_parser('graph', help='LangGraph trading pipeline')
    graph_sub = graph_parser.add_subparsers(dest='graph_command')

    graph_run = graph_sub.add_parser('run', help='Run the full trading pipeline')
    graph_run.add_argument('--symbol', default='XAUUSD', help='Symbol (default: XAUUSD)')
    graph_run.add_argument('--timeframe', default='H1', help='Timeframe (default: H1)')
    graph_run.add_argument('--auto', action='store_true', help='Auto-approve (simulation mode)')
    graph_run.set_defaults(func=cmd_graph_run)

    graph_show = graph_sub.add_parser('show', help='Show graph structure')
    graph_show.set_defaults(func=cmd_graph_show)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if not hasattr(args, 'func'):
        # Check if it's a subcommand without func
        if args.command == 'news' and hasattr(args, 'news_command'):
            news_parser.print_help()
        elif args.command == 'notify' and hasattr(args, 'notify_command'):
            notify_parser.print_help()
        elif args.command == 'journal' and hasattr(args, 'journal_command'):
            journal_parser.print_help()
        elif args.command == 'calendar' and hasattr(args, 'calendar_command'):
            calendar_parser.print_help()
        elif args.command == 'order' and hasattr(args, 'order_command'):
            order_parser.print_help()
        elif args.command == 'learn' and hasattr(args, 'learn_command'):
            learn_parser.print_help()
        elif args.command == 'agent' and hasattr(args, 'agent_command'):
            if args.agent_command == 'schedule' and hasattr(args, 'schedule_command'):
                agent_sched_parser.print_help()
            else:
                agent_parser.print_help()
        elif args.command == 'orchestrator' and hasattr(args, 'orch_command'):
            orch_parser.print_help()
        elif args.command == 'signals' and hasattr(args, 'signal_command'):
            signal_parser.print_help()
        elif args.command == 'pamm' and hasattr(args, 'pamm_command'):
            pamm_parser.print_help()
        elif args.command == 'performance' and hasattr(args, 'perf_command'):
            perf_parser.print_help()
        elif args.command == 'graph' and hasattr(args, 'graph_command'):
            graph_parser.print_help()
        else:
            parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == '__main__':
    main()
