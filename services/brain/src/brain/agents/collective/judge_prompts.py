"""Structured prompt builder for GPT-OSS 120B judge in collective meta-agent.

Implements 6-section structured prompts for optimal synthesis:
1. Conversation Context - Recent dialogue history
2. Task Description - Core user request
3. Full Knowledge Base - Unfiltered KB access with chunk IDs
4. Specialist Proposals - All proposals with KB citations
5. Tool Instructions - Available tools and usage guidance
6. Synthesis Instructions - Final verdict requirements
"""

from __future__ import annotations
from typing import List, Dict, Optional, Set
import re
import logging

from brain.token_budgets import TokenBudgetManager

logger = logging.getLogger(__name__)


def deduplicate_kb_references(proposals: List[str]) -> Set[str]:
    """Extract unique KB chunk IDs referenced across all proposals.

    Args:
        proposals: List of specialist proposal texts

    Returns:
        Set of KB chunk IDs referenced (e.g., {'mem_123', 'mem_456'})
    """
    kb_refs = set()

    # Pattern matches [KB#id] where id can be alphanumeric/underscore
    pattern = r'\[KB#([\w\-]+)\]'

    for proposal in proposals:
        matches = re.findall(pattern, proposal)
        kb_refs.update(matches)

    return kb_refs


def build_judge_system_prompt(pattern: str = "council") -> str:
    """Build system prompt for GPT-OSS 120B judge.

    Args:
        pattern: Deliberation pattern (council, debate, pipeline)

    Returns:
        System prompt string
    """
    base = """You are GPT-OSS 120B Judge, KITTY's deliberation synthesizer.

## Core Constraints (CRITICAL)
- **NEVER** fabricate information, citations, or KB chunk IDs
- **ALWAYS** cite KB chunk IDs (e.g., [KB#123]) when referencing knowledge base content
- **ALWAYS** verify claims against KB context before including in verdict
- If specialists disagree → explicitly acknowledge the disagreement and explain your reasoning
- If evidence is inconclusive → state this clearly and provide best available guidance

## Your Role
- Review all specialist proposals with full context access
- Use thinking mode to deeply analyze evidence and arguments
- Verify that specialist claims are supported by KB evidence
- Synthesize a final verdict that integrates the best ideas
- Ensure safety, clarity, and testability in recommendations
- Call tools to verify claims or gather additional context when needed

## Evidence Synthesis Requirements
- Cross-reference specialist proposals against KB context
- Identify which claims have strong KB support vs. weak/no support
- Prioritize recommendations backed by evidence over unsupported assertions
- Note any conflicts between specialists and how you resolved them

## You have access to
- Full conversation history
- Complete knowledge base (no tag filtering)
- All specialist proposals with KB citations
- Web search and other verification tools

"""

    if pattern == "council":
        base += """## Pattern: Council
Synthesize diverse specialist viewpoints into a unified recommendation.
- Identify consensus areas across specialists
- Note where specialists diverge and explain which approach you favor
- Integrate the strongest arguments from each proposal"""
    elif pattern == "debate":
        base += """## Pattern: Debate
Weigh PRO and CON arguments, then make a balanced decision.
- Evaluate the strength of evidence on each side
- Identify which arguments are well-supported by KB context
- Acknowledge valid points from both sides before concluding"""
    elif pattern == "pipeline":
        base += """## Pattern: Pipeline
Review the sequential pipeline output and provide final assessment.
- Verify each pipeline stage completed successfully
- Identify any gaps or issues in the pipeline output"""

    return base


def build_judge_user_prompt(
    task: str,
    conversation_summary: str,
    kb_context: str,
    proposals: List[str],
    plan_logs: Optional[str] = None
) -> str:
    """Build structured user prompt for GPT-OSS 120B judge.

    6-section structure optimized for synthesis:
    1. Conversation Context
    2. Task Description
    3. Knowledge Base
    4. Specialist Proposals
    5. Planning Context (if available)
    6. Synthesis Instructions

    Args:
        task: User task/query
        conversation_summary: Conversation history summary
        kb_context: Full KB context with chunk IDs
        proposals: List of specialist proposals
        plan_logs: Optional planning logs

    Returns:
        Structured user prompt string
    """
    sections = []

    # Section 1: Conversation Context
    if conversation_summary:
        sections.append(
            f"## 1. Conversation Context\n\n{conversation_summary}"
        )

    # Section 2: Task Description
    sections.append(
        f"## 2. Task\n\n{task}"
    )

    # Section 3: Knowledge Base (Full Access)
    sections.append(
        f"## 3. Knowledge Base (Full Context)\n\n{kb_context}\n\n"
        f"Note: KB chunks are tagged with [KB#id] for citation tracking."
    )

    # Section 4: Specialist Proposals
    proposals_text = "\n\n---\n\n".join([
        f"**Proposal {i+1}:**\n{prop}"
        for i, prop in enumerate(proposals)
    ])

    sections.append(
        f"## 4. Specialist Proposals\n\n{proposals_text}\n\n"
        f"Each proposal may reference KB chunks using [KB#id] citations."
    )

    # Section 5: Planning Context (if available)
    if plan_logs:
        sections.append(
            f"## 5. Planning Context\n\n{plan_logs}"
        )

    # Section 6: Synthesis Instructions with quality requirements
    sections.append(
        "## 6. Your Synthesis\n\n"
        "Provide your final verdict using this structure:\n\n"
        "### Decision\n"
        "Clear, actionable recommendation addressing the task.\n\n"
        "### Confidence Level\n"
        "State High/Medium/Low based on evidence quality:\n"
        "- **High**: Strong KB support, specialist consensus, verified claims\n"
        "- **Medium**: Partial KB support, some disagreement, reasonable inference\n"
        "- **Low**: Limited evidence, significant disagreement, uncertainty\n\n"
        "### Rationale\n"
        "Key reasoning with KB citations [KB#id]. Explain:\n"
        "- Which specialist arguments you found most compelling\n"
        "- How KB evidence supports your decision\n"
        "- Any disagreements and how you resolved them\n\n"
        "### Evidence Summary\n"
        "- Strongest supporting evidence from KB\n"
        "- Any gaps or limitations in available information\n"
        "- Claims that could not be fully verified\n\n"
        "### Next Steps\n"
        "Concrete actions or considerations for the user.\n\n"
        "---\n"
        "Use thinking mode to analyze deeply. Call tools if you need to verify "
        "claims or gather additional context before deciding."
    )

    return "\n\n".join(sections)


def check_judge_prompt_budget(
    system_prompt: str,
    user_prompt: str,
    tools_json: Optional[str] = None
) -> bool:
    """Check if judge prompt fits within 100k token budget.

    Args:
        system_prompt: System prompt text
        user_prompt: User prompt text
        tools_json: Optional tools JSON

    Returns:
        True if within budget, False otherwise
    """
    total_tokens = (
        TokenBudgetManager.estimate_tokens(system_prompt) +
        TokenBudgetManager.estimate_tokens(user_prompt)
    )

    if tools_json:
        total_tokens += TokenBudgetManager.estimate_tokens(tools_json)

    budget_limit = TokenBudgetManager.JUDGE_BUDGET.prompt_budget

    if total_tokens > budget_limit:
        logger.warning(
            f"Judge prompt exceeds budget: {total_tokens}/{budget_limit} tokens"
        )
        return False

    logger.info(f"Judge prompt within budget: {total_tokens}/{budget_limit} tokens")
    return True


def trim_proposals_to_budget(
    proposals: List[str],
    max_tokens: int = 25000
) -> List[str]:
    """Trim specialist proposals to fit within token budget.

    Keeps all proposals but truncates each proportionally to fit.

    Args:
        proposals: List of specialist proposals
        max_tokens: Maximum tokens for all proposals combined

    Returns:
        List of trimmed proposals
    """
    if not proposals:
        return proposals

    # Calculate current total
    current_tokens = sum(TokenBudgetManager.estimate_tokens(p) for p in proposals)

    if current_tokens <= max_tokens:
        return proposals  # No trimming needed

    # Trim each proposal proportionally
    tokens_per_proposal = max_tokens // len(proposals)

    trimmed = []
    for proposal in proposals:
        trimmed_prop = TokenBudgetManager.trim_to_budget(
            proposal,
            tokens_per_proposal,
            preserve_end=False  # Keep beginning with key arguments
        )
        trimmed.append(trimmed_prop)

    logger.warning(
        f"Trimmed {len(proposals)} proposals from {current_tokens} to ~{max_tokens} tokens"
    )

    return trimmed
