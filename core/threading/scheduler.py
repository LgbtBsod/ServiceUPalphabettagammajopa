"""
Task Scheduler.
Provides scheduled task execution with support for cron-like scheduling.
"""

import threading
import time
import logging
from typing import Callable, Any, Optional, Dict, List
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import heapq


logger = logging.getLogger(__name__)


class ScheduleType(Enum):
    """Type of schedule."""
    ONCE = "once"
    INTERVAL = "interval"
    CRON = "cron"  # Simplified cron support


@dataclass
class ScheduledTask:
    """Represents a scheduled task."""
    id: str
    func: Callable[..., Any]
    args: tuple = field(default_factory=tuple)
    kwargs: Dict[str, Any] = field(default_factory=dict)
    schedule_type: ScheduleType = ScheduleType.ONCE
    next_run: datetime = field(default_factory=datetime.now)
    interval_seconds: Optional[int] = None
    cron_expression: Optional[str] = None  # Simplified: "minute hour day month weekday"
    enabled: bool = True
    run_count: int = 0
    last_run: Optional[datetime] = None
    last_error: Optional[Exception] = None
    
    def __lt__(self, other: "ScheduledTask") -> bool:
        """Compare by next_run time for heap operations."""
        return self.next_run < other.next_run


class TaskScheduler:
    """
    Task scheduler for executing tasks at specific times or intervals.
    
    Features:
    - One-time scheduled execution
    - Periodic interval-based execution
    - Simplified cron-like scheduling
    - Thread-safe operations
    - Graceful shutdown
    """
    
    def __init__(self, name: str = "TaskScheduler"):
        self.name = name
        self._tasks: Dict[str, ScheduledTask] = {}
        self._heap: List[ScheduledTask] = []
        self._lock = threading.RLock()
        self._shutdown = False
        self._thread: Optional[threading.Thread] = None
        self._wake_event = threading.Event()
        
        logger.info(f"{name} initialized")
    
    def start(self):
        """Start the scheduler thread."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                logger.warning(f"{self.name} already running")
                return
            
            self._shutdown = False
            self._thread = threading.Thread(
                target=self._scheduler_loop,
                name=f"{self.name}-Thread",
                daemon=True,
            )
            self._thread.start()
            logger.info(f"{self.name} started")
    
    def stop(self, wait: bool = True) -> None:
        """Stop the scheduler."""
        logger.info(f"Stopping {self.name}...")
        self._shutdown = True
        self._wake_event.set()
        
        if wait and self._thread:
            self._thread.join(timeout=5.0)
            self._thread = None
        
        logger.info(f"{self.name} stopped")
    
    def schedule_once(
        self,
        task_id: str,
        func: Callable[..., Any],
        run_at: datetime,
        *args: Any,
        **kwargs: Any,
    ) -> bool:
        """
        Schedule a task to run once at a specific time.
        
        Args:
            task_id: Unique identifier for the task
            func: Callable to execute
            run_at: When to run the task
            *args: Positional arguments for the callable
            **kwargs: Keyword arguments for the callable
            
        Returns:
            True if scheduled successfully, False otherwise
        """
        return self._schedule_task(
            task_id=task_id,
            func=func,
            args=args,
            kwargs=kwargs,
            schedule_type=ScheduleType.ONCE,
            next_run=run_at,
        )
    
    def schedule_interval(
        self,
        task_id: str,
        func: Callable[..., Any],
        interval_seconds: int,
        start_immediately: bool = False,
        *args: Any,
        **kwargs: Any,
    ) -> bool:
        """
        Schedule a task to run at regular intervals.
        
        Args:
            task_id: Unique identifier for the task
            func: Callable to execute
            interval_seconds: Interval between executions in seconds
            start_immediately: Whether to run immediately on first schedule
            *args: Positional arguments for the callable
            **kwargs: Keyword arguments for the callable
            
        Returns:
            True if scheduled successfully, False otherwise
        """
        next_run = datetime.now() if start_immediately else datetime.now() + timedelta(seconds=interval_seconds)
        
        return self._schedule_task(
            task_id=task_id,
            func=func,
            args=args,
            kwargs=kwargs,
            schedule_type=ScheduleType.INTERVAL,
            next_run=next_run,
            interval_seconds=interval_seconds,
        )
    
    def _schedule_task(
        self,
        task_id: str,
        func: Callable[..., Any],
        args: tuple,
        kwargs: Dict[str, Any],
        schedule_type: ScheduleType,
        next_run: datetime,
        interval_seconds: Optional[int] = None,
    ) -> bool:
        """Internal method to schedule a task."""
        with self._lock:
            if task_id in self._tasks:
                logger.warning(f"Scheduled task '{task_id}' already exists")
                return False
            
            task = ScheduledTask(
                id=task_id,
                func=func,
                args=args,
                kwargs=kwargs,
                schedule_type=schedule_type,
                next_run=next_run,
                interval_seconds=interval_seconds,
            )
            
            self._tasks[task_id] = task
            heapq.heappush(self._heap, task)
            
            self._wake_event.set()  # Wake up scheduler to re-evaluate
            logger.info(f"Scheduled task '{task_id}' for {next_run}")
            return True
    
    def cancel(self, task_id: str) -> bool:
        """
        Cancel a scheduled task.
        
        Args:
            task_id: ID of task to cancel
            
        Returns:
            True if cancelled, False if not found
        """
        with self._lock:
            if task_id not in self._tasks:
                return False
            
            self._tasks[task_id].enabled = False
            # Remove from heap (will be skipped in scheduler loop)
            logger.info(f"Cancelled scheduled task '{task_id}'")
            return True
    
    def _scheduler_loop(self):
        """Main scheduler loop."""
        while not self._shutdown:
            try:
                now = datetime.now()
                tasks_to_run = []
                
                with self._lock:
                    # Collect all tasks that should run now
                    while self._heap and self._heap[0].next_run <= now:
                        task = heapq.heappop(self._heap)
                        if task.enabled:
                            tasks_to_run.append(task)
                        elif task.schedule_type == ScheduleType.INTERVAL:
                            # Re-schedule disabled interval tasks
                            task.next_run = now + timedelta(seconds=task.interval_seconds or 0)
                            heapq.heappush(self._heap, task)
                
                # Execute collected tasks outside lock
                for task in tasks_to_run:
                    self._execute_task(task)
                
                # Calculate sleep time until next task
                with self._lock:
                    if self._heap:
                        next_run = self._heap[0].next_run
                        sleep_seconds = max(0, (next_run - datetime.now()).total_seconds())
                    else:
                        sleep_seconds = 1.0  # Default check interval
                
                # Wait for wake event or timeout
                self._wake_event.wait(timeout=min(sleep_seconds, 1.0))
                self._wake_event.clear()
                
            except Exception as e:
                logger.error(f"{self.name} error: {e}", exc_info=True)
                time.sleep(1.0)
    
    def _execute_task(self, task: ScheduledTask):
        """Execute a scheduled task."""
        try:
            logger.debug(f"Executing scheduled task '{task.id}'")
            task.func(*task.args, **task.kwargs)
            
            with self._lock:
                task.run_count += 1
                task.last_run = datetime.now()
                
                # Re-schedule if interval-based
                if task.schedule_type == ScheduleType.INTERVAL and task.interval_seconds:
                    task.next_run = datetime.now() + timedelta(seconds=task.interval_seconds)
                    heapq.heappush(self._heap, task)
                    
        except Exception as e:
            logger.error(f"Scheduled task '{task.id}' failed: {e}", exc_info=True)
            with self._lock:
                task.last_error = e
                
                # Still re-schedule interval tasks even on error
                if task.schedule_type == ScheduleType.INTERVAL and task.interval_seconds:
                    task.next_run = datetime.now() + timedelta(seconds=task.interval_seconds)
                    heapq.heappush(self._heap, task)
    
    def get_task_info(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get information about a scheduled task."""
        with self._lock:
            if task_id not in self._tasks:
                return None
            
            task = self._tasks[task_id]
            return {
                "id": task.id,
                "schedule_type": task.schedule_type.value,
                "next_run": task.next_run.isoformat(),
                "last_run": task.last_run.isoformat() if task.last_run else None,
                "run_count": task.run_count,
                "enabled": task.enabled,
                "last_error": str(task.last_error) if task.last_error else None,
            }
    
    def get_all_tasks(self) -> List[Dict[str, Any]]:
        """Get information about all scheduled tasks."""
        with self._lock:
            return [
                {
                    "id": task.id,
                    "schedule_type": task.schedule_type.value,
                    "next_run": task.next_run.isoformat(),
                    "last_run": task.last_run.isoformat() if task.last_run else None,
                    "run_count": task.run_count,
                    "enabled": task.enabled,
                }
                for task in self._tasks.values()
            ]
    
    @property
    def pending_count(self) -> int:
        """Get count of pending scheduled tasks."""
        with self._lock:
            return len([t for t in self._tasks.values() if t.enabled])
