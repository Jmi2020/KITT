# Research Pipeline Refactor – Implementation Plan

Research Pipeline Refactor – Implementation Plan

0. Mental model of what you’re building

You already have:
    •    A LangGraph-based 🧩 autonomous research agent￼ orchestrated by graph.py + nodes.py.
    •    Evidence-first claim extraction in extraction.py that produces Claim objects with supporting quotes.
    •    Final synthesis via _generate_ai_synthesis in nodes.py, plus a fallback “basic” synthesis when no coordinator is available.

We’ll add three core capabilities:
    1.    Per-source summarization – each fetched page gets a small, query-focused summary.
    2.    Opinion-aware claim extraction – each claim is tagged as fact, opinion, or recommendation.
    3.    A stronger evidence-first final synthesis prompt – with an executive summary, deep dive by theme, and explicit treatment of opinions & disagreements.

The steps are designed so you can ship them incrementally behind feature flags.

⸻

1. Add feature flags to ResearchConfig (state.py)

First, make these new features configurable.

1.1 Extend ResearchConfig

In state.py, extend ResearchConfig:

class ResearchConfig(TypedDict, total=False):
    """Configuration for research session"""
    # Strategy
    strategy: str  # "breadth_first", "depth_first", "task_decomposition", "hybrid"

    # Iteration limits
    max_iterations: int
    max_depth: int
    max_breadth: int

    # Quality thresholds
    min_quality_score: float
    min_confidence: float
    min_ragas_score: float

    # Saturation
    saturation_threshold: float
    min_novelty_rate: float

    # Budget
    max_total_cost_usd: float
    max_external_calls: int

    # Time limits
    max_time_seconds: Optional[float]

    # Model selection
    prefer_local: bool
    allow_external: bool
    enable_debate: bool
    enable_hierarchical: bool

    # NEW: analysis options
    enable_source_summaries: bool        # Summarize each fetched source
    enable_opinion_tagging: bool         # Tag claims as fact/opinion/recommendation

    # Decomposition config...
    # (rest of your fields unchanged)

1.2 Update DEFAULT_RESEARCH_CONFIG

Still in state.py, extend DEFAULT_RESEARCH_CONFIG:

DEFAULT_RESEARCH_CONFIG: ResearchConfig = {
    "strategy": "hybrid",
    "max_iterations": 15,
    "max_depth": 3,
    "max_breadth": 10,
    "min_quality_score": 0.7,
    "min_confidence": 0.7,
    "min_ragas_score": 0.75,
    "saturation_threshold": 0.75,
    "min_novelty_rate": 0.15,
    "max_total_cost_usd": 2.0,
    "max_external_calls": 10,
    "max_time_seconds": None,
    "prefer_local": True,
    "allow_external": True,
    "enable_debate": True,
    "enable_hierarchical": False,
    "min_sub_questions": 2,
    "max_sub_questions": 5,
    "sub_question_min_iterations": 2,
    "sub_question_max_iterations": 5,

    # NEW
    "enable_source_summaries": True,
    "enable_opinion_tagging": True,
}

That lets you A/B-test the new behavior per session.

⸻

2. Opinion-aware claim extraction (extraction.py + your Claim type)

Right now, extraction.py pulls only factual claims. We’ll tag each extracted claim with a simple claim_type:
    •    "fact" – objective, verifiable statement
    •    "opinion" – author’s judgment / interpretation
    •    "recommendation" – explicit advice or best-practice

This powers later synthesis and “perspectives” sections.

2.1 Extend your Claim dataclass (in types.py)

Wherever Claim is defined (e.g. types.py), extend it with a claim_type field:

from dataclasses import dataclass
from typing import List, Optional

@dataclass
class EvidenceSpan:
    source_id: str
    url: str
    title: str
    quote: str
    char_start: Optional[int]
    char_end: Optional[int]

@dataclass
class Claim:
    id: str
    session_id: str
    sub_question_id: Optional[str]
    text: str
    evidence: List[EvidenceSpan]
    entailment_score: float
    provenance_score: float
    dedupe_fingerprint: str
    confidence: float

    # NEW: what kind of claim is this?
    claim_type: str = "fact"   # "fact" | "opinion" | "recommendation"

If you’re persisting Claim somewhere (DB, JSON), you can default-migrate: treat missing claim_type as "fact".

2.2 Update CLAIM_EXTRACTION_PROMPT

In extraction.py, your CLAIM_EXTRACTION_PROMPT currently just asks for claims + quotes. Replace / extend it so the JSON includes a claim_type:

CLAIM_EXTRACTION_PROMPT = """You are a research assistant extracting verifiable claims from text.

TASK: Extract atomic claims that are DIRECTLY SUPPORTED by verbatim quotes from the passage below.

For each claim, classify its type as one of:
- "fact"          → objective, verifiable statement
- "opinion"       → author’s judgment, interpretation, or prediction
- "recommendation" → advice, best-practice, or suggested action

RULES:
1. Each claim must be a single, independent factual or opinionated assertion
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
      "claim": "string",
      "claim_type": "fact" | "opinion" | "recommendation",
      "quotes": [
        {
          "text": "verbatim quote",
          "char_start": 0,
          "char_end": 42
        }
      ]
    }
  ]
}

PASSAGE:
{content}

CONTEXT QUERY: {query}

Extract all verifiable claims with their supporting quotes and types:”””

This keeps your existing JSON structure but adds one extra field.

### 2.3 Parse `claim_type` from the LLM output

In `extract_claims_from_content` (still `extraction.py`), inside the loop that converts `claim_data` into `Claim` objects, extend it like this:

```python
        # Convert to Claim objects
        claims: List[Claim] = []
        for claim_data in claims_data:
            claim_text = claim_data.get("claim", "").strip()
            if not claim_text:
                continue

            # NEW: parse claim_type
            raw_type = (claim_data.get("claim_type") or "fact").strip().lower()
            if raw_type not in {"fact", "opinion", "recommendation"}:
                raw_type = "fact"
            claim_type = raw_type

            quotes_data = claim_data.get("quotes", [])
            if not quotes_data:
                logger.debug(f"No quotes for claim: {claim_text}")
                continue

            # Create evidence spans (unchanged)
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

            # Compute provenance score (unchanged)
            quote_texts = [ev.quote for ev in evidence]
            prov_score = compute_provenance_score(claim_text, quote_texts)

            # Create claim with type
            claim = Claim(
                id=uuid.uuid4().hex,
                session_id=session_id,
                sub_question_id=sub_question_id,
                text=claim_text,
                evidence=evidence,
                entailment_score=0.0,  # NLI later
                provenance_score=prov_score,
                dedupe_fingerprint=fingerprint(claim_text),
                confidence=prov_score * 0.7,
                claim_type=claim_type,  # NEW
            )

            claims.append(claim)

Now every claim knows whether it’s a fact, opinion, or recommendation. That sets you up for opinion-aware synthesis and “perspectives” sections.

🔎 For background on this style of tagging, check: 🧠 opinion mining with LLMs￼.

⸻

3. Per-source summarization (summarization.py + nodes.py)

Now we make each fetched source digestible before extraction. This is mostly for you, but you can also use summaries during synthesis.

3.1 New module: summarization.py

Create a new file next to extraction.py:

# summarization.py
"""
Source-level summarization used by the autonomous research pipeline.
"""

import logging
from typing import Optional

from .extraction import invoke_llama_direct

logger = logging.getLogger(__name__)

SOURCE_SUMMARY_PROMPT = """You are summarizing a single web page for an autonomous research agent.

Original query: {query}
Source title: {title}
Source URL: {url}

TASK:
1. Write a 3–5 sentence summary focused on what this source contributes to the query.
2. Then list 3–7 bullet points capturing the most important specific claims or findings.
3. If the author expresses clear opinions or recommendations, include them explicitly.

Respond in Markdown with the following sections:

## Summary
[3–5 sentences]

## Key Points
- ...

## Author Perspective
- ... (omit this section if no clear opinions)

Source content:
\"\"\"{content}\"\"\""""

async def summarize_source_content(
    content: str,
    query: str,
    source_url: str,
    source_title: str,
    session_id: str,
    model_id: str = "llama-f16",
) -> str:
    """
    Summarize a single source for the current research session.
    """
    if not content or not content.strip():
        return ""

    prompt = SOURCE_SUMMARY_PROMPT.format(
        query=query,
        title=source_title,
        url=source_url,
        content=content,
    )

    context = {
        "session_id": session_id,
        "temperature": 0.2,
        "max_tokens": 800,
        "purpose": "source_summary",
    }

    try:
        summary_md = await invoke_llama_direct(
            model_id=model_id,
            prompt=prompt,
            context=context,
        )
        if not summary_md:
            return ""
        return summary_md.strip()
    except Exception as e:
        logger.error(f"Failed to summarize source {source_url}: {e}")
        # Fall back to a truncated preview
        return (content[:1000] + "\n\n[summary failed; truncated raw content]")

This reuses your existing direct 🖥️ llama.cpp￼ integration.

3.2 Wire summarization into _execute_tasks_real (nodes.py)

In nodes.py, import the helper:

from ..summarization import summarize_source_content

Inside _execute_tasks_real, in the web-search / research-deep branch where you build full_contents:
    1.    After constructing full_contents, call the summarizer if the feature flag is enabled.
    2.    Attach summaries to the finding so they’re available later.

Conceptually:

                        # full_contents already populated: [{"index", "url", "title", "content"}, ...]

                        source_summaries: list[dict[str, str]] = []
                        if state["config"].get("enable_source_summaries", True):
                            for fc in full_contents:
                                try:
                                    summary_md = await summarize_source_content(
                                        content=fc["content"],
                                        query=state["query"],
                                        source_url=fc["url"],
                                        source_title=fc["title"],
                                        session_id=state["session_id"],
                                    )
                                    if summary_md:
                                        source_summaries.append(
                                            {
                                                "url": fc["url"],
                                                "title": fc["title"],
                                                "summary": summary_md,
                                            }
                                        )
                                except Exception as e:
                                    logger.error(
                                        f"Source summarization failed for {fc.get('url')}: {e}",
                                        exc_info=True,
                                    )

                        # Create finding from fetched content (existing logic)
                        if full_contents:
                            content_parts = []
                            for fc in full_contents:
                                content_parts.append(
                                    f"## Source {fc['index']}: {fc['title']}\n"
                                    f"URL: {fc['url']}\n\n"
                                    f"{fc['content']}"
                                )
                            content = "\n\n---\n\n".join(content_parts)

                            finding = {
                                "id": f"finding_{state['current_iteration']}_{task['task_id']}",
                                "finding_type": "web_search",
                                "content": content,
                                "confidence": 0.0,
                                "tool": tool_name.value,
                                "search_query": task.get("query_used", task.get("query")),
                                # other existing fields...
                            }

                            # NEW: attach summaries
                            if source_summaries:
                                finding["source_summaries"] = source_summaries

You don’t have to use the summaries immediately; just getting them into state["findings"] gives you a hook for later UI / synthesis improvements.

⸻

4. Make the final synthesis actually “insightful” (nodes.py)

Now that we have claim_type and (optionally) source summaries, we can beef up the final synthesis.

4.1 Include claim_type in the claims JSON for synthesis

In _generate_ai_synthesis (claims branch) you already build claims_json. Update it so each entry includes the new field:

        if claims:
            logger.info(f"Synthesizing with {len(claims)} structured claims")

            import json
            claims_json = []
            for claim in claims:
                claim_obj = {
                    "claim": claim.text,
                    "claim_type": getattr(claim, "claim_type", "fact"),  # NEW
                    "confidence": round(claim.confidence, 2),
                    "provenance_score": round(claim.provenance_score, 2),
                    "quotes": [
                        {
                            "text": ev.quote,
                            "source_url": ev.url,
                            "source_title": ev.title,
                        }
                        for ev in claim.evidence
                    ],
                }
                claims_json.append(claim_obj)

            claims_text = json.dumps(claims_json, indent=2, ensure_ascii=False)

Now the synthesis model sees facts vs opinions vs recommendations explicitly.

4.2 Replace the claims-based synthesis prompt with a “summary + deep dive” format

Replace the claims-branch prompt in _generate_ai_synthesis with something like:

            # Construct evidence-first synthesis prompt
            prompt = f"""You are an expert research synthesizer helping an autonomous research agent.

Original Query: {state["query"]}

You are given VERIFIED CLAIMS extracted from multiple sources. Each claim includes:
- claim: the text of the claim
- claim_type: "fact", "opinion", or "recommendation"
- quotes: verbatim evidence with source URLs and titles
- provenance_score and confidence scores

VERIFIED CLAIMS (JSON):
{claims_text}

SOURCES TABLE:
{sources_text}

YOUR TASK
=========
Produce a two-part answer:

1. **Executive Summary** — a concise, non-technical overview of the most important takeaways.
2. **Deep Dive by Theme** — a structured analysis that groups related claims into themes, surfaces consensus and disagreements, and clearly distinguishes facts from opinions/recommendations.

DETAILED REQUIREMENTS
---------------------
- Work ONLY from the verified claims and sources table above.
- First, mentally cluster claims into 3–7 themes (e.g., "Effectiveness", "Risks", "Adoption Barriers").
- Within each theme:
  - Clearly state the main factual findings.
  - Call out author opinions and recommendations (claim_type != "fact") as perspectives, not facts.
  - Explicitly describe any disagreements or conflicting claims between sources.
- Use inline citation numbers [1], [2], ... that map back to the SOURCES TABLE.
- Prefer high-provenance, high-confidence claims; mention when evidence is thin or mixed.

OUTPUT FORMAT (Markdown)
------------------------

## Executive Summary
- 3–6 bullet points summarizing the most important overall insights.
- Each bullet should be stand-alone and, where possible, include citation numbers [1], [2]...

## Deep Dive by Theme

### Theme 1: <short label>
- Short paragraph describing the theme and why it matters.
- Bullet list of key factual findings with citations (fact claims).
- Bullet list or short paragraph for author opinions / recommendations, clearly labeled as such.

### Theme 2: <short label>
...

(Continue with as many themes as are justified by the claims.)

## Perspectives & Disagreements
- Bullet list of the most important areas where sources disagree, including citations.
- For each, briefly describe why the disagreement exists (different data, methodology, context, etc.) if you can infer it from the claims.

## Knowledge Gaps
- Bullet list of missing information, ambiguities, or open questions.

## Confidence Assessment
One short paragraph stating overall confidence (High / Medium / Low) and why, based on:
- number and diversity of sources
- provenance_score and confidence for key claims
- presence or absence of strong disagreements.
"""

This forces the model into the “summary + deep dive + perspectives” structure instead of a bland essay.

📚 For inspiration on this style of answer, see: 📖 citation-rich RAG synthesis patterns￼.

⸻

5. Optional next steps (if you want to go further)

These are next-level, optional improvements:
    1.    Use source summaries during synthesis
In _generate_ai_synthesis, if finding["source_summaries"] exists, you can include a short “Source Summaries” section in the prompt (especially in the fallback branch when no claims exist).
    2.    Lightweight clustering before synthesis
Instead of asking the model to “mentally” cluster, you can pre-cluster claims into themes using an embedding model like 🧬 Sentence Transformers￼ and pass those theme labels into the prompt.
    3.    NLI-based contradiction detection
Add an offline step that runs a small NLI model over pairs of high-impact claims to identify explicit contradictions, then feed those into the “Perspectives & Disagreements” section.

None of these are required to get a big quality jump; your big wins will come from:
    •    tagging claims by type,
    •    summarizing each source,
    •    and tightening the synthesis prompt.

⸻

6. Integration checklist

To make this concrete, here’s a quick checklist you can work through:
    1.    Config
    •    Add enable_source_summaries and enable_opinion_tagging to ResearchConfig.
    •    Set sensible defaults in DEFAULT_RESEARCH_CONFIG.
    2.    Claim model + extraction
    •    Add claim_type: str = "fact" to Claim.
    •    Update CLAIM_EXTRACTION_PROMPT with the claim_type field.
    •    Parse claim_type in extract_claims_from_content.
    3.    Summarization
    •    Create summarization.py with summarize_source_content.
    •    Import and call summarize_source_content in _execute_tasks_real.
    •    Attach source_summaries to each finding.
    4.    Synthesis
    •    Include claim_type when building claims_json in _generate_ai_synthesis.
    •    Replace the existing claims-branch prompt with the “Executive Summary + Deep Dive” prompt above.
    •    Run a full research session and manually inspect the new answer shape.
    5.    Polish
    •    Tweak prompt wording once you see 2–3 real outputs.
    •    Turn the features off/on via config to compare old vs new reports.
