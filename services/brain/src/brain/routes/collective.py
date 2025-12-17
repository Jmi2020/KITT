
from __future__ import annotations
import asyncio
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Callable

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, Query
from prometheus_client import Counter, Histogram
from pydantic import BaseModel, ConfigDict, Field

from common.db.conversations import record_conversation_message
from common.db.models import ConversationRole

from ..agents.collective.metrics import pairwise_diversity

# Use async graph for better performance (concurrent proposals)
# Fall back to sync graph if async disabled via env var
USE_ASYNC_GRAPH = os.getenv("COLLECTIVE_USE_ASYNC", "true").lower() == "true"

if USE_ASYNC_GRAPH:
    from ..agents.collective.graph_async import build_collective_graph_async
    _graph = build_collective_graph_async()
else:
    from ..agents.collective.graph import build_collective_graph
    _graph = build_collective_graph()

# Optional: reuse coding graph for 'pipeline' pattern if available
# NOTE: coder-agent service is not yet implemented in KITTY
# When available, uncomment and adapt this import:
# try:
#     from ..agents.graphs.coding_graph import build_coding_graph
#     _HAS_CODING = True
# except Exception:
#     _HAS_CODING = False
_HAS_CODING = False

router = APIRouter(prefix="/api/collective", tags=["collective"])
logger = logging.getLogger(__name__)

# Prometheus metrics
collective_requests = Counter(
    "collective_requests_total",
    "Total collective meta-agent requests",
    ["pattern", "status"]
)

collective_latency = Histogram(
    "collective_latency_seconds",
    "Collective execution latency by pattern",
    ["pattern"],
    buckets=[1, 5, 10, 30, 60, 120, 180, 300, 600]
)

proposal_count = Histogram(
    "collective_proposals_count",
    "Number of proposals generated",
    ["pattern"],
    buckets=[1, 2, 3, 4, 5, 6, 7, 10]
)

verdict_length = Histogram(
    "collective_verdict_length_chars",
    "Length of judge verdict in characters",
    ["pattern"],
    buckets=[50, 100, 200, 500, 1000, 2000, 5000]
)

proposal_diversity = Histogram(
    "collective_proposal_diversity",
    "Diversity of proposals (1 - avg Jaccard similarity)",
    ["pattern"],
    buckets=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
)

class RunReq(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    task: str = Field(..., description="Natural language task")
    pattern: Literal["pipeline","council","debate"] = "pipeline"
    k: int = Field(3, ge=2, le=7, description="council size")
    max_steps: int = Field(8, ge=1, le=20)
    conversation_id: Optional[str] = Field(default=None, alias="conversationId")
    user_id: Optional[str] = Field(default=None, alias="userId")

class Proposal(BaseModel):
    role: str
    text: str
    label: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = None

class RunRes(BaseModel):
    pattern: str
    proposals: List[Proposal]
    verdict: str
    logs: Optional[str] = None
    peer_reviews: Optional[List[Dict[str, Any]]] = None
    aggregate_rankings: Optional[List[Dict[str, Any]]] = None
    peer_review_enabled: bool = True
    aux: Dict[str, Any] = {}

@router.post("/run", response_model=RunRes)
async def run_collective(req: RunReq):
    """Execute collective meta-agent pattern (council, debate, or pipeline).

    Patterns:
    - council: K independent specialists propose solutions, deep reasoner judges and synthesizes
      * With async: All K proposals generated concurrently (~K speedup)
    - debate: PRO vs CON argue, deep reasoner judges
      * With async: PRO and CON generated concurrently (~2x speedup)
    - pipeline: Sequential workflow (requires coding graph - not yet implemented)

    Performance (Quality-First mode with async enabled):
    - Council k=3: ~60s (vs ~90s sync) - 33% faster
    - Debate: ~50s (vs ~75s sync) - 33% faster

    Example:
        POST /api/collective/run
        {
            "task": "Compare PETG vs ABS settings for Voron at 0.2mm layer height",
            "pattern": "council",
            "k": 3
        }

    Returns:
        - proposals: List of agent proposals with roles
        - verdict: Final synthesized decision from deep reasoner judge
        - logs: Execution logs
    """
    start_time = time.time()
    status = "success"

    if req.conversation_id:
        try:
            record_conversation_message(
                conversation_id=req.conversation_id,
                role=ConversationRole.user,
                content=f"[collective:{req.pattern}] {req.task}",
                user_id=req.user_id,
                metadata={
                    "command": "collective",
                    "pattern": req.pattern,
                    "k": req.k,
                },
                title_hint=req.task,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to record collective request for %s: %s",
                req.conversation_id,
                exc,
            )

    try:
        proposals: List[Proposal] = []
        logs: List[str] = []

        # If pipeline and coding graph exists, run it and collect as single proposal
        if req.pattern == "pipeline" and _HAS_CODING:
            # Future implementation when coder-agent service is ready
            # cgraph = build_coding_graph()
            # st = {"user_request": req.task}
            # out = await cgraph.ainvoke(st)  # Use async invoke
            # final_md = out.get("final_answer") or out.get("result") or ""
            # proposals.append(Proposal(role="pipeline", text=final_md))
            # logs.append("[pipeline] executed coding graph")
            # state = {"task": req.task, "pattern": "pipeline", "proposals": [final_md]}
            # result = await _graph.ainvoke(state)  # Use async invoke
            # return RunRes(
            #     pattern="pipeline",
            #     proposals=proposals,
            #     verdict=result.get("verdict",""),
            #     logs="\n".join(logs),
            #     aux={
            #         "passed": out.get("passed"),
            #         "stdout": out.get("run_stdout"),
            #         "stderr": out.get("run_stderr"),
            #     }
            # )
            pass

        # Use council/debate (or pipeline fallback without coding graph)
        state = {"task": req.task, "pattern": req.pattern, "k": req.k}

        # Use async invoke if async graph enabled, otherwise sync
        if USE_ASYNC_GRAPH:
            result = await _graph.ainvoke(state)
        else:
            result = _graph.invoke(state)

        raw_props = result.get("proposals", [])
        for i, p in enumerate(raw_props):
            role = "pro" if (req.pattern=="debate" and i==0) else ("con" if (req.pattern=="debate" and i==1) else f"specialist_{i+1}")
            if isinstance(p, dict):
                proposals.append(
                    Proposal(
                        role=role,
                        text=p.get("content",""),
                        label=p.get("label"),
                        model=p.get("model"),
                        temperature=p.get("temperature"),
                    )
                )
            else:
                proposals.append(Proposal(role=role, text=str(p)))

        # Calculate diversity metrics
        diversity_metrics = pairwise_diversity(raw_props)

        # Record metrics before returning
        latency = time.time() - start_time
        collective_requests.labels(pattern=req.pattern, status=status).inc()
        collective_latency.labels(pattern=req.pattern).observe(latency)
        proposal_count.labels(pattern=req.pattern).observe(len(proposals))
        verdict_length.labels(pattern=req.pattern).observe(len(result.get("verdict", "")))
        proposal_diversity.labels(pattern=req.pattern).observe(diversity_metrics["avg_diversity"])

        verdict_text = result.get("verdict", "")
        peer_reviews = result.get("peer_reviews")
        aggregate_rankings = result.get("aggregate_rankings")

        if req.conversation_id:
            try:
                proposal_lines = [
                    f"{prop.role}: {prop.text.strip()}" for prop in proposals
                ]
                summary_lines = []
                if aggregate_rankings:
                    summary_lines.append("Aggregate ranking:")
                    for r in aggregate_rankings:
                        summary_lines.append(
                            f"- {r.get('label','')} ({r.get('model','')}): avg_rank={r.get('average_rank')}"
                        )
                assistant_body = "\n\n".join(
                    proposal_lines
                    + (["\n".join(summary_lines)] if summary_lines else [])
                    + [f"Verdict: {verdict_text}"]
                )
                record_conversation_message(
                    conversation_id=req.conversation_id,
                    role=ConversationRole.assistant,
                    content=assistant_body,
                    metadata={
                        "command": "collective",
                        "pattern": req.pattern,
                        "k": req.k,
                        "proposalCount": len(proposals),
                        "verdict": verdict_text,
                        "aggregate_rankings": aggregate_rankings,
                    },
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Failed to record collective response for %s: %s",
                    req.conversation_id,
                    exc,
                )

        return RunRes(
            pattern=req.pattern,
            proposals=proposals,
            verdict=verdict_text,
            logs=result.get("logs",""),
            peer_reviews=peer_reviews,
            aggregate_rankings=aggregate_rankings,
            peer_review_enabled=os.getenv("COLLECTIVE_ENABLE_PEER_REVIEW", "true").lower() == "true",
            aux={}
        )

    except Exception as exc:
        status = "error"
        collective_requests.labels(pattern=req.pattern, status=status).inc()
        if req.conversation_id:
            try:
                record_conversation_message(
                    conversation_id=req.conversation_id,
                    role=ConversationRole.assistant,
                    content=f"Collective request failed: {exc}",
                    metadata={
                        "command": "collective",
                        "pattern": req.pattern,
                        "k": req.k,
                        "error": True,
                    },
                )
            except Exception as log_exc:  # noqa: BLE001
                logger.warning(
                    "Failed to record collective error for %s: %s",
                    req.conversation_id,
                    log_exc,
                )
        raise


# =============================================================================
# Session Management for Streaming
# =============================================================================

class CollectiveSession:
    """Tracks a collective run for streaming progress."""

    def __init__(
        self,
        session_id: str,
        task: str,
        pattern: str,
        k: int,
        user_id: Optional[str] = None,
    ):
        self.session_id = session_id
        self.task = task
        self.pattern = pattern
        self.k = k
        self.user_id = user_id
        self.created_at = datetime.now(timezone.utc)
        self.status = "pending"
        self.proposals: List[Dict[str, Any]] = []
        self.verdict: Optional[str] = None
        self.error: Optional[str] = None
        self._callbacks: List[Callable] = []

    def add_callback(self, callback: Callable):
        """Register a callback for progress events."""
        self._callbacks.append(callback)

    def remove_callback(self, callback: Callable):
        """Remove a callback."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    async def emit(self, event: Dict[str, Any]):
        """Emit an event to all callbacks."""
        for callback in self._callbacks:
            try:
                await callback(event)
            except Exception as e:
                logger.warning(f"Callback error: {e}")


# In-memory session store (could be Redis for production)
_sessions: Dict[str, CollectiveSession] = {}
_sessions_lock = asyncio.Lock()


async def get_or_create_session(
    task: str,
    pattern: str,
    k: int,
    user_id: Optional[str] = None,
) -> CollectiveSession:
    """Create a new collective session."""
    session_id = str(uuid.uuid4())
    session = CollectiveSession(
        session_id=session_id,
        task=task,
        pattern=pattern,
        k=k,
        user_id=user_id,
    )
    async with _sessions_lock:
        _sessions[session_id] = session
    return session


async def get_session(session_id: str) -> Optional[CollectiveSession]:
    """Get a session by ID."""
    async with _sessions_lock:
        return _sessions.get(session_id)


# =============================================================================
# Streaming Execution
# =============================================================================

async def run_collective_streaming(session: CollectiveSession):
    """Run collective with streaming events."""
    from ..agents.collective.graph_async import (
        n_plan,
        n_propose_council,
        n_propose_debate,
        n_judge,
        CollectiveState,
    )

    try:
        session.status = "running"
        await session.emit({
            "type": "started",
            "session_id": session.session_id,
            "pattern": session.pattern,
            "k": session.k,
            "task": session.task,
        })

        # Initialize state
        state: CollectiveState = {
            "task": session.task,
            "pattern": session.pattern,
            "k": session.k,
            "proposals": [],
            "verdict": "",
            "logs": "",
        }

        # Plan phase
        await session.emit({"type": "plan_start"})
        state = await n_plan(state)
        await session.emit({
            "type": "plan_complete",
            "plan": state.get("logs", ""),
        })

        # Propose phase - run with progress tracking
        if session.pattern == "council":
            await session.emit({
                "type": "proposals_start",
                "count": session.k,
            })

            # Run proposals with individual progress
            state = await _run_council_with_streaming(state, session)

        elif session.pattern == "debate":
            await session.emit({
                "type": "proposals_start",
                "count": 2,
            })
            state = await n_propose_debate(state)

            # Emit debate results
            proposals = state.get("proposals", [])
            for i, prop in enumerate(proposals):
                role = "pro" if i == 0 else "con"
                await session.emit({
                    "type": "proposal_complete",
                    "index": i,
                    "role": role,
                    "text": prop if isinstance(prop, str) else prop.get("content", ""),
                })
                session.proposals.append({
                    "role": role,
                    "text": prop if isinstance(prop, str) else prop.get("content", ""),
                })

        # Judge phase
        await session.emit({"type": "judge_start"})
        state = await n_judge(state)
        verdict = state.get("verdict", "")

        await session.emit({
            "type": "verdict_complete",
            "verdict": verdict,
        })

        session.verdict = verdict
        session.status = "completed"

        await session.emit({
            "type": "complete",
            "session_id": session.session_id,
            "proposals": session.proposals,
            "verdict": verdict,
        })

    except Exception as e:
        session.status = "error"
        session.error = str(e)
        logger.error(f"Collective streaming error: {e}")
        await session.emit({
            "type": "error",
            "message": str(e),
        })


async def _run_council_with_streaming(
    state: CollectiveState,
    session: CollectiveSession,
) -> CollectiveState:
    """Run council proposals with streaming progress."""
    from ..agents.collective.context_policy import fetch_domain_context
    from ..agents.collective.graph_async import (
        HALLUCINATION_PREVENTION,
        EVIDENCE_REQUIREMENTS,
        DECISION_FRAMEWORK,
        HINT_PROPOSER,
    )
    from brain.token_budgets import summarize_conversation
    from brain.llm_client import chat_async

    k = int(state.get("k", 3))
    conversation_history = state.get("conversation_history", [])
    conv_summary = summarize_conversation(conversation_history, max_tokens=2000) if conversation_history else ""

    context = fetch_domain_context(
        state["task"],
        limit=10,
        for_proposer=True,
        token_budget=10000
    )

    async def generate_and_emit(i: int) -> str:
        role = f"specialist_{i+1}"
        await session.emit({
            "type": "proposal_start",
            "index": i,
            "role": role,
        })

        temperature = 0.7 + (i * 0.1)
        max_tokens = 6000 + (i * 500)

        system_prompt = f"""You are {role}, an expert specialist providing independent analysis.

## Your Role
{HINT_PROPOSER}
{HALLUCINATION_PREVENTION}
{EVIDENCE_REQUIREMENTS}
{DECISION_FRAMEWORK}

## Response Guidelines
- Provide a detailed, well-justified proposal
- Structure your response with clear sections (Analysis, Recommendation, Rationale)
- Include confidence level for your recommendation (High/Medium/Low)
- End with any caveats or limitations of your analysis"""

        user_prompt_parts = []
        if conv_summary:
            user_prompt_parts.append(f"## Conversation Context\n{conv_summary}")
        user_prompt_parts.append(f"## Task\n{state['task']}")
        user_prompt_parts.append(f"## Relevant Knowledge\n{context}")
        user_prompt_parts.append(
            "\n## Your Proposal\nProvide your expert analysis and recommendation. "
            "Reference KB chunks using [KB#id] when citing evidence."
        )
        user_prompt = "\n\n".join(user_prompt_parts)

        response, metadata = await chat_async([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ], which="Q4", temperature=temperature, max_tokens=max_tokens)

        await session.emit({
            "type": "proposal_complete",
            "index": i,
            "role": role,
            "text": response,
            "model": "Q4",
            "temperature": temperature,
        })

        session.proposals.append({
            "role": role,
            "text": response,
            "model": "Q4",
            "temperature": temperature,
        })

        return response

    # Run all proposals in parallel
    props = await asyncio.gather(*[generate_and_emit(i) for i in range(k)])

    return {**state, "proposals": list(props)}


# =============================================================================
# Streaming API Endpoints
# =============================================================================

class StreamRunReq(BaseModel):
    """Request to start a streaming collective run."""
    model_config = ConfigDict(populate_by_name=True)

    task: str = Field(..., description="Natural language task")
    pattern: Literal["pipeline", "council", "debate"] = "council"
    k: int = Field(3, ge=2, le=7, description="Council size")
    user_id: Optional[str] = Field(default=None, alias="userId")


class StreamRunRes(BaseModel):
    """Response with session ID for streaming."""
    session_id: str
    status: str
    message: str


@router.post("/stream/start", response_model=StreamRunRes)
async def start_streaming_collective(req: StreamRunReq):
    """Start a collective run with streaming support.

    Creates a session that can be monitored via WebSocket.

    Example:
        POST /api/collective/stream/start
        {
            "task": "Compare PETG vs ABS for outdoor use",
            "pattern": "council",
            "k": 3
        }

    Returns:
        session_id to connect via WebSocket
    """
    session = await get_or_create_session(
        task=req.task,
        pattern=req.pattern,
        k=req.k,
        user_id=req.user_id,
    )

    # Start execution in background
    asyncio.create_task(run_collective_streaming(session))

    return StreamRunRes(
        session_id=session.session_id,
        status="started",
        message="Connect to WebSocket to receive streaming updates",
    )


@router.websocket("/stream/{session_id}")
async def stream_collective_progress(
    websocket: WebSocket,
    session_id: str,
):
    """Stream real-time collective progress via WebSocket.

    Sends JSON messages with progress updates:
    - started: Session started
    - plan_start/plan_complete: Planning phase
    - proposals_start: Beginning proposal generation
    - proposal_start: Individual proposal started
    - proposal_complete: Individual proposal completed with text
    - judge_start: Judge synthesis started
    - verdict_complete: Final verdict ready
    - complete: Session completed with full results
    - error: Error occurred

    Example (JavaScript):
        ```javascript
        const ws = new WebSocket('ws://localhost:8080/api/collective/stream/{session_id}');

        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.type === 'proposal_complete') {
                console.log(`Specialist ${data.index + 1}: ${data.text}`);
            }
        };
        ```
    """
    await websocket.accept()

    # Send connection confirmation
    await websocket.send_json({
        "type": "connection",
        "session_id": session_id,
        "message": "Connected to collective stream",
    })

    session = await get_session(session_id)
    if not session:
        await websocket.send_json({
            "type": "error",
            "message": f"Session {session_id} not found",
        })
        await websocket.close()
        return

    # Track if we've received the completion event
    completion_received = asyncio.Event()

    async def send_event_with_completion_check(event: Dict[str, Any]):
        try:
            await websocket.send_json(event)
            # Signal completion when we get terminal events
            if event.get("type") in ("complete", "error", "cancelled"):
                completion_received.set()
        except Exception as e:
            logger.warning(f"WebSocket send error: {e}")
            completion_received.set()  # Unblock on error

    session.add_callback(send_event_with_completion_check)

    try:
        # If session already completed, send final state
        if session.status == "completed":
            await websocket.send_json({
                "type": "complete",
                "session_id": session.session_id,
                "proposals": session.proposals,
                "verdict": session.verdict,
            })
            completion_received.set()
        elif session.status == "error":
            await websocket.send_json({
                "type": "error",
                "message": session.error,
            })
            completion_received.set()

        # Keep connection open until completion event is received
        while not completion_received.is_set():
            try:
                # Check for client messages (e.g., cancel request)
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=1.0,
                )
                if data == "cancel":
                    session.status = "cancelled"
                    await websocket.send_json({
                        "type": "cancelled",
                        "message": "Session cancelled by client",
                    })
                    completion_received.set()
                    break
            except asyncio.TimeoutError:
                # No message, continue waiting
                continue
            except WebSocketDisconnect:
                break

        # Give a moment for any final events to be processed
        await asyncio.sleep(0.1)

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for session {session_id}")
    finally:
        session.remove_callback(send_event_with_completion_check)


@router.get("/sessions")
async def list_collective_sessions(
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of sessions"),
):
    """List recent collective sessions.

    Returns recent sessions for viewing history.
    """
    async with _sessions_lock:
        sessions = list(_sessions.values())

    # Filter
    if user_id:
        sessions = [s for s in sessions if s.user_id == user_id]
    if status:
        sessions = [s for s in sessions if s.status == status]

    # Sort by created_at descending
    sessions.sort(key=lambda s: s.created_at, reverse=True)

    # Limit
    sessions = sessions[:limit]

    return {
        "sessions": [
            {
                "session_id": s.session_id,
                "task": s.task,
                "pattern": s.pattern,
                "k": s.k,
                "status": s.status,
                "created_at": s.created_at.isoformat(),
                "proposals_count": len(s.proposals),
                "has_verdict": s.verdict is not None,
            }
            for s in sessions
        ],
        "total": len(sessions),
    }


@router.get("/sessions/{session_id}")
async def get_collective_session(session_id: str):
    """Get details for a specific collective session."""
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "session_id": session.session_id,
        "task": session.task,
        "pattern": session.pattern,
        "k": session.k,
        "status": session.status,
        "created_at": session.created_at.isoformat(),
        "proposals": session.proposals,
        "verdict": session.verdict,
        "error": session.error,
    }
