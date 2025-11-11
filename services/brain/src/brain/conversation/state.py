# noqa: D401
"""Conversation state management for multi-turn ReAct workflows."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from brain.agents.react_agent import AgentStep


@dataclass
class ConversationState:
    """State for a single conversation thread.

    Tracks history, pending confirmations, and metadata across multiple turns.
    """

    conversation_id: str
    user_id: str
    history: List[AgentStep] = field(default_factory=list)
    pending_confirmation: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def add_step(self, step: AgentStep) -> None:
        """Add a reasoning step to the conversation history."""
        self.history.append(step)
        self.updated_at = time.time()

    def set_pending_confirmation(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        confirmation_phrase: str,
        hazard_class: str,
        reason: str,
    ) -> None:
        """Set a pending confirmation request.

        Args:
            tool_name: Name of the tool awaiting confirmation
            tool_args: Arguments for the tool
            confirmation_phrase: Required phrase to confirm
            hazard_class: Hazard classification (low/medium/high)
            reason: Reason for requiring confirmation
        """
        self.pending_confirmation = {
            "tool_name": tool_name,
            "tool_args": tool_args,
            "confirmation_phrase": confirmation_phrase,
            "hazard_class": hazard_class,
            "reason": reason,
            "timestamp": time.time(),
        }
        self.updated_at = time.time()

    def clear_pending_confirmation(self) -> Optional[Dict[str, Any]]:
        """Clear and return the pending confirmation.

        Returns:
            The pending confirmation dict if one exists, None otherwise
        """
        pending = self.pending_confirmation
        self.pending_confirmation = None
        self.updated_at = time.time()
        return pending

    def has_pending_confirmation(self) -> bool:
        """Check if there's a pending confirmation."""
        return self.pending_confirmation is not None

    def is_confirmation_expired(self, timeout_seconds: float = 300) -> bool:
        """Check if pending confirmation has expired.

        Args:
            timeout_seconds: Timeout in seconds (default: 5 minutes)

        Returns:
            True if confirmation exists and is expired, False otherwise
        """
        if not self.pending_confirmation:
            return False

        timestamp = self.pending_confirmation.get("timestamp", 0)
        return (time.time() - timestamp) > timeout_seconds

    def update_metadata(self, key: str, value: Any) -> None:
        """Update a metadata field."""
        self.metadata[key] = value
        self.updated_at = time.time()


class ConversationStateManager:
    """Manages conversation states across multiple conversations.

    This is an in-memory implementation. For production, consider
    Redis or PostgreSQL for persistence.
    """

    def __init__(self) -> None:
        """Initialize the state manager."""
        self._states: Dict[str, ConversationState] = {}

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
        if conversation_id not in self._states:
            self._states[conversation_id] = ConversationState(
                conversation_id=conversation_id, user_id=user_id
            )
        return self._states[conversation_id]

    def get(self, conversation_id: str) -> Optional[ConversationState]:
        """Get conversation state if it exists.

        Args:
            conversation_id: Unique conversation identifier

        Returns:
            ConversationState if exists, None otherwise
        """
        return self._states.get(conversation_id)

    def delete(self, conversation_id: str) -> bool:
        """Delete a conversation state.

        Args:
            conversation_id: Unique conversation identifier

        Returns:
            True if state existed and was deleted, False otherwise
        """
        if conversation_id in self._states:
            del self._states[conversation_id]
            return True
        return False

    def cleanup_expired(self, max_age_seconds: float = 3600) -> int:
        """Remove conversation states older than max_age_seconds.

        Args:
            max_age_seconds: Maximum age in seconds (default: 1 hour)

        Returns:
            Number of states removed
        """
        now = time.time()
        expired = [
            cid
            for cid, state in self._states.items()
            if (now - state.updated_at) > max_age_seconds
        ]

        for cid in expired:
            del self._states[cid]

        return len(expired)

    def count(self) -> int:
        """Get count of active conversation states."""
        return len(self._states)


__all__ = ["ConversationState", "ConversationStateManager"]
