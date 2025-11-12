
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Literal, Optional, List, Dict, Any
import os
import time
from prometheus_client import Counter, Histogram

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
    task: str = Field(..., description="Natural language task")
    pattern: Literal["pipeline","council","debate"] = "pipeline"
    k: int = Field(3, ge=2, le=7, description="council size")
    max_steps: int = Field(8, ge=1, le=20)

class Proposal(BaseModel):
    role: str
    text: str

class RunRes(BaseModel):
    pattern: str
    proposals: List[Proposal]
    verdict: str
    logs: Optional[str] = None
    aux: Dict[str, Any] = {}

@router.post("/run", response_model=RunRes)
async def run_collective(req: RunReq):
    """Execute collective meta-agent pattern (council, debate, or pipeline).

    Patterns:
    - council: K independent specialists propose solutions, F16 judges and synthesizes
      * With async: All K proposals generated concurrently (~K speedup)
    - debate: PRO vs CON argue, F16 judges
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
        - verdict: Final synthesized decision from F16 judge
        - logs: Execution logs
    """
    start_time = time.time()
    status = "success"

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

        props = result.get("proposals", [])

        for i, p in enumerate(props):
            role = "pro" if (req.pattern=="debate" and i==0) else ("con" if (req.pattern=="debate" and i==1) else f"specialist_{i+1}")
            proposals.append(Proposal(role=role, text=p))

        # Calculate diversity metrics
        diversity_metrics = pairwise_diversity(props)

        # Record metrics before returning
        latency = time.time() - start_time
        collective_requests.labels(pattern=req.pattern, status=status).inc()
        collective_latency.labels(pattern=req.pattern).observe(latency)
        proposal_count.labels(pattern=req.pattern).observe(len(proposals))
        verdict_length.labels(pattern=req.pattern).observe(len(result.get("verdict", "")))
        proposal_diversity.labels(pattern=req.pattern).observe(diversity_metrics["avg_diversity"])

        return RunRes(
            pattern=req.pattern,
            proposals=proposals,
            verdict=result.get("verdict",""),
            logs=result.get("logs",""),
            aux={}
        )

    except Exception as exc:
        status = "error"
        collective_requests.labels(pattern=req.pattern, status=status).inc()
        raise
