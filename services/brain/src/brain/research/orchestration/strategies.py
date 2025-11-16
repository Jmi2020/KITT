"""
Multi-Strategy Research Agents

Provides different research strategies for autonomous exploration:
- Breadth-First: Cast wide net, explore many sources
- Depth-First: Deep dive into specific sources/topics
- Task Decomposition: Break complex queries into subtasks
- Hybrid: Adaptive combination of strategies
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Set
from enum import Enum
import asyncio

logger = logging.getLogger(__name__)


class ResearchStrategy(str, Enum):
    """Available research strategies"""
    BREADTH_FIRST = "breadth_first"
    DEPTH_FIRST = "depth_first"
    TASK_DECOMPOSITION = "task_decomposition"
    HYBRID = "hybrid"


@dataclass
class ResearchTask:
    """A research task/subtask"""
    task_id: str
    query: str
    priority: float = 1.0
    depth: int = 0
    parent_task_id: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)

    # Execution state
    status: str = "pending"  # pending, in_progress, completed, failed
    result: Optional[Any] = None
    error: Optional[str] = None


@dataclass
class ResearchNode:
    """A node in the research exploration graph"""
    node_id: str
    content: str
    source: Optional[str] = None
    depth: int = 0
    relevance_score: float = 0.0
    novelty_score: float = 0.0
    children: List[str] = field(default_factory=list)
    visited: bool = False


@dataclass
class StrategyContext:
    """Context for strategy execution"""
    session_id: str
    original_query: str
    max_depth: int = 3
    max_breadth: int = 10
    max_iterations: int = 15
    min_sources: int = 5
    budget_remaining: float = 2.0
    external_calls_remaining: int = 10

    # Accumulated state
    nodes_explored: int = 0
    findings: List[Dict[str, Any]] = field(default_factory=list)
    sources: Set[str] = field(default_factory=set)


class BaseResearchStrategy(ABC):
    """Base class for research strategies"""

    def __init__(self, strategy_name: str):
        self.strategy_name = strategy_name

    @abstractmethod
    async def plan(self, query: str, context: StrategyContext) -> List[ResearchTask]:
        """
        Plan research tasks for the given query.

        Args:
            query: Research query
            context: Strategy execution context

        Returns:
            List of research tasks to execute
        """
        pass

    @abstractmethod
    async def should_continue(self, context: StrategyContext) -> bool:
        """
        Determine if research should continue.

        Args:
            context: Current strategy context

        Returns:
            True if research should continue, False otherwise
        """
        pass

    async def prioritize_tasks(self, tasks: List[ResearchTask]) -> List[ResearchTask]:
        """
        Prioritize tasks for execution.

        Default: sort by priority score.
        Subclasses can override for custom logic.
        """
        return sorted(tasks, key=lambda t: t.priority, reverse=True)


class BreadthFirstStrategy(BaseResearchStrategy):
    """
    Breadth-First Research Strategy

    Explores multiple sources at same depth before going deeper.
    Good for comprehensive overviews and diverse perspectives.

    Approach:
    1. Start with broad search across multiple sources
    2. Extract key topics/entities from results
    3. Explore each topic in parallel (same depth)
    4. Synthesize findings across all topics
    5. Go deeper only if coverage gaps detected
    """

    def __init__(self):
        super().__init__(strategy_name="breadth_first")

    async def plan(self, query: str, context: StrategyContext) -> List[ResearchTask]:
        """Plan breadth-first exploration"""
        tasks = []

        # Level 0: Broad search
        if context.nodes_explored == 0:
            tasks.append(
                ResearchTask(
                    task_id=f"{context.session_id}_search_0",
                    query=query,
                    priority=1.0,
                    depth=0,
                    context={"search_type": "broad", "max_results": context.max_breadth}
                )
            )
            logger.info(f"Breadth-first: Starting with broad search for '{query}'")
            return tasks

        # Level 1+: Extract topics from findings and explore each
        current_depth = max(f.get("depth", 0) for f in context.findings) if context.findings else 0

        if current_depth < context.max_depth:
            # Extract unexplored topics from current findings
            topics = self._extract_topics(context.findings)

            for i, topic in enumerate(topics[:context.max_breadth]):
                if topic not in [f.get("topic") for f in context.findings]:
                    tasks.append(
                        ResearchTask(
                            task_id=f"{context.session_id}_topic_{current_depth+1}_{i}",
                            query=f"{query} {topic}",
                            priority=0.8,
                            depth=current_depth + 1,
                            context={"topic": topic, "search_type": "focused"}
                        )
                    )

            logger.info(f"Breadth-first: Exploring {len(tasks)} topics at depth {current_depth+1}")

        return tasks

    async def should_continue(self, context: StrategyContext) -> bool:
        """Continue if:
        - Haven't reached max iterations
        - Haven't reached max depth
        - Still have budget
        - Haven't met minimum source threshold
        """
        if context.nodes_explored >= context.max_iterations:
            logger.info("Breadth-first: Max iterations reached")
            return False

        if context.budget_remaining <= 0:
            logger.info("Breadth-first: Budget exhausted")
            return False

        current_depth = max(f.get("depth", 0) for f in context.findings) if context.findings else 0
        if current_depth >= context.max_depth and len(context.sources) >= context.min_sources:
            logger.info("Breadth-first: Max depth and min sources reached")
            return False

        return True

    def _extract_topics(self, findings: List[Dict[str, Any]]) -> List[str]:
        """Extract key topics from findings for further exploration"""
        topics = []

        for finding in findings:
            # Extract topics from finding metadata
            if "topics" in finding:
                topics.extend(finding["topics"])

            # Extract entities/keywords
            if "entities" in finding:
                topics.extend(finding["entities"])

        # Deduplicate and return most relevant
        unique_topics = list(set(topics))
        return unique_topics[:10]  # Top 10 topics


class DepthFirstStrategy(BaseResearchStrategy):
    """
    Depth-First Research Strategy

    Follows most promising leads deeply before exploring alternatives.
    Good for detailed investigation and causal chains.

    Approach:
    1. Start with initial search
    2. Select most relevant/novel result
    3. Deeply explore that source (citations, related work, etc.)
    4. When exhausted, backtrack and try next best alternative
    5. Continue until depth limit or saturation
    """

    def __init__(self):
        super().__init__(strategy_name="depth_first")
        self.exploration_stack: List[ResearchNode] = []

    async def plan(self, query: str, context: StrategyContext) -> List[ResearchTask]:
        """Plan depth-first exploration"""
        tasks = []

        # Level 0: Initial search
        if context.nodes_explored == 0:
            tasks.append(
                ResearchTask(
                    task_id=f"{context.session_id}_search_0",
                    query=query,
                    priority=1.0,
                    depth=0,
                    context={"search_type": "initial"}
                )
            )
            logger.info(f"Depth-first: Starting initial search for '{query}'")
            return tasks

        # Find the most promising unvisited node
        best_node = self._select_best_unvisited_node(context)

        if best_node and best_node.depth < context.max_depth:
            # Deep dive into this source
            tasks.append(
                ResearchTask(
                    task_id=f"{context.session_id}_dive_{best_node.node_id}",
                    query=f"{query} related to {best_node.content[:100]}",
                    priority=best_node.relevance_score * best_node.novelty_score,
                    depth=best_node.depth + 1,
                    parent_task_id=best_node.node_id,
                    context={"parent_node": best_node.node_id, "search_type": "deep_dive"}
                )
            )
            logger.info(f"Depth-first: Deep diving from node {best_node.node_id} at depth {best_node.depth}")

        return tasks

    async def should_continue(self, context: StrategyContext) -> bool:
        """Continue if:
        - Haven't exhausted exploration stack
        - Haven't reached max iterations
        - Still have budget
        """
        if context.nodes_explored >= context.max_iterations:
            logger.info("Depth-first: Max iterations reached")
            return False

        if context.budget_remaining <= 0:
            logger.info("Depth-first: Budget exhausted")
            return False

        # Check if we have unexplored promising nodes
        unvisited = [f for f in context.findings if not f.get("visited", False)]
        if not unvisited and len(context.sources) >= context.min_sources:
            logger.info("Depth-first: All nodes explored and min sources met")
            return False

        return True

    def _select_best_unvisited_node(self, context: StrategyContext) -> Optional[ResearchNode]:
        """Select the most promising unvisited node for exploration"""
        unvisited = [f for f in context.findings if not f.get("visited", False)]

        if not unvisited:
            return None

        # Score by relevance * novelty
        scored = [
            (f, f.get("relevance_score", 0.5) * f.get("novelty_score", 0.5))
            for f in unvisited
        ]
        scored.sort(key=lambda x: x[1], reverse=True)

        best_finding = scored[0][0]

        return ResearchNode(
            node_id=best_finding.get("id", "unknown"),
            content=best_finding.get("content", ""),
            source=best_finding.get("source"),
            depth=best_finding.get("depth", 0),
            relevance_score=best_finding.get("relevance_score", 0.5),
            novelty_score=best_finding.get("novelty_score", 0.5)
        )


class TaskDecompositionStrategy(BaseResearchStrategy):
    """
    Task Decomposition Strategy

    Breaks complex queries into manageable subtasks.
    Good for multi-faceted questions requiring different types of research.

    Approach:
    1. Analyze query complexity and identify sub-questions
    2. Create subtasks for each sub-question
    3. Execute subtasks in parallel or sequentially based on dependencies
    4. Synthesize results from all subtasks
    5. Identify and fill gaps
    """

    def __init__(self):
        super().__init__(strategy_name="task_decomposition")
        self.subtasks_created = False

    async def plan(self, query: str, context: StrategyContext) -> List[ResearchTask]:
        """Plan task decomposition"""
        tasks = []

        # First pass: decompose query into subtasks
        if not self.subtasks_created:
            subtasks = await self._decompose_query(query)

            for i, subtask_query in enumerate(subtasks):
                tasks.append(
                    ResearchTask(
                        task_id=f"{context.session_id}_subtask_{i}",
                        query=subtask_query,
                        priority=1.0 - (i * 0.1),  # Earlier tasks slightly higher priority
                        depth=0,
                        context={"subtask_index": i, "total_subtasks": len(subtasks)}
                    )
                )

            self.subtasks_created = True
            logger.info(f"Task decomposition: Created {len(tasks)} subtasks")
            return tasks

        # Subsequent passes: check if subtasks need refinement
        completed_subtasks = [f for f in context.findings if f.get("status") == "completed"]
        pending_subtasks = [f for f in context.findings if f.get("status") == "pending"]

        if pending_subtasks:
            # Still have pending subtasks, no new planning needed yet
            return []

        # All subtasks complete, check for gaps
        if self._has_knowledge_gaps(context):
            gap_tasks = await self._create_gap_filling_tasks(query, context)
            tasks.extend(gap_tasks)
            logger.info(f"Task decomposition: Created {len(gap_tasks)} gap-filling tasks")

        return tasks

    async def should_continue(self, context: StrategyContext) -> bool:
        """Continue if:
        - Not all subtasks completed
        - Knowledge gaps exist
        - Haven't reached max iterations
        - Still have budget
        """
        if context.nodes_explored >= context.max_iterations:
            logger.info("Task decomposition: Max iterations reached")
            return False

        if context.budget_remaining <= 0:
            logger.info("Task decomposition: Budget exhausted")
            return False

        # Check if all subtasks are complete and no gaps
        pending = [f for f in context.findings if f.get("status") == "pending"]
        has_gaps = self._has_knowledge_gaps(context)

        if not pending and not has_gaps and len(context.sources) >= context.min_sources:
            logger.info("Task decomposition: All subtasks complete and no gaps")
            return False

        return True

    async def _decompose_query(self, query: str) -> List[str]:
        """
        Decompose complex query into subtasks.

        This is a simple heuristic-based approach.
        In Phase 3, this will use LLM-based decomposition.
        """
        subtasks = []

        # Check for common multi-part patterns
        if "compare" in query.lower() or "versus" in query.lower() or " vs " in query.lower():
            # Comparative query - research each side
            parts = query.replace(" versus ", " vs ").split(" vs ")
            if len(parts) == 2:
                subtasks.append(f"What is {parts[0].strip()}?")
                subtasks.append(f"What is {parts[1].strip()}?")
                subtasks.append(f"How do {parts[0].strip()} and {parts[1].strip()} differ?")

        elif "and" in query.lower():
            # Multiple topics - research each
            parts = query.split(" and ")
            for part in parts:
                subtasks.append(part.strip() + "?")

        elif "how" in query.lower() and "why" in query.lower():
            # Mechanism + causation
            subtasks.append(query.replace("why", "").strip())
            subtasks.append(query.replace("how", "").strip())

        else:
            # Default decomposition: what, how, why
            subtasks.append(f"What is {query}?")
            subtasks.append(f"How does {query} work?")
            subtasks.append(f"Why is {query} important?")

        return subtasks[:5]  # Max 5 subtasks

    def _has_knowledge_gaps(self, context: StrategyContext) -> bool:
        """Check if there are knowledge gaps in current findings"""
        # Simple heuristic: check source diversity
        if len(context.sources) < context.min_sources:
            return True

        # Check finding completeness
        if len(context.findings) < 3:
            return True

        return False

    async def _create_gap_filling_tasks(self, query: str, context: StrategyContext) -> List[ResearchTask]:
        """Create tasks to fill identified knowledge gaps"""
        tasks = []

        # If not enough sources, create broad search task
        if len(context.sources) < context.min_sources:
            tasks.append(
                ResearchTask(
                    task_id=f"{context.session_id}_gap_sources",
                    query=f"{query} additional sources",
                    priority=0.8,
                    depth=1,
                    context={"gap_type": "sources"}
                )
            )

        return tasks


class HybridStrategy(BaseResearchStrategy):
    """
    Hybrid Research Strategy

    Adaptively combines breadth-first and depth-first approaches.
    Switches strategy based on progress and context.

    Decision logic:
    - Start with breadth to get overview
    - Switch to depth when promising lead found
    - Return to breadth if depth exhausted
    - Use task decomposition for complex queries
    """

    def __init__(self):
        super().__init__(strategy_name="hybrid")
        self.breadth_strategy = BreadthFirstStrategy()
        self.depth_strategy = DepthFirstStrategy()
        self.task_decomposition_strategy = TaskDecompositionStrategy()
        self.current_strategy: BaseResearchStrategy = self.breadth_strategy

    async def plan(self, query: str, context: StrategyContext) -> List[ResearchTask]:
        """Plan using adaptive strategy selection"""

        # Decide which strategy to use
        self._select_strategy(context)

        # Delegate to selected strategy
        return await self.current_strategy.plan(query, context)

    async def should_continue(self, context: StrategyContext) -> bool:
        """Delegate to current strategy"""
        return await self.current_strategy.should_continue(context)

    def _select_strategy(self, context: StrategyContext):
        """Select best strategy for current context"""

        # Start with breadth for exploration
        if context.nodes_explored < 3:
            self.current_strategy = self.breadth_strategy
            return

        # Switch to depth if we found very relevant result
        if context.findings:
            max_relevance = max(f.get("relevance_score", 0) for f in context.findings)
            if max_relevance > 0.85:
                logger.info("Hybrid: Switching to depth-first (high relevance found)")
                self.current_strategy = self.depth_strategy
                return

        # Use task decomposition for complex queries (heuristic: long queries)
        if len(context.original_query.split()) > 10 and context.nodes_explored < 5:
            logger.info("Hybrid: Using task decomposition (complex query)")
            self.current_strategy = self.task_decomposition_strategy
            return

        # Default to breadth
        self.current_strategy = self.breadth_strategy


def create_strategy(strategy_type: ResearchStrategy) -> BaseResearchStrategy:
    """
    Factory function to create research strategy.

    Args:
        strategy_type: Type of strategy to create

    Returns:
        Configured research strategy instance
    """
    strategies = {
        ResearchStrategy.BREADTH_FIRST: BreadthFirstStrategy,
        ResearchStrategy.DEPTH_FIRST: DepthFirstStrategy,
        ResearchStrategy.TASK_DECOMPOSITION: TaskDecompositionStrategy,
        ResearchStrategy.HYBRID: HybridStrategy,
    }

    strategy_class = strategies.get(strategy_type)
    if not strategy_class:
        raise ValueError(f"Unknown strategy type: {strategy_type}")

    return strategy_class()
