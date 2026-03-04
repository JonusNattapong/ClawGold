"""
PAMM Manager — ClawGold Business Module
=========================================
ระบบบริหารพอร์ตให้นักลงทุน (Percent Allocation Management Module)

Business Model:
    - รับเงินจากนักลงทุน → เทรดรวมกัน → แบ่งกำไร
    - Performance Fee: 20% of profits (High Watermark)
    - Management Fee: 1.5% ต่อปี (รายเดือน)
    - High Watermark: คิด Performance Fee เฉพาะกำไรใหม่ที่ทำได้

Example:
    Investor A: $10,000 → NAV ขึ้น 10% → ได้ $900 (หลังหัก 20% perf fee)
    ClawGold รับ: $100 (perf fee) + $12.50 (mgmt fee)

Usage:
    python claw.py pamm add-investor --name "Alice" --amount 10000
    python claw.py pamm update-nav --nav 21500.00
    python claw.py pamm monthly-statement
    python claw.py pamm withdraw --investor alice --amount 5000
"""

import sqlite3
import json
import os
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from datetime import datetime, timedelta
from contextlib import contextmanager

from logger import get_logger

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────────
# Fee Structure (แก้ไขได้ในนี้หรือ config.yaml)
# ─────────────────────────────────────────────────────────
PERFORMANCE_FEE_PCT = 0.20   # 20% of profit above high watermark
MANAGEMENT_FEE_PCT  = 0.015  # 1.5% per year billed monthly (= 0.125%/mo)


@dataclass
class Investor:
    id: int
    name: str
    email: str
    capital: float           # Total capital allocated (USD)
    share_pct: float         # % of total fund
    high_watermark: float    # Highest NAV per unit ever achieved
    joined_at: str
    active: bool = True
    unrealized_pnl: float = 0.0
    total_fees_paid: float = 0.0
    contact: Optional[str] = None


@dataclass
class FundSnapshot:
    total_nav: float         # Total Net Asset Value (all investors)
    date: str
    sharpe: Optional[float] = None
    drawdown: Optional[float] = None
    note: Optional[str] = None


class PAMMManager:
    """
    PAMM (Percent Allocation Management Module) for ClawGold.
    Manages investor allocations, profit sharing, and monthly statements.
    """

    def __init__(self, db_path: str = "data/pamm.db",
                 notifier=None,
                 config: Optional[dict] = None):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.notifier = notifier
        self.config = config or {}
        self.perf_fee = self.config.get('pamm', {}).get('performance_fee', PERFORMANCE_FEE_PCT)
        self.mgmt_fee = self.config.get('pamm', {}).get('management_fee', MANAGEMENT_FEE_PCT)
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
                CREATE TABLE IF NOT EXISTS investors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    email TEXT,
                    contact TEXT,
                    capital REAL NOT NULL DEFAULT 0.0,
                    share_pct REAL DEFAULT 0.0,
                    high_watermark REAL DEFAULT 0.0,
                    joined_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    active INTEGER DEFAULT 1,
                    total_fees_paid REAL DEFAULT 0.0,
                    unrealized_pnl REAL DEFAULT 0.0
                );

                CREATE TABLE IF NOT EXISTS nav_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    total_nav REAL NOT NULL,
                    date TEXT DEFAULT CURRENT_TIMESTAMP,
                    sharpe REAL,
                    drawdown REAL,
                    note TEXT
                );

                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    investor_id INTEGER NOT NULL,
                    type TEXT NOT NULL,     -- deposit / withdrawal / fee / profit_share
                    amount REAL NOT NULL,
                    note TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS monthly_statements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    investor_id INTEGER NOT NULL,
                    month TEXT NOT NULL,
                    opening_nav REAL,
                    closing_nav REAL,
                    gross_profit REAL,
                    performance_fee REAL,
                    management_fee REAL,
                    net_profit REAL,
                    return_pct REAL,
                    generated_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.commit()

    # ─────────────────────────────────────────────
    # Investor Management
    # ─────────────────────────────────────────────

    def add_investor(self, name: str, capital: float, email: str = "",
                     contact: str = "") -> int:
        """
        Onboard a new investor with initial capital.
        Returns investor ID.
        """
        if capital < 1000:
            raise ValueError("Minimum investment is $1,000")

        with self._connect() as conn:
            cur = conn.execute("""
                INSERT INTO investors (name, email, contact, capital, high_watermark, joined_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (name, email, contact, capital, capital, datetime.now().isoformat()))
            investor_id = cur.lastrowid

            conn.execute("""
                INSERT INTO transactions (investor_id, type, amount, note)
                VALUES (?, 'deposit', ?, ?)
            """, (investor_id, capital, f"Initial investment by {name}"))

            conn.commit()

        # Recalculate all share percentages
        self._recompute_shares()

        logger.info(f"New investor: {name} – ${capital:,.2f}")
        return investor_id

    def record_deposit(self, investor_id: int, amount: float) -> bool:
        """Record additional capital deposit."""
        with self._connect() as conn:
            conn.execute("UPDATE investors SET capital=capital+? WHERE id=?", (amount, investor_id))
            conn.execute("""
                INSERT INTO transactions (investor_id, type, amount, note)
                VALUES (?, 'deposit', ?, 'Additional deposit')
            """, (investor_id, amount))
            conn.commit()
        self._recompute_shares()
        return True

    def record_withdrawal(self, investor_id: int, amount: float) -> bool:
        """Record capital withdrawal (deducted from capital)."""
        with self._connect() as conn:
            inv = conn.execute("SELECT * FROM investors WHERE id=?", (investor_id,)).fetchone()
            if not inv or inv['capital'] < amount:
                logger.error("Insufficient capital for withdrawal")
                return False

            conn.execute("UPDATE investors SET capital=capital-? WHERE id=?", (amount, investor_id))
            conn.execute("""
                INSERT INTO transactions (investor_id, type, amount, note)
                VALUES (?, 'withdrawal', ?, 'Client withdrawal')
            """, (investor_id, amount))
            conn.commit()

        self._recompute_shares()
        return True

    def _recompute_shares(self):
        """Recompute share % for all active investors."""
        with self._connect() as conn:
            total = conn.execute(
                "SELECT SUM(capital) as t FROM investors WHERE active=1"
            ).fetchone()['t'] or 0
            if total == 0:
                return
            investors = conn.execute("SELECT id, capital FROM investors WHERE active=1").fetchall()
            for inv in investors:
                pct = inv['capital'] / total * 100
                conn.execute("UPDATE investors SET share_pct=? WHERE id=?", (round(pct, 4), inv['id']))
            conn.commit()

    # ─────────────────────────────────────────────
    # NAV & Profit Distribution
    # ─────────────────────────────────────────────

    def update_nav(self, total_nav: float, note: str = "") -> Dict[str, Any]:
        """
        Update fund NAV and calculate profit distribution.

        Args:
            total_nav: Current total fund value (all accounts combined)
            note: Optional note (e.g., "End of Month")

        Returns:
            Distribution summary per investor
        """
        with self._connect() as conn:
            # Get previous NAV
            prev = conn.execute(
                "SELECT total_nav FROM nav_history ORDER BY id DESC LIMIT 1"
            ).fetchone()
            prev_nav = prev['total_nav'] if prev else total_nav

            conn.execute("""
                INSERT INTO nav_history (total_nav, date, note)
                VALUES (?, ?, ?)
            """, (total_nav, datetime.now().isoformat(), note))

            investors = conn.execute("SELECT * FROM investors WHERE active=1").fetchall()
            conn.commit()

        distributions = []
        total_perf_fee = 0.0
        total_mgmt_fee = 0.0

        for inv in investors:
            share = inv['share_pct'] / 100
            current_value = total_nav * share
            prev_value = prev_nav * share
            gross_profit = current_value - prev_value

            # Performance Fee (only on new highs above high watermark)
            high_wm = inv['high_watermark']
            perf_fee = 0.0
            if current_value > high_wm and gross_profit > 0:
                above_hwm_profit = current_value - high_wm
                perf_fee = above_hwm_profit * self.perf_fee

            # Management Fee (monthly: annual rate / 12)
            monthly_mgmt = inv['capital'] * (self.mgmt_fee / 12)

            net_profit = gross_profit - perf_fee - monthly_mgmt
            new_hwm = max(current_value, high_wm)

            with self._connect() as conn:
                conn.execute("""
                    UPDATE investors
                    SET high_watermark=?,
                        unrealized_pnl=?,
                        total_fees_paid=total_fees_paid+?
                    WHERE id=?
                """, (new_hwm, net_profit, perf_fee + monthly_mgmt, inv['id']))

                if perf_fee + monthly_mgmt > 0:
                    conn.execute("""
                        INSERT INTO transactions (investor_id, type, amount, note)
                        VALUES (?, 'fee', ?, ?)
                    """, (inv['id'], perf_fee + monthly_mgmt,
                          f"Perf: ${perf_fee:.2f} + Mgmt: ${monthly_mgmt:.2f}"))
                conn.commit()

            total_perf_fee += perf_fee
            total_mgmt_fee += monthly_mgmt
            return_pct = (net_profit / prev_value * 100) if prev_value > 0 else 0

            distributions.append({
                'investor':        inv['name'],
                'share':           f"{inv['share_pct']:.2f}%",
                'prev_value':      round(prev_value, 2),
                'current_value':   round(current_value, 2),
                'gross_profit':    round(gross_profit, 2),
                'performance_fee': round(perf_fee, 2),
                'management_fee':  round(monthly_mgmt, 2),
                'net_profit':      round(net_profit, 2),
                'return_pct':      round(return_pct, 2),
            })

        logger.info(
            f"NAV updated: ${total_nav:,.2f} | "
            f"Perf Fees: ${total_perf_fee:.2f} | Mgmt Fees: ${total_mgmt_fee:.2f}"
        )

        return {
            'total_nav':        round(total_nav, 2),
            'change_from_prev': round(total_nav - prev_nav, 2),
            'total_perf_fee':   round(total_perf_fee, 2),
            'total_mgmt_fee':   round(total_mgmt_fee, 2),
            'total_clawgold_fee': round(total_perf_fee + total_mgmt_fee, 2),
            'distributions':    distributions,
        }

    # ─────────────────────────────────────────────
    # Monthly Statement
    # ─────────────────────────────────────────────

    def generate_monthly_statement(self, month: Optional[str] = None) -> List[Dict]:
        """
        Generate monthly statement for all investors.
        Month format: '2026-03'
        """
        if not month:
            month = datetime.now().strftime('%Y-%m')

        month_start = f"{month}-01"
        with self._connect() as conn:
            nav_rows = conn.execute("""
                SELECT * FROM nav_history
                WHERE date LIKE ? ORDER BY date ASC LIMIT 1
            """, (f"{month}%",)).fetchone()

            nav_end = conn.execute("""
                SELECT * FROM nav_history
                WHERE date LIKE ? ORDER BY date DESC LIMIT 1
            """, (f"{month}%",)).fetchone()

            investors = conn.execute("SELECT * FROM investors WHERE active=1").fetchall()

        statements = []
        for inv in investors:
            share = inv['share_pct'] / 100
            opening = (nav_rows['total_nav'] * share) if nav_rows else inv['capital']
            closing = (nav_end['total_nav'] * share) if nav_end else inv['capital']
            gross = closing - opening
            perf_fee = max(0, gross * self.perf_fee) if gross > 0 else 0
            mgmt_fee = inv['capital'] * (self.mgmt_fee / 12)
            net = gross - perf_fee - mgmt_fee
            ret_pct = (net / opening * 100) if opening > 0 else 0

            stmt = {
                'month':            month,
                'investor':         inv['name'],
                'email':            inv['email'],
                'opening_nav':      round(opening, 2),
                'closing_nav':      round(closing, 2),
                'gross_profit':     round(gross, 2),
                'performance_fee':  round(perf_fee, 2),
                'management_fee':   round(mgmt_fee, 2),
                'net_profit':       round(net, 2),
                'return_pct':       round(ret_pct, 2),
            }
            statements.append(stmt)

            with self._connect() as conn:
                conn.execute("""
                    INSERT INTO monthly_statements
                    (investor_id, month, opening_nav, closing_nav, gross_profit,
                     performance_fee, management_fee, net_profit, return_pct)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (inv['id'], month, stmt['opening_nav'], stmt['closing_nav'],
                      stmt['gross_profit'], stmt['performance_fee'], stmt['management_fee'],
                      stmt['net_profit'], stmt['return_pct']))
                conn.commit()

        return statements

    # ─────────────────────────────────────────────
    # Fund Overview
    # ─────────────────────────────────────────────

    def get_fund_overview(self) -> Dict[str, Any]:
        """Get current fund summary for dashboard."""
        with self._connect() as conn:
            latest_nav = conn.execute(
                "SELECT total_nav, date FROM nav_history ORDER BY id DESC LIMIT 1"
            ).fetchone()

            first_nav = conn.execute(
                "SELECT total_nav FROM nav_history ORDER BY id ASC LIMIT 1"
            ).fetchone()

            investors = conn.execute(
                "SELECT COUNT(*) as cnt, SUM(capital) as total_cap FROM investors WHERE active=1"
            ).fetchone()

            total_fees = conn.execute(
                "SELECT SUM(amount) as total FROM transactions WHERE type='fee'"
            ).fetchone()

        current_nav = latest_nav['total_nav'] if latest_nav else 0
        initial_nav = first_nav['total_nav'] if first_nav else current_nav
        total_return = (current_nav - initial_nav) / initial_nav * 100 if initial_nav > 0 else 0

        return {
            'fund': {
                'current_nav':    round(current_nav, 2),
                'initial_nav':    round(initial_nav, 2),
                'total_return':   round(total_return, 2),
                'as_of_date':     latest_nav['date'][:10] if latest_nav else 'N/A',
            },
            'investors': {
                'active_count':   investors['cnt'] or 0,
                'total_capital':  round(investors['total_cap'] or 0, 2),
            },
            'clawgold_revenue': {
                'total_fees_earned': round(total_fees['total'] or 0, 2),
                'fee_structure':     f"{self.perf_fee*100:.0f}% perf + {self.mgmt_fee*100:.1f}%/yr mgmt"
            }
        }
