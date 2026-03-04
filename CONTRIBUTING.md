# Contributing to ClawGold

Thank you for your interest in contributing to ClawGold! This document provides guidelines for contributing to the project.

## 🦞 Code of Conduct

- Be respectful and constructive in all interactions
- Focus on what is best for the community
- Show empathy towards other community members

## How Can I Contribute?

### Reporting Bugs

Before creating bug reports, please check the existing issues to avoid duplicates. When you create a bug report, include:

- **Use a clear descriptive title**
- **Describe the exact steps to reproduce the problem**
- **Provide specific examples** (commands, code snippets, config)
- **Describe the behavior you observed** vs what you expected
- **Include system information** (OS, Python version, MT5 version)

```markdown
**Bug Report Template:**

**Description:**
[Clear description of the bug]

**Steps to Reproduce:**
1. Run '...'
2. Execute '...'
3. See error

**Expected Behavior:**
[What you expected to happen]

**Actual Behavior:**
[What actually happened]

**Environment:**
- OS: [e.g., Windows 11]
- Python: [e.g., 3.11.4]
- MT5: [e.g., build 3661]
- ClawGold: [e.g., v1.0.0]
```

### Suggesting Enhancements

Enhancement suggestions are welcome! Please provide:

- **Clear use case** - What problem does it solve?
- **Detailed description** - How should it work?
- **Possible implementation** - Any ideas on how to build it?

### Pull Requests

1. Fork the repository
2. Create a branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests and linting
5. Commit with clear messages
6. Push to your fork
7. Open a Pull Request

## Development Setup

```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/ClawGold.git
cd ClawGold

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dev dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Run tests
pytest tests/

# Run linting
flake8 scripts/
black scripts/
```

## Coding Standards

### Python Style Guide

- Follow PEP 8
- Use type hints where possible
- Maximum line length: 100 characters
- Use docstrings for all public functions

```python
def calculate_position_size(
    account_balance: float,
    risk_percent: float,
    stop_loss_pips: float
) -> float:
    """
    Calculate recommended position size based on risk parameters.
    
    Args:
        account_balance: Current account balance in USD
        risk_percent: Risk percentage per trade (e.g., 0.01 for 1%)
        stop_loss_pips: Stop loss distance in pips
    
    Returns:
        Recommended position size in lots
    
    Example:
        >>> calculate_position_size(10000, 0.01, 50)
        0.2
    """
    # Implementation
    pass
```

### Commit Message Format

```
type(scope): subject

body (optional)

footer (optional)
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style (formatting, no logic change)
- `refactor`: Code refactoring
- `perf`: Performance improvements
- `test`: Adding/updating tests
- `chore`: Maintenance tasks

**Examples:**
```
feat(strategies): add martingale strategy

fix(mt5): handle connection timeout gracefully
docs(readme): update installation instructions
```

## Project Structure

When adding new features, follow the existing structure:

```
scripts/
├── mt5_manager.py      # MT5 connection & operations
├── risk_manager.py     # Risk management
├── advanced_trader.py  # Trading strategies
├── news_aggregator.py  # News & AI research
└── [your_module].py    # New modules here
```

## Testing Guidelines

### Writing Tests

```python
# tests/test_risk_manager.py
import pytest
from scripts.risk_manager import RiskManager

@pytest.fixture
def config():
    return {
        'trading': {'risk_per_trade': 0.01},
        'risk': {'max_position_size': 1.0}
    }

def test_position_size_limit(config):
    rm = RiskManager(config)
    can_trade, reason = rm.can_trade('XAUUSD', 'BUY', 2.0)
    assert not can_trade
    assert 'exceeds max position size' in reason
```

### Test Categories

1. **Unit Tests**: Test individual functions
2. **Integration Tests**: Test component interactions
3. **Live Tests**: Test with real MT5 (marked with `@pytest.mark.live`)

## Strategy Development Guide

Want to add a new trading strategy? Here's how:

```python
# scripts/strategies/my_strategy.py

from dataclasses import dataclass
from typing import Dict
from scripts.mt5_manager import MT5Manager

@dataclass
class MyStrategyConfig:
    param1: float = 10.0
    param2: int = 5

class MyStrategy:
    """Description of your strategy."""
    
    def __init__(self, config: Dict):
        self.config = config
        self.strategy_config = MyStrategyConfig()
    
    def analyze(self, symbol: str) -> Dict:
        """Analyze market and return signal."""
        with MT5Manager() as mt5:
            # Your analysis logic
            return {
                'signal': 'buy',  # or 'sell', 'hold'
                'confidence': 0.8,
                'reason': 'Your reasoning'
            }
```

Then add CLI command in `claw.py`:

```python
def cmd_my_strategy(args):
    from scripts.strategies.my_strategy import MyStrategy
    # Implementation
```

## Documentation

- Update README.md if adding new features
- Add docstrings to all public APIs
- Update CHANGELOG.md with your changes
- Add examples for complex features

## Release Process

Maintainers only:

1. Update version in `__init__.py`
2. Update CHANGELOG.md
3. Create git tag: `git tag v1.x.x`
4. Push tag: `git push origin v1.x.x`
5. Create GitHub release

## Questions?

- Open an issue for questions
- Join discussions in existing issues
- Contact: [maintainer@clawgold.dev](mailto:maintainer@clawgold.dev)

---

**Thank you for contributing to ClawGold! 🦞**
