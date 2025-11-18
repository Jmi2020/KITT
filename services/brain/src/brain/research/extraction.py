"""
Evidence-First Claim Extraction

Extracts atomic claims with verbatim quotes from research content.
"""

import logging
import uuid
import json
import re
from typing import List, Dict, Any, Optional
from decimal import Decimal

from .types import Claim, EvidenceSpan, fingerprint, compute_provenance_score, merge_duplicate_claims

logger = logging.getLogger(__name__)


# Extraction prompt for atomic claims with quotes
CLAIM_EXTRACTION_PROMPT = """You are a research assistant extracting verifiable claims from text.

TASK: Extract atomic claims that are DIRECTLY SUPPORTED by verbatim quotes from the passage below.

RULES:
1. Each claim must be a single, independent factual assertion
2. Only extract claims that have direct quote support in the passage
3. Provide the exact verbatim quote(s) that support each claim
4. Include character positions (char_start, char_end) for each quote if possible
5. Do NOT infer or extrapolate beyond what quotes directly state
6. Do NOT include claims without quote support

OUTPUT FORMAT (strict JSON):
```json
{
  "claims": [
    {
      "claim": "The exact claim text",
      "quotes": [
        {
          "text": "The exact verbatim quote from passage",
          "char_start": 0,
          "char_end": 42
        }
      ]
    }
  ]
}
```

PASSAGE:
{content}

CONTEXT QUERY: {query}

Extract all verifiable claims with their supporting quotes:"""


async def extract_claims_from_content(
    content: str,
    source_id: str,
    source_url: str,
    source_title: str,
    session_id: str,
    query: str,
    sub_question_id: Optional[str],
    model_coordinator,
    current_iteration: int = 0
) -> List[Claim]:
    """
    Extract atomic claims with evidence from research content.

    Args:
        content: The text content to extract claims from
        source_id: Unique identifier for the source
        source_url: URL of the source
        source_title: Title of the source
        session_id: Research session ID
        query: The research query for context
        sub_question_id: Sub-question ID if hierarchical
        model_coordinator: ModelCoordinator for LLM invocation
        current_iteration: Current research iteration

    Returns:
        List of structured Claim objects with evidence
    """
    if not content or not content.strip():
        logger.debug("Empty content provided for claim extraction")
        return []

    # Truncate very long content to avoid token limits
    max_chars = 12000
    if len(content) > max_chars:
        logger.info(f"Truncating content from {len(content)} to {max_chars} chars for extraction")
        content = content[:max_chars] + "\n\n[...truncated...]"

    try:
        # Format the extraction prompt
        prompt = CLAIM_EXTRACTION_PROMPT.format(
            content=content,
            query=query
        )

        # Call model with low temperature for extraction
        logger.info(f"Extracting claims from content (length: {len(content)} chars)")

        # Use model coordinator to get a suitable model
        response = await model_coordinator.consult(
            task_description=prompt,
            required_capabilities=["reasoning"],
            context={"task": "extraction", "temperature": 0.1}
        )

        if not response or not response.content:
            logger.warning("No response from model for claim extraction")
            return []

        # Parse the response
        response_text = response.content.strip()

        # Extract JSON from response (handle markdown code blocks)
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # Try to find JSON directly
            json_match = re.search(r'\{.*"claims".*\}', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
            else:
                logger.warning(f"Could not find JSON in extraction response: {response_text[:200]}")
                return []

        try:
            extraction_result = json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse extraction JSON: {e}, text: {json_str[:200]}")
            return []

        claims_data = extraction_result.get("claims", [])
        if not claims_data:
            logger.debug("No claims extracted from content")
            return []

        # Convert to Claim objects
        claims: List[Claim] = []
        for claim_data in claims_data:
            claim_text = claim_data.get("claim", "").strip()
            quotes_data = claim_data.get("quotes", [])

            if not claim_text or not quotes_data:
                logger.debug(f"Skipping incomplete claim: {claim_text}")
                continue

            # Create evidence spans
            evidence: List[EvidenceSpan] = []
            for quote_data in quotes_data:
                quote_text = quote_data.get("text", "").strip()
                if not quote_text:
                    continue

                evidence.append(EvidenceSpan(
                    source_id=source_id,
                    url=source_url,
                    title=source_title,
                    quote=quote_text,
                    char_start=quote_data.get("char_start"),
                    char_end=quote_data.get("char_end")
                ))

            if not evidence:
                logger.debug(f"No evidence for claim: {claim_text}")
                continue

            # Compute provenance score
            quote_texts = [ev.quote for ev in evidence]
            prov_score = compute_provenance_score(claim_text, quote_texts)

            # Create claim
            claim = Claim(
                id=uuid.uuid4().hex,
                session_id=session_id,
                sub_question_id=sub_question_id,
                text=claim_text,
                evidence=evidence,
                entailment_score=0.0,  # Will be computed later by NLI
                provenance_score=prov_score,
                dedupe_fingerprint=fingerprint(claim_text),
                confidence=prov_score * 0.7  # Bootstrap confidence from provenance
            )

            claims.append(claim)
            logger.debug(
                f"Extracted claim: '{claim_text[:60]}...' "
                f"with {len(evidence)} quotes, provenance={prov_score:.2f}"
            )

        logger.info(f"Extracted {len(claims)} claims from content")
        return claims

    except Exception as e:
        logger.error(f"Error during claim extraction: {e}", exc_info=True)
        return []


def deduplicate_and_merge_claims(claims: List[Claim]) -> List[Claim]:
    """
    Deduplicate claims by fingerprint and merge evidence.

    Wrapper around merge_duplicate_claims from types module.

    Args:
        claims: List of potentially duplicate claims

    Returns:
        Deduplicated and merged claims
    """
    if not claims:
        return []

    initial_count = len(claims)
    merged = merge_duplicate_claims(claims)

    if len(merged) < initial_count:
        logger.info(
            f"Deduplicated {initial_count} claims to {len(merged)} "
            f"({initial_count - len(merged)} duplicates merged)"
        )

    return merged


def get_claim_summary(claims: List[Claim]) -> Dict[str, Any]:
    """
    Generate summary statistics for a list of claims.

    Args:
        claims: List of claims to summarize

    Returns:
        Dictionary with claim statistics
    """
    if not claims:
        return {
            "total_claims": 0,
            "total_evidence": 0,
            "avg_provenance": 0.0,
            "avg_confidence": 0.0,
            "unique_sources": 0
        }

    total_evidence = sum(len(c.evidence) for c in claims)
    avg_provenance = sum(c.provenance_score for c in claims) / len(claims)
    avg_confidence = sum(c.confidence for c in claims) / len(claims)
    unique_sources = len(set(ev.url for c in claims for ev in c.evidence))

    return {
        "total_claims": len(claims),
        "total_evidence": total_evidence,
        "avg_provenance": round(avg_provenance, 3),
        "avg_confidence": round(avg_confidence, 3),
        "unique_sources": unique_sources,
        "avg_evidence_per_claim": round(total_evidence / len(claims), 2)
    }
