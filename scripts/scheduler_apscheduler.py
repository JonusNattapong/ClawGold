"""
APScheduler-based Task Scheduler
=================================

Replaces the custom scheduling implementation with APScheduler for:
- More reliable task execution
- Built-in persistence (SQLite)
- Better error handling
- Cleaner API

Phase 1: High Impact / Quick Wins
"""

import json
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass, asdict

from logger import get_logger

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger
    from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
    from apscheduler.jobstores.memory import MemoryJobStore
    from apscheduler.executors.pool import ThreadPoolExecutor
    from pytz import utc
except ImportError:
    raise ImportError("APScheduler not installed. Run: pip install apscheduler")

logger = get_logger(__name__)


@dataclass
class TaskConfig:
    """Task configuration."""
    job_id: str
    description: str
    enabled: bool = True
    task_type: str = "daily"  # daily, interval, cron
    hour: int = 9  # For daily tasks
    minute: int = 0
    interval_seconds: int = 3600  # For interval tasks
    cron_expr: str = ""  # For cron tasks (e.g., "0 9 * * MON-FRI")


class APSchedulerManager:
    """
    APScheduler-based task manager for ClawGold.
    
    Features:
    - Background task execution
    - SQLite persistence
    - Cron/interval/daily scheduling
    - Job result tracking
    - Error recovery
    """
    
    def __init__(self, db_path: str = "data/scheduler.db", use_persistence: bool = True):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.use_persistence = use_persistence
        self.scheduler: Optional[BackgroundScheduler] = None
        self.tasks: Dict[str, TaskConfig] = {}
        self._init_scheduler()
        
    def _init_scheduler(self):
        """Initialize APScheduler."""
        if self.use_persistence:
            jobstore_url = f"sqlite:///{self.db_path}"
            jobstores = {"default": SQLAlchemyJobStore(url=jobstore_url)}
        else:
            jobstores = {"default": MemoryJobStore()}
        
        executors = {
            "default": ThreadPoolExecutor(max_workers=4),
        }
        
        job_defaults = {
            "coalesce": True,  # Only run once even if multiple triggers fire
            "max_instances": 1,  # Only one instance per job
            "misfire_grace_time": 30,  # Allow 30s grace for misfired jobs
        }
        
        self.scheduler = BackgroundScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
            timezone=utc
        )
        
        logger.info("[APScheduler] Manager initialized with persistence=" + str(self.use_persistence))
    
    def add_task(self, job_id: str, func: Callable, task_config: TaskConfig):
        """
        Add a task to the scheduler.
        
        Args:
            job_id: Unique task ID
            func: Callable to execute
            task_config: TaskConfig with schedule details
        """
        if not task_config.enabled:
            logger.info(f"[APScheduler] Task {job_id} is disabled, skipping")
            return
        
        try:
            self.tasks[job_id] = task_config
            
            if task_config.task_type == "daily":
                trigger = CronTrigger(
                    hour=task_config.hour,
                    minute=task_config.minute,
                    timezone=utc
                )
            elif task_config.task_type == "interval":
                trigger = IntervalTrigger(
                    seconds=task_config.interval_seconds,
                    timezone=utc
                )
            elif task_config.task_type == "cron":
                trigger = CronTrigger.from_crontab(task_config.cron_expr, timezone=utc)
            else:
                raise ValueError(f"Unknown task_type: {task_config.task_type}")
            
            # Add job to scheduler
            job = self.scheduler.add_job(
                func,
                trigger,
                id=job_id,
                name=task_config.description,
                replace_existing=True,
                args=(),
                kwargs={},
            )
            
            logger.info(
                f"[APScheduler] Task added: {job_id} | {task_config.description} | "
                f"{task_config.task_type}"
            )
            
        except Exception as e:
            logger.error(f"[APScheduler] Failed to add task {job_id}: {e}")
    
    def remove_task(self, job_id: str):
        """Remove a task."""
        try:
            if self.scheduler and job_id in [job.id for job in self.scheduler.get_jobs()]:
                self.scheduler.remove_job(job_id)
                if job_id in self.tasks:
                    del self.tasks[job_id]
                logger.info(f"[APScheduler] Task removed: {job_id}")
        except Exception as e:
            logger.error(f"[APScheduler] Failed to remove task {job_id}: {e}")
    
    def enable_task(self, job_id: str):
        """Resume a paused task."""
        try:
            if self.scheduler:
                job = self.scheduler.get_job(job_id)
                if job:
                    job.resume()
                    if job_id in self.tasks:
                        self.tasks[job_id].enabled = True
                    logger.info(f"[APScheduler] Task enabled: {job_id}")
        except Exception as e:
            logger.error(f"[APScheduler] Failed to enable task {job_id}: {e}")
    
    def disable_task(self, job_id: str):
        """Pause a task without removing it."""
        try:
            if self.scheduler:
                job = self.scheduler.get_job(job_id)
                if job:
                    job.pause()
                    if job_id in self.tasks:
                        self.tasks[job_id].enabled = False
                    logger.info(f"[APScheduler] Task disabled: {job_id}")
        except Exception as e:
            logger.error(f"[APScheduler] Failed to disable task {job_id}: {e}")
    
    def get_task_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a specific task."""
        try:
            if self.scheduler:
                job = self.scheduler.get_job(job_id)
                if job:
                    return {
                        "id": job.id,
                        "name": job.name,
                        "next_run": str(job.next_run_time) if job.next_run_time else None,
                        "enabled": True,  # APScheduler doesn't have explicit enabled flag
                    }
        except Exception as e:
            logger.error(f"[APScheduler] Failed to get task status: {e}")
        return None
    
    def get_all_tasks(self) -> List[Dict[str, Any]]:
        """Get all scheduled tasks."""
        result = []
        try:
            if self.scheduler:
                for job in self.scheduler.get_jobs():
                    result.append({
                        "id": job.id,
                        "name": job.name,
                        "next_run": str(job.next_run_time) if job.next_run_time else None,
                        "enabled": True,
                    })
        except Exception as e:
            logger.error(f"[APScheduler] Failed to get all tasks: {e}")
        return result
    
    def start(self):
        """Start the scheduler."""
        try:
            if self.scheduler and not self.scheduler.running:
                self.scheduler.start()
                logger.info("[APScheduler] Scheduler started")
        except Exception as e:
            logger.error(f"[APScheduler] Failed to start scheduler: {e}")
    
    def stop(self):
        """Stop the scheduler."""
        try:
            if self.scheduler and self.scheduler.running:
                self.scheduler.shutdown()
                logger.info("[APScheduler] Scheduler stopped")
        except Exception as e:
            logger.error(f"[APScheduler] Failed to stop scheduler: {e}")
    
    def is_running(self) -> bool:
        """Check if scheduler is running."""
        return bool(self.scheduler and self.scheduler.running)


# Singleton manager
_scheduler_manager: Optional[APSchedulerManager] = None


def get_scheduler_manager() -> APSchedulerManager:
    """Get or create the singleton scheduler manager."""
    global _scheduler_manager
    if _scheduler_manager is None:
        _scheduler_manager = APSchedulerManager()
    return _scheduler_manager
