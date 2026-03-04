"""
Tests for Agent Executor
========================
Unit tests for the AgentExecutor, SubAgentOrchestrator, and AgentScheduler.
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from datetime import datetime

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from agent_executor import AgentExecutor, AgentResult, AgentTool, AgentCapability


class TestAgentResult(unittest.TestCase):
    """Tests for AgentResult dataclass."""

    def test_to_dict(self):
        result = AgentResult(
            tool="opencode", task="test task",
            response="test response",
            success=True, execution_time=1.5,
        )
        d = result.to_dict()
        self.assertEqual(d['tool'], 'opencode')
        self.assertEqual(d['task'], 'test task')
        self.assertEqual(d['response'], 'test response')
        self.assertTrue(d['success'])
        self.assertEqual(d['execution_time'], 1.5)
        self.assertFalse(d['cached'])
        self.assertIsNotNone(d['timestamp'])

    def test_error_result(self):
        result = AgentResult(
            tool="gemini", task="fail task",
            response="", success=False,
            execution_time=0, error="Not installed",
        )
        self.assertFalse(result.success)
        self.assertEqual(result.error, "Not installed")


class TestAgentExecutor(unittest.TestCase):
    """Tests for AgentExecutor."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.cache_dir = os.path.join(self.tmpdir, "cache")
        self.db_path = os.path.join(self.tmpdir, "history.db")

    @patch('agent_executor.shutil.which')
    def test_discover_tools_none_available(self, mock_which):
        """When no CLI tools are installed, all tools should be unavailable."""
        mock_which.return_value = None
        executor = AgentExecutor(
            cache_dir=self.cache_dir, db_path=self.db_path,
        )
        available = executor.get_available_tools()
        self.assertEqual(len(available), 0)

    @patch('agent_executor.shutil.which')
    @patch('agent_executor.subprocess.run')
    def test_discover_tools_one_available(self, mock_subprocess, mock_which):
        """When one tool is installed, it should be discovered."""
        def which_side_effect(binary):
            if binary == 'gemini':
                return '/usr/bin/gemini'
            return None

        mock_which.side_effect = which_side_effect
        mock_subprocess.return_value = MagicMock(
            stdout='gemini 1.0.0', stderr='', returncode=0,
        )

        executor = AgentExecutor(
            cache_dir=self.cache_dir, db_path=self.db_path,
        )
        available = executor.get_available_tools()
        self.assertEqual(len(available), 1)
        self.assertEqual(available[0].tool, AgentTool.GEMINI)

    @patch('agent_executor.shutil.which')
    def test_run_unavailable_tool(self, mock_which):
        """Running a task on an unavailable tool returns error."""
        mock_which.return_value = None
        executor = AgentExecutor(
            cache_dir=self.cache_dir, db_path=self.db_path,
        )
        result = executor.run('opencode', 'test task')
        self.assertFalse(result.success)
        self.assertIn('not installed', result.error.lower())

    @patch('agent_executor.shutil.which')
    def test_run_unknown_tool(self, mock_which):
        """Running a task on an unknown tool returns error."""
        mock_which.return_value = None
        executor = AgentExecutor(
            cache_dir=self.cache_dir, db_path=self.db_path,
        )
        result = executor.run('nonexistent_tool', 'test')
        self.assertFalse(result.success)
        self.assertIn('Unknown tool', result.error)

    @patch('agent_executor.shutil.which')
    @patch('agent_executor.subprocess.run')
    def test_run_success(self, mock_subprocess, mock_which):
        """Successful execution returns response."""
        mock_which.return_value = '/usr/bin/gemini'
        mock_subprocess.return_value = MagicMock(
            stdout='Gold is bullish today', stderr='', returncode=0,
        )

        executor = AgentExecutor(
            cache_dir=self.cache_dir, db_path=self.db_path,
        )
        result = executor.run('gemini', 'gold outlook', use_cache=False)
        self.assertTrue(result.success)
        self.assertIn('bullish', result.response.lower())
        self.assertGreater(result.execution_time, 0)

    @patch('agent_executor.shutil.which')
    @patch('agent_executor.subprocess.run')
    def test_run_with_caching(self, mock_subprocess, mock_which):
        """Second call should return cached result."""
        mock_which.return_value = '/usr/bin/gemini'
        mock_subprocess.return_value = MagicMock(
            stdout='Gold is bullish', stderr='', returncode=0,
        )

        executor = AgentExecutor(
            cache_dir=self.cache_dir, db_path=self.db_path,
        )
        # First call
        r1 = executor.run('gemini', 'gold test query', use_cache=True)
        self.assertTrue(r1.success)
        self.assertFalse(r1.cached)

        # Second call — should be cached
        r2 = executor.run('gemini', 'gold test query', use_cache=True)
        self.assertTrue(r2.success)
        self.assertTrue(r2.cached)

    @patch('agent_executor.shutil.which')
    @patch('agent_executor.subprocess.run')
    def test_metrics_tracking(self, mock_subprocess, mock_which):
        """Metrics should update after runs."""
        mock_which.return_value = '/usr/bin/gemini'
        mock_subprocess.return_value = MagicMock(
            stdout='response', stderr='', returncode=0,
        )

        executor = AgentExecutor(
            cache_dir=self.cache_dir, db_path=self.db_path,
        )
        executor.run('gemini', 'test 1', use_cache=False)
        executor.run('gemini', 'test 2', use_cache=False)

        metrics = executor.get_metrics()
        self.assertEqual(metrics['gemini']['total_calls'], 2)
        self.assertEqual(metrics['gemini']['successes'], 2)

    @patch('agent_executor.shutil.which')
    @patch('agent_executor.subprocess.run')
    def test_history_recording(self, mock_subprocess, mock_which):
        """Execution should be recorded in history DB."""
        mock_which.return_value = '/usr/bin/gemini'
        mock_subprocess.return_value = MagicMock(
            stdout='history test', stderr='', returncode=0,
        )

        executor = AgentExecutor(
            cache_dir=self.cache_dir, db_path=self.db_path,
        )
        executor.run('gemini', 'history test task', use_cache=False)

        history = executor.get_history(limit=5)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]['tool'], 'gemini')
        self.assertIn('history test task', history[0]['task'])

    def test_extract_sentiment(self):
        """Sentiment extraction should work correctly."""
        self.assertEqual(
            AgentExecutor._extract_sentiment("Gold is bullish with strong uptrend"),
            'bullish'
        )
        self.assertEqual(
            AgentExecutor._extract_sentiment("Market is bearish, decline expected"),
            'bearish'
        )
        self.assertEqual(
            AgentExecutor._extract_sentiment("Market is stable and calm"),
            'neutral'
        )

    @patch('agent_executor.shutil.which')
    @patch('agent_executor.subprocess.run')
    def test_consensus(self, mock_subprocess, mock_which):
        """Consensus should aggregate results from multiple tools."""
        # Make all tools available
        mock_which.return_value = '/usr/bin/tool'
        mock_subprocess.return_value = MagicMock(
            stdout='Gold is bullish with strong momentum', stderr='', returncode=0,
        )

        executor = AgentExecutor(
            cache_dir=self.cache_dir, db_path=self.db_path,
        )
        result = executor.consensus('gold outlook')
        self.assertTrue(result['success'])
        self.assertIn('consensus_sentiment', result)
        self.assertGreater(len(result['tools_used']), 0)

    @patch('agent_executor.shutil.which')
    def test_run_best_no_tools(self, mock_which):
        """run_best with no tools available returns error."""
        mock_which.return_value = None
        executor = AgentExecutor(
            cache_dir=self.cache_dir, db_path=self.db_path,
        )
        result = executor.run_best('test')
        self.assertFalse(result.success)
        self.assertIn('No AI CLI tools', result.error)

    @patch('agent_executor.shutil.which')
    def test_get_all_tools(self, mock_which):
        """get_all_tools should return all 4 tools."""
        mock_which.return_value = None
        executor = AgentExecutor(
            cache_dir=self.cache_dir, db_path=self.db_path,
        )
        all_tools = executor.get_all_tools()
        self.assertEqual(len(all_tools), 4)
        names = [t.tool.value for t in all_tools]
        self.assertIn('opencode', names)
        self.assertIn('gemini', names)
        self.assertIn('codex', names)
        self.assertIn('claude', names)


class TestSubAgentOrchestrator(unittest.TestCase):
    """Tests for SubAgentOrchestrator."""

    @patch('agent_executor.shutil.which')
    @patch('agent_executor.subprocess.run')
    def test_ask(self, mock_subprocess, mock_which):
        """ask() should dispatch correctly."""
        mock_which.return_value = '/usr/bin/gemini'
        mock_subprocess.return_value = MagicMock(
            stdout='response text', stderr='', returncode=0,
        )
        from sub_agent import SubAgentOrchestrator
        orch = SubAgentOrchestrator()
        result = orch.ask("What is gold price?")
        self.assertTrue(result['success'])
        self.assertEqual(result['role'], 'general')
        self.assertIn('response text', result['response'])

    @patch('agent_executor.shutil.which')
    @patch('agent_executor.subprocess.run')
    def test_research(self, mock_subprocess, mock_which):
        """research() should produce researcher role output."""
        mock_which.return_value = '/usr/bin/gemini'
        mock_subprocess.return_value = MagicMock(
            stdout='Gold research findings', stderr='', returncode=0,
        )
        from sub_agent import SubAgentOrchestrator
        orch = SubAgentOrchestrator()
        result = orch.research("gold outlook today")
        self.assertTrue(result['success'])
        self.assertEqual(result['role'], 'researcher')

    @patch('agent_executor.shutil.which')
    @patch('agent_executor.subprocess.run')
    def test_analyze(self, mock_subprocess, mock_which):
        mock_which.return_value = '/usr/bin/gemini'
        mock_subprocess.return_value = MagicMock(
            stdout='Support at 2900, Resistance at 3000', stderr='', returncode=0,
        )
        from sub_agent import SubAgentOrchestrator
        orch = SubAgentOrchestrator()
        result = orch.analyze(symbol="XAUUSD", timeframe="H4")
        self.assertEqual(result['role'], 'analyst')

    @patch('agent_executor.shutil.which')
    @patch('agent_executor.subprocess.run')
    def test_plan(self, mock_subprocess, mock_which):
        mock_which.return_value = '/usr/bin/gemini'
        mock_subprocess.return_value = MagicMock(
            stdout='Trading plan for today', stderr='', returncode=0,
        )
        from sub_agent import SubAgentOrchestrator
        orch = SubAgentOrchestrator()
        result = orch.plan(symbol="XAUUSD", balance=10000)
        self.assertEqual(result['role'], 'strategist')

    @patch('agent_executor.shutil.which')
    @patch('agent_executor.subprocess.run')
    def test_task_log(self, mock_subprocess, mock_which):
        """Task log should track dispatched tasks."""
        mock_which.return_value = '/usr/bin/gemini'
        mock_subprocess.return_value = MagicMock(
            stdout='response', stderr='', returncode=0,
        )
        from sub_agent import SubAgentOrchestrator
        orch = SubAgentOrchestrator()
        orch.ask("test 1")
        orch.research("test 2")
        log = orch.get_task_log()
        self.assertEqual(len(log), 2)
        self.assertEqual(log[0]['role'], 'general')
        self.assertEqual(log[1]['role'], 'researcher')

    def test_get_available_roles(self):
        """Should return all 5 roles."""
        from sub_agent import SubAgentOrchestrator
        with patch('agent_executor.shutil.which', return_value=None):
            orch = SubAgentOrchestrator()
        roles = orch.get_available_roles()
        self.assertEqual(len(roles), 5)
        role_names = [r['role'] for r in roles]
        self.assertIn('researcher', role_names)
        self.assertIn('analyst', role_names)
        self.assertIn('strategist', role_names)
        self.assertIn('monitor', role_names)
        self.assertIn('general', role_names)

    @patch('sub_agent.AgentLangGraphOrchestrator.is_available', return_value=True)
    @patch('sub_agent.AgentLangGraphOrchestrator.run_daily_routine')
    @patch('agent_executor.shutil.which', return_value=None)
    def test_daily_routine_langgraph_path(self, _mock_which, mock_run_graph, _mock_available):
        """daily_routine should use LangGraph path when enabled and available."""
        from sub_agent import SubAgentOrchestrator

        mock_run_graph.return_value = {
            'success': True,
            'orchestration': 'langgraph',
            'steps': {},
        }
        orch = SubAgentOrchestrator(use_langgraph=True)
        result = orch.daily_routine(symbol='XAUUSD')

        self.assertTrue(result['success'])
        self.assertEqual(result['orchestration'], 'langgraph')


class TestAgentExecutorLangGraphBridge(unittest.TestCase):
    """Tests for AgentExecutor bridge method to LangGraph flow."""

    @patch('agent_executor.shutil.which', return_value=None)
    @patch('sub_agent.SubAgentOrchestrator')
    def test_run_stateful_daily_flow_bridge(self, mock_sub_orch, _mock_which):
        from agent_executor import AgentExecutor

        instance = mock_sub_orch.return_value
        instance.daily_routine.return_value = {
            'success': True,
            'orchestration': 'langgraph',
            'symbol': 'XAUUSD',
        }

        executor = AgentExecutor()
        result = executor.run_stateful_daily_flow(symbol='XAUUSD', preferred_tool='gemini')

        self.assertTrue(result['success'])
        self.assertEqual(result['orchestration'], 'langgraph')
        instance.daily_routine.assert_called_once()


class TestAgentScheduler(unittest.TestCase):
    """Tests for AgentScheduler."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "scheduler.db")

    def test_default_tasks_created(self):
        """Scheduler should initialize with default tasks."""
        from agent_scheduler import AgentScheduler
        scheduler = AgentScheduler(db_path=self.db_path)
        tasks = scheduler.list_tasks()
        self.assertGreater(len(tasks), 0)
        names = [t['name'] for t in tasks]
        self.assertIn('morning_research', names)
        self.assertIn('daily_summary', names)

    def test_add_task(self):
        """Should be able to add a new task."""
        from agent_scheduler import AgentScheduler
        scheduler = AgentScheduler(db_path=self.db_path)
        initial_count = len(scheduler.list_tasks())

        scheduler.add_task(
            name='custom_test',
            schedule_type='daily',
            schedule_value='09:00',
            task_type='market_research',
            task_params={'query': 'test query'},
        )

        tasks = scheduler.list_tasks()
        self.assertEqual(len(tasks), initial_count + 1)
        custom = [t for t in tasks if t['name'] == 'custom_test'][0]
        self.assertEqual(custom['task'], 'market_research')

    def test_remove_task(self):
        """Should be able to remove a task."""
        from agent_scheduler import AgentScheduler
        scheduler = AgentScheduler(db_path=self.db_path)

        scheduler.add_task('to_remove', 'interval', '60', 'news_digest')
        self.assertTrue(scheduler.remove_task('to_remove'))
        self.assertFalse(scheduler.remove_task('nonexistent'))

    def test_enable_disable_task(self):
        """Should be able to toggle task enabled state."""
        from agent_scheduler import AgentScheduler
        scheduler = AgentScheduler(db_path=self.db_path)

        # Disable morning_research
        scheduler.disable_task('morning_research')
        tasks = scheduler.list_tasks()
        mr = [t for t in tasks if t['name'] == 'morning_research'][0]
        self.assertFalse(mr['enabled'])

        # Re-enable
        scheduler.enable_task('morning_research')
        tasks = scheduler.list_tasks()
        mr = [t for t in tasks if t['name'] == 'morning_research'][0]
        self.assertTrue(mr['enabled'])

    def test_persistence(self):
        """Tasks should persist across scheduler instances."""
        from agent_scheduler import AgentScheduler

        s1 = AgentScheduler(db_path=self.db_path)
        s1.add_task('persist_test', 'daily', '10:00', 'news_digest')
        del s1

        s2 = AgentScheduler(db_path=self.db_path)
        tasks = s2.list_tasks()
        names = [t['name'] for t in tasks]
        self.assertIn('persist_test', names)


if __name__ == '__main__':
    unittest.main()
