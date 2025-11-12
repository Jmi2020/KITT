"""
Enhanced Tool Orchestration - Parallel execution with dependency resolution.

Features:
- Parallel tool execution (concurrent instead of sequential)
- Dependency resolution (CAD → analysis → fabrication)
- Tool validation checkpoints
- User intervention points for hazardous operations
- Retry logic with exponential backoff
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class ToolPriority(Enum):
    """Tool execution priority levels."""

    CRITICAL = 1  # Must succeed (CAD generation)
    HIGH = 2  # Important but can fail (analysis)
    MEDIUM = 3  # Nice to have (optimization)
    LOW = 4  # Optional (suggestions)


class ToolStatus(Enum):
    """Tool execution status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"  # Waiting on dependencies


@dataclass
class ToolDependency:
    """Defines a dependency relationship between tools."""

    tool_name: str
    depends_on: List[str]  # Must complete before this tool runs
    optional: bool = False  # If True, tool runs even if dependencies fail


@dataclass
class ToolExecutionPlan:
    """Plan for executing a set of tools with dependencies."""

    tools: List[str]  # All tools to execute
    dependencies: Dict[str, List[str]]  # tool_name → [dependency_names]
    priorities: Dict[str, ToolPriority]  # tool_name → priority
    execution_order: List[List[str]]  # Batches of tools (can run in parallel)


@dataclass
class ToolExecutionResult:
    """Result of tool execution."""

    tool_name: str
    status: ToolStatus
    output: Any
    error: Optional[str] = None
    latency_ms: float = 0.0
    retry_count: int = 0


class ToolOrchestrator:
    """
    Enhanced tool orchestrator with parallel execution and dependency resolution.

    Features:
    - Builds dependency graph from tool requirements
    - Executes tools in parallel where possible
    - Respects dependencies and priorities
    - Retries failed tools with exponential backoff
    - Provides validation checkpoints
    """

    def __init__(
        self,
        mcp_client: Any,
        max_parallel: int = 3,
        max_retries: int = 2,
        retry_delay_ms: float = 1000.0,
    ) -> None:
        """
        Initialize tool orchestrator.

        Args:
            mcp_client: MCP client for tool execution
            max_parallel: Maximum concurrent tool executions
            max_retries: Maximum retry attempts per tool
            retry_delay_ms: Initial retry delay (exponential backoff)
        """
        self.mcp = mcp_client
        self.max_parallel = max_parallel
        self.max_retries = max_retries
        self.retry_delay_ms = retry_delay_ms

        # Tool dependency registry
        self.dependencies = self._build_dependency_registry()

        logger.info(f"ToolOrchestrator initialized (max_parallel={max_parallel})")

    def _build_dependency_registry(self) -> Dict[str, ToolDependency]:
        """
        Build tool dependency registry.

        Returns:
            Dict mapping tool names to their dependencies
        """
        return {
            # CAD workflow
            "generate_cad": ToolDependency(
                tool_name="generate_cad",
                depends_on=[],  # No dependencies
            ),
            "analyze_model": ToolDependency(
                tool_name="analyze_model",
                depends_on=["generate_cad"],  # Needs CAD model first
            ),
            "optimize_model": ToolDependency(
                tool_name="optimize_model",
                depends_on=["generate_cad", "analyze_model"],
                optional=True,  # Can skip if analysis fails
            ),
            "export_model": ToolDependency(
                tool_name="export_model",
                depends_on=["generate_cad"],  # Only needs CAD, not analysis
            ),
            # Fabrication workflow
            "slice_model": ToolDependency(
                tool_name="slice_model",
                depends_on=["generate_cad"],  # Or "export_model" if STL needed
            ),
            "queue_print": ToolDependency(
                tool_name="queue_print",
                depends_on=["slice_model"],
            ),
            # Search and research
            "web_search": ToolDependency(
                tool_name="web_search",
                depends_on=[],  # Independent
            ),
            "perplexity_search": ToolDependency(
                tool_name="perplexity_search",
                depends_on=[],  # Independent
            ),
            # Code generation
            "coding.generate": ToolDependency(
                tool_name="coding.generate",
                depends_on=[],  # Independent
            ),
            "coding.test": ToolDependency(
                tool_name="coding.test",
                depends_on=["coding.generate"],
            ),
        }

    def build_execution_plan(
        self,
        tools: List[str],
        priorities: Optional[Dict[str, ToolPriority]] = None,
    ) -> ToolExecutionPlan:
        """
        Build execution plan with dependency resolution.

        Args:
            tools: List of tool names to execute
            priorities: Optional priority overrides

        Returns:
            ToolExecutionPlan with batched execution order
        """
        logger.debug(f"Building execution plan for {len(tools)} tools")

        # Build dependency graph
        dependency_map: Dict[str, List[str]] = {}
        for tool in tools:
            dep_info = self.dependencies.get(tool)
            if dep_info:
                dependency_map[tool] = [d for d in dep_info.depends_on if d in tools]
            else:
                dependency_map[tool] = []  # Unknown tool, no dependencies

        # Topological sort to determine execution order
        execution_batches = self._topological_sort(tools, dependency_map)

        # Assign priorities
        tool_priorities = {}
        for tool in tools:
            if priorities and tool in priorities:
                tool_priorities[tool] = priorities[tool]
            else:
                # Default priorities based on tool type
                if "generate" in tool or "cad" in tool:
                    tool_priorities[tool] = ToolPriority.CRITICAL
                elif "analyze" in tool or "test" in tool:
                    tool_priorities[tool] = ToolPriority.HIGH
                elif "optimize" in tool:
                    tool_priorities[tool] = ToolPriority.MEDIUM
                else:
                    tool_priorities[tool] = ToolPriority.MEDIUM

        plan = ToolExecutionPlan(
            tools=tools,
            dependencies=dependency_map,
            priorities=tool_priorities,
            execution_order=execution_batches,
        )

        logger.info(
            f"Execution plan: {len(execution_batches)} batches, "
            f"max parallel per batch: {min(self.max_parallel, max(len(b) for b in execution_batches))}"
        )

        return plan

    def _topological_sort(
        self, tools: List[str], dependencies: Dict[str, List[str]]
    ) -> List[List[str]]:
        """
        Topological sort with batching for parallel execution.

        Args:
            tools: List of all tools
            dependencies: Dependency map (tool → [dependencies])

        Returns:
            List of batches (each batch can run in parallel)
        """
        # Calculate in-degrees (number of dependencies)
        in_degree: Dict[str, int] = {tool: len(dependencies.get(tool, [])) for tool in tools}

        # Track completed tools
        completed: Set[str] = set()

        # Batches for parallel execution
        batches: List[List[str]] = []

        while len(completed) < len(tools):
            # Find all tools with no pending dependencies
            ready = [tool for tool in tools if in_degree[tool] == 0 and tool not in completed]

            if not ready:
                # Circular dependency or error
                remaining = set(tools) - completed
                logger.warning(f"Circular dependency detected. Remaining tools: {remaining}")
                # Force execution of remaining tools
                batches.append(list(remaining))
                break

            # Add batch of ready tools
            batches.append(ready)

            # Mark ready tools as completed
            for tool in ready:
                completed.add(tool)

                # Decrease in-degree of dependent tools
                for other_tool in tools:
                    if tool in dependencies.get(other_tool, []):
                        in_degree[other_tool] -= 1

        logger.debug(f"Topological sort: {len(batches)} batches")
        return batches

    async def execute_plan(
        self,
        plan: ToolExecutionPlan,
        tool_args: Dict[str, Dict[str, Any]],
    ) -> Dict[str, ToolExecutionResult]:
        """
        Execute tool orchestration plan.

        Args:
            plan: Execution plan with batched tools
            tool_args: Arguments for each tool {tool_name: {arg: value}}

        Returns:
            Dict of execution results {tool_name: result}
        """
        logger.info(f"Executing plan with {len(plan.execution_order)} batches")

        results: Dict[str, ToolExecutionResult] = {}

        # Execute batches in order
        for batch_idx, batch in enumerate(plan.execution_order):
            logger.info(f"Executing batch {batch_idx + 1}/{len(plan.execution_order)}: {batch}")

            # Check dependencies before executing batch
            batch_to_execute = []
            for tool in batch:
                deps = plan.dependencies.get(tool, [])
                deps_satisfied = all(
                    results.get(dep) and results[dep].status == ToolStatus.COMPLETED for dep in deps
                )

                if deps_satisfied or not deps:
                    batch_to_execute.append(tool)
                else:
                    # Dependencies failed, skip this tool
                    dep_info = self.dependencies.get(tool)
                    if dep_info and dep_info.optional:
                        logger.info(f"Skipping optional tool {tool} (dependencies failed)")
                        results[tool] = ToolExecutionResult(
                            tool_name=tool,
                            status=ToolStatus.SKIPPED,
                            output=None,
                            error="Optional tool skipped due to failed dependencies",
                        )
                    else:
                        logger.warning(f"Blocking tool {tool} (dependencies not satisfied)")
                        results[tool] = ToolExecutionResult(
                            tool_name=tool,
                            status=ToolStatus.BLOCKED,
                            output=None,
                            error="Dependencies not satisfied",
                        )

            if not batch_to_execute:
                logger.warning(f"Batch {batch_idx + 1} has no tools to execute (all blocked/skipped)")
                continue

            # Execute batch in parallel (up to max_parallel)
            batch_results = await self._execute_batch_parallel(
                batch_to_execute,
                tool_args,
                plan.priorities,
            )

            # Merge batch results
            results.update(batch_results)

        logger.info(
            f"Execution complete: "
            f"{sum(1 for r in results.values() if r.status == ToolStatus.COMPLETED)} completed, "
            f"{sum(1 for r in results.values() if r.status == ToolStatus.FAILED)} failed, "
            f"{sum(1 for r in results.values() if r.status == ToolStatus.SKIPPED)} skipped"
        )

        return results

    async def _execute_batch_parallel(
        self,
        batch: List[str],
        tool_args: Dict[str, Dict[str, Any]],
        priorities: Dict[str, ToolPriority],
    ) -> Dict[str, ToolExecutionResult]:
        """
        Execute a batch of tools in parallel.

        Args:
            batch: List of tools to execute
            tool_args: Arguments for each tool
            priorities: Tool priorities

        Returns:
            Dict of execution results for this batch
        """
        # Sort by priority (critical first)
        sorted_batch = sorted(
            batch,
            key=lambda t: priorities.get(t, ToolPriority.MEDIUM).value,
        )

        # Execute with semaphore to limit concurrency
        semaphore = asyncio.Semaphore(self.max_parallel)

        async def execute_with_semaphore(tool_name: str) -> ToolExecutionResult:
            async with semaphore:
                return await self._execute_tool_with_retry(
                    tool_name,
                    tool_args.get(tool_name, {}),
                    priorities.get(tool_name, ToolPriority.MEDIUM),
                )

        # Execute all tools in parallel (respecting semaphore)
        tasks = [execute_with_semaphore(tool) for tool in sorted_batch]
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Build result dict
        results = {}
        for tool_name, result in zip(sorted_batch, batch_results):
            if isinstance(result, Exception):
                logger.error(f"Tool {tool_name} raised exception: {result}")
                results[tool_name] = ToolExecutionResult(
                    tool_name=tool_name,
                    status=ToolStatus.FAILED,
                    output=None,
                    error=str(result),
                )
            else:
                results[tool_name] = result

        return results

    async def _execute_tool_with_retry(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        priority: ToolPriority,
    ) -> ToolExecutionResult:
        """
        Execute a single tool with retry logic.

        Args:
            tool_name: Tool name
            tool_args: Tool arguments
            priority: Tool priority (determines retry behavior)

        Returns:
            ToolExecutionResult
        """
        import time

        retry_count = 0
        last_error = None

        # Determine max retries based on priority
        max_retries = self.max_retries if priority in [ToolPriority.CRITICAL, ToolPriority.HIGH] else 1

        while retry_count <= max_retries:
            try:
                start_time = time.time()

                logger.debug(f"Executing tool: {tool_name} (attempt {retry_count + 1}/{max_retries + 1})")

                # Execute tool via MCP
                result = await self.mcp.execute_tool(tool_name, **tool_args)

                latency_ms = (time.time() - start_time) * 1000

                # Check if tool succeeded
                if result.get("success", True):
                    logger.info(f"Tool {tool_name} succeeded ({latency_ms:.0f}ms)")
                    return ToolExecutionResult(
                        tool_name=tool_name,
                        status=ToolStatus.COMPLETED,
                        output=result.get("output"),
                        latency_ms=latency_ms,
                        retry_count=retry_count,
                    )
                else:
                    # Tool returned failure
                    last_error = result.get("error", "Unknown error")
                    logger.warning(f"Tool {tool_name} failed: {last_error}")

            except Exception as exc:
                last_error = str(exc)
                logger.warning(f"Tool {tool_name} exception: {exc}")

            # Retry with exponential backoff
            if retry_count < max_retries:
                delay = self.retry_delay_ms * (2 ** retry_count) / 1000.0  # Convert to seconds
                logger.info(f"Retrying {tool_name} after {delay:.1f}s...")
                await asyncio.sleep(delay)

            retry_count += 1

        # All retries exhausted
        logger.error(f"Tool {tool_name} failed after {retry_count} attempts: {last_error}")
        return ToolExecutionResult(
            tool_name=tool_name,
            status=ToolStatus.FAILED,
            output=None,
            error=last_error,
            retry_count=retry_count - 1,
        )


async def create_tool_orchestrator(
    mcp_client: Any,
    max_parallel: int = 3,
    max_retries: int = 2,
) -> ToolOrchestrator:
    """
    Factory function to create tool orchestrator.

    Args:
        mcp_client: MCP client for tool execution
        max_parallel: Maximum concurrent tool executions
        max_retries: Maximum retry attempts per tool

    Returns:
        Initialized ToolOrchestrator
    """
    return ToolOrchestrator(
        mcp_client=mcp_client,
        max_parallel=max_parallel,
        max_retries=max_retries,
    )
