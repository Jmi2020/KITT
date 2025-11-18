"""
Research Types for Evidence-First System

Provides structured types for claims, evidence, and verification.
"""

import hashlib
import re
from dataclasses import dataclass, field
from typing import List, Optional, Set


@dataclass
class EvidenceSpan:
    """
    A verbatim quote from a source supporting a claim.

    Attributes:
        source_id: Unique identifier for the source document
        url: Source URL
        title: Source title/name
        quote: Exact verbatim text from source
        char_start: Character offset where quote begins (optional)
        char_end: Character offset where quote ends (optional)
    """
    source_id: str
    url: str
    title: str
    quote: str
    char_start: Optional[int] = None
    char_end: Optional[int] = None


@dataclass
class Claim:
    """
    An atomic claim extracted from research with evidence attribution.

    Represents a single factual assertion backed by verbatim quotes.

    Attributes:
        id: Unique claim identifier
        session_id: Research session this claim belongs to
        sub_question_id: Sub-question this claim answers (if hierarchical)
        text: The claim statement
        evidence: List of evidence spans supporting this claim
        entailment_score: NLI entailment score 0-1 (premise→hypothesis)
        provenance_score: Quote coverage score 0-1 (lexical overlap)
        dedupe_fingerprint: Hash for clustering duplicate claims
        confidence: Overall confidence score 0-1
    """
    id: str
    session_id: str
    sub_question_id: Optional[str]
    text: str
    evidence: List[EvidenceSpan]
    entailment_score: float = 0.0       # 0..1 (NLI score when available)
    provenance_score: float = 0.0       # 0..1 (quote coverage)
    dedupe_fingerprint: str = ""        # For clustering identical claims
    confidence: float = 0.0              # Overall confidence


# Helper functions

def fingerprint(text: str) -> str:
    """
    Generate a deduplication fingerprint for a claim.

    Used to cluster semantically identical claims even with slight
    wording variations.

    Args:
        text: Claim text to fingerprint

    Returns:
        16-character hex fingerprint
    """
    normalized = text.strip().lower()
    return hashlib.sha1(normalized.encode()).hexdigest()[:16]


def compute_provenance_score(claim_text: str, quotes: List[str]) -> float:
    """
    Calculate how well quotes support a claim using lexical overlap.

    Computes the fraction of content words in the claim that appear
    in at least one supporting quote. This is a simple baseline for
    evidence strength before NLI verification is available.

    Args:
        claim_text: The claim statement
        quotes: List of verbatim quote strings

    Returns:
        Score from 0.0 (no overlap) to 1.0 (full coverage)
    """
    # Extract content words from claim (>3 chars, alphanumeric)
    claim_words = set([
        w for w in re.findall(r"[a-z0-9]+", claim_text.lower())
        if len(w) > 3
    ])

    if not claim_words:
        return 0.0

    # Count how many claim words appear in quotes
    supported_words = sum(
        1 for word in claim_words
        if any(word in quote.lower() for quote in quotes)
    )

    return supported_words / len(claim_words)


def compute_composite_confidence(
    claims: List[Claim],
    domain_diversity: float = 0.0,
    cluster_consensus: float = 0.0,
    recency_score: float = 0.0
) -> float:
    """
    Calculate composite confidence score from multiple factors.

    Weighted combination:
    - 35% average entailment score
    - 25% average provenance score
    - 15% domain diversity (unique domains / total sources)
    - 15% cluster consensus (agreement between similar claims)
    - 10% recency (how recent sources are)

    Args:
        claims: List of claims to score
        domain_diversity: Domain diversity metric 0-1
        cluster_consensus: Claim clustering consensus 0-1
        recency_score: Source recency metric 0-1

    Returns:
        Composite confidence score 0-1
    """
    if not claims:
        return 0.0

    avg_entailment = sum(c.entailment_score for c in claims) / len(claims)
    avg_provenance = sum(c.provenance_score for c in claims) / len(claims)

    confidence = (
        0.35 * avg_entailment +
        0.25 * avg_provenance +
        0.15 * domain_diversity +
        0.15 * cluster_consensus +
        0.10 * recency_score
    )

    return min(1.0, max(0.0, confidence))


def cluster_claims_by_fingerprint(claims: List[Claim]) -> dict[str, List[Claim]]:
    """
    Group claims by deduplication fingerprint.

    Claims with identical fingerprints are likely duplicates or
    near-duplicates and should be merged.

    Args:
        claims: List of claims to cluster

    Returns:
        Dict mapping fingerprint -> list of claims with that fingerprint
    """
    clusters: dict[str, List[Claim]] = {}

    for claim in claims:
        fp = claim.dedupe_fingerprint
        if fp not in clusters:
            clusters[fp] = []
        clusters[fp].append(claim)

    return clusters


def merge_duplicate_claims(claims: List[Claim]) -> List[Claim]:
    """
    Deduplicate and merge claims with identical fingerprints.

    For each cluster of duplicate claims:
    - Keep the claim with highest confidence
    - Merge all evidence from duplicates
    - Average scores

    Args:
        claims: List of potentially duplicate claims

    Returns:
        Deduplicated list of claims
    """
    clusters = cluster_claims_by_fingerprint(claims)
    merged: List[Claim] = []

    for fingerprint, cluster in clusters.items():
        if len(cluster) == 1:
            # No duplicates
            merged.append(cluster[0])
        else:
            # Merge duplicates
            # Keep claim with highest confidence as base
            best = max(cluster, key=lambda c: c.confidence)

            # Collect all unique evidence
            all_evidence: List[EvidenceSpan] = []
            seen_quotes: Set[str] = set()

            for claim in cluster:
                for ev in claim.evidence:
                    if ev.quote not in seen_quotes:
                        all_evidence.append(ev)
                        seen_quotes.add(ev.quote)

            # Average scores
            avg_entailment = sum(c.entailment_score for c in cluster) / len(cluster)
            avg_provenance = sum(c.provenance_score for c in cluster) / len(cluster)
            avg_confidence = sum(c.confidence for c in cluster) / len(cluster)

            # Create merged claim
            merged_claim = Claim(
                id=best.id,  # Keep ID of highest confidence claim
                session_id=best.session_id,
                sub_question_id=best.sub_question_id,
                text=best.text,
                evidence=all_evidence,
                entailment_score=avg_entailment,
                provenance_score=avg_provenance,
                dedupe_fingerprint=fingerprint,
                confidence=avg_confidence
            )

            merged.append(merged_claim)

    return merged
