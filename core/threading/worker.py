"""
Worker Pool and Task definitions.
Provides a thread pool for executing tasks concurrently.
"""

import threading
import queue
import logging
from typing import Callable, Any
from dataclasses import dataclass, field
from datetime import datetime
from concurrent.futures import Future, ThreadPoolExecutor
from enum import Enum


logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    """Status of a task."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(slots=True)
class Task:
    """
    Represents a unit of work to be executed.
    
    Attributes:
        id: Unique identifier for the task
        func: Callable to execute
        args: Positional arguments for the callable
        kwargs: Keyword arguments for the callable
        priority: Task priority (lower number = higher priority)
        status: Current task status
        result: Result of task execution
        error: Error if task failed
        created_at: When task was created
        started_at: When task execution started
        completed_at: When task execution completed
    """
    id: str
    func: Callable[..., Any]
    args: tuple = field(default_factory=tuple)
    kwargs: dict[str, Any] = field(default_factory=dict)
    priority: int = 0
    status: TaskStatus = TaskStatus.PENDING
    result: Any = None
    error: Exception | None = None
    created_at: datetime = field(default_factory=datetime.now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    
    def __lt__(self, other: "Task") -> bool:
        """Compare tasks by priority for priority queue."""
        return self.priority < other.priority


class WorkerPool:
    """
    Thread pool for executing tasks concurrently.
    
    Provides:
    - Configurable number of worker threads
    - Priority-based task scheduling
    - Task status tracking
    - Graceful shutdown
    """
    
    def __init__(
        self,
        max_workers: int = 4,
        name: str = "WorkerPool",
        enable_priority: bool = True,
    ):
        """
        Initialize worker pool.
        
        Args:
            max_workers: Maximum number of concurrent workers
            name: Pool name for logging
            enable_priority: Whether to use priority queue
        """
        self.max_workers = max_workers
        self.name = name
        self.enable_priority = enable_priority
        
        self._executor: ThreadPoolExecutor | None = None
        self._task_queue: queue.PriorityQueue if enable_priority else queue.Queue
        self._tasks: dict[str, Task] = {}
        self._futures: dict[str, Future] = {}
        self._lock = threading.RLock()
        self._shutdown = False
        
        if enable_priority:
            self._task_queue = queue.PriorityQueue()
        else:
            self._task_queue = queue.Queue()
        
        logger.info(f"{name} initialized with {max_workers} workers")
    
    def start(self):
        """Start the worker pool."""
        with self._lock:
            if self._executor is not None:
                logger.warning(f"{self.name} already started")
                return
            
            self._executor = ThreadPoolExecutor(
                max_workers=self.max_workers,
                thread_name_prefix=self.name,
            )
            self._shutdown = False
            # Start worker threads
            for i in range(self.max_workers):
                self._executor.submit(self._worker_loop)
            logger.info(f"{self.name} started")
    
    def submit(
        self,
        task_id: str,
        func: Callable[..., Any],
        priority: int = 0,
        *args: Any,
        **kwargs: Any,
    ) -> str | None:
        """
        Submit a task to the pool.
        
        Args:
            task_id: Unique identifier for the task
            func: Callable to execute
            priority: Task priority (lower = higher priority)
            *args: Positional arguments for the callable
            **kwargs: Keyword arguments for the callable
            
        Returns:
            Task ID if submitted successfully, None otherwise
        """
        with self._lock:
            if self._shutdown:
                logger.warning(f"{self.name} is shutting down, task rejected")
                return None
            
            if task_id in self._tasks:
                logger.warning(f"Task '{task_id}' already exists")
                return None
            
            task = Task(
                id=task_id,
                func=func,
                args=args,
                kwargs=kwargs,
                priority=priority,
            )
            
            self._tasks[task_id] = task
            
            if self.enable_priority:
                self._task_queue.put((priority, task_id, task))
            else:
                self._task_queue.put(task)
            
            logger.debug(f"Task '{task_id}' submitted with priority {priority}")
            return task_id
    
    def _worker_loop(self):
        """Worker loop to process tasks from queue."""
        while not self._shutdown:
            try:
                if self.enable_priority:
                    _, task_id, task = self._task_queue.get(timeout=0.1)
                else:
                    task = self._task_queue.get(timeout=0.1)
                    task_id = task.id
                
                self._execute_task(task)
                self._task_queue.task_done()
                
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"{self.name} worker error: {e}", exc_info=True)
    
    def _execute_task(self, task: Task):
        """Execute a single task."""
        with self._lock:
            if task.status == TaskStatus.CANCELLED:
                return
            
            task.status = TaskStatus.RUNNING
            task.started_at = datetime.now()
            self._tasks[task.id] = task
        
        try:
            logger.debug(f"Executing task '{task.id}'")
            result = task.func(*task.args, **task.kwargs)
            
            with self._lock:
                task.status = TaskStatus.COMPLETED
                task.result = result
                task.completed_at = datetime.now()
                self._tasks[task.id] = task
            
            logger.debug(f"Task '{task.id}' completed successfully")
            
        except Exception as e:
            logger.error(f"Task '{task.id}' failed: {e}", exc_info=True)
            with self._lock:
                task.status = TaskStatus.FAILED
                task.error = e
                task.completed_at = datetime.now()
                self._tasks[task.id] = task
    
    def get_task_status(self, task_id: str) -> TaskStatus | None:
        """Get status of a specific task."""
        with self._lock:
            if task_id not in self._tasks:
                return None
            return self._tasks[task_id].status
    
    def get_task_result(self, task_id: str, timeout: float | None = None) -> Any:
        """
        Get result of a completed task.
        
        Args:
            task_id: ID of task
            timeout: Maximum time to wait for completion
            
        Returns:
            Task result or None if not completed
        """
        with self._lock:
            if task_id not in self._tasks:
                return None
            task = self._tasks[task_id]
        
        if task.status == TaskStatus.COMPLETED:
            return task.result
        elif task.status == TaskStatus.FAILED:
            raise task.error or RuntimeError("Task failed with unknown error")
        
        return None
    
    def cancel_task(self, task_id: str) -> bool:
        """
        Cancel a pending task.
        
        Args:
            task_id: ID of task to cancel
            
        Returns:
            True if cancelled, False if already running or completed
        """
        with self._lock:
            if task_id not in self._tasks:
                return False
            
            task = self._tasks[task_id]
            if task.status != TaskStatus.PENDING:
                return False
            
            task.status = TaskStatus.CANCELLED
            task.completed_at = datetime.now()
            logger.info(f"Task '{task_id}' cancelled")
            return True
    
    def shutdown(self, wait: bool = True, cancel_pending: bool = True) -> None:
        """
        Shutdown the worker pool.
        
        Args:
            wait: Whether to wait for running tasks to complete
            cancel_pending: Whether to cancel pending tasks
        """
        logger.info(f"Shutting down {self.name}...")
        
        with self._lock:
            self._shutdown = True
            
            if cancel_pending:
                for task in self._tasks.values():
                    if task.status == TaskStatus.PENDING:
                        task.status = TaskStatus.CANCELLED
                        task.completed_at = datetime.now()
        
        if self._executor:
            self._executor.shutdown(wait=wait)
            self._executor = None
        
        logger.info(f"{self.name} shut down complete")
    
    @property
    def active_count(self) -> int:
        """Get count of currently running tasks."""
        with self._lock:
            return sum(
                1 for task in self._tasks.values()
                if task.status == TaskStatus.RUNNING
            )
    
    @property
    def pending_count(self) -> int:
        """Get count of pending tasks."""
        with self._lock:
            return sum(
                1 for task in self._tasks.values()
                if task.status == TaskStatus.PENDING
            )
    
    def get_all_tasks(self) -> list[Task]:
        """Get list of all tasks."""
        with self._lock:
            return list(self._tasks.values())
