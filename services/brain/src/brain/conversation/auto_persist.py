"""Auto-persisting conversation state wrapper.

Wraps ConversationState to automatically persist changes to database
after each state modification. This ensures consistency and prevents
data loss without requiring manual save() calls.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

from brain.agents.types import AgentStep
from brain.conversation.state import ConversationState
from brain.conversation.persistent_state import PersistentConversationStateManager

logger = logging.getLogger(__name__)


class AutoPersistConversationState(ConversationState):
    """ConversationState that automatically persists changes.

    Wraps ConversationState and persists to database after each mutation.
    This prevents data loss and ensures hazard confirmations survive restarts.

    Attributes:
        _manager: PersistentConversationStateManager for database operations
        _persist_task: Background task for async persistence
    """

    def __init__(
        self,
        conversation_id: str,
        user_id: str,
        manager: PersistentConversationStateManager,
        **kwargs
    ):
        """Initialize auto-persisting conversation state.

        Args:
            conversation_id: Unique conversation identifier
            user_id: User identifier
            manager: PersistentConversationStateManager instance
            **kwargs: Additional ConversationState fields
        """
        super().__init__(conversation_id=conversation_id, user_id=user_id, **kwargs)
        self._manager = manager
        self._persist_task: Optional[asyncio.Task] = None

    def add_step(self, step: AgentStep) -> None:
        """Add a reasoning step and persist to database.

        Args:
            step: AgentStep to add to history
        """
        super().add_step(step)
        self._schedule_persist()

    def set_pending_confirmation(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        confirmation_phrase: str,
        hazard_class: str,
        reason: str,
    ) -> None:
        """Set pending confirmation and persist to database.

        CRITICAL: This immediately persists to ensure hazard confirmations
        survive restart. Double-execution of hazard operations must be prevented.

        Args:
            tool_name: Name of the tool awaiting confirmation
            tool_args: Arguments for the tool
            confirmation_phrase: Required phrase to confirm
            hazard_class: Hazard classification (low/medium/high)
            reason: Reason for requiring confirmation
        """
        super().set_pending_confirmation(
            tool_name, tool_args, confirmation_phrase, hazard_class, reason
        )

        # CRITICAL: Persist immediately for hazard operations
        self._schedule_persist(immediate=True)

        logger.warning(
            f"Pending confirmation set for {tool_name} (hazard: {hazard_class}) "
            f"in conversation {self.conversation_id} - PERSISTED TO DATABASE"
        )

    def clear_pending_confirmation(self) -> Optional[Dict[str, Any]]:
        """Clear pending confirmation and persist to database.

        Returns:
            The pending confirmation dict if one exists, None otherwise
        """
        pending = super().clear_pending_confirmation()

        if pending:
            # CRITICAL: Persist immediately when clearing hazard confirmation
            self._schedule_persist(immediate=True)

            logger.info(
                f"Pending confirmation cleared for {pending.get('tool_name')} "
                f"in conversation {self.conversation_id} - PERSISTED TO DATABASE"
            )

        return pending

    def update_metadata(self, key: str, value: Any) -> None:
        """Update metadata and persist to database.

        Args:
            key: Metadata key
            value: Metadata value
        """
        super().update_metadata(key, value)
        self._schedule_persist()

    def _schedule_persist(self, immediate: bool = False) -> None:
        """Schedule persistence to database.

        Args:
            immediate: If True, persist synchronously (blocks). Use for critical operations.
        """
        if immediate:
            # For critical operations (hazard confirmations), persist immediately
            # This runs in the event loop but blocks until complete
            try:
                # Create a new task and wait for it
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Schedule as background task if loop is running
                    asyncio.create_task(self._persist())
                else:
                    # Run synchronously if no loop
                    loop.run_until_complete(self._persist())
            except Exception as e:
                logger.error(f"Critical error persisting conversation state: {e}")
                # Re-raise for critical operations
                raise
        else:
            # For non-critical operations, debounce persistence
            if self._persist_task and not self._persist_task.done():
                self._persist_task.cancel()

            self._persist_task = asyncio.create_task(self._persist())

    async def _persist(self) -> None:
        """Persist state to database.

        Logs errors but does not raise to prevent disrupting conversation flow.
        """
        try:
            success = await self._manager.save(self)

            if not success:
                logger.error(
                    f"Failed to persist conversation state {self.conversation_id}"
                )
        except Exception as e:
            logger.error(
                f"Exception persisting conversation state {self.conversation_id}: {e}",
                exc_info=True
            )


class AutoPersistStateManager:
    """Wrapper around PersistentConversationStateManager that returns auto-persisting states.

    Provides the same interface as ConversationStateManager but returns
    AutoPersistConversationState instances that automatically save to database.

    Attributes:
        _persistent_manager: Underlying PersistentConversationStateManager
    """

    def __init__(self, persistent_manager: PersistentConversationStateManager):
        """Initialize auto-persist state manager.

        Args:
            persistent_manager: PersistentConversationStateManager instance
        """
        self._persistent_manager = persistent_manager

    async def get_or_create(
        self, conversation_id: str, user_id: str = "unknown"
    ) -> AutoPersistConversationState:
        """Get existing conversation state or create new one.

        Args:
            conversation_id: Unique conversation identifier
            user_id: User identifier

        Returns:
            AutoPersistConversationState for this conversation
        """
        # Load from database
        base_state = await self._persistent_manager.get_or_create(conversation_id, user_id)

        # Wrap in auto-persisting wrapper
        auto_state = AutoPersistConversationState(
            conversation_id=base_state.conversation_id,
            user_id=base_state.user_id,
            manager=self._persistent_manager,
            history=base_state.history,
            pending_confirmation=base_state.pending_confirmation,
            metadata=base_state.metadata,
            created_at=base_state.created_at,
            updated_at=base_state.updated_at
        )

        return auto_state

    async def get(self, conversation_id: str) -> Optional[AutoPersistConversationState]:
        """Get conversation state if it exists.

        Args:
            conversation_id: Unique conversation identifier

        Returns:
            AutoPersistConversationState if exists, None otherwise
        """
        base_state = await self._persistent_manager.get(conversation_id)

        if not base_state:
            return None

        # Wrap in auto-persisting wrapper
        auto_state = AutoPersistConversationState(
            conversation_id=base_state.conversation_id,
            user_id=base_state.user_id,
            manager=self._persistent_manager,
            history=base_state.history,
            pending_confirmation=base_state.pending_confirmation,
            metadata=base_state.metadata,
            created_at=base_state.created_at,
            updated_at=base_state.updated_at
        )

        return auto_state

    async def delete(self, conversation_id: str) -> bool:
        """Delete a conversation state.

        Args:
            conversation_id: Unique conversation identifier

        Returns:
            True if state existed and was deleted, False otherwise
        """
        return await self._persistent_manager.delete(conversation_id)

    async def cleanup_expired(self, max_age_seconds: float = 3600) -> int:
        """Remove conversation states older than max_age_seconds.

        Args:
            max_age_seconds: Maximum age in seconds (default: 1 hour)

        Returns:
            Number of states removed
        """
        return await self._persistent_manager.cleanup_expired(max_age_seconds)

    async def count(self) -> int:
        """Get count of active conversation states.

        Returns:
            Number of conversation states
        """
        return await self._persistent_manager.count()


__all__ = ["AutoPersistConversationState", "AutoPersistStateManager"]
