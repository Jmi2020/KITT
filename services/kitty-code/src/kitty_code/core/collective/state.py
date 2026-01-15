"""
State machine definitions for the Tiered Collective Architecture.

Implements the state machine:
IDLE → ROUTING → PLANNING → EXECUTING → JUDGING → (REVISING) → COMPLETE
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Dict, List, Optional


class CollectiveState(Enum):
    """
    State machine states for collective orchestration.

    Flow:
    1. IDLE: Waiting for user input
    2. ROUTING: Analyzing task complexity
    3. DIRECT_EXECUTE: Simple task, bypass collective
    4. PLANNING: Planner creating task plan
    5. EXECUTING: Executor implementing current step
    6. JUDGING: Judge validating executor output
    7. REVISING: Applying Judge feedback
    8. ESCALATE: Re-planning after failure
    9. COMPLETE: Task finished successfully
    10. ERROR: Unrecoverable failure
    """

    IDLE = auto()
    ROUTING = auto()
    DIRECT_EXECUTE = auto()
    PLANNING = auto()
    EXECUTING = auto()
    JUDGING = auto()
    REVISING = auto()
    ESCALATE = auto()
    COMPLETE = auto()
    ERROR = auto()

    def is_terminal(self) -> bool:
        """Check if this is a terminal state."""
        return self in (CollectiveState.IDLE, CollectiveState.COMPLETE, CollectiveState.ERROR)

    def requires_model(self) -> bool:
        """Check if this state requires model inference."""
        return self in (
            CollectiveState.PLANNING,
            CollectiveState.EXECUTING,
            CollectiveState.JUDGING,
            CollectiveState.DIRECT_EXECUTE,
        )

    def next_states(self) -> List["CollectiveState"]:
        """Return valid next states from current state."""
        transitions = {
            CollectiveState.IDLE: [CollectiveState.ROUTING],
            CollectiveState.ROUTING: [CollectiveState.DIRECT_EXECUTE, CollectiveState.PLANNING],
            CollectiveState.DIRECT_EXECUTE: [CollectiveState.COMPLETE],
            CollectiveState.PLANNING: [CollectiveState.EXECUTING, CollectiveState.IDLE],
            CollectiveState.EXECUTING: [CollectiveState.JUDGING, CollectiveState.ESCALATE],
            CollectiveState.JUDGING: [
                CollectiveState.COMPLETE,
                CollectiveState.REVISING,
                CollectiveState.ESCALATE,
            ],
            CollectiveState.REVISING: [CollectiveState.EXECUTING, CollectiveState.ESCALATE],
            CollectiveState.ESCALATE: [CollectiveState.PLANNING, CollectiveState.ERROR],
            CollectiveState.COMPLETE: [CollectiveState.IDLE],
            CollectiveState.ERROR: [CollectiveState.IDLE],
        }
        return transitions.get(self, [])


@dataclass
class StateTransition:
    """Record of a state transition."""

    from_state: CollectiveState
    to_state: CollectiveState
    timestamp: datetime = field(default_factory=datetime.now)
    reason: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CollectiveContext:
    """
    Context maintained throughout collective orchestration.

    Tracks state, history, and accumulated data as the collective
    processes a user request through Planner → Executor → Judge.
    """

    # Current state
    state: CollectiveState = CollectiveState.IDLE

    # Original user input
    user_input: str = ""

    # Routing decision
    routing_confidence: float = 0.0
    routing_mode: str = "direct"  # "direct" or "collective"

    # Current plan (from Planner)
    current_plan: Optional[Any] = None  # TaskPlan
    current_step_index: int = 0

    # Execution history
    execution_results: List[Any] = field(default_factory=list)  # List[ExecutionResult]

    # Judgment history
    judgments: List[Any] = field(default_factory=list)  # List[Judgment]

    # Revision tracking
    revision_count: int = 0
    escalation_count: int = 0

    # State history for debugging
    state_history: List[StateTransition] = field(default_factory=list)

    # Timing
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Error info
    error_message: Optional[str] = None

    def transition_to(
        self,
        new_state: CollectiveState,
        reason: Optional[str] = None,
        **metadata: Any,
    ) -> bool:
        """
        Attempt to transition to a new state.

        Args:
            new_state: Target state
            reason: Human-readable reason for transition
            **metadata: Additional context for the transition

        Returns:
            True if transition successful, False if invalid
        """
        # Validate transition
        if new_state not in self.state.next_states():
            return False

        # Record transition
        transition = StateTransition(
            from_state=self.state,
            to_state=new_state,
            reason=reason,
            metadata=metadata,
        )
        self.state_history.append(transition)

        # Update state
        self.state = new_state

        # Update timing
        if new_state == CollectiveState.ROUTING and self.started_at is None:
            self.started_at = datetime.now()
        elif new_state.is_terminal():
            self.completed_at = datetime.now()

        return True

    def get_current_step(self) -> Optional[Any]:
        """Get the current step from the plan."""
        if self.current_plan is None:
            return None
        if not hasattr(self.current_plan, "steps"):
            return None
        if self.current_step_index >= len(self.current_plan.steps):
            return None
        return self.current_plan.steps[self.current_step_index]

    def advance_step(self) -> bool:
        """Advance to the next step in the plan."""
        if self.current_plan is None:
            return False
        if not hasattr(self.current_plan, "steps"):
            return False
        if self.current_step_index + 1 >= len(self.current_plan.steps):
            return False
        self.current_step_index += 1
        return True

    def is_plan_complete(self) -> bool:
        """Check if all steps in the plan have been executed."""
        if self.current_plan is None:
            return True
        if not hasattr(self.current_plan, "steps"):
            return True
        return self.current_step_index >= len(self.current_plan.steps) - 1

    def get_elapsed_time_ms(self) -> Optional[int]:
        """Get elapsed time in milliseconds."""
        if self.started_at is None:
            return None
        end = self.completed_at or datetime.now()
        return int((end - self.started_at).total_seconds() * 1000)

    def can_revise(self, max_revisions: int) -> bool:
        """Check if we can attempt another revision."""
        return self.revision_count < max_revisions

    def can_escalate(self, max_escalations: int) -> bool:
        """Check if we can escalate to re-planning."""
        return self.escalation_count < max_escalations

    def record_revision(self) -> None:
        """Record a revision attempt."""
        self.revision_count += 1

    def record_escalation(self) -> None:
        """Record an escalation to re-planning."""
        self.escalation_count += 1

    def reset_for_new_request(self, user_input: str) -> None:
        """Reset context for a new user request."""
        self.state = CollectiveState.IDLE
        self.user_input = user_input
        self.routing_confidence = 0.0
        self.routing_mode = "direct"
        self.current_plan = None
        self.current_step_index = 0
        self.execution_results = []
        self.judgments = []
        self.revision_count = 0
        self.escalation_count = 0
        self.state_history = []
        self.started_at = None
        self.completed_at = None
        self.error_message = None

    def to_debug_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for debugging/logging."""
        return {
            "state": self.state.name,
            "user_input": self.user_input[:100] + "..." if len(self.user_input) > 100 else self.user_input,
            "routing": {
                "mode": self.routing_mode,
                "confidence": self.routing_confidence,
            },
            "plan": {
                "has_plan": self.current_plan is not None,
                "current_step": self.current_step_index,
            },
            "history": {
                "execution_count": len(self.execution_results),
                "judgment_count": len(self.judgments),
                "revision_count": self.revision_count,
                "escalation_count": self.escalation_count,
            },
            "timing": {
                "elapsed_ms": self.get_elapsed_time_ms(),
            },
            "error": self.error_message,
        }
