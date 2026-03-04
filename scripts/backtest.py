import backtrader as bt
import yfinance as yf
import pandas as pd
import json
from typing import Dict, Any, Optional

try:
    from agent_executor import AgentExecutor
    from config_loader import load_config
    AGENT_AVAILABLE = True
except ImportError:
    AGENT_AVAILABLE = False

class MAStrategy(bt.Strategy):
    params = (
        ('short_period', 10),
        ('long_period', 20),
    )

    def __init__(self):
        # Add indicators
        self.short_ma = bt.indicators.SimpleMovingAverage(
            self.data.close, period=self.params.short_period)
        self.long_ma = bt.indicators.SimpleMovingAverage(
            self.data.close, period=self.params.long_period)

    def next(self):
        # Check for crossover
        if self.short_ma > self.long_ma and self.position.size == 0:
            # Buy signal
            self.buy()
        elif self.short_ma < self.long_ma and self.position.size > 0:
            # Sell signal
            self.sell()

def run_backtest():
    # Download historical data for XAUUSD (GC=F)
    print("Downloading historical data for XAUUSD...")
    data = yf.download('GC=F', start='2020-01-01', end='2024-01-01', interval='1d')
    if data.empty:
        print("Failed to download data.")
        return

    # Fix MultiIndex columns from yfinance
    data.columns = data.columns.droplevel(1)  # Drop the ticker level
    # Ensure correct order for backtrader: Open, High, Low, Close, Volume
    data = data[['Open', 'High', 'Low', 'Close', 'Volume']]

    # Convert to Backtrader format
    data_feed = bt.feeds.PandasData(dataname=data)

    # Create Cerebro engine
    cerebro = bt.Cerebro()

    # Add strategy
    cerebro.addstrategy(MAStrategy, short_period=10, long_period=20)

    # Add data
    cerebro.adddata(data_feed)

    # Set initial cash
    cerebro.broker.setcash(10000.0)

    # Set commission (0.1% per trade)
    cerebro.broker.setcommission(commission=0.001)

    # Print starting portfolio value
    print(f'Starting Portfolio Value: {cerebro.broker.getvalue():.2f}')

    # Run backtest
    print("Running backtest...")
    cerebro.run()

    # Print final portfolio value
    print(f'Final Portfolio Value: {cerebro.broker.getvalue():.2f}')

def describe_results_with_ai(results: Dict[str, Any]) -> str:
    """Uses AI to explain backtest results and suggest improvements."""
    if not AGENT_AVAILABLE:
        return "AI not available for results interpretation."
        
    try:
        config = load_config()
        executor = AgentExecutor(config)
        
        prompt = f"""
        Analyze these backtest results for an XAUUSD (Gold) trading strategy:
        {json.dumps(results)}
        
        Please provide:
        1. Performance summary (Win rate, Profit Factor, Sharpe Ratio)
        2. Strengths and weaknesses observed
        3. Potential optimizations for the strategy parameters
        4. Market conditions where this strategy would perform best/worst
        
        Respond clearly as a quantitative analyst.
        """
        
        response = executor.run_best(prompt, task_name="backtest_analysis")
        return response.get('output', "AI failed to interpret results.")
    except Exception as e:
        return f"AI analysis error: {str(e)}"

def run_backtest():
    # ... (rest of code)
    print(f'Total Return: {total_return:.2f}%')
    
    # Calculate more metrics for the AI to analyze
    metrics = {
        'starting_portfolio': 10000.0,
        'final_portfolio': final_value,
        'total_return_pct': float(total_return),
        'strategy': 'MAStrategy',
        'params': {'short_period': 10, 'long_period': 20}
    }
    
    print("\n" + "="*50)
    print("AI ANALYSIS OF RESULTS")
    print("="*50)
    print(describe_results_with_ai(metrics))

if __name__ == "__main__":
    run_backtest()
