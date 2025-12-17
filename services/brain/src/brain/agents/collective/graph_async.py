
from __future__ import annotations
from typing import TypedDict, List, Dict, Any, Optional
import os
import logging
from langgraph.graph import StateGraph, END

# Import async chat interface
from brain.llm_client import chat_async
from .context_policy import fetch_domain_context

# Import tool registry and MCP execution
from brain.routing.tool_registry import TOOL_DEFINITIONS
from brain.tools.mcp_client import MCPClient

# Import token budget system
from brain.token_budgets import TokenBudgetManager, summarize_conversation

# Import judge prompt builder
from .judge_prompts import (
    build_judge_system_prompt,
    build_judge_user_prompt,
    check_judge_prompt_budget,
    trim_proposals_to_budget,
    deduplicate_kb_references
)

logger = logging.getLogger(__name__)

# Global MCP client instance (lazy initialization)
_mcp_client: Optional[MCPClient] = None


def _get_mcp_client() -> MCPClient:
    """Get or create global MCP client instance."""
    global _mcp_client
    if _mcp_client is None:
        _mcp_client = MCPClient()
        logger.info("Initialized MCPClient for collective tool execution")
    return _mcp_client

# Prompts from environment
HINT_PROPOSER = os.getenv("COLLECTIVE_HINT_PROPOSER",
                          "Solve independently; do not reference other agents or a group.")
HINT_JUDGE = os.getenv("COLLECTIVE_HINT_JUDGE",
                       "You are the judge; prefer safety, clarity, testability.")

# Quality improvement: Hallucination prevention constraints (from unified.py)
HALLUCINATION_PREVENTION = """
## Core Constraints (CRITICAL)
- **NEVER** fabricate information, citations, or KB chunk IDs
- **ALWAYS** cite KB chunk IDs (e.g., [KB#123]) when referencing knowledge base content
- **ALWAYS** distinguish between: knowledge from KB context vs. your training data
- If uncertain about a fact → clearly state "I'm not certain" rather than guessing
- If KB context doesn't cover a topic → acknowledge "The provided context doesn't address this"
"""

# Quality improvement: Evidence requirements
EVIDENCE_REQUIREMENTS = """
## Evidence & Citation Requirements
- Support claims with specific KB references using [KB#id] format
- When making recommendations, explain the reasoning with evidence
- If multiple KB sources conflict, acknowledge the disagreement
- Prefer citing KB context over training data for domain-specific claims
"""

# Quality improvement: Decision framework for proposals
DECISION_FRAMEWORK = """
## Analysis Framework
Before providing your proposal:
1. **Identify** the core question or problem to solve
2. **Assess** relevant KB context - what does the evidence say?
3. **Evaluate** confidence: High (clear KB support), Medium (partial support), Low (limited evidence)
4. **Recommend** with appropriate confidence qualifiers
"""


async def _execute_tool_calls(tool_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Execute tool calls via MCP and return results.

    Simplified version for collective agents - no safety checks since these are
    read-only research tools (web_search mainly).

    Args:
        tool_calls: List of tool call dicts with 'function' containing 'name' and 'arguments'

    Returns:
        List of result dicts with 'tool', 'result', or 'error' keys
    """
    results = []
    mcp_client = _get_mcp_client()

    for tool_call in tool_calls:
        try:
            # Parse tool call structure (supports both llama.cpp and Ollama formats)
            if isinstance(tool_call, dict):
                if "function" in tool_call:
                    # Ollama format: {function: {name: ..., arguments: ...}}
                    func = tool_call.get("function", {})
                    tool_name = func.get("name")
                    tool_args = func.get("arguments", {})
                else:
                    # Direct format: {name: ..., arguments: ...}
                    tool_name = tool_call.get("name")
                    tool_args = tool_call.get("arguments", {})
            else:
                # Object format (hasattr)
                tool_name = getattr(tool_call, "name", None)
                tool_args = getattr(tool_call, "arguments", {}) or {}

            if not tool_name:
                results.append({"tool": "unknown", "error": "Missing tool name"})
                continue

            logger.info(f"Collective executing tool: {tool_name}")

            # Execute via MCP (returns dict with success, data, error, metadata)
            result = await mcp_client.execute_tool(tool_name, tool_args)

            # Format result for collective agents
            if result.get("success"):
                results.append({"tool": tool_name, "result": result.get("data")})
            else:
                results.append({"tool": tool_name, "error": result.get("error", "Unknown error")})

        except Exception as e:
            logger.error(f"Collective tool execution failed for {tool_name}: {e}")
            results.append({"tool": tool_name, "error": str(e)})

    return results


class CollectiveState(TypedDict, total=False):
    task: str
    pattern: str           # pipeline|council|debate
    k: int                 # number of council members
    proposals: List[str]
    verdict: str
    logs: str

async def n_plan(s: CollectiveState) -> CollectiveState:
    """Plan node - uses Q4 to create high-level plan.

    Token Budget (Option A): Planning with 32k context limit:
    - Lightweight planning (no KB context needed)
    - ~2k tokens for conversation summary
    - ~2k tokens for system + task
    - ~2k tokens for plan output
    """
    # Get conversation summary if available
    conversation_history = s.get("conversation_history", [])
    conv_summary = summarize_conversation(conversation_history, max_tokens=2000) if conversation_history else ""

    # Build system prompt
    system_prompt = (
        "You are KITTY's meta-orchestrator. Plan agent roles and workflow for the task briefly.\n"
        "Provide a concise plan outlining how specialists should approach the problem."
    )

    # Build user prompt
    user_prompt_parts = []

    if conv_summary:
        user_prompt_parts.append(f"## Conversation Context\n{conv_summary}")

    user_prompt_parts.append(
        f"## Task\n{s['task']}\n\n"
        f"Pattern: {s.get('pattern','pipeline')} | k={s.get('k',3)}\n\n"
        f"Create a brief plan outlining the deliberation strategy."
    )

    user_prompt = "\n\n".join(user_prompt_parts)

    # Simple planning call (no tools, no KB context to fit within budget)
    plan, metadata = await chat_async([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ], which="Q4", max_tokens=2000)

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

    Token Budget (Option A): Athene specialists work within 32k training context:
    - Total budget: 24k prompt + 6-8k output = 30-32k
    - KB chunks: Auto-trimmed to fit ~10k token budget
    - Conversation summary: ~2k tokens
    - System + task framing: ~6k tokens
    - Output: 6-8k tokens for detailed proposals
    """
    import asyncio

    k = int(s.get("k", 3))

    # Get conversation summary if available (for multi-turn context)
    conversation_history = s.get("conversation_history", [])
    conv_summary = summarize_conversation(conversation_history, max_tokens=2000) if conversation_history else ""

    # Fetch filtered context for proposers with token budget
    # Budget: ~10k tokens for KB chunks (auto-trimmed by fetch_domain_context)
    context = fetch_domain_context(
        s["task"],
        limit=10,  # Fetch more, let auto-trim select best chunks
        for_proposer=True,
        token_budget=10000  # Athene KB budget
    )

    # Generate all proposals concurrently
    async def generate_proposal(i: int) -> str:
        role = f"specialist_{i+1}"
        which_model = "Q4"

        # Vary temperature slightly across specialists (0.7-0.9)
        temperature = 0.7 + (i * 0.1)

        # Output budget: 6-8k tokens
        max_tokens = 6000 + (i * 500)  # Vary slightly (6k-7.5k)

        # Build system prompt with quality improvements
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

        # Build user prompt with budget-aware components
        user_prompt_parts = []

        if conv_summary:
            user_prompt_parts.append(f"## Conversation Context\n{conv_summary}")

        user_prompt_parts.append(f"## Task\n{s['task']}")
        user_prompt_parts.append(f"## Relevant Knowledge\n{context}")
        user_prompt_parts.append(
            "\n## Your Proposal\nProvide your expert analysis and recommendation. "
            "Reference KB chunks using [KB#id] when citing evidence."
        )

        user_prompt = "\n\n".join(user_prompt_parts)

        # Check budget before calling (log for debugging)
        budget_ok, allocations = TokenBudgetManager.check_athene_budget(
            system_prompt=system_prompt,
            conversation_summary=conv_summary,
            kb_chunks=context,
            task_query=s['task'],
            tools_json=None  # No tools for Athene specialists
        )

        if not budget_ok:
            logger.warning(f"Specialist {i+1} budget overflow detected")
            TokenBudgetManager.log_budget_status(allocations, f"Specialist_{i+1}")

        # Generate proposal (no tools to stay within 32k context limit)
        response, metadata = await chat_async([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ], which=which_model, temperature=temperature, max_tokens=max_tokens)

        return response

    # Run all proposals in parallel
    props = await asyncio.gather(*[generate_proposal(i) for i in range(k)])

    return {**s, "proposals": list(props)}

async def n_propose_debate(s: CollectiveState) -> CollectiveState:
    """Debate node - generates PRO and CON arguments using Q4.

    Performance: Both PRO and CON generated concurrently for 2x speedup.

    Confidentiality: Both debaters receive filtered context (excludes meta/dev/collective)
    to maintain independence and prevent anchoring.

    Token Budget (Option A): Athene debaters work within 32k training context:
    - Same budget as council specialists (24k prompt + 6-8k output)
    - KB chunks auto-trimmed to ~10k tokens
    - Conversation summary: ~2k tokens
    """
    import asyncio

    # Get conversation summary if available
    conversation_history = s.get("conversation_history", [])
    conv_summary = summarize_conversation(conversation_history, max_tokens=2000) if conversation_history else ""

    # Fetch filtered context for debaters with token budget
    context = fetch_domain_context(
        s["task"],
        limit=10,
        for_proposer=True,
        token_budget=10000
    )

    # Helper to generate debate argument with budget awareness
    async def generate_argument(stance: str, is_pro: bool) -> str:
        stance_direction = "FOR" if is_pro else "AGAINST"
        # Build system prompt with quality improvements
        system_prompt = f"""You are the {stance} debater, arguing {stance_direction} the proposal.

## Your Role
{HINT_PROPOSER}
You must argue {stance_direction} the proposal with conviction, using evidence to support your position.
{HALLUCINATION_PREVENTION}
{EVIDENCE_REQUIREMENTS}

## Argumentation Guidelines
- Present your strongest arguments first
- Support each argument with KB evidence where available [KB#id]
- Anticipate counterarguments and address them
- Be persuasive but factually accurate
- Conclude with a summary of your key points
- Include confidence level for your strongest arguments (High/Medium/Low)"""

        # Build user prompt
        user_prompt_parts = []

        if conv_summary:
            user_prompt_parts.append(f"## Conversation Context\n{conv_summary}")

        user_prompt_parts.append(f"## Task\n{s['task']}")
        user_prompt_parts.append(f"## Relevant Knowledge\n{context}")
        user_prompt_parts.append(
            f"\n## Your {'PRO' if is_pro else 'CON'} Arguments\n"
            f"Present compelling arguments {'supporting' if is_pro else 'opposing'} the proposal. "
            f"Reference KB chunks using [KB#id] when citing evidence."
        )

        user_prompt = "\n\n".join(user_prompt_parts)

        # Check budget before calling
        budget_ok, allocations = TokenBudgetManager.check_athene_budget(
            system_prompt=system_prompt,
            conversation_summary=conv_summary,
            kb_chunks=context,
            task_query=s['task'],
            tools_json=None
        )

        if not budget_ok:
            logger.warning(f"Debater {stance} budget overflow detected")
            TokenBudgetManager.log_budget_status(allocations, f"Debater_{stance}")

        # Generate argument (no tools to stay within 32k context limit)
        response, metadata = await chat_async([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ], which="Q4", max_tokens=6000)

        return response

    # Generate PRO and CON concurrently
    pro_task = generate_argument("PRO", is_pro=True)
    con_task = generate_argument("CON", is_pro=False)

    # Gather results
    results = await asyncio.gather(pro_task, con_task)
    pro = results[0]
    con = results[1]

    return {**s, "proposals": [pro, con]}

async def n_judge(s: CollectiveState) -> CollectiveState:
    """Judge node - uses F16 (GPT-OSS 120B) to synthesize proposals into final verdict.

    Confidentiality: Judge receives FULL context (no tag filtering) to make
    informed decisions considering both domain knowledge and process context.

    Token Budget (Option A): GPT-OSS 120B with 128k context:
    - Total budget: 100k prompt + 6-8k output = 106-108k
    - Full KB context: ~35k tokens (unfiltered, all tags)
    - Specialist proposals: ~25k tokens (auto-trimmed if needed)
    - Conversation summary: ~2k tokens
    - Tools: ~10k tokens
    - System + task framing: ~6k tokens
    - Margin: ~7k tokens

    Tool Access: Judge can use tools to verify claims, research additional context,
    or fact-check proposals before making final decision. GPT-OSS 120B's thinking
    mode helps with deep reasoning over tool results.

    Structured Prompts: Uses 6-section prompt format for optimal synthesis:
    1. Conversation Context
    2. Task Description
    3. Full Knowledge Base
    4. Specialist Proposals (with KB citations)
    5. Planning Context
    6. Synthesis Instructions
    """
    # Get conversation summary
    conversation_history = s.get("conversation_history", [])
    conv_summary = summarize_conversation(conversation_history, max_tokens=2000) if conversation_history else ""

    # Fetch full context for judge (no tag filtering)
    # Judge budget: ~35k tokens for KB chunks
    full_context = fetch_domain_context(
        s["task"],
        limit=20,  # Fetch many, let auto-trim select best
        for_proposer=False,  # Full access (no tag filtering)
        token_budget=35000  # Judge KB budget
    )

    # Get proposals and trim if needed
    proposals = s.get("proposals", [])
    proposals = trim_proposals_to_budget(proposals, max_tokens=25000)

    # Log KB reference deduplication
    kb_refs = deduplicate_kb_references(proposals)
    if kb_refs:
        logger.info(f"Judge analyzing {len(kb_refs)} unique KB chunks cited by specialists: {kb_refs}")

    # Build structured prompts
    pattern = s.get("pattern", "council")
    system_prompt = build_judge_system_prompt(pattern)
    user_prompt = build_judge_user_prompt(
        task=s["task"],
        conversation_summary=conv_summary,
        kb_context=full_context,
        proposals=proposals,
        plan_logs=s.get("logs")
    )

    # Convert tool registry to list format
    tools_list = list(TOOL_DEFINITIONS.values())

    # Check budget before calling
    import json
    tools_json = json.dumps(tools_list)
    budget_ok = check_judge_prompt_budget(system_prompt, user_prompt, tools_json)

    if not budget_ok:
        logger.warning("Judge prompt exceeds budget - proceeding with caution")

    # Initial call with tools (GPT-OSS 120B with thinking mode)
    verdict, metadata = await chat_async([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ], which="DEEP", tools=tools_list, max_tokens=6000)

    # If tool calls were made, execute them and get final verdict
    tool_calls = metadata.get("tool_calls", [])
    if tool_calls:
        logger.info(f"Judge (DEEP/GPT-OSS) executing {len(tool_calls)} tool calls")
        tool_results = await _execute_tool_calls(tool_calls)

        # Format results for model
        results_text = "\n".join([
            f"Tool: {r['tool']}\nResult: {r.get('result', r.get('error'))}"
            for r in tool_results
        ])

        # Get final verdict incorporating tool results
        # GPT-OSS 120B will use thinking mode to deeply reason about the evidence
        verdict, _ = await chat_async([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
            {"role": "assistant", "content": "I need to verify some claims first."},
            {"role": "user", "content": f"Verification results:\n{results_text}\n\nNow provide your final verdict considering all evidence."}
        ], which="DEEP", max_tokens=6000)

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
