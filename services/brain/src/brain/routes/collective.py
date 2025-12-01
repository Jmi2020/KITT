
from __future__ import annotations
import logging
import os
import time
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, HTTPException
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
