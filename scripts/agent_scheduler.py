"""
Agent Scheduler
===============
Background scheduler for automated/periodic trading tasks.
Runs sub-agent workflows on a schedule (daily analysis, periodic monitoring, etc.)

Now powered by APScheduler for robust, persistent background task execution.

Usage:
    from agent_scheduler import AgentScheduler
    
    scheduler = AgentScheduler()
    scheduler.add_daily("morning_routine", "07:00", task_fn)
    scheduler.add_interval("position_check", 300, task_fn)  # every 5 min
    scheduler.start()  # blocking
"""

import json
import time
import sqlite3
from contextlib import contextmanager
from typing import Callable, Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from enum import Enum

from logger import get_logger
from rich_logger import get_rich_logger
from scheduler_apscheduler import get_scheduler_manager, TaskConfig

logger = get_logger(__name__)
rich_logger = get_rich_logger()


class ScheduleType(Enum):
    DAILY = "daily"         # Run at specific time each day
    INTERVAL = "interval"   # Run every N seconds
    CRON = "cron"           # Simple cron-like (hh:mm on weekdays)


@dataclass
class ScheduledTask:
    """A scheduled task definition."""
    name: str
    schedule_type: ScheduleType
    schedule_value: str  # "07:00" for daily, "300" for interval, "MON-FRI 08:00" for cron
    task_type: str       # which sub-agent task to run
    task_params: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    last_run: Optional[str] = None
    next_run: Optional[str] = None
    run_count: int = 0
    last_error: Optional[str] = None


# ---------------------------------------------------------------------------
# Pre-built task definitions
# ---------------------------------------------------------------------------

DEFAULT_TASKS = [
    ScheduledTask(
        name="morning_research",
        schedule_type=ScheduleType.DAILY,
        schedule_value="07:00",
        task_type="news_digest",
        task_params={'topics': 'XAUUSD gold overnight moves, Asia session, key economic data today'},
    ),
    ScheduledTask(
        name="morning_plan",
        schedule_type=ScheduleType.DAILY,
        schedule_value="07:30",
        task_type="trading_plan",
        task_params={'symbol': 'XAUUSD'},
    ),
    ScheduledTask(
        name="midday_analysis",
        schedule_type=ScheduleType.DAILY,
        schedule_value="12:00",
        task_type="technical_analysis",
        task_params={'symbol': 'XAUUSD', 'timeframe': 'H1'},
    ),
    ScheduledTask(
        name="position_check",
        schedule_type=ScheduleType.INTERVAL,
        schedule_value="600",  # every 10 minutes
        task_type="position_review",
        task_params={},
    ),
    ScheduledTask(
        name="afternoon_risk",
        schedule_type=ScheduleType.DAILY,
        schedule_value="15:00",
        task_type="risk_assessment",
        task_params={},
    ),
    ScheduledTask(
        name="daily_summary",
        schedule_type=ScheduleType.DAILY,
        schedule_value="17:00",
        task_type="daily_summary",
        task_params={},
    ),
    ScheduledTask(
        name="evening_research",
        schedule_type=ScheduleType.DAILY,
        schedule_value="20:00",
        task_type="market_research",
        task_params={'query': 'Gold XAUUSD: US session recap, after-hours developments, tomorrow outlook'},
    ),
]


class AgentScheduler:
    """
    Scheduler for running sub-agent tasks automatically.
    
    Uses APScheduler backend for robust, persistent background execution.
    
    Supports:
        - Daily tasks at specific times (e.g., morning research at 07:00)
        - Interval tasks (e.g., position check every 10 minutes)
        - Weekday-only cron-like schedules
    """

    def __init__(self, db_path: str = "data/agent_scheduler.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

        self.tasks: Dict[str, ScheduledTask] = {}
        self._running = False
        
        # Use APScheduler for the heavy lifting
        self.ap_scheduler = get_scheduler_manager()

        # Load saved tasks or use defaults
        self._load_tasks()

    @contextmanager
    def _connect(self):
        """Context manager that properly closes the SQLite connection."""
        conn = sqlite3.connect(str(self.db_path))
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS scheduled_tasks (
                    name TEXT PRIMARY KEY,
                    schedule_type TEXT NOT NULL,
                    schedule_value TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    task_params TEXT DEFAULT '{}',
                    enabled INTEGER DEFAULT 1,
                    last_run TEXT,
                    run_count INTEGER DEFAULT 0,
                    last_error TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS schedule_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_name TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    success INTEGER,
                    response_preview TEXT,
                    error TEXT,
                    execution_time REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def _load_tasks(self):
        """Load tasks from DB or initialize defaults."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM scheduled_tasks").fetchall()

        if rows:
            for row in rows:
                self.tasks[row['name']] = ScheduledTask(
                    name=row['name'],
                    schedule_type=ScheduleType(row['schedule_type']),
                    schedule_value=row['schedule_value'],
                    task_type=row['task_type'],
                    task_params=json.loads(row['task_params'] or '{}'),
                    enabled=bool(row['enabled']),
                    last_run=row['last_run'],
                    run_count=row['run_count'] or 0,
                    last_error=row['last_error'],
                )
        else:
            # Initialize with defaults
            for task in DEFAULT_TASKS:
                self.tasks[task.name] = task
                self._save_task(task)

    def _save_task(self, task: ScheduledTask):
        with self._connect() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO scheduled_tasks 
                (name, schedule_type, schedule_value, task_type, task_params, enabled, last_run, run_count, last_error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                task.name, task.schedule_type.value, task.schedule_value,
                task.task_type, json.dumps(task.task_params),
                1 if task.enabled else 0, task.last_run,
                task.run_count, task.last_error,
            ))
            conn.commit()

    def _log_run(self, task_name: str, task_type: str,
                 success: bool, response_preview: str = "",
                 error: str = "", execution_time: float = 0):
        try:
            with self._connect() as conn:
                conn.execute("""
                    INSERT INTO schedule_log (task_name, task_type, success, response_preview, error, execution_time)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (task_name, task_type, 1 if success else 0,
                      response_preview[:500], error, execution_time))
                conn.commit()
        except Exception as e:
            logger.debug(f"Log write failed: {e}")

    # ------------------------------------------------------------------
    # Task management
    # ------------------------------------------------------------------

    def add_task(self, name: str, schedule_type: str, schedule_value: str,
                 task_type: str, task_params: Optional[Dict] = None) -> ScheduledTask:
        """Add a new scheduled task."""
        task = ScheduledTask(
            name=name,
            schedule_type=ScheduleType(schedule_type),
            schedule_value=schedule_value,
            task_type=task_type,
            task_params=task_params or {},
        )
        self.tasks[name] = task
        self._save_task(task)
        logger.info(f"Added scheduled task: {name} ({schedule_type} @ {schedule_value})")
        return task

    def remove_task(self, name: str) -> bool:
        if name in self.tasks:
            del self.tasks[name]
            with self._connect() as conn:
                conn.execute("DELETE FROM scheduled_tasks WHERE name = ?", (name,))
                conn.commit()
            return True
        return False

    def enable_task(self, name: str) -> bool:
        if name in self.tasks:
            self.tasks[name].enabled = True
            self._save_task(self.tasks[name])
            return True
        return False

    def disable_task(self, name: str) -> bool:
        if name in self.tasks:
            self.tasks[name].enabled = False
            self._save_task(self.tasks[name])
            return True
        return False

    def list_tasks(self) -> List[Dict]:
        """List all scheduled tasks."""
        result = []
        for task in self.tasks.values():
            result.append({
                'name': task.name,
                'type': task.schedule_type.value,
                'schedule': task.schedule_value,
                'task': task.task_type,
                'enabled': task.enabled,
                'last_run': task.last_run or 'never',
                'run_count': task.run_count,
                'last_error': task.last_error,
            })
        return result

    def get_log(self, limit: int = 20) -> List[Dict]:
        """Get recent schedule execution log."""
        try:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute("""
                    SELECT * FROM schedule_log
                    ORDER BY created_at DESC LIMIT ?
                """, (limit,)).fetchall()
                return [dict(r) for r in rows]
        except Exception:
            return []

    # ------------------------------------------------------------------
    # Scheduling logic
    # ------------------------------------------------------------------

    def run_once(self):
        """Run all due tasks immediately (for backward compatibility)."""
        for task in self.tasks.values():
            if task.enabled:
                self._execute_task(task)

    def start(self, blocking: bool = True):
        """
        Start the scheduler.
        
        Args:
            blocking: If True, runs in foreground. If False, runs in background.
        
        Note: With APScheduler backend, this runs persistently regardless of blocking mode.
        """
        self._running = True
        
        rich_logger.panel("🦞 Agent Scheduler Starting", title="Scheduler", style="blue")
        
        # Register all enabled tasks with APScheduler
        for task in self.tasks.values():
            if task.enabled:
                self._register_task_with_apscheduler(task)
        
        # Start the APScheduler instance
        self.ap_scheduler.start()
        
        self._print_schedule()
        
        if blocking:
            rich_logger.info("Scheduler running in foreground (Ctrl+C to stop)")
            try:
                import threading
                import signal
                
                def handler(sig, frame):
                    self.stop()
                
                signal.signal(signal.SIGINT, handler)
                # Keep the main thread alive
                while self._running:
                    time.sleep(1)
            except KeyboardInterrupt:
                self.stop()
        else:
            rich_logger.info("Scheduler running in background")

    def _register_task_with_apscheduler(self, task: ScheduledTask):
        """Register a ScheduledTask with the APScheduler backend."""
        # Create a wrapper function that calls _execute_task
        def task_wrapper():
            self._execute_task(task)
        
        # Create TaskConfig based on schedule type
        task_config = TaskConfig(
            job_id=task.name,
            description=f"{task.task_type}: {task.name}",
            enabled=task.enabled,
            task_type=task.schedule_type.value,
        )
        
        if task.schedule_type == ScheduleType.DAILY:
            try:
                hour, minute = map(int, task.schedule_value.split(':'))
                task_config.hour = hour
                task_config.minute = minute
            except ValueError:
                rich_logger.warning(f"Invalid daily schedule: {task.schedule_value}")
                return
        
        elif task.schedule_type == ScheduleType.INTERVAL:
            try:
                interval_secs = int(task.schedule_value)
                task_config.interval_seconds = interval_secs
            except ValueError:
                rich_logger.warning(f"Invalid interval: {task.schedule_value}")
                return
        
        elif task.schedule_type == ScheduleType.CRON:
            # Convert agent_scheduler cron format to apscheduler cron
            # Format: "MON-FRI HH:MM" → apscheduler format
            try:
                parts = task.schedule_value.split()
                if len(parts) == 2:
                    days_str, time_str = parts
                    hour, minute = map(int, time_str.split(':'))
                    task_config.hour = hour
                    task_config.minute = minute
                    task_config.cron_expr = f"0 {minute} {hour} * * {days_str}"
                    task_config.task_type = "cron"
            except ValueError:
                rich_logger.warning(f"Invalid cron schedule: {task.schedule_value}")
                return
        
        # Add to APScheduler
        try:
            self.ap_scheduler.add_task(task.name, task_wrapper, task_config)
            rich_logger.info(f"✓ Task {task.name} registered with APScheduler")
        except Exception as e:
            rich_logger.error(f"Failed to register {task.name}: {e}")

    def _execute_task(self, task: ScheduledTask):
        """Execute a scheduled task using SubAgentOrchestrator."""
        from sub_agent import SubAgentOrchestrator

        rich_logger.info(f"[Scheduler] Executing: {task.name} ({task.task_type})")
        start = time.time()

        try:
            orch = SubAgentOrchestrator()
            result = None

            # Map task_type to orchestrator method
            if task.task_type == 'news_digest':
                result = orch.news_digest(**task.task_params)
            elif task.task_type == 'trading_plan':
                result = orch.plan(**task.task_params)
            elif task.task_type == 'technical_analysis':
                result = orch.analyze(**task.task_params)
            elif task.task_type == 'position_review':
                result = orch.review_positions(**task.task_params)
            elif task.task_type == 'risk_assessment':
                result = orch.assess_risk(**task.task_params)
            elif task.task_type == 'daily_summary':
                result = orch.daily_summary(**task.task_params)
            elif task.task_type == 'market_research':
                query = task.task_params.get('query', 'XAUUSD gold market analysis')
                result = orch.research(query)
            elif task.task_type == 'daily_routine':
                result = orch.daily_routine(**task.task_params)
            else:
                # Generic ask
                result = orch.ask(task.task_params.get('task', task.task_type))

            elapsed = time.time() - start
            success = result.get('success', False) if result else False

            task.last_run = datetime.now().isoformat()
            task.run_count += 1
            task.last_error = None if success else result.get('error', 'Unknown')
            self._save_task(task)

            preview = result.get('response', '')[:300] if result else ''
            self._log_run(task.name, task.task_type, success, preview,
                          task.last_error or '', elapsed)

            # Send notification if configured
            self._notify_result(task, result, success)

            if success:
                rich_logger.success(f"✓ {task.name} completed in {elapsed:.1f}s")
            else:
                rich_logger.failure(f"✗ {task.name} failed in {elapsed:.1f}s")

        except Exception as e:
            elapsed = time.time() - start
            task.last_run = datetime.now().isoformat()
            task.run_count += 1
            task.last_error = str(e)
            self._save_task(task)
            self._log_run(task.name, task.task_type, False, '', str(e), elapsed)
            rich_logger.error(f"[Scheduler] {task.name} failed: {e}")

    def _notify_result(self, task: ScheduledTask, result: Optional[Dict], success: bool):
        """Send Telegram notification for task completion."""
        try:
            from notifier import get_notifier
            notifier = get_notifier()
            if not notifier.enabled:
                return

            if success and result:
                text = result.get('response', '')[:500]
                msg = f"🦞 <b>Scheduled Task: {task.name}</b>\n\n{text}"
            else:
                msg = f"⚠️ <b>Scheduled Task Failed: {task.name}</b>\nError: {task.last_error}"

            notifier._send_message(msg)
        except Exception:
            pass  # Notification is best-effort

    def stop(self):
        """Stop the scheduler."""
        self._running = False
        self.ap_scheduler.stop()
        rich_logger.info("✓ Scheduler stopped")

    def _print_schedule(self):
        """Print the current schedule to console."""
        print(f"\n{'='*70}")
        print(f"🦞 ClawGold Agent Scheduler")
        print(f"{'='*70}")
        print(f"{'Name':<25} {'Type':<10} {'Schedule':<15} {'Task':<20} {'Status':<8}")
        print(f"{'-'*70}")
        for task in self.tasks.values():
            status = "ON" if task.enabled else "OFF"
            print(f"{task.name:<25} {task.schedule_type.value:<10} "
                  f"{task.schedule_value:<15} {task.task_type:<20} {status:<8}")
        print(f"{'='*70}")
        print(f"Checking every 30 seconds. Press Ctrl+C to stop.\n")

    @property
    def is_running(self) -> bool:
        return self._running
