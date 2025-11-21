"""Token budget management for collective meta-agent (Option A).

Enforces strict token budgets to keep Athene-V2 specialists within their 32k
training context limit while allowing GPT-OSS 120B judge to use full 128k context.

Architecture:
- Athene specialists: 24k prompt + 6-8k output = 30-32k total (within 32k limit)
- GPT-OSS judge: 100k prompt + 4-8k output = 104-108k total (within 128k limit)

Token Budget Breakdown (Athene):
- System prompt + persona + tools: ~4k
- Conversation summary: ~2k
- KB chunks (tagged with IDs): ~8-12k
- User query + task framing: ~2k
- Safety margin: ~2k
- Available for specialist output: ~6-8k

Token Budget Breakdown (Judge):
- System prompt + judge instructions: ~4k
- Conversation summary: ~2k
- KB chunks (full context, tagged): ~30-40k
- All specialist proposals (k=3-5): ~20-30k
- Evidence aggregation: ~10-15k
- Safety margin: ~5k
- Available for synthesis output: ~4-8k
"""

from __future__ import annotations
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class BudgetAllocation:
    """Token budget for a specific component."""
    component: str
    allocated_tokens: int
    actual_tokens: int = 0
    overflow: bool = False

    @property
    def remaining(self) -> int:
        """Remaining tokens in this budget."""
        return max(0, self.allocated_tokens - self.actual_tokens)

    @property
    def utilization(self) -> float:
        """Budget utilization as percentage."""
        if self.allocated_tokens == 0:
            return 0.0
        return (self.actual_tokens / self.allocated_tokens) * 100


@dataclass
class ModelBudget:
    """Complete token budget for a model/agent."""
    model_name: str
    total_context: int
    prompt_budget: int
    output_budget: int
    allocations: Dict[str, int]

    def __post_init__(self):
        """Validate budget doesn't exceed total context."""
        total_allocated = self.prompt_budget + self.output_budget
        if total_allocated > self.total_context:
            raise ValueError(
                f"{self.model_name}: total allocated ({total_allocated}) "
                f"exceeds context limit ({self.total_context})"
            )


class TokenBudgetManager:
    """Manages token budgets for collective meta-agent nodes.

    Provides:
    - Explicit budget allocations per component
    - Token counting (simple char/4 approximation for now)
    - Auto-trimming helpers
    - Budget enforcement and overflow detection
    """

    # Athene-V2 Agent Budget (Q4 - 32k training context)
    ATHENE_BUDGET = ModelBudget(
        model_name="Athene-V2-Agent-Q4",
        total_context=32768,
        prompt_budget=24000,  # Conservative to stay within limit
        output_budget=6000,   # Can expand to 8k if needed
        allocations={
            "system_prompt": 4000,
            "conversation_summary": 2000,
            "kb_chunks": 10000,  # Will be trimmed to fit
            "task_framing": 2000,
            "tools": 4000,       # If tools are re-enabled
            "margin": 2000,
        }
    )

    # GPT-OSS 120B Judge Budget (F16 - 128k context)
    JUDGE_BUDGET = ModelBudget(
        model_name="GPT-OSS-120B-Judge",
        total_context=131072,
        prompt_budget=100000,
        output_budget=6000,  # Can expand to 8k if needed
        allocations={
            "system_prompt": 4000,
            "conversation_summary": 2000,
            "kb_chunks": 35000,  # Full context access
            "specialist_proposals": 25000,
            "evidence_aggregation": 15000,
            "task_framing": 2000,
            "tools": 10000,
            "margin": 7000,
        }
    )

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Estimate token count for text.

        Uses simple char/4 approximation. This is conservative for English text
        and reasonably accurate for Qwen/Llama tokenizers.

        TODO: Use proper tiktoken or transformers tokenizer for exact counts.

        Args:
            text: Input text to estimate

        Returns:
            Estimated token count
        """
        if not text:
            return 0
        # Conservative estimate: 1 token ≈ 4 chars for English
        # Actual can vary (3-5 chars/token), but 4 is a safe middle ground
        return len(text) // 4

    @staticmethod
    def estimate_tokens_messages(messages: List[Dict[str, str]]) -> int:
        """Estimate tokens for a list of chat messages.

        Args:
            messages: List of message dicts with 'role' and 'content'

        Returns:
            Total estimated token count including overhead
        """
        if not messages:
            return 0

        total = 0
        for msg in messages:
            content = msg.get("content", "")
            role = msg.get("role", "")
            # Content tokens + role overhead (~4 tokens per message for formatting)
            total += TokenBudgetManager.estimate_tokens(content) + 4

        return total

    @classmethod
    def check_athene_budget(
        cls,
        system_prompt: str,
        conversation_summary: str,
        kb_chunks: str,
        task_query: str,
        tools_json: Optional[str] = None,
    ) -> Tuple[bool, List[BudgetAllocation]]:
        """Check if Athene specialist prompt fits within budget.

        Args:
            system_prompt: System prompt text
            conversation_summary: Conversation history summary
            kb_chunks: Knowledge base context chunks
            task_query: User task/query
            tools_json: Optional tools JSON (if tools enabled)

        Returns:
            (fits_budget, allocations): Boolean and list of allocations
        """
        allocations = [
            BudgetAllocation("system_prompt", cls.ATHENE_BUDGET.allocations["system_prompt"],
                           cls.estimate_tokens(system_prompt)),
            BudgetAllocation("conversation_summary", cls.ATHENE_BUDGET.allocations["conversation_summary"],
                           cls.estimate_tokens(conversation_summary)),
            BudgetAllocation("kb_chunks", cls.ATHENE_BUDGET.allocations["kb_chunks"],
                           cls.estimate_tokens(kb_chunks)),
            BudgetAllocation("task_framing", cls.ATHENE_BUDGET.allocations["task_framing"],
                           cls.estimate_tokens(task_query)),
        ]

        if tools_json:
            allocations.append(
                BudgetAllocation("tools", cls.ATHENE_BUDGET.allocations["tools"],
                               cls.estimate_tokens(tools_json))
            )

        # Check for overflows
        total_tokens = sum(a.actual_tokens for a in allocations)
        fits = total_tokens <= cls.ATHENE_BUDGET.prompt_budget

        for alloc in allocations:
            if alloc.actual_tokens > alloc.allocated_tokens:
                alloc.overflow = True

        return fits, allocations

    @classmethod
    def check_judge_budget(
        cls,
        system_prompt: str,
        conversation_summary: str,
        kb_chunks: str,
        proposals: List[str],
        task_query: str,
        tools_json: Optional[str] = None,
    ) -> Tuple[bool, List[BudgetAllocation]]:
        """Check if Judge prompt fits within budget.

        Args:
            system_prompt: System prompt text
            conversation_summary: Conversation history summary
            kb_chunks: Knowledge base context chunks (full access)
            proposals: List of specialist proposal texts
            task_query: User task/query
            tools_json: Optional tools JSON

        Returns:
            (fits_budget, allocations): Boolean and list of allocations
        """
        proposals_text = "\n\n---\n\n".join(proposals)

        allocations = [
            BudgetAllocation("system_prompt", cls.JUDGE_BUDGET.allocations["system_prompt"],
                           cls.estimate_tokens(system_prompt)),
            BudgetAllocation("conversation_summary", cls.JUDGE_BUDGET.allocations["conversation_summary"],
                           cls.estimate_tokens(conversation_summary)),
            BudgetAllocation("kb_chunks", cls.JUDGE_BUDGET.allocations["kb_chunks"],
                           cls.estimate_tokens(kb_chunks)),
            BudgetAllocation("specialist_proposals", cls.JUDGE_BUDGET.allocations["specialist_proposals"],
                           cls.estimate_tokens(proposals_text)),
            BudgetAllocation("task_framing", cls.JUDGE_BUDGET.allocations["task_framing"],
                           cls.estimate_tokens(task_query)),
        ]

        if tools_json:
            allocations.append(
                BudgetAllocation("tools", cls.JUDGE_BUDGET.allocations["tools"],
                               cls.estimate_tokens(tools_json))
            )

        total_tokens = sum(a.actual_tokens for a in allocations)
        fits = total_tokens <= cls.JUDGE_BUDGET.prompt_budget

        for alloc in allocations:
            if alloc.actual_tokens > alloc.allocated_tokens:
                alloc.overflow = True

        return fits, allocations

    @staticmethod
    def trim_to_budget(text: str, budget_tokens: int, preserve_end: bool = False) -> str:
        """Trim text to fit within token budget.

        Args:
            text: Text to trim
            budget_tokens: Maximum tokens allowed
            preserve_end: If True, keep end of text; if False, keep beginning

        Returns:
            Trimmed text
        """
        current_tokens = TokenBudgetManager.estimate_tokens(text)

        if current_tokens <= budget_tokens:
            return text

        # Calculate character budget (tokens * 4)
        char_budget = budget_tokens * 4

        if preserve_end:
            # Keep the end (useful for recent context)
            trimmed = text[-char_budget:]
            marker = "... [trimmed start] ..."
        else:
            # Keep the beginning (useful for KB chunks)
            trimmed = text[:char_budget]
            marker = "... [trimmed end] ..."

        logger.warning(
            f"Trimmed text from {current_tokens} to ~{budget_tokens} tokens "
            f"(preserve_end={preserve_end})"
        )

        return marker + "\n" + trimmed if preserve_end else trimmed + "\n" + marker

    @classmethod
    def log_budget_status(cls, allocations: List[BudgetAllocation], agent_name: str):
        """Log budget allocation status for debugging.

        Args:
            allocations: List of budget allocations
            agent_name: Name of agent (for logging)
        """
        total_actual = sum(a.actual_tokens for a in allocations)
        has_overflow = any(a.overflow for a in allocations)

        logger.info(f"=== {agent_name} Budget Status ===")
        for alloc in allocations:
            status = "⚠️ OVERFLOW" if alloc.overflow else "✓"
            logger.info(
                f"  {status} {alloc.component}: {alloc.actual_tokens}/{alloc.allocated_tokens} "
                f"({alloc.utilization:.1f}%)"
            )
        logger.info(f"  Total: {total_actual} tokens")

        if has_overflow:
            logger.warning(f"{agent_name} has budget overflows - consider trimming")


def summarize_conversation(
    messages: List[Dict[str, str]],
    max_tokens: int = 2000
) -> str:
    """Summarize conversation history to fit within token budget.

    Simple implementation: Keep most recent messages that fit within budget.
    Can be enhanced with LLM-based summarization later.

    Args:
        messages: List of message dicts
        max_tokens: Maximum tokens for summary

    Returns:
        Conversation summary text
    """
    if not messages:
        return ""

    # Simple approach: Keep most recent messages
    summary_parts = []
    current_tokens = 0

    # Reverse iterate to keep most recent
    for msg in reversed(messages):
        content = msg.get("content", "")
        role = msg.get("role", "user")
        msg_text = f"[{role}]: {content}"
        msg_tokens = TokenBudgetManager.estimate_tokens(msg_text)

        if current_tokens + msg_tokens > max_tokens:
            break

        summary_parts.insert(0, msg_text)
        current_tokens += msg_tokens

    if len(summary_parts) < len(messages):
        prefix = f"[Conversation history - showing {len(summary_parts)}/{len(messages)} recent messages]\n\n"
    else:
        prefix = "[Conversation history]\n\n"

    return prefix + "\n\n".join(summary_parts)
