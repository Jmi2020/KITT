"""
KITTY Gateway - Coder Agent Service Proxy

Proxies code generation requests to the coder-agent service.
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api/coding", tags=["coding"])

CODER_AGENT_BASE = os.getenv("CODER_AGENT_BASE", "http://coder-agent:8092")


@router.post("/generate")
async def generate_code(request: Request) -> dict[str, Any]:
    """
    Generate Python code from natural language request.

    Implements Plan-Code-Test-Run-Refine-Summarize workflow with
    automated testing and refinement.

    Request body:
    {
        "request": "Write a function to calculate fibonacci numbers",
        "max_refinements": 2,
        "timeout_seconds": 20,
        "allow_network": false
    }

    Response:
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

    Proxies to coder-agent /api/coding/generate
    """
    try:
        data = await request.json()
        async with httpx.AsyncClient(timeout=180.0) as client:  # Long timeout for code gen
            response = await client.post(
                f"{CODER_AGENT_BASE}/api/coding/generate",
                json=data,
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
        # Forward the exact error from the coder-agent service
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail=f"Coder agent service error: {e}")


@router.get("/health")
async def health_check() -> dict[str, Any]:
    """
    Check health of coder-agent service.

    Returns service status and llama.cpp server health.

    Response:
    {
        "status": "ok",
        "llm_servers": {
            "q4": true,
            "f16": true,
            "coder": false
        }
    }

    Proxies to coder-agent /healthz
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{CODER_AGENT_BASE}/healthz")
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail=f"Coder agent service error: {e}")
