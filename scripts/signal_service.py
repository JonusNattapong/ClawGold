"""
Signal Service — ClawGold Business Module
==========================================
ระบบขาย Trading Signal ผ่าน Telegram แบบ Subscription

Business Model:
    - Free Tier    : สัญญาณล่าช้า 4 ชั่วโมง, 3 สัญญาณ/วัน
    - Basic Tier   : สัญญาณ Real-time, ไม่จำกัด (~$29/เดือน)
    - Pro Tier     : Real-time + Entry/SL/TP + AI Reasoning (~$79/เดือน)
    - VIP Tier     : Pro + โทรศัพท์ consultation + 1-on-1 (~$199/เดือน)

Usage:
    python claw.py signals add-subscriber --chat-id 123456 --tier pro --expires 2026-04-01
    python claw.py signals broadcast --signal BUY --price 2950.5 --sl 2920 --tp 3010
    python claw.py signals stats
    python claw.py signals monthly-revenue
"""

import sqlite3
import json
import os
import requests
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
from contextlib import contextmanager

from logger import get_logger

logger = get_logger(__name__)


class SubscriptionTier(Enum):
    FREE  = "free"
    BASIC = "basic"    # $29/mo
    PRO   = "pro"      # $79/mo
    VIP   = "vip"      # $199/mo


# Tier pricing in USD
TIER_PRICES = {
    SubscriptionTier.FREE:  0,
    SubscriptionTier.BASIC: 29,
    SubscriptionTier.PRO:   79,
    SubscriptionTier.VIP:   199,
}

# Tier features
TIER_FEATURES = {
    SubscriptionTier.FREE:  {"delay_hours": 4, "signals_per_day": 3, "include_tp_sl": False, "include_ai_reason": False},
    SubscriptionTier.BASIC: {"delay_hours": 0, "signals_per_day": 999, "include_tp_sl": True,  "include_ai_reason": False},
    SubscriptionTier.PRO:   {"delay_hours": 0, "signals_per_day": 999, "include_tp_sl": True,  "include_ai_reason": True},
    SubscriptionTier.VIP:   {"delay_hours": 0, "signals_per_day": 999, "include_tp_sl": True,  "include_ai_reason": True},
}


@dataclass
class Subscriber:
    chat_id: str
    name: str
    tier: str
    expires_at: str
    active: bool = True
    joined_at: str = ""
    signals_received: int = 0
    referral_code: Optional[str] = None


@dataclass 
class SentSignal:
    symbol: str
    action: str          # BUY / SELL / CLOSE
    entry_price: float
    stop_loss: Optional[float]
    take_profit: Optional[float]
    confidence: float
    ai_reasoning: Optional[str]
    outcome: Optional[str] = None    # WIN / LOSS / PENDING
    close_price: Optional[float] = None
    pnl_pips: Optional[float] = None
    sent_at: str = ""


class SignalService:
    """Telegram Signal Service for ClawGold."""

    # Tier-to-group channel mapping (loaded from config)
    TIER_CHANNELS: Dict[str, str] = {}

    def __init__(self, db_path: str = "data/signal_service.db",
                 bot_token: Optional[str] = None,
                 config: Optional[dict] = None):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.config = config or {}

        # Load tier channel IDs from config
        channels_cfg = self.config.get('signal_service', {}).get('channels', {})
        self.TIER_CHANNELS = {
            'free':  channels_cfg.get('free',  os.getenv('SIGNAL_CH_FREE',  '-1002530348291')),
            'basic': channels_cfg.get('basic', os.getenv('SIGNAL_CH_BASIC', '-1002609941948')),
            'pro':   channels_cfg.get('pro',   os.getenv('SIGNAL_CH_PRO',   '-1002694677449')),
            'vip':   channels_cfg.get('vip',   os.getenv('SIGNAL_CH_VIP',   '')),
        }
        logger.info(f"Signal channels loaded: { {k: v for k, v in self.TIER_CHANNELS.items() if v} }")
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
                CREATE TABLE IF NOT EXISTS subscribers (
                    chat_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    tier TEXT NOT NULL DEFAULT 'free',
                    expires_at TEXT,
                    active INTEGER DEFAULT 1,
                    joined_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    signals_received INTEGER DEFAULT 0,
                    referral_code TEXT
                );

                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    action TEXT NOT NULL,
                    entry_price REAL,
                    stop_loss REAL,
                    take_profit REAL,
                    confidence REAL,
                    ai_reasoning TEXT,
                    outcome TEXT,
                    close_price REAL,
                    pnl_pips REAL,
                    sent_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id TEXT NOT NULL,
                    amount REAL NOT NULL,
                    currency TEXT DEFAULT 'USD',
                    tier TEXT NOT NULL,
                    months INTEGER DEFAULT 1,
                    method TEXT,
                    note TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.commit()

    # ─────────────────────────────────────────────
    # Subscriber Management
    # ─────────────────────────────────────────────

    def add_subscriber(self, chat_id: str, name: str, tier: str = "free",
                       months: int = 1, payment_method: str = "manual") -> bool:
        """Add or upgrade a subscriber."""
        expires = (datetime.now() + timedelta(days=30 * months)).isoformat()
        try:
            tier_enum = SubscriptionTier(tier)
        except ValueError:
            logger.error(f"Invalid tier: {tier}")
            return False

        with self._connect() as conn:
            conn.execute("""
                INSERT INTO subscribers (chat_id, name, tier, expires_at, active, joined_at)
                VALUES (?, ?, ?, ?, 1, ?)
                ON CONFLICT(chat_id) DO UPDATE SET
                    tier = excluded.tier,
                    expires_at = excluded.expires_at,
                    active = 1
            """, (chat_id, name, tier, expires, datetime.now().isoformat()))

            if tier != "free":
                price = TIER_PRICES[tier_enum]
                conn.execute("""
                    INSERT INTO payments (chat_id, amount, tier, months, method)
                    VALUES (?, ?, ?, ?, ?)
                """, (chat_id, price * months, tier, months, payment_method))

            conn.commit()

        logger.info(f"Subscriber {name} ({chat_id}) added as {tier.upper()} until {expires[:10]}")

        # Welcome message
        features = TIER_FEATURES[tier_enum]
        rt_label = "✓" if features['delay_hours'] == 0 else f"ล่าช้า {features['delay_hours']}h"
        msg = (
            f"🏆 <b>ยินดีต้อนรับสู่ ClawGold Signal Service!</b>\n\n"
            f"👤 ชื่อ: {name}\n"
            f"⭐ Tier: <b>{tier.upper()}</b>\n"
            f"📅 หมดอายุ: {expires[:10]}\n\n"
            f"✅ Real-time Signals: {rt_label}\n"
            f"🎯 Entry / SL / TP: {'✓' if features['include_tp_sl'] else '✗'}\n"
            f"🤖 AI Reasoning: {'✓' if features['include_ai_reason'] else '✗'}\n\n"
            f"📊 Track Record: https://clawgold.io/performance\n"
        )
        self._send(chat_id, msg)
        return True

    def remove_subscriber(self, chat_id: str) -> bool:
        with self._connect() as conn:
            conn.execute("UPDATE subscribers SET active=0 WHERE chat_id=?", (chat_id,))
            conn.commit()
        return True

    def get_active_subscribers(self, tier: Optional[str] = None) -> List[Dict]:
        now = datetime.now().isoformat()
        with self._connect() as conn:
            if tier:
                rows = conn.execute("""
                    SELECT * FROM subscribers
                    WHERE active=1 AND tier=? AND (expires_at IS NULL OR expires_at > ?)
                """, (tier, now)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT * FROM subscribers
                    WHERE active=1 AND (expires_at IS NULL OR expires_at > ?)
                """, (now,)).fetchall()
        return [dict(r) for r in rows]

    def get_expiring_soon(self, days: int = 3) -> List[Dict]:
        """Get subscribers expiring within N days."""
        cutoff = (datetime.now() + timedelta(days=days)).isoformat()
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT * FROM subscribers
                WHERE active=1 AND expires_at < ? AND tier != 'free'
                ORDER BY expires_at ASC
            """, (cutoff,)).fetchall()
        return [dict(r) for r in rows]

    # ─────────────────────────────────────────────
    # Signal Broadcasting
    # ─────────────────────────────────────────────

    def broadcast_signal(self, symbol: str, action: str, entry_price: float,
                         stop_loss: Optional[float] = None,
                         take_profit: Optional[float] = None,
                         confidence: float = 0.75,
                         ai_reasoning: Optional[str] = None) -> int:
        """
        Broadcast trading signal to all eligible subscribers.
        Returns number of messages sent.
        """
        now = datetime.now()

        # Save signal to DB
        with self._connect() as conn:
            cur = conn.execute("""
                INSERT INTO signals (symbol, action, entry_price, stop_loss, take_profit,
                    confidence, ai_reasoning, sent_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (symbol, action, entry_price, stop_loss, take_profit,
                  confidence, ai_reasoning, now.isoformat()))
            signal_id = cur.lastrowid
            conn.commit()

        sent_count = 0

        # ── Broadcast to Tier Group Channels ──────────────────────────
        # Each tier has its own Telegram group. We send ONE message per tier
        # so all group members receive it simultaneously — no need to loop
        # through individual subscribers.
        tier_order = ['vip', 'pro', 'basic', 'free']  # highest first
        for tier_name in tier_order:
            channel_id = self.TIER_CHANNELS.get(tier_name, '')
            if not channel_id:
                continue

            tier_enum = SubscriptionTier(tier_name)
            features  = TIER_FEATURES[tier_enum]

            # Free tier: no real-time — post a teaser only
            if features['delay_hours'] > 0:
                teaser = (
                    f"⚡ <b>ClawGold Signal #{signal_id} — {action} {symbol}</b>\n"
                    f"🔒 สัญญาณ Real-time สำหรับสมาชิก Basic ขึ้นไป\n"
                    f"👉 อัปเกรด: @ClawGoldAdmin | ${TIER_PRICES[SubscriptionTier.BASIC]}/เดือน"
                )
                if self._send(channel_id, teaser):
                    sent_count += 1
                continue

            msg = self._format_signal_message(
                symbol=symbol,
                action=action,
                entry_price=entry_price,
                stop_loss=stop_loss if features['include_tp_sl'] else None,
                take_profit=take_profit if features['include_tp_sl'] else None,
                confidence=confidence,
                ai_reasoning=ai_reasoning if features['include_ai_reason'] else None,
                tier=tier_name,
                signal_id=signal_id
            )

            if self._send(channel_id, msg):
                sent_count += 1
                logger.info(f"Signal #{signal_id} → {tier_name.upper()} channel {channel_id}")

        # ── Also send to individual VIP DMs (optional concierge) ──────
        vip_subs = self.get_active_subscribers(tier='vip')
        for sub in vip_subs:
            msg = self._format_signal_message(
                symbol=symbol, action=action, entry_price=entry_price,
                stop_loss=stop_loss, take_profit=take_profit,
                confidence=confidence, ai_reasoning=ai_reasoning,
                tier='vip', signal_id=signal_id
            )
            if self._send(sub['chat_id'], msg):
                with self._connect() as conn:
                    conn.execute(
                        "UPDATE subscribers SET signals_received=signals_received+1 WHERE chat_id=?",
                        (sub['chat_id'],)
                    )
                    conn.commit()

        logger.info(f"Signal #{signal_id} broadcast complete — {sent_count} channels reached")
        return sent_count

    def _format_signal_message(self, symbol: str, action: str, entry_price: float,
                                stop_loss: Optional[float], take_profit: Optional[float],
                                confidence: float, ai_reasoning: Optional[str],
                                tier: str, signal_id: int) -> str:
        """Format signal message based on tier."""
        emoji = "🟢" if action == "BUY" else ("🔴" if action == "SELL" else "⚪")
        rr = None
        if stop_loss and take_profit:
            risk = abs(entry_price - stop_loss)
            reward = abs(take_profit - entry_price)
            rr = round(reward / risk, 2) if risk > 0 else None

        msg = (
            f"⚡ <b>ClawGold Signal #{signal_id}</b>\n"
            f"{'─' * 28}\n"
            f"{emoji} <b>{action}</b> {symbol}\n"
            f"💵 Entry: <code>{entry_price:.2f}</code>\n"
        )

        if stop_loss:
            msg += f"🛑 Stop Loss: <code>{stop_loss:.2f}</code>\n"
        if take_profit:
            msg += f"🎯 Take Profit: <code>{take_profit:.2f}</code>\n"
        if rr:
            msg += f"📐 Risk:Reward = 1:{rr}\n"

        msg += (
            f"📊 Confidence: {confidence:.0%}\n"
            f"⏱ {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC\n"
        )

        if ai_reasoning:
            msg += f"\n🤖 <b>AI Analysis:</b>\n<i>{ai_reasoning[:300]}</i>\n"

        msg += (
            f"\n{'─' * 28}\n"
            f"⭐ Tier: {tier.upper()}\n"
            f"📈 Track Record: https://clawgold.io/performance\n"
            f"⚠️ <i>Trading involves risk. Not financial advice.</i>"
        )
        return msg

    def close_signal(self, signal_id: int, close_price: float, outcome: str = "WIN") -> bool:
        """Mark signal as closed with outcome."""
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM signals WHERE id=?", (signal_id,)).fetchone()
            if not row:
                return False

            pnl = None
            action = row['action']
            entry = row['entry_price']
            if action == 'BUY':
                pnl = round((close_price - entry) / 0.1, 1)   # pips approx
            elif action == 'SELL':
                pnl = round((entry - close_price) / 0.1, 1)

            conn.execute("""
                UPDATE signals
                SET outcome=?, close_price=?, pnl_pips=?
                WHERE id=?
            """, (outcome, close_price, pnl, signal_id))
            conn.commit()

        # Broadcast close notification
        msg = (
            f"{'✅' if outcome == 'WIN' else '❌'} <b>Signal #{signal_id} CLOSED</b>\n\n"
            f"Symbol: {row['symbol']}  {row['action']}\n"
            f"Entry: {row['entry_price']:.2f} → Close: {close_price:.2f}\n"
            f"Result: <b>{outcome}</b>  ({pnl:+.1f} pips)\n\n"
            f"📊 Updated record: https://clawgold.io/performance"
        )
        for sub in self.get_active_subscribers():
            if SubscriptionTier(sub['tier']) != SubscriptionTier.FREE:
                self._send(sub['chat_id'], msg)

        return True

    # ─────────────────────────────────────────────
    # Revenue & Stats
    # ─────────────────────────────────────────────

    def get_revenue_stats(self) -> Dict[str, Any]:
        """Monthly revenue breakdown."""
        now = datetime.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0).isoformat()

        with self._connect() as conn:
            # Total subscribers by tier
            tier_counts = {row['tier']: row['cnt'] for row in conn.execute(
                "SELECT tier, COUNT(*) as cnt FROM subscribers WHERE active=1 GROUP BY tier"
            ).fetchall()}

            # Monthly revenue (from payments this month)
            monthly_rev = conn.execute("""
                SELECT SUM(amount) as total FROM payments WHERE created_at > ?
            """, (month_start,)).fetchone()['total'] or 0

            # Total all-time revenue
            total_rev = conn.execute("SELECT SUM(amount) as total FROM payments").fetchone()['total'] or 0

            # Signal win rate
            signals = conn.execute("""
                SELECT outcome, COUNT(*) as cnt FROM signals
                WHERE outcome IS NOT NULL GROUP BY outcome
            """).fetchall()

        wins = sum(r['cnt'] for r in signals if r['outcome'] == 'WIN')
        losses = sum(r['cnt'] for r in signals if r['outcome'] == 'LOSS')
        total_closed = wins + losses
        win_rate = wins / total_closed * 100 if total_closed > 0 else 0

        # Monthly recurring revenue projection
        mrr = sum(TIER_PRICES[SubscriptionTier(t)] * tier_counts.get(t, 0)
                  for t in ['basic', 'pro', 'vip'])

        return {
            'subscribers': {
                'free':  tier_counts.get('free', 0),
                'basic': tier_counts.get('basic', 0),
                'pro':   tier_counts.get('pro', 0),
                'vip':   tier_counts.get('vip', 0),
                'total': sum(tier_counts.values())
            },
            'revenue': {
                'monthly_this_month': round(monthly_rev, 2),
                'mrr_projected':      round(mrr, 2),
                'arr_projected':      round(mrr * 12, 2),
                'total_all_time':     round(total_rev, 2),
            },
            'performance': {
                'signals_sent':  total_closed + wins + losses,
                'win_rate':      round(win_rate, 1),
                'total_wins':    wins,
                'total_losses':  losses,
            }
        }

    def send_renewal_reminders(self):
        """Send renewal reminders to expiring subscribers."""
        expiring = self.get_expiring_soon(days=3)
        for sub in expiring:
            tier_enum = SubscriptionTier(sub['tier'])
            price = TIER_PRICES[tier_enum]
            expires = sub['expires_at'][:10]
            msg = (
                f"⏰ <b>Subscription แจ้งเตือนหมดอายุ</b>\n\n"
                f"สวัสดีคุณ {sub['name']},\n"
                f"Subscription ของคุณ (<b>{sub['tier'].upper()}</b>) "
                f"จะหมดอายุในวันที่ {expires}\n\n"
                f"💳 ต่ออายุ: ${price}/เดือน\n"
                f"📩 ติดต่อต่ออายุ: @ClawGoldAdmin\n\n"
                f"อย่าพลาดสัญญาณทำเงินที่กำลังจะมาถึง! 🥇"
            )
            self._send(sub['chat_id'], msg)
            logger.info(f"Renewal reminder sent to {sub['name']} ({sub['chat_id']})")

    # ─────────────────────────────────────────────
    # Telegram Helpers
    # ─────────────────────────────────────────────

    def _send(self, chat_id: str, text: str) -> bool:
        if not self.bot_token:
            logger.warning(f"[SimMode] Signal to {chat_id}: {text[:60]}...")
            return True
        try:
            resp = requests.post(
                f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
                timeout=10
            )
            return resp.json().get("ok", False)
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
            return False
