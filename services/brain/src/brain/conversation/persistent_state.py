"""PostgreSQL-backed persistent conversation state management.

Provides durable storage for conversation state including:
- Agent reasoning history
- Pending hazard confirmations
- Conversation metadata

This prevents data loss on service restart and ensures
hazard operations cannot be double-executed.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional
from uuid import UUID

from psycopg_pool import AsyncConnectionPool
from psycopg.types.json import Json

from brain.agents.types import AgentStep
from brain.conversation.state import ConversationState

logger = logging.getLogger(__name__)


class PersistentConversationStateManager:
    """PostgreSQL-backed conversation state manager.

    Persists conversation state to PostgreSQL for durability across restarts.
    Critical for preventing double-execution of hazard operations.

    Attributes:
        pool: Async PostgreSQL connection pool
    """

    def __init__(self, connection_pool: AsyncConnectionPool):
        """Initialize persistent state manager.

        Args:
            connection_pool: AsyncConnectionPool for PostgreSQL
        """
        self.pool = connection_pool
        logger.info("PersistentConversationStateManager initialized")

    async def get_or_create(
        self, conversation_id: str, user_id: str = "unknown"
    ) -> ConversationState:
        """Get existing conversation state or create new one.

        Args:
            conversation_id: Unique conversation identifier
            user_id: User identifier

        Returns:
            ConversationState for this conversation
        """
        # Try to load from database
        state = await self.get(conversation_id)

        if state:
            return state

        # Create new state
        state = ConversationState(
            conversation_id=conversation_id,
            user_id=user_id
        )

        # Persist to database
        await self._persist(state)

        logger.info(f"Created new conversation state: {conversation_id}")
        return state

    async def get(self, conversation_id: str) -> Optional[ConversationState]:
        """Get conversation state from database.

        Args:
            conversation_id: Unique conversation identifier

        Returns:
            ConversationState if exists, None otherwise
        """
        try:
            async with self.pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        SELECT
                            id, context_key, user_id,
                            agent_history, pending_confirmation,
                            conversation_metadata, created_at, updated_at
                        FROM conversation_sessions
                        WHERE id = %s OR context_key = %s
                        """,
                        (conversation_id, conversation_id)
                    )

                    row = await cur.fetchone()

                    if not row:
                        return None

                    # Deserialize state from database
                    state = self._deserialize_state(row)
                    return state

        except Exception as e:
            logger.error(f"Error loading conversation state {conversation_id}: {e}")
            return None

    async def save(self, state: ConversationState) -> bool:
        """Save conversation state to database.

        Args:
            state: ConversationState to persist

        Returns:
            True if successful, False otherwise
        """
        return await self._persist(state)

    async def delete(self, conversation_id: str) -> bool:
        """Delete a conversation state from database.

        Args:
            conversation_id: Unique conversation identifier

        Returns:
            True if state existed and was deleted, False otherwise
        """
        try:
            async with self.pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        DELETE FROM conversation_sessions
                        WHERE id = %s OR context_key = %s
                        """,
                        (conversation_id, conversation_id)
                    )
                    await conn.commit()

                    deleted = cur.rowcount > 0

                    if deleted:
                        logger.info(f"Deleted conversation state: {conversation_id}")

                    return deleted

        except Exception as e:
            logger.error(f"Error deleting conversation state {conversation_id}: {e}")
            return False

    async def cleanup_expired(self, max_age_seconds: float = 3600) -> int:
        """Remove conversation states older than max_age_seconds.

        Args:
            max_age_seconds: Maximum age in seconds (default: 1 hour)

        Returns:
            Number of states removed
        """
        try:
            async with self.pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        DELETE FROM conversation_sessions
                        WHERE updated_at < NOW() - INTERVAL '%s seconds'
                        """,
                        (max_age_seconds,)
                    )
                    await conn.commit()

                    deleted_count = cur.rowcount

                    if deleted_count > 0:
                        logger.info(f"Cleaned up {deleted_count} expired conversation states")

                    return deleted_count

        except Exception as e:
            logger.error(f"Error cleaning up expired states: {e}")
            return 0

    async def count(self) -> int:
        """Get count of active conversation states.

        Returns:
            Number of conversation states in database
        """
        try:
            async with self.pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("SELECT COUNT(*) FROM conversation_sessions")
                    row = await cur.fetchone()
                    return row[0] if row else 0

        except Exception as e:
            logger.error(f"Error counting conversation states: {e}")
            return 0

    async def get_pending_confirmations(self) -> List[Dict[str, Any]]:
        """Get all conversations with pending confirmations.

        Useful for recovery/monitoring.

        Returns:
            List of dicts with conversation_id and pending_confirmation
        """
        try:
            async with self.pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        SELECT id, context_key, user_id, pending_confirmation
                        FROM conversation_sessions
                        WHERE pending_confirmation IS NOT NULL
                        """
                    )

                    rows = await cur.fetchall()

                    return [
                        {
                            "conversation_id": row[0] or row[1],
                            "user_id": row[2],
                            "pending_confirmation": row[3]
                        }
                        for row in rows
                    ]

        except Exception as e:
            logger.error(f"Error getting pending confirmations: {e}")
            return []

    # Private methods

    async def _persist(self, state: ConversationState) -> bool:
        """Persist conversation state to database.

        Args:
            state: ConversationState to persist

        Returns:
            True if successful, False otherwise
        """
        try:
            # Serialize state to JSON-compatible format
            serialized = self._serialize_state(state)

            async with self.pool.connection() as conn:
                async with conn.cursor() as cur:
                    # Upsert conversation state
                    await cur.execute(
                        """
                        INSERT INTO conversation_sessions (
                            id, context_key, user_id,
                            agent_history, pending_confirmation, conversation_metadata,
                            state, active_participants,
                            last_message_at, created_at, updated_at
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s,
                            NOW(), NOW(), NOW()
                        )
                        ON CONFLICT (id) DO UPDATE SET
                            user_id = EXCLUDED.user_id,
                            agent_history = EXCLUDED.agent_history,
                            pending_confirmation = EXCLUDED.pending_confirmation,
                            conversation_metadata = EXCLUDED.conversation_metadata,
                            state = EXCLUDED.state,
                            updated_at = NOW()
                        """,
                        (
                            serialized["id"],
                            serialized["context_key"],
                            serialized["user_id"],
                            Json(serialized["agent_history"]),
                            Json(serialized["pending_confirmation"]) if serialized["pending_confirmation"] else None,
                            Json(serialized["conversation_metadata"]),
                            Json({"updated_at": serialized["updated_at"]}),  # Legacy state field
                            Json([]),  # active_participants
                        )
                    )
                    await conn.commit()

                    logger.debug(f"Persisted conversation state: {state.conversation_id}")
                    return True

        except Exception as e:
            logger.error(f"Error persisting conversation state {state.conversation_id}: {e}")
            return False

    def _serialize_state(self, state: ConversationState) -> Dict[str, Any]:
        """Serialize ConversationState to JSON-compatible dict.

        Args:
            state: ConversationState to serialize

        Returns:
            JSON-compatible dict
        """
        return {
            "id": state.conversation_id,
            "context_key": state.conversation_id,
            "user_id": state.user_id,
            "agent_history": [self._serialize_agent_step(step) for step in state.history],
            "pending_confirmation": state.pending_confirmation,
            "conversation_metadata": state.metadata,
            "created_at": state.created_at,
            "updated_at": state.updated_at
        }

    def _serialize_agent_step(self, step: AgentStep) -> Dict[str, Any]:
        """Serialize AgentStep to JSON-compatible dict.

        Args:
            step: AgentStep to serialize

        Returns:
            JSON-compatible dict
        """
        return {
            "thought": step.thought,
            "action": step.action,
            "action_input": step.action_input,
            "observation": step.observation,
            "error": step.error,
            "timestamp": getattr(step, "timestamp", time.time())
        }

    def _deserialize_state(self, row: tuple) -> ConversationState:
        """Deserialize database row to ConversationState.

        Args:
            row: Database row tuple

        Returns:
            ConversationState object
        """
        (
            conversation_id,
            context_key,
            user_id,
            agent_history,
            pending_confirmation,
            conversation_metadata,
            created_at,
            updated_at
        ) = row

        # Use context_key if id is None (legacy compatibility)
        conv_id = conversation_id or context_key

        # Deserialize agent history
        history = [
            self._deserialize_agent_step(step_dict)
            for step_dict in (agent_history or [])
        ]

        # Create ConversationState
        state = ConversationState(
            conversation_id=str(conv_id),
            user_id=str(user_id) if user_id else "unknown",
            history=history,
            pending_confirmation=pending_confirmation,
            metadata=conversation_metadata or {},
            created_at=created_at.timestamp() if created_at else time.time(),
            updated_at=updated_at.timestamp() if updated_at else time.time()
        )

        return state

    def _deserialize_agent_step(self, step_dict: Dict[str, Any]) -> AgentStep:
        """Deserialize dict to AgentStep.

        Args:
            step_dict: JSON dict with agent step data

        Returns:
            AgentStep object
        """
        return AgentStep(
            thought=step_dict.get("thought", ""),
            action=step_dict.get("action", ""),
            action_input=step_dict.get("action_input"),
            observation=step_dict.get("observation"),
            error=step_dict.get("error")
        )


__all__ = ["PersistentConversationStateManager"]
