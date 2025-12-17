"""Search query deduplication for collective two-phase proposals.

This module handles deduplicating search queries across multiple specialists
to avoid redundant searches and stay within rate limits.
"""

from __future__ import annotations

import re
from typing import Dict, List, Set, Tuple

from .schemas import DeduplicatedSearch, Phase1Output, SearchRequest, SearchResult


def normalize_query(query: str) -> str:
    """Normalize a query for comparison.

    - Lowercase
    - Remove extra whitespace
    - Remove common punctuation
    - Sort words alphabetically (for order-independent matching)
    """
    # Lowercase and strip
    normalized = query.lower().strip()

    # Remove punctuation except hyphens in compound words
    normalized = re.sub(r'[^\w\s-]', ' ', normalized)

    # Collapse multiple spaces
    normalized = re.sub(r'\s+', ' ', normalized).strip()

    return normalized


def get_word_set(query: str) -> Set[str]:
    """Extract word set from a normalized query."""
    normalized = normalize_query(query)
    return set(normalized.split())


def jaccard_similarity(q1: str, q2: str) -> float:
    """Calculate word-level Jaccard similarity between two queries.

    Returns a value between 0.0 (no overlap) and 1.0 (identical).
    """
    words1 = get_word_set(q1)
    words2 = get_word_set(q2)

    if not words1 or not words2:
        return 0.0

    intersection = words1 & words2
    union = words1 | words2

    return len(intersection) / len(union)


def find_canonical_query(
    query: str,
    existing_canonical: Dict[str, str],
    similarity_threshold: float = 0.7,
) -> Tuple[str, bool]:
    """Find the canonical query for a given query.

    Returns:
        Tuple of (canonical_query, is_new)
        - If query matches an existing one, returns (existing_canonical, False)
        - If query is new, returns (query, True)
    """
    normalized = normalize_query(query)

    # Check exact match first
    if normalized in existing_canonical:
        return existing_canonical[normalized], False

    # Check Jaccard similarity
    for existing_norm, canonical in existing_canonical.items():
        if jaccard_similarity(normalized, existing_norm) >= similarity_threshold:
            return canonical, False

    return query, True


def deduplicate_search_requests(
    phase1_outputs: List[Phase1Output],
    max_total_searches: int = 9,
    max_per_specialist: int = 3,
    similarity_threshold: float = 0.7,
) -> Tuple[List[DeduplicatedSearch], Dict[str, str]]:
    """Deduplicate search requests across all specialists.

    Args:
        phase1_outputs: Phase 1 outputs from all specialists
        max_total_searches: Maximum total unique searches to allow
        max_per_specialist: Maximum searches per specialist (already enforced in schema)
        similarity_threshold: Jaccard similarity threshold for deduplication

    Returns:
        Tuple of:
        - List of deduplicated searches (sorted by priority)
        - Dict mapping original queries to canonical queries
    """
    # Track: normalized_query -> canonical_query
    canonical_map: Dict[str, str] = {}

    # Track: canonical_query -> DeduplicatedSearch
    dedup_searches: Dict[str, DeduplicatedSearch] = {}

    # Track: original_query -> canonical_query (for result mapping)
    original_to_canonical: Dict[str, str] = {}

    for output in phase1_outputs:
        specialist_id = output.specialist_id

        for request in output.search_requests[:max_per_specialist]:
            query = request.query.strip()
            normalized = normalize_query(query)

            # Find or create canonical query
            canonical, is_new = find_canonical_query(
                query, canonical_map, similarity_threshold
            )

            # Map for result assignment
            original_to_canonical[query] = canonical

            if is_new:
                # New unique query
                canonical_map[normalized] = canonical
                dedup_searches[canonical] = DeduplicatedSearch(
                    query=canonical,
                    normalized_query=normalized,
                    requesting_specialists=[specialist_id],
                    max_priority=request.priority,
                    purposes=[request.purpose],
                )
            else:
                # Existing query - merge metadata
                existing = dedup_searches[canonical]
                if specialist_id not in existing.requesting_specialists:
                    existing.requesting_specialists.append(specialist_id)
                existing.max_priority = min(existing.max_priority, request.priority)
                if request.purpose not in existing.purposes:
                    existing.purposes.append(request.purpose)

    # Sort by priority (lower number = higher priority)
    sorted_searches = sorted(dedup_searches.values(), key=lambda s: s.max_priority)

    # Limit total searches
    limited_searches = sorted_searches[:max_total_searches]

    return limited_searches, original_to_canonical


def assign_results_to_specialists(
    search_results: Dict[str, SearchResult],
    phase1_outputs: List[Phase1Output],
    original_to_canonical: Dict[str, str],
) -> Dict[str, List[SearchResult]]:
    """Map search results back to each specialist's original requests.

    Args:
        search_results: Dict of canonical_query -> SearchResult
        phase1_outputs: Original Phase 1 outputs
        original_to_canonical: Mapping from original queries to canonical

    Returns:
        Dict of specialist_id -> List[SearchResult]
    """
    specialist_results: Dict[str, List[SearchResult]] = {}

    for output in phase1_outputs:
        specialist_id = output.specialist_id
        results_for_specialist: List[SearchResult] = []

        for request in output.search_requests:
            original_query = request.query.strip()
            canonical_query = original_to_canonical.get(original_query)

            if canonical_query and canonical_query in search_results:
                # Create a copy with the original query for context
                result = search_results[canonical_query]
                results_for_specialist.append(SearchResult(
                    query=original_query,  # Use original query for specialist
                    success=result.success,
                    results=result.results,
                    error=result.error,
                    execution_time_ms=result.execution_time_ms,
                ))
            else:
                # No result found
                results_for_specialist.append(SearchResult(
                    query=original_query,
                    success=False,
                    error="Query not executed (outside limit or failed)",
                ))

        specialist_results[specialist_id] = results_for_specialist

    return specialist_results


def get_dedup_stats(
    phase1_outputs: List[Phase1Output],
    dedup_searches: List[DeduplicatedSearch],
) -> Dict[str, int]:
    """Get statistics about the deduplication process.

    Returns:
        Dict with keys: total_requests, unique_queries, duplicates_removed,
                       specialists_with_requests, avg_priority
    """
    total_requests = sum(len(o.search_requests) for o in phase1_outputs)
    unique_queries = len(dedup_searches)
    duplicates_removed = total_requests - unique_queries
    specialists_with_requests = sum(1 for o in phase1_outputs if o.search_requests)

    avg_priority = 0.0
    if dedup_searches:
        avg_priority = sum(s.max_priority for s in dedup_searches) / len(dedup_searches)

    return {
        "total_requests": total_requests,
        "unique_queries": unique_queries,
        "duplicates_removed": duplicates_removed,
        "specialists_with_requests": specialists_with_requests,
        "avg_priority": round(avg_priority, 2),
    }
