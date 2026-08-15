"""
Thread Manager.
Centralized manager for all application threads.
Ensures safe creation, monitoring, and shutdown of threads.
"""

import threading
import logging
from typing import Callable, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class ThreadStatus(Enum):
    """Status of a managed thread."""
    CREATED = "created"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass(slots=True)
class ThreadInfo:
    """Information about a managed thread."""
    thread_id: str
    thread: threading.Thread
    status: ThreadStatus
    started_at: datetime | None = None
    stopped_at: datetime | None = None
    error: Exception | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


logger = logging.getLogger(__name__)


class ThreadManager:
    """
    Centralized thread manager.
    
    Provides:
    - Safe thread creation and tracking
    - Graceful shutdown of all threads
    - Error handling and recovery
    - Thread status monitoring
    """
    
    _instance: "ThreadManager | None" = None
    _lock = threading.Lock()
    
    def __new__(cls) -> "ThreadManager":
        """Singleton pattern to ensure single thread manager instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._threads: dict[str, ThreadInfo] = {}
        self._lock = threading.RLock()
        self._shutdown_event = threading.Event()
        self._initialized = True
        
        logger.info("ThreadManager initialized")
    
    @classmethod
    def get_instance(cls) -> "ThreadManager":
        """Get the singleton instance."""
        return cls()
    
    def create_thread(
        self,
        name: str,
        target: Callable[..., Any],
        args: tuple = (),
        kwargs: dict[str, Any] | None = None,
        daemon: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """
        Create and register a new managed thread.
        
        Args:
            name: Unique identifier for the thread
            target: Target callable to execute
            args: Positional arguments for target
            kwargs: Keyword arguments for target
            daemon: Whether thread should be daemon
            metadata: Additional metadata for tracking
            
        Returns:
            Thread ID
            
        Raises:
            ValueError: If thread with given name already exists
        """
        with self._lock:
            if name in self._threads:
                raise ValueError(f"Thread '{name}' already exists")
            
            def wrapped_target():
                try:
                    logger.debug(f"Thread '{name}' started")
                    target(*args, **(kwargs or {}))
                except Exception as e:
                    logger.error(f"Thread '{name}' error: {e}", exc_info=True)
                    with self._lock:
                        if name in self._threads:
                            self._threads[name].status = ThreadStatus.ERROR
                            self._threads[name].error = e
                finally:
                    with self._lock:
                        if name in self._threads:
                            self._threads[name].status = ThreadStatus.STOPPED
                            self._threads[name].stopped_at = datetime.now()
            
            thread = threading.Thread(
                target=wrapped_target,
                name=name,
                daemon=daemon,
            )
            
            thread_info = ThreadInfo(
                thread_id=name,
                thread=thread,
                status=ThreadStatus.CREATED,
                metadata=metadata or {},
            )
            
            self._threads[name] = thread_info
            logger.info(f"Thread '{name}' created")
            
            return name
    
    def start_thread(self, thread_id: str) -> bool:
        """
        Start a registered thread.
        
        Args:
            thread_id: ID of thread to start
            
        Returns:
            True if started successfully, False otherwise
        """
        with self._lock:
            if thread_id not in self._threads:
                logger.error(f"Thread '{thread_id}' not found")
                return False
            
            thread_info = self._threads[thread_id]
            if thread_info.status != ThreadStatus.CREATED:
                logger.warning(f"Thread '{thread_id}' is not in CREATED state")
                return False
            
            try:
                thread_info.thread.start()
                thread_info.status = ThreadStatus.RUNNING
                thread_info.started_at = datetime.now()
                logger.info(f"Thread '{thread_id}' started")
                return True
            except Exception as e:
                logger.error(f"Failed to start thread '{thread_id}': {e}")
                thread_info.status = ThreadStatus.ERROR
                thread_info.error = e
                return False
    
    def stop_thread(self, thread_id: str, timeout: float = 5.0) -> bool:
        """
        Stop a running thread gracefully.
        
        Note: This relies on the thread checking the shutdown event
        or completing its task naturally.
        
        Args:
            thread_id: ID of thread to stop
            timeout: Maximum time to wait for thread to stop
            
        Returns:
            True if stopped successfully, False otherwise
        """
        with self._lock:
            if thread_id not in self._threads:
                logger.warning(f"Thread '{thread_id}' not found")
                return False
            
            thread_info = self._threads[thread_id]
            if thread_info.status not in (ThreadStatus.RUNNING, ThreadStatus.CREATED):
                logger.warning(f"Thread '{thread_id}' is not running")
                return False
            
            thread_info.status = ThreadStatus.STOPPING
            logger.info(f"Stopping thread '{thread_id}'")
        
        # Wait outside lock to avoid deadlock
        thread_info.thread.join(timeout=timeout)
        
        with self._lock:
            if thread_info.thread.is_alive():
                logger.warning(f"Thread '{thread_id}' did not stop within timeout")
                return False
            
            thread_info.stopped_at = datetime.now()
            logger.info(f"Thread '{thread_id}' stopped")
            return True
    
    def stop_all(self, timeout: float = 10.0) -> dict[str, bool]:
        """
        Stop all managed threads gracefully.
        
        Args:
            timeout: Maximum time to wait for each thread
            
        Returns:
            Dictionary mapping thread IDs to success status
        """
        logger.info("Stopping all threads...")
        self._shutdown_event.set()
        
        results = {}
        with self._lock:
            thread_ids = list(self._threads.keys())
        
        for thread_id in thread_ids:
            results[thread_id] = self.stop_thread(thread_id, timeout=timeout / max(len(thread_ids), 1))
        
        logger.info(f"All threads stopped. Success: {sum(results.values())}/{len(results)}")
        return results
    
    def get_thread_status(self, thread_id: str) -> ThreadStatus | None:
        """Get status of a specific thread."""
        with self._lock:
            if thread_id not in self._threads:
                return None
            return self._threads[thread_id].status
    
    def get_all_statuses(self) -> dict[str, ThreadStatus]:
        """Get statuses of all managed threads."""
        with self._lock:
            return {
                thread_id: info.status 
                for thread_id, info in self._threads.items()
            }
    
    def is_running(self, thread_id: str) -> bool:
        """Check if a specific thread is running."""
        status = self.get_thread_status(thread_id)
        return status == ThreadStatus.RUNNING
    
    def get_active_count(self) -> int:
        """Get count of currently running threads."""
        with self._lock:
            return sum(
                1 for info in self._threads.values() 
                if info.status == ThreadStatus.RUNNING
            )
    
    def cleanup_stopped(self) -> int:
        """Remove stopped threads from tracking. Returns count of removed threads."""
        with self._lock:
            to_remove = [
                tid for tid, info in self._threads.items()
                if info.status in (ThreadStatus.STOPPED, ThreadStatus.ERROR)
            ]
            for tid in to_remove:
                del self._threads[tid]
            return len(to_remove)
    
    @property
    def shutdown_event(self) -> threading.Event:
        """Get the global shutdown event for threads to monitor."""
        return self._shutdown_event
    
    def reset_shutdown(self):
        """Reset shutdown event for new operation cycle."""
        self._shutdown_event.clear()
        logger.debug("Shutdown event reset")
