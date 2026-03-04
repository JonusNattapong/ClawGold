"""
Performance Tracker — ClawGold Business Module
================================================
Track record แบบมืออาชีพสำหรับดึงดูดนักลงทุน
คำนวณ: Equity Curve, Sharpe Ratio, Calmar Ratio, Max Drawdown, Win Rate

Output:
    - HTML/JSON Track Record (ใช้ใน website / Telegram)
    - ZuluTrade / MyFXBook compatible export
    - ISO 9001 compliant performance report

Usage:
    python claw.py performance report --format html
    python claw.py performance stats
    python claw.py performance export --format myfxbook
"""

import sqlite3
import json
import math
import os
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from datetime import datetime, timedelta
from contextlib import contextmanager

from logger import get_logger

try:
    from trade_journal import TradeJournal
    JOURNAL_AVAILABLE = True
except ImportError:
    JOURNAL_AVAILABLE = False

try:
    from agent_executor import AgentExecutor
    AGENT_AVAILABLE = True
except ImportError:
    AGENT_AVAILABLE = False

logger = get_logger(__name__)


@dataclass
class TradeRecord:
    ticket: int
    symbol: str
    direction: str          # BUY / SELL
    open_price: float
    close_price: float
    volume: float
    profit: float
    profit_pct: float
    open_time: str
    close_time: str
    duration_minutes: int
    strategy: Optional[str] = None
    comment: Optional[str] = None


@dataclass
class PerformanceStats:
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_profit: float
    total_loss: float
    net_profit: float
    profit_factor: float
    max_drawdown: float
    max_drawdown_pct: float
    sharpe_ratio: float
    calmar_ratio: float
    avg_win: float
    avg_loss: float
    risk_reward: float
    best_month: str
    worst_month: str
    total_return_pct: float
    annual_return_pct: float
    start_balance: float
    current_balance: float


class PerformanceTracker:
    """
    Professional track record system for ClawGold.
    Attracts investors and builds credibility.
    """

    def __init__(self, db_path: str = "data/performance.db",
                 initial_balance: float = 10000.0,
                 config: Optional[dict] = None):
        self.db_path = db_path
        self.initial_balance = initial_balance
        self.config = config or {}
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS trades (
                    ticket INTEGER PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    open_price REAL,
                    close_price REAL,
                    volume REAL,
                    profit REAL,
                    profit_pct REAL,
                    open_time TEXT,
                    close_time TEXT,
                    duration_minutes INTEGER,
                    strategy TEXT,
                    comment TEXT
                );

                CREATE TABLE IF NOT EXISTS equity_curve (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    balance REAL NOT NULL,
                    equity REAL NOT NULL,
                    drawdown_pct REAL DEFAULT 0.0,
                    timestamp TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS monthly_returns (
                    month TEXT PRIMARY KEY,
                    opening_balance REAL,
                    closing_balance REAL,
                    profit REAL,
                    return_pct REAL,
                    trade_count INTEGER,
                    win_count INTEGER
                );
            """)
            conn.commit()

    # ─────────────────────────────────────────────
    # Trade Recording
    # ─────────────────────────────────────────────

    def record_trade(self, ticket: int, symbol: str, direction: str,
                     open_price: float, close_price: float, volume: float,
                     profit: float, open_time: str, close_time: str,
                     strategy: Optional[str] = None) -> bool:
        """Record a completed trade."""
        try:
            open_dt  = datetime.fromisoformat(open_time)
            close_dt = datetime.fromisoformat(close_time)
            duration = int((close_dt - open_dt).total_seconds() / 60)
        except Exception:
            duration = 0

        profit_pct = profit / self.initial_balance * 100

        with self._connect() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO trades
                (ticket, symbol, direction, open_price, close_price, volume,
                 profit, profit_pct, open_time, close_time, duration_minutes, strategy)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (ticket, symbol, direction, open_price, close_price, volume,
                  profit, profit_pct, open_time, close_time, duration, strategy))
            conn.commit()
        return True

    def record_equity_snapshot(self, balance: float, equity: float):
        """Record equity curve data point."""
        with self._connect() as conn:
            peak = conn.execute("SELECT MAX(equity) as m FROM equity_curve").fetchone()['m'] or balance
            drawdown_pct = max(0, (peak - equity) / peak * 100) if peak > 0 else 0
            conn.execute("""
                INSERT INTO equity_curve (balance, equity, drawdown_pct, timestamp)
                VALUES (?, ?, ?, ?)
            """, (balance, equity, drawdown_pct, datetime.now().isoformat()))
            conn.commit()

    # ─────────────────────────────────────────────
    # Statistics Calculation
    # ─────────────────────────────────────────────

    def calculate_stats(self, days: int = 0) -> PerformanceStats:
        """
        Calculate comprehensive performance statistics.
        days=0 means all-time.
        """
        with self._connect() as conn:
            if days > 0:
                since = (datetime.now() - timedelta(days=days)).isoformat()
                trades = conn.execute(
                    "SELECT * FROM trades WHERE close_time > ? ORDER BY close_time", (since,)
                ).fetchall()
            else:
                trades = conn.execute("SELECT * FROM trades ORDER BY close_time").fetchall()

        trades = [dict(t) for t in trades]
        if not trades:
            return self._empty_stats()

        profits = [t['profit'] for t in trades]
        wins    = [p for p in profits if p > 0]
        losses  = [p for p in profits if p <= 0]

        total_profit = sum(w for w in wins)
        total_loss   = abs(sum(losses))
        net_profit   = sum(profits)

        win_rate = len(wins) / len(trades) * 100
        profit_factor = (total_profit / total_loss) if total_loss > 0 else float('inf')
        avg_win  = total_profit / len(wins) if wins else 0
        avg_loss = total_loss / len(losses) if losses else 0
        risk_reward = (avg_win / avg_loss) if avg_loss > 0 else 0

        # Max Drawdown
        with self._connect() as conn:
            max_dd = conn.execute("SELECT MAX(drawdown_pct) as m FROM equity_curve").fetchone()['m'] or 0

        # Sharpe Ratio (annualized from monthly returns)
        monthly = self._get_monthly_returns_list()
        sharpe = self._calc_sharpe(monthly)

        # Annual return
        start = datetime.fromisoformat(trades[0]['open_time']) if trades else datetime.now()
        end   = datetime.fromisoformat(trades[-1]['close_time']) if trades else datetime.now()
        years = max((end - start).days / 365, 1/12)
        total_return_pct = net_profit / self.initial_balance * 100
        annual_return_pct = ((1 + total_return_pct / 100) ** (1 / years) - 1) * 100

        calmar = (annual_return_pct / max_dd) if max_dd > 0 else 0

        # Best/Worst month
        month_data = self._monthly_pnl(trades)
        best_month  = max(month_data, key=lambda x: x['return_pct'], default={}).get('month', 'N/A')
        worst_month = min(month_data, key=lambda x: x['return_pct'], default={}).get('month', 'N/A')

        return PerformanceStats(
            total_trades=len(trades),
            winning_trades=len(wins),
            losing_trades=len(losses),
            win_rate=round(win_rate, 2),
            total_profit=round(total_profit, 2),
            total_loss=round(total_loss, 2),
            net_profit=round(net_profit, 2),
            profit_factor=round(profit_factor, 2),
            max_drawdown=round(max_dd, 2),
            max_drawdown_pct=round(max_dd, 2),
            sharpe_ratio=round(sharpe, 2),
            calmar_ratio=round(calmar, 2),
            avg_win=round(avg_win, 2),
            avg_loss=round(avg_loss, 2),
            risk_reward=round(risk_reward, 2),
            best_month=best_month,
            worst_month=worst_month,
            total_return_pct=round(total_return_pct, 2),
            annual_return_pct=round(annual_return_pct, 2),
            start_balance=self.initial_balance,
            current_balance=round(self.initial_balance + net_profit, 2),
        )

    def _empty_stats(self) -> PerformanceStats:
        return PerformanceStats(
            total_trades=0, winning_trades=0, losing_trades=0, win_rate=0,
            total_profit=0, total_loss=0, net_profit=0, profit_factor=0,
            max_drawdown=0, max_drawdown_pct=0, sharpe_ratio=0, calmar_ratio=0,
            avg_win=0, avg_loss=0, risk_reward=0, best_month='N/A', worst_month='N/A',
            total_return_pct=0, annual_return_pct=0, start_balance=self.initial_balance,
            current_balance=self.initial_balance,
        )

    def _calc_sharpe(self, monthly_returns: List[float], risk_free: float = 0.04) -> float:
        if len(monthly_returns) < 2:
            return 0.0
        avg = sum(monthly_returns) / len(monthly_returns)
        std = math.sqrt(sum((r - avg) ** 2 for r in monthly_returns) / len(monthly_returns))
        if std == 0:
            return 0.0
        monthly_rf = risk_free / 12
        return (avg - monthly_rf) / std * math.sqrt(12)   # annualized

    def _get_monthly_returns_list(self) -> List[float]:
        with self._connect() as conn:
            rows = conn.execute("SELECT return_pct FROM monthly_returns ORDER BY month").fetchall()
        return [r['return_pct'] for r in rows]

    def _monthly_pnl(self, trades: List[Dict]) -> List[Dict]:
        """Group trade profits by month."""
        month_map: Dict[str, float] = {}
        for t in trades:
            try:
                month = t['close_time'][:7]
            except Exception:
                continue
            month_map[month] = month_map.get(month, 0) + t['profit']

        return [
            {'month': m, 'pnl': round(v, 2),
             'return_pct': round(v / self.initial_balance * 100, 2)}
            for m, v in sorted(month_map.items())
        ]

    # ─────────────────────────────────────────────
    # Reports & Export
    # ─────────────────────────────────────────────

    def generate_html_report(self) -> str:
        """Generate a professional HTML track record report."""
        s = self.calculate_stats()
        now = datetime.now().strftime('%Y-%m-%d %H:%M')

        green = "#27ae60"
        red   = "#e74c3c"

        html = f"""<!DOCTYPE html>
<html lang="th">
<head>
    <meta charset="UTF-8">
    <title>ClawGold — Performance Track Record</title>
    <style>
        body {{ font-family: 'Segoe UI', sans-serif; background:#0d1117; color:#e6edf3; margin:0; padding:20px; }}
        h1 {{ color:#f0b429; text-align:center; }}
        .stats-grid {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(180px,1fr)); gap:12px; margin:20px 0; }}
        .card {{ background:#161b22; border-radius:10px; padding:16px; text-align:center; border:1px solid #30363d; }}
        .card .value {{ font-size:1.8em; font-weight:bold; }}
        .card .label {{ font-size:0.8em; color:#8b949e; margin-top:4px; }}
        .green {{ color:{green}; }}
        .red {{ color:{red}; }}
        .section {{ background:#161b22; border-radius:10px; padding:20px; margin:20px 0; border:1px solid #30363d; }}
        table {{ width:100%; border-collapse:collapse; }}
        th {{ background:#21262d; padding:10px; text-align:left; }}
        td {{ padding:8px; border-bottom:1px solid #21262d; }}
        .footer {{ text-align:center; color:#8b949e; margin-top:20px; font-size:0.8em; }}
    </style>
</head>
<body>
    <h1>🏆 ClawGold — XAUUSD Track Record</h1>
    <p style="text-align:center;color:#8b949e;">Generated: {now} UTC | Initial Capital: ${s.start_balance:,.2f}</p>

    <div class="stats-grid">
        <div class="card">
            <div class="value {'green' if s.net_profit >= 0 else 'red'}">${s.net_profit:+,.2f}</div>
            <div class="label">Net Profit</div>
        </div>
        <div class="card">
            <div class="value {'green' if s.total_return_pct >= 0 else 'red'}">{s.total_return_pct:+.2f}%</div>
            <div class="label">Total Return</div>
        </div>
        <div class="card">
            <div class="value green">{s.win_rate:.1f}%</div>
            <div class="label">Win Rate</div>
        </div>
        <div class="card">
            <div class="value green">{s.profit_factor:.2f}x</div>
            <div class="label">Profit Factor</div>
        </div>
        <div class="card">
            <div class="value red">-{s.max_drawdown:.2f}%</div>
            <div class="label">Max Drawdown</div>
        </div>
        <div class="card">
            <div class="value">{s.sharpe_ratio:.2f}</div>
            <div class="label">Sharpe Ratio</div>
        </div>
        <div class="card">
            <div class="value">{s.calmar_ratio:.2f}</div>
            <div class="label">Calmar Ratio</div>
        </div>
        <div class="card">
            <div class="value">{s.total_trades}</div>
            <div class="label">Total Trades</div>
        </div>
    </div>

    <div class="section">
        <h3>📊 Detailed Statistics</h3>
        <table>
            <tr><th>Metric</th><th>Value</th></tr>
            <tr><td>Annual Return</td><td class="{'green' if s.annual_return_pct>0 else 'red'}">{s.annual_return_pct:+.2f}%</td></tr>
            <tr><td>Winning Trades</td><td class="green">{s.winning_trades}</td></tr>
            <tr><td>Losing Trades</td><td class="red">{s.losing_trades}</td></tr>
            <tr><td>Average Win</td><td class="green">${s.avg_win:.2f}</td></tr>
            <tr><td>Average Loss</td><td class="red">-${s.avg_loss:.2f}</td></tr>
            <tr><td>Risk:Reward</td><td>1:{s.risk_reward:.2f}</td></tr>
            <tr><td>Best Month</td><td class="green">{s.best_month}</td></tr>
            <tr><td>Worst Month</td><td class="red">{s.worst_month}</td></tr>
            <tr><td>Current Balance</td><td>${s.current_balance:,.2f}</td></tr>
        </table>
    </div>

    <div class="footer">
        ⚠️ Past performance does not guarantee future results. Trading gold involves substantial risk.
        <br>© {datetime.now().year} ClawGold | clawgold.io
    </div>
</body>
</html>"""
        return html

    def export_myfxbook(self) -> Dict[str, Any]:
        """Export data in MyFXBook-compatible JSON format."""
        s = self.calculate_stats()
        with self._connect() as conn:
            trades = [dict(t) for t in conn.execute("SELECT * FROM trades ORDER BY close_time").fetchall()]

        return {
            "account": {
                "balance":       s.current_balance,
                "equity":        s.current_balance,
                "profit":        s.net_profit,
                "deposit":       s.start_balance,
                "profitFactor":  s.profit_factor,
                "winRatio":      s.win_rate,
                "drawdown":      s.max_drawdown,
                "trades":        s.total_trades,
                "wonTrades":     s.winning_trades,
                "lostTrades":    s.losing_trades,
            },
            "trades": [
                {
                    "openTime":  t['open_time'],
                    "closeTime": t['close_time'],
                    "symbol":    t['symbol'],
                    "action":    t['direction'],
                    "lots":      t['volume'],
                    "openPrice": t['open_price'],
                    "closePrice":t['close_price'],
                    "profit":    t['profit'],
                }
                for t in trades
            ]
        }

    def print_summary(self) -> str:
        """1-line Telegram-friendly summary."""
        s = self.calculate_stats()
        return (
            f"📊 <b>ClawGold Performance</b>\n"
            f"💰 Net: ${s.net_profit:+,.2f} ({s.total_return_pct:+.2f}%)\n"
            f"🎯 Win Rate: {s.win_rate:.1f}%  |  PF: {s.profit_factor:.2f}x\n"
            f"📉 Max DD: {s.max_drawdown:.2f}%  |  Sharpe: {s.sharpe_ratio:.2f}\n"
            f"📈 Trades: {s.total_trades} ({s.winning_trades}W/{s.losing_trades}L)"
        )
