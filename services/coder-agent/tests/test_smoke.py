"""
Smoke tests for coder-agent service.

Basic tests to verify core functionality works end-to-end.
"""

import pytest


def test_imports():
    """Test that all core modules can be imported."""
    from coder_agent import __version__
    from coder_agent.app import app
    from coder_agent.graph import CoderGraph, CoderState
    from coder_agent.llm_client import CoderLLMClient, LlamaCppClient
    from coder_agent.models import (
        GenerateCodeRequest,
        GenerateCodeResponse,
        HealthCheckResponse,
    )
    from coder_agent.prompts import (
        CODER_SYSTEM,
        PLAN_PROMPT,
        CODE_PROMPT_TEMPLATE,
        TEST_PROMPT_TEMPLATE,
        REFINE_PROMPT_TEMPLATE,
        SUMMARIZE_PROMPT_TEMPLATE,
    )
    from coder_agent.sandbox import CodeSandbox, TestRunner, ExecutionResult

    assert __version__ == "1.0.0"
    assert app is not None


def test_sandbox_syntax_check():
    """Test sandbox syntax validation."""
    from coder_agent.sandbox import CodeSandbox

    sandbox = CodeSandbox(timeout_seconds=5)

    # Valid code
    valid_result = sandbox._check_syntax("def foo(): return 42")
    assert valid_result.success
    assert valid_result.exit_code == 0

    # Invalid code
    invalid_result = sandbox._check_syntax("def foo( return 42")
    assert not invalid_result.success
    assert "syntax" in invalid_result.error_message.lower()


def test_sandbox_code_execution():
    """Test basic code execution in sandbox."""
    from coder_agent.sandbox import CodeSandbox

    sandbox = CodeSandbox(timeout_seconds=10, allow_network=False)

    code = """
def add(a: int, b: int) -> int:
    return a + b

result = add(2, 3)
print(f"Result: {result}")
"""

    result = sandbox.run_code(code, check_syntax=True)

    assert result.success or result.exit_code == 0  # Some environments may vary
    # Note: If no __main__ execution, code runs but produces no output


def test_sandbox_test_execution():
    """Test pytest execution in sandbox."""
    from coder_agent.sandbox import CodeSandbox

    sandbox = CodeSandbox(timeout_seconds=10)

    code = """
def add(a: int, b: int) -> int:
    return a + b
"""

    test_code = """
def test_add():
    from module import add
    assert add(2, 3) == 5
    assert add(-1, 1) == 0
"""

    result = sandbox.run_tests(code, test_code)

    # Tests should pass
    assert result.success
    assert result.exit_code == 0
    assert "passed" in result.stdout.lower() or "2 passed" in result.stdout


def test_sandbox_timeout():
    """Test that sandbox enforces timeout."""
    from coder_agent.sandbox import CodeSandbox

    sandbox = CodeSandbox(timeout_seconds=2)

    # Infinite loop code
    code = """
while True:
    pass
"""

    result = sandbox.run_code(code)

    assert not result.success
    assert result.timed_out
    assert "timeout" in result.error_message.lower()


def test_generate_code_request_validation():
    """Test request model validation."""
    from coder_agent.models import GenerateCodeRequest
    from pydantic import ValidationError

    # Valid request
    valid_req = GenerateCodeRequest(
        request="Write a function to calculate factorial",
        max_refinements=2,
        timeout_seconds=20,
    )
    assert valid_req.request == "Write a function to calculate factorial"
    assert valid_req.max_refinements == 2

    # Invalid: request too short
    with pytest.raises(ValidationError):
        GenerateCodeRequest(request="abc")

    # Invalid: max_refinements out of range
    with pytest.raises(ValidationError):
        GenerateCodeRequest(request="Write a function", max_refinements=10)


def test_graph_clean_code_output():
    """Test code cleaning helper."""
    from coder_agent.graph import CoderGraph

    # Clean markdown fences
    code_with_fences = '''```python
def foo():
    return 42
```'''

    cleaned = CoderGraph._clean_code_output(code_with_fences)
    assert cleaned == "def foo():\n    return 42"
    assert "```" not in cleaned

    # Already clean code
    clean_code = "def bar(): return 1"
    assert CoderGraph._clean_code_output(clean_code) == clean_code


@pytest.mark.asyncio
async def test_health_check_response():
    """Test health check response model."""
    from coder_agent.models import HealthCheckResponse

    response = HealthCheckResponse(
        status="ok",
        llm_servers={"q4": True, "f16": True, "coder": False},
    )

    assert response.status == "ok"
    assert response.llm_servers["q4"] is True
    assert response.llm_servers["coder"] is False


def test_prompts_defined():
    """Test that all prompts are defined and non-empty."""
    from coder_agent.prompts import (
        CODER_SYSTEM,
        PLAN_PROMPT,
        CODE_PROMPT_TEMPLATE,
        TEST_PROMPT_TEMPLATE,
        REFINE_PROMPT_TEMPLATE,
        SUMMARIZE_PROMPT_TEMPLATE,
        MAX_CODE_LENGTH,
        TEST_STYLE,
    )

    assert len(CODER_SYSTEM) > 100
    assert len(PLAN_PROMPT) > 50
    assert "{user_request}" in CODE_PROMPT_TEMPLATE
    assert "{plan}" in CODE_PROMPT_TEMPLATE
    assert "{code}" in TEST_PROMPT_TEMPLATE
    assert "{stdout}" in REFINE_PROMPT_TEMPLATE
    assert "{stderr}" in REFINE_PROMPT_TEMPLATE
    assert MAX_CODE_LENGTH == 8000
    assert TEST_STYLE == "pytest"
