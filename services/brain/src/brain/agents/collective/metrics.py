"""Diversity metrics for collective meta-agent proposals.

Measures how different proposals are from each other to validate that
proposer blinding is working effectively.
"""

from __future__ import annotations

import re
from typing import List, Dict, Any


def jaccard_similarity(text_a: str, text_b: str) -> float:
    """Calculate Jaccard similarity between two texts.

    Args:
        text_a: First text
        text_b: Second text

    Returns:
        Similarity score between 0.0 (completely different) and 1.0 (identical)
    """
    # Tokenize into words (lowercase, alphanumeric only)
    tokens_a = set(re.findall(r"\w+", text_a.lower()))
    tokens_b = set(re.findall(r"\w+", text_b.lower()))

    # Handle empty sets
    if not tokens_a and not tokens_b:
        return 1.0  # Both empty = identical
    if not tokens_a or not tokens_b:
        return 0.0  # One empty = completely different

    # Jaccard = |A ∩ B| / |A ∪ B|
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b

    return len(intersection) / len(union) if union else 0.0


def pairwise_diversity(proposals: List[str]) -> Dict[str, Any]:
    """Calculate pairwise diversity metrics for a set of proposals.

    Args:
        proposals: List of proposal texts

    Returns:
        Dictionary with diversity metrics:
        - avg_jaccard: Average Jaccard similarity (0=different, 1=identical)
        - avg_diversity: 1 - avg_jaccard (0=identical, 1=different)
        - min_similarity: Minimum pairwise similarity
        - max_similarity: Maximum pairwise similarity
        - pairs_analyzed: Number of pairs compared
    """
    if len(proposals) < 2:
        return {
            "avg_jaccard": 0.0,
            "avg_diversity": 1.0,
            "min_similarity": 0.0,
            "max_similarity": 0.0,
            "pairs_analyzed": 0,
        }

    similarities = []

    # Calculate all pairwise similarities
    for i in range(len(proposals)):
        for j in range(i + 1, len(proposals)):
            sim = jaccard_similarity(proposals[i], proposals[j])
            similarities.append(sim)

    avg_sim = sum(similarities) / len(similarities) if similarities else 0.0

    return {
        "avg_jaccard": round(avg_sim, 3),
        "avg_diversity": round(1.0 - avg_sim, 3),
        "min_similarity": round(min(similarities), 3) if similarities else 0.0,
        "max_similarity": round(max(similarities), 3) if similarities else 0.0,
        "pairs_analyzed": len(similarities),
    }


def calculate_proposal_metrics(proposals: List[str]) -> Dict[str, Any]:
    """Calculate comprehensive metrics for a set of proposals.

    Args:
        proposals: List of proposal texts

    Returns:
        Dictionary with metrics:
        - count: Number of proposals
        - avg_length: Average proposal length in characters
        - diversity: Diversity metrics from pairwise_diversity()
    """
    if not proposals:
        return {
            "count": 0,
            "avg_length": 0,
            "diversity": pairwise_diversity([]),
        }

    lengths = [len(p) for p in proposals]

    return {
        "count": len(proposals),
        "avg_length": round(sum(lengths) / len(lengths), 1) if lengths else 0.0,
        "min_length": min(lengths) if lengths else 0,
        "max_length": max(lengths) if lengths else 0,
        "diversity": pairwise_diversity(proposals),
    }
