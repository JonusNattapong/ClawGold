import pandas as pd
import MetaTrader5 as mt5
import pandas_ta as ta
from pathlib import Path
try:
    from .config_loader import load_config, DEFAULT_MT5_TERMINAL_PATH
except ImportError:
    from config_loader import load_config, DEFAULT_MT5_TERMINAL_PATH

CONFIG_FILE = 'config.yaml'
ROOT_DIR = Path(__file__).resolve().parent.parent

config = None

def initialize_plugin():
    """Initialize the plugin."""
    global config
    if config is None:
        try:
            config = load_config(str(ROOT_DIR / CONFIG_FILE))
        except Exception as e:
            return f"Error loading config: {str(e)}"
    
    mode = config['trading']['mode']
    if mode != 'real':
        return "Only real mode is supported. Set TRADING_MODE=real in .env"

    path = config.get('mt5', {}).get('terminal_path', DEFAULT_MT5_TERMINAL_PATH)
    login = config['mt5']['login']
    password = config['mt5']['password']
    server = config['mt5']['server']
    if not mt5.initialize(path, login=login, server=server, password=password):
        return "MT5 initialize failed. Check credentials and MT5 setup."
    return "ClawGold initialized for real trading with MT5."

def get_xauusd_price():
    """Fetch current XAUUSD price."""
    if config['trading']['mode'] != 'real':
        return "Error: Only real mode is supported."

    symbol = config['trading']['symbol']
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return "Error: Unable to fetch price from MT5."
    return f"Current {symbol} price: {tick.bid:.2f} USD (bid), {tick.ask:.2f} USD (ask)"

def calculate_moving_average(period=20):
    """Calculate simple moving average for the last period days."""
    if config['trading']['mode'] != 'real':
        return "Error: Only real mode is supported."

    symbol = config['trading']['symbol']
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_D1, 0, period + 10)
    if rates is None or len(rates) < period:
        return f"Not enough data for MA({period})."
    closes = [rate.close for rate in rates[-period:]]
    sma = sum(closes) / len(closes)
    return f"SMA({period}): {sma:.2f}"

def generate_trading_signal(short_period=10, long_period=20):
    """Generate trading signal based on MACD."""
    if config['trading']['mode'] != 'real':
        return "Error: Only real mode is supported."

    symbol = config['trading']['symbol']
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_D1, 0, 100)  # Get enough data
    if rates is None or len(rates) < 26:  # MACD needs at least 26 periods
        return "Not enough data for signal."
    df = pd.DataFrame(rates)
    macd = ta.macd(df['close'])
    if macd is None or macd.empty:
        return "MACD calculation failed."
    macd_line = macd['MACD']
    signal_line = macd['MACDs']
    if len(macd_line) < 2 or len(signal_line) < 2:
        return "Insufficient data for signal."
    if macd_line.iloc[-1] > signal_line.iloc[-1] and macd_line.iloc[-2] <= signal_line.iloc[-2]:
        return "BUY signal"
    if macd_line.iloc[-1] < signal_line.iloc[-1] and macd_line.iloc[-2] >= signal_line.iloc[-2]:
        return "SELL signal"
    return "HOLD"

def execute_trade(action, amount):
    """Execute buying or selling XAUUSD in real mode."""
    if config['trading']['mode'] != 'real':
        return "Error: Only real mode is supported."

    symbol = config['trading']['symbol']
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return "Error: Unable to fetch tick."

    # Convert amount (ounces) to volume (lots), assuming 1 lot = 100 ounces
    volume = amount / 100.0

    if action.upper() == 'BUY':
        price = tick.ask
        order_type = mt5.ORDER_TYPE_BUY
    elif action.upper() == 'SELL':
        price = tick.bid
        order_type = mt5.ORDER_TYPE_SELL
    else:
        return "Invalid action. Use BUY or SELL."

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": volume,
        "type": order_type,
        "price": price,
        "deviation": 10,
        "magic": 123456,
        "comment": "ClawGold",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        return f"Order failed: {result.retcode}"
    return f"Real {action.upper()}: {amount} ounces at {price:.2f} USD"


def get_portfolio_status():
    """Get current real portfolio/account status."""
    if config['trading']['mode'] != 'real':
        return "Error: Only real mode is supported."

    account = mt5.account_info()
    if account is None:
        return "Error: Unable to get account info."
    balance = account.balance
    symbol = config['trading']['symbol']
    positions = mt5.positions_get(symbol=symbol)
    if positions is None:
        positions = []
    status = f"Balance: {balance:.2f} USD\n"
    if positions:
        status += "Positions:\n"
        for pos in positions:
            type_str = "BUY" if pos.type == mt5.POSITION_TYPE_BUY else "SELL"
            # Volume in lots, convert to ounces (1 lot = 100 oz)
            ounces = pos.volume * 100
            status += f"  {type_str} {ounces:.0f} ounces at {pos.price_open:.2f} USD\n"
    else:
        status += "No open positions.\n"
    return status

def interactive():
    """Interactive mode for standalone use."""
    print("Welcome to ClawGold - XAUUSD Real Trading")
    print("Initializing...")
    print(initialize_plugin())
    print()

    while True:
        print("\nMenu:")
        print("1. Get current XAUUSD price")
        print("2. Calculate moving average")
        print("3. Generate trading signal")
        print("4. Execute trade")
        print("5. Get portfolio status")
        print("6. Exit")
        choice = input("Choose an option (1-6): ").strip()

        if choice == '1':
            print("Fetching price...")
            print(get_xauusd_price())
        elif choice == '2':
            period = input("Enter period (default 20): ").strip()
            period = int(period) if period else 20
            print(f"Calculating MA({period})...")
            print(calculate_moving_average(period))
        elif choice == '3':
            short = input("Enter short period (default 10): ").strip()
            short = int(short) if short else 10
            long_p = input("Enter long period (default 20): ").strip()
            long_p = int(long_p) if long_p else 20
            print("Generating signal...")
            print(generate_trading_signal(short, long_p))
        elif choice == '4':
            action = input("Enter action (BUY/SELL): ").strip().upper()
            if action not in ['BUY', 'SELL']:
                print("Invalid action.")
                continue
            amount = input("Enter amount in ounces: ").strip()
            try:
                amount = float(amount)
                print("Executing trade...")
                print(execute_trade(action, amount))
            except ValueError:
                print("Invalid amount.")
        elif choice == '5':
            print("Portfolio status:")
            print(get_portfolio_status())
        elif choice == '6':
            print("Exiting ClawGold. Goodbye!")
            break
        else:
            print("Invalid choice. Please select 1-6.")

        input("\nPress Enter to continue...")

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        # Interactive mode
        interactive()
    else:
        # CLI mode for OpenClaw
        func = sys.argv[1]
        if func == 'initialize_plugin':
            print(initialize_plugin())
        elif func == 'get_xauusd_price':
            print(get_xauusd_price())
        elif func == 'calculate_moving_average':
            period = int(sys.argv[2]) if len(sys.argv) > 2 else 20
            print(calculate_moving_average(period))
        elif func == 'generate_trading_signal':
            short = int(sys.argv[2]) if len(sys.argv) > 2 else 10
            long_p = int(sys.argv[3]) if len(sys.argv) > 3 else 20
            print(generate_trading_signal(short, long_p))
        elif func == 'execute_trade':
            if len(sys.argv) < 4:
                print("Usage: execute_trade <action> <amount>")
                sys.exit(1)
            action = sys.argv[2]
            amount = float(sys.argv[3])
            print(execute_trade(action, amount))
        elif func == 'get_portfolio_status':
            print(get_portfolio_status())
        else:
            print(f"Unknown function: {func}")
