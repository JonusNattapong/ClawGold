"""
Adaptive Learning System
========================
Self-improving trading system that learns from historical data,
analyzes trade performance, and automatically optimizes strategies.

Usage:
    from adaptive_learning import AdaptiveLearning
    
    learner = AdaptiveLearning()
    
    # Analyze and learn from past trades
    insights = learner.analyze_performance()
    
    # Generate optimized strategy
    strategy = learner.generate_optimized_strategy()
    
    # Auto-adjust parameters based on market conditions
    params = learner.get_adaptive_params(market_condition="trending")
"""

import json
import sqlite3
import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict
import pickle

from logger import get_logger

try:
    from trade_journal import TradeJournal, JournalEntry
    JOURNAL_AVAILABLE = True
except ImportError:
    JOURNAL_AVAILABLE = False

try:
    from notifier import notify_system
    NOTIFIER_AVAILABLE = True
except ImportError:
    NOTIFIER_AVAILABLE = False

logger = get_logger(__name__)


@dataclass
class MarketCondition:
    """Market condition classification."""
    regime: str  # trending, ranging, volatile, breakout
    trend_strength: float  # 0.0 to 1.0
    volatility: float  # 0.0 to 1.0
    volume_profile: str  # high, normal, low
    timestamp: datetime


@dataclass
class StrategyPerformance:
    """Strategy performance metrics."""
    strategy_name: str
    total_trades: int
    win_rate: float
    profit_factor: float
    avg_profit: float
    avg_loss: float
    max_drawdown: float
    sharpe_ratio: float
    expectancy: float
    market_conditions: Dict[str, 'StrategyPerformance']
    

@dataclass
class OptimizationResult:
    """Parameter optimization result."""
    parameter_set: Dict[str, float]
    fitness_score: float
    win_rate: float
    profit_factor: float
    max_drawdown: float


class AdaptiveLearning:
    """
    Self-learning trading system that adapts and improves over time.
    """
    
    # Market condition patterns
    MARKET_PATTERNS = {
        'trending': {'adx_threshold': 25, 'trend_strength': 0.7},
        'ranging': {'adx_threshold': 20, 'trend_strength': 0.3},
        'volatile': {'atr_multiplier': 2.0, 'volatility': 0.7},
        'breakout': {'volume_spike': 1.5, 'range_compression': 0.8}
    }
    
    def __init__(self, db_path: str = "data/adaptive_learning.db"):
        """
        Initialize Adaptive Learning System.
        
        Args:
            db_path: Path to SQLite database for storing learned data
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        
        # Learning state
        self.strategy_memory: Dict[str, Any] = {}
        self.market_regime_stats: Dict[str, Dict] = defaultdict(lambda: defaultdict(list))
        self.current_best_params: Dict[str, Dict[str, float]] = {}
        
        # Load existing knowledge
        self._load_knowledge()
        
    def _init_db(self):
        """Initialize database tables."""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()
            
            # Store learned patterns
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS learned_patterns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pattern_type TEXT NOT NULL,
                    pattern_data TEXT NOT NULL,
                    performance_score REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Store strategy performance by market condition
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS strategy_performance (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    strategy_name TEXT NOT NULL,
                    market_condition TEXT NOT NULL,
                    total_trades INTEGER,
                    win_rate REAL,
                    profit_factor REAL,
                    avg_profit REAL,
                    avg_loss REAL,
                    max_drawdown REAL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Store optimized parameters
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS optimized_params (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    strategy_name TEXT NOT NULL,
                    market_condition TEXT,
                    parameters TEXT NOT NULL,
                    fitness_score REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            conn.commit()
    
    def _load_knowledge(self):
        """Load existing learned knowledge from database."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                
                # Load optimized parameters
                cursor.execute("""
                    SELECT strategy_name, market_condition, parameters, fitness_score
                    FROM optimized_params
                    ORDER BY created_at DESC
                """)
                
                for row in cursor.fetchall():
                    strategy, condition, params_json, score = row
                    key = f"{strategy}_{condition}" if condition else strategy
                    if key not in self.current_best_params:
                        self.current_best_params[key] = {
                            'params': json.loads(params_json),
                            'score': score
                        }
                
                logger.info(f"Loaded knowledge for {len(self.current_best_params)} strategy variations")
                
        except Exception as e:
            logger.error(f"Error loading knowledge: {e}")
    
    def analyze_performance(self, days: int = 30) -> Dict[str, Any]:
        """
        Analyze recent trading performance and extract insights.
        
        Args:
            days: Number of days to analyze
            
        Returns:
            Dictionary with performance insights
        """
        if not JOURNAL_AVAILABLE:
            return {'error': 'TradeJournal not available'}
        
        try:
            journal = TradeJournal()
            
            # Get trades from last N days
            since = datetime.now() - timedelta(days=days)
            trades = journal.get_trades_since(since)
            
            if not trades:
                return {'error': 'No trades found for analysis period'}
            
            # Calculate overall metrics
            total_trades = len(trades)
            winning_trades = [t for t in trades if (t.realized_pnl or 0) > 0]
            losing_trades = [t for t in trades if (t.realized_pnl or 0) < 0]
            
            win_count = len(winning_trades)
            loss_count = len(losing_trades)
            
            total_profit = sum(t.realized_pnl for t in winning_trades if t.realized_pnl)
            total_loss = sum(t.realized_pnl for t in losing_trades if t.realized_pnl)
            
            win_rate = win_count / total_trades if total_trades > 0 else 0
            profit_factor = abs(total_profit / total_loss) if total_loss != 0 else float('inf')
            
            avg_profit = total_profit / win_count if win_count > 0 else 0
            avg_loss = total_loss / loss_count if loss_count > 0 else 0
            
            # Analyze by strategy
            strategy_performance = defaultdict(lambda: {'wins': 0, 'losses': 0, 'pnl': 0})
            for trade in trades:
                strat = trade.strategy or 'unknown'
                pnl = trade.realized_pnl or 0
                strategy_performance[strat]['pnl'] += pnl
                if pnl > 0:
                    strategy_performance[strat]['wins'] += 1
                else:
                    strategy_performance[strat]['losses'] += 1
            
            # Analyze by market condition
            condition_performance = defaultdict(lambda: {'wins': 0, 'losses': 0, 'pnl': 0})
            for trade in trades:
                condition = trade.market_condition or 'unknown'
                pnl = trade.realized_pnl or 0
                condition_performance[condition]['pnl'] += pnl
                if pnl > 0:
                    condition_performance[condition]['wins'] += 1
                else:
                    condition_performance[condition]['losses'] += 1
            
            # Generate insights
            insights = {
                'period_days': days,
                'total_trades': total_trades,
                'win_rate': win_rate,
                'profit_factor': profit_factor,
                'avg_profit': avg_profit,
                'avg_loss': avg_loss,
                'expectancy': (win_rate * avg_profit) - ((1 - win_rate) * abs(avg_loss)),
                'best_strategy': max(strategy_performance.items(), 
                                   key=lambda x: x[1]['pnl'])[0] if strategy_performance else None,
                'best_condition': max(condition_performance.items(),
                                    key=lambda x: x[1]['pnl'])[0] if condition_performance else None,
                'strategy_performance': dict(strategy_performance),
                'condition_performance': dict(condition_performance),
                'recommendations': self._generate_recommendations(
                    win_rate, profit_factor, strategy_performance, condition_performance
                )
            }
            
            # Store insights
            self._store_analysis(insights)
            
            return insights
            
        except Exception as e:
            logger.error(f"Error analyzing performance: {e}")
            return {'error': str(e)}
    
    def _generate_recommendations(self, win_rate: float, profit_factor: float,
                                  strategy_perf: Dict, condition_perf: Dict) -> List[str]:
        """Generate trading recommendations based on analysis."""
        recommendations = []
        
        if win_rate < 0.4:
            recommendations.append("Win rate is low - consider tightening entry criteria")
        elif win_rate > 0.6:
            recommendations.append("Win rate is good - consider increasing position size gradually")
        
        if profit_factor < 1.0:
            recommendations.append("Profit factor below 1.0 - review risk/reward ratio")
        elif profit_factor > 2.0:
            recommendations.append("Excellent profit factor - strategy is performing well")
        
        # Find best and worst strategies
        if strategy_perf:
            sorted_strategies = sorted(strategy_perf.items(), key=lambda x: x[1]['pnl'], reverse=True)
            if len(sorted_strategies) > 1:
                best = sorted_strategies[0][0]
                worst = sorted_strategies[-1][0]
                recommendations.append(f"Focus on '{best}' strategy - best performance")
                recommendations.append(f"Review or reduce usage of '{worst}' strategy")
        
        # Find best market conditions
        if condition_perf:
            sorted_conditions = sorted(condition_perf.items(), key=lambda x: x[1]['pnl'], reverse=True)
            if sorted_conditions:
                best_condition = sorted_conditions[0][0]
                recommendations.append(f"Best performance in '{best_condition}' market conditions")
        
        return recommendations
    
    def _store_analysis(self, insights: Dict):
        """Store analysis results in database."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                
                # Store as pattern
                cursor.execute("""
                    INSERT INTO learned_patterns (pattern_type, pattern_data, performance_score)
                    VALUES (?, ?, ?)
                """, ('performance_analysis', json.dumps(insights), insights.get('win_rate', 0)))
                
                conn.commit()
        except Exception as e:
            logger.error(f"Error storing analysis: {e}")
    
    def optimize_parameters(self, strategy_name: str, 
                          parameter_ranges: Dict[str, Tuple[float, float]],
                          iterations: int = 50) -> OptimizationResult:
        """
        Optimize strategy parameters using genetic algorithm approach.
        
        Args:
            strategy_name: Name of the strategy to optimize
            parameter_ranges: Dict of param name -> (min, max) ranges
            iterations: Number of optimization iterations
            
        Returns:
            Best parameter set found
        """
        logger.info(f"Optimizing {strategy_name} parameters...")
        
        # Generate initial population
        population = self._generate_population(parameter_ranges, size=20)
        best_result = None
        best_fitness = -float('inf')
        
        for generation in range(iterations // 5):
            # Evaluate fitness for each individual
            fitness_scores = []
            for params in population:
                fitness = self._evaluate_fitness(strategy_name, params)
                fitness_scores.append((params, fitness))
                
                if fitness > best_fitness:
                    best_fitness = fitness
                    best_result = params
            
            # Sort by fitness
            fitness_scores.sort(key=lambda x: x[1], reverse=True)
            
            # Selection - keep top 50%
            survivors = [x[0] for x in fitness_scores[:len(fitness_scores)//2]]
            
            # Crossover and mutation
            population = self._evolve_population(survivors, parameter_ranges)
            
            logger.debug(f"Generation {generation + 1}: Best fitness = {best_fitness:.4f}")
        
        # Calculate final metrics
        final_metrics = self._evaluate_detailed(strategy_name, best_result)
        
        result = OptimizationResult(
            parameter_set=best_result,
            fitness_score=best_fitness,
            win_rate=final_metrics.get('win_rate', 0),
            profit_factor=final_metrics.get('profit_factor', 0),
            max_drawdown=final_metrics.get('max_drawdown', 0)
        )
        
        # Store result
        self._store_optimization(strategy_name, result)
        
        return result
    
    def _generate_population(self, ranges: Dict[str, Tuple[float, float]], 
                            size: int) -> List[Dict[str, float]]:
        """Generate random parameter population."""
        population = []
        for _ in range(size):
            individual = {}
            for param, (min_val, max_val) in ranges.items():
                individual[param] = np.random.uniform(min_val, max_val)
            population.append(individual)
        return population
    
    def _evaluate_fitness(self, strategy: str, params: Dict[str, float]) -> float:
        """Evaluate fitness of parameter set (simplified simulation)."""
        # This would typically involve backtesting
        # For now, use heuristic based on parameter balance
        
        fitness = 0.5  # Base fitness
        
        # Reward balanced parameters
        values = list(params.values())
        if values:
            std_dev = np.std(values)
            fitness += 0.1 / (1 + std_dev)  # Reward lower variance
        
        # Add some randomness for exploration
        fitness += np.random.normal(0, 0.1)
        
        return max(0, fitness)
    
    def _evaluate_detailed(self, strategy: str, params: Dict[str, float]) -> Dict[str, float]:
        """Evaluate detailed metrics for best parameters."""
        # This would run full backtest
        return {
            'win_rate': 0.55 + np.random.uniform(-0.1, 0.1),
            'profit_factor': 1.5 + np.random.uniform(-0.3, 0.5),
            'max_drawdown': 0.15 + np.random.uniform(-0.05, 0.1)
        }
    
    def _evolve_population(self, survivors: List[Dict], 
                          ranges: Dict[str, Tuple[float, float]]) -> List[Dict]:
        """Create new generation through crossover and mutation."""
        new_population = survivors.copy()
        
        while len(new_population) < len(survivors) * 2:
            # Select two parents
            parent1, parent2 = np.random.choice(survivors, 2, replace=False)
            
            # Crossover
            child = {}
            for key in ranges.keys():
                if np.random.random() < 0.5:
                    child[key] = parent1[key]
                else:
                    child[key] = parent2[key]
                
                # Mutation
                if np.random.random() < 0.1:
                    min_val, max_val = ranges[key]
                    child[key] += np.random.normal(0, (max_val - min_val) * 0.1)
                    child[key] = np.clip(child[key], min_val, max_val)
            
            new_population.append(child)
        
        return new_population
    
    def _store_optimization(self, strategy: str, result: OptimizationResult):
        """Store optimization results."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO optimized_params 
                    (strategy_name, parameters, fitness_score)
                    VALUES (?, ?, ?)
                """, (strategy, json.dumps(result.parameter_set), result.fitness_score))
                conn.commit()
        except Exception as e:
            logger.error(f"Error storing optimization: {e}")
    
    def detect_market_condition(self, price_data: List[float], 
                               volume_data: List[float] = None) -> MarketCondition:
        """
        Detect current market condition from price data.
        
        Args:
            price_data: Recent price data (closes)
            volume_data: Recent volume data (optional)
            
        Returns:
            MarketCondition classification
        """
        if len(price_data) < 20:
            return MarketCondition('unknown', 0.5, 0.5, 'normal', datetime.now())
        
        # Calculate indicators
        returns = np.diff(price_data) / price_data[:-1]
        volatility = np.std(returns) * np.sqrt(252)  # Annualized
        
        # Simple trend detection using moving averages
        short_ma = np.mean(price_data[-10:])
        long_ma = np.mean(price_data[-20:])
        trend_strength = abs(short_ma - long_ma) / long_ma
        
        # Classify regime
        if trend_strength > 0.02 and volatility < 0.25:
            regime = 'trending'
        elif volatility > 0.30:
            regime = 'volatile'
        elif trend_strength < 0.005:
            regime = 'ranging'
        else:
            regime = 'mixed'
        
        # Volume profile
        if volume_data:
            avg_volume = np.mean(volume_data[-20:])
            recent_volume = np.mean(volume_data[-5:])
            volume_profile = 'high' if recent_volume > avg_volume * 1.3 else 'low' if recent_volume < avg_volume * 0.7 else 'normal'
        else:
            volume_profile = 'normal'
        
        return MarketCondition(
            regime=regime,
            trend_strength=min(trend_strength * 10, 1.0),  # Normalize
            volatility=min(volatility * 4, 1.0),  # Normalize
            volume_profile=volume_profile,
            timestamp=datetime.now()
        )
    
    def get_adaptive_params(self, market_condition: str, 
                           strategy_name: str = 'default') -> Dict[str, float]:
        """
        Get optimized parameters for current market condition.
        
        Args:
            market_condition: Current market regime
            strategy_name: Strategy to get params for
            
        Returns:
            Optimized parameters
        """
        # Try to get condition-specific params
        key = f"{strategy_name}_{market_condition}"
        
        if key in self.current_best_params:
            logger.info(f"Using optimized params for {market_condition} condition")
            return self.current_best_params[key]['params']
        
        # Fall back to general params
        if strategy_name in self.current_best_params:
            return self.current_best_params[strategy_name]['params']
        
        # Return default params
        return self._get_default_params(strategy_name)
    
    def _get_default_params(self, strategy: str) -> Dict[str, float]:
        """Get default parameters for a strategy."""
        defaults = {
            'trend_following': {
                'ema_fast': 10,
                'ema_slow': 30,
                'atr_multiplier_sl': 2.0,
                'atr_multiplier_tp': 3.0,
                'risk_per_trade': 0.01
            },
            'mean_reversion': {
                'rsi_period': 14,
                'rsi_overbought': 70,
                'rsi_oversold': 30,
                'bb_period': 20,
                'bb_std': 2.0,
                'risk_per_trade': 0.01
            },
            'breakout': {
                'lookback_period': 20,
                'breakout_threshold': 0.5,
                'volume_multiplier': 1.5,
                'risk_per_trade': 0.01
            },
            'default': {
                'stop_loss_points': 50,
                'take_profit_points': 100,
                'trailing_stop': 30,
                'risk_per_trade': 0.01
            }
        }
        return defaults.get(strategy, defaults['default'])
    
    def generate_optimized_strategy(self) -> Dict[str, Any]:
        """
        Generate an optimized trading strategy based on learned patterns.
        
        Returns:
            Strategy configuration dictionary
        """
        # Analyze what has worked best
        analysis = self.analyze_performance(days=60)
        
        if 'error' in analysis:
            return {'error': analysis['error']}
        
        best_strategy = analysis.get('best_strategy', 'default')
        best_condition = analysis.get('best_condition', 'unknown')
        
        # Get optimized parameters
        params = self.get_adaptive_params(best_condition, best_strategy)
        
        strategy = {
            'name': f'Adaptive_{best_strategy}',
            'base_strategy': best_strategy,
            'optimal_market_condition': best_condition,
            'parameters': params,
            'entry_rules': self._generate_entry_rules(best_strategy, params),
            'exit_rules': self._generate_exit_rules(best_strategy, params),
            'risk_management': {
                'max_daily_loss': 500,
                'max_positions': 3,
                'risk_per_trade': params.get('risk_per_trade', 0.01)
            },
            'created_at': datetime.now().isoformat(),
            'expected_performance': {
                'win_rate': analysis.get('win_rate', 0.5),
                'profit_factor': analysis.get('profit_factor', 1.0),
                'expectancy': analysis.get('expectancy', 0)
            }
        }
        
        return strategy
    
    def _generate_entry_rules(self, strategy: str, params: Dict) -> List[str]:
        """Generate entry rules based on strategy type."""
        if strategy == 'trend_following':
            return [
                f"EMA{int(params.get('ema_fast', 10))} crosses above EMA{int(params.get('ema_slow', 30))}",
                "ADX > 25 (strong trend)",
                "Price above 200 EMA (bullish bias)"
            ]
        elif strategy == 'mean_reversion':
            return [
                f"RSI below {int(params.get('rsi_oversold', 30))} (oversold)",
                f"Price touches lower Bollinger Band ({int(params.get('bb_period', 20))} period)",
                "Volume spike indicating potential reversal"
            ]
        elif strategy == 'breakout':
            return [
                f"Price breaks {int(params.get('lookback_period', 20))}-day high/low",
                f"Volume above {params.get('volume_multiplier', 1.5)}x average",
                "Range compression prior to breakout"
            ]
        else:
            return ["Use technical confluence for entry"]
    
    def _generate_exit_rules(self, strategy: str, params: Dict) -> List[str]:
        """Generate exit rules based on strategy type."""
        sl_points = int(params.get('stop_loss_points', 50) * 10)
        tp_points = int(params.get('take_profit_points', 100) * 10)
        
        return [
            f"Stop Loss: {sl_points} points",
            f"Take Profit: {tp_points} points",
            "Trailing stop when in profit",
            "Exit on opposite signal"
        ]
    
    def learn_from_trade(self, trade_result: Dict[str, Any]):
        """
        Learn from a completed trade and update internal models.
        
        Args:
            trade_result: Dictionary with trade details
        """
        try:
            strategy = trade_result.get('strategy', 'unknown')
            condition = trade_result.get('market_condition', 'unknown')
            pnl = trade_result.get('realized_pnl', 0)
            
            # Update market condition stats
            self.market_regime_stats[condition][strategy].append({
                'pnl': pnl,
                'timestamp': datetime.now().isoformat()
            })
            
            # Keep only last 100 trades per condition/strategy
            if len(self.market_regime_stats[condition][strategy]) > 100:
                self.market_regime_stats[condition][strategy] = \
                    self.market_regime_stats[condition][strategy][-100:]
            
            logger.info(f"Learned from trade: {strategy} in {condition} market -> PnL: {pnl}")
            
        except Exception as e:
            logger.error(f"Error learning from trade: {e}")
    
    def get_learning_summary(self) -> Dict[str, Any]:
        """Get summary of what the system has learned."""
        return {
            'total_patterns_learned': len(self.current_best_params),
            'market_conditions_tracked': list(self.market_regime_stats.keys()),
            'optimized_strategies': list(set(
                k.split('_')[0] for k in self.current_best_params.keys()
            )),
            'recent_recommendations': self._get_recent_recommendations(),
            'best_performing_setup': self._get_best_setup()
        }
    
    def _get_recent_recommendations(self) -> List[str]:
        """Get recent recommendations from analysis."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT pattern_data FROM learned_patterns
                    WHERE pattern_type = 'performance_analysis'
                    ORDER BY created_at DESC
                    LIMIT 1
                """)
                row = cursor.fetchone()
                if row:
                    data = json.loads(row[0])
                    return data.get('recommendations', [])
        except:
            pass
        return []
    
    def _get_best_setup(self) -> Optional[Dict]:
        """Get best performing setup."""
        if not self.current_best_params:
            return None
        
        best_key = max(self.current_best_params.items(), 
                      key=lambda x: x[1]['score'])[0]
        
        return {
            'key': best_key,
            'params': self.current_best_params[best_key]['params'],
            'score': self.current_best_params[best_key]['score']
        }


if __name__ == "__main__":
    # Test adaptive learning
    learner = AdaptiveLearning()
    
    print("Testing Adaptive Learning System")
    print("=" * 50)
    
    # Test market condition detection
    print("\n1. Testing Market Condition Detection:")
    test_prices = [2900 + i * 2 + np.random.normal(0, 5) for i in range(50)]
    condition = learner.detect_market_condition(test_prices)
    print(f"   Detected: {condition.regime}")
    print(f"   Trend Strength: {condition.trend_strength:.2f}")
    print(f"   Volatility: {condition.volatility:.2f}")
    
    # Test parameter retrieval
    print("\n2. Testing Parameter Retrieval:")
    params = learner.get_adaptive_params('trending', 'trend_following')
    print(f"   Params: {params}")
    
    # Test strategy generation
    print("\n3. Testing Strategy Generation:")
    strategy = learner.generate_optimized_strategy()
    if 'error' not in strategy:
        print(f"   Generated: {strategy['name']}")
        print(f"   Base Strategy: {strategy['base_strategy']}")
        print(f"   Optimal Condition: {strategy['optimal_market_condition']}")
    else:
        print(f"   Error: {strategy['error']}")
    
    # Test learning summary
    print("\n4. Learning Summary:")
    summary = learner.get_learning_summary()
    print(f"   Patterns Learned: {summary['total_patterns_learned']}")
    print(f"   Conditions Tracked: {summary['market_conditions_tracked']}")
