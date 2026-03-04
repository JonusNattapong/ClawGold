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
    
    symbol = config['trading']['symbol']
    positions = mt5.positions_get(symbol=symbol)
    if positions is None:
        positions = []
    
    if positions:
        print(f"Open positions for {symbol}:")
        for pos in positions:
            type_str = "BUY" if pos.type == mt5.POSITION_TYPE_BUY else "SELL"
            ounces = pos.volume * 100  # Assuming 1 lot = 100 oz
            print(f"  {type_str} {ounces:.0f} oz at {pos.price_open:.2f} USD, P/L: {pos.profit:.2f} USD")
    else:
        print(f"No open positions for {symbol}.")
    
    mt5.shutdown()
else:
    print("Real trading mode not enabled in config.yaml.")
