
from __future__ import annotations
from typing import TypedDict, List
from langgraph.graph import StateGraph, END
from ..llm_client import chat

class CollectiveState(TypedDict, total=False):
    task: str
    pattern: str           # pipeline|council|debate
    k: int                 # number of council members
    proposals: List[str]
    verdict: str
    logs: str

def n_plan(s: CollectiveState) -> CollectiveState:
    plan = chat([
        {"role":"system","content":"You are KITTY's meta-orchestrator. Plan agent roles for the task briefly."},
        {"role":"user","content":f"Task: {s['task']} | Pattern: {s.get('pattern','pipeline')} | k={s.get('k',3)}"}
    ], which="Q4")
    return {**s, "logs": (s.get("logs","") + "\n[plan]\n" + plan)}

def n_propose_pipeline(s: CollectiveState) -> CollectiveState:
    # defer to coding graph externally; this node just marks the step.
    return {**s, "proposals": s.get("proposals", []) + ["<pipeline result inserted by router>"]}

def n_propose_council(s: CollectiveState) -> CollectiveState:
    k = int(s.get("k", 3))
    props = []
    for i in range(k):
        role = f"specialist_{i+1}"
        props.append(chat([
            {"role":"system","content":f"You are {role}. Provide an independent, concise proposal with justification."},
            {"role":"user","content":s["task"]}
        ], which="Q4"))
    return {**s, "proposals": props}

def n_propose_debate(s: CollectiveState) -> CollectiveState:
    pro = chat([
        {"role":"system","content":"You are PRO. Argue FOR the proposal in 6 concise bullet points."},
        {"role":"user","content":s["task"]}
    ], which="Q4")
    con = chat([
        {"role":"system","content":"You are CON. Argue AGAINST the proposal in 6 concise bullet points."},
        {"role":"user","content":s["task"]}
    ], which="Q4")
    return {**s, "proposals": [pro, con]}

def n_judge(s: CollectiveState) -> CollectiveState:
    verdict = chat([
        {"role":"system","content":"You are the JUDGE. Prefer safety, clarity, and testability."},
        {"role":"user","content":f"Given proposals below, produce a final decision + rationale + next step.\n\n{chr(10).join(s.get('proposals',[]))}"}
    ], which="F16")
    return {**s, "verdict": verdict}

def build_collective_graph() -> StateGraph:
    g = StateGraph(CollectiveState)
    g.add_node("plan", n_plan); g.set_entry_point("plan")
    g.add_node("propose_pipeline", n_propose_pipeline)
    g.add_node("propose_council", n_propose_council)
    g.add_node("propose_debate", n_propose_debate)
    g.add_node("judge", n_judge)

    def route(s: CollectiveState):
        pattern = (s.get("pattern","pipeline") or "pipeline").lower()
        if pattern not in ("pipeline","council","debate"):
            pattern = "pipeline"
        return {
            "pipeline":"propose_pipeline",
            "council":"propose_council",
            "debate":"propose_debate"
        }[pattern]

    g.add_conditional_edges("plan", route, {
        "propose_pipeline":"propose_pipeline",
        "propose_council":"propose_council",
        "propose_debate":"propose_debate"
    })
    g.add_edge("propose_pipeline","judge")
    g.add_edge("propose_council","judge")
    g.add_edge("propose_debate","judge")
    g.add_edge("judge", END)
    return g
