
from __future__ import annotations
from typing import TypedDict, List
import os
from langgraph.graph import StateGraph, END

# Import async chat interface
from brain.llm_client import chat_async
from .context_policy import fetch_domain_context

# Prompts from environment
HINT_PROPOSER = os.getenv("COLLECTIVE_HINT_PROPOSER",
                          "Solve independently; do not reference other agents or a group.")
HINT_JUDGE = os.getenv("COLLECTIVE_HINT_JUDGE",
                       "You are the judge; prefer safety, clarity, testability.")

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

    Confidentiality: Proposers receive filtered context (excludes meta/dev/collective)
    to maintain independence and prevent groupthink.
    """
    import asyncio

    k = int(s.get("k", 3))

    # Fetch filtered context for proposers (excludes meta/dev tags)
    context = fetch_domain_context(s["task"], limit=6, for_proposer=True)

    # Generate all proposals concurrently
    async def generate_proposal(i: int) -> str:
        role = f"specialist_{i+1}"
        system_prompt = f"You are {role}. {HINT_PROPOSER}"
        user_prompt = f"Task:\n{s['task']}\n\nRelevant context:\n{context}\n\nProvide a concise proposal with justification."

        return await chat_async([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ], which="Q4")

    # Run all proposals in parallel
    props = await asyncio.gather(*[generate_proposal(i) for i in range(k)])

    return {**s, "proposals": list(props)}

async def n_propose_debate(s: CollectiveState) -> CollectiveState:
    """Debate node - generates PRO and CON arguments using Q4.

    Performance: Both PRO and CON generated concurrently for 2x speedup.

    Confidentiality: Both debaters receive filtered context (excludes meta/dev/collective)
    to maintain independence and prevent anchoring.
    """
    import asyncio

    # Fetch filtered context for debaters (excludes meta/dev tags)
    context = fetch_domain_context(s["task"], limit=6, for_proposer=True)

    # Generate PRO and CON concurrently
    pro_task = chat_async([
        {"role": "system", "content": f"You are PRO. {HINT_PROPOSER} Argue FOR the proposal in 6 concise bullet points."},
        {"role": "user", "content": f"Task:\n{s['task']}\n\nRelevant context:\n{context}\n\nProvide PRO arguments."}
    ], which="Q4")

    con_task = chat_async([
        {"role": "system", "content": f"You are CON. {HINT_PROPOSER} Argue AGAINST the proposal in 6 concise bullet points."},
        {"role": "user", "content": f"Task:\n{s['task']}\n\nRelevant context:\n{context}\n\nProvide CON arguments."}
    ], which="Q4")

    pro, con = await asyncio.gather(pro_task, con_task)

    return {**s, "proposals": [pro, con]}

async def n_judge(s: CollectiveState) -> CollectiveState:
    """Judge node - uses F16 to synthesize proposals into final verdict.

    Confidentiality: Judge receives FULL context (no tag filtering) to make
    informed decisions considering both domain knowledge and process context.
    """
    # Fetch full context for judge (no tag filtering)
    full_context = fetch_domain_context(s["task"], limit=10, for_proposer=False)

    proposals_text = "\n\n---\n\n".join(s.get("proposals", []))
    user_prompt = f"Task:\n{s['task']}\n\nRelevant context (full access):\n{full_context}\n\nProposals:\n\n{proposals_text}\n\nProvide: final decision, rationale, and next step."

    verdict = await chat_async([
        {"role": "system", "content": f"{HINT_JUDGE} You may consider all available context including process and meta information."},
        {"role": "user", "content": user_prompt}
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
