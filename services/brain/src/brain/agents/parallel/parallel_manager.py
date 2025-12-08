"""
High-performance parallel task manager for multi-agent orchestration.

Provides the core decompose → parallel execute → synthesize pipeline:
1. Decompose: Break complex goals into parallelizable subtasks
2. Execute: Run independent tasks concurrently across specialized agents
3. Synthesize: Combine results into coherent final output

Features:
- Slot-aware resource management
- Dependency graph resolution via topological sort
- Automatic fallback to secondary tiers
- Comprehensive metrics collection
- Fail-soft partial execution
"""

import asyncio
import json
import logging
import os
import re
import time
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from .types import (
    AgentExecutionMetrics,
    KittyTask,
    ModelTier,
    TaskStatus,
)
from .registry import KITTY_AGENTS, KittyAgent, get_agent
from .llm_adapter import ParallelLLMClient, get_parallel_client

logger = logging.getLogger("brain.parallel.manager")


class ParallelTaskManager:
    """
    High-performance task orchestration with parallel execution.

    Features:
    - Concurrent execution of independent tasks
    - Slot-aware load balancing across endpoints
    - Dependency graph resolution
    - Automatic retries with fallback tiers
    - Comprehensive metrics collection

    Usage:
        manager = ParallelTaskManager()
        result = await manager.execute_goal(
            goal="Research quantum computing and write a Python simulation",
            max_tasks=6,
        )
        print(result["final_output"])
        print(result["metrics"])
    """

    def __init__(
        self,
        agents: Optional[Dict[str, KittyAgent]] = None,
        llm_client: Optional[ParallelLLMClient] = None,
        max_parallel: int = 8,
    ):
        """
        Initialize the parallel task manager.

        Args:
            agents: Custom agent registry (uses KITTY_AGENTS if None)
            llm_client: Custom LLM client (uses global singleton if None)
            max_parallel: Maximum concurrent tasks
        """
        self.agents = agents or KITTY_AGENTS
        self.llm = llm_client or get_parallel_client()
        self.max_parallel = int(os.getenv("PARALLEL_AGENT_MAX_CONCURRENT", str(max_parallel)))

        self._semaphore = asyncio.Semaphore(self.max_parallel)
        self._tasks: Dict[str, KittyTask] = {}
        self._execution_log: List[Dict] = []

    def _log(self, message: str, level: str = "info") -> None:
        """Structured logging with timestamp."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message": message,
            "level": level,
        }
        self._execution_log.append(entry)
        getattr(logger, level)(message)

    async def execute_goal(
        self,
        goal: str,
        context: Optional[Dict[str, Any]] = None,
        max_tasks: int = 6,
        include_summary: bool = True,
    ) -> Dict[str, Any]:
        """
        Full pipeline: decompose → parallel execute → synthesize.

        Args:
            goal: The complex goal to accomplish
            context: Optional context (conversation history, files, etc.)
            max_tasks: Maximum number of subtasks to create
            include_summary: Whether to create voice-friendly summary

        Returns:
            Dict with keys:
            - goal: Original goal
            - tasks: List of task dicts with results
            - task_results: Dict mapping task_id to result string
            - final_output: Synthesized final answer
            - voice_summary: Optional TTS-friendly summary
            - metrics: AgentExecutionMetrics dict
            - execution_log: List of log entries
        """
        start_time = time.perf_counter()
        self._execution_log = []
        self._tasks = {}

        self._log(f"Starting parallel execution for: {goal[:100]}...")

        # Phase 1: Decomposition
        tasks = await self.decompose_goal(goal, max_tasks)

        # Phase 2: Parallel Execution
        results = await self.execute_parallel(tasks, context)

        # Phase 3: Synthesis
        final_output = await self.synthesize(goal, results)

        # Phase 4: Optional Voice Summary
        voice_summary = None
        if include_summary:
            voice_summary = await self._create_voice_summary(final_output)

        # Calculate metrics
        total_time = time.perf_counter() - start_time
        parallel_batches = self._count_parallel_batches(tasks)
        metrics = AgentExecutionMetrics.from_tasks(
            goal=goal,
            tasks=tasks,
            total_time=total_time,
            parallel_batches=parallel_batches,
        )

        self._log(
            f"Completed in {total_time:.1f}s "
            f"({metrics.total_tokens} tokens, {parallel_batches} batches)"
        )

        return {
            "goal": goal,
            "tasks": [t.to_dict() for t in tasks],
            "task_results": results,
            "final_output": final_output,
            "voice_summary": voice_summary,
            "metrics": metrics.to_dict(),
            "execution_log": self._execution_log,
        }

    async def decompose_goal(
        self,
        goal: str,
        max_tasks: int = 6,
    ) -> List[KittyTask]:
        """
        Decompose a complex goal into parallelizable subtasks.

        Uses Q4 for fast decomposition and creates a dependency graph.

        Args:
            goal: The goal to decompose
            max_tasks: Maximum subtasks to create

        Returns:
            List of KittyTask objects with dependencies
        """
        self._log(f"Decomposing goal into {max_tasks} tasks")

        # Build agent descriptions for the decomposer
        agent_descriptions = "\n".join([
            f"- {name}: {agent.expertise}"
            for name, agent in self.agents.items()
        ])

        prompt = f"""Decompose this goal into {max_tasks} or fewer specific subtasks.
Maximize parallelism by minimizing dependencies where possible.
Assign each task to the most appropriate agent.

Goal: {goal}

Available agents:
{agent_descriptions}

Rules:
1. Tasks with no dependencies can run in parallel
2. Only add dependencies if output is truly required
3. Use 'reasoner' for final synthesis tasks
4. Use 'researcher' for any web lookups
5. Use 'coder' for code generation tasks
6. Use 'cad_designer' for 3D model creation
7. Use 'fabricator' for printing/manufacturing
8. Use 'vision_analyst' for image analysis
9. Use 'analyst' for data/metrics analysis
10. Use 'summarizer' for compression

Respond with ONLY a JSON array:
[
  {{"id": "task_1", "description": "...", "assigned_to": "researcher", "dependencies": []}},
  {{"id": "task_2", "description": "...", "assigned_to": "coder", "dependencies": []}},
  {{"id": "task_3", "description": "...", "assigned_to": "reasoner", "dependencies": ["task_1", "task_2"]}}
]"""

        try:
            response, _ = await self.llm.generate(
                tier=ModelTier.Q4_TOOLS,
                prompt=prompt,
                system_prompt="You are a task planning expert. Output valid JSON only.",
                max_tokens=1024,
                temperature=0.3,
            )

            tasks = self._parse_tasks(response, goal)
        except Exception as e:
            self._log(f"Decomposition failed: {e}", "error")
            tasks = self._create_fallback_tasks(goal)

        # Log task graph
        for task in tasks:
            deps = f" (needs: {', '.join(task.dependencies)})" if task.dependencies else " (parallel)"
            self._log(f"  Task {task.id}: {task.description[:50]}... -> {task.assigned_to}{deps}")

        return tasks

    def _parse_tasks(self, response: str, goal: str) -> List[KittyTask]:
        """Parse JSON tasks from LLM response with fallback."""
        try:
            # Find JSON array in response
            match = re.search(r'\[\s*\{.*?\}\s*\]', response, re.DOTALL)
            if match:
                tasks_data = json.loads(match.group())
            else:
                raise ValueError("No JSON array found")
        except (json.JSONDecodeError, ValueError) as e:
            self._log(f"JSON parse failed, using fallback: {e}", "warning")
            return self._create_fallback_tasks(goal)

        tasks = []
        for data in tasks_data[:6]:  # Max 6 tasks
            agent_name = data.get("assigned_to", "researcher")
            if agent_name not in self.agents:
                agent_name = "researcher"  # Default fallback

            task = KittyTask(
                id=data.get("id", f"task_{len(tasks) + 1}"),
                description=data.get("description", goal),
                assigned_to=agent_name,
                dependencies=data.get("dependencies", []),
            )
            self._tasks[task.id] = task
            tasks.append(task)

        return tasks

    def _create_fallback_tasks(self, goal: str) -> List[KittyTask]:
        """Default task structure when LLM parsing fails."""
        goal_lower = goal.lower()

        if any(kw in goal_lower for kw in ["code", "implement", "program", "script"]):
            tasks_data = [
                {"id": "task_1", "description": f"Research best practices for: {goal}",
                 "assigned_to": "researcher", "dependencies": []},
                {"id": "task_2", "description": f"Implement code solution for: {goal}",
                 "assigned_to": "coder", "dependencies": []},
                {"id": "task_3", "description": "Synthesize research and code into final answer",
                 "assigned_to": "reasoner", "dependencies": ["task_1", "task_2"]},
            ]
        elif any(kw in goal_lower for kw in ["design", "cad", "model", "print", "3d"]):
            tasks_data = [
                {"id": "task_1", "description": f"Search for reference designs: {goal}",
                 "assigned_to": "researcher", "dependencies": []},
                {"id": "task_2", "description": f"Generate CAD model for: {goal}",
                 "assigned_to": "cad_designer", "dependencies": ["task_1"]},
                {"id": "task_3", "description": "Analyze printability and recommend settings",
                 "assigned_to": "fabricator", "dependencies": ["task_2"]},
            ]
        else:
            tasks_data = [
                {"id": "task_1", "description": f"Research: {goal}",
                 "assigned_to": "researcher", "dependencies": []},
                {"id": "task_2", "description": "Analyze and structure findings",
                 "assigned_to": "analyst", "dependencies": ["task_1"]},
                {"id": "task_3", "description": "Synthesize into comprehensive answer",
                 "assigned_to": "reasoner", "dependencies": ["task_2"]},
            ]

        tasks = []
        for data in tasks_data:
            task = KittyTask(
                id=data["id"],
                description=data["description"],
                assigned_to=data["assigned_to"],
                dependencies=data["dependencies"],
            )
            self._tasks[task.id] = task
            tasks.append(task)

        return tasks

    async def execute_parallel(
        self,
        tasks: List[KittyTask],
        context: Optional[Dict[str, str]] = None,
    ) -> Dict[str, str]:
        """
        Execute tasks with maximum parallelism respecting dependencies.

        Uses topological sort + concurrent execution of independent tasks.

        Args:
            tasks: List of tasks to execute
            context: Optional initial context

        Returns:
            Dict mapping task_id to result string
        """
        self._log(f"Executing {len(tasks)} tasks with parallel orchestration")

        results: Dict[str, str] = context.copy() if context else {}
        completed: Set[str] = set(results.keys())
        pending = {t.id: t for t in tasks if t.id not in completed}

        batch_num = 0
        while pending:
            batch_num += 1

            # Find all tasks whose dependencies are satisfied
            ready = [
                task for task in pending.values()
                if all(dep in completed for dep in task.dependencies)
            ]

            if not ready:
                # Check for circular dependencies
                self._log("No ready tasks - possible circular dependency", "warning")
                break

            self._log(f"  Batch {batch_num}: {[t.id for t in ready]}")

            # Execute ready tasks in parallel
            batch_results = await asyncio.gather(
                *[self._execute_single_task(task, results) for task in ready],
                return_exceptions=True,
            )

            # Process results
            for task, result in zip(ready, batch_results):
                if isinstance(result, Exception):
                    task.mark_failed(str(result))
                    self._log(f"  Task {task.id} failed: {result}", "error")
                    results[task.id] = f"[Task failed: {result}]"
                else:
                    results[task.id] = result

                completed.add(task.id)
                del pending[task.id]

        return results

    async def _execute_single_task(
        self,
        task: KittyTask,
        context: Dict[str, str],
    ) -> str:
        """Execute a single task with the assigned agent."""
        async with self._semaphore:  # Limit overall concurrency
            task.mark_started()

            agent = self.agents.get(task.assigned_to)
            if not agent:
                agent = self.agents.get("researcher")  # Fallback
                self._log(f"Unknown agent {task.assigned_to}, using researcher", "warning")

            # Build context from dependencies
            context_parts = []
            for dep_id in task.dependencies:
                if dep_id in context:
                    # Truncate long results
                    dep_result = context[dep_id][:1500]
                    context_parts.append(f"### {dep_id} result:\n{dep_result}")

            context_str = "\n\n".join(context_parts) if context_parts else ""

            prompt = f"""{task.description}

{f'Context from previous tasks:{chr(10)}{context_str}' if context_str else ''}

Provide a thorough, actionable response:"""

            try:
                result, metadata = await self.llm.generate_for_agent(
                    agent=agent,
                    prompt=prompt,
                    context="",  # Context already in prompt
                )

                task.mark_completed(
                    result=result,
                    model=metadata.get("model", ""),
                    tokens=metadata.get("tokens", 0),
                )
                task.tokens_prompt = metadata.get("tokens_prompt", 0)
                task.fallback_used = metadata.get("fallback_used", False)

                self._log(
                    f"  Task {task.id} completed in {task.latency_ms}ms "
                    f"({task.tokens_used} tokens via {agent.primary_tier.value})"
                )

                return result

            except Exception as e:
                task.mark_failed(str(e))
                raise

    async def synthesize(
        self,
        goal: str,
        results: Dict[str, str],
        use_deep_reasoning: bool = True,
    ) -> str:
        """
        Synthesize all task results into coherent final output.

        Uses GPTOSS 120B with thinking mode for best quality.

        Args:
            goal: Original goal
            results: Dict of task_id -> result
            use_deep_reasoning: Whether to use GPTOSS (True) or Q4 (False)

        Returns:
            Synthesized final answer
        """
        self._log("Synthesizing results with deep reasoning...")

        # Build results summary
        results_text = "\n\n".join([
            f"### {task_id}\n{result[:2000]}"
            for task_id, result in results.items()
        ])

        prompt = f"""Synthesize these task results into one comprehensive, actionable answer.

## Original Goal
{goal}

## Task Results
{results_text}

## Instructions
1. Integrate all findings into a coherent response
2. Resolve any contradictions between sources
3. Highlight key insights and recommendations
4. Structure for clarity (use headers if helpful)
5. Be thorough but concise

## Final Answer"""

        tier = ModelTier.GPTOSS_REASON if use_deep_reasoning else ModelTier.Q4_TOOLS

        result, metadata = await self.llm.generate(
            tier=tier,
            prompt=prompt,
            system_prompt="You are KITTY's synthesis agent. Create unified, insightful responses.",
            max_tokens=4096,
            temperature=0.5,
        )

        self._log(f"Synthesis complete ({metadata.get('latency_ms', 0)}ms)")

        return result

    async def _create_voice_summary(self, full_output: str) -> str:
        """Create TTS-friendly summary using Hermes 8B."""
        try:
            result, _ = await self.llm.generate(
                tier=ModelTier.SUMMARY,
                prompt=f"Summarize this for voice output (2-3 sentences, conversational):\n\n{full_output[:3000]}",
                system_prompt="Create brief, natural summaries suitable for text-to-speech.",
                max_tokens=256,
                temperature=0.4,
            )
            return result
        except Exception as e:
            self._log(f"Voice summary failed: {e}", "warning")
            return ""

    def _count_parallel_batches(self, tasks: List[KittyTask]) -> int:
        """Count how many parallel execution batches were needed."""
        completed: Set[str] = set()
        batches = 0
        remaining = set(t.id for t in tasks)

        while remaining:
            ready = {
                tid for tid in remaining
                if all(dep in completed for dep in self._tasks[tid].dependencies)
            }
            if not ready:
                break
            completed.update(ready)
            remaining -= ready
            batches += 1

        return batches

    def get_status(self) -> Dict[str, Any]:
        """Get current execution status."""
        return {
            "tasks": {tid: t.to_dict() for tid, t in self._tasks.items()},
            "slots": self.llm.get_slot_status(),
            "log": self._execution_log,
        }

    async def close(self) -> None:
        """Close resources."""
        await self.llm.close()


# Singleton instance
_task_manager: Optional[ParallelTaskManager] = None


def get_task_manager() -> ParallelTaskManager:
    """Get or create the global task manager instance."""
    global _task_manager
    if _task_manager is None:
        _task_manager = ParallelTaskManager()
    return _task_manager


async def reset_task_manager() -> None:
    """Reset the global task manager (for testing)."""
    global _task_manager
    if _task_manager:
        await _task_manager.close()
    _task_manager = None
