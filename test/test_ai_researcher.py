"""
Unit Tests for AI Researcher Module
====================================
Tests for AIResearcher class and related functionality.
"""

import unittest
import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from ai_researcher import AIResearcher, AIResult


class TestAIResearcher(unittest.TestCase):
    """Test cases for AIResearcher class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.researcher = AIResearcher(cache_db=None, cache_ttl_hours=6)
    
    def test_initialization(self):
        """Test AIResearcher initialization."""
        self.assertIsNotNone(self.researcher.tools)
        self.assertIn('opencode', self.researcher.tools)
        self.assertIn('kilocode', self.researcher.tools)
        self.assertIn('gemini', self.researcher.tools)
        self.assertTrue(self.researcher.enable_fallback)
        self.assertEqual(self.researcher.max_retries, 2)
    
    def test_metrics_initialization(self):
        """Test metrics are initialized correctly."""
        metrics = self.researcher.get_metrics()
        self.assertIn('opencode', metrics)
        self.assertIn('kilocode', metrics)
        self.assertIn('gemini', metrics)
        
        for tool in ['opencode', 'kilocode', 'gemini']:
            self.assertEqual(metrics[tool]['total_calls'], 0)
            self.assertEqual(metrics[tool]['success_rate'], '0.0%')
    
    def test_update_metrics(self):
        """Test metrics update correctly."""
        # Simulate successful call
        self.researcher._update_metrics('opencode', True, 1.5)
        metrics = self.researcher.get_metrics()
        self.assertEqual(metrics['opencode']['total_calls'], 1)
        self.assertEqual(metrics['opencode']['successes'], 1)
        self.assertEqual(metrics['opencode']['success_rate'], '100.0%')
        
        # Simulate failed call
        self.researcher._update_metrics('opencode', False, 2.0)
        metrics = self.researcher.get_metrics()
        self.assertEqual(metrics['opencode']['total_calls'], 2)
        self.assertEqual(metrics['opencode']['failures'], 1)
        self.assertEqual(metrics['opencode']['success_rate'], '50.0%')
    
    def test_extract_confidence(self):
        """Test confidence extraction from text."""
        test_cases = [
            ("I am 85% confident", 0.85),
            ("confidence: 90%", 0.90),
            ("confidence is 75", 0.75),
            ("50% sure", 0.50),
            ("no confidence here", None),
        ]
        
        for text, expected in test_cases:
            result = self.researcher._extract_confidence(text)
            self.assertEqual(result, expected, f"Failed for: {text}")
    
    def test_extract_sentiment(self):
        """Test sentiment extraction from text."""
        test_cases = [
            ("The market is bullish and positive", "bullish"),
            ("Bearish trend with negative outlook", "bearish"),
            ("Mixed signals, sideways movement", "neutral"),
            ("Strong buy signal, uptrend forming", "bullish"),
            ("Sell now, downtrend confirmed", "bearish"),
        ]
        
        for text, expected in test_cases:
            result = self.researcher._extract_sentiment(text)
            self.assertEqual(result, expected, f"Failed for: {text}")
    
    @patch.object(AIResearcher, '_call_opencode')
    def test_research_single_success(self, mock_call):
        """Test successful research single call."""
        mock_call.return_value = "Bullish outlook with 80% confidence"
        
        result = self.researcher.research_single('opencode', 'test query', use_cache=False)
        
        self.assertIsInstance(result, AIResult)
        self.assertEqual(result.tool, 'opencode')
        self.assertEqual(result.query, 'test query')
        self.assertTrue(result.success)
        self.assertIsNone(result.error)
        self.assertEqual(result.confidence, 0.80)
    
    @patch.object(AIResearcher, '_call_opencode')
    def test_research_single_failure(self, mock_call):
        """Test failed research single call."""
        mock_call.return_value = "Error: CLI not found"
        
        result = self.researcher.research_single('opencode', 'test query', use_cache=False)
        
        self.assertIsInstance(result, AIResult)
        self.assertFalse(result.success)
        self.assertIsNotNone(result.error)
    
    @patch.object(AIResearcher, '_call_opencode')
    @patch.object(AIResearcher, '_call_kilocode')
    def test_fallback_mechanism(self, mock_kilo, mock_open):
        """Test fallback to other tools when primary fails."""
        # First tool fails, second succeeds
        mock_open.return_value = "Error: Connection timeout"
        mock_kilo.return_value = "Bullish with 75% confidence"
        
        result = self.researcher.research_single('opencode', 'test query', use_cache=False)
        
        # Should have tried fallback
        self.assertTrue(result.success)
        self.assertIn('Fallback', result.response)
    
    def test_unknown_tool(self):
        """Test handling of unknown tool."""
        result = self.researcher.research_single('unknown_tool', 'test query')
        
        self.assertFalse(result.success)
        self.assertIn('Unknown tool', result.error)
    
    def test_aggregate_results(self):
        """Test results aggregation."""
        results = [
            AIResult('opencode', 'test', 'Bullish outlook', True, 1.0, confidence=0.8),
            AIResult('kilocode', 'test', 'Positive trend', True, 1.2, confidence=0.75),
            AIResult('gemini', 'test', 'Error: timeout', False, 0.5, error='timeout'),
        ]
        
        aggregated = self.researcher.aggregate_results(results)
        
        self.assertIn('consensus_sentiment', aggregated)
        self.assertIn('tools_used', aggregated)
        self.assertEqual(len(aggregated['tools_used']), 2)  # Only successful ones
        self.assertAlmostEqual(aggregated['average_confidence'], 0.775, places=2)


class TestAIResult(unittest.TestCase):
    """Test cases for AIResult dataclass."""
    
    def test_creation(self):
        """Test AIResult creation."""
        result = AIResult(
            tool='opencode',
            query='test',
            response='Bullish',
            success=True,
            execution_time=1.5,
            confidence=0.8
        )
        
        self.assertEqual(result.tool, 'opencode')
        self.assertEqual(result.response, 'Bullish')
        self.assertTrue(result.success)
        self.assertEqual(result.execution_time, 1.5)
        self.assertEqual(result.confidence, 0.8)


if __name__ == '__main__':
    unittest.main()
