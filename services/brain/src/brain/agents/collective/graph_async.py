
from __future__ import annotations
from typing import TypedDict, List, Dict, Any, Optional, TYPE_CHECKING
import os
import logging
from langgraph.graph import StateGraph, END

# Import async chat interface
from brain.llm_client import chat_async
from .context_policy import fetch_domain_context
from .providers import SpecialistConfig, get_specialists_by_ids

if TYPE_CHECKING:
    from .providers import SpecialistConfig

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
    # Two-phase search fields
    enable_search_phase: bool
    phase1_outputs: List[Dict[str, Any]]
    search_results: Dict[str, Any]
    search_execution_time_ms: float
    conversation_history: List[Dict[str, str]]
    # Multi-provider specialist selection
    specialist_configs: List[SpecialistConfig]  # Optional: specific specialists to use

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

# =============================================================================
# Multi-Provider Proposal Generation
# =============================================================================

async def generate_proposal_for_specialist(
    specialist: SpecialistConfig,
    task: str,
    context: str,
    conv_summary: str,
    index: int,
    search_results_formatted: str = "",
    phase1_assessment: str = "",
) -> Dict[str, Any]:
    """Generate a proposal using a specific specialist (local or cloud).

    Routes to the appropriate provider based on specialist config:
    - Local: Uses `which` param to select local model (Q4, CODER, Q4B)
    - Cloud: Uses `provider` and `model` params for API routing

    Args:
        specialist: SpecialistConfig defining which provider/model to use
        task: The task to address
        context: KB context
        conv_summary: Conversation summary
        index: Specialist index (for temperature variation)
        search_results_formatted: Optional search results (two-phase mode)
        phase1_assessment: Optional phase 1 assessment (two-phase mode)

    Returns:
        Dict with proposal text, model info, and metadata
    """
    role = specialist.display_name or f"specialist_{index + 1}"

    # Vary temperature slightly across specialists (0.7-0.9)
    temperature = 0.7 + (index * 0.05)  # Smaller increments for more specialists
    temperature = min(temperature, 0.95)  # Cap at 0.95

    # Output budget varies by provider
    max_tokens = 6000 if specialist.provider == "local" else 4000  # Cloud often has stricter limits

    # Build system prompt with quality improvements
    search_section = ""
    if search_results_formatted:
        search_section = """
## Using Search Results
- Reference specific sources when citing web search findings
- Combine search results with KB context for comprehensive analysis
"""

    system_prompt = f"""You are {role}, an expert specialist providing independent analysis.

## Your Role
{HINT_PROPOSER}
{HALLUCINATION_PREVENTION}
{EVIDENCE_REQUIREMENTS}
{DECISION_FRAMEWORK}
{search_section}
## Response Guidelines
- Provide a detailed, well-justified proposal
- Structure your response with clear sections (Analysis, Recommendation, Rationale)
- Include confidence level for your recommendation (High/Medium/Low)
- End with any caveats or limitations of your analysis"""

    # Build user prompt
    user_prompt_parts = []

    if conv_summary:
        user_prompt_parts.append(f"## Conversation Context\n{conv_summary}")

    if phase1_assessment:
        user_prompt_parts.append(f"## Initial Assessment\n{phase1_assessment}")

    user_prompt_parts.append(f"## Task\n{task}")
    user_prompt_parts.append(f"## Relevant Knowledge\n{context}")

    if search_results_formatted:
        user_prompt_parts.append(search_results_formatted)

    user_prompt_parts.append(
        "\n## Your Proposal\nProvide your expert analysis and recommendation. "
        "Reference KB chunks using [KB#id] when citing evidence."
    )

    user_prompt = "\n\n".join(user_prompt_parts)

    # Route to appropriate provider
    try:
        if specialist.provider == "local":
            # Local model - use which parameter
            response, metadata = await chat_async(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                which=specialist.local_which or "Q4",
                temperature=temperature,
                max_tokens=max_tokens,
            )
        else:
            # Cloud provider - use provider and model parameters
            response, metadata = await chat_async(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                provider=specialist.provider,
                model=specialist.model,
                temperature=temperature,
                max_tokens=max_tokens,
            )

        # Estimate cost for cloud providers
        cost_usd = 0.0
        if specialist.provider != "local":
            # Rough token estimation (4 chars per token)
            prompt_tokens = (len(system_prompt) + len(user_prompt)) // 4
            completion_tokens = len(response) // 4
            cost_usd = specialist.estimate_cost(prompt_tokens, completion_tokens)

        return {
            "text": response,
            "role": role,
            "model": specialist.model,
            "provider": specialist.provider,
            "temperature": temperature,
            "specialist_id": specialist.id,
            "cost_usd": cost_usd,
            "metadata": metadata,
        }

    except Exception as e:
        logger.error(f"Proposal generation failed for {specialist.id}: {e}")
        return {
            "text": f"[Error generating proposal: {str(e)}]",
            "role": role,
            "model": specialist.model,
            "provider": specialist.provider,
            "specialist_id": specialist.id,
            "error": str(e),
        }


async def n_propose_council_multi_provider(s: CollectiveState) -> CollectiveState:
    """Council node with multi-provider support.

    Uses specialist_configs from state to generate proposals from
    mixed local and cloud providers.
    """
    import asyncio

    specialist_configs = s.get("specialist_configs", [])

    if not specialist_configs:
        # Fall back to standard council if no configs provided
        return await n_propose_council(s)

    # Get conversation summary
    conversation_history = s.get("conversation_history", [])
    conv_summary = summarize_conversation(conversation_history, max_tokens=2000) if conversation_history else ""

    # Fetch context
    context = fetch_domain_context(
        s["task"],
        limit=10,
        for_proposer=True,
        token_budget=10000
    )

    # Generate all proposals in parallel
    async def generate_for_specialist(i: int, spec: SpecialistConfig):
        return await generate_proposal_for_specialist(
            specialist=spec,
            task=s["task"],
            context=context,
            conv_summary=conv_summary,
            index=i,
        )

    proposals = await asyncio.gather(*[
        generate_for_specialist(i, spec)
        for i, spec in enumerate(specialist_configs)
    ])

    # Extract text and preserve metadata
    proposal_texts = [p["text"] for p in proposals]

    # Log provider usage
    providers_used = [f"{p['provider']}/{p['model']}" for p in proposals]
    logger.info(f"Multi-provider council generated {len(proposals)} proposals from: {providers_used}")

    return {
        **s,
        "proposals": proposal_texts,
        "proposal_metadata": proposals,  # Full metadata for streaming
    }


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


# =============================================================================
# Two-Phase Proposal Functions (with Search Access)
# =============================================================================

async def generate_phase1_search_requests(
    *,
    task: str,
    specialist_id: str,
    kb_context: str = "",
    conversation_history: List[Dict[str, Any]] | None = None,
):
    """Generate Phase 1 output with search requests for one specialist.

    This is a lightweight call focused on identifying what searches would help.

    Args:
        task: The task/question to address
        specialist_id: Identifier for this specialist (e.g., "specialist_1")
        kb_context: Knowledge base context
        conversation_history: Previous conversation messages

    Returns:
        Phase1Output with specialist_id, search_requests, initial_assessment, confidence
    """
    import json
    from .search_prompts import build_phase1_system_prompt, build_phase1_user_prompt
    from .schemas import Phase1Output, SearchRequest

    # Build conversation summary from history
    conv_summary = ""
    if conversation_history:
        recent = conversation_history[-5:]  # Last 5 messages
        conv_summary = "\n".join(
            f"{m.get('role', 'user')}: {m.get('content', '')[:200]}"
            for m in recent
        )

    system_prompt = build_phase1_system_prompt(specialist_id)
    user_prompt = build_phase1_user_prompt(
        task=task,
        kb_context=kb_context,
        conversation_summary=conv_summary,
    )

    # Phase 1 is lightweight - lower token budget, more deterministic
    response, metadata = await chat_async([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ], which="Q4", temperature=0.5, max_tokens=1500)

    # Parse JSON response
    try:
        # Clean response (handle markdown code blocks)
        cleaned = response.strip()
        if cleaned.startswith("```"):
            # Remove markdown code block
            lines = cleaned.split("\n")
            cleaned = "\n".join(lines[1:-1]) if lines[-1] == "```" else "\n".join(lines[1:])
            cleaned = cleaned.strip()

        parsed = json.loads(cleaned)

        # Convert raw search requests to SearchRequest objects
        search_requests = []
        for req in parsed.get("search_requests", [])[:3]:  # Max 3
            if isinstance(req, dict):
                search_requests.append(SearchRequest(
                    query=req.get("query", ""),
                    purpose=req.get("purpose", req.get("rationale", "")),
                    priority=req.get("priority", 2),
                ))
            elif isinstance(req, str):
                search_requests.append(SearchRequest(query=req, purpose="", priority=2))

        return Phase1Output(
            specialist_id=specialist_id,
            search_requests=search_requests,
            initial_assessment=parsed.get("initial_assessment", "")[:1000],
            confidence_without_search=float(parsed.get("confidence_without_search", 0.5)),
        )
    except json.JSONDecodeError as e:
        logger.warning(f"Phase 1 JSON parse failed for {specialist_id}: {e}")
        # Return empty search requests on parse failure
        return Phase1Output(
            specialist_id=specialist_id,
            search_requests=[],
            initial_assessment=response[:500],  # Use raw response as assessment
            confidence_without_search=0.5,
        )


async def execute_searches_centralized(
    dedup_searches: List[Any],
    max_concurrent: int = 3,
    timeout_per_search: float = 10.0,
) -> Dict[str, Any]:
    """Execute deduplicated searches via MCPClient with rate limiting.

    Args:
        dedup_searches: List of DeduplicatedSearch objects
        max_concurrent: Max concurrent search requests
        timeout_per_search: Timeout per search in seconds

    Returns:
        Dict mapping canonical query to SearchResult
    """
    import asyncio
    import time
    from .schemas import SearchResult

    mcp_client = _get_mcp_client()
    results: Dict[str, SearchResult] = {}
    semaphore = asyncio.Semaphore(max_concurrent)

    async def execute_one(search) -> tuple:
        query = search.query
        start = time.time()

        async with semaphore:
            try:
                # Execute web_search via MCP
                result = await asyncio.wait_for(
                    mcp_client.execute_tool("web_search", {"query": query}),
                    timeout=timeout_per_search,
                )

                elapsed = (time.time() - start) * 1000

                if result.get("success"):
                    data = result.get("data", {})
                    search_results = data.get("results", []) if isinstance(data, dict) else []
                    return query, SearchResult(
                        query=query,
                        success=True,
                        results=search_results,
                        execution_time_ms=elapsed,
                    )
                else:
                    return query, SearchResult(
                        query=query,
                        success=False,
                        error=result.get("error", "Unknown error"),
                        execution_time_ms=elapsed,
                    )

            except asyncio.TimeoutError:
                return query, SearchResult(
                    query=query,
                    success=False,
                    error=f"Search timed out after {timeout_per_search}s",
                    execution_time_ms=timeout_per_search * 1000,
                )
            except Exception as e:
                logger.error(f"Search execution failed for '{query}': {e}")
                return query, SearchResult(
                    query=query,
                    success=False,
                    error=str(e),
                    execution_time_ms=(time.time() - start) * 1000,
                )

    # Execute all searches (limited by semaphore)
    tasks = [execute_one(s) for s in dedup_searches]
    search_results = await asyncio.gather(*tasks)

    # Build results dict
    for query, result in search_results:
        results[query] = result

    return results


async def generate_phase2_proposal(
    *,
    task: str,
    specialist_id: str,
    kb_context: str = "",
    search_results_formatted: str = "",
    phase1_assessment: str = "",
    conversation_history: List[Dict[str, Any]] | None = None,
    temperature: float = 0.7,
) -> str:
    """Generate Phase 2 full proposal with search results.

    Args:
        task: The task/question to address
        specialist_id: Identifier for this specialist
        kb_context: Knowledge base context
        search_results_formatted: Formatted search results for this specialist
        phase1_assessment: Initial assessment from Phase 1
        conversation_history: Previous conversation messages
        temperature: Generation temperature

    Returns:
        Full proposal text
    """
    from .search_prompts import build_phase2_system_prompt, build_phase2_user_prompt

    # Build conversation summary from history
    conv_summary = ""
    if conversation_history:
        recent = conversation_history[-5:]  # Last 5 messages
        conv_summary = "\n".join(
            f"{m.get('role', 'user')}: {m.get('content', '')[:200]}"
            for m in recent
        )

    has_search_results = bool(search_results_formatted.strip())

    system_prompt = build_phase2_system_prompt(specialist_id, has_search_results)
    user_prompt = build_phase2_user_prompt(
        task=task,
        kb_context=kb_context,
        search_results_formatted=search_results_formatted,
        phase1_assessment=phase1_assessment,
        conversation_summary=conv_summary,
    )

    response, metadata = await chat_async([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ], which="Q4", temperature=temperature, max_tokens=6000)

    return response


async def n_propose_council_two_phase(s: CollectiveState) -> CollectiveState:
    """Two-phase council proposal generation with search access.

    Phase 1: All specialists identify search needs (parallel, fast)
    Central: Orchestrator executes deduplicated searches
    Phase 2: All specialists generate full proposals with results (parallel)

    This provides ~8s overhead but gives specialists access to web search.
    """
    import asyncio
    import time
    from .schemas import Phase1Output
    from .search_dedup import deduplicate_search_requests, assign_results_to_specialists, get_dedup_stats
    from .search_prompts import format_search_results_for_specialist

    k = int(s.get("k", 3))

    # Get conversation summary
    conversation_history = s.get("conversation_history", [])
    conv_summary = summarize_conversation(conversation_history, max_tokens=1500) if conversation_history else ""

    # Fetch context (trimmed for Phase 1)
    context = fetch_domain_context(
        s["task"],
        limit=8,
        for_proposer=True,
        token_budget=6000  # Smaller budget for Phase 1
    )

    # ========== PHASE 1: Collect search requests ==========
    logger.info(f"Two-phase council: Starting Phase 1 with {k} specialists")
    phase1_start = time.time()

    phase1_tasks = [
        generate_phase1_search_requests(
            task=s["task"],
            specialist_id=f"specialist_{i+1}",
            kb_context=context,
            conversation_history=conversation_history,
        )
        for i in range(k)
    ]
    phase1_outputs = await asyncio.gather(*phase1_tasks)

    phase1_time = (time.time() - phase1_start) * 1000
    logger.info(f"Phase 1 completed in {phase1_time:.0f}ms")

    # Phase1Output objects are now returned directly
    phase1_models = list(phase1_outputs)

    # ========== DEDUPLICATION ==========
    dedup_searches, original_to_canonical = deduplicate_search_requests(
        phase1_models,
        max_total_searches=9,
        max_per_specialist=3,
    )

    stats = get_dedup_stats(phase1_models, dedup_searches)
    logger.info(
        f"Search deduplication: {stats['total_requests']} requests -> "
        f"{stats['unique_queries']} unique queries"
    )

    # ========== CENTRAL FETCH ==========
    search_results = {}
    search_time = 0.0

    if dedup_searches:
        logger.info(f"Executing {len(dedup_searches)} unique searches")
        search_start = time.time()

        search_results = await execute_searches_centralized(
            dedup_searches,
            max_concurrent=3,
            timeout_per_search=10.0,
        )

        search_time = (time.time() - search_start) * 1000
        successful = sum(1 for r in search_results.values() if r.success)
        logger.info(f"Search execution: {successful}/{len(search_results)} succeeded in {search_time:.0f}ms")

    # Map results back to specialists
    specialist_results = assign_results_to_specialists(
        search_results,
        phase1_models,
        original_to_canonical,
    )

    # ========== PHASE 2: Generate full proposals ==========
    # Re-fetch context with full budget for Phase 2
    full_context = fetch_domain_context(
        s["task"],
        limit=10,
        for_proposer=True,
        token_budget=8000  # Reduced since we have search results too
    )

    logger.info(f"Two-phase council: Starting Phase 2 with {k} specialists")
    phase2_start = time.time()

    phase2_tasks = []
    for i in range(k):
        specialist_id = f"specialist_{i + 1}"
        results_for_specialist = specialist_results.get(specialist_id, [])
        formatted_results = format_search_results_for_specialist(results_for_specialist)
        phase1_assessment = phase1_models[i].initial_assessment

        phase2_tasks.append(
            generate_phase2_proposal(
                task=s["task"],
                specialist_id=specialist_id,
                kb_context=full_context,
                search_results_formatted=formatted_results,
                phase1_assessment=phase1_assessment,
                conversation_history=conversation_history,
                temperature=0.7 + (i * 0.1),
            )
        )

    proposals = await asyncio.gather(*phase2_tasks)

    phase2_time = (time.time() - phase2_start) * 1000
    total_time = phase1_time + search_time + phase2_time
    logger.info(
        f"Two-phase council complete: Phase1={phase1_time:.0f}ms, "
        f"Search={search_time:.0f}ms, Phase2={phase2_time:.0f}ms, "
        f"Total={total_time:.0f}ms"
    )

    return {
        **s,
        "proposals": list(proposals),
        "phase1_outputs": [p.model_dump() for p in phase1_models],
        "search_results": {q: r.__dict__ for q, r in search_results.items()},
        "search_execution_time_ms": search_time,
    }


async def n_propose_debate_two_phase(s: CollectiveState) -> CollectiveState:
    """Two-phase debate proposal generation with search access.

    Similar to council but with PRO/CON debaters instead of specialists.
    """
    import asyncio
    import time
    from .schemas import Phase1Output, SearchRequest
    from .search_dedup import deduplicate_search_requests, assign_results_to_specialists, get_dedup_stats
    from .search_prompts import format_search_results_for_specialist

    # Get conversation summary
    conversation_history = s.get("conversation_history", [])
    conv_summary = summarize_conversation(conversation_history, max_tokens=1500) if conversation_history else ""

    # Fetch context for Phase 1
    context = fetch_domain_context(
        s["task"],
        limit=8,
        for_proposer=True,
        token_budget=6000,
    )

    # ========== PHASE 1: Collect search requests from PRO and CON ==========
    logger.info("Two-phase debate: Starting Phase 1 with PRO and CON")

    async def phase1_debater(stance: str, is_pro: bool) -> Dict[str, Any]:
        """Generate Phase 1 for a debater."""
        import json
        specialist_id = f"debater_{stance}"

        system_prompt = f"""You are the {stance} debater preparing to argue {'FOR' if is_pro else 'AGAINST'} the proposal.

## Your Goal (Phase 1)
Identify what web searches would help you build a stronger {'supporting' if is_pro else 'opposing'} argument.

## Instructions
1. Consider what evidence would strengthen your {stance} position
2. Identify gaps in the knowledge base that search could fill
3. Output a JSON object with search requests

## Output Format (JSON only)
{{
  "search_requests": [
    {{"query": "specific search query", "purpose": "why needed for {stance} argument", "priority": 1}}
  ],
  "initial_assessment": "Brief analysis of your {stance} position...",
  "confidence_without_search": 0.7
}}

IMPORTANT: Output ONLY valid JSON."""

        user_prompt = f"## Task\n{s['task']}\n\n## Knowledge Base\n{context}\n\nIdentify searches for your {stance} argument."

        response, _ = await chat_async([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ], which="Q4", temperature=0.5, max_tokens=1500)

        try:
            cleaned = response.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                cleaned = "\n".join(lines[1:-1]) if lines[-1] == "```" else "\n".join(lines[1:])
            parsed = json.loads(cleaned.strip())
            return {
                "specialist_id": specialist_id,
                "search_requests": parsed.get("search_requests", []),
                "initial_assessment": parsed.get("initial_assessment", ""),
                "confidence_without_search": parsed.get("confidence_without_search", 0.5),
            }
        except json.JSONDecodeError:
            return {
                "specialist_id": specialist_id,
                "search_requests": [],
                "initial_assessment": response[:500],
                "confidence_without_search": 0.5,
            }

    phase1_start = time.time()
    phase1_results = await asyncio.gather(
        phase1_debater("PRO", True),
        phase1_debater("CON", False),
    )
    phase1_time = (time.time() - phase1_start) * 1000

    # Convert to Phase1Output models
    phase1_models = []
    for output in phase1_results:
        search_reqs = [
            SearchRequest(
                query=r.get("query", ""),
                purpose=r.get("purpose", ""),
                priority=r.get("priority", 2),
            )
            for r in output.get("search_requests", [])
            if r.get("query")
        ]
        phase1_models.append(Phase1Output(
            specialist_id=output["specialist_id"],
            search_requests=search_reqs,
            initial_assessment=output.get("initial_assessment", ""),
            confidence_without_search=output.get("confidence_without_search", 0.5),
        ))

    # ========== DEDUPLICATION ==========
    dedup_searches, original_to_canonical = deduplicate_search_requests(
        phase1_models,
        max_total_searches=6,  # Fewer for debate (only 2 debaters)
        max_per_specialist=3,
    )

    # ========== CENTRAL FETCH ==========
    search_results = {}
    search_time = 0.0

    if dedup_searches:
        logger.info(f"Executing {len(dedup_searches)} unique searches for debate")
        search_start = time.time()
        search_results = await execute_searches_centralized(dedup_searches)
        search_time = (time.time() - search_start) * 1000

    # Map results back
    specialist_results = assign_results_to_specialists(
        search_results,
        phase1_models,
        original_to_canonical,
    )

    # ========== PHASE 2: Generate full debate arguments ==========
    full_context = fetch_domain_context(s["task"], limit=10, for_proposer=True, token_budget=8000)

    async def phase2_debater(stance: str, is_pro: bool, idx: int) -> str:
        """Generate Phase 2 full argument for a debater."""
        specialist_id = f"debater_{stance}"
        results = specialist_results.get(specialist_id, [])
        formatted_results = format_search_results_for_specialist(results)
        phase1_assessment = phase1_models[idx].initial_assessment
        has_results = bool(formatted_results.strip())

        search_section = ""
        if has_results:
            search_section = """
## Using Search Results
- Reference specific sources when using search information
- Combine search findings with KB context for stronger arguments
"""

        system_prompt = f"""You are the {stance} debater arguing {'FOR' if is_pro else 'AGAINST'} the proposal.

## Your Role
Present compelling arguments {'supporting' if is_pro else 'opposing'} the proposal using all available evidence.
{HALLUCINATION_PREVENTION}
{EVIDENCE_REQUIREMENTS}
{search_section}
## Argumentation Guidelines
- Present your strongest arguments first
- Support each argument with KB evidence [KB#id] and search citations
- Anticipate counterarguments and address them
- Be persuasive but factually accurate"""

        user_parts = [f"## Task\n{s['task']}"]
        if phase1_assessment:
            user_parts.append(f"## Your Initial Assessment\n{phase1_assessment}")
        user_parts.append(f"## Knowledge Base\n{full_context}")
        if formatted_results:
            user_parts.append(formatted_results)
        user_parts.append(f"\n## Your {stance} Arguments\nPresent your {'supporting' if is_pro else 'opposing'} case.")

        response, _ = await chat_async([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "\n\n".join(user_parts)}
        ], which="Q4", max_tokens=6000)

        return response

    phase2_start = time.time()
    proposals = await asyncio.gather(
        phase2_debater("PRO", True, 0),
        phase2_debater("CON", False, 1),
    )
    phase2_time = (time.time() - phase2_start) * 1000

    total_time = phase1_time + search_time + phase2_time
    logger.info(f"Two-phase debate complete: Total={total_time:.0f}ms")

    return {
        **s,
        "proposals": list(proposals),
        "phase1_outputs": [p.model_dump() for p in phase1_models],
        "search_results": {q: r.__dict__ for q, r in search_results.items()},
        "search_execution_time_ms": search_time,
    }


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

def build_collective_graph_async(enable_two_phase: bool = False) -> StateGraph:
    """Build async collective meta-agent LangGraph.

    This version uses async nodes with chat_async() for better performance:
    - Council proposals generated in parallel (K concurrent Q4 calls)
    - Debate PRO/CON generated in parallel (2 concurrent Q4 calls)
    - No ThreadPoolExecutor overhead
    - Clean async/await semantics

    Args:
        enable_two_phase: If True, use two-phase nodes with search access.
                         If False, use standard single-phase nodes.

    Performance improvement over sync version:
    - Council k=3: ~50% faster (3 sequential → 3 parallel)
    - Debate: ~30% faster (2 sequential → 2 parallel)

    Two-phase overhead (when enabled):
    - Additional ~8s for search phase (Phase 1 + search execution)
    - Specialists gain access to web search results
    """
    g = StateGraph(CollectiveState)

    # Add all nodes (async)
    g.add_node("plan", n_plan)
    g.set_entry_point("plan")

    g.add_node("propose_pipeline", n_propose_pipeline)

    if enable_two_phase:
        # Two-phase nodes with search access
        g.add_node("propose_council", n_propose_council_two_phase)
        g.add_node("propose_debate", n_propose_debate_two_phase)
        logger.info("Collective graph built with two-phase search access enabled")
    else:
        # Standard single-phase nodes
        g.add_node("propose_council", n_propose_council)
        g.add_node("propose_debate", n_propose_debate)

    g.add_node("judge", n_judge)

    # Routing logic - can also check enable_search_phase at runtime
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
