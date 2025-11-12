
from __future__ import annotations
from typing import TypedDict, List
from langgraph.graph import StateGraph, END

# Import async chat interface
from brain.llm_client import chat_async

class CollectiveState(TypedDict, total=False):
    task: str
    pattern: str           # pipeline|council|debate
    k: int                 # number of council members
    proposals: List[str]
    verdict: str
    logs: str

async def n_plan(s: CollectiveState) -> CollectiveState:
    """Plan node - uses Q4 to create high-level plan."""
    plan = await chat_async([
        {"role":"system","content":"You are KITTY's meta-orchestrator. Plan agent roles for the task briefly."},
        {"role":"user","content":f"Task: {s['task']} | Pattern: {s.get('pattern','pipeline')} | k={s.get('k',3)}"}
    ], which="Q4")
    return {**s, "logs": (s.get("logs","") + "\n[plan]\n" + plan)}

async def n_propose_pipeline(s: CollectiveState) -> CollectiveState:
    """Pipeline node - defer to coding graph externally."""
    # This node just marks the step; actual pipeline execution happens in router
    return {**s, "proposals": s.get("proposals", []) + ["<pipeline result inserted by router>"]}

async def n_propose_council(s: CollectiveState) -> CollectiveState:
    """Council node - generates K independent specialist proposals using Q4.

    Performance: With async, all K proposals can be generated concurrently
    for ~K speedup vs sequential execution.
    """
    import asyncio

    k = int(s.get("k", 3))

    # Generate all proposals concurrently
    async def generate_proposal(i: int) -> str:
        role = f"specialist_{i+1}"
        return await chat_async([
            {"role":"system","content":f"You are {role}. Provide an independent, concise proposal with justification."},
            {"role":"user","content":s["task"]}
        ], which="Q4")

    # Run all proposals in parallel
    props = await asyncio.gather(*[generate_proposal(i) for i in range(k)])

    return {**s, "proposals": list(props)}

async def n_propose_debate(s: CollectiveState) -> CollectiveState:
    """Debate node - generates PRO and CON arguments using Q4.

    Performance: Both PRO and CON generated concurrently for 2x speedup.
    """
    import asyncio

    # Generate PRO and CON concurrently
    pro_task = chat_async([
        {"role":"system","content":"You are PRO. Argue FOR the proposal in 6 concise bullet points."},
        {"role":"user","content":s["task"]}
    ], which="Q4")

    con_task = chat_async([
        {"role":"system","content":"You are CON. Argue AGAINST the proposal in 6 concise bullet points."},
        {"role":"user","content":s["task"]}
    ], which="Q4")

    pro, con = await asyncio.gather(pro_task, con_task)

    return {**s, "proposals": [pro, con]}

async def n_judge(s: CollectiveState) -> CollectiveState:
    """Judge node - uses F16 to synthesize proposals into final verdict."""
    verdict = await chat_async([
        {"role":"system","content":"You are the JUDGE. Prefer safety, clarity, and testability."},
        {"role":"user","content":f"Given proposals below, produce a final decision + rationale + next step.\n\n{chr(10).join(s.get('proposals',[]))}"}
    ], which="F16")
    return {**s, "verdict": verdict}

def build_collective_graph_async() -> StateGraph:
    """Build async collective meta-agent LangGraph.

    This version uses async nodes with chat_async() for better performance:
    - Council proposals generated in parallel (K concurrent Q4 calls)
    - Debate PRO/CON generated in parallel (2 concurrent Q4 calls)
    - No ThreadPoolExecutor overhead
    - Clean async/await semantics

    Performance improvement over sync version:
    - Council k=3: ~50% faster (3 sequential → 3 parallel)
    - Debate: ~30% faster (2 sequential → 2 parallel)
    """
    g = StateGraph(CollectiveState)

    # Add all nodes (async)
    g.add_node("plan", n_plan)
    g.set_entry_point("plan")

    g.add_node("propose_pipeline", n_propose_pipeline)
    g.add_node("propose_council", n_propose_council)
    g.add_node("propose_debate", n_propose_debate)
    g.add_node("judge", n_judge)

    # Routing logic (same as sync version)
    def route(s: CollectiveState):
        pattern = (s.get("pattern","pipeline") or "pipeline").lower()
        if pattern not in ("pipeline","council","debate"):
            pattern = "pipeline"
        return {
            "pipeline":"propose_pipeline",
            "council":"propose_council",
            "debate":"propose_debate"
        }[pattern]

    # Connect nodes
    g.add_conditional_edges("plan", route, {
        "propose_pipeline":"propose_pipeline",
        "propose_council":"propose_council",
        "propose_debate":"propose_debate"
    })
    g.add_edge("propose_pipeline","judge")
    g.add_edge("propose_council","judge")
    g.add_edge("propose_debate","judge")
    g.add_edge("judge", END)

    return g.compile()
