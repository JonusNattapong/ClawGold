"""
Configuration Validator
=======================
Validates config.yaml for required fields and correct values.
"""

from pathlib import Path
from typing import List
try:
    from .config_loader import load_config
except ImportError:
    from config_loader import load_config


class ConfigValidator:
    """Validates ClawGold configuration."""
    
    REQUIRED_SECTIONS = ['trading', 'mt5', 'api', 'logging']
    TRADING_FIELDS = ['mode', 'symbol', 'risk_per_trade']
    MT5_FIELDS = ['login', 'password', 'server']
    
    VALID_MODES = ['real']
    VALID_SYMBOLS = ['XAUUSD', 'GOLD']
    
    def __init__(self, config_path: str = None):
        self.config_path = config_path or Path(__file__).parent.parent / "config.yaml"
        self.errors = []
    
    def validate(self) -> List[str]:
        """
        Validate configuration file.
        
        Returns:
            List of error messages (empty if valid)
        """
        self.errors = []
        
        # Load config
        try:
            config = load_config(str(self.config_path))
        except Exception as e:
            self.errors.append(f"Failed to load config: {e}")
            return self.errors
        
        if config is None:
            self.errors.append("Config file is empty")
            return self.errors
        
        # Check required sections
        for section in self.REQUIRED_SECTIONS:
            if section not in config:
                self.errors.append(f"Missing required section: {section}")
        
        if self.errors:
            return self.errors
        
        # Validate trading section
        self._validate_trading(config.get('trading', {}))
        
        # Validate MT5 section (only if mode is real)
        if config.get('trading', {}).get('mode') == 'real':
            self._validate_mt5(config.get('mt5', {}))
        
        # Validate API section
        self._validate_api(config.get('api', {}))
        
        # Validate logging section
        self._validate_logging(config.get('logging', {}))
        
        return self.errors
    
    def _validate_trading(self, trading: dict):
        """Validate trading configuration."""
        for field in self.TRADING_FIELDS:
            if field not in trading:
                self.errors.append(f"Missing trading.{field}")
        
        # Check mode
        mode = trading.get('mode')
        if mode and mode not in self.VALID_MODES:
            self.errors.append(f"Invalid trading.mode: {mode}. Must be one of {self.VALID_MODES}")
        
        # Check risk_per_trade
        risk = trading.get('risk_per_trade')
        if risk is not None:
            if not isinstance(risk, (int, float)):
                self.errors.append("trading.risk_per_trade must be a number")
            elif risk < 0 or risk > 1:
                self.errors.append("trading.risk_per_trade must be between 0 and 1")
        
        # Check symbol
        symbol = trading.get('symbol')
        if symbol and symbol not in self.VALID_SYMBOLS:
            self.errors.append(f"Invalid trading.symbol: {symbol}")
    
    def _validate_mt5(self, mt5: dict):
        """Validate MT5 configuration."""
        for field in self.MT5_FIELDS:
            if field not in mt5:
                self.errors.append(
                    f"Missing MT5 credential '{field}' (set in .env as MT5_{field.upper()})"
                )
        
        # Check login is number
        login = mt5.get('login')
        if login is not None and not isinstance(login, int):
            self.errors.append("mt5.login must be an integer")
    
    def _validate_api(self, api: dict):
        """Validate API configuration."""
        if 'provider' not in api:
            self.errors.append("Missing api.provider")
        
        if 'ticker' not in api:
            self.errors.append("Missing api.ticker")
    
    def _validate_logging(self, logging: dict):
        """Validate logging configuration."""
        if 'enable' not in logging:
            self.errors.append("Missing logging.enable")
        
        if 'log_file' not in logging:
            self.errors.append("Missing logging.log_file")
    
    def is_valid(self) -> bool:
        """Check if configuration is valid."""
        return len(self.validate()) == 0
