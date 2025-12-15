"""
Brain Service Proxy Routes.

Proxies requests to the brain service for routes not handled directly by gateway:
- /api/query - Main chat endpoint
- /api/conversations - Conversation history
- /api/memory - Semantic memory
- /api/autonomy - Autonomous operations
- /api/projects - Project management
- /api/usage - Usage metrics
- /api/routing/models - Model listing (brain has this, gateway has /logs)
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

router = APIRouter(tags=["brain-proxy"])

BRAIN_URL = os.getenv("UPSTREAM_BRAIN_URL", "http://brain:8000")

# Routes to proxy to brain service
BRAIN_ROUTES = [
    "/api/query",
    "/api/conversations",
    "/api/memory",
    "/api/autonomy",
    "/api/projects",
    "/api/usage",
]


async def proxy_to_brain(request: Request, path: str) -> Response:
    """Proxy request to brain service."""
    url = f"{BRAIN_URL}{path}"

    # Get query string
    if request.query_params:
        url += f"?{request.query_params}"

    # Get headers (exclude host)
    headers = {
        key: value for key, value in request.headers.items()
        if key.lower() not in ("host", "content-length")
    }

    # Get body for POST/PUT/PATCH
    body = None
    if request.method in ("POST", "PUT", "PATCH"):
        body = await request.body()

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.request(
                method=request.method,
                url=url,
                headers=headers,
                content=body,
            )

            # Return proxied response
            return Response(
                content=response.content,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.headers.get("content-type"),
            )
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Brain service timeout")
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Brain service unavailable")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Brain proxy error: {str(e)}")


# Query endpoints
@router.post("/api/query")
async def proxy_query(request: Request) -> Response:
    """Proxy query to brain."""
    return await proxy_to_brain(request, "/api/query")


@router.post("/api/query/stream")
async def proxy_query_stream(request: Request) -> Response:
    """Proxy streaming query to brain."""
    return await proxy_to_brain(request, "/api/query/stream")


# Conversation endpoints
@router.get("/api/conversations")
async def proxy_conversations_list(request: Request) -> Response:
    """Proxy conversation list to brain."""
    return await proxy_to_brain(request, "/api/conversations")


@router.get("/api/conversations/{conversation_id}")
async def proxy_conversation_get(request: Request, conversation_id: str) -> Response:
    """Proxy conversation get to brain."""
    return await proxy_to_brain(request, f"/api/conversations/{conversation_id}")


@router.get("/api/conversations/{conversation_id}/messages")
async def proxy_conversation_messages(request: Request, conversation_id: str) -> Response:
    """Proxy conversation messages to brain."""
    return await proxy_to_brain(request, f"/api/conversations/{conversation_id}/messages")


@router.post("/api/conversations/{conversation_id}/title")
async def proxy_conversation_title(request: Request, conversation_id: str) -> Response:
    """Proxy conversation title update to brain."""
    return await proxy_to_brain(request, f"/api/conversations/{conversation_id}/title")


@router.delete("/api/conversations/{conversation_id}")
async def proxy_conversation_delete(request: Request, conversation_id: str) -> Response:
    """Proxy conversation delete to brain."""
    return await proxy_to_brain(request, f"/api/conversations/{conversation_id}")


# Memory endpoints
@router.post("/api/memory/remember")
async def proxy_memory_remember(request: Request) -> Response:
    """Proxy memory remember to brain."""
    return await proxy_to_brain(request, "/api/memory/remember")


@router.post("/api/memory/search")
async def proxy_memory_search(request: Request) -> Response:
    """Proxy memory search to brain."""
    return await proxy_to_brain(request, "/api/memory/search")


# Autonomy endpoints
@router.get("/api/autonomy/status")
async def proxy_autonomy_status(request: Request) -> Response:
    """Proxy autonomy status to brain."""
    return await proxy_to_brain(request, "/api/autonomy/status")


@router.get("/api/autonomy/budget")
async def proxy_autonomy_budget(request: Request) -> Response:
    """Proxy autonomy budget to brain."""
    return await proxy_to_brain(request, "/api/autonomy/budget")


@router.get("/api/autonomy/goals")
async def proxy_autonomy_goals(request: Request) -> Response:
    """Proxy autonomy goals to brain."""
    return await proxy_to_brain(request, "/api/autonomy/goals")


@router.get("/api/autonomy/goals/{goal_id}")
async def proxy_autonomy_goal(request: Request, goal_id: str) -> Response:
    """Proxy autonomy goal get to brain."""
    return await proxy_to_brain(request, f"/api/autonomy/goals/{goal_id}")


@router.post("/api/autonomy/goals/{goal_id}/approve")
async def proxy_autonomy_goal_approve(request: Request, goal_id: str) -> Response:
    """Proxy autonomy goal approve to brain."""
    return await proxy_to_brain(request, f"/api/autonomy/goals/{goal_id}/approve")


@router.post("/api/autonomy/goals/{goal_id}/reject")
async def proxy_autonomy_goal_reject(request: Request, goal_id: str) -> Response:
    """Proxy autonomy goal reject to brain."""
    return await proxy_to_brain(request, f"/api/autonomy/goals/{goal_id}/reject")


# Autonomy Calendar endpoints
@router.get("/api/autonomy/calendar/schedules")
async def proxy_calendar_schedules(request: Request) -> Response:
    """Proxy calendar schedules list to brain."""
    return await proxy_to_brain(request, "/api/autonomy/calendar/schedules")


@router.post("/api/autonomy/calendar/schedules")
async def proxy_calendar_schedule_create(request: Request) -> Response:
    """Proxy calendar schedule create to brain."""
    return await proxy_to_brain(request, "/api/autonomy/calendar/schedules")


@router.get("/api/autonomy/calendar/schedules/{schedule_id}")
async def proxy_calendar_schedule_get(request: Request, schedule_id: str) -> Response:
    """Proxy calendar schedule get to brain."""
    return await proxy_to_brain(request, f"/api/autonomy/calendar/schedules/{schedule_id}")


@router.patch("/api/autonomy/calendar/schedules/{schedule_id}")
async def proxy_calendar_schedule_update(request: Request, schedule_id: str) -> Response:
    """Proxy calendar schedule update to brain."""
    return await proxy_to_brain(request, f"/api/autonomy/calendar/schedules/{schedule_id}")


@router.delete("/api/autonomy/calendar/schedules/{schedule_id}")
async def proxy_calendar_schedule_delete(request: Request, schedule_id: str) -> Response:
    """Proxy calendar schedule delete to brain."""
    return await proxy_to_brain(request, f"/api/autonomy/calendar/schedules/{schedule_id}")


@router.get("/api/autonomy/calendar/history")
async def proxy_calendar_history(request: Request) -> Response:
    """Proxy calendar history to brain."""
    return await proxy_to_brain(request, "/api/autonomy/calendar/history")


# Projects endpoints
@router.get("/api/projects")
async def proxy_projects_list(request: Request) -> Response:
    """Proxy projects list to brain."""
    return await proxy_to_brain(request, "/api/projects")


@router.get("/api/projects/")
async def proxy_projects_list_slash(request: Request) -> Response:
    """Proxy projects list to brain (with trailing slash)."""
    return await proxy_to_brain(request, "/api/projects/")


@router.post("/api/projects")
async def proxy_project_create(request: Request) -> Response:
    """Proxy project create to brain."""
    return await proxy_to_brain(request, "/api/projects")


@router.post("/api/projects/")
async def proxy_project_create_slash(request: Request) -> Response:
    """Proxy project create to brain (with trailing slash)."""
    return await proxy_to_brain(request, "/api/projects/")

@router.get("/api/projects/{project_id}")
async def proxy_project_get(request: Request, project_id: str) -> Response:
    """Proxy project detail to brain."""
    return await proxy_to_brain(request, f"/api/projects/{project_id}")


@router.patch("/api/projects/{project_id}")
async def proxy_project_update(request: Request, project_id: str) -> Response:
    """Proxy project update to brain."""
    return await proxy_to_brain(request, f"/api/projects/{project_id}")


@router.post("/api/projects/{project_id}/artifacts")
async def proxy_project_artifacts(request: Request, project_id: str) -> Response:
    """Proxy project artifact append to brain."""
    return await proxy_to_brain(request, f"/api/projects/{project_id}/artifacts")


@router.delete("/api/projects/{project_id}")
async def proxy_project_delete(request: Request, project_id: str) -> Response:
    """Proxy project delete to brain."""
    return await proxy_to_brain(request, f"/api/projects/{project_id}")


# Usage endpoints
@router.get("/api/usage/metrics")
async def proxy_usage_metrics(request: Request) -> Response:
    """Proxy usage metrics to brain."""
    return await proxy_to_brain(request, "/api/usage/metrics")


# Routing models endpoint (brain has model listing)
@router.get("/api/routing/models")
async def proxy_routing_models(request: Request) -> Response:
    """Proxy routing models to brain."""
    return await proxy_to_brain(request, "/api/routing/models")
