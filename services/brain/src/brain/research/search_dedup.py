"""
Search Query Deduplication for Research Pipeline

Collects search queries at iteration start, deduplicates similar ones
using Jaccard similarity, and enables parallel execution of unique queries.

Adapted from the Collective Intelligence dedup module.
"""

import re
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple

logger = logging.getLogger(__name__)


def normalize_query(query: str) -> str:
    """
    Normalize a query for comparison.

    - Lowercase
    - Remove extra whitespace
    - Remove common punctuation
    """
    # Lowercase and strip
    normalized = query.lower().strip()

    # Remove punctuation except hyphens in compound words
    normalized = re.sub(r'[^\w\s-]', ' ', normalized)

    # Collapse multiple spaces
    normalized = re.sub(r'\s+', ' ', normalized).strip()

    return normalized


def get_word_set(query: str) -> Set[str]:
    """Extract word set from a query."""
    normalized = normalize_query(query)
    return set(normalized.split())


def jaccard_similarity(q1: str, q2: str) -> float:
    """
    Calculate word-level Jaccard similarity between two queries.

    Returns a value between 0.0 (no overlap) and 1.0 (identical).
    """
    words1 = get_word_set(q1)
    words2 = get_word_set(q2)

    if not words1 or not words2:
        return 0.0

    intersection = words1 & words2
    union = words1 | words2

    return len(intersection) / len(union)


@dataclass
class DeduplicationResult:
    """Result of query deduplication."""

    unique_queries: List[str]
    original_to_canonical: Dict[str, str]
    duplicates_removed: int
    similarity_threshold: float

    def get_canonical(self, original: str) -> str:
        """Get the canonical query for an original query."""
        return self.original_to_canonical.get(original, original)

    def map_results(
        self, results: Dict[str, List[Dict]]
    ) -> Dict[str, List[Dict]]:
        """
        Map results from canonical queries back to original queries.

        Args:
            results: Dict mapping canonical query -> search results

        Returns:
            Dict mapping original query -> search results
        """
        mapped = {}
        for original, canonical in self.original_to_canonical.items():
            if canonical in results:
                mapped[original] = results[canonical]
        return mapped


def deduplicate_queries(
    queries: List[str],
    similarity_threshold: float = 0.7,
    max_queries: int = 15,
) -> DeduplicationResult:
    """
    Deduplicate a list of search queries.

    Two queries are considered duplicates if their Jaccard similarity
    exceeds the threshold (default 0.7 = 70% word overlap).

    Args:
        queries: List of search queries to deduplicate
        similarity_threshold: Jaccard threshold (0.0-1.0)
        max_queries: Maximum unique queries to return

    Returns:
        DeduplicationResult with unique queries and mapping
    """
    if not queries:
        return DeduplicationResult(
            unique_queries=[],
            original_to_canonical={},
            duplicates_removed=0,
            similarity_threshold=similarity_threshold,
        )

    # Track: normalized_query -> canonical_query
    canonical_map: Dict[str, str] = {}

    # Track: original_query -> canonical_query
    original_to_canonical: Dict[str, str] = {}

    # Unique queries in order seen
    unique_queries: List[str] = []

    for query in queries:
        query = query.strip()
        if not query:
            continue

        normalized = normalize_query(query)

        # Check for exact match (normalized)
        if normalized in canonical_map:
            original_to_canonical[query] = canonical_map[normalized]
            logger.debug(
                f"Exact duplicate: '{query[:40]}...' -> '{canonical_map[normalized][:40]}...'"
            )
            continue

        # Check Jaccard similarity against existing canonical queries
        is_duplicate = False
        for existing_norm, canonical in canonical_map.items():
            similarity = jaccard_similarity(normalized, existing_norm)
            if similarity >= similarity_threshold:
                original_to_canonical[query] = canonical
                is_duplicate = True
                logger.debug(
                    f"Similar query ({similarity:.2f}): '{query[:40]}...' "
                    f"-> '{canonical[:40]}...'"
                )
                break

        if not is_duplicate:
            # New unique query
            canonical_map[normalized] = query
            original_to_canonical[query] = query
            unique_queries.append(query)

    # Limit total queries
    if len(unique_queries) > max_queries:
        logger.info(
            f"Limiting queries from {len(unique_queries)} to {max_queries}"
        )
        unique_queries = unique_queries[:max_queries]

    duplicates_removed = len(queries) - len(unique_queries)

    logger.info(
        f"Deduplication: {len(queries)} queries -> {len(unique_queries)} unique "
        f"(removed {duplicates_removed} duplicates, threshold={similarity_threshold})"
    )

    return DeduplicationResult(
        unique_queries=unique_queries,
        original_to_canonical=original_to_canonical,
        duplicates_removed=duplicates_removed,
        similarity_threshold=similarity_threshold,
    )


def get_dedup_stats(
    original_count: int,
    dedup_result: DeduplicationResult,
) -> Dict[str, int]:
    """
    Get statistics about the deduplication process.

    Returns:
        Dict with keys: original_count, unique_count, duplicates_removed
    """
    return {
        "original_count": original_count,
        "unique_count": len(dedup_result.unique_queries),
        "duplicates_removed": dedup_result.duplicates_removed,
    }
