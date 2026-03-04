"""
Background news research worker for container deployment.
"""

import os
import time
from datetime import datetime

from logger import get_logger
from news_aggregator import NewsAggregator

logger = get_logger(__name__)


def _as_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def main() -> None:
    symbol = os.getenv("RESEARCH_SYMBOL", "XAUUSD")
    query = os.getenv("RESEARCH_QUERY") or None
    interval_seconds = int(os.getenv("RESEARCH_INTERVAL_SECONDS", "1800"))
    use_ai = _as_bool(os.getenv("RESEARCH_USE_AI", "true"))

    logger.info(
        "Starting news worker | symbol=%s interval=%ss use_ai=%s",
        symbol,
        interval_seconds,
        use_ai,
    )

    aggregator = NewsAggregator()

    while True:
        started = datetime.now()
        try:
            result = aggregator.research_symbol(
                symbol=symbol,
                query=query,
                use_ai=use_ai,
            )
            signal = result.get("trading_signal", {})
            logger.info(
                "Research cycle complete | direction=%s confidence=%.2f",
                signal.get("direction", "neutral"),
                signal.get("confidence", 0.0),
            )
        except Exception:
            logger.exception("Research cycle failed")

        elapsed = int((datetime.now() - started).total_seconds())
        sleep_for = max(interval_seconds - elapsed, 1)
        logger.info("Sleeping for %s seconds", sleep_for)
        time.sleep(sleep_for)


if __name__ == "__main__":
    main()
