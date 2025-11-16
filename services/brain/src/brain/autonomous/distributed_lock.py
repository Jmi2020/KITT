"""Distributed locking for concurrent job execution.

Provides Redis-based distributed locks to prevent race conditions when
multiple APScheduler jobs access shared resources (tasks, projects, goals).

Uses the Redlock algorithm for reliable distributed locking with automatic
expiration to prevent deadlocks from crashes.
"""

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from typing import Optional
from uuid import uuid4

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)


class DistributedLock:
    """Redis-based distributed lock for preventing concurrent access.

    Implements a simplified Redlock algorithm with automatic expiration
    to prevent deadlocks from process crashes.

    Features:
    - Automatic lock expiration (prevents deadlocks)
    - Lock holder identification (prevents accidental unlock by other processes)
    - Async context manager support
    - Retry with exponential backoff

    Example:
        async with DistributedLock(redis_client, "task:123", ttl_seconds=30):
            # Exclusive access to task 123
            await execute_task(task_123)
    """

    def __init__(
        self,
        redis_client: aioredis.Redis,
        lock_key: str,
        ttl_seconds: int = 30,
        retry_count: int = 3,
        retry_delay: float = 0.1,
    ):
        """Initialize distributed lock.

        Args:
            redis_client: Async Redis client
            lock_key: Unique key for this lock (e.g., "task:123", "goal:456")
            ttl_seconds: Lock expiration time (prevents deadlocks)
            retry_count: Number of acquisition retries
            retry_delay: Initial delay between retries (exponential backoff)
        """
        self._redis = redis_client
        self._lock_key = f"lock:{lock_key}"
        self._ttl_seconds = ttl_seconds
        self._retry_count = retry_count
        self._retry_delay = retry_delay
        self._lock_id = str(uuid4())  # Unique ID for this lock holder
        self._acquired = False

    async def acquire(self) -> bool:
        """Acquire the lock with retries.

        Returns:
            True if lock acquired, False if failed after retries
        """
        for attempt in range(self._retry_count):
            # SET NX (only if not exists) with expiration
            acquired = await self._redis.set(
                self._lock_key,
                self._lock_id,
                ex=self._ttl_seconds,
                nx=True  # Only set if key doesn't exist
            )

            if acquired:
                self._acquired = True
                logger.debug(
                    f"Lock acquired: {self._lock_key} "
                    f"(holder: {self._lock_id[:8]}, ttl: {self._ttl_seconds}s)"
                )
                return True

            # Lock held by another process - wait and retry
            if attempt < self._retry_count - 1:
                delay = self._retry_delay * (2 ** attempt)  # Exponential backoff
                logger.debug(
                    f"Lock busy: {self._lock_key}, retrying in {delay:.2f}s "
                    f"(attempt {attempt + 1}/{self._retry_count})"
                )
                await asyncio.sleep(delay)

        logger.warning(
            f"Failed to acquire lock after {self._retry_count} attempts: {self._lock_key}"
        )
        return False

    async def release(self) -> bool:
        """Release the lock (only if we hold it).

        Returns:
            True if lock released, False if we don't hold it
        """
        if not self._acquired:
            return False

        # Lua script for atomic check-and-delete
        # Only delete if lock_id matches (prevents accidental unlock by other processes)
        lua_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """

        released = await self._redis.eval(lua_script, 1, self._lock_key, self._lock_id)

        if released:
            self._acquired = False
            logger.debug(
                f"Lock released: {self._lock_key} (holder: {self._lock_id[:8]})"
            )
            return True
        else:
            logger.warning(
                f"Lock release failed - lock held by different process: {self._lock_key}"
            )
            return False

    async def __aenter__(self):
        """Async context manager entry."""
        acquired = await self.acquire()
        if not acquired:
            raise RuntimeError(
                f"Failed to acquire distributed lock: {self._lock_key}"
            )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.release()
        return False  # Don't suppress exceptions


class LockManager:
    """Manager for distributed locks across the system.

    Provides high-level API for acquiring locks on specific resources
    with sensible defaults for different resource types.
    """

    # Default TTLs for different resource types
    DEFAULT_TTLS = {
        "task": 300,  # 5 minutes - task execution can be slow
        "project": 60,  # 1 minute - project operations are fast
        "goal": 60,  # 1 minute - goal operations are fast
        "job": 30,  # 30 seconds - job scheduling is fast
        "session": 120,  # 2 minutes - research sessions need longer
    }

    def __init__(self, redis_client: aioredis.Redis):
        """Initialize lock manager.

        Args:
            redis_client: Async Redis client for lock storage
        """
        self._redis = redis_client

    @asynccontextmanager
    async def lock_task(self, task_id: str, ttl_seconds: Optional[int] = None):
        """Acquire lock for task execution.

        Args:
            task_id: Task ID to lock
            ttl_seconds: Lock expiration (default: 5 minutes)

        Example:
            async with lock_manager.lock_task("task-123"):
                await execute_task(task_123)
        """
        ttl = ttl_seconds or self.DEFAULT_TTLS["task"]
        lock = DistributedLock(
            self._redis,
            f"task:{task_id}",
            ttl_seconds=ttl
        )
        async with lock:
            yield

    @asynccontextmanager
    async def lock_project(self, project_id: str, ttl_seconds: Optional[int] = None):
        """Acquire lock for project operations.

        Args:
            project_id: Project ID to lock
            ttl_seconds: Lock expiration (default: 1 minute)
        """
        ttl = ttl_seconds or self.DEFAULT_TTLS["project"]
        lock = DistributedLock(
            self._redis,
            f"project:{project_id}",
            ttl_seconds=ttl
        )
        async with lock:
            yield

    @asynccontextmanager
    async def lock_goal(self, goal_id: str, ttl_seconds: Optional[int] = None):
        """Acquire lock for goal operations.

        Args:
            goal_id: Goal ID to lock
            ttl_seconds: Lock expiration (default: 1 minute)
        """
        ttl = ttl_seconds or self.DEFAULT_TTLS["goal"]
        lock = DistributedLock(
            self._redis,
            f"goal:{goal_id}",
            ttl_seconds=ttl
        )
        async with lock:
            yield

    @asynccontextmanager
    async def lock_research_session(
        self,
        session_id: str,
        ttl_seconds: Optional[int] = None
    ):
        """Acquire lock for research session operations.

        Args:
            session_id: Research session ID to lock
            ttl_seconds: Lock expiration (default: 2 minutes)
        """
        ttl = ttl_seconds or self.DEFAULT_TTLS["session"]
        lock = DistributedLock(
            self._redis,
            f"session:{session_id}",
            ttl_seconds=ttl
        )
        async with lock:
            yield

    @asynccontextmanager
    async def lock_custom(
        self,
        lock_key: str,
        ttl_seconds: int = 30,
        retry_count: int = 3
    ):
        """Acquire custom lock with specified parameters.

        Args:
            lock_key: Custom lock key (will be prefixed with "lock:")
            ttl_seconds: Lock expiration time
            retry_count: Number of acquisition retries

        Example:
            async with lock_manager.lock_custom("batch-import", ttl_seconds=300):
                await import_large_dataset()
        """
        lock = DistributedLock(
            self._redis,
            lock_key,
            ttl_seconds=ttl_seconds,
            retry_count=retry_count
        )
        async with lock:
            yield

    async def is_locked(self, resource_type: str, resource_id: str) -> bool:
        """Check if a resource is currently locked.

        Args:
            resource_type: Type of resource ("task", "project", "goal", etc.)
            resource_id: Resource ID

        Returns:
            True if locked, False otherwise
        """
        lock_key = f"lock:{resource_type}:{resource_id}"
        exists = await self._redis.exists(lock_key)
        return bool(exists)

    async def get_lock_holder(self, resource_type: str, resource_id: str) -> Optional[str]:
        """Get the ID of the process holding the lock.

        Args:
            resource_type: Type of resource
            resource_id: Resource ID

        Returns:
            Lock holder ID if locked, None if not locked
        """
        lock_key = f"lock:{resource_type}:{resource_id}"
        holder = await self._redis.get(lock_key)
        return holder.decode() if holder else None


__all__ = ["DistributedLock", "LockManager", "get_lock_manager", "set_lock_manager"]


# Global lock manager instance (singleton)
_lock_manager_instance: Optional[LockManager] = None


def get_lock_manager() -> Optional[LockManager]:
    """Get the global lock manager instance.

    Returns:
        LockManager instance, or None if not initialized
    """
    return _lock_manager_instance


def set_lock_manager(redis_client: aioredis.Redis) -> LockManager:
    """Initialize and set the global lock manager.

    Args:
        redis_client: Async Redis client for distributed locking

    Returns:
        Initialized LockManager instance
    """
    global _lock_manager_instance
    _lock_manager_instance = LockManager(redis_client)
    logger.info("Global LockManager initialized for distributed locking")
    return _lock_manager_instance
