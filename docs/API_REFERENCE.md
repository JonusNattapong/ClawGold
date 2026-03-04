# API Reference

Complete API documentation for ClawGold modules.

## Table of Contents

- [MT5 Manager](#mt5-manager)
- [Risk Manager](#risk-manager)
- [Advanced Trader](#advanced-trader)
- [News Aggregator](#news-aggregator)
- [AI Researcher](#ai-researcher)
- [Sentiment Analyzer](#sentiment-analyzer)
- [News Database](#news-database)

---

## MT5 Manager

### MT5Manager

Context manager for MetaTrader 5 operations.

```python
from scripts.mt5_manager import MT5Manager

with MT5Manager(config_path: Optional[str] = None) as mt5:
    # Use mt5 instance
    pass
```

#### Methods

##### `get_account_info() -> Optional[Dict]`

Retrieve account information.

**Returns:**
```python
{
    'balance': float,      # Account balance
    'equity': float,       # Account equity
    'margin': float,       # Used margin
    'margin_free': float,  # Free margin
    'profit': float,       # Current profit/loss
    'margin_level': float, # Margin level percentage
    'currency': str        # Account currency
}
```

**Example:**
```python
with MT5Manager() as mt5:
    account = mt5.get_account_info()
    print(f"Balance: {account['balance']} USD")
```

---

##### `get_positions(symbol: Optional[str] = None) -> List[Dict]`

Get open positions.

**Parameters:**
- `symbol` (str, optional): Filter by symbol

**Returns:**
```python
[
    {
        'ticket': int,
        'symbol': str,
        'type': int,           # 0=Buy, 1=Sell
        'volume': float,
        'price_open': float,
        'price_current': float,
        'profit': float,
        'swap': float
    }
]
```

---

##### `get_tick(symbol: str) -> Optional[Dict]`

Get current price tick.

**Parameters:**
- `symbol` (str): Trading symbol (e.g., 'XAUUSD')

**Returns:**
```python
{
    'bid': float,
    'ask': float,
    'last': float,
    'time': int,
    'volume': int
}
```

---

##### `execute_trade(action: str, volume: float, deviation: int = 10) -> Dict`

Execute market order.

**Parameters:**
- `action` (str): 'BUY' or 'SELL'
- `volume` (float): Volume in lots
- `deviation` (int): Price deviation in points

**Returns:**
```python
{
    'success': bool,
    'order': int,          # Order ticket
    'volume': float,
    'price': float,
    'error': str           # Only if success=False
}
```

---

##### `close_position(ticket: int) -> Dict`

Close specific position.

**Parameters:**
- `ticket` (int): Position ticket number

**Returns:**
```python
{
    'success': bool,
    'ticket': int,
    'profit': float,
    'error': str
}
```

---

##### `close_all_positions() -> List[Dict]`

Close all open positions.

**Returns:** List of close results for each position.

---

## Risk Manager

### RiskManager

Trading risk assessment and management.

```python
from scripts.risk_manager import RiskManager, RiskLimits

config = {'trading': {'risk_per_trade': 0.01}, 'risk': {...}}
rm = RiskManager(config)
```

#### Methods

##### `can_trade(symbol: str, action: str, volume: float, account_info: dict = None, positions: list = None) -> Tuple[bool, str]`

Check if trade is allowed.

**Parameters:**
- `symbol` (str): Trading symbol
- `action` (str): 'BUY' or 'SELL'
- `volume` (float): Trade volume
- `account_info` (dict, optional): Current account info
- `positions` (list, optional): Current positions

**Returns:**
```python
(can_trade: bool, reason: str)
```

**Example:**
```python
can_trade, reason = rm.can_trade('XAUUSD', 'BUY', 0.1)
if not can_trade:
    print(f"Trade rejected: {reason}")
```

---

##### `calculate_position_size(account_balance: float, stop_loss_pips: float = 50) -> float`

Calculate recommended position size.

**Parameters:**
- `account_balance` (float): Account balance
- `stop_loss_pips` (float): Stop loss distance

**Returns:** Recommended volume in lots

---

##### `get_risk_summary(account_info: dict, positions: list) -> dict`

Generate risk summary.

**Returns:**
```python
{
    'balance': float,
    'equity': float,
    'margin_used': float,
    'margin_level': float,
    'total_positions': int,
    'margin_status': str  # 'SAFE', 'WARNING', 'DANGER'
}
```

---

## Advanced Trader

### AdvancedTrader

Sophisticated trading strategies.

```python
from scripts.advanced_trader import AdvancedTrader, TrailingStopConfig

config = {...}
trader = AdvancedTrader(config)
```

#### Methods

##### `apply_trailing_stop(ticket: int, config: TrailingStopConfig) -> bool`

Apply trailing stop to position.

**Parameters:**
- `ticket` (int): Position ticket
- `config` (TrailingStopConfig): Trailing stop settings

**TrailingStopConfig:**
```python
{
    'activation_profit': float,  # Points to activate
    'trailing_distance': float,  # Points to trail
    'step_size': float           # Minimum step
}
```

---

##### `start_grid_trading(config: GridConfig, center_price: float, direction: str = 'both') -> List[TradeLevel]`

Initialize grid trading.

**GridConfig:**
```python
{
    'levels': int,         # Number of grid levels
    'grid_size': float,    # Points between levels
    'volume_per_level': float,
    'take_profit': float,
    'stop_loss': float
}
```

---

##### `detect_breakout(symbol: str, config: BreakoutConfig) -> Tuple[bool, str]`

Detect price breakout.

**Returns:** `(is_breakout: bool, direction: str)`

Direction: `'buy'`, `'sell'`, or `''`

---

##### `multi_timeframe_analysis(symbol: str) -> Dict`

Analyze multiple timeframes.

**Returns:**
```python
{
    'timeframes': {
        'M15': {'signal': str, 'price': float, 'ema_20': float, ...},
        'H1': {...},
        'H4': {...},
        'D1': {...}
    },
    'overall_signal': str,
    'confluence_score': float
}
```

---

## News Aggregator

### NewsAggregator

AI-powered news research and analysis.

```python
from scripts.news_aggregator import NewsAggregator

aggregator = NewsAggregator(db_path='data/news.db')
```

#### Methods

##### `research_symbol(symbol: str, query: str = None, hours: int = 24, use_ai: bool = True) -> Dict`

Comprehensive research on a symbol.

**Parameters:**
- `symbol` (str): Trading symbol
- `query` (str, optional): Custom search query
- `hours` (int): Lookback period
- `use_ai` (bool): Use AI tools

**Returns:**
```python
{
    'symbol': str,
    'query': str,
    'cached_news': List[Dict],
    'ai_analysis': Dict,
    'sentiment': Dict,
    'trading_signal': Dict
}
```

---

##### `get_sentiment_trend(symbol: str, hours: int = 72) -> Dict`

Get sentiment trend over time.

**Returns:**
```python
{
    'symbol': str,
    'trend': str,        # 'improving', 'deteriorating', 'stable'
    'momentum': float,
    'current_sentiment': float,
    'history': List[Dict]
}
```

---

##### `get_trading_signal(research_results: Dict) -> Dict`

Generate trading signal from research.

**Returns:**
```python
{
    'direction': str,      # 'buy', 'sell', 'neutral'
    'confidence': float,   # 0-1
    'strength': int,       # 0-3
    'recommendation': str, # e.g., 'strong_buy'
    'factors': List[str]
}
```

---

## AI Researcher

### AIResearcher

Interface to AI CLI tools.

```python
from scripts.ai_researcher import AIResearcher, AIResult

researcher = AIResearcher(cache_db=news_db, cache_ttl_hours=6)
```

#### Methods

##### `research_single(tool: str, query: str, use_cache: bool = True) -> AIResult`

Research using single AI tool.

**Parameters:**
- `tool` (str): 'opencode', 'kilocode', or 'gemini'
- `query` (str): Research query
- `use_cache` (bool): Use cached results

**Returns:** `AIResult` object

**AIResult:**
```python
{
    'tool': str,
    'query': str,
    'response': str,
    'success': bool,
    'execution_time': float,
    'confidence': float,
    'sources': List[str]
}
```

---

##### `research_all(query: str, tools: List[str] = None, use_cache: bool = True, parallel: bool = True) -> List[AIResult]`

Research using all AI tools.

**Parameters:**
- `tools` (List[str], optional): Specific tools to use
- `parallel` (bool): Run in parallel

**Returns:** List of `AIResult` objects

---

##### `aggregate_results(results: List[AIResult]) -> Dict`

Aggregate results from multiple tools.

**Returns:**
```python
{
    'success': bool,
    'consensus_sentiment': str,
    'consensus_strength': float,
    'average_confidence': float,
    'tools_used': List[str],
    'sentiment_distribution': Dict,
    'combined_analysis': str
}
```

---

## Sentiment Analyzer

### SentimentAnalyzer

Sentiment analysis engine.

```python
from scripts.sentiment_analyzer import SentimentAnalyzer, SentimentScore

analyzer = SentimentAnalyzer()
```

#### Methods

##### `analyze_text(text: str) -> SentimentScore`

Analyze sentiment of text.

**Returns:**
```python
{
    'score': float,        # -1 to 1
    'confidence': float,   # 0 to 1
    'label': str,          # 'bullish', 'bearish', 'neutral'
    'keywords': List[str]
}
```

---

##### `analyze_multiple(texts: List[str]) -> Dict`

Analyze multiple texts.

**Returns:**
```python
{
    'average_score': float,
    'average_confidence': float,
    'dominant_sentiment': str,
    'sentiment_distribution': Dict,
    'all_keywords': List[str],
    'keyword_frequency': Dict
}
```

---

##### `calculate_impact_score(text: str, source_weight: float = 1.0) -> float`

Calculate potential market impact.

**Returns:** Impact score (0-1)

---

## News Database

### NewsDatabase

SQLite database for news storage.

```python
from scripts.news_db import NewsDatabase, NewsArticle

db = NewsDatabase('data/news.db')
```

#### Methods

##### `add_news(article: NewsArticle) -> int`

Add news article.

**NewsArticle:**
```python
{
    'id': Optional[int],
    'title': str,
    'content': str,
    'source': str,
    'url': Optional[str],
    'published_at': datetime,
    'symbol': str,
    'category': str,
    'sentiment': Optional[float],
    'impact_score': Optional[float],
    'ai_analysis': Optional[str]
}
```

**Returns:** Article ID

---

##### `get_recent_news(symbol: str, hours: int = 24, category: str = None) -> List[Dict]`

Get recent news for symbol.

---

##### `add_ai_research(query: str, tool: str, response: str, symbol: str = None, category: str = None, confidence: float = None, sources: List[str] = None, ttl_hours: int = 24) -> int`

Store AI research result.

---

##### `get_cached_research(query: str, tool: str, max_age_hours: int = 24) -> Optional[Dict]`

Get cached research if not expired.

---

##### `add_sentiment_snapshot(symbol: str, sentiment: float, news_count: int, bullish: int, bearish: int, neutral: int, weighted_score: float)`

Record sentiment snapshot.

---

##### `get_sentiment_trend(symbol: str, hours: int = 24) -> List[Dict]`

Get sentiment history.

---

## Configuration

### Config Loader

```python
from scripts.config_loader import load_config

config = load_config('config.yaml')
```

**Config Structure:**
```python
{
    'trading': {
        'mode': str,              # 'real' or 'simulation'
        'symbol': str,
        'risk_per_trade': float
    },
    'risk': {
        'max_positions': int,
        'max_daily_loss': float,
        'max_position_size': float
    },
    'mt5': {
        'login': int,
        'password': str,
        'server': str
    }
}
```

---

## Examples

### Complete Trading Workflow

```python
from scripts.mt5_manager import MT5Manager
from scripts.risk_manager import RiskManager
from scripts.news_aggregator import NewsAggregator
from scripts.config_loader import load_config

config = load_config('config.yaml')

# 1. Research
aggregator = NewsAggregator()
research = aggregator.research_symbol('XAUUSD')
signal = research['trading_signal']

if signal['confidence'] > 0.7 and signal['direction'] == 'buy':
    # 2. Check risk
    rm = RiskManager(config)
    
    with MT5Manager() as mt5:
        account = mt5.get_account_info()
        positions = mt5.get_positions()
        
        can_trade, reason = rm.can_trade(
            'XAUUSD', 'BUY', 0.1, account, positions
        )
        
        if can_trade:
            # 3. Execute
            result = mt5.execute_trade('BUY', 0.1)
            print(f"Trade executed: {result}")
```

---

*Last Updated: 2026-03-04*
