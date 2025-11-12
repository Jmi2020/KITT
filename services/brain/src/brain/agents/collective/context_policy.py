"""Context policy for collective meta-agent - implements proposer blinding."""

from __future__ import annotations

import os
from typing import Optional

import httpx


# Configuration from environment
BLIND_PROPOSERS = os.getenv("COLLECTIVE_PROPOSER_BLIND", "1") == "1"
EXCLUDE_TAGS = os.getenv("MEMORY_EXCLUDE_TAGS", "meta,dev,collective")
INCLUDE_TAGS = os.getenv("MEMORY_INCLUDE_TAGS", "domain,procedure,safety")


def fetch_domain_context(query: str, limit: int = 6, for_proposer: bool = True) -> str:
    """Fetch relevant context from memory, optionally filtered for proposer blinding.

    Args:
        query: The search query
        limit: Maximum number of memories to retrieve
        for_proposer: If True and BLIND_PROPOSERS=1, excludes meta/dev/collective tags

    Returns:
        Formatted context string from relevant memories
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

        # Format memories into context
        memories = data.get("memories", [])
        if not memories:
            return "(No relevant context found)"

        context_lines = []
        for mem in memories:
            content = mem.get("content", "")
            score = mem.get("score", 0.0)
            context_lines.append(f"[Score: {score:.2f}] {content}")

        return "\n\n".join(context_lines)

    except Exception as e:
        # Graceful degradation - continue without context
        return f"(Context retrieval unavailable: {str(e)})"
