# Architecture Overview

This document describes the high-level architecture of ClawGold.

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLI Layer                                │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐           │
│  │  Trade   │ │  Monitor │ │   News   │ │  Analyze │           │
│  │ Commands │ │ Commands │ │ Commands │ │ Commands │           │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘           │
└─────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────────┐
│                     Business Logic Layer                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ Risk Manager │  │Advanced Trader│  │News Aggregator│         │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ AI Researcher│  │   Sentiment  │  │ Position Mon │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────────┐
│                     Infrastructure Layer                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ MT5 Manager  │  │   News DB    │  │   Logger     │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│  ┌──────────────┐  ┌──────────────┐                            │
│  │Config Loader │  │ Config Validator                          │
│  └──────────────┘  └──────────────┘                            │
└─────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────────┐
│                     External Services                            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐       │
│  │   MT5    │  │ OpenCode │  │ KiloCode │  │  Gemini  │       │
│  │ Terminal │  │   CLI    │  │   CLI    │  │   CLI    │       │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘       │
└─────────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. CLI Layer (`claw.py`)

The command-line interface providing unified access to all functionality.

**Responsibilities:**
- Parse command-line arguments
- Route commands to appropriate handlers
- Display formatted output
- Handle user interactions

### 2. MT5 Manager (`mt5_manager.py`)

Context manager for MetaTrader 5 integration.

**Responsibilities:**
- Manage MT5 connection lifecycle
- Execute trades (market orders)
- Retrieve account information
- Fetch price data and positions
- Handle connection errors

### 3. Risk Manager (`risk_manager.py`)

Trading risk assessment and limits enforcement.

**Responsibilities:**
- Validate trades against risk rules
- Calculate position sizes
- Monitor daily loss limits
- Track margin levels
- Prevent over-trading

### 4. Advanced Trader (`advanced_trader.py`)

Sophisticated trading strategies implementation.

**Strategies:**
- **Trailing Stop**: Dynamic stop-loss adjustment
- **Grid Trading**: Multiple pending orders at intervals
- **Breakout Detection**: Support/resistance level breaks
- **Scalping**: Short-term momentum trading
- **Multi-Timeframe Analysis**: EMA crossovers

### 5. News Aggregator (`news_aggregator.py`)

AI-powered news research and sentiment analysis.

**Responsibilities:**
- Coordinate AI tool queries
- Aggregate multiple research sources
- Calculate sentiment scores
- Generate trading signals
- Cache research results

### 6. AI Researcher (`ai_researcher.py`)

Interface to external AI CLI tools.

**Supported Tools:**
- OpenCode CLI
- KiloCode CLI
- Google Gemini CLI

**Features:**
- Parallel execution
- Response caching
- Confidence extraction
- Sentiment analysis

### 7. Sentiment Analyzer (`sentiment_analyzer.py`)

Keyword-based sentiment analysis engine.

**Methodology:**
- Bullish/bearish keyword matching
- Impact score calculation
- Sentiment trend tracking
- Keyword frequency analysis

### 8. News Database (`news_db.py`)

SQLite database for persistent storage.

**Tables:**
- `news_articles`: Stored news and analysis
- `ai_research`: Cached AI responses
- `sentiment_history`: Sentiment trends
- `market_events`: Economic events
- `price_correlations`: News-price relationships

## Data Flow

### Trade Execution Flow

```
User Command → CLI → Risk Manager → MT5 Manager → MT5 Terminal
                   ↓
              [Validation]
                   ↓
              Position Opened → Database → Logger
```

### News Research Flow

```
Query → AI Researcher → Parallel AI Calls
              ↓
        Cache Check → [Hit] → Return Cached
              ↓
        [Miss] → Execute AI Tools
              ↓
        Aggregate Results → Sentiment Analysis
              ↓
        Generate Signal → Store in DB → Return to User
```

### Position Monitoring Flow

```
Monitor Command → Position Monitor → MT5 Manager
         ↓
    [Loop] Fetch Positions
         ↓
    Check Thresholds → Alert if Triggered
         ↓
    Update Trailing Stops
         ↓
    Display Status
```

## Design Patterns

### 1. Context Managers

Used for resource management (MT5 connections, database transactions).

```python
with MT5Manager() as mt5:
    account = mt5.get_account_info()
    # Connection auto-closes on exit
```

### 2. Strategy Pattern

Trading strategies are interchangeable.

```python
class TradingStrategy(ABC):
    @abstractmethod
    def analyze(self, symbol: str) -> Signal:
        pass
```

### 3. Observer Pattern

Position monitoring uses event-driven alerts.

```python
monitor = PositionMonitor(on_alert=handler_function)
```

### 4. Repository Pattern

Database operations abstracted behind repository classes.

```python
news_db = NewsDatabase()
articles = news_db.get_recent_news(symbol)
```

## Threading Model

### Parallel Operations

- **AI Research**: Multiple AI tools run concurrently using `ThreadPoolExecutor`
- **News Fetching**: Background refresh of news feeds
- **Position Monitoring**: Continuous monitoring in separate thread

### Thread Safety

- Database connections are per-thread
- MT5 connection is single-threaded (serializes access)
- Configuration is read-only after initialization

## Caching Strategy

### Cache Layers

1. **AI Research Cache**: 6-hour TTL for AI responses
2. **Price Cache**: 5-second TTL for tick data
3. **News Cache**: 1-hour TTL for news articles

### Cache Invalidation

- Time-based expiration
- Manual clear via CLI
- Automatic cleanup of old data

## Error Handling

### Error Types

1. **Connection Errors**: MT5 disconnection, network issues
2. **Validation Errors**: Risk limit violations, invalid parameters
3. **Execution Errors**: Order rejection, insufficient margin
4. **AI Tool Errors**: CLI not found, timeout, rate limiting

### Error Recovery

- Automatic reconnection to MT5
- Fallback to cached data
- Graceful degradation of features
- Comprehensive error logging

## Security Considerations

### Credential Management

- Credentials stored in config.yaml or environment variables
- .env file support for local development
- No credentials in logs or error messages

### Data Protection

- Local-only database (no cloud)
- No sensitive data in AI queries
- Log rotation to prevent data accumulation

## Performance Optimizations

1. **Connection Pooling**: Reuse MT5 connections
2. **Parallel AI Queries**: Reduce research time
3. **Database Indexing**: Fast news retrieval
4. **Lazy Loading**: Load modules on demand
5. **Caching**: Reduce redundant operations

## Extension Points

### Adding New Strategies

1. Create strategy class in `scripts/strategies/`
2. Implement required interface
3. Register in CLI

### Adding New AI Tools

1. Add tool handler in `ai_researcher.py`
2. Define command and prompt template
3. Add to tool registry

### Adding New Commands

1. Create command function in `claw.py`
2. Define argument parser
3. Add to subparsers

## Testing Architecture

### Test Levels

1. **Unit Tests**: Individual functions
2. **Integration Tests**: Component interactions
3. **Live Tests**: Real MT5 connection

### Mock Strategy

- MT5 connection mocked for unit tests
- AI tools return canned responses
- Database uses in-memory SQLite

## Deployment Considerations

### Requirements

- Windows OS (for MT5)
- Python 3.10+
- Sufficient RAM for AI tool execution
- Disk space for database growth

### Monitoring

- Log files in `logs/` directory
- Database statistics via CLI
- Health check endpoint (future)

## Future Architecture

### Planned Enhancements

1. **Web Dashboard**: Real-time monitoring UI
2. **API Server**: REST API for external integrations
3. **Machine Learning**: Price prediction models
4. **Multi-Asset**: Support for other instruments
5. **Cloud Sync**: Optional cloud backup

---

*Last Updated: 2026-03-04*
