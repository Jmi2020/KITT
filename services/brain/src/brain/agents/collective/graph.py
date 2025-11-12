
from __future__ import annotations
from typing import TypedDict, List
import os
from langgraph.graph import StateGraph, END

# Import from brain's llm_client adapter
from brain.llm_client import chat
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
    """Council node - generates K independent specialist proposals.

    Confidentiality: Proposers receive filtered context (excludes meta/dev/collective)
    to maintain independence and prevent groupthink.
    """
    k = int(s.get("k", 3))
    # Fetch filtered context for proposers (excludes meta/dev tags)
    context = fetch_domain_context(s["task"], limit=6, for_proposer=True)

    props = []
    for i in range(k):
        role = f"specialist_{i+1}"
        system_prompt = f"You are {role}. {HINT_PROPOSER}"
        user_prompt = f"Task:\n{s['task']}\n\nRelevant context:\n{context}\n\nProvide a concise proposal with justification."

        props.append(chat([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ], which="Q4"))
    return {**s, "proposals": props}

def n_propose_debate(s: CollectiveState) -> CollectiveState:
    """Debate node - generates PRO and CON arguments.

    Confidentiality: Both debaters receive filtered context (excludes meta/dev/collective)
    to maintain independence and prevent anchoring.
    """
    # Fetch filtered context for debaters (excludes meta/dev tags)
    context = fetch_domain_context(s["task"], limit=6, for_proposer=True)

    pro = chat([
        {"role": "system", "content": f"You are PRO. {HINT_PROPOSER} Argue FOR the proposal in 6 concise bullet points."},
        {"role": "user", "content": f"Task:\n{s['task']}\n\nRelevant context:\n{context}\n\nProvide PRO arguments."}
    ], which="Q4")

    con = chat([
        {"role": "system", "content": f"You are CON. {HINT_PROPOSER} Argue AGAINST the proposal in 6 concise bullet points."},
        {"role": "user", "content": f"Task:\n{s['task']}\n\nRelevant context:\n{context}\n\nProvide CON arguments."}
    ], which="Q4")

    return {**s, "proposals": [pro, con]}

def n_judge(s: CollectiveState) -> CollectiveState:
    """Judge node - synthesizes proposals into final verdict.

    Confidentiality: Judge receives FULL context (no tag filtering) to make
    informed decisions considering both domain knowledge and process context.
    """
    # Fetch full context for judge (no tag filtering)
    full_context = fetch_domain_context(s["task"], limit=10, for_proposer=False)

    proposals_text = "\n\n---\n\n".join(s.get("proposals", []))
    user_prompt = f"Task:\n{s['task']}\n\nRelevant context (full access):\n{full_context}\n\nProposals:\n\n{proposals_text}\n\nProvide: final decision, rationale, and next step."

    verdict = chat([
        {"role": "system", "content": f"{HINT_JUDGE} You may consider all available context including process and meta information."},
        {"role": "user", "content": user_prompt}
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
    return g.compile()
