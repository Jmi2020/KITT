"""
PostgreSQL Checkpointer for LangGraph

Provides fault-tolerant state persistence for multi-hour research sessions.
Automatically saves state after each graph node execution, enabling crash recovery.
"""

import logging
import os
from typing import Optional

from langgraph.checkpoint.postgres import PostgresSaver
from psycopg_pool import ConnectionPool

logger = logging.getLogger(__name__)


def create_connection_pool(
    database_url: Optional[str] = None,
    min_size: int = 2,
    max_size: int = 20
) -> ConnectionPool:
    """
    Create a PostgreSQL connection pool for checkpointing.

    Args:
        database_url: PostgreSQL connection string. Defaults to DATABASE_URL env var.
        min_size: Minimum number of connections in pool
        max_size: Maximum number of connections in pool

    Returns:
        ConnectionPool configured for checkpointing

    Raises:
        ValueError: If database_url is not provided and DATABASE_URL env var not set
    """
    if database_url is None:
        database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise ValueError(
            "Database URL must be provided either as argument or via DATABASE_URL env var"
        )

    logger.info(
        f"Creating connection pool: min_size={min_size}, max_size={max_size}"
    )

    # Create connection pool with autocommit and dict row factory
    pool = ConnectionPool(
        conninfo=database_url,
        min_size=min_size,
        max_size=max_size,
        kwargs={
            "autocommit": True,
            "prepare_threshold": None  # Disable prepared statements for compatibility
        }
    )

    logger.info("Connection pool created successfully")
    return pool


def init_checkpointer(
    connection_pool: ConnectionPool,
    auto_setup: bool = True
) -> PostgresSaver:
    """
    Initialize PostgreSQL checkpointer for LangGraph.

    Args:
        connection_pool: PostgreSQL connection pool
        auto_setup: If True, automatically create checkpoint tables if they don't exist

    Returns:
        PostgresSaver configured for checkpointing

    Example:
        ```python
        pool = create_connection_pool()
        checkpointer = init_checkpointer(pool)
        graph = build_research_graph(checkpointer)
        ```
    """
    logger.info("Initializing PostgreSQL checkpointer")

    # Create PostgresSaver
    checkpointer = PostgresSaver(connection_pool)

    # Setup checkpoint tables if requested
    if auto_setup:
        try:
            logger.info("Setting up checkpoint tables")
            checkpointer.setup()
            logger.info("Checkpoint tables setup complete")
        except Exception as e:
            logger.warning(
                f"Checkpoint table setup failed (may already exist): {e}"
            )

    return checkpointer


class CheckpointManager:
    """
    Manages checkpoint operations and provides utilities for recovery.

    Handles:
    - Checkpoint listing and retrieval
    - State compression for long sessions
    - Recovery from crashes
    - Checkpoint cleanup
    """

    def __init__(self, checkpointer: PostgresSaver, connection_pool: ConnectionPool):
        self.checkpointer = checkpointer
        self.pool = connection_pool
        self.logger = logging.getLogger(__name__ + ".CheckpointManager")

    async def get_latest_checkpoint(self, thread_id: str) -> Optional[dict]:
        """
        Get the most recent checkpoint for a thread.

        Args:
            thread_id: Thread ID to retrieve checkpoint for

        Returns:
            Latest checkpoint dict or None if no checkpoints exist
        """
        config = {"configurable": {"thread_id": thread_id}}

        try:
            state = self.checkpointer.get(config)
            if state:
                self.logger.info(f"Retrieved checkpoint for thread {thread_id}")
                return state
            else:
                self.logger.info(f"No checkpoint found for thread {thread_id}")
                return None
        except Exception as e:
            self.logger.error(f"Error retrieving checkpoint: {e}")
            return None

    async def list_checkpoints(
        self,
        thread_id: str,
        limit: int = 10
    ) -> list[dict]:
        """
        List recent checkpoints for a thread.

        Args:
            thread_id: Thread ID to list checkpoints for
            limit: Maximum number of checkpoints to return

        Returns:
            List of checkpoint dicts ordered by timestamp descending
        """
        try:
            with self.pool.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT
                            checkpoint_id,
                            parent_checkpoint_id,
                            checkpoint->>'ts' as timestamp,
                            type,
                            jsonb_object_keys(checkpoint->'channel_values') as channels
                        FROM checkpoints
                        WHERE thread_id = %s
                        AND checkpoint_ns = ''
                        ORDER BY checkpoint->>'ts' DESC
                        LIMIT %s
                        """,
                        (thread_id, limit)
                    )

                    results = cur.fetchall()
                    self.logger.info(
                        f"Found {len(results)} checkpoints for thread {thread_id}"
                    )
                    return [dict(row) for row in results]

        except Exception as e:
            self.logger.error(f"Error listing checkpoints: {e}")
            return []

    async def cleanup_old_checkpoints(
        self,
        thread_id: str,
        keep_last_n: int = 50
    ) -> int:
        """
        Remove old checkpoints to prevent database bloat.

        Keeps the most recent N checkpoints for a thread.

        Args:
            thread_id: Thread ID to cleanup checkpoints for
            keep_last_n: Number of recent checkpoints to keep

        Returns:
            Number of checkpoints deleted
        """
        try:
            with self.pool.connection() as conn:
                with conn.cursor() as cur:
                    # Delete old checkpoints, keeping the most recent N
                    cur.execute(
                        """
                        WITH checkpoints_to_delete AS (
                            SELECT checkpoint_id
                            FROM checkpoints
                            WHERE thread_id = %s
                            AND checkpoint_ns = ''
                            ORDER BY checkpoint->>'ts' DESC
                            OFFSET %s
                        )
                        DELETE FROM checkpoints
                        WHERE thread_id = %s
                        AND checkpoint_id IN (SELECT checkpoint_id FROM checkpoints_to_delete)
                        """,
                        (thread_id, keep_last_n, thread_id)
                    )

                    deleted_count = cur.rowcount
                    conn.commit()

                    self.logger.info(
                        f"Deleted {deleted_count} old checkpoints for thread {thread_id}"
                    )
                    return deleted_count

        except Exception as e:
            self.logger.error(f"Error cleaning up checkpoints: {e}")
            return 0

    async def get_checkpoint_size(self, thread_id: str) -> dict:
        """
        Get size statistics for checkpoints of a thread.

        Args:
            thread_id: Thread ID to analyze

        Returns:
            Dict with checkpoint size statistics
        """
        try:
            with self.pool.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT
                            COUNT(*) as checkpoint_count,
                            SUM(pg_column_size(checkpoint)) as total_checkpoint_bytes,
                            AVG(pg_column_size(checkpoint)) as avg_checkpoint_bytes,
                            MAX(pg_column_size(checkpoint)) as max_checkpoint_bytes
                        FROM checkpoints
                        WHERE thread_id = %s
                        AND checkpoint_ns = ''
                        """,
                        (thread_id,)
                    )

                    result = cur.fetchone()

                    if result:
                        stats = {
                            "checkpoint_count": result[0] or 0,
                            "total_bytes": result[1] or 0,
                            "avg_bytes": int(result[2] or 0),
                            "max_bytes": result[3] or 0,
                            "total_mb": round((result[1] or 0) / (1024 * 1024), 2)
                        }

                        self.logger.info(
                            f"Checkpoint stats for {thread_id}: {stats['checkpoint_count']} checkpoints, "
                            f"{stats['total_mb']} MB total"
                        )

                        return stats

                    return {
                        "checkpoint_count": 0,
                        "total_bytes": 0,
                        "avg_bytes": 0,
                        "max_bytes": 0,
                        "total_mb": 0
                    }

        except Exception as e:
            self.logger.error(f"Error getting checkpoint size: {e}")
            return {
                "checkpoint_count": 0,
                "total_bytes": 0,
                "avg_bytes": 0,
                "max_bytes": 0,
                "total_mb": 0,
                "error": str(e)
            }

    async def is_checkpoint_stale(
        self,
        thread_id: str,
        stale_threshold_seconds: int = 300
    ) -> bool:
        """
        Check if the latest checkpoint is stale (no progress in N seconds).

        Useful for detecting stuck sessions that need recovery.

        Args:
            thread_id: Thread ID to check
            stale_threshold_seconds: Seconds without progress to consider stale

        Returns:
            True if checkpoint is stale, False otherwise
        """
        try:
            with self.pool.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT
                            EXTRACT(EPOCH FROM (NOW() - to_timestamp((checkpoint->>'ts')::numeric))) as age_seconds
                        FROM checkpoints
                        WHERE thread_id = %s
                        AND checkpoint_ns = ''
                        ORDER BY checkpoint->>'ts' DESC
                        LIMIT 1
                        """,
                        (thread_id,)
                    )

                    result = cur.fetchone()

                    if result:
                        age_seconds = result[0]
                        is_stale = age_seconds > stale_threshold_seconds

                        self.logger.info(
                            f"Thread {thread_id} checkpoint age: {age_seconds:.1f}s "
                            f"(stale={is_stale})"
                        )

                        return is_stale

                    self.logger.info(f"No checkpoint found for thread {thread_id}")
                    return False

        except Exception as e:
            self.logger.error(f"Error checking checkpoint staleness: {e}")
            return False
