"""Async Utilities Module
Provides async wrappers and utilities for multi-threading/async operations
Uses Python 3.14 standard library asyncio and concurrent.futures
Follows SOLID/DRY principles
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Callable, Coroutine
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import asynccontextmanager
from functools import wraps
from typing import Any, TypeVar

from config import get_max_workers
from shared.logging_config import get_logger

T = TypeVar("T")

logger = get_logger("serviceup.async_utils")


class AsyncExecutor:
    """Thread-safe async executor with configurable worker pool
    Implements Singleton pattern via module-level instance
    """

    def __init__(self, max_workers: int | None = None):
        self.max_workers = max_workers or get_max_workers()
        self._executor: ThreadPoolExecutor | None = None
        self._lock = threading.Lock()
        self._shutdown = False

    def _get_executor(self) -> ThreadPoolExecutor:
        """Lazy initialization of executor (thread-safe)"""
        if self._executor is None:
            with self._lock:
                if self._executor is None:
                    self._executor = ThreadPoolExecutor(
                        max_workers=self.max_workers,
                        thread_name_prefix="serviceup_worker",
                    )
        return self._executor

    def run_sync_in_async(
        self,
        func: Callable[..., T],
        *args: Any,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> Coroutine[Any, Any, T]:
        """Run synchronous function in async context using thread pool

        Args:
            func: Synchronous function to run
            *args: Positional arguments for func
            timeout: Optional timeout in seconds
            **kwargs: Keyword arguments for func

        Returns:
            Coroutine that resolves to function result
        """
        if self._shutdown:
            raise RuntimeError("Executor has been shut down")

        executor = self._get_executor()

        async def wrapper() -> T:
            loop = asyncio.get_event_loop()
            try:
                return await asyncio.wait_for(
                    loop.run_in_executor(executor, lambda: func(*args, **kwargs)),
                    timeout=timeout,
                )
            except TimeoutError:
                logger.exception(
                    f"Operation timed out after {timeout}s: {func.__name__}"
                )
                raise

        return wrapper()

    def run_async_in_sync(
        self, coro: Coroutine[Any, Any, T], timeout: float | None = None
    ) -> T:
        """Run async coroutine in synchronous context

        Args:
            coro: Coroutine to run
            timeout: Optional timeout in seconds

        Returns:
            Result of coroutine
        """
        if self._shutdown:
            raise RuntimeError("Executor has been shut down")

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        if loop.is_running():
            # We're already in an async context, use run_sync_in_async
            future = asyncio.run_coroutine_threadsafe(coro, loop)
            return future.result(timeout=timeout)
        else:
            return loop.run_until_complete(asyncio.wait_for(coro, timeout=timeout))

    def map_parallel(
        self,
        func: Callable[..., T],
        items: list[Any],
        timeout_per_item: float | None = None,
    ) -> list[T]:
        """Execute function in parallel for multiple items

        Args:
            func: Function to execute
            items: List of items to process
            timeout_per_item: Timeout per item in seconds

        Returns:
            List of results in same order as input
        """
        if self._shutdown:
            raise RuntimeError("Executor has been shut down")

        executor = self._get_executor()

        # Submit all tasks
        futures = {executor.submit(func, item): idx for idx, item in enumerate(items)}

        # Collect results maintaining order
        ordered_results = [None] * len(items)

        for future in as_completed(
            futures, timeout=timeout_per_item * len(items) if timeout_per_item else None
        ):
            idx = futures[future]
            try:
                ordered_results[idx] = future.result()
            except Exception as e:
                logger.exception(f"Task failed for item {idx}: {e}")
                ordered_results[idx] = None

        return ordered_results

    def shutdown(self, wait: bool = True) -> None:
        """Shutdown the executor

        Args:
            wait: If True, wait for pending tasks to complete
        """
        with self._lock:
            self._shutdown = True
            if self._executor:
                self._executor.shutdown(wait=wait)
                self._executor = None


# Global executor instance (Singleton)
_executor_instance: AsyncExecutor | None = None


def get_executor() -> AsyncExecutor:
    """Get global executor instance (thread-safe singleton)"""
    global _executor_instance
    if _executor_instance is None:
        _executor_instance = AsyncExecutor()
    return _executor_instance


def async_wrap[T](func: Callable[..., T]) -> Callable[..., Coroutine[Any, Any, T]]:
    """Decorator to wrap sync function as async
    Usage:
        @async_wrap
        def my_sync_function(x, y):
            return x + y

        result = await my_sync_function(1, 2)
    """

    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> T:
        return await get_executor().run_sync_in_async(func, *args, **kwargs)

    return wrapper


def sync_unwrap[T](
    coro_func: Callable[..., Coroutine[Any, Any, T]],
) -> Callable[..., T]:
    """Decorator to make async function callable from sync context
    Usage:
        @sync_unwrap
        async def my_async_function(x, y):
            return x + y

        result = my_async_function(1, 2)
    """

    @wraps(coro_func)
    def wrapper(*args: Any, **kwargs: Any) -> T:
        coro = coro_func(*args, **kwargs)
        return get_executor().run_async_in_sync(coro)

    return wrapper


@asynccontextmanager
async def async_timeout(timeout: float, operation_name: str = "operation"):
    """Async context manager for timeout handling
    Usage:
        async with async_timeout(5.0, "database_query"):
            await some_async_operation()
    """
    start_time = time.perf_counter()
    try:
        async with asyncio.timeout(timeout):
            yield
        elapsed = time.perf_counter() - start_time
        logger.debug(f"Completed {operation_name} in {elapsed:.4f}s")
    except TimeoutError:
        elapsed = time.perf_counter() - start_time
        logger.exception(
            f"Timeout: {operation_name} exceeded {timeout}s after {elapsed:.4f}s"
        )
        raise


async def gather_with_concurrency[T](
    n: int, *coros: Coroutine[Any, Any, T], return_exceptions: bool = False
) -> list[T]:
    """Run coroutines with limited concurrency
    Similar to asyncio.gather but with max concurrent tasks

    Args:
        n: Maximum number of concurrent tasks
        *coros: Coroutines to run
        return_exceptions: If True, return exceptions instead of raising

    Returns:
        List of results
    """
    semaphore = asyncio.Semaphore(n)

    async def limited_coro(coro: Coroutine[Any, Any, T]) -> T:
        async with semaphore:
            try:
                return await coro
            except Exception as e:
                if return_exceptions:
                    return e  # type: ignore
                raise

    tasks = [limited_coro(c) for c in coros]
    return await asyncio.gather(*tasks, return_exceptions=return_exceptions)


# Convenience functions (DRY principle)
async def run_in_background[T](
    func: Callable[..., T], *args: Any, **kwargs: Any
) -> asyncio.Task[T]:
    """Run function in background task
    Returns immediately with asyncio.Task
    """
    return asyncio.create_task(get_executor().run_sync_in_async(func, *args, **kwargs))


def batch_process[T](
    items: list[Any],
    func: Callable[..., T],
    batch_size: int = 10,
    max_workers: int | None = None,
) -> list[T]:
    """Process items in batches with parallel execution

    Args:
        items: Items to process
        func: Processing function
        batch_size: Items per batch
        max_workers: Override default worker count

    Returns:
        List of all results
    """
    executor = AsyncExecutor(max_workers=max_workers)
    results = []

    try:
        # Split into batches
        batches = [items[i : i + batch_size] for i in range(0, len(items), batch_size)]

        # Process each batch
        for batch in batches:
            batch_results = executor.map_parallel(func, batch)
            results.extend([r for r in batch_results if r is not None])

        return results
    finally:
        executor.shutdown(wait=True)


# Export public API
__all__ = [
    "AsyncExecutor",
    "async_timeout",
    "async_wrap",
    "batch_process",
    "gather_with_concurrency",
    "get_executor",
    "run_in_background",
    "sync_unwrap",
]
