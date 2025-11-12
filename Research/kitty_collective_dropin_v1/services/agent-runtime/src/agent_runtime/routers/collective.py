
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Literal, Optional, List, Dict, Any
from ..collective.graph import build_collective_graph
from ..llm_client import chat

# Optional: reuse coding graph for 'pipeline' pattern if available
try:
    from ..graphs.graph_coding import build_coding_graph  # previously implemented
    _HAS_CODING = True
except Exception:
    _HAS_CODING = False

router = APIRouter(prefix="/api/collective", tags=["collective"])
_graph = build_collective_graph()

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
def run_collective(req: RunReq):
    proposals: List[Proposal] = []
    logs: List[str] = []

    # If pipeline and coding graph exists, run it and collect as single proposal
    if req.pattern == "pipeline" and _HAS_CODING:
        cgraph = build_coding_graph()
        st = {"user_request": req.task}
        out = cgraph.invoke(st)
        final_md = out.get("final_answer") or out.get("result") or ""
        proposals.append(Proposal(role="pipeline", text=final_md))
        logs.append("[pipeline] executed coding graph")
        # build a minimal state to drive collective judge
        state = {"task": req.task, "pattern": "pipeline", "proposals": [final_md]}
        result = _graph.invoke(state)
        return RunRes(
            pattern="pipeline",
            proposals=proposals,
            verdict=result.get("verdict",""),
            logs="\n".join(logs),
            aux={
                "passed": out.get("passed"),
                "stdout": out.get("run_stdout"),
                "stderr": out.get("run_stderr"),
            }
        )

    # else use council/debate (or pipeline fallback without coding graph)
    state = {"task": req.task, "pattern": req.pattern, "k": req.k}
    result = _graph.invoke(state)
    props = result.get("proposals", [])
    for i, p in enumerate(props):
        role = "pro" if (req.pattern=="debate" and i==0) else ("con" if (req.pattern=="debate" and i==1) else f"specialist_{i+1}")
        proposals.append(Proposal(role=role, text=p))

    return RunRes(
        pattern=req.pattern,
        proposals=proposals,
        verdict=result.get("verdict",""),
        logs=result.get("logs",""),
        aux={}
    )
