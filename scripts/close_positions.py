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
    
    if not positions:
        print(f"No open positions for {symbol} to close.")
    else:
        print(f"Closing {len(positions)} position(s) for {symbol}...")
        for pos in positions:
            request = {
                "action": mt5.TRADE_ACTION_CLOSE_POSITION,
                "position": pos.ticket,
            }
            result = mt5.order_send(request)
            if result.retcode == mt5.TRADE_RETCODE_DONE:
                print(f"Closed position {pos.ticket}")
            else:
                print(f"Failed to close position {pos.ticket}: {result.retcode}")
    
    mt5.shutdown()
else:
    print("Real trading mode not enabled in config.yaml.")
