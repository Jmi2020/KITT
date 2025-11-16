"""
FastAPI routes for autonomous research sessions.

Provides REST API for:
- Creating/pausing/resuming/cancelling sessions
- Querying session status and history
- Streaming real-time progress via WebSocket
"""

import logging
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, Depends, Query, Request
from pydantic import BaseModel, Field

from brain.research.session_manager import (
    ResearchSessionManager,
    SessionStatus,
    SessionInfo
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/research", tags=["research"])


# ============================================================================
# Request/Response Models
# ============================================================================

class CreateSessionRequest(BaseModel):
    """Request to create a new research session"""
    query: str = Field(..., description="Research query/question", min_length=10)
    user_id: str = Field(..., description="User ID creating the session")
    config: Optional[dict] = Field(
        default=None,
        description="Optional configuration (max_iterations, max_cost_usd, etc.)"
    )


class CreateSessionResponse(BaseModel):
    """Response for session creation"""
    session_id: str
    status: str
    message: str
    thread_id: Optional[str] = None


class SessionDetailResponse(BaseModel):
    """Detailed session information"""
    session_id: str
    user_id: str
    query: str
    status: str
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
    thread_id: Optional[str] = None
    config: Optional[dict] = None
    metadata: Optional[dict] = None

    # Statistics
    total_iterations: int = 0
    total_findings: int = 0
    total_sources: int = 0
    total_cost_usd: float = 0.0
    external_calls_used: int = 0

    # Quality scores
    completeness_score: Optional[float] = None
    confidence_score: Optional[float] = None
    saturation_status: Optional[dict] = None

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class SessionListResponse(BaseModel):
    """List of sessions"""
    sessions: List[SessionDetailResponse]
    total: int


class StatusResponse(BaseModel):
    """Generic status response"""
    success: bool
    message: str


# ============================================================================
# Dependency Injection
# ============================================================================

async def get_session_manager(request: Request) -> ResearchSessionManager:
    """Get session manager from app state"""
    if not hasattr(request.app.state, 'session_manager') or request.app.state.session_manager is None:
        raise HTTPException(
            status_code=503,
            detail="Research service not available (DATABASE_URL not configured)"
        )
    return request.app.state.session_manager


# ============================================================================
# Routes
# ============================================================================

@router.post("/sessions", response_model=CreateSessionResponse, status_code=201)
async def create_research_session(
    request: CreateSessionRequest,
    manager: ResearchSessionManager = Depends(get_session_manager)
):
    """
    Create a new autonomous research session.

    The session will be created with status 'active' and a unique thread_id
    for checkpoint persistence. The actual research execution happens in the
    background and can be monitored via WebSocket streaming.

    Args:
        request: Session creation request with query and configuration

    Returns:
        Session ID and initial status

    Example:
        ```python
        import httpx

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "http://localhost:8080/api/research/sessions",
                json={
                    "query": "Research sustainable 3D printing materials",
                    "user_id": "user123",
                    "config": {
                        "max_iterations": 15,
                        "max_cost_usd": 2.0
                    }
                }
            )
            session_id = response.json()["session_id"]
        ```
    """
    try:
        # Create session in database
        session_id = await manager.create_session(
            user_id=request.user_id,
            query=request.query,
            config=request.config
        )

        # Start research execution in background
        await manager.start_research(
            session_id=session_id,
            user_id=request.user_id,
            query=request.query,
            config=request.config
        )

        # Get session info to return thread_id
        session = await manager.get_session(session_id)

        return CreateSessionResponse(
            session_id=session_id,
            status=SessionStatus.ACTIVE.value,
            message="Research session created and started successfully",
            thread_id=session.thread_id if session else None
        )

    except Exception as e:
        logger.error(f"Error creating session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions", response_model=SessionListResponse)
async def list_research_sessions(
    user_id: str = Query(..., description="User ID to list sessions for"),
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of sessions"),
    manager: ResearchSessionManager = Depends(get_session_manager)
):
    """
    List research sessions for a user.

    Args:
        user_id: User ID to list sessions for
        status: Optional status filter (active, paused, completed, failed)
        limit: Maximum number of sessions to return (1-100)

    Returns:
        List of sessions with details

    Example:
        ```
        GET /api/research/sessions?user_id=user123&status=active
        ```
    """
    try:
        # Parse status if provided
        status_filter = None
        if status:
            try:
                status_filter = SessionStatus(status)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid status: {status}. Must be one of: active, paused, completed, failed"
                )

        sessions = await manager.list_user_sessions(
            user_id=user_id,
            status=status_filter,
            limit=limit
        )

        # Convert to response models
        session_responses = [
            SessionDetailResponse(
                session_id=s.session_id,
                user_id=s.user_id,
                query=s.query,
                status=s.status.value,
                created_at=s.created_at,
                updated_at=s.updated_at,
                completed_at=s.completed_at,
                thread_id=s.thread_id,
                config=s.config,
                metadata=s.metadata,
                total_iterations=s.total_iterations,
                total_findings=s.total_findings,
                total_sources=s.total_sources,
                total_cost_usd=s.total_cost_usd,
                external_calls_used=s.external_calls_used,
                completeness_score=s.completeness_score,
                confidence_score=s.confidence_score,
                saturation_status=s.saturation_status
            )
            for s in sessions
        ]

        return SessionListResponse(
            sessions=session_responses,
            total=len(session_responses)
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing sessions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
async def get_research_session(
    session_id: str,
    manager: ResearchSessionManager = Depends(get_session_manager)
):
    """
    Get detailed information about a research session.

    Args:
        session_id: Session ID to retrieve

    Returns:
        Detailed session information including statistics and quality scores

    Raises:
        404: Session not found
    """
    try:
        session = await manager.get_session(session_id)

        if not session:
            raise HTTPException(
                status_code=404,
                detail=f"Session {session_id} not found"
            )

        return SessionDetailResponse(
            session_id=session.session_id,
            user_id=session.user_id,
            query=session.query,
            status=session.status.value,
            created_at=session.created_at,
            updated_at=session.updated_at,
            completed_at=session.completed_at,
            thread_id=session.thread_id,
            config=session.config,
            metadata=session.metadata,
            total_iterations=session.total_iterations,
            total_findings=session.total_findings,
            total_sources=session.total_sources,
            total_cost_usd=session.total_cost_usd,
            external_calls_used=session.external_calls_used,
            completeness_score=session.completeness_score,
            confidence_score=session.confidence_score,
            saturation_status=session.saturation_status
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions/{session_id}/pause", response_model=StatusResponse)
async def pause_research_session(
    session_id: str,
    manager: ResearchSessionManager = Depends(get_session_manager)
):
    """
    Pause an active research session.

    The session state is preserved via checkpointing and can be resumed later.
    Background tasks are cancelled when pausing.

    Args:
        session_id: Session ID to pause

    Returns:
        Success status

    Raises:
        404: Session not found or not active
    """
    try:
        success = await manager.pause_session(session_id)

        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"Session {session_id} not found or not active"
            )

        return StatusResponse(
            success=True,
            message=f"Session {session_id} paused successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error pausing session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions/{session_id}/resume", response_model=StatusResponse)
async def resume_research_session(
    session_id: str,
    additional_input: Optional[dict] = None,
    manager: ResearchSessionManager = Depends(get_session_manager)
):
    """
    Resume a paused research session.

    The session will continue from the last checkpoint with full state
    restoration. Optionally provide additional input to merge into state.

    Args:
        session_id: Session ID to resume
        additional_input: Optional additional context/input

    Returns:
        Success status

    Raises:
        404: Session not found or not paused
    """
    try:
        success = await manager.resume_session(session_id, additional_input)

        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"Session {session_id} not found or not paused"
            )

        return StatusResponse(
            success=True,
            message=f"Session {session_id} resumed successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resuming session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/sessions/{session_id}", response_model=StatusResponse)
async def cancel_research_session(
    session_id: str,
    manager: ResearchSessionManager = Depends(get_session_manager)
):
    """
    Cancel a research session.

    The session will be marked as failed and background tasks cancelled.
    Checkpoints are preserved for analysis.

    Args:
        session_id: Session ID to cancel

    Returns:
        Success status

    Raises:
        404: Session not found
    """
    try:
        success = await manager.cancel_session(session_id)

        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"Session {session_id} not found"
            )

        return StatusResponse(
            success=True,
            message=f"Session {session_id} cancelled successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# WebSocket Streaming
# ============================================================================

@router.websocket("/sessions/{session_id}/stream")
async def stream_research_progress(
    websocket: WebSocket,
    session_id: str
):
    """
    Stream real-time research progress via WebSocket.

    Sends JSON messages with progress updates:
    - iteration: Current iteration number
    - status: Current status
    - findings: New findings discovered
    - quality_scores: Updated quality metrics
    - events: Research events (tool calls, decisions, etc.)

    Args:
        websocket: WebSocket connection
        session_id: Session ID to stream

    Example (JavaScript):
        ```javascript
        const ws = new WebSocket('ws://localhost:8080/api/research/sessions/{id}/stream');

        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            console.log('Progress:', data);
        };
        ```
    """
    await websocket.accept()

    # Send connection confirmation
    await websocket.send_json({
        "type": "connection",
        "session_id": session_id,
        "message": "Connected to research session stream"
    })

    try:
        # Get session manager
        manager = websocket.app.state.session_manager

        if not manager:
            await websocket.send_json({
                "type": "error",
                "error": "Research service not available"
            })
            await websocket.close()
            return

        # Get session info
        session = await manager.get_session(session_id)

        if not session:
            await websocket.send_json({
                "type": "error",
                "error": f"Session {session_id} not found"
            })
            await websocket.close()
            return

        # Stream research progress from graph
        async for state_update in manager.stream_research(
            session_id=session_id,
            user_id=session.user_id,
            query=session.query,
            config=session.config
        ):
            # Extract node name and state from update
            if isinstance(state_update, dict):
                for node_name, node_state in state_update.items():
                    # Send progress update
                    await websocket.send_json({
                        "type": "progress",
                        "node": node_name,
                        "iteration": node_state.get("current_iteration", 0),
                        "status": node_state.get("status", "active"),
                        "findings_count": len(node_state.get("findings", [])),
                        "sources_count": len(node_state.get("sources", [])),
                        "budget_remaining": float(node_state.get("budget_remaining", 0.0)),
                        "saturation": node_state.get("saturation_status", {}),
                        "stopping_decision": node_state.get("stopping_decision", {}),
                        "timestamp": datetime.utcnow().isoformat()
                    })

        # Send completion message
        await websocket.send_json({
            "type": "complete",
            "session_id": session_id,
            "message": "Research completed",
            "timestamp": datetime.utcnow().isoformat()
        })

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for session {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try:
            await websocket.send_json({
                "type": "error",
                "error": str(e)
            })
            await websocket.close()
        except:
            pass


# ============================================================================
# Health Check
# ============================================================================

@router.get("/health")
async def research_health_check():
    """
    Health check endpoint for research service.

    Returns:
        Service health status
    """
    return {
        "service": "autonomous_research",
        "status": "healthy",
        "version": "0.1.0"
    }
