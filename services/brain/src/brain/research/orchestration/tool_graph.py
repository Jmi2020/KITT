"""
Tool Dependency Graph and Wave Execution

Enables parallel execution of independent tools while respecting dependencies.
Uses topological sort to organize tools into waves for optimal parallelization.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional, Any, Callable
from enum import Enum
import time

logger = logging.getLogger(__name__)


class ToolStatus(str, Enum):
    """Tool execution status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class ToolResult:
    """Result from tool execution"""
    tool_id: str
    success: bool
    data: Any = None
    error: Optional[str] = None
    latency_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def status(self) -> ToolStatus:
        if self.success:
            return ToolStatus.COMPLETED
        return ToolStatus.FAILED


@dataclass
class ToolNode:
    """Node in the tool dependency graph"""
    tool_id: str
    execute: Callable  # Async function to execute
    dependencies: List[str] = field(default_factory=list)

    # Tool metadata
    description: str = ""
    timeout_seconds: float = 30.0
    retry_count: int = 0
    max_retries: int = 3

    # Execution state
    status: ToolStatus = ToolStatus.PENDING
    result: Optional[ToolResult] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None

    @property
    def latency_ms(self) -> float:
        """Calculate execution latency in milliseconds"""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time) * 1000
        return 0.0


class CyclicDependencyError(Exception):
    """Raised when tool dependency graph contains a cycle"""
    pass


class ToolDependencyGraph:
    """
    Manages tool dependencies and execution order.

    Uses topological sort to determine execution waves where tools
    can be executed in parallel within a wave.
    """

    def __init__(self):
        self.nodes: Dict[str, ToolNode] = {}
        self.waves: Optional[List[List[str]]] = None
        self._execution_order: Optional[List[str]] = None

    def add_tool(
        self,
        tool_id: str,
        execute: Callable,
        dependencies: Optional[List[str]] = None,
        description: str = "",
        timeout_seconds: float = 30.0,
        max_retries: int = 3
    ):
        """
        Add a tool to the dependency graph.

        Args:
            tool_id: Unique identifier for the tool
            execute: Async callable that executes the tool
            dependencies: List of tool_ids this tool depends on
            description: Human-readable description
            timeout_seconds: Maximum execution time
            max_retries: Maximum retry attempts on failure

        Example:
            ```python
            graph = ToolDependencyGraph()

            graph.add_tool(
                tool_id="search",
                execute=search_tool.run,
                dependencies=[],
                description="Web search for materials"
            )

            graph.add_tool(
                tool_id="fetch_page",
                execute=fetch_tool.run,
                dependencies=["search"],  # Depends on search results
                description="Fetch top search results"
            )
            ```
        """
        if dependencies is None:
            dependencies = []

        # Validate dependencies exist (or will exist)
        for dep in dependencies:
            if dep not in self.nodes and dep != tool_id:
                logger.warning(f"Tool {tool_id} depends on {dep} which doesn't exist yet")

        self.nodes[tool_id] = ToolNode(
            tool_id=tool_id,
            execute=execute,
            dependencies=dependencies,
            description=description,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries
        )

        # Invalidate cached waves since graph changed
        self.waves = None
        self._execution_order = None

        logger.debug(f"Added tool {tool_id} with {len(dependencies)} dependencies")

    def remove_tool(self, tool_id: str):
        """Remove a tool from the graph"""
        if tool_id in self.nodes:
            del self.nodes[tool_id]
            self.waves = None
            self._execution_order = None
            logger.debug(f"Removed tool {tool_id}")

    def get_tool(self, tool_id: str) -> Optional[ToolNode]:
        """Get a tool node by ID"""
        return self.nodes.get(tool_id)

    def calculate_waves(self) -> List[List[str]]:
        """
        Calculate execution waves using topological sort.

        Tools in the same wave can be executed in parallel.
        Each wave must complete before the next wave starts.

        Returns:
            List of waves, where each wave is a list of tool_ids

        Raises:
            CyclicDependencyError: If dependency graph contains a cycle

        Example:
            Given tools: A, B (depends on A), C (depends on A), D (depends on B, C)
            Waves: [[A], [B, C], [D]]
        """
        if self.waves is not None:
            return self.waves

        waves = []
        remaining = set(self.nodes.keys())
        completed = set()

        # Track iterations to detect cycles
        max_iterations = len(self.nodes) + 1
        iteration = 0

        while remaining and iteration < max_iterations:
            # Find nodes with all dependencies satisfied
            wave = [
                node_id for node_id in remaining
                if all(dep in completed for dep in self.nodes[node_id].dependencies)
            ]

            if not wave:
                # No progress possible - must be a cycle
                raise CyclicDependencyError(
                    f"Cyclic dependency detected in tools: {remaining}"
                )

            waves.append(wave)
            remaining -= set(wave)
            completed.update(wave)
            iteration += 1

        if remaining:
            raise CyclicDependencyError(
                f"Could not resolve dependencies for tools: {remaining}"
            )

        self.waves = waves
        logger.info(f"Calculated {len(waves)} execution waves")
        for i, wave in enumerate(waves):
            logger.debug(f"Wave {i}: {wave}")

        return waves

    def get_execution_order(self) -> List[str]:
        """
        Get a flattened execution order (all waves concatenated).

        Returns:
            List of tool_ids in execution order
        """
        if self._execution_order is not None:
            return self._execution_order

        waves = self.calculate_waves()
        self._execution_order = [tool_id for wave in waves for tool_id in wave]
        return self._execution_order

    def validate(self) -> bool:
        """
        Validate the dependency graph.

        Checks:
        - All dependencies reference existing tools
        - No cycles exist

        Returns:
            True if valid, False otherwise
        """
        try:
            # Check all dependencies exist
            for tool_id, node in self.nodes.items():
                for dep in node.dependencies:
                    if dep not in self.nodes:
                        logger.error(
                            f"Tool {tool_id} depends on non-existent tool {dep}"
                        )
                        return False

            # Check for cycles by calculating waves
            self.calculate_waves()

            return True

        except CyclicDependencyError as e:
            logger.error(f"Validation failed: {e}")
            return False

    def reset_execution_state(self):
        """Reset all tools to pending state"""
        for node in self.nodes.values():
            node.status = ToolStatus.PENDING
            node.result = None
            node.start_time = None
            node.end_time = None
            node.retry_count = 0

    def get_stats(self) -> Dict[str, Any]:
        """Get execution statistics"""
        total_tools = len(self.nodes)
        completed = sum(1 for n in self.nodes.values() if n.status == ToolStatus.COMPLETED)
        failed = sum(1 for n in self.nodes.values() if n.status == ToolStatus.FAILED)
        running = sum(1 for n in self.nodes.values() if n.status == ToolStatus.RUNNING)

        total_latency = sum(n.latency_ms for n in self.nodes.values() if n.end_time)
        avg_latency = total_latency / completed if completed > 0 else 0

        return {
            "total_tools": total_tools,
            "completed": completed,
            "failed": failed,
            "running": running,
            "pending": total_tools - completed - failed - running,
            "total_latency_ms": total_latency,
            "avg_latency_ms": avg_latency,
            "total_waves": len(self.waves) if self.waves else 0
        }


class WaveExecutor:
    """
    Executes tools in waves with parallelization.

    Tools within a wave are executed concurrently.
    Waves execute sequentially to respect dependencies.
    """

    def __init__(
        self,
        graph: ToolDependencyGraph,
        max_concurrent: int = 10,
        fail_fast: bool = False
    ):
        """
        Initialize wave executor.

        Args:
            graph: Tool dependency graph
            max_concurrent: Maximum concurrent tool executions per wave
            fail_fast: If True, stop execution on first failure
        """
        self.graph = graph
        self.max_concurrent = max_concurrent
        self.fail_fast = fail_fast

    async def execute(self, context: Dict[str, Any]) -> Dict[str, ToolResult]:
        """
        Execute all tools in the graph.

        Args:
            context: Shared context passed to all tools

        Returns:
            Dictionary mapping tool_id to ToolResult

        Example:
            ```python
            executor = WaveExecutor(graph)
            results = await executor.execute({"query": "research materials"})

            for tool_id, result in results.items():
                if result.success:
                    print(f"{tool_id}: {result.data}")
                else:
                    print(f"{tool_id} failed: {result.error}")
            ```
        """
        logger.info("Starting wave execution")
        self.graph.reset_execution_state()

        # Calculate execution waves
        try:
            waves = self.graph.calculate_waves()
        except CyclicDependencyError as e:
            logger.error(f"Cannot execute due to cyclic dependencies: {e}")
            return {}

        results: Dict[str, ToolResult] = {}

        # Execute each wave
        for wave_num, wave in enumerate(waves):
            logger.info(f"Executing wave {wave_num + 1}/{len(waves)} with {len(wave)} tools")

            # Execute all tools in this wave concurrently
            wave_results = await self._execute_wave(wave, context, results)
            results.update(wave_results)

            # Check for failures if fail_fast enabled
            if self.fail_fast:
                failed_tools = [
                    tool_id for tool_id, result in wave_results.items()
                    if not result.success
                ]
                if failed_tools:
                    logger.error(
                        f"Wave {wave_num + 1} failed (fail_fast enabled): {failed_tools}"
                    )
                    # Mark remaining tools as skipped
                    for remaining_wave in waves[wave_num + 1:]:
                        for tool_id in remaining_wave:
                            node = self.graph.get_tool(tool_id)
                            if node:
                                node.status = ToolStatus.SKIPPED
                                results[tool_id] = ToolResult(
                                    tool_id=tool_id,
                                    success=False,
                                    error="Skipped due to previous failure"
                                )
                    break

        stats = self.graph.get_stats()
        logger.info(
            f"Wave execution complete: {stats['completed']}/{stats['total_tools']} succeeded, "
            f"{stats['failed']} failed, avg latency {stats['avg_latency_ms']:.1f}ms"
        )

        return results

    async def _execute_wave(
        self,
        wave: List[str],
        context: Dict[str, Any],
        previous_results: Dict[str, ToolResult]
    ) -> Dict[str, ToolResult]:
        """Execute all tools in a wave concurrently"""

        # Create execution tasks for all tools in the wave
        tasks = []
        for tool_id in wave:
            task = self._execute_tool(tool_id, context, previous_results)
            tasks.append(task)

        # Execute concurrently with max_concurrent limit
        results = {}

        # Process in batches if wave is larger than max_concurrent
        for i in range(0, len(tasks), self.max_concurrent):
            batch = tasks[i:i + self.max_concurrent]
            batch_tool_ids = wave[i:i + self.max_concurrent]

            batch_results = await asyncio.gather(*batch, return_exceptions=True)

            for tool_id, result in zip(batch_tool_ids, batch_results):
                if isinstance(result, Exception):
                    logger.error(f"Tool {tool_id} raised exception: {result}")
                    results[tool_id] = ToolResult(
                        tool_id=tool_id,
                        success=False,
                        error=str(result)
                    )
                else:
                    results[tool_id] = result

        return results

    async def _execute_tool(
        self,
        tool_id: str,
        context: Dict[str, Any],
        previous_results: Dict[str, ToolResult]
    ) -> ToolResult:
        """Execute a single tool with retry logic"""

        node = self.graph.get_tool(tool_id)
        if not node:
            return ToolResult(
                tool_id=tool_id,
                success=False,
                error=f"Tool {tool_id} not found"
            )

        # Build input context with dependency results
        tool_context = context.copy()
        tool_context["dependency_results"] = {
            dep: previous_results.get(dep)
            for dep in node.dependencies
        }

        # Retry loop
        for attempt in range(node.max_retries + 1):
            try:
                node.status = ToolStatus.RUNNING
                node.start_time = time.time()
                node.retry_count = attempt

                # Execute with timeout
                result_data = await asyncio.wait_for(
                    node.execute(tool_context),
                    timeout=node.timeout_seconds
                )

                node.end_time = time.time()
                node.status = ToolStatus.COMPLETED

                result = ToolResult(
                    tool_id=tool_id,
                    success=True,
                    data=result_data,
                    latency_ms=node.latency_ms,
                    metadata={
                        "attempt": attempt + 1,
                        "max_retries": node.max_retries
                    }
                )
                node.result = result

                logger.info(
                    f"Tool {tool_id} completed in {node.latency_ms:.1f}ms "
                    f"(attempt {attempt + 1})"
                )

                return result

            except asyncio.TimeoutError:
                error_msg = f"Timeout after {node.timeout_seconds}s"
                logger.warning(f"Tool {tool_id} timed out (attempt {attempt + 1})")

            except Exception as e:
                error_msg = str(e)
                logger.warning(f"Tool {tool_id} failed: {e} (attempt {attempt + 1})")

            # Retry with exponential backoff
            if attempt < node.max_retries:
                backoff_seconds = 2 ** attempt
                logger.info(f"Retrying {tool_id} in {backoff_seconds}s...")
                await asyncio.sleep(backoff_seconds)

        # All retries exhausted
        node.end_time = time.time()
        node.status = ToolStatus.FAILED

        result = ToolResult(
            tool_id=tool_id,
            success=False,
            error=error_msg,
            latency_ms=node.latency_ms,
            metadata={
                "attempt": node.max_retries + 1,
                "max_retries": node.max_retries
            }
        )
        node.result = result

        logger.error(
            f"Tool {tool_id} failed after {node.max_retries + 1} attempts: {error_msg}"
        )

        return result
