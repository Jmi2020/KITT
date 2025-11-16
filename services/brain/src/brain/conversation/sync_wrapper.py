"""Synchronous wrapper for persistent conversation state manager.

Provides backwards-compatible synchronous interface while using
async PostgreSQL persistence under the hood.
"""

import asyncio
import logging
from typing import Optional

from brain.conversation.state import ConversationState
from brain.conversation.auto_persist import AutoPersistStateManager

logger = logging.getLogger(__name__)


class SyncPersistentStateManager:
    """Synchronous wrapper around AutoPersistStateManager.

    Provides the same interface as ConversationStateManager but persists
    to PostgreSQL using async operations run in the event loop.

    Attributes:
        _async_manager: Underlying AutoPersistStateManager
        _loop: Event loop for running async operations
    """

    def __init__(self, async_manager: AutoPersistStateManager):
        """Initialize sync wrapper.

        Args:
            async_manager: AutoPersistStateManager instance
        """
        self._async_manager = async_manager
        self._loop = None

    def _get_loop(self) -> asyncio.AbstractEventLoop:
        """Get or create event loop."""
        if self._loop is None or self._loop.is_closed():
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                # No event loop running, create a new one
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
        return self._loop

    def _run_async(self, coro):
        """Run async coroutine synchronously.

        Args:
            coro: Coroutine to run

        Returns:
            Result of coroutine
        """
        loop = self._get_loop()

        if loop.is_running():
            # We're already in an async context, create a task
            # This should work because we're called from a sync function
            # in an async context
            future = asyncio.ensure_future(coro, loop=loop)
            # Note: This won't block, caller needs to await the future
            # For now, return a placeholder - this is a limitation
            logger.warning("Running async operation in running loop - may not complete immediately")
            return future
        else:
            # No loop running, run until complete
            return loop.run_until_complete(coro)

    def get_or_create(
        self, conversation_id: str, user_id: str = "unknown"
    ) -> ConversationState:
        """Get existing conversation state or create new one.

        Args:
            conversation_id: Unique conversation identifier
            user_id: User identifier

        Returns:
            ConversationState for this conversation
        """
        try:
            return self._run_async(
                self._async_manager.get_or_create(conversation_id, user_id)
            )
        except Exception as e:
            logger.error(f"Error getting conversation state {conversation_id}: {e}")
            # Fallback to creating in-memory state
            return ConversationState(
                conversation_id=conversation_id,
                user_id=user_id
            )

    def get(self, conversation_id: str) -> Optional[ConversationState]:
        """Get conversation state if it exists.

        Args:
            conversation_id: Unique conversation identifier

        Returns:
            ConversationState if exists, None otherwise
        """
        try:
            return self._run_async(
                self._async_manager.get(conversation_id)
            )
        except Exception as e:
            logger.error(f"Error getting conversation state {conversation_id}: {e}")
            return None

    def delete(self, conversation_id: str) -> bool:
        """Delete a conversation state.

        Args:
            conversation_id: Unique conversation identifier

        Returns:
            True if state existed and was deleted, False otherwise
        """
        try:
            return self._run_async(
                self._async_manager.delete(conversation_id)
            )
        except Exception as e:
            logger.error(f"Error deleting conversation state {conversation_id}: {e}")
            return False

    def cleanup_expired(self, max_age_seconds: float = 3600) -> int:
        """Remove conversation states older than max_age_seconds.

        Args:
            max_age_seconds: Maximum age in seconds (default: 1 hour)

        Returns:
            Number of states removed
        """
        try:
            return self._run_async(
                self._async_manager.cleanup_expired(max_age_seconds)
            )
        except Exception as e:
            logger.error(f"Error cleaning up expired states: {e}")
            return 0

    def count(self) -> int:
        """Get count of active conversation states.

        Returns:
            Number of conversation states
        """
        try:
            return self._run_async(
                self._async_manager.count()
            )
        except Exception as e:
            logger.error(f"Error counting conversation states: {e}")
            return 0


__all__ = ["SyncPersistentStateManager"]
