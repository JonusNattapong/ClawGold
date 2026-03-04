"""
Trade Journal & Analytics
=========================
Stores trade rationale + AI snapshot and provides performance analytics.
"""

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

from logger import get_logger

logger = get_logger(__name__)


@dataclass
class JournalEntry:
    """Trade journal entry model."""
    action: str
    symbol: str
    volume: float
    price: float
    strategy: str = "manual"
    market_condition: str = "unknown"
    reason: str = ""
    ai_research_snapshot: Optional[Dict[str, Any]] = None
    realized_pnl: Optional[float] = None
    ticket: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None
    occurred_at: Optional[datetime] = None
    account_equity: Optional[float] = None


class TradeJournal:
    """SQLite-backed trade journal and analytics engine."""

    def __init__(self, db_path: str = "data/trade_journal.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS trade_journal (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    occurred_at TIMESTAMP NOT NULL,
                    action TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    volume REAL NOT NULL,
                    price REAL NOT NULL,
                    ticket INTEGER,
                    strategy TEXT NOT NULL,
                    market_condition TEXT NOT NULL,
                    reason TEXT,
                    ai_research_snapshot TEXT,
                    realized_pnl REAL,
                    account_equity REAL,
                    metadata TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_journal_time
                ON trade_journal(occurred_at)
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_journal_strategy
                ON trade_journal(strategy)
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_journal_market_condition
                ON trade_journal(market_condition)
                """
            )
            conn.commit()

    def add_entry(self, entry: JournalEntry) -> int:
        """Insert a trade journal entry and return row id."""
        occurred_at = entry.occurred_at or datetime.now()
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO trade_journal (
                    occurred_at, action, symbol, volume, price, ticket,
                    strategy, market_condition, reason, ai_research_snapshot,
                    realized_pnl, account_equity, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    occurred_at,
                    entry.action.upper(),
                    entry.symbol,
                    entry.volume,
                    entry.price,
                    entry.ticket,
                    entry.strategy,
                    entry.market_condition,
                    entry.reason,
                    json.dumps(entry.ai_research_snapshot, ensure_ascii=False)
                    if entry.ai_research_snapshot
                    else None,
                    entry.realized_pnl,
                    entry.account_equity,
                    json.dumps(entry.metadata, ensure_ascii=False)
                    if entry.metadata
                    else None,
                ),
            )
            conn.commit()
            row_id = cursor.lastrowid
            logger.info(f"Trade journal entry saved: id={row_id}, action={entry.action}")
            return row_id

    def _load_rows(self, since: datetime) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM trade_journal
                WHERE occurred_at >= ?
                ORDER BY occurred_at ASC
                """,
                (since,),
            )
            rows = [dict(r) for r in cursor.fetchall()]
            for r in rows:
                if r.get("ai_research_snapshot"):
                    r["ai_research_snapshot"] = json.loads(r["ai_research_snapshot"])
                if r.get("metadata"):
                    r["metadata"] = json.loads(r["metadata"])
            return rows

    @staticmethod
    def _time_bucket(dt: datetime) -> str:
        hour = dt.hour
        if 0 <= hour < 6:
            return "00-06"
        if 6 <= hour < 12:
            return "06-12"
        if 12 <= hour < 18:
            return "12-18"
        return "18-24"

    def get_analytics(self, days: int = 90) -> Dict[str, Any]:
        """Compute win-rate analytics by strategy, time bucket, and market condition."""
        since = datetime.now() - timedelta(days=days)
        rows = self._load_rows(since)

        closed = [r for r in rows if r.get("realized_pnl") is not None]
        total_closed = len(closed)
        wins = len([r for r in closed if float(r["realized_pnl"]) > 0])

        def add_stat(group: Dict[str, Dict[str, int]], key: str, pnl: float):
            if key not in group:
                group[key] = {"wins": 0, "losses": 0, "total": 0}
            group[key]["total"] += 1
            if pnl > 0:
                group[key]["wins"] += 1
            else:
                group[key]["losses"] += 1

        by_strategy: Dict[str, Dict[str, int]] = {}
        by_time: Dict[str, Dict[str, int]] = {}
        by_market_condition: Dict[str, Dict[str, int]] = {}

        for r in closed:
            pnl = float(r["realized_pnl"])
            strategy = r.get("strategy") or "unknown"
            market = r.get("market_condition") or "unknown"
            occurred_at = datetime.fromisoformat(str(r["occurred_at"]))
            bucket = self._time_bucket(occurred_at)

            add_stat(by_strategy, strategy, pnl)
            add_stat(by_market_condition, market, pnl)
            add_stat(by_time, bucket, pnl)

        def with_rate(group: Dict[str, Dict[str, int]]) -> Dict[str, Dict[str, Any]]:
            out: Dict[str, Dict[str, Any]] = {}
            for k, v in group.items():
                total = v["total"]
                out[k] = {
                    **v,
                    "win_rate": (v["wins"] / total) if total else 0.0,
                }
            return out

        return {
            "days": days,
            "total_entries": len(rows),
            "total_closed": total_closed,
            "overall_win_rate": (wins / total_closed) if total_closed else 0.0,
            "win_rate_by_strategy": with_rate(by_strategy),
            "win_rate_by_time": with_rate(by_time),
            "win_rate_by_market_condition": with_rate(by_market_condition),
        }

    def get_equity_curve(self, days: int = 90) -> List[Dict[str, Any]]:
        """Return ordered equity points for charting/tracking."""
        since = datetime.now() - timedelta(days=days)
        rows = self._load_rows(since)

        points = []
        for r in rows:
            if r.get("account_equity") is None:
                continue
            points.append(
                {
                    "timestamp": r["occurred_at"],
                    "equity": float(r["account_equity"]),
                    "action": r["action"],
                    "symbol": r["symbol"],
                }
            )
        return points

