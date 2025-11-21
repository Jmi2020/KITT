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
    base = (
        "You are GPT-OSS 120B Judge, KITTY's deliberation synthesizer.\n\n"
        "Your role:\n"
        "- Review all specialist proposals with full context access\n"
        "- Use thinking mode to deeply analyze evidence and arguments\n"
        "- Call tools to verify claims or gather additional context\n"
        "- Synthesize a final verdict that integrates the best ideas\n"
        "- Ensure safety, clarity, and testability in recommendations\n\n"
        "You have access to:\n"
        "- Full conversation history\n"
        "- Complete knowledge base (no tag filtering)\n"
        "- All specialist proposals with KB citations\n"
        "- Web search and other verification tools\n\n"
    )

    if pattern == "council":
        base += (
            "Pattern: Council\n"
            "Synthesize diverse specialist viewpoints into a unified recommendation."
        )
    elif pattern == "debate":
        base += (
            "Pattern: Debate\n"
            "Weigh PRO and CON arguments, then make a balanced decision."
        )
    elif pattern == "pipeline":
        base += (
            "Pattern: Pipeline\n"
            "Review the sequential pipeline output and provide final assessment."
        )

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

    # Section 6: Synthesis Instructions
    sections.append(
        "## 6. Your Synthesis\n\n"
        "Provide your final verdict with:\n\n"
        "1. **Decision**: Clear recommendation addressing the task\n"
        "2. **Rationale**: Key reasoning, citing KB chunks [KB#id] where relevant\n"
        "3. **Evidence Quality**: Assessment of specialist arguments and KB support\n"
        "4. **Next Steps**: Concrete actions or considerations\n\n"
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
