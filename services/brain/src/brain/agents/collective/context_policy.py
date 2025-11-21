"""Context policy for collective meta-agent - implements proposer blinding."""

from __future__ import annotations

import os
from typing import Optional

import httpx

# Import token budget manager for auto-trimming
from brain.token_budgets import TokenBudgetManager


# Configuration from environment
BLIND_PROPOSERS = os.getenv("COLLECTIVE_PROPOSER_BLIND", "1") == "1"
EXCLUDE_TAGS = os.getenv("MEMORY_EXCLUDE_TAGS", "meta,dev,collective")
INCLUDE_TAGS = os.getenv("MEMORY_INCLUDE_TAGS", "domain,procedure,safety")


def fetch_domain_context(
    query: str,
    limit: int = 6,
    for_proposer: bool = True,
    token_budget: Optional[int] = None
) -> str:
    """Fetch relevant context from memory, optionally filtered for proposer blinding.

    Now budget-aware with KB chunk ID tagging for structured evidence flow.

    Args:
        query: The search query
        limit: Maximum number of memories to retrieve
        for_proposer: If True and BLIND_PROPOSERS=1, excludes meta/dev/collective tags
        token_budget: Optional token budget for auto-trimming (None = no limit)

    Returns:
        Formatted context string from relevant memories with KB chunk IDs
    """
    # Determine tag filters based on role
    exclude_tags = None
    include_tags = None

    if for_proposer and BLIND_PROPOSERS:
        # Blind proposers to meta/dev context
        exclude_tags = [tag.strip() for tag in EXCLUDE_TAGS.split(",") if tag.strip()]
        include_tags = [tag.strip() for tag in INCLUDE_TAGS.split(",") if tag.strip()]

    # Build search request
    search_request = {
        "query": query,
        "limit": limit,
        "score_threshold": 0.6,  # Lower threshold for better recall
    }

    if exclude_tags:
        search_request["exclude_tags"] = exclude_tags
    if include_tags:
        search_request["include_tags"] = include_tags

    try:
        # Call Memory MCP service (running on localhost for brain service)
        # In production, use http://mem0-mcp:8765 from Docker network
        base_url = os.getenv("MEM0_MCP_URL", "http://localhost:8765")
        response = httpx.post(
            f"{base_url}/memory/search",
            json=search_request,
            timeout=30
        )
        response.raise_for_status()
        data = response.json()

        # Format memories into context with KB chunk IDs
        memories = data.get("memories", [])
        if not memories:
            return "(No relevant context found)"

        context_lines = []
        for idx, mem in enumerate(memories):
            content = mem.get("content", "")
            score = mem.get("score", 0.0)
            mem_id = mem.get("id", f"mem_{idx}")

            # Format with KB chunk ID for traceability
            # Format: [KB#id] [Score: X.XX] content
            chunk_line = f"[KB#{mem_id}] [Score: {score:.2f}] {content}"
            context_lines.append(chunk_line)

        full_context = "\n\n".join(context_lines)

        # Apply token budget if specified
        if token_budget:
            current_tokens = TokenBudgetManager.estimate_tokens(full_context)
            if current_tokens > token_budget:
                # Trim by removing lowest-scoring chunks first
                # Sort by score (highest first) and trim to budget
                scored_chunks = [
                    (mem.get("score", 0.0), context_lines[i])
                    for i, mem in enumerate(memories)
                ]
                scored_chunks.sort(reverse=True, key=lambda x: x[0])

                trimmed_lines = []
                accumulated_tokens = 0
                for score, chunk in scored_chunks:
                    chunk_tokens = TokenBudgetManager.estimate_tokens(chunk)
                    if accumulated_tokens + chunk_tokens <= token_budget:
                        trimmed_lines.append(chunk)
                        accumulated_tokens += chunk_tokens
                    else:
                        # Stop adding chunks
                        break

                # Sort trimmed lines back by original order (highest scores still first)
                full_context = "\n\n".join(trimmed_lines)

                # Add budget notice
                full_context = (
                    f"[Context trimmed to {accumulated_tokens}/{token_budget} tokens, "
                    f"showing {len(trimmed_lines)}/{len(memories)} chunks]\n\n"
                    + full_context
                )

        return full_context

    except Exception as e:
        # Graceful degradation - continue without context
        return f"(Context retrieval unavailable: {str(e)})"
