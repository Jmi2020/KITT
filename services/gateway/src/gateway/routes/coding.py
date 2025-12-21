"""
KITTY Gateway - Coder Agent Service Proxy

Proxies code generation requests to the coder-agent service.
Supports both non-streaming and SSE streaming endpoints.
Also manages coding projects for organizing generated code.
"""

from __future__ import annotations

import os
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncGenerator, Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api/coding", tags=["coding"])

CODER_AGENT_BASE = os.getenv("CODER_AGENT_BASE", "http://coder-agent:8092")
CODING_PROJECTS_ROOT = Path(os.getenv("CODING_PROJECTS_ROOT", "/app/storage/code/projects")).expanduser()


# =============================================================================
# Coding Projects Models
# =============================================================================


class CodingProjectCreate(BaseModel):
    """Request model for creating a coding project."""

    title: str
    working_dir: Optional[str] = None
    init_git: bool = True


class CodingProject(BaseModel):
    """Coding project model."""

    id: str
    title: str
    working_dir: Optional[str] = None
    conversation_id: Optional[str] = None
    status: str = "active"  # active, completed, archived
    created_at: str
    updated_at: str
    metadata: dict = {}


class CodingProjectList(BaseModel):
    """Response model for listing projects."""

    projects: list[CodingProject]
    total: int


# In-memory store (TODO: migrate to database)
_coding_projects: dict[str, CodingProject] = {}


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


# =============================================================================
# Coding Projects Endpoints
# =============================================================================


@router.get("/projects", response_model=CodingProjectList)
async def list_coding_projects(
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> CodingProjectList:
    """
    List all coding projects.

    Args:
        status: Filter by status (active, completed, archived)
        limit: Maximum projects to return
        offset: Pagination offset

    Returns:
        List of coding projects
    """
    projects = list(_coding_projects.values())

    # Filter by status
    if status:
        projects = [p for p in projects if p.status == status]

    # Sort by updated_at descending
    projects.sort(key=lambda p: p.updated_at, reverse=True)

    # Apply pagination
    total = len(projects)
    projects = projects[offset : offset + limit]

    return CodingProjectList(projects=projects, total=total)


@router.post("/projects", response_model=CodingProject)
async def create_coding_project(data: CodingProjectCreate) -> CodingProject:
    """
    Create a new coding project.

    Creates a project directory and optionally initializes git.

    Args:
        data: Project creation data

    Returns:
        Created project
    """
    project_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat() + "Z"

    # Determine working directory
    if data.working_dir:
        working_dir = Path(data.working_dir).expanduser()
    else:
        # Create project directory under projects root
        CODING_PROJECTS_ROOT.mkdir(parents=True, exist_ok=True)
        working_dir = CODING_PROJECTS_ROOT / project_id
        working_dir.mkdir(parents=True, exist_ok=True)

    # Initialize git if requested
    git_initialized = False
    if data.init_git and working_dir.exists():
        git_dir = working_dir / ".git"
        if not git_dir.exists():
            try:
                subprocess.run(
                    ["git", "init"],
                    cwd=str(working_dir),
                    capture_output=True,
                    timeout=10,
                )
                git_initialized = True
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass

    project = CodingProject(
        id=project_id,
        title=data.title,
        working_dir=str(working_dir) if working_dir.exists() else None,
        status="active",
        created_at=now,
        updated_at=now,
        metadata={
            "git_repo": git_initialized,
            "files_generated": 0,
        },
    )

    _coding_projects[project_id] = project
    return project


@router.get("/projects/{project_id}", response_model=CodingProject)
async def get_coding_project(project_id: str) -> CodingProject:
    """
    Get a coding project by ID.

    Args:
        project_id: Project ID

    Returns:
        Project details
    """
    if project_id not in _coding_projects:
        raise HTTPException(status_code=404, detail="Project not found")

    return _coding_projects[project_id]


@router.patch("/projects/{project_id}", response_model=CodingProject)
async def update_coding_project(
    project_id: str,
    title: Optional[str] = None,
    status: Optional[str] = None,
) -> CodingProject:
    """
    Update a coding project.

    Args:
        project_id: Project ID
        title: New title (optional)
        status: New status (optional)

    Returns:
        Updated project
    """
    if project_id not in _coding_projects:
        raise HTTPException(status_code=404, detail="Project not found")

    project = _coding_projects[project_id]

    if title:
        project.title = title
    if status:
        if status not in ("active", "completed", "archived"):
            raise HTTPException(status_code=400, detail="Invalid status")
        project.status = status

    project.updated_at = datetime.utcnow().isoformat() + "Z"
    _coding_projects[project_id] = project

    return project


@router.delete("/projects/{project_id}")
async def delete_coding_project(project_id: str) -> dict[str, str]:
    """
    Delete a coding project (marks as archived).

    Args:
        project_id: Project ID

    Returns:
        Confirmation message
    """
    if project_id not in _coding_projects:
        raise HTTPException(status_code=404, detail="Project not found")

    # Just mark as archived, don't delete files
    project = _coding_projects[project_id]
    project.status = "archived"
    project.updated_at = datetime.utcnow().isoformat() + "Z"

    return {"message": f"Project {project_id} archived"}
