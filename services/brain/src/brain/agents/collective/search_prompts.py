"""Prompts for two-phase collective search integration.

Phase 1: Lightweight prompts for identifying search needs
Phase 2: Integration of search results into full proposals
"""

from __future__ import annotations

from typing import List

from .schemas import SearchResult


def build_phase1_system_prompt(specialist_id: str) -> str:
    """Build the system prompt for Phase 1 search request generation.

    This is a lightweight prompt focused on identifying what searches
    would help the specialist provide a better proposal.
    """
    return f"""You are {specialist_id}, an expert specialist analyzing a task.

## Your Goal (Phase 1)
Identify what web searches would help you provide a better, more informed proposal.

## Instructions
1. Read the task and available knowledge base context
2. Identify gaps in your knowledge that web search could fill
3. Output a JSON object with:
   - search_requests: List of searches you need (max 3)
   - initial_assessment: Brief analysis of the task (2-3 sentences)
   - confidence_without_search: Your confidence (0.0-1.0) in answering well without search

## Search Request Guidelines
- Only request searches if genuinely needed (not for basic knowledge)
- Be specific with queries - include relevant keywords
- Prioritize: 1=critical, 2=helpful, 3=nice-to-have
- Focus on recent information, specific data, or verification needs

## Output Format (JSON only)
{{
  "search_requests": [
    {{"query": "specific search query", "purpose": "why needed", "priority": 1}}
  ],
  "initial_assessment": "Brief analysis of the task...",
  "confidence_without_search": 0.7
}}

IMPORTANT: Output ONLY valid JSON. No markdown, no explanation, just the JSON object."""


def build_phase1_user_prompt(
    task: str,
    kb_context: str,
    conversation_summary: str = "",
) -> str:
    """Build the user prompt for Phase 1."""
    parts = []

    if conversation_summary:
        parts.append(f"## Conversation Context\n{conversation_summary}")

    parts.append(f"## Task\n{task}")

    if kb_context:
        parts.append(f"## Available Knowledge Base Context\n{kb_context}")

    parts.append(
        "\n## Your Response\n"
        "Analyze the task and output your JSON response with search requests."
    )

    return "\n\n".join(parts)


def format_search_results_for_specialist(
    results: List[SearchResult],
    max_results_per_query: int = 5,
    max_snippet_length: int = 500,
) -> str:
    """Format search results for injection into Phase 2 prompt.

    Args:
        results: List of SearchResult for this specialist
        max_results_per_query: Max results to include per query
        max_snippet_length: Max characters for content snippets

    Returns:
        Formatted string for Phase 2 prompt
    """
    if not results:
        return ""

    # Check if any searches succeeded
    successful = [r for r in results if r.success and r.results]
    if not successful:
        return "## Web Search Results\n_No search results available._"

    sections = ["## Web Search Results (from your Phase 1 requests)"]

    for result in results:
        sections.append(f"\n### Query: \"{result.query}\"")

        if not result.success:
            sections.append(f"_Search failed: {result.error or 'Unknown error'}_")
            continue

        if not result.results:
            sections.append("_No results found._")
            continue

        # Format top results
        for i, item in enumerate(result.results[:max_results_per_query]):
            title = item.get("title", "Untitled")
            url = item.get("url", "")
            snippet = item.get("content_snippet") or item.get("snippet") or item.get("description", "")

            # Truncate snippet
            if len(snippet) > max_snippet_length:
                snippet = snippet[:max_snippet_length].rsplit(" ", 1)[0] + "..."

            sections.append(f"\n**{i + 1}. {title}**")
            if url:
                sections.append(f"   URL: {url}")
            if snippet:
                sections.append(f"   > {snippet}")

    sections.append(
        "\n_Use these search results to inform your proposal. "
        "Cite sources when referencing specific information._"
    )

    return "\n".join(sections)


def build_phase2_system_prompt(
    specialist_id: str,
    has_search_results: bool,
) -> str:
    """Build system prompt for Phase 2 full proposal generation.

    This extends the standard specialist prompt with search result integration.
    """
    search_section = ""
    if has_search_results:
        search_section = """
## Using Search Results
- Search results from your Phase 1 requests are provided below
- Reference specific sources when using information from search
- Combine search findings with KB context for comprehensive analysis
- Note if search results conflict with KB or your prior knowledge
"""

    return f"""You are {specialist_id}, an expert specialist providing independent analysis.

## Your Role
Provide a detailed, well-justified proposal based on the task, knowledge base context,
{"and web search results" if has_search_results else "and your expertise"}.

## Core Constraints (CRITICAL)
- **NEVER** fabricate information, citations, or KB chunk IDs
- **ALWAYS** cite KB chunk IDs (e.g., [KB#123]) when referencing knowledge base content
- **ALWAYS** distinguish between: knowledge from KB context vs. web search vs. your training
- If uncertain about a fact, clearly state "I'm not certain" rather than guessing
{search_section}
## Response Structure
1. **Analysis**: Break down the core question or problem
2. **Evidence**: What do KB context and search results tell us?
3. **Recommendation**: Your expert proposal with clear reasoning
4. **Confidence Level**: High/Medium/Low with justification
5. **Caveats**: Any limitations or assumptions in your analysis

## Response Guidelines
- Be thorough but concise
- Support claims with specific KB references [KB#id] and search citations
- Provide actionable recommendations where applicable
- End with any important caveats or limitations"""


def build_phase2_user_prompt(
    task: str,
    kb_context: str,
    search_results_formatted: str,
    phase1_assessment: str,
    conversation_summary: str = "",
) -> str:
    """Build user prompt for Phase 2 full proposal generation."""
    parts = []

    if conversation_summary:
        parts.append(f"## Conversation Context\n{conversation_summary}")

    parts.append(f"## Task\n{task}")

    if phase1_assessment:
        parts.append(f"## Your Initial Assessment (Phase 1)\n{phase1_assessment}")

    if kb_context:
        parts.append(f"## Knowledge Base Context\n{kb_context}")

    if search_results_formatted:
        parts.append(search_results_formatted)

    parts.append(
        "\n## Your Proposal\n"
        "Provide your expert analysis and recommendation. "
        "Reference KB chunks using [KB#id] and cite search sources when applicable."
    )

    return "\n\n".join(parts)
