
from __future__ import annotations
from typing import TypedDict, List, Dict, Any
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
PEER_REVIEW_ENABLED = os.getenv("COLLECTIVE_ENABLE_PEER_REVIEW", "true").lower() == "true"


class Proposal(TypedDict, total=False):
    label: str
    content: str
    model: str
    role: str
    temperature: float


class PeerReview(TypedDict, total=False):
    reviewer_model: str
    critiques: str
    raw_ranking: str
    parsed_ranking: List[str]


class AggregateRank(TypedDict, total=False):
    label: str
    model: str
    average_rank: float
    rankings_count: int


class CollectiveState(TypedDict, total=False):
    task: str
    pattern: str           # pipeline|council|debate
    k: int                 # number of council members
    proposals: List[Proposal]
    peer_reviews: List[PeerReview]
    aggregate_rankings: List[AggregateRank]
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

    Diversity: First specialist uses Q4B (diversity seat - different model family)
    to reduce correlated failures and introduce varied perspectives.
    """
    k = int(s.get("k", 3))
    # Fetch filtered context for proposers (excludes meta/dev tags)
    context = fetch_domain_context(s["task"], limit=6, for_proposer=True)

    props: List[Proposal] = []
    for i in range(k):
        role = f"specialist_{i+1}"

        # Use Q4B (diversity seat) for first specialist, Q4 for others
        # This introduces model family diversity to reduce correlated failures
        which_model = "Q4B" if i == 0 else "Q4"

        # Vary temperature slightly across specialists (0.7-0.9)
        temperature = 0.7 + (i * 0.1)

        # Vary max_tokens slightly (400-600)
        max_tokens = 400 + (i * 100)

        system_prompt = f"You are {role}. {HINT_PROPOSER}"
        user_prompt = f"Task:\n{s['task']}\n\nRelevant context:\n{context}\n\nProvide a concise proposal with justification."

        content = chat([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ], which=which_model, temperature=temperature, max_tokens=max_tokens)

        label = chr(65 + i)  # A, B, C...
        props.append(
            Proposal(
                label=f"Response {label}",
                content=content,
                model=which_model,
                role=role,
                temperature=temperature,
            )
        )
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

def _parse_rankings(text: str) -> List[str]:
    """Parse 'FINAL RANKING' style lists similar to llm-council."""
    import re
    if not text:
        return []
    if "FINAL RANKING:" in text:
        parts = text.split("FINAL RANKING:")
        if len(parts) >= 2:
            section = parts[1]
            numbered = re.findall(r'\d+\.\s*Response [A-Z]', section)
            if numbered:
                return [re.search(r'Response [A-Z]', m).group() for m in numbered if re.search(r'Response [A-Z]', m)]
            fallback = re.findall(r'Response [A-Z]', section)
            if fallback:
                return fallback
    return re.findall(r'Response [A-Z]', text)

def _aggregate_rankings(reviews: List[PeerReview], proposals: List[Proposal]) -> List[AggregateRank]:
    from collections import defaultdict
    label_to_model = {p.get("label"): p.get("model", "unknown") for p in proposals}
    positions = defaultdict(list)
    for pr in reviews:
        for idx, label in enumerate(pr.get("parsed_ranking", []), start=1):
            positions[label].append(idx)
    agg: List[AggregateRank] = []
    for label, pos in positions.items():
        if pos:
            agg.append(
                AggregateRank(
                    label=label,
                    model=label_to_model.get(label, "unknown"),
                    average_rank=round(sum(pos)/len(pos), 2),
                    rankings_count=len(pos),
                )
            )
    agg.sort(key=lambda x: x["average_rank"])
    return agg

def n_peer_review(s: CollectiveState) -> CollectiveState:
    """Each specialist reviews anonymized proposals and ranks them."""
    proposals: List[Proposal] = s.get("proposals", [])
    if not proposals:
        return s

    # Build anonymized text bundle
    responses_text = "\n\n".join([f"{p['label']}:\n{p['content']}" for p in proposals])

    reviews: List[PeerReview] = []
    for p in proposals:
        reviewer_model = p.get("model", "Q4")
        prompt = (
            "You are reviewing anonymous responses to the task. "
            "For each response, briefly note strengths and weaknesses. "
            "Then provide a FINAL RANKING section (exactly this format):\n"
            "FINAL RANKING:\n1. Response X\n2. Response Y\n..."
        )
        user_prompt = (
            f"Task:\n{s['task']}\n\n"
            f"Anonymous responses:\n{responses_text}\n\n"
            f"Do not prefer your own label; labels are anonymous."
        )
        ranking_text = chat(
            [
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_prompt},
            ],
            which=reviewer_model,
            temperature=0.6,
            max_tokens=500,
        )
        parsed = _parse_rankings(ranking_text)
        reviews.append(
            PeerReview(
                reviewer_model=reviewer_model,
                critiques=ranking_text,
                raw_ranking=ranking_text,
                parsed_ranking=parsed,
            )
        )

    agg = _aggregate_rankings(reviews, proposals)
    return {**s, "peer_reviews": reviews, "aggregate_rankings": agg}

def n_judge(s: CollectiveState) -> CollectiveState:
    """Judge node - synthesizes proposals into final verdict.

    Confidentiality: Judge receives FULL context (no tag filtering) to make
    informed decisions considering both domain knowledge and process context.
    """
    # Fetch full context for judge (no tag filtering)
    full_context = fetch_domain_context(s["task"], limit=10, for_proposer=False)

    # Proposals (labeled) and peer signals
    proposals = s.get("proposals", [])
    proposals_text = "\n\n---\n\n".join(
        [f"{p.get('label')}: ({p.get('model')})\n{p.get('content')}" for p in proposals]
    )

    peer_reviews = s.get("peer_reviews", [])
    peer_text = "\n\n".join(
        [
            f"Reviewer {pr.get('reviewer_model')}:\nCritiques:\n{pr.get('critiques')}\nParsed ranking: {pr.get('parsed_ranking')}"
            for pr in peer_reviews
        ]
    )

    agg = s.get("aggregate_rankings", [])
    agg_text = "\n".join([f"{r['label']} (model {r['model']}): avg_rank={r['average_rank']}" for r in agg])

    user_prompt = (
        f"Task:\n{s['task']}\n\n"
        f"Relevant context (full access):\n{full_context}\n\n"
        f"Proposals:\n{proposals_text}\n\n"
        f"Peer reviews & rankings:\n{peer_text if peer_reviews else 'None'}\n\n"
        f"Aggregate ranking:\n{agg_text if agg else 'None'}\n\n"
        "Provide: final decision, rationale, and next step. Prefer higher-ranked proposals but resolve conflicts explicitly."
    )

    verdict = chat([
        {"role": "system", "content": f"{HINT_JUDGE} You may consider all available context including process and meta information."},
        {"role": "user", "content": user_prompt}
    ], which="DEEP")

    return {**s, "verdict": verdict}

def build_collective_graph() -> StateGraph:
    g = StateGraph(CollectiveState)
    g.add_node("plan", n_plan); g.set_entry_point("plan")
    g.add_node("propose_pipeline", n_propose_pipeline)
    g.add_node("propose_council", n_propose_council)
    g.add_node("propose_debate", n_propose_debate)
    g.add_node("peer_review", n_peer_review)
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
    if PEER_REVIEW_ENABLED:
        g.add_edge("propose_council","peer_review")
        g.add_edge("peer_review","judge")
    else:
        g.add_edge("propose_council","judge")
    g.add_edge("propose_debate","judge")
    g.add_edge("judge", END)
    return g.compile()
