"""
Centralized config loader with .env support.
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

DEFAULT_MT5_TERMINAL_PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"


def _parse_value(raw: str) -> Any:
    lowered = raw.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    try:
        if "." in raw:
            return float(raw)
        return int(raw)
    except ValueError:
        return raw


def load_dotenv(dotenv_path: Path) -> None:
    """Load .env key-values into process env if not already set."""
    if not dotenv_path.exists():
        return

    for line in dotenv_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _apply_env_overrides(config: Dict[str, Any]) -> Dict[str, Any]:
    trading = config.setdefault("trading", {})
    mt5 = config.setdefault("mt5", {})

    if "TRADING_MODE" in os.environ:
        trading["mode"] = os.environ["TRADING_MODE"].strip()

    if "RISK_PER_TRADE" in os.environ:
        trading["risk_per_trade"] = _parse_value(os.environ["RISK_PER_TRADE"].strip())

    if "MT5_LOGIN" in os.environ:
        mt5["login"] = int(os.environ["MT5_LOGIN"].strip())
    if "MT5_PASSWORD" in os.environ:
        mt5["password"] = os.environ["MT5_PASSWORD"]
    if "MT5_SERVER" in os.environ:
        mt5["server"] = os.environ["MT5_SERVER"]

    mt5["terminal_path"] = os.environ.get(
        "MT5_TERMINAL_PATH",
        mt5.get("terminal_path", DEFAULT_MT5_TERMINAL_PATH),
    )

    # Telegram
    tg = config.setdefault("telegram", {})
    if "TELEGRAM_BOT_TOKEN" in os.environ:
        tg["bot_token"] = os.environ["TELEGRAM_BOT_TOKEN"]
    if "TELEGRAM_CHAT_ID" in os.environ:
        tg["chat_id"] = os.environ["TELEGRAM_CHAT_ID"]

    # Signal Service — tier channel IDs
    ss = config.setdefault("signal_service", {}).setdefault("channels", {})
    for tier, env_key in {
        "free":  "SIGNAL_CH_FREE",
        "basic": "SIGNAL_CH_BASIC",
        "pro":   "SIGNAL_CH_PRO",
        "vip":   "SIGNAL_CH_VIP",
    }.items():
        if os.environ.get(env_key):
            ss[tier] = os.environ[env_key]

    return config


def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    root = Path(__file__).resolve().parent.parent
    path = Path(config_path) if config_path else (root / "config.yaml")

    load_dotenv(root / ".env")

    with open(path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    return _apply_env_overrides(config)


def get_shared_executor(config: Dict[str, Any]):
    """Singleton getter for AgentExecutor across all modules."""
    if '_shared' not in config:
        from scripts.agent_executor import AgentExecutor
        config['_shared'] = {'executor': AgentExecutor(config=config)}
    return config['_shared']['executor']
