"""
Integration layer between ParallelTaskManager and BrainOrchestrator.

Provides feature-flagged routing that can use either:
1. Parallel multi-agent orchestration (for complex multi-step goals)
2. Traditional sequential routing (fallback)

Similar pattern to LangGraphRoutingIntegration for consistency.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from brain.routing.router import RoutingRequest

from .parallel_manager import ParallelTaskManager, get_task_manager

logger = logging.getLogger("brain.parallel.integration")


# Keywords that suggest a complex, multi-step goal
PARALLEL_TRIGGER_KEYWORDS = [
    "research and",
    "design and",
    "create and",
    "build and",
    "analyze and",
    "compare",
    "evaluate multiple",
    "step by step",
    "comprehensive",
    "thorough analysis",
    "in-depth",
    "detailed report",
    "multiple sources",
    "investigate",
]

# Keywords that suggest a simple, single-step query
SIMPLE_QUERY_KEYWORDS = [
    "what is",
    "how do i",
    "explain",
    "define",
    "list",
    "show me",
    "tell me about",
    "hello",
    "hi",
    "thanks",
]


@dataclass
class ParallelExecutionResult:
    """Result from parallel agent execution."""
    response: str
    voice_summary: Optional[str]
    tasks: list
    metrics: Dict[str, Any]
    execution_log: list

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "response": self.response,
            "voice_summary": self.voice_summary,
            "tasks": self.tasks,
            "metrics": self.metrics,
            "execution_log": self.execution_log,
        }


class ParallelAgentIntegration:
    """
    Feature-flagged integration for parallel multi-agent orchestration.

    Falls back to traditional router if parallel execution is disabled,
    not appropriate for the query, or fails.

    Usage:
        integration = ParallelAgentIntegration()

        if await integration.should_use_parallel(prompt, conversation_id):
            result = await integration.execute_parallel(goal=prompt)
        else:
            # Use traditional routing
            ...
    """

    def __init__(
        self,
        task_manager: Optional[ParallelTaskManager] = None,
    ) -> None:
        """
        Initialize parallel agent integration.

        Args:
            task_manager: Custom task manager (uses global singleton if None)
        """
        self._task_manager = task_manager

        # Feature flag
        self.enabled = os.getenv("ENABLE_PARALLEL_AGENTS", "false").lower() == "true"

        # Rollout percentage (0-100)
        self.rollout_percent = int(os.getenv("PARALLEL_AGENT_ROLLOUT_PERCENT", "0"))

        # Complexity threshold (0.0-1.0) - higher = more complex queries trigger parallel
        self.complexity_threshold = float(os.getenv("PARALLEL_AGENT_COMPLEXITY_THRESHOLD", "0.6"))

        # Max tasks per execution
        self.max_tasks = int(os.getenv("PARALLEL_AGENT_MAX_TASKS", "6"))

        if self.enabled:
            logger.info(
                f"Parallel agent orchestration enabled "
                f"(rollout: {self.rollout_percent}%, threshold: {self.complexity_threshold})"
            )
        else:
            logger.info("Parallel agent orchestration disabled")

    @property
    def task_manager(self) -> ParallelTaskManager:
        """Get or create task manager."""
        if self._task_manager is None:
            self._task_manager = get_task_manager()
        return self._task_manager

    def _estimate_complexity(self, prompt: str) -> float:
        """
        Estimate query complexity to determine if parallel execution is beneficial.

        Returns:
            Float between 0.0 (simple) and 1.0 (complex)
        """
        prompt_lower = prompt.lower()
        score = 0.0

        # Check for parallel trigger keywords
        for keyword in PARALLEL_TRIGGER_KEYWORDS:
            if keyword in prompt_lower:
                score += 0.2

        # Check for simple query patterns
        for keyword in SIMPLE_QUERY_KEYWORDS:
            if prompt_lower.startswith(keyword):
                score -= 0.3

        # Length-based heuristic (longer prompts often more complex)
        word_count = len(prompt.split())
        if word_count > 50:
            score += 0.2
        elif word_count > 100:
            score += 0.3
        elif word_count < 10:
            score -= 0.2

        # Multiple questions indicator
        question_count = prompt.count("?")
        if question_count > 1:
            score += 0.15 * question_count

        # "And" conjunction suggests multi-part request
        and_count = len(re.findall(r'\band\b', prompt_lower))
        if and_count >= 2:
            score += 0.2

        # Numbered list suggests multi-step
        if re.search(r'\b(1\.|first|a\))', prompt_lower):
            score += 0.2

        return max(0.0, min(1.0, score))

    async def should_use_parallel(
        self,
        prompt: str,
        conversation_id: Optional[str] = None,
        force: bool = False,
    ) -> bool:
        """
        Determine if this request should use parallel agent orchestration.

        Args:
            prompt: User prompt/goal
            conversation_id: Optional conversation ID for rollout consistency
            force: If True, bypass complexity check

        Returns:
            True if should use parallel orchestration, False otherwise
        """
        if not self.enabled:
            return False

        # Rollout logic (hash-based for consistency)
        if self.rollout_percent < 100:
            if conversation_id:
                hash_val = hash(conversation_id) % 100
            else:
                hash_val = hash(prompt) % 100

            if hash_val >= self.rollout_percent:
                logger.debug(f"Rollout check failed ({hash_val} >= {self.rollout_percent})")
                return False

        # Force flag bypasses complexity check
        if force:
            return True

        # Complexity estimation
        complexity = self._estimate_complexity(prompt)
        logger.debug(f"Estimated complexity: {complexity:.2f} (threshold: {self.complexity_threshold})")

        if complexity < self.complexity_threshold:
            logger.debug("Query too simple for parallel execution")
            return False

        return True

    async def execute_parallel(
        self,
        goal: str,
        context: Optional[Dict[str, Any]] = None,
        include_voice_summary: bool = True,
    ) -> ParallelExecutionResult:
        """
        Execute goal using parallel multi-agent orchestration.

        Args:
            goal: The complex goal to accomplish
            context: Optional context (conversation history, etc.)
            include_voice_summary: Whether to generate TTS-friendly summary

        Returns:
            ParallelExecutionResult with response, metrics, etc.

        Raises:
            Exception: If parallel execution fails
        """
        logger.info(f"Starting parallel execution for: {goal[:100]}...")

        try:
            result = await self.task_manager.execute_goal(
                goal=goal,
                context=context,
                max_tasks=self.max_tasks,
                include_summary=include_voice_summary,
            )

            return ParallelExecutionResult(
                response=result["final_output"],
                voice_summary=result.get("voice_summary"),
                tasks=result["tasks"],
                metrics=result["metrics"],
                execution_log=result["execution_log"],
            )

        except Exception as e:
            logger.error(f"Parallel execution failed: {e}", exc_info=True)
            raise

    def get_status(self) -> Dict[str, Any]:
        """Get current integration status."""
        return {
            "enabled": self.enabled,
            "rollout_percent": self.rollout_percent,
            "complexity_threshold": self.complexity_threshold,
            "max_tasks": self.max_tasks,
            "task_manager_status": self.task_manager.get_status() if self._task_manager else None,
        }


# Singleton instance
_parallel_integration: Optional[ParallelAgentIntegration] = None


def get_parallel_integration() -> ParallelAgentIntegration:
    """Get or create the global parallel integration instance."""
    global _parallel_integration
    if _parallel_integration is None:
        _parallel_integration = ParallelAgentIntegration()
    return _parallel_integration


async def reset_parallel_integration() -> None:
    """Reset the global integration (for testing)."""
    global _parallel_integration
    _parallel_integration = None
