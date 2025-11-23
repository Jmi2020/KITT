"""
FastAPI routes for autonomous research sessions.

Provides REST API for:
- Creating/pausing/resuming/cancelling sessions
- Querying session status and history
- Streaming real-time progress via WebSocket
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, Depends, Query, Request
from pydantic import BaseModel, Field

from brain.research.session_manager import (
    ResearchSessionManager,
    SessionStatus,
    SessionInfo
)
from brain.research.templates import (
    ResearchTemplateType,
    apply_template,
    TEMPLATES
)
from brain.research.extraction import extract_claims_from_content
from brain.research.types import Claim, EvidenceSpan
from brain.research.template_selector import TemplateSelector
from brain.research.graph.nodes import invoke_model

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/research", tags=["research"])


# ============================================================================
# Request/Response Models
# ============================================================================

class CreateSessionRequest(BaseModel):
    """Request to create a new research session"""
    query: str = Field(..., description="Research query/question", min_length=10)
    user_id: str = Field(..., description="User ID creating the session")
    template: Optional[str] = Field(
        default=None,
        description="Optional research template (auto-detected if not provided). Options: technical_docs, comparison, troubleshooting, product_research, academic, quick_fact, deep_dive, general"
    )
    config: Optional[dict] = Field(
        default=None,
        description="Optional configuration (max_iterations, max_cost_usd, etc.). Overrides template settings."
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


class FindingDetail(BaseModel):
    """Detailed finding information"""
    id: int
    finding_type: str
    content: str
    confidence: float
    sources: list
    iteration: int
    created_at: datetime

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class SessionResults(BaseModel):
    """Complete session results"""
    session_id: str
    query: str
    status: str
    final_synthesis: Optional[str]
    synthesis_model: Optional[str]
    findings: List[FindingDetail]
    total_findings: int
    total_sources: int
    total_cost_usd: float
    completeness_score: Optional[float]
    confidence_score: Optional[float]

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class SynthesisResponse(BaseModel):
    """Response for synthesis generation"""
    success: bool
    synthesis: Optional[str]
    model_used: Optional[str]
    cost_usd: float
    message: str


class EvidenceSpanResponse(BaseModel):
    """Evidence span within a claim"""
    source_id: str
    url: str
    title: str
    quote: str
    char_start: Optional[int] = None
    char_end: Optional[int] = None


class ClaimResponse(BaseModel):
    """Extracted claim with evidence"""
    id: str
    session_id: str
    sub_question_id: Optional[str]
    text: str
    evidence: List[EvidenceSpanResponse]
    entailment_score: float
    provenance_score: float
    dedupe_fingerprint: str
    confidence: float
    claim_type: str = "fact"


class ExtractClaimsRequest(BaseModel):
    """Request to extract claims from content"""
    content: str = Field(..., description="Text content to extract claims from", min_length=1)
    source_id: str = Field(..., description="Unique identifier for the source")
    source_url: str = Field(..., description="URL of the source")
    source_title: str = Field(..., description="Title of the source")
    session_id: str = Field(..., description="Research session ID")
    query: str = Field(..., description="Research query for context")
    sub_question_id: Optional[str] = Field(default=None, description="Sub-question ID if hierarchical")
    current_iteration: int = Field(default=0, description="Current research iteration")


class ExtractClaimsResponse(BaseModel):
    """Response with extracted claims"""
    claims: List[ClaimResponse]
    count: int
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


async def get_model_coordinator(request: Request):
    """Get model coordinator from app state"""
    if not hasattr(request.app.state, 'model_coordinator') or request.app.state.model_coordinator is None:
        raise HTTPException(
            status_code=503,
            detail="Model coordinator not available"
        )
    return request.app.state.model_coordinator


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
        # Apply research template
        if request.template:
            try:
                template_type = ResearchTemplateType(request.template)
                config = apply_template(request.query, request.config)
                logger.info(f"Applied template '{request.template}' to query")
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid template: {request.template}. Valid options: {[t.value for t in ResearchTemplateType]}"
                )
        else:
            # Use enhanced selector for better template matching (ethics/academic vs product, etc.)
            selector = TemplateSelector()
            selected = selector.select_template(request.query)
            config = selected["config"].copy()
            if request.config:
                config.update(request.config)
            config["template"] = {
                "type": selected["name"],
                "name": selected["name"],
                "description": selected["name"],
            }

        # Create session in database
        session_id = await manager.create_session(
            user_id=request.user_id,
            query=request.query,
            config=config
        )

        # Start research execution in background
        await manager.start_research(
            session_id=session_id,
            user_id=request.user_id,
            query=request.query,
            config=config
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


@router.get("/templates")
async def list_research_templates():
    """
    List all available research templates.

    Research templates provide pre-configured settings optimized for
    different types of queries (technical docs, comparisons, troubleshooting, etc.).

    Returns:
        List of available templates with descriptions and settings
    """
    return {
        "templates": [
            {
                "type": template_type.value,
                "name": template.name,
                "description": template.description,
                "strategy": template.strategy,
                "max_iterations": template.max_iterations,
                "min_sources": template.min_sources,
                "min_confidence": template.min_confidence,
                "use_debate": template.use_debate,
            }
            for template_type, template in TEMPLATES.items()
        ]
    }


@router.get("/sessions/{session_id}/results", response_model=SessionResults)
async def get_session_results(
    session_id: str,
    manager: ResearchSessionManager = Depends(get_session_manager)
):
    """
    Get complete results for a research session.

    Returns synthesis, findings, sources, and quality metrics.

    Args:
        session_id: Session ID

    Returns:
        Complete session results

    Raises:
        404: Session not found
    """
    try:
        # Get session info
        session = await manager.get_session(session_id)

        if not session:
            raise HTTPException(
                status_code=404,
                detail=f"Session {session_id} not found"
            )

        # Get findings from database
        async with manager.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT id, finding_type, content, confidence, sources, iteration, created_at
                    FROM research_findings
                    WHERE session_id = %s
                    ORDER BY iteration, id
                    """,
                    (session_id,)
                )

                findings_rows = await cur.fetchall()
                findings = [
                    FindingDetail(
                        id=row[0],
                        finding_type=row[1],
                        content=row[2],
                        confidence=float(row[3]),
                        sources=row[4] if row[4] else [],
                        iteration=row[5],
                        created_at=row[6]
                    )
                    for row in findings_rows
                ]

        # Get synthesis
        synthesis = await manager.get_session_synthesis(session_id)

        return SessionResults(
            session_id=session.session_id,
            query=session.query,
            status=session.status.value,
            final_synthesis=synthesis,
            synthesis_model=None,  # TODO: Get from session
            findings=findings,
            total_findings=session.total_findings,
            total_sources=session.total_sources,
            total_cost_usd=session.total_cost_usd,
            completeness_score=session.completeness_score,
            confidence_score=session.confidence_score
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting session results: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions/{session_id}/findings")
async def get_session_findings(
    session_id: str,
    page: int = Query(0, ge=0, description="Page number (0-indexed)"),
    limit: int = Query(20, ge=1, le=100, description="Results per page"),
    manager: ResearchSessionManager = Depends(get_session_manager)
):
    """
    Get paginated findings for a session.

    Args:
        session_id: Session ID
        page: Page number (0-indexed)
        limit: Results per page (1-100)

    Returns:
        Paginated list of findings

    Raises:
        404: Session not found
    """
    try:
        # Verify session exists
        session = await manager.get_session(session_id)
        if not session:
            raise HTTPException(
                status_code=404,
                detail=f"Session {session_id} not found"
            )

        offset = page * limit

        async with manager.pool.connection() as conn:
            async with conn.cursor() as cur:
                # Get total count
                await cur.execute(
                    "SELECT COUNT(*) FROM research_findings WHERE session_id = %s",
                    (session_id,)
                )
                total = (await cur.fetchone())[0]

                # Get paginated findings
                await cur.execute(
                    """
                    SELECT id, finding_type, content, confidence, sources, iteration, created_at
                    FROM research_findings
                    WHERE session_id = %s
                    ORDER BY iteration, id
                    LIMIT %s OFFSET %s
                    """,
                    (session_id, limit, offset)
                )

                findings_rows = await cur.fetchall()
                findings = [
                    {
                        "id": row[0],
                        "finding_type": row[1],
                        "content": row[2],
                        "confidence": float(row[3]),
                        "sources": row[4] if row[4] else [],
                        "iteration": row[5],
                        "created_at": row[6].isoformat() if row[6] else None
                    }
                    for row in findings_rows
                ]

        return {
            "session_id": session_id,
            "findings": findings,
            "page": page,
            "limit": limit,
            "total": total,
            "pages": (total + limit - 1) // limit
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting findings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions/{session_id}/followup", response_model=CreateSessionResponse, status_code=201)
async def create_followup_session(
    session_id: str,
    followup_query: str = Query(..., min_length=10, description="Follow-up question"),
    use_context: bool = Query(True, description="Include parent session findings as context"),
    manager: ResearchSessionManager = Depends(get_session_manager)
):
    """
    Create a follow-up research session based on a previous session.

    The follow-up inherits findings from the parent session as context,
    allowing for iterative refinement and additional questions.

    Args:
        session_id: Parent session ID
        followup_query: Follow-up question
        use_context: Whether to inject parent findings as context

    Returns:
        New session ID and status

    Raises:
        404: Parent session not found
    """
    try:
        # Get parent session
        parent_session = await manager.get_session(session_id)

        if not parent_session:
            raise HTTPException(
                status_code=404,
                detail=f"Parent session {session_id} not found"
            )

        # Use same user_id and config as parent
        user_id = parent_session.user_id
        config = parent_session.config or {}

        # Create new session with parent reference
        new_session_id = await manager.create_session(
            user_id=user_id,
            query=followup_query,
            config=config
        )

        # Update parent_session_id in database
        async with manager.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    UPDATE research_sessions
                    SET parent_session_id = %s
                    WHERE session_id = %s
                    """,
                    (session_id, new_session_id)
                )
                await conn.commit()

        # TODO: If use_context=True, inject parent findings into initial state
        # This requires modifications to start_research to accept initial findings

        # Start research
        await manager.start_research(
            session_id=new_session_id,
            user_id=user_id,
            query=followup_query,
            config=config
        )

        return CreateSessionResponse(
            session_id=new_session_id,
            status=SessionStatus.ACTIVE.value,
            message=f"Follow-up session created based on {session_id}",
            thread_id=f"research_{new_session_id}"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating follow-up session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class SynthesisResponse(BaseModel):
    """Response from synthesis generation"""
    session_id: str
    synthesis: str
    model: str
    cost_usd: float


@router.post("/sessions/{session_id}/generate-synthesis", response_model=SynthesisResponse)
async def generate_synthesis(
    session_id: str,
    force: bool = Query(False, description="Regenerate even if synthesis already exists"),
    manager: ResearchSessionManager = Depends(get_session_manager)
):
    """
    Generate a cohesive synthesis from existing research findings.

    This endpoint:
    1. Retrieves all findings for the session
    2. Uses an LLM to create a unified analysis
    3. Saves the synthesis to the database
    4. Returns the generated synthesis

    Useful for:
    - Sessions completed before synthesis persistence was added
    - Regenerating synthesis with improved prompts
    - Creating synthesis for manually imported findings

    Args:
        session_id: Session ID
        force: Regenerate even if synthesis exists (default: False)

    Returns:
        Generated synthesis with metadata

    Raises:
        404: Session not found
        400: No findings to synthesize
    """
    try:
        from brain.llm_client import chat_async

        # Get session info
        session = await manager.get_session(session_id)
        if not session:
            raise HTTPException(
                status_code=404,
                detail=f"Session {session_id} not found"
            )

        # Check if synthesis already exists
        if session.final_synthesis and not force:
            return SynthesisResponse(
                session_id=session_id,
                synthesis=session.final_synthesis,
                model=session.synthesis_model or "existing",
                cost_usd=session.synthesis_cost_usd or 0.0
            )

        # Get all findings
        async with manager.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT id, finding_type, content, confidence, sources, iteration
                    FROM research_findings
                    WHERE session_id = %s
                    ORDER BY iteration, id
                    """,
                    (session_id,)
                )
                findings_rows = await cur.fetchall()

        if not findings_rows:
            raise HTTPException(
                status_code=400,
                detail="No findings available to synthesize"
            )

        # Format findings for synthesis
        findings_text = []
        all_sources = []
        seen_urls = set()

        for row in findings_rows:
            finding_type, content, confidence, sources = row[1], row[2], row[3], row[4]
            findings_text.append(
                f"[{finding_type.upper()} - {confidence*100:.0f}% confidence]\n{content}"
            )

            # Collect unique sources from all findings
            if sources:
                for source in sources:
                    url = source.get("url")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        all_sources.append(source)

        # Format sources with content for LLM analysis
        sources_with_content = []
        for i, s in enumerate(all_sources[:20], 1):  # Limit to top 20 sources
            source_entry = f"{i}. **{s.get('title', 'Untitled')}**"
            source_entry += f"\n   URL: {s.get('url', 'N/A')}"
            if s.get('snippet'):
                source_entry += f"\n   Content: {s.get('snippet')[:300]}"
            if s.get('relevance'):
                source_entry += f"\n   Relevance: {s.get('relevance'):.2f}"
            source_entry += f"\n   Tool: {s.get('tool', 'unknown')}"
            sources_with_content.append(source_entry)

        sources_text = "\n\n".join(sources_with_content) if sources_with_content else "No source metadata available (old session)"

        # Create synthesis prompt with source analysis
        synthesis_prompt = f"""You are analyzing research findings to create a comprehensive answer.

**Original Question:**
{session.query}

**Research Findings:**
{chr(10).join(findings_text)}

**Sources Consulted (with content excerpts):**
{sources_text}

IMPORTANT: If sources with content are available, analyze the actual source content provided above. Reference specific information, quotes, and evidence from the source snippets when constructing your synthesis. Evaluate source quality, relevance, and consistency.

**Task:**
Create a cohesive, well-structured answer to the original question based on the findings and source analysis.

Requirements:
- Synthesize information from all findings into a unified response
- If sources are available, cite specific evidence from source content
- Maintain factual accuracy and cite confidence levels where relevant
- Structure the response logically with clear sections if needed
- Address the question directly and comprehensively
- Acknowledge uncertainties or conflicting information if present
- Properly attribute information to sources when available

Provide ONLY the synthesis (no meta-commentary about the task)."""

        # Generate synthesis using F16 model for higher quality
        messages = [{"role": "user", "content": synthesis_prompt}]
        synthesis_text, metadata = await chat_async(
            messages=messages,
            which="F16",  # Use F16 for quality synthesis
            temperature=0.3,  # Lower temperature for factual synthesis
            max_tokens=2000
        )

        # Extract model and cost from metadata
        model_used = metadata.get("model", "kitty-primary")
        tokens_input = metadata.get("usage", {}).get("prompt_tokens", 0)
        tokens_output = metadata.get("usage", {}).get("completion_tokens", 0)

        # Rough cost estimate (local models are effectively free, but track tokens)
        cost_usd = 0.0  # Local models

        # Save synthesis to database
        async with manager.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    UPDATE research_sessions
                    SET final_synthesis = %s,
                        synthesis_model = %s,
                        synthesis_cost_usd = %s,
                        updated_at = NOW()
                    WHERE session_id = %s
                    """,
                    (synthesis_text, model_used, cost_usd, session_id)
                )
                await conn.commit()

        logger.info(
            f"Generated synthesis for session {session_id}: "
            f"{len(synthesis_text)} chars, model={model_used}"
        )

        return SynthesisResponse(
            session_id=session_id,
            synthesis=synthesis_text,
            model=model_used,
            cost_usd=cost_usd
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating synthesis: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/extract-claims", response_model=ExtractClaimsResponse, status_code=200)
async def extract_claims_endpoint(
    request: ExtractClaimsRequest,
    model_coordinator=Depends(get_model_coordinator)
):
    """
    Extract atomic claims with evidence from research content.

    This endpoint bypasses any module caching issues by providing
    direct HTTP access to the claim extraction functionality.

    Args:
        request: Extraction request with content and metadata
        model_coordinator: Model coordinator from app state

    Returns:
        ExtractClaimsResponse with list of extracted claims
    """
    try:
        logger.info(f"🔬 HTTP Extraction endpoint called for session {request.session_id}")

        # Call the extraction function directly using imported invoke_model
        claims: List[Claim] = await extract_claims_from_content(
            content=request.content,
            source_id=request.source_id,
            source_url=request.source_url,
            source_title=request.source_title,
            session_id=request.session_id,
            query=request.query,
            sub_question_id=request.sub_question_id,
            model_coordinator=model_coordinator,
            current_iteration=request.current_iteration,
            invoke_model_func=invoke_model
        )

        logger.info(f"✅ Extracted {len(claims)} claims via HTTP endpoint")

        # Convert Claim objects to response models
        claim_responses = []
        for claim in claims:
            evidence_responses = [
                EvidenceSpanResponse(
                    source_id=ev.source_id,
                    url=ev.url,
                    title=ev.title,
                    quote=ev.quote,
                    char_start=ev.char_start,
                    char_end=ev.char_end
                )
                for ev in claim.evidence
            ]

            claim_responses.append(
                ClaimResponse(
                    id=claim.id,
                    session_id=claim.session_id,
                    sub_question_id=claim.sub_question_id,
                    text=claim.text,
                    evidence=evidence_responses,
                    entailment_score=claim.entailment_score,
                    provenance_score=claim.provenance_score,
                    dedupe_fingerprint=claim.dedupe_fingerprint,
                    confidence=claim.confidence,
                    claim_type=getattr(claim, "claim_type", "fact")
                )
            )

        return ExtractClaimsResponse(
            claims=claim_responses,
            count=len(claim_responses),
            message=f"Successfully extracted {len(claim_responses)} claims"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error in HTTP extraction endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Extraction failed: {str(e)}")
