"""
Pydantic models for coder-agent API.

Request/response schemas for code generation endpoints.
"""

from typing import Optional

from pydantic import BaseModel, Field


class GenerateCodeRequest(BaseModel):
    """
    Request for code generation.

    Example:
        {
            "request": "Write a function to calculate fibonacci numbers",
            "max_refinements": 2,
            "timeout_seconds": 20,
            "allow_network": false
        }
    """

    request: str = Field(
        ...,
        description="Natural language coding request",
        min_length=10,
        max_length=5000,
    )

    max_refinements: int = Field(
        default=2,
        description="Maximum refinement iterations if tests fail",
        ge=0,
        le=5,
    )

    timeout_seconds: int = Field(
        default=20,
        description="Sandbox execution timeout",
        ge=5,
        le=120,
    )

    allow_network: bool = Field(
        default=False,
        description="Allow network access in sandbox (not recommended)",
    )


class GenerateCodeResponse(BaseModel):
    """
    Response with generated code and metadata.

    Example:
        {
            "success": true,
            "code": "def fibonacci(n: int) -> int: ...",
            "test_code": "def test_fibonacci(): ...",
            "tests_passed": true,
            "refinement_count": 1,
            "summary": "## Fibonacci Function\\n...",
            "plan": "1. Implement recursive fibonacci\\n...",
            "test_output": "===== test session starts =====\\n...",
            "error": null
        }
    """

    success: bool = Field(
        ...,
        description="Whether code generation succeeded",
    )

    code: Optional[str] = Field(
        None,
        description="Generated Python code",
    )

    test_code: Optional[str] = Field(
        None,
        description="Generated pytest test code",
    )

    tests_passed: bool = Field(
        default=False,
        description="Whether tests passed in final run",
    )

    refinement_count: int = Field(
        default=0,
        description="Number of refinement iterations performed",
    )

    summary: Optional[str] = Field(
        None,
        description="Markdown summary with usage examples",
    )

    plan: Optional[str] = Field(
        None,
        description="Implementation plan generated in first phase",
    )

    test_output: Optional[str] = Field(
        None,
        description="Final test execution output (stdout + stderr)",
    )

    error: Optional[str] = Field(
        None,
        description="Error message if generation failed",
    )


class HealthCheckResponse(BaseModel):
    """
    Health check response.

    Example:
        {
            "status": "ok",
            "llm_servers": {
                "q4": true,
                "f16": true,
                "coder": false
            }
        }
    """

    status: str = Field(
        ...,
        description="Service health status",
    )

    llm_servers: Optional[dict[str, bool]] = Field(
        None,
        description="Health status of llama.cpp servers",
    )
