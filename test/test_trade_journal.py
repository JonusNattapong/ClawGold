"""
Unit tests for Trade Journal & Analytics.
"""

import sys
import tempfile
import unittest
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from trade_journal import TradeJournal, JournalEntry


class TestTradeJournal(unittest.TestCase):
    def setUp(self):
        fd, temp_path = tempfile.mkstemp(prefix="trade_journal_test_", suffix=".db")
        os.close(fd)
        self.db_path = temp_path
        self.journal = TradeJournal(db_path=self.db_path)

    def tearDown(self):
        self.journal = None
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_add_entry(self):
        entry_id = self.journal.add_entry(JournalEntry(
            action="BUY",
            symbol="XAUUSD",
            volume=0.1,
            price=2950.5,
            strategy="breakout",
            market_condition="trending",
            reason="Breakout above resistance",
            ai_research_snapshot={"summary": "Bullish momentum"},
            account_equity=10050.0,
        ))
        self.assertGreater(entry_id, 0)

    def test_analytics_and_equity_curve(self):
        self.journal.add_entry(JournalEntry(
            action="BUY",
            symbol="XAUUSD",
            volume=0.1,
            price=2950.0,
            strategy="breakout",
            market_condition="trending",
            reason="Entry",
            account_equity=10000.0,
        ))
        self.journal.add_entry(JournalEntry(
            action="CLOSE",
            symbol="XAUUSD",
            volume=0.0,
            price=2955.0,
            strategy="breakout",
            market_condition="trending",
            reason="Take profit",
            realized_pnl=50.0,
            account_equity=10050.0,
        ))
        self.journal.add_entry(JournalEntry(
            action="CLOSE",
            symbol="XAUUSD",
            volume=0.0,
            price=2948.0,
            strategy="mean_reversion",
            market_condition="ranging",
            reason="Stop loss",
            realized_pnl=-20.0,
            account_equity=10030.0,
        ))

        analytics = self.journal.get_analytics(days=7)
        self.assertEqual(analytics["total_closed"], 2)
        self.assertAlmostEqual(analytics["overall_win_rate"], 0.5, places=3)
        self.assertIn("breakout", analytics["win_rate_by_strategy"])
        self.assertIn("trending", analytics["win_rate_by_market_condition"])

        curve = self.journal.get_equity_curve(days=7)
        self.assertEqual(len(curve), 3)
        self.assertEqual(curve[-1]["equity"], 10030.0)


if __name__ == "__main__":
    unittest.main()

