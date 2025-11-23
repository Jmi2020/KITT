"""
Source-level summarization used by the autonomous research pipeline.

Generates short, query-focused summaries for each fetched source so
downstream synthesis can reason over distilled content instead of raw pages.
"""

from __future__ import annotations

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
\"\"\"{content}\"\"\"
"""


async def summarize_source_content(
    content: str,
    query: str,
    source_url: str,
    source_title: str,
    session_id: str,
    model_id: str = "llama-f16",
) -> str:
    """Summarize a single source for the current research session."""
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
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Failed to summarize source {source_url}: {exc}")
        # Fall back to a truncated preview for downstream visibility
        return (content[:1000] + "\n\n[summary failed; truncated raw content]")
