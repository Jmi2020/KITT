"""Tests for CollectiveState and CollectiveContext."""

import pytest
from datetime import datetime, timedelta

from kitty_code.core.collective.state import CollectiveState, CollectiveContext


class TestCollectiveState:
    """Test suite for CollectiveState enum."""

    def test_terminal_states(self):
        """Test is_terminal for terminal states."""
        assert CollectiveState.IDLE.is_terminal()
        assert CollectiveState.COMPLETE.is_terminal()
        assert CollectiveState.ERROR.is_terminal()

    def test_non_terminal_states(self):
        """Test is_terminal for non-terminal states."""
        assert not CollectiveState.ROUTING.is_terminal()
        assert not CollectiveState.PLANNING.is_terminal()
        assert not CollectiveState.EXECUTING.is_terminal()
        assert not CollectiveState.JUDGING.is_terminal()
        assert not CollectiveState.REVISING.is_terminal()
        assert not CollectiveState.ESCALATE.is_terminal()

    def test_model_required_states(self):
        """Test requires_model for states needing inference."""
        assert CollectiveState.PLANNING.requires_model()
        assert CollectiveState.EXECUTING.requires_model()
        assert CollectiveState.JUDGING.requires_model()
        assert CollectiveState.DIRECT_EXECUTE.requires_model()

    def test_model_not_required_states(self):
        """Test requires_model for states not needing inference."""
        assert not CollectiveState.IDLE.requires_model()
        assert not CollectiveState.ROUTING.requires_model()
        assert not CollectiveState.REVISING.requires_model()
        assert not CollectiveState.ESCALATE.requires_model()
        assert not CollectiveState.COMPLETE.requires_model()
        assert not CollectiveState.ERROR.requires_model()

    def test_valid_transitions_from_idle(self):
        """Test valid transitions from IDLE."""
        next_states = CollectiveState.IDLE.next_states()
        assert CollectiveState.ROUTING in next_states

    def test_valid_transitions_from_routing(self):
        """Test valid transitions from ROUTING."""
        next_states = CollectiveState.ROUTING.next_states()
        assert CollectiveState.DIRECT_EXECUTE in next_states
        assert CollectiveState.PLANNING in next_states

    def test_valid_transitions_from_executing(self):
        """Test valid transitions from EXECUTING."""
        next_states = CollectiveState.EXECUTING.next_states()
        assert CollectiveState.JUDGING in next_states
        assert CollectiveState.ESCALATE in next_states

    def test_valid_transitions_from_judging(self):
        """Test valid transitions from JUDGING."""
        next_states = CollectiveState.JUDGING.next_states()
        assert CollectiveState.COMPLETE in next_states
        assert CollectiveState.REVISING in next_states
        assert CollectiveState.ESCALATE in next_states


class TestCollectiveContext:
    """Test suite for CollectiveContext."""

    @pytest.fixture
    def context(self) -> CollectiveContext:
        """Create a fresh context."""
        return CollectiveContext()

    def test_initial_state(self, context: CollectiveContext):
        """Test initial state is IDLE."""
        assert context.state == CollectiveState.IDLE

    def test_valid_transition(self, context: CollectiveContext):
        """Test valid state transition."""
        # IDLE -> ROUTING is valid
        result = context.transition_to(CollectiveState.ROUTING, "Start routing")
        assert result is True
        assert context.state == CollectiveState.ROUTING

    def test_invalid_transition(self, context: CollectiveContext):
        """Test invalid state transition is rejected."""
        # IDLE -> EXECUTING is invalid (must go through ROUTING first)
        result = context.transition_to(CollectiveState.EXECUTING)
        assert result is False
        assert context.state == CollectiveState.IDLE

    def test_transition_records_history(self, context: CollectiveContext):
        """Test transitions are recorded in history."""
        context.transition_to(CollectiveState.ROUTING, "Test transition")
        assert len(context.state_history) == 1
        assert context.state_history[0].from_state == CollectiveState.IDLE
        assert context.state_history[0].to_state == CollectiveState.ROUTING
        assert context.state_history[0].reason == "Test transition"

    def test_transition_sets_start_time(self, context: CollectiveContext):
        """Test first non-IDLE transition sets started_at."""
        assert context.started_at is None
        context.transition_to(CollectiveState.ROUTING)
        assert context.started_at is not None

    def test_transition_to_terminal_sets_completed(self, context: CollectiveContext):
        """Test terminal state sets completed_at."""
        # Walk through valid path to COMPLETE
        context.transition_to(CollectiveState.ROUTING)
        context.transition_to(CollectiveState.DIRECT_EXECUTE)
        context.transition_to(CollectiveState.COMPLETE)
        assert context.completed_at is not None

    def test_reset_for_new_request(self, context: CollectiveContext):
        """Test context resets properly."""
        # Make some state changes
        context.transition_to(CollectiveState.ROUTING)
        context.user_input = "old input"
        context.revision_count = 2

        # Reset
        context.reset_for_new_request("new input")

        assert context.state == CollectiveState.IDLE
        assert context.user_input == "new input"
        assert context.revision_count == 0
        assert len(context.state_history) == 0

    def test_can_revise_within_limit(self, context: CollectiveContext):
        """Test revision check within limit."""
        context.revision_count = 1
        assert context.can_revise(max_revisions=3) is True

    def test_can_revise_at_limit(self, context: CollectiveContext):
        """Test revision check at limit."""
        context.revision_count = 3
        assert context.can_revise(max_revisions=3) is False

    def test_can_escalate_within_limit(self, context: CollectiveContext):
        """Test escalation check within limit."""
        context.escalation_count = 1
        assert context.can_escalate(max_escalations=2) is True

    def test_can_escalate_at_limit(self, context: CollectiveContext):
        """Test escalation check at limit."""
        context.escalation_count = 2
        assert context.can_escalate(max_escalations=2) is False

    def test_record_revision(self, context: CollectiveContext):
        """Test revision recording."""
        initial = context.revision_count
        context.record_revision()
        assert context.revision_count == initial + 1

    def test_record_escalation(self, context: CollectiveContext):
        """Test escalation recording."""
        initial = context.escalation_count
        context.record_escalation()
        assert context.escalation_count == initial + 1

    def test_elapsed_time(self, context: CollectiveContext):
        """Test elapsed time calculation."""
        assert context.get_elapsed_time_ms() is None

        context.transition_to(CollectiveState.ROUTING)
        elapsed = context.get_elapsed_time_ms()
        assert elapsed is not None
        assert elapsed >= 0

    def test_to_debug_dict(self, context: CollectiveContext):
        """Test debug dictionary output."""
        context.user_input = "test input"
        context.routing_mode = "collective"
        context.routing_confidence = 0.6

        debug = context.to_debug_dict()

        assert debug["state"] == "IDLE"
        assert debug["user_input"] == "test input"
        assert debug["routing"]["mode"] == "collective"
        assert debug["routing"]["confidence"] == 0.6


class TestCollectiveStateWorkflow:
    """Integration tests for full state machine workflows."""

    def test_simple_direct_workflow(self):
        """Test simple task workflow: IDLE -> ROUTING -> DIRECT_EXECUTE -> COMPLETE."""
        ctx = CollectiveContext()
        ctx.reset_for_new_request("fix typo")

        # Start routing
        assert ctx.transition_to(CollectiveState.ROUTING, "Analyzing task")
        assert ctx.state == CollectiveState.ROUTING

        # Route to direct (simple task)
        ctx.routing_mode = "direct"
        ctx.routing_confidence = 0.95
        assert ctx.transition_to(CollectiveState.DIRECT_EXECUTE, "Simple task")
        assert ctx.state == CollectiveState.DIRECT_EXECUTE

        # Complete
        assert ctx.transition_to(CollectiveState.COMPLETE, "Done")
        assert ctx.state == CollectiveState.COMPLETE
        assert ctx.state.is_terminal()

    def test_collective_workflow_happy_path(self):
        """Test collective workflow: IDLE -> ROUTING -> PLANNING -> EXECUTING -> JUDGING -> COMPLETE."""
        ctx = CollectiveContext()
        ctx.reset_for_new_request("implement feature X")

        # Route to collective
        assert ctx.transition_to(CollectiveState.ROUTING)
        ctx.routing_mode = "collective"
        ctx.routing_confidence = 0.4

        # Plan
        assert ctx.transition_to(CollectiveState.PLANNING, "Creating plan")
        assert ctx.state == CollectiveState.PLANNING

        # Execute
        assert ctx.transition_to(CollectiveState.EXECUTING, "Implementing step 1")
        assert ctx.state == CollectiveState.EXECUTING

        # Judge (approve)
        assert ctx.transition_to(CollectiveState.JUDGING, "Reviewing")
        assert ctx.state == CollectiveState.JUDGING

        # Complete
        assert ctx.transition_to(CollectiveState.COMPLETE, "Approved")
        assert ctx.state == CollectiveState.COMPLETE

    def test_collective_workflow_with_revision(self):
        """Test collective workflow with revision loop."""
        ctx = CollectiveContext()
        ctx.reset_for_new_request("refactor module")

        # Get to JUDGING state
        ctx.transition_to(CollectiveState.ROUTING)
        ctx.transition_to(CollectiveState.PLANNING)
        ctx.transition_to(CollectiveState.EXECUTING)
        ctx.transition_to(CollectiveState.JUDGING)

        # Judge requests revision
        assert ctx.transition_to(CollectiveState.REVISING, "Needs improvement")
        ctx.record_revision()
        assert ctx.revision_count == 1

        # Re-execute
        assert ctx.transition_to(CollectiveState.EXECUTING, "Applying feedback")

        # Re-judge (approve this time)
        assert ctx.transition_to(CollectiveState.JUDGING)
        assert ctx.transition_to(CollectiveState.COMPLETE)

    def test_collective_workflow_with_escalation(self):
        """Test collective workflow with escalation to re-planning."""
        ctx = CollectiveContext()
        ctx.reset_for_new_request("complex task")

        # Get to JUDGING state
        ctx.transition_to(CollectiveState.ROUTING)
        ctx.transition_to(CollectiveState.PLANNING)
        ctx.transition_to(CollectiveState.EXECUTING)
        ctx.transition_to(CollectiveState.JUDGING)

        # Judge rejects - escalate
        assert ctx.transition_to(CollectiveState.ESCALATE, "Rejected - needs new approach")
        ctx.record_escalation()
        assert ctx.escalation_count == 1

        # Re-plan
        assert ctx.transition_to(CollectiveState.PLANNING, "New approach")

        # Continue to completion
        ctx.transition_to(CollectiveState.EXECUTING)
        ctx.transition_to(CollectiveState.JUDGING)
        ctx.transition_to(CollectiveState.COMPLETE)
        assert ctx.state.is_terminal()
