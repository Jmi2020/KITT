
from __future__ import annotations
import asyncio
import logging
import os
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Callable

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, Query
from prometheus_client import Counter, Histogram
from pydantic import BaseModel, ConfigDict, Field

from common.db.conversations import record_conversation_message
from common.db.models import ConversationRole

from ..agents.collective.metrics import pairwise_diversity
from ..agents.collective.providers import (
    get_available_specialists,
    get_specialists_by_ids,
    estimate_total_cost,
    SpecialistConfig,
)

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


# =============================================================================
# Specialist Provider Endpoints
# =============================================================================

class SpecialistConfigResponse(BaseModel):
    """Specialist configuration for API response."""
    id: str
    display_name: str
    provider: str
    model: str
    description: str
    cost_per_1m_in: float
    cost_per_1m_out: float
    is_available: bool


class SpecialistsListResponse(BaseModel):
    """Response listing available specialists."""
    specialists: List[SpecialistConfigResponse]
    local_count: int
    cloud_count: int
    available_count: int


class CostEstimateRequest(BaseModel):
    """Request to estimate cost for selected specialists."""
    specialist_ids: List[str]
    tokens_per_proposal: int = Field(4000, ge=1000, le=20000)


class CostEstimateResponse(BaseModel):
    """Response with estimated cost."""
    specialist_ids: List[str]
    estimated_cost_usd: float
    tokens_per_proposal: int


@router.get("/specialists", response_model=SpecialistsListResponse)
async def list_specialists(
    include_unavailable: bool = Query(
        True, description="Include specialists without API keys"
    ),
):
    """List available specialists for collective deliberation.

    Returns local models (always available) and cloud providers
    (available if API key is configured).

    Example:
        GET /api/collective/specialists

    Returns:
        - specialists: List of available specialists with config
        - local_count: Number of local models
        - cloud_count: Number of cloud providers
        - available_count: Number currently available (API keys set)
    """
    specialists = get_available_specialists(include_unavailable=include_unavailable)

    return SpecialistsListResponse(
        specialists=[
            SpecialistConfigResponse(
                id=s.id,
                display_name=s.display_name,
                provider=s.provider,
                model=s.model,
                description=s.description,
                cost_per_1m_in=s.cost_per_1m_in,
                cost_per_1m_out=s.cost_per_1m_out,
                is_available=s.is_available,
            )
            for s in specialists
        ],
        local_count=sum(1 for s in specialists if s.provider == "local"),
        cloud_count=sum(1 for s in specialists if s.provider != "local"),
        available_count=sum(1 for s in specialists if s.is_available),
    )


@router.post("/specialists/estimate", response_model=CostEstimateResponse)
async def estimate_specialist_cost(req: CostEstimateRequest):
    """Estimate cost for running collective with selected specialists.

    Example:
        POST /api/collective/specialists/estimate
        {
            "specialist_ids": ["local_q4", "openai_gpt4o_mini", "anthropic_haiku"],
            "tokens_per_proposal": 4000
        }

    Returns:
        - estimated_cost_usd: Total estimated cost
    """
    cost = estimate_total_cost(req.specialist_ids, req.tokens_per_proposal)

    return CostEstimateResponse(
        specialist_ids=req.specialist_ids,
        estimated_cost_usd=cost,
        tokens_per_proposal=req.tokens_per_proposal,
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
        enable_search_phase: bool = False,
        selected_specialists: Optional[List[str]] = None,
    ):
        self.session_id = session_id
        self.task = task
        self.pattern = pattern
        self.k = k
        self.user_id = user_id
        self.enable_search_phase = enable_search_phase
        self.selected_specialists = selected_specialists  # List of specialist IDs
        self.specialist_configs: List[SpecialistConfig] = []  # Resolved configs
        self.created_at = datetime.now(timezone.utc)
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        self.status = "pending"
        self.proposals: List[Dict[str, Any]] = []
        self.verdict: Optional[str] = None
        self.error: Optional[str] = None
        self.search_results: Dict[str, Any] = {}
        self.phase1_outputs: List[Dict[str, Any]] = []
        self._callbacks: List[Callable] = []

        # Resolve specialist configs if IDs provided
        if selected_specialists:
            self.specialist_configs = get_specialists_by_ids(selected_specialists)
            # Update k to match specialist count
            self.k = len(self.specialist_configs)

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


# In-memory session store (for active sessions)
_sessions: Dict[str, CollectiveSession] = {}
_sessions_lock = asyncio.Lock()


# =============================================================================
# Database Persistence
# =============================================================================

def _get_db_session():
    """Get a database session."""
    try:
        from common.db import SessionLocal
        return SessionLocal()
    except Exception as e:
        logger.warning(f"Could not get database session: {e}")
        return None


async def _save_session_to_db(session: CollectiveSession):
    """Save a collective session to the database."""
    db = _get_db_session()
    if not db:
        return

    try:
        from common.db.models import CollectiveSessionRecord, CollectivePatternEnum, CollectiveStatusEnum

        # Map status string to enum
        status_map = {
            "pending": CollectiveStatusEnum.pending,
            "running": CollectiveStatusEnum.running,
            "completed": CollectiveStatusEnum.completed,
            "error": CollectiveStatusEnum.error,
            "cancelled": CollectiveStatusEnum.cancelled,
        }

        # Map pattern string to enum
        pattern_map = {
            "council": CollectivePatternEnum.council,
            "debate": CollectivePatternEnum.debate,
            "pipeline": CollectivePatternEnum.pipeline,
        }

        # Check if session already exists
        existing = db.query(CollectiveSessionRecord).filter(
            CollectiveSessionRecord.id == session.session_id
        ).first()

        proposals_data = [
            {
                "role": p.get("role", ""),
                "text": p.get("text", ""),
                "model": p.get("model"),
                "provider": p.get("provider"),
                "temperature": p.get("temperature"),
            }
            for p in (session.proposals or [])
        ]

        if existing:
            # Update existing record
            existing.status = status_map.get(session.status, CollectiveStatusEnum.pending)
            existing.proposals = proposals_data
            existing.verdict = session.verdict
            existing.error_message = session.error
            existing.completed_at = session.completed_at
            existing.started_at = session.started_at
            existing.specialists_used = session.selected_specialists or []
            existing.search_enabled = session.enable_search_phase
        else:
            # Create new record
            record = CollectiveSessionRecord(
                id=session.session_id,
                user_id=session.user_id,
                task=session.task,
                pattern=pattern_map.get(session.pattern, CollectivePatternEnum.council),
                k=session.k,
                status=status_map.get(session.status, CollectiveStatusEnum.pending),
                proposals=proposals_data,
                verdict=session.verdict,
                error_message=session.error,
                specialists_used=session.selected_specialists or [],
                search_enabled=session.enable_search_phase,
                created_at=session.created_at,
                started_at=session.started_at,
                completed_at=session.completed_at,
            )
            db.add(record)

        db.commit()
        logger.debug(f"Saved session {session.session_id} to database")
    except Exception as e:
        logger.warning(f"Failed to save session to database: {e}")
        db.rollback()
    finally:
        db.close()


async def _load_sessions_from_db(
    user_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 20,
) -> List[Dict]:
    """Load collective sessions from the database."""
    db = _get_db_session()
    if not db:
        return []

    try:
        from common.db.models import CollectiveSessionRecord

        query = db.query(CollectiveSessionRecord)

        if user_id:
            query = query.filter(CollectiveSessionRecord.user_id == user_id)
        if status:
            from common.db.models import CollectiveStatusEnum
            status_map = {
                "pending": CollectiveStatusEnum.pending,
                "running": CollectiveStatusEnum.running,
                "completed": CollectiveStatusEnum.completed,
                "error": CollectiveStatusEnum.error,
                "cancelled": CollectiveStatusEnum.cancelled,
            }
            if status in status_map:
                query = query.filter(CollectiveSessionRecord.status == status_map[status])

        query = query.order_by(CollectiveSessionRecord.created_at.desc())
        query = query.limit(limit)

        records = query.all()

        return [
            {
                "session_id": r.id,
                "task": r.task,
                "pattern": r.pattern.value if r.pattern else "council",
                "k": r.k,
                "status": r.status.value if r.status else "pending",
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "proposals_count": len(r.proposals or []),
                "has_verdict": bool(r.verdict),
                "user_id": r.user_id,
            }
            for r in records
        ]
    except Exception as e:
        logger.warning(f"Failed to load sessions from database: {e}")
        return []
    finally:
        db.close()


async def _load_session_details_from_db(session_id: str) -> Optional[Dict]:
    """Load full session details from the database."""
    db = _get_db_session()
    if not db:
        return None

    try:
        from common.db.models import CollectiveSessionRecord

        record = db.query(CollectiveSessionRecord).filter(
            CollectiveSessionRecord.id == session_id
        ).first()

        if not record:
            return None

        return {
            "session_id": record.id,
            "task": record.task,
            "pattern": record.pattern.value if record.pattern else "council",
            "k": record.k,
            "status": record.status.value if record.status else "pending",
            "created_at": record.created_at.isoformat() if record.created_at else None,
            "started_at": record.started_at.isoformat() if record.started_at else None,
            "completed_at": record.completed_at.isoformat() if record.completed_at else None,
            "proposals": record.proposals or [],
            "verdict": record.verdict,
            "error": record.error_message,
            "user_id": record.user_id,
            "specialists_used": record.specialists_used or [],
            "search_enabled": record.search_enabled,
        }
    except Exception as e:
        logger.warning(f"Failed to load session details from database: {e}")
        return None
    finally:
        db.close()


async def _delete_session_from_db(session_id: str) -> bool:
    """Delete a collective session from the database.

    Returns True if deleted, False if not found.
    """
    db = _get_db_session()
    if not db:
        return False

    try:
        from common.db.models import CollectiveSessionRecord

        record = db.query(CollectiveSessionRecord).filter(
            CollectiveSessionRecord.id == session_id
        ).first()

        if not record:
            return False

        db.delete(record)
        db.commit()
        logger.info(f"Deleted collective session {session_id} from database")
        return True
    except Exception as e:
        logger.error(f"Failed to delete session from database: {e}")
        db.rollback()
        return False
    finally:
        db.close()


async def get_or_create_session(
    task: str,
    pattern: str,
    k: int,
    user_id: Optional[str] = None,
    enable_search_phase: bool = False,
    selected_specialists: Optional[List[str]] = None,
) -> CollectiveSession:
    """Create a new collective session and persist to database."""
    session_id = str(uuid.uuid4())
    session = CollectiveSession(
        session_id=session_id,
        task=task,
        pattern=pattern,
        k=k,
        user_id=user_id,
        enable_search_phase=enable_search_phase,
        selected_specialists=selected_specialists,
    )
    async with _sessions_lock:
        _sessions[session_id] = session

    # Persist to database
    await _save_session_to_db(session)

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
        session.started_at = datetime.now(timezone.utc)

        # Include specialist info in started event
        specialist_info = None
        if session.specialist_configs:
            specialist_info = [
                {
                    "id": s.id,
                    "display_name": s.display_name,
                    "provider": s.provider,
                    "model": s.model,
                }
                for s in session.specialist_configs
            ]

        await session.emit({
            "type": "started",
            "session_id": session.session_id,
            "pattern": session.pattern,
            "k": session.k,
            "task": session.task,
            "enable_search_phase": session.enable_search_phase,
            "specialists": specialist_info,
        })

        # Initialize state
        state: CollectiveState = {
            "task": session.task,
            "pattern": session.pattern,
            "k": session.k,
            "proposals": [],
            "verdict": "",
            "logs": "",
            "enable_search_phase": session.enable_search_phase,
        }

        # Add specialist configs to state if provided
        if session.specialist_configs:
            state["specialist_configs"] = session.specialist_configs

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
                "two_phase": session.enable_search_phase,
            })

            if session.enable_search_phase:
                # Run two-phase proposals with search integration
                state = await _run_council_two_phase_streaming(state, session)
            else:
                # Run standard proposals
                state = await _run_council_with_streaming(state, session)

        elif session.pattern == "debate":
            await session.emit({
                "type": "proposals_start",
                "count": 2,
                "two_phase": session.enable_search_phase,
            })

            if session.enable_search_phase:
                # Run two-phase debate with search integration
                state = await _run_debate_two_phase_streaming(state, session)
            else:
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
        session.completed_at = datetime.now(timezone.utc)

        # Include search metadata in completion
        completion_data = {
            "type": "complete",
            "session_id": session.session_id,
            "proposals": session.proposals,
            "verdict": verdict,
        }
        if session.enable_search_phase:
            completion_data["search_metadata"] = {
                "phase1_outputs": session.phase1_outputs,
                "search_results_count": len(session.search_results),
            }

        await session.emit(completion_data)

        # Persist completed session to database
        await _save_session_to_db(session)

    except Exception as e:
        session.status = "error"
        session.error = str(e)
        session.completed_at = datetime.now(timezone.utc)
        logger.error(f"Collective streaming error: {e}")
        await session.emit({
            "type": "error",
            "message": str(e),
        })

        # Persist error session to database
        await _save_session_to_db(session)


async def _run_council_with_streaming(
    state: CollectiveState,
    session: CollectiveSession,
) -> CollectiveState:
    """Run council proposals with streaming progress.

    Supports both:
    - Legacy mode: Uses K local Q4 specialists
    - Multi-provider mode: Uses selected specialist configs (local + cloud)
    """
    from ..agents.collective.context_policy import fetch_domain_context
    from ..agents.collective.graph_async import (
        HALLUCINATION_PREVENTION,
        EVIDENCE_REQUIREMENTS,
        DECISION_FRAMEWORK,
        HINT_PROPOSER,
        generate_proposal_for_specialist,
    )
    from brain.token_budgets import summarize_conversation
    from brain.llm_client import chat_async

    conversation_history = state.get("conversation_history", [])
    conv_summary = summarize_conversation(conversation_history, max_tokens=2000) if conversation_history else ""

    context = fetch_domain_context(
        state["task"],
        limit=10,
        for_proposer=True,
        token_budget=10000
    )

    # Check if multi-provider mode (specialist configs provided)
    if session.specialist_configs:
        # Multi-provider mode: use selected specialists
        async def generate_and_emit_multi(i: int, spec: SpecialistConfig) -> str:
            role = spec.display_name
            await session.emit({
                "type": "proposal_start",
                "index": i,
                "role": role,
                "provider": spec.provider,
                "model": spec.model,
            })

            result = await generate_proposal_for_specialist(
                specialist=spec,
                task=state["task"],
                context=context,
                conv_summary=conv_summary,
                index=i,
            )

            await session.emit({
                "type": "proposal_complete",
                "index": i,
                "role": role,
                "text": result["text"],
                "model": result["model"],
                "provider": result["provider"],
                "temperature": result.get("temperature"),
                "cost_usd": result.get("cost_usd", 0),
            })

            session.proposals.append({
                "role": role,
                "text": result["text"],
                "model": result["model"],
                "provider": result["provider"],
                "temperature": result.get("temperature"),
                "cost_usd": result.get("cost_usd", 0),
            })

            return result["text"]

        # Run all proposals in parallel
        props = await asyncio.gather(*[
            generate_and_emit_multi(i, spec)
            for i, spec in enumerate(session.specialist_configs)
        ])

        # Calculate total cost
        total_cost = sum(p.get("cost_usd", 0) for p in session.proposals)
        if total_cost > 0:
            logger.info(f"Multi-provider council total cost: ${total_cost:.4f}")

        return {**state, "proposals": list(props)}

    # Legacy mode: use K local Q4 specialists
    k = int(state.get("k", 3))

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


async def _run_council_two_phase_streaming(
    state: CollectiveState,
    session: CollectiveSession,
) -> CollectiveState:
    """Run two-phase council proposals with streaming progress.

    Supports both:
    - Legacy mode: Uses K local Q4 specialists
    - Multi-provider mode: Uses selected specialist configs (local + cloud)

    Phase 1: Specialists generate search requests (fast, parallel, always local)
    Central: Execute deduplicated searches via MCP
    Phase 2: Specialists generate full proposals with search results (parallel, multi-provider)
    """
    from ..agents.collective.graph_async import (
        generate_phase1_search_requests,
        execute_searches_centralized,
        generate_phase2_proposal,
        generate_proposal_for_specialist,
    )
    from ..agents.collective.context_policy import fetch_domain_context
    from ..agents.collective.search_dedup import (
        deduplicate_search_requests,
        assign_results_to_specialists,
        get_dedup_stats,
    )
    from ..agents.collective.search_prompts import format_search_results_for_specialist
    from ..agents.collective.schemas import Phase1Output
    from brain.token_budgets import summarize_conversation

    # Determine specialist count from configs or K parameter
    use_multi_provider = bool(session.specialist_configs)
    k = len(session.specialist_configs) if use_multi_provider else int(state.get("k", 3))
    task = state["task"]

    # =========================================================================
    # PHASE 1: Collect search requests from all specialists
    # =========================================================================
    await session.emit({
        "type": "search_phase_start",
        "phase": 1,
        "specialist_count": k,
        "message": "Specialists identifying search needs...",
    })

    async def run_phase1(i: int) -> Phase1Output:
        specialist_id = f"specialist_{i+1}"
        await session.emit({
            "type": "phase1_start",
            "index": i,
            "specialist_id": specialist_id,
        })

        output = await generate_phase1_search_requests(
            task=task,
            specialist_id=specialist_id,
            kb_context=state.get("kb_context", ""),
            conversation_history=state.get("conversation_history", []),
        )

        await session.emit({
            "type": "phase1_complete",
            "index": i,
            "specialist_id": specialist_id,
            "search_request_count": len(output.search_requests),
            "confidence_without_search": output.confidence_without_search,
        })

        return output

    # Run all Phase 1 in parallel
    phase1_outputs = await asyncio.gather(*[run_phase1(i) for i in range(k)])
    session.phase1_outputs = [o.model_dump() for o in phase1_outputs]

    # =========================================================================
    # DEDUPLICATION: Merge similar queries across specialists
    # =========================================================================
    dedup_searches, original_to_canonical = deduplicate_search_requests(
        phase1_outputs,
        max_total_searches=9,
        similarity_threshold=0.7,
    )

    stats = get_dedup_stats(phase1_outputs, dedup_searches)

    await session.emit({
        "type": "search_requests_collected",
        "total_requests": stats["total_requests"],
        "unique_queries": stats["unique_queries"],
        "duplicates_removed": stats["duplicates_removed"],
        "queries": [s.query for s in dedup_searches],
    })

    # =========================================================================
    # CENTRAL FETCH: Execute searches via MCP
    # =========================================================================
    if dedup_searches:
        await session.emit({
            "type": "search_execution_start",
            "total": len(dedup_searches),
        })

        async def execute_and_emit(i: int, search):
            await session.emit({
                "type": "search_executing",
                "index": i,
                "total": len(dedup_searches),
                "query": search.query,
            })

            result = await execute_searches_centralized([search])
            success = search.query in result and result[search.query].success

            await session.emit({
                "type": "search_complete",
                "index": i,
                "query": search.query,
                "success": success,
                "result_count": result[search.query].result_count if success else 0,
            })

            return search.query, result.get(search.query)

        # Execute searches (can be parallel or sequential based on rate limits)
        search_results_list = await asyncio.gather(*[
            execute_and_emit(i, s) for i, s in enumerate(dedup_searches)
        ])
        search_results = {q: r for q, r in search_results_list if r}
        session.search_results = {q: r.results if r.success else [] for q, r in search_results.items()}

        # Map results back to each specialist
        specialist_results = assign_results_to_specialists(
            search_results,
            phase1_outputs,
            original_to_canonical,
        )

        await session.emit({
            "type": "search_phase_complete",
            "total_results": sum(len(r.results) for r in search_results.values() if r.success),
            "successful_queries": sum(1 for r in search_results.values() if r.success),
        })
    else:
        specialist_results = {}
        await session.emit({
            "type": "search_phase_complete",
            "total_results": 0,
            "successful_queries": 0,
            "message": "No searches requested by specialists",
        })

    # =========================================================================
    # PHASE 2: Generate full proposals with search results
    # =========================================================================
    await session.emit({
        "type": "proposal_phase_start",
        "specialist_count": k,
        "message": "Specialists generating proposals with search results...",
        "multi_provider": use_multi_provider,
    })

    # Prepare context for multi-provider mode
    if use_multi_provider:
        conversation_history = state.get("conversation_history", [])
        conv_summary = summarize_conversation(conversation_history, max_tokens=2000) if conversation_history else ""
        context = fetch_domain_context(task, limit=10, for_proposer=True, token_budget=10000)

    async def run_phase2(i: int) -> str:
        specialist_id = f"specialist_{i+1}"
        phase1_output = phase1_outputs[i]

        # Format search results for this specialist
        results_for_specialist = specialist_results.get(specialist_id, [])
        formatted_results = format_search_results_for_specialist(results_for_specialist)

        if use_multi_provider:
            # Multi-provider mode: use specialist configs
            spec = session.specialist_configs[i]
            role = spec.display_name

            await session.emit({
                "type": "proposal_start",
                "index": i,
                "role": role,
                "provider": spec.provider,
                "model": spec.model,
                "has_search_results": bool(results_for_specialist),
            })

            result = await generate_proposal_for_specialist(
                specialist=spec,
                task=task,
                context=context,
                conv_summary=conv_summary,
                index=i,
                search_results_formatted=formatted_results,
                phase1_assessment=phase1_output.initial_assessment,
            )

            await session.emit({
                "type": "proposal_complete",
                "index": i,
                "role": role,
                "text": result["text"],
                "model": result["model"],
                "provider": result["provider"],
                "temperature": result.get("temperature"),
                "cost_usd": result.get("cost_usd", 0),
                "search_results_used": len(results_for_specialist),
            })

            session.proposals.append({
                "role": role,
                "text": result["text"],
                "model": result["model"],
                "provider": result["provider"],
                "temperature": result.get("temperature"),
                "cost_usd": result.get("cost_usd", 0),
                "search_results_used": len(results_for_specialist),
            })

            return result["text"]

        else:
            # Legacy mode: use Q4 for all specialists
            await session.emit({
                "type": "proposal_start",
                "index": i,
                "role": specialist_id,
                "has_search_results": bool(results_for_specialist),
            })

            temperature = 0.7 + (i * 0.1)

            response = await generate_phase2_proposal(
                task=task,
                specialist_id=specialist_id,
                kb_context=state.get("kb_context", ""),
                search_results_formatted=formatted_results,
                phase1_assessment=phase1_output.initial_assessment,
                conversation_history=state.get("conversation_history", []),
                temperature=temperature,
            )

            await session.emit({
                "type": "proposal_complete",
                "index": i,
                "role": specialist_id,
                "text": response,
                "model": "Q4",
                "temperature": temperature,
                "search_results_used": len(results_for_specialist),
            })

            session.proposals.append({
                "role": specialist_id,
                "text": response,
                "model": "Q4",
                "temperature": temperature,
                "search_results_used": len(results_for_specialist),
            })

            return response

    # Run all Phase 2 in parallel
    props = await asyncio.gather(*[run_phase2(i) for i in range(k)])

    # Log total cost for multi-provider mode
    if use_multi_provider:
        total_cost = sum(p.get("cost_usd", 0) for p in session.proposals)
        if total_cost > 0:
            logger.info(f"Two-phase multi-provider council total cost: ${total_cost:.4f}")

    return {
        **state,
        "proposals": list(props),
        "phase1_outputs": session.phase1_outputs,
        "search_results": session.search_results,
    }


async def _run_debate_two_phase_streaming(
    state: CollectiveState,
    session: CollectiveSession,
) -> CollectiveState:
    """Run two-phase debate with streaming progress.

    Same as council but for PRO and CON positions.
    """
    from ..agents.collective.graph_async import (
        generate_phase1_search_requests,
        execute_searches_centralized,
        generate_phase2_proposal,
    )
    from ..agents.collective.search_dedup import (
        deduplicate_search_requests,
        assign_results_to_specialists,
    )
    from ..agents.collective.search_prompts import format_search_results_for_specialist
    from ..agents.collective.schemas import Phase1Output

    task = state["task"]
    roles = ["pro", "con"]

    # =========================================================================
    # PHASE 1: Collect search requests from both positions
    # =========================================================================
    await session.emit({
        "type": "search_phase_start",
        "phase": 1,
        "specialist_count": 2,
        "message": "Debate positions identifying search needs...",
    })

    async def run_phase1(i: int, role: str) -> Phase1Output:
        specialist_id = role
        await session.emit({
            "type": "phase1_start",
            "index": i,
            "specialist_id": specialist_id,
        })

        output = await generate_phase1_search_requests(
            task=f"Argue the {role.upper()} position for: {task}",
            specialist_id=specialist_id,
            kb_context=state.get("kb_context", ""),
            conversation_history=state.get("conversation_history", []),
        )

        await session.emit({
            "type": "phase1_complete",
            "index": i,
            "specialist_id": specialist_id,
            "search_request_count": len(output.search_requests),
        })

        return output

    # Run Phase 1 in parallel for both positions
    phase1_outputs = await asyncio.gather(*[run_phase1(i, r) for i, r in enumerate(roles)])
    session.phase1_outputs = [o.model_dump() for o in phase1_outputs]

    # Deduplicate
    dedup_searches, original_to_canonical = deduplicate_search_requests(
        phase1_outputs,
        max_total_searches=6,
        similarity_threshold=0.7,
    )

    await session.emit({
        "type": "search_requests_collected",
        "total_requests": sum(len(o.search_requests) for o in phase1_outputs),
        "unique_queries": len(dedup_searches),
        "queries": [s.query for s in dedup_searches],
    })

    # Execute searches
    if dedup_searches:
        search_results = await execute_searches_centralized(dedup_searches)
        session.search_results = {q: r.results if r.success else [] for q, r in search_results.items()}

        specialist_results = assign_results_to_specialists(
            search_results,
            phase1_outputs,
            original_to_canonical,
        )

        await session.emit({
            "type": "search_phase_complete",
            "total_results": sum(len(r.results) for r in search_results.values() if r.success),
        })
    else:
        specialist_results = {}
        await session.emit({
            "type": "search_phase_complete",
            "total_results": 0,
        })

    # =========================================================================
    # PHASE 2: Generate debate arguments with search results
    # =========================================================================
    await session.emit({
        "type": "proposal_phase_start",
        "specialist_count": 2,
    })

    async def run_phase2(i: int, role: str) -> str:
        phase1_output = phase1_outputs[i]

        await session.emit({
            "type": "proposal_start",
            "index": i,
            "role": role,
        })

        results_for_specialist = specialist_results.get(role, [])
        formatted_results = format_search_results_for_specialist(results_for_specialist)

        response = await generate_phase2_proposal(
            task=f"Argue the {role.upper()} position for: {task}",
            specialist_id=role,
            kb_context=state.get("kb_context", ""),
            search_results_formatted=formatted_results,
            phase1_assessment=phase1_output.initial_assessment,
            conversation_history=state.get("conversation_history", []),
            temperature=0.7,
        )

        await session.emit({
            "type": "proposal_complete",
            "index": i,
            "role": role,
            "text": response,
        })

        session.proposals.append({
            "role": role,
            "text": response,
        })

        return response

    props = await asyncio.gather(*[run_phase2(i, r) for i, r in enumerate(roles)])

    return {
        **state,
        "proposals": list(props),
        "phase1_outputs": session.phase1_outputs,
        "search_results": session.search_results,
    }


# =============================================================================
# Streaming API Endpoints
# =============================================================================

class StreamRunReq(BaseModel):
    """Request to start a streaming collective run."""
    model_config = ConfigDict(populate_by_name=True)

    task: str = Field(..., description="Natural language task")
    pattern: Literal["pipeline", "council", "debate"] = "council"
    k: int = Field(3, ge=2, le=7, description="Council size (fallback if no specialists selected)")
    user_id: Optional[str] = Field(default=None, alias="userId")
    enable_search_phase: bool = Field(
        default=False,
        alias="enableSearchPhase",
        description="Enable two-phase proposal with web search access for specialists",
    )
    selected_specialists: Optional[List[str]] = Field(
        default=None,
        alias="selectedSpecialists",
        description="List of specialist IDs to use (e.g., ['local_q4', 'openai_gpt4o_mini']). "
                    "If provided, overrides 'k' parameter.",
    )


class StreamRunRes(BaseModel):
    """Response with session ID for streaming."""
    session_id: str
    status: str
    message: str


@router.post("/stream/start", response_model=StreamRunRes)
async def start_streaming_collective(req: StreamRunReq):
    """Start a collective run with streaming support.

    Creates a session that can be monitored via WebSocket.

    Example with k (legacy):
        POST /api/collective/stream/start
        {
            "task": "Compare PETG vs ABS for outdoor use",
            "pattern": "council",
            "k": 3
        }

    Example with selected specialists:
        POST /api/collective/stream/start
        {
            "task": "Compare PETG vs ABS for outdoor use",
            "pattern": "council",
            "selectedSpecialists": ["local_q4", "local_coder", "openai_gpt4o_mini"]
        }

    Returns:
        session_id to connect via WebSocket
    """
    # Validate selected specialists if provided
    if req.selected_specialists:
        specialists = get_specialists_by_ids(req.selected_specialists)
        if len(specialists) != len(req.selected_specialists):
            found_ids = {s.id for s in specialists}
            missing = [sid for sid in req.selected_specialists if sid not in found_ids]
            raise HTTPException(
                status_code=400,
                detail=f"Unknown specialist IDs: {missing}"
            )

        # Check availability
        unavailable = [s.id for s in specialists if not s.is_available]
        if unavailable:
            raise HTTPException(
                status_code=400,
                detail=f"Specialists not available (missing API keys): {unavailable}"
            )

        # Check minimum count
        if len(specialists) < 2:
            raise HTTPException(
                status_code=400,
                detail="Minimum 2 specialists required"
            )
        if len(specialists) > 7:
            raise HTTPException(
                status_code=400,
                detail="Maximum 7 specialists allowed"
            )

    session = await get_or_create_session(
        task=req.task,
        pattern=req.pattern,
        k=req.k,
        user_id=req.user_id,
        enable_search_phase=req.enable_search_phase,
        selected_specialists=req.selected_specialists,
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

    Returns recent sessions from database, merged with active in-memory sessions.
    """
    # Get sessions from database
    db_sessions = await _load_sessions_from_db(
        user_id=user_id,
        status=status,
        limit=limit,
    )

    # Get active in-memory sessions (may be more current than DB)
    async with _sessions_lock:
        active_sessions = list(_sessions.values())

    # Filter in-memory sessions
    if user_id:
        active_sessions = [s for s in active_sessions if s.user_id == user_id]
    if status:
        active_sessions = [s for s in active_sessions if s.status == status]

    # Convert active sessions to dict format
    active_session_dicts = [
        {
            "session_id": s.session_id,
            "task": s.task,
            "pattern": s.pattern,
            "k": s.k,
            "status": s.status,
            "created_at": s.created_at.isoformat(),
            "proposals_count": len(s.proposals),
            "has_verdict": s.verdict is not None,
            "user_id": s.user_id,
        }
        for s in active_sessions
    ]

    # Merge: prefer in-memory sessions (more current) over DB sessions
    active_ids = {s["session_id"] for s in active_session_dicts}
    merged = active_session_dicts + [s for s in db_sessions if s["session_id"] not in active_ids]

    # Sort by created_at descending
    merged.sort(key=lambda s: s.get("created_at", ""), reverse=True)

    # Limit
    merged = merged[:limit]

    return {
        "sessions": merged,
        "total": len(merged),
    }


@router.get("/sessions/{session_id}")
async def get_collective_session(session_id: str):
    """Get details for a specific collective session.

    Checks in-memory first (for active sessions), then falls back to database.
    """
    # Check in-memory first
    session = await get_session(session_id)
    if session:
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

    # Fall back to database
    db_session = await _load_session_details_from_db(session_id)
    if db_session:
        return db_session

    raise HTTPException(status_code=404, detail="Session not found")


@router.delete("/sessions/{session_id}")
async def delete_collective_session(session_id: str):
    """Delete a collective session from history.

    Removes the session from both in-memory storage and database.
    """
    # Remove from in-memory storage
    async with _sessions_lock:
        if session_id in _sessions:
            del _sessions[session_id]
            logger.info(f"Removed session {session_id} from in-memory storage")

    # Delete from database
    deleted = await _delete_session_from_db(session_id)

    if deleted:
        return {"status": "deleted", "session_id": session_id}

    # Check if it was only in memory (already removed above)
    raise HTTPException(status_code=404, detail="Session not found")
