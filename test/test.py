import sys
sys.path.append('.')
import scripts.claw_gold as cg

print("Initializing ClawGold...")
print(cg.initialize_plugin())

print("\nFetching current XAUUSD price:")
print(cg.get_xauusd_price())

print("\nCalculating moving average (20 days):")
print(cg.calculate_moving_average(20))

print("\nGenerating trading signal:")
print(cg.generate_trading_signal())

print("\nCurrent portfolio status:")
print(cg.get_portfolio_status())

print("\nExecuting buy of 0.1 oz:")
print(cg.execute_trade('buy', 0.1))

print("\nPortfolio after buy:")
print(cg.get_portfolio_status())

print("\nExecuting sell of 0.05 oz:")
print(cg.execute_trade('sell', 0.05))

print("\nFinal portfolio status:")
print(cg.get_portfolio_status())
