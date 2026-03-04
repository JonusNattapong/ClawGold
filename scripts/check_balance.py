import MetaTrader5 as mt5
import sys
import os
try:
    from .config_loader import load_config, DEFAULT_MT5_TERMINAL_PATH
except ImportError:
    from config_loader import load_config, DEFAULT_MT5_TERMINAL_PATH

# Load config
CONFIG_FILE = os.path.join(os.path.dirname(__file__), '..', 'config.yaml')
config = load_config(CONFIG_FILE)

if config['trading']['mode'] == 'real':
    path = config.get('mt5', {}).get('terminal_path', DEFAULT_MT5_TERMINAL_PATH)
    login = config['mt5']['login']
    password = config['mt5']['password']
    server = config['mt5']['server']
    if not mt5.initialize(path, login=login, server=server, password=password):
        print("MT5 initialize failed.")
        sys.exit(1)
    
    account = mt5.account_info()
    if account:
        print(f"Account Balance: {account.balance:.2f} USD")
        print(f"Account Equity: {account.equity:.2f} USD")
        print(f"Used Margin: {account.margin:.2f} USD")
        print(f"Free Margin: {account.margin_free:.2f} USD")
        print(f"Profit/Loss: {account.profit:.2f} USD")
    else:
        print("Failed to retrieve account information.")
    
    mt5.shutdown()
else:
    print("Real trading mode not enabled in config.yaml.")
