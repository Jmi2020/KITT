"""Fixtures for collective integration tests."""

import json
import pytest
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

from kitty_code.core.collective.config import CollectiveConfig, RoutingConfig, JudgmentConfig
from kitty_code.core.collective.backends import BackendPool, BackendInstance
from kitty_code.core.collective.orchestrator import CollectiveOrchestrator
from kitty_code.core.config import ModelConfig


# ============================================================================
# Mock Model Response Generators
# ============================================================================

def make_planner_response(
    summary: str,
    steps: List[Dict[str, Any]],
) -> str:
    """Generate a mock Planner response with JSON plan."""
    plan = {
        "summary": summary,
        "steps": steps,
        "success_criteria": ["All tests pass", "No errors in output"],
        "complexity_rating": len(steps) * 2,
    }
    return f"```json\n{json.dumps(plan, indent=2)}\n```"


def make_executor_response(
    text: str,
    tool_calls: Optional[List[Dict]] = None,
) -> Dict[str, Any]:
    """Generate a mock Executor response."""
    return {
        "content": text,
        "tool_calls": tool_calls or [],
        "success": True,
        "prompt_tokens": 100,
        "completion_tokens": 50,
    }


def make_judge_response(
    verdict: str,
    confidence: float = 0.9,
    reasoning: str = "Execution meets criteria",
    issues: Optional[List[str]] = None,
    suggestions: Optional[List[str]] = None,
) -> str:
    """Generate a mock Judge response with JSON verdict."""
    judgment = {
        "verdict": verdict,
        "confidence": confidence,
        "reasoning": reasoning,
    }
    if verdict == "REVISE" and (issues or suggestions):
        judgment["revision_feedback"] = {
            "issues": issues or [],
            "suggestions": suggestions or [],
        }
    return f"```json\n{json.dumps(judgment, indent=2)}\n```"


# ============================================================================
# Mock Backend Factory
# ============================================================================

def create_mock_backend(model_config: ModelConfig) -> MagicMock:
    """Create a mock backend instance."""
    backend = MagicMock()
    backend.model_config = model_config
    return backend


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def model_configs() -> Dict[str, ModelConfig]:
    """Standard model configurations for testing."""
    return {
        "devstral:123b": ModelConfig(
            name="devstral:123b",
            provider="ollama",
            alias="devstral:123b",
        ),
        "devstral-small-2:24b": ModelConfig(
            name="devstral-small-2:24b",
            provider="ollama",
            alias="devstral-small-2:24b",
        ),
    }


@pytest.fixture
def collective_config() -> CollectiveConfig:
    """Standard collective configuration for testing."""
    return CollectiveConfig(
        enabled=True,
        planner_model="devstral:123b",
        executor_model="devstral-small-2:24b",
        judge_model="devstral:123b",
        routing=RoutingConfig(
            complexity_threshold=0.7,
        ),
        judgment=JudgmentConfig(
            max_revision_cycles=2,
            max_escalations=1,
        ),
    )


@pytest.fixture
def backend_pool(model_configs: Dict[str, ModelConfig]) -> BackendPool:
    """Create a backend pool with mock backends."""
    pool = BackendPool(
        planner_model="devstral:123b",
        executor_model="devstral-small-2:24b",
        judge_model="devstral:123b",
        backend_factory=create_mock_backend,
        model_configs=model_configs,
    )
    return pool


@pytest.fixture
def orchestrator(
    collective_config: CollectiveConfig,
    backend_pool: BackendPool,
) -> CollectiveOrchestrator:
    """Create an orchestrator for testing."""
    return CollectiveOrchestrator(
        config=collective_config,
        backend_pool=backend_pool,
    )


# ============================================================================
# Response Scenario Fixtures
# ============================================================================

@pytest.fixture
def simple_task_plan_responses() -> List[Dict[str, Any]]:
    """Responses for a simple single-step task."""
    return [
        # Planner response
        {
            "content": make_planner_response(
                summary="Fix typo in README",
                steps=[
                    {
                        "step_id": "step_1",
                        "description": "Update README.md with corrected text",
                        "tools_required": ["edit_file"],
                        "success_criteria": ["File updated", "No syntax errors"],
                    }
                ],
            ),
            "success": True,
        },
        # Executor response
        make_executor_response(
            text="Fixed the typo in README.md by changing 'teh' to 'the'.",
            tool_calls=[{"name": "edit_file", "args": {"file": "README.md"}}],
        ),
        # Judge response
        {
            "content": make_judge_response(
                verdict="APPROVE",
                confidence=0.95,
                reasoning="The typo was successfully corrected.",
            ),
            "success": True,
        },
    ]


@pytest.fixture
def multi_step_plan_responses() -> List[Dict[str, Any]]:
    """Responses for a multi-step task."""
    return [
        # Planner response
        {
            "content": make_planner_response(
                summary="Add user authentication feature",
                steps=[
                    {
                        "step_id": "step_1",
                        "description": "Create user model",
                        "tools_required": ["write_file"],
                        "success_criteria": ["Model file created"],
                    },
                    {
                        "step_id": "step_2",
                        "description": "Add authentication routes",
                        "tools_required": ["write_file", "edit_file"],
                        "success_criteria": ["Routes added"],
                    },
                    {
                        "step_id": "step_3",
                        "description": "Write tests",
                        "tools_required": ["write_file"],
                        "success_criteria": ["Tests pass"],
                    },
                ],
            ),
            "success": True,
        },
        # Executor response for step 1
        make_executor_response(
            text="Created user model in models/user.py",
            tool_calls=[{"name": "write_file", "args": {"file": "models/user.py"}}],
        ),
        # Judge response for step 1
        {"content": make_judge_response("APPROVE", 0.9), "success": True},
        # Executor response for step 2
        make_executor_response(
            text="Added authentication routes to routes/auth.py",
            tool_calls=[{"name": "write_file", "args": {"file": "routes/auth.py"}}],
        ),
        # Judge response for step 2
        {"content": make_judge_response("APPROVE", 0.85), "success": True},
        # Executor response for step 3
        make_executor_response(
            text="Created test file tests/test_auth.py",
            tool_calls=[{"name": "write_file", "args": {"file": "tests/test_auth.py"}}],
        ),
        # Judge response for step 3
        {"content": make_judge_response("APPROVE", 0.95), "success": True},
    ]


@pytest.fixture
def revision_flow_responses() -> List[Dict[str, Any]]:
    """Responses that trigger a revision cycle."""
    return [
        # Planner response
        {
            "content": make_planner_response(
                summary="Update config parser",
                steps=[
                    {
                        "step_id": "step_1",
                        "description": "Refactor config parser",
                        "tools_required": ["edit_file"],
                        "success_criteria": ["Parser handles all formats"],
                    }
                ],
            ),
            "success": True,
        },
        # First executor attempt
        make_executor_response(
            text="Updated config parser, but forgot YAML support.",
            tool_calls=[{"name": "edit_file", "args": {"file": "config/parser.py"}}],
        ),
        # Judge requests revision
        {
            "content": make_judge_response(
                verdict="REVISE",
                confidence=0.6,
                reasoning="Missing YAML format support",
                issues=["YAML parsing not implemented"],
                suggestions=["Add yaml.safe_load for .yaml files"],
            ),
            "success": True,
        },
        # Second executor attempt (after revision)
        make_executor_response(
            text="Added YAML support to config parser.",
            tool_calls=[{"name": "edit_file", "args": {"file": "config/parser.py"}}],
        ),
        # Judge approves after revision
        {"content": make_judge_response("APPROVE", 0.9), "success": True},
    ]


@pytest.fixture
def escalation_flow_responses() -> List[Dict[str, Any]]:
    """Responses that trigger an escalation."""
    return [
        # Planner response
        {
            "content": make_planner_response(
                summary="Complex database migration",
                steps=[
                    {
                        "step_id": "step_1",
                        "description": "Migrate user table",
                        "tools_required": ["bash"],
                        "success_criteria": ["Migration completes"],
                    }
                ],
            ),
            "success": True,
        },
        # Executor fails
        {
            "content": "Attempted migration but encountered error.",
            "tool_calls": [],
            "success": False,
            "error": "Database connection failed",
        },
        # After escalation - new plan
        {
            "content": make_planner_response(
                summary="Complex database migration (retry)",
                steps=[
                    {
                        "step_id": "step_1",
                        "description": "Check database connection first",
                        "tools_required": ["bash"],
                        "success_criteria": ["Connection verified"],
                    },
                    {
                        "step_id": "step_2",
                        "description": "Run migration",
                        "tools_required": ["bash"],
                        "success_criteria": ["Migration completes"],
                    },
                ],
            ),
            "success": True,
        },
    ]
