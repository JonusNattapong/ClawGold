"""
OmegaConf Configuration Management
==================================
Type-safe configuration with schema validation using OmegaConf and Pydantic.

Provides:
- YAML configuration with strong typing
- Environment variable interpolation
- Schema validation with Pydantic
- Defaults with overrides
- Config hot-reload support

Usage:
    from omegaconf_config import get_config, ConfigModel
    
    config = get_config()
    
    # Access with type safety
    print(config.trading.symbol)      # XAUUSD
    print(config.agent.max_retries)   # 3
    
    # Environment override
    # export AGENT_MAX_RETRIES=5
    # config will have max_retries=5
"""

import os
import yaml
from typing import Optional, Dict, Any, Type
from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum

try:
    from omegaconf import OmegaConf, DictConfig, MISSING
    from pydantic import BaseModel, Field, validator
    OMEGACONF_AVAILABLE = True
except ImportError:
    OMEGACONF_AVAILABLE = False

from logger import get_logger

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────
# Configuration Models (Pydantic)
# ─────────────────────────────────────────────────────

class TradingConfig(BaseModel):
    """Trading strategy configuration."""
    symbol: str = Field(default="XAUUSD", description="Trading symbol")
    timeframes: list = Field(default_factory=lambda: ["M15", "H1", "H4", "D1"])
    max_positions: int = Field(default=5, ge=1, le=10)
    position_size: float = Field(default=0.1, gt=0, le=1.0)
    use_leverage: bool = Field(default=False)
    
    class Config:
        extra = 'allow'


class RiskConfig(BaseModel):
    """Risk management configuration."""
    daily_loss_limit: float = Field(default=500.0, gt=0)
    max_loss_percent: float = Field(default=2.0, gt=0, le=10.0)
    use_stop_loss: bool = Field(default=True)
    use_take_profit: bool = Field(default=True)
    default_sl_pips: int = Field(default=50, ge=10, le=500)
    default_tp_pips: int = Field(default=100, ge=20, le=1000)
    
    class Config:
        extra = 'allow'


class AgentConfig(BaseModel):
    """AI agent configuration."""
    enabled: bool = Field(default=True)
    max_retries: int = Field(default=3, ge=1, le=10)
    retry_delay_seconds: int = Field(default=2, ge=1)
    timeout_seconds: int = Field(default=30, ge=5, le=300)
    preferred_tools: list = Field(
        default_factory=lambda: ["opencode", "gemini"]
    )
    cache_ttl_hours: int = Field(default=24, ge=1, le=168)
    
    class Config:
        extra = 'allow'


class ScheduleConfig(BaseModel):
    """Background scheduler configuration."""
    enabled: bool = Field(default=True)
    daily_analysis_time: str = Field(default="09:00")  # HH:MM format
    check_interval_minutes: int = Field(default=15, ge=5, le=60)
    max_concurrent_tasks: int = Field(default=4, ge=1, le=16)
    
    class Config:
        extra = 'allow'


class ObservabilityConfig(BaseModel):
    """Observability and monitoring configuration."""
    langfuse_enabled: bool = Field(default=False)
    langfuse_public_key: str = Field(default="")
    langfuse_secret_key: str = Field(default="")
    log_level: str = Field(default="INFO")
    log_file: str = Field(default="logs/clawgold.log")
    
    class Config:
        extra = 'allow'


class DatabaseConfig(BaseModel):
    """Database configuration."""
    db_path: str = Field(default="data/clawgold.db")
    cache_dir: str = Field(default="data/.cache")
    backup_enabled: bool = Field(default=True)
    backup_interval_days: int = Field(default=7, ge=1)
    
    class Config:
        extra = 'allow'


class ConfigModel(BaseModel):
    """Root configuration model."""
    trading: TradingConfig = Field(default_factory=TradingConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    schedule: ScheduleConfig = Field(default_factory=ScheduleConfig)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    
    class Config:
        extra = 'allow'


# ─────────────────────────────────────────────────────
# OmegaConf Configuration Manager
# ─────────────────────────────────────────────────────

class ConfigManager:
    """
    Configuration management with OmegaConf and Pydantic validation.
    
    Features:
    - YAML file loading with schema validation
    - Environment variable interpolation
    - Type-safe config access
    - Defaults + overrides
    - Hot-reload support
    """
    
    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = config_path
        self.config: Optional[DictConfig] = None
        self.validated_model: Optional[ConfigModel] = None
        self.enabled = OMEGACONF_AVAILABLE
        
        self._initialize()
    
    def _initialize(self):
        """Initialize configuration."""
        if not OMEGACONF_AVAILABLE:
            logger.warning("[OmegaConf] Package not installed (pip install omegaconf pydantic)")
            self.enabled = False
            return
        
        try:
            self._load_config()
            logger.info(f"[OmegaConf] Config loaded: {self.config_path}")
        except Exception as e:
            logger.error(f"[OmegaConf] Failed to load config: {e}")
            self.enabled = False
    
    def _load_config(self):
        """Load and validate configuration from YAML."""
        # Load defaults
        defaults = OmegaConf.structured(ConfigModel)
        
        # Load from file if exists
        if Path(self.config_path).exists():
            with open(self.config_path, 'r') as f:
                file_config = OmegaConf.create(yaml.safe_load(f))
            self.config = OmegaConf.merge(defaults, file_config)
        else:
            self.config = defaults
        
        # Apply environment overrides
        self._apply_env_overrides()
        
        # Validate with Pydantic
        config_dict = OmegaConf.to_container(self.config, resolve=True)
        self.validated_model = ConfigModel(**config_dict)
    
    def _apply_env_overrides(self):
        """Apply environment variable overrides."""
        env_mapping = {
            'TRADING_SYMBOL': 'trading.symbol',
            'TRADING_MAX_POSITIONS': 'trading.max_positions',
            'RISK_DAILY_LOSS_LIMIT': 'risk.daily_loss_limit',
            'AGENT_MAX_RETRIES': 'agent.max_retries',
            'AGENT_TIMEOUT_SECONDS': 'agent.timeout_seconds',
            'SCHEDULE_CHECK_INTERVAL': 'schedule.check_interval_minutes',
            'LANGFUSE_ENABLED': 'observability.langfuse_enabled',
            'LANGFUSE_PUBLIC_KEY': 'observability.langfuse_public_key',
            'LANGFUSE_SECRET_KEY': 'observability.langfuse_secret_key',
            'LOG_LEVEL': 'observability.log_level',
        }
        
        for env_var, config_path in env_mapping.items():
            value = os.getenv(env_var)
            if value is not None:
                # Type conversion based on existing value
                try:
                    existing = OmegaConf.select(self.config, config_path)
                    if isinstance(existing, bool):
                        value = value.lower() in ('true', '1', 'yes')
                    elif isinstance(existing, int):
                        value = int(value)
                    elif isinstance(existing, float):
                        value = float(value)
                    
                    OmegaConf.update(self.config, config_path, value)
                    logger.debug(f"Env override: {env_var} → {config_path}")
                except Exception as e:
                    logger.warning(f"Failed to apply {env_var}: {e}")
    
    # ─────────────────────────────────────────────────
    # Config Access Methods
    # ─────────────────────────────────────────────────
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value by dotted key.
        
        Args:
            key: Dotted key (e.g., 'trading.symbol')
            default: Default value if key not found
        
        Returns:
            Configuration value
        """
        if not self.enabled or not self.config:
            return default
        
        try:
            value = OmegaConf.select(self.config, key)
            return value if value is not None else default
        except Exception as e:
            logger.warning(f"Config get failed for {key}: {e}")
            return default
    
    def set(self, key: str, value: Any) -> bool:
        """Set configuration value (in memory)."""
        if not self.enabled or not self.config:
            return False
        
        try:
            OmegaConf.update(self.config, key, value)
            logger.debug(f"Config set: {key} = {value}")
            return True
        except Exception as e:
            logger.warning(f"Config set failed: {e}")
            return False
    
    def save(self, path: Optional[str] = None) -> bool:
        """Save configuration to YAML file."""
        if not self.enabled or not self.config:
            return False
        
        try:
            target_path = path or self.config_path
            with open(target_path, 'w') as f:
                yaml.dump(OmegaConf.to_container(self.config), f)
            logger.info(f"[OmegaConf] Config saved to {target_path}")
            return True
        except Exception as e:
            logger.error(f"Config save failed: {e}")
            return False
    
    def reload(self) -> bool:
        """Reload configuration from disk."""
        try:
            self._load_config()
            logger.info("[OmegaConf] Config reloaded")
            return True
        except Exception as e:
            logger.error(f"Config reload failed: {e}")
            return False
    
    # ─────────────────────────────────────────────────
    # Direct Access to Sections
    # ─────────────────────────────────────────────────
    
    @property
    def trading(self) -> TradingConfig:
        """Get trading config."""
        return self.validated_model.trading if self.validated_model else TradingConfig()
    
    @property
    def risk(self) -> RiskConfig:
        """Get risk config."""
        return self.validated_model.risk if self.validated_model else RiskConfig()
    
    @property
    def agent(self) -> AgentConfig:
        """Get agent config."""
        return self.validated_model.agent if self.validated_model else AgentConfig()
    
    @property
    def schedule(self) -> ScheduleConfig:
        """Get schedule config."""
        return self.validated_model.schedule if self.validated_model else ScheduleConfig()
    
    @property
    def observability(self) -> ObservabilityConfig:
        """Get observability config."""
        return self.validated_model.observability if self.validated_model else ObservabilityConfig()
    
    @property
    def database(self) -> DatabaseConfig:
        """Get database config."""
        return self.validated_model.database if self.validated_model else DatabaseConfig()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dict."""
        if self.config:
            return OmegaConf.to_container(self.config)
        return {}
    
    def validate(self) -> bool:
        """Validate current configuration against schema."""
        try:
            if self.config:
                config_dict = OmegaConf.to_container(self.config, resolve=True)
                ConfigModel(**config_dict)
                logger.info("[OmegaConf] Config validation passed ✓")
                return True
        except Exception as e:
            logger.error(f"[OmegaConf] Config validation failed: {e}")
            return False
        return False


# ─────────────────────────────────────────────────────
# Singleton Factory
# ─────────────────────────────────────────────────────

_config_instance: Optional[ConfigManager] = None


def get_config(config_path: str = "config.yaml") -> ConfigManager:
    """
    Get or create singleton ConfigManager instance.
    
    Args:
        config_path: Path to config.yaml file
    
    Returns:
        ConfigManager singleton
    """
    global _config_instance
    if _config_instance is None:
        _config_instance = ConfigManager(config_path)
    return _config_instance
