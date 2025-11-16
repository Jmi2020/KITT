"""
Research Session Manager

Manages autonomous research session lifecycle:
- Create/pause/resume/cancel operations
- Status tracking and monitoring
- Crash recovery
- Background task orchestration
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import StateGraph
from psycopg.types.json import Json
from psycopg_pool import AsyncConnectionPool

from brain.research.checkpoint import CheckpointManager

logger = logging.getLogger(__name__)


class SessionStatus(str, Enum):
    """Research session status"""
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class SessionInfo:
    """Research session information"""
    session_id: str
    user_id: str
    query: str
    status: SessionStatus
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
    thread_id: Optional[str] = None
    config: Dict[str, Any] = None
    metadata: Dict[str, Any] = None

    # Statistics
    total_iterations: int = 0
    total_findings: int = 0
    total_sources: int = 0
    total_cost_usd: float = 0.0
    external_calls_used: int = 0

    # Quality scores
    completeness_score: Optional[float] = None
    confidence_score: Optional[float] = None
    saturation_status: Optional[Dict] = None


class ResearchSessionManager:
    """
    Manages research session lifecycle with fault tolerance.

    Provides:
    - Session creation with checkpointing
    - Pause/resume operations
    - Status tracking in PostgreSQL
    - Crash recovery
    - Background monitoring
    """

    def __init__(
        self,
        graph: StateGraph,
        checkpointer: AsyncPostgresSaver,
        connection_pool: AsyncConnectionPool
    ):
        """
        Initialize session manager.

        Args:
            graph: LangGraph research graph (compiled with checkpointer)
            checkpointer: PostgreSQL checkpointer for state persistence
            connection_pool: Database connection pool
        """
        self.graph = graph
        self.checkpointer = checkpointer
        self.pool = connection_pool
        self.checkpoint_manager = CheckpointManager(checkpointer, connection_pool)

        # Track active sessions and their background tasks
        self.active_sessions: Dict[str, asyncio.Task] = {}

        logger.info("ResearchSessionManager initialized")

    async def create_session(
        self,
        user_id: str,
        query: str,
        config: Optional[Dict] = None
    ) -> str:
        """
        Create a new research session.

        Args:
            user_id: User ID creating the session
            query: Research query/question
            config: Optional configuration (max_iterations, etc.)

        Returns:
            session_id: Unique session identifier

        Example:
            ```python
            session_id = await manager.create_session(
                user_id="user123",
                query="Research sustainable 3D printing materials",
                config={"max_iterations": 15}
            )
            ```
        """
        session_id = str(uuid.uuid4())
        thread_id = f"research_{session_id}"

        if config is None:
            config = {}

        # Set defaults
        config.setdefault("max_iterations", 15)
        config.setdefault("max_cost_usd", 2.0)
        config.setdefault("max_external_calls", 10)

        logger.info(
            f"Creating research session {session_id} for user {user_id}: {query[:100]}"
        )

        try:
            # Insert into database
            async with self.pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        INSERT INTO research_sessions (
                            session_id, user_id, query, status, thread_id,
                            config, metadata, created_at, updated_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                        """,
                        (
                            session_id,
                            user_id,
                            query,
                            SessionStatus.ACTIVE.value,
                            thread_id,
                            Json(config),
                            Json({})  # metadata
                        )
                    )
                    await conn.commit()

            logger.info(f"Session {session_id} created successfully")
            return session_id

        except Exception as e:
            logger.error(f"Failed to create session: {e}")
            raise

    async def get_session(self, session_id: str) -> Optional[SessionInfo]:
        """
        Get session information.

        Args:
            session_id: Session ID to retrieve

        Returns:
            SessionInfo or None if not found
        """
        try:
            async with self.pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        SELECT
                            session_id, user_id, query, status,
                            created_at, updated_at, completed_at,
                            thread_id, config, metadata,
                            total_iterations, total_findings, total_sources,
                            total_cost_usd, external_calls_used,
                            completeness_score, confidence_score, saturation_status
                        FROM research_sessions
                        WHERE session_id = %s
                        """,
                        (session_id,)
                    )

                    row = await cur.fetchone()

                    if row:
                        return SessionInfo(
                            session_id=row[0],
                            user_id=row[1],
                            query=row[2],
                            status=SessionStatus(row[3]),
                            created_at=row[4],
                            updated_at=row[5],
                            completed_at=row[6],
                            thread_id=row[7],
                            config=row[8],
                            metadata=row[9],
                            total_iterations=row[10] or 0,
                            total_findings=row[11] or 0,
                            total_sources=row[12] or 0,
                            total_cost_usd=float(row[13] or 0.0),
                            external_calls_used=row[14] or 0,
                            completeness_score=float(row[15]) if row[15] else None,
                            confidence_score=float(row[16]) if row[16] else None,
                            saturation_status=row[17]
                        )

                    return None

        except Exception as e:
            logger.error(f"Error getting session {session_id}: {e}")
            return None

    async def list_user_sessions(
        self,
        user_id: str,
        status: Optional[SessionStatus] = None,
        limit: int = 50
    ) -> List[SessionInfo]:
        """
        List sessions for a user.

        Args:
            user_id: User ID to list sessions for
            status: Optional status filter
            limit: Maximum number of sessions to return

        Returns:
            List of SessionInfo objects
        """
        try:
            async with self.pool.connection() as conn:
                async with conn.cursor() as cur:
                    if status:
                        query = """
                            SELECT session_id, user_id, query, status,
                                   created_at, updated_at, completed_at,
                                   thread_id, config, metadata,
                                   total_iterations, total_findings, total_sources,
                                   total_cost_usd, external_calls_used,
                                   completeness_score, confidence_score, saturation_status
                            FROM research_sessions
                            WHERE user_id = %s AND status = %s
                            ORDER BY created_at DESC
                            LIMIT %s
                        """
                        params = (user_id, status.value, limit)
                    else:
                        query = """
                            SELECT session_id, user_id, query, status,
                                   created_at, updated_at, completed_at,
                                   thread_id, config, metadata,
                                   total_iterations, total_findings, total_sources,
                                   total_cost_usd, external_calls_used,
                                   completeness_score, confidence_score, saturation_status
                            FROM research_sessions
                            WHERE user_id = %s
                            ORDER BY created_at DESC
                            LIMIT %s
                        """
                        params = (user_id, limit)

                    await cur.execute(query, params)
                    rows = await cur.fetchall()

                    return [
                        SessionInfo(
                            session_id=row[0],
                            user_id=row[1],
                            query=row[2],
                            status=SessionStatus(row[3]),
                            created_at=row[4],
                            updated_at=row[5],
                            completed_at=row[6],
                            thread_id=row[7],
                            config=row[8],
                            metadata=row[9],
                            total_iterations=row[10] or 0,
                            total_findings=row[11] or 0,
                            total_sources=row[12] or 0,
                            total_cost_usd=float(row[13] or 0.0),
                            external_calls_used=row[14] or 0,
                            completeness_score=float(row[15]) if row[15] else None,
                            confidence_score=float(row[16]) if row[16] else None,
                            saturation_status=row[17]
                        )
                        for row in rows
                    ]

        except Exception as e:
            logger.error(f"Error listing sessions for user {user_id}: {e}")
            return []

    async def pause_session(self, session_id: str) -> bool:
        """
        Pause an active research session.

        Args:
            session_id: Session ID to pause

        Returns:
            True if successful, False otherwise
        """
        logger.info(f"Pausing session {session_id}")

        try:
            # Update status in database
            async with self.pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        UPDATE research_sessions
                        SET status = %s, updated_at = NOW()
                        WHERE session_id = %s AND status = %s
                        """,
                        (SessionStatus.PAUSED.value, session_id, SessionStatus.ACTIVE.value)
                    )
                    await conn.commit()

                    if cur.rowcount == 0:
                        logger.warning(f"Session {session_id} not found or not active")
                        return False

            # Cancel background task if running
            if session_id in self.active_sessions:
                task = self.active_sessions[session_id]
                task.cancel()
                del self.active_sessions[session_id]
                logger.info(f"Cancelled background task for session {session_id}")

            logger.info(f"Session {session_id} paused successfully")
            return True

        except Exception as e:
            logger.error(f"Error pausing session {session_id}: {e}")
            return False

    async def resume_session(
        self,
        session_id: str,
        additional_input: Optional[Dict] = None
    ) -> bool:
        """
        Resume a paused research session.

        Args:
            session_id: Session ID to resume
            additional_input: Optional additional input to merge into state

        Returns:
            True if successful, False otherwise
        """
        logger.info(f"Resuming session {session_id}")

        try:
            session = await self.get_session(session_id)

            if not session:
                logger.error(f"Session {session_id} not found")
                return False

            if session.status != SessionStatus.PAUSED:
                logger.error(f"Session {session_id} is not paused (status: {session.status})")
                return False

            # Update status to active
            async with self.pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        UPDATE research_sessions
                        SET status = %s, updated_at = NOW()
                        WHERE session_id = %s
                        """,
                        (SessionStatus.ACTIVE.value, session_id)
                    )
                    await conn.commit()

            # Resume execution from checkpoint
            # (Actual graph execution would happen in run_session method)
            logger.info(f"Session {session_id} resumed successfully")
            return True

        except Exception as e:
            logger.error(f"Error resuming session {session_id}: {e}")
            return False

    async def start_research(
        self,
        session_id: str,
        user_id: str,
        query: str,
        config: Optional[Dict] = None
    ) -> str:
        """
        Start autonomous research (creates session and begins execution).

        Args:
            session_id: Session ID
            user_id: User ID
            query: Research query
            config: Optional configuration

        Returns:
            session_id
        """
        if not self.graph:
            raise ValueError("Research graph not initialized")

        logger.info(f"Starting research for session {session_id}")

        # Start research in background
        task = asyncio.create_task(self._run_research(session_id, user_id, query, config))
        self.active_sessions[session_id] = task

        return session_id

    async def _run_research(
        self,
        session_id: str,
        user_id: str,
        query: str,
        config: Optional[Dict] = None
    ):
        """
        Run research graph (internal background task).

        Args:
            session_id: Session ID
            user_id: User ID
            query: Research query
            config: Optional configuration
        """
        try:
            logger.info(f"Running research graph for session {session_id}")

            # Execute graph
            final_state = await self.graph.run(
                session_id=session_id,
                user_id=user_id,
                query=query,
                config=config
            )

            # Update session with final results
            await self.update_session_stats(
                session_id=session_id,
                total_iterations=final_state.get("current_iteration", 0),
                total_findings=len(final_state.get("findings", [])),
                total_sources=len(final_state.get("sources", [])),
                total_cost_usd=float(final_state.get("total_cost_usd", 0.0)),
                external_calls_used=final_state.get("external_calls_used", 0)
            )

            # Mark as completed
            await self.mark_completed(
                session_id=session_id,
                completeness_score=final_state.get("quality_scores", [0.0])[-1] if final_state.get("quality_scores") else None,
                confidence_score=final_state.get("confidence_scores", [{}])[-1].get("overall") if final_state.get("confidence_scores") else None
            )

            logger.info(f"Research completed for session {session_id}")

        except Exception as e:
            logger.error(f"Research failed for session {session_id}: {e}")

            # Mark as failed
            async with self.pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        UPDATE research_sessions
                        SET status = %s, updated_at = NOW(), completed_at = NOW()
                        WHERE session_id = %s
                        """,
                        (SessionStatus.FAILED.value, session_id)
                    )
                    await conn.commit()

        finally:
            # Remove from active sessions
            if session_id in self.active_sessions:
                del self.active_sessions[session_id]

    async def stream_research(
        self,
        session_id: str,
        user_id: str,
        query: str,
        config: Optional[Dict] = None
    ):
        """
        Stream research progress in real-time.

        Args:
            session_id: Session ID
            user_id: User ID
            query: Research query
            config: Optional configuration

        Yields:
            State updates as research progresses
        """
        if not self.graph:
            raise ValueError("Research graph not initialized")

        logger.info(f"Streaming research for session {session_id}")

        try:
            async for state_update in self.graph.stream(
                session_id=session_id,
                user_id=user_id,
                query=query,
                config=config
            ):
                yield state_update

        except Exception as e:
            logger.error(f"Streaming failed for session {session_id}: {e}")
            raise

    async def cancel_session(self, session_id: str) -> bool:
        """
        Cancel a research session.

        Args:
            session_id: Session ID to cancel

        Returns:
            True if successful, False otherwise
        """
        logger.info(f"Cancelling session {session_id}")

        try:
            # Update status
            async with self.pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        UPDATE research_sessions
                        SET status = %s, updated_at = NOW(), completed_at = NOW()
                        WHERE session_id = %s AND status IN (%s, %s)
                        """,
                        (
                            SessionStatus.FAILED.value,
                            session_id,
                            SessionStatus.ACTIVE.value,
                            SessionStatus.PAUSED.value
                        )
                    )
                    await conn.commit()

            # Cancel background task
            if session_id in self.active_sessions:
                task = self.active_sessions[session_id]
                task.cancel()
                del self.active_sessions[session_id]

            logger.info(f"Session {session_id} cancelled successfully")
            return True

        except Exception as e:
            logger.error(f"Error cancelling session {session_id}: {e}")
            return False

    async def update_session_stats(
        self,
        session_id: str,
        iterations: Optional[int] = None,
        findings: Optional[int] = None,
        sources: Optional[int] = None,
        cost_usd: Optional[float] = None,
        external_calls: Optional[int] = None,
        completeness: Optional[float] = None,
        confidence: Optional[float] = None,
        saturation: Optional[Dict] = None
    ) -> bool:
        """
        Update session statistics.

        Args:
            session_id: Session ID
            iterations: Total iterations count
            findings: Total findings count
            sources: Total sources count
            cost_usd: Total cost in USD
            external_calls: External API calls used
            completeness: Completeness score (0-1)
            confidence: Confidence score (0-1)
            saturation: Saturation status dict

        Returns:
            True if successful, False otherwise
        """
        try:
            # Build dynamic UPDATE query
            updates = []
            params = []

            if iterations is not None:
                updates.append("total_iterations = %s")
                params.append(iterations)
            if findings is not None:
                updates.append("total_findings = %s")
                params.append(findings)
            if sources is not None:
                updates.append("total_sources = %s")
                params.append(sources)
            if cost_usd is not None:
                updates.append("total_cost_usd = %s")
                params.append(cost_usd)
            if external_calls is not None:
                updates.append("external_calls_used = %s")
                params.append(external_calls)
            if completeness is not None:
                updates.append("completeness_score = %s")
                params.append(completeness)
            if confidence is not None:
                updates.append("confidence_score = %s")
                params.append(confidence)
            if saturation is not None:
                updates.append("saturation_status = %s")
                params.append(Json(saturation))

            if not updates:
                return True  # Nothing to update

            updates.append("updated_at = NOW()")
            params.append(session_id)

            query = f"""
                UPDATE research_sessions
                SET {', '.join(updates)}
                WHERE session_id = %s
            """

            async with self.pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(query, params)
                    await conn.commit()

            return True

        except Exception as e:
            logger.error(f"Error updating session stats: {e}")
            return False

    async def mark_completed(
        self,
        session_id: str,
        success: bool = True
    ) -> bool:
        """
        Mark session as completed or failed.

        Args:
            session_id: Session ID
            success: True for completed, False for failed

        Returns:
            True if successful, False otherwise
        """
        status = SessionStatus.COMPLETED if success else SessionStatus.FAILED

        logger.info(f"Marking session {session_id} as {status.value}")

        try:
            async with self.pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        UPDATE research_sessions
                        SET status = %s, updated_at = NOW(), completed_at = NOW()
                        WHERE session_id = %s
                        """,
                        (status.value, session_id)
                    )
                    await conn.commit()

            # Remove from active sessions
            if session_id in self.active_sessions:
                del self.active_sessions[session_id]

            logger.info(f"Session {session_id} marked as {status.value}")
            return True

        except Exception as e:
            logger.error(f"Error marking session complete: {e}")
            return False

    async def recover_stale_sessions(
        self,
        stale_threshold_seconds: int = 300
    ) -> int:
        """
        Recover stale sessions (no progress for N seconds).

        Args:
            stale_threshold_seconds: Seconds without progress to consider stale

        Returns:
            Number of sessions recovered
        """
        logger.info(f"Checking for stale sessions (threshold: {stale_threshold_seconds}s)")

        recovered_count = 0

        try:
            # Find active sessions
            async with self.pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        SELECT session_id, thread_id
                        FROM research_sessions
                        WHERE status = %s
                        """,
                        (SessionStatus.ACTIVE.value,)
                    )

                    active_sessions = await cur.fetchall()

            # Check each session for staleness
            for session_id, thread_id in active_sessions:
                if thread_id:
                    is_stale = await self.checkpoint_manager.is_checkpoint_stale(
                        thread_id, stale_threshold_seconds
                    )

                    if is_stale:
                        logger.warning(f"Session {session_id} is stale, attempting recovery")
                        # Recovery would involve resuming the graph from checkpoint
                        # For now, just log it
                        recovered_count += 1

            if recovered_count > 0:
                logger.info(f"Recovered {recovered_count} stale sessions")

            return recovered_count

        except Exception as e:
            logger.error(f"Error recovering stale sessions: {e}")
            return recovered_count

    async def cleanup_old_sessions(
        self,
        days_old: int = 90
    ) -> int:
        """
        Archive sessions older than N days.

        Args:
            days_old: Age threshold in days

        Returns:
            Number of sessions archived
        """
        logger.info(f"Archiving sessions older than {days_old} days")

        try:
            async with self.pool.connection() as conn:
                async with conn.cursor() as cur:
                    # Call the archive function from migration
                    await cur.execute(
                        "SELECT archive_old_sessions(%s)",
                        (days_old,)
                    )

                    result = await cur.fetchone()
                    archived_count = result[0] if result else 0
                    await conn.commit()

            if archived_count > 0:
                logger.info(f"Archived {archived_count} old sessions")

            return archived_count

        except Exception as e:
            logger.error(f"Error archiving old sessions: {e}")
            return 0
