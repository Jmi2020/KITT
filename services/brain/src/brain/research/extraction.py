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
from .models.coordinator import ConsultationRequest, ConsultationTier, ModelCapability

logger = logging.getLogger(__name__)


async def invoke_llama_direct(model_id: str, prompt: str, context: dict) -> str:
    """
    Directly invoke llama.cpp server without going through /api/query.
    This avoids circular dependencies in the research extraction flow.
    """
    import httpx

    # Determine which llama.cpp server based on model_id
    # Port 8082 = F16 (Llama-3.3-70B), Port 8083 = Q4 (Athene-V2)
    if "f16" in model_id.lower():
        llama_url = "http://host.docker.internal:8082/v1/chat/completions"
    else:
        llama_url = "http://host.docker.internal:8083/v1/chat/completions"

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                llama_url,
                json={
                    "messages": [
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": context.get("temperature", 0.1),
                    "max_tokens": 2000,
                    "stream": False
                }
            )
            response.raise_for_status()
            data = response.json()

            # Extract content from llama.cpp response
            if "choices" in data and len(data["choices"]) > 0:
                content = data["choices"][0].get("message", {}).get("content", "")
                logger.debug(f"LLM returned {len(content)} chars")
                return content
            else:
                logger.warning(f"Unexpected llama.cpp response format: {data}")
                return ""

    except Exception as e:
        logger.error(f"Direct llama.cpp invocation failed: {e}", exc_info=True)
        return ""


# Extraction prompt for atomic claims with quotes
CLAIM_EXTRACTION_PROMPT = """You are a research assistant extracting verifiable claims from text.

TASK: Extract atomic claims that are DIRECTLY SUPPORTED by verbatim quotes from the passage below.

For each claim, classify its type as one of:
- "fact"           → objective, verifiable statement
- "opinion"        → author’s judgment, interpretation, or prediction
- "recommendation" → explicit advice, best-practice, or suggested action

RULES:
1. Each claim must be a single, independent factual or opinionated assertion
2. Only extract claims that have direct quote support in the passage
3. Provide the exact verbatim quote(s) that support each claim
4. Include character positions (char_start, char_end) for each quote if possible
5. Do NOT infer or extrapolate beyond what quotes directly state
6. Do NOT include claims without quote support

OUTPUT FORMAT (strict JSON):
```json
{{
  "claims": [
    {{
      "claim": "The exact claim text",
      "claim_type": "fact" | "opinion" | "recommendation",
      "quotes": [
        {{
          "text": "The exact verbatim quote from passage",
          "char_start": 0,
          "char_end": 42
        }}
      ]
    }}
  ]
}}
```

PASSAGE:
{content}

CONTEXT QUERY: {query}

Extract all verifiable claims with their supporting quotes and types:"""


async def extract_claims_from_content(
    content: str,
    source_id: str,
    source_url: str,
    source_title: str,
    session_id: str,
    query: str,
    sub_question_id: Optional[str],
    model_coordinator,
    current_iteration: int = 0,
    invoke_model_func: Optional[Any] = None
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

        # Call llama.cpp directly to avoid /api/query circular dependency
        logger.info(f"🔍 Extracting claims from content (length: {len(content)} chars)")
        logger.info(f"🔍 Calling llama.cpp directly for extraction...")

        # Call llama.cpp directly
        response_text = await invoke_llama_direct(
            model_id="kitty-q4",
            prompt=prompt,
            context={"task": "extraction", "temperature": 0.1}
        )

        logger.info(f"🔍 LLM returned: {len(response_text)} chars")

        if not response_text or not response_text.strip():
            logger.warning("⚠️  No response from LLM for claim extraction")
            return []

        # Parse the response
        response_text = response_text.strip()

        # DEBUG: Log the raw response
        logger.debug(f"Raw LLM response (first 500 chars): {response_text[:500]}")

        # Extract JSON from response (handle markdown code blocks)
        json_str = None

        # Try extracting from code blocks first
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(1).strip()
        else:
            # Try to find JSON directly - look for outermost braces
            # Find the first { and last } to get the JSON object
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}')
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                json_str = response_text[start_idx:end_idx + 1]
            else:
                logger.warning(f"Could not find JSON in extraction response: {response_text[:200]}")
                return []

        # Clean the JSON string - remove any leading/trailing whitespace from lines
        json_str = '\n'.join(line.strip() for line in json_str.split('\n'))

        # DEBUG: Log the extracted JSON string
        logger.debug(f"Extracted JSON string (first 500 chars): {json_str[:500]}")

        try:
            extraction_result = json.loads(json_str)
            logger.debug(f"Successfully parsed JSON. Keys: {list(extraction_result.keys())}")
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse extraction JSON: {e}")
            logger.error(f"JSON string (first 500 chars): {json_str[:500]}")
            # Try one more time with aggressive cleaning
            try:
                # Remove all newlines and extra spaces from the JSON
                cleaned = ' '.join(json_str.split())
                extraction_result = json.loads(cleaned)
                logger.info("Successfully parsed JSON after aggressive cleaning")
            except json.JSONDecodeError as e2:
                logger.error(f"Failed even after cleaning: {e2}")
                return []

        claims_data = extraction_result.get("claims", [])
        if not claims_data:
            logger.debug("No claims extracted from content")
            return []

        # Convert to Claim objects
        claims: List[Claim] = []
        for claim_data in claims_data:
            claim_text = claim_data.get("claim", "").strip()
            raw_type = (claim_data.get("claim_type") or "fact").strip().lower()
            claim_type = raw_type if raw_type in {"fact", "opinion", "recommendation"} else "fact"
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
                confidence=prov_score * 0.7,  # Bootstrap confidence from provenance
                claim_type=claim_type,
            )

            claims.append(claim)
            logger.debug(
                f"Extracted claim: '{claim_text[:60]}...' "
                f"with {len(evidence)} quotes, provenance={prov_score:.2f}"
            )

        logger.info(f"Extracted {len(claims)} claims from content")
        return claims

    except Exception as e:
        logger.error(f"Error during claim extraction: {type(e).__name__}: {e}", exc_info=True)
        logger.error(f"Exception type: {type(e)}, Exception repr: {repr(e)}")
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
