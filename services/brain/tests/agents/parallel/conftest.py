"""
Shared fixtures for parallel agent orchestration tests.
"""

import asyncio
from dataclasses import dataclass
from typing import Dict, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from brain.agents.parallel.types import ModelTier, TaskStatus, KittyTask
from brain.agents.parallel.registry import ModelEndpoint, KittyAgent, ENDPOINTS


# ============================================================================
# Pytest Configuration
# ============================================================================

@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ============================================================================
# Model Endpoint Fixtures
# ============================================================================

@pytest.fixture
def mock_endpoint() -> ModelEndpoint:
    """Create a mock endpoint for testing."""
    return ModelEndpoint(
        name="Test Endpoint",
        base_url="http://localhost:9999",
        max_slots=3,
        context_length=8192,
        model_id="test-model",
        supports_tools=True,
    )


@pytest.fixture
def q4_endpoint() -> ModelEndpoint:
    """Create Q4 endpoint matching production config."""
    return ModelEndpoint(
        name="Q4 Tools",
        base_url="http://localhost:8083",
        max_slots=6,
        context_length=131072,
        model_id="kitty-q4",
        supports_tools=True,
    )


@pytest.fixture
def mock_endpoints() -> Dict[ModelTier, ModelEndpoint]:
    """Create mock endpoint registry."""
    return {
        ModelTier.Q4_TOOLS: ModelEndpoint(
            name="Q4 Tools",
            base_url="http://localhost:8083",
            max_slots=6,
            context_length=16384,
            model_id="kitty-q4",
            supports_tools=True,
        ),
        ModelTier.GPTOSS_REASON: ModelEndpoint(
            name="GPT-OSS",
            base_url="http://localhost:11434",
            max_slots=2,
            context_length=65536,
            model_id="gpt-oss-120b",
            thinking_mode="medium",
        ),
        ModelTier.CODER: ModelEndpoint(
            name="Coder",
            base_url="http://localhost:8087",
            max_slots=4,
            context_length=32768,
            model_id="kitty-coder",
        ),
        ModelTier.SUMMARY: ModelEndpoint(
            name="Summary",
            base_url="http://localhost:8084",
            max_slots=4,
            context_length=4096,
            model_id="kitty-summary",
        ),
        ModelTier.VISION: ModelEndpoint(
            name="Vision",
            base_url="http://localhost:8086",
            max_slots=2,
            context_length=4096,
            model_id="kitty-vision",
            supports_vision=True,
        ),
    }


# ============================================================================
# Agent Fixtures
# ============================================================================

@pytest.fixture
def mock_agent() -> KittyAgent:
    """Create a mock agent for testing."""
    return KittyAgent(
        name="test_agent",
        role="Test Agent",
        expertise="Testing",
        system_prompt="You are a test agent.",
        primary_tier=ModelTier.Q4_TOOLS,
        fallback_tier=ModelTier.CODER,
        tool_allowlist=["test_tool"],
        max_tokens=1024,
        temperature=0.5,
    )


@pytest.fixture
def researcher_agent() -> KittyAgent:
    """Create researcher agent matching production config."""
    return KittyAgent(
        name="researcher",
        role="Research Specialist",
        expertise="Web search, document analysis",
        system_prompt="You are KITTY's research agent.",
        primary_tier=ModelTier.Q4_TOOLS,
        tool_allowlist=["web_search", "fetch_webpage"],
        temperature=0.3,
    )


# ============================================================================
# Task Fixtures
# ============================================================================

@pytest.fixture
def pending_task() -> KittyTask:
    """Create a pending task."""
    return KittyTask(
        id="task_1",
        description="Test task",
        assigned_to="researcher",
    )


@pytest.fixture
def completed_task() -> KittyTask:
    """Create a completed task with metrics."""
    task = KittyTask(
        id="task_2",
        description="Completed task",
        assigned_to="researcher",
    )
    task.mark_started()
    task.mark_completed("Result text", "kitty-q4", tokens=100)
    return task


@pytest.fixture
def task_with_dependencies() -> KittyTask:
    """Create a task with dependencies."""
    return KittyTask(
        id="task_3",
        description="Dependent task",
        assigned_to="reasoner",
        dependencies=["task_1", "task_2"],
    )


@pytest.fixture
def task_list() -> list:
    """Create a list of tasks for testing."""
    t1 = KittyTask(id="t1", description="Research", assigned_to="researcher")
    t2 = KittyTask(id="t2", description="Code", assigned_to="coder")
    t3 = KittyTask(id="t3", description="Synthesize", assigned_to="reasoner", dependencies=["t1", "t2"])
    return [t1, t2, t3]


# ============================================================================
# HTTP Mock Fixtures
# ============================================================================

@pytest.fixture
def mock_httpx_client():
    """Create mock httpx client for LLM requests."""
    client = MagicMock()  # Use MagicMock for property access

    # Mock successful llama.cpp response
    llamacpp_response = MagicMock()
    llamacpp_response.status_code = 200
    llamacpp_response.raise_for_status = MagicMock()
    llamacpp_response.json.return_value = {
        "content": "Test response from llama.cpp",
        "tokens_predicted": 50,
        "tokens_evaluated": 100,
    }

    # Mock successful Ollama response
    ollama_response = MagicMock()
    ollama_response.status_code = 200
    ollama_response.raise_for_status = MagicMock()
    ollama_response.json.return_value = {
        "response": "Test response from Ollama",
        "eval_count": 50,
        "prompt_eval_count": 100,
        "thinking": "Let me think...",
    }

    # Mock health check response
    health_response = MagicMock()
    health_response.status_code = 200
    health_response.raise_for_status = MagicMock()

    async def route_request(*args, **kwargs):
        url = args[0] if args else kwargs.get("url", "")
        if "health" in url or "api/tags" in url:
            return health_response
        elif "11434" in url or "api/generate" in url:
            return ollama_response
        else:
            return llamacpp_response

    client.post = AsyncMock(side_effect=route_request)
    client.get = AsyncMock(return_value=health_response)
    client.is_closed = False  # Property access returns False
    client.aclose = AsyncMock()

    return client


@pytest.fixture
def mock_httpx_error_client():
    """Create mock httpx client that returns errors."""
    client = AsyncMock()
    client.post = AsyncMock(side_effect=Exception("Connection failed"))
    client.get = AsyncMock(side_effect=Exception("Connection failed"))
    client.is_closed = False
    client.aclose = AsyncMock()
    return client


# ============================================================================
# Environment Fixtures
# ============================================================================

@pytest.fixture
def parallel_enabled_env(monkeypatch):
    """Set environment for parallel agents enabled."""
    monkeypatch.setenv("ENABLE_PARALLEL_AGENTS", "true")
    monkeypatch.setenv("PARALLEL_AGENT_ROLLOUT_PERCENT", "100")
    monkeypatch.setenv("PARALLEL_AGENT_COMPLEXITY_THRESHOLD", "0.6")
    monkeypatch.setenv("PARALLEL_AGENT_MAX_TASKS", "6")


@pytest.fixture
def parallel_disabled_env(monkeypatch):
    """Set environment for parallel agents disabled."""
    monkeypatch.setenv("ENABLE_PARALLEL_AGENTS", "false")


# ============================================================================
# Cleanup Fixtures
# ============================================================================

@pytest.fixture
async def reset_singletons():
    """Reset global singletons after test (use explicitly in async tests)."""
    yield
    # Import here to avoid circular imports
    from brain.agents.parallel.slot_manager import reset_slot_manager
    from brain.agents.parallel.llm_adapter import reset_parallel_client
    from brain.agents.parallel.parallel_manager import reset_task_manager
    from brain.agents.parallel.integration import reset_parallel_integration

    await reset_slot_manager()
    await reset_parallel_client()
    await reset_task_manager()
    await reset_parallel_integration()
