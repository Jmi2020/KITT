"""
KITTY Gateway - Coder Agent Service Proxy

Proxies code generation requests to the coder-agent service.
Supports both non-streaming and SSE streaming endpoints.
"""

from __future__ import annotations

import os
from typing import Any, AsyncGenerator

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

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


@router.post("/stream")
async def stream_generate_code(request: Request) -> StreamingResponse:
    """
    Stream code generation with Server-Sent Events.

    Provides real-time updates as the Plan→Code→Test→Run→Refine→Summarize
    workflow progresses. Each phase emits events with partial results.

    Request body:
    {
        "request": "Write a function to calculate fibonacci numbers",
        "max_refinements": 2,
        "timeout_seconds": 20
    }

    SSE Events:
        - started: Session started
        - plan_start/plan_complete: Planning phase
        - code_start/code_complete: Code generation phase
        - test_start/test_complete: Test generation phase
        - run_start/run_output/run_complete: Test execution phase
        - refine_start/refine_complete: Refinement phase
        - summary_start/summary_complete: Summary phase
        - complete: Workflow complete
        - error: Error occurred

    Proxies SSE stream from coder-agent /api/coding/stream
    """
    async def stream_proxy() -> AsyncGenerator[bytes, None]:
        """Proxy SSE stream from coder-agent."""
        try:
            data = await request.json()
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream(
                    "POST",
                    f"{CODER_AGENT_BASE}/api/coding/stream",
                    json=data,
                    headers={"Accept": "text/event-stream"},
                ) as response:
                    response.raise_for_status()
                    async for chunk in response.aiter_bytes():
                        yield chunk

        except httpx.HTTPStatusError as e:
            # Emit error event
            import json
            error_event = f"data: {json.dumps({'type': 'error', 'error': f'HTTP {e.response.status_code}'})}\n\n"
            yield error_event.encode()

        except httpx.HTTPError as e:
            # Emit error event
            import json
            error_event = f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
            yield error_event.encode()

    return StreamingResponse(
        stream_proxy(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@router.get("/health")
async def health_check() -> dict[str, Any]:
    """
    Check health of coder-agent service.

    Returns service status and LLM server health.

    Response:
    {
        "status": "ok",
        "llm_servers": {
            "ollama": true,
            "q4": true,
            "f16": true
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
