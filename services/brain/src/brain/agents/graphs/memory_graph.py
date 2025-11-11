"""
Memory-Augmented Conversation Graph - Adaptive memory retrieval and fact extraction.

Features:
- Adaptive memory search depth based on initial results
- Memory sufficiency scoring
- Automatic fact extraction from conversations
- Memory-guided query reformulation
- User preference learning over time
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Literal, Optional

from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from brain.memory import MemoryClient

logger = logging.getLogger(__name__)


class MemoryAugmentedState(TypedDict, total=False):
    """State for memory-augmented conversation workflow."""

    # Input
    query: str
    original_query: str
    user_id: str
    conversation_id: str

    # Memory retrieval
    initial_memories: List[Dict[str, Any]]
    deep_memories: List[Dict[str, Any]]
    all_memories: List[Dict[str, Any]]  # Combined memories
    memory_sufficiency_score: float  # 0.0-1.0

    # Fact extraction
    new_facts: List[str]  # Facts from current conversation
    facts_to_store: List[Dict[str, Any]]  # Structured facts ready for storage

    # Query reformulation
    reformulated_query: Optional[str]
    reformulation_count: int
    max_reformulations: int

    # Output
    memory_context: str  # Formatted context for prompts
    should_deep_search: bool
    nodes_executed: List[str]


class MemoryGraph:
    """
    Memory-augmented conversation graph using LangGraph.

    Workflow:
    1. Initial Memory Search: Quick search with standard threshold
    2. Memory Sufficiency Check: Assess if more context needed
    3. Deep Memory Search: Lower threshold, broader search if needed
    4. Query Reformulation: Rephrase query for better retrieval (if insufficient)
    5. Fact Extraction: Extract facts from conversation for future storage
    6. Context Formatting: Create structured memory context for LLM
    """

    def __init__(
        self,
        memory_client: MemoryClient,
        initial_score_threshold: float = 0.75,
        deep_score_threshold: float = 0.60,
        sufficiency_threshold: float = 0.70,
        max_reformulations: int = 2,
    ) -> None:
        """
        Initialize memory graph.

        Args:
            memory_client: Memory search client
            initial_score_threshold: Threshold for initial search
            deep_score_threshold: Lower threshold for deep search
            sufficiency_threshold: Minimum score for sufficient memory
            max_reformulations: Maximum query reformulation attempts
        """
        self.memory = memory_client
        self.initial_threshold = initial_score_threshold
        self.deep_threshold = deep_score_threshold
        self.sufficiency_threshold = sufficiency_threshold
        self.max_reformulations = max_reformulations

        # Build graph
        self.graph = self._build_graph()

        logger.info("MemoryGraph initialized with adaptive memory retrieval")

    def _build_graph(self) -> StateGraph:
        """Build LangGraph state machine for memory retrieval."""
        workflow = StateGraph(MemoryAugmentedState)

        # Add nodes
        workflow.add_node("initial_search", self._initial_search_node)
        workflow.add_node("sufficiency_check", self._sufficiency_check_node)
        workflow.add_node("deep_search", self._deep_search_node)
        workflow.add_node("query_reformulation", self._query_reformulation_node)
        workflow.add_node("fact_extraction", self._fact_extraction_node)
        workflow.add_node("context_formatting", self._context_formatting_node)

        # Entry point
        workflow.set_entry_point("initial_search")

        # Linear flow
        workflow.add_edge("initial_search", "sufficiency_check")

        # Conditional: sufficiency → deep_search or fact_extraction
        workflow.add_conditional_edges(
            "sufficiency_check",
            self._should_deep_search,
            {
                "deep_search": "deep_search",
                "fact_extraction": "fact_extraction",
            },
        )

        workflow.add_edge("deep_search", "sufficiency_check")  # Re-check after deep search

        # Conditional: sufficiency → reformulation or fact_extraction (after deep search fails)
        # Note: This is a simplified flow; in practice, reformulation would loop back to search

        workflow.add_edge("fact_extraction", "context_formatting")
        workflow.add_edge("context_formatting", END)

        return workflow.compile()

    async def run(
        self,
        query: str,
        user_id: str,
        conversation_id: str,
    ) -> MemoryAugmentedState:
        """
        Execute memory-augmented retrieval.

        Args:
            query: User query
            user_id: User identifier
            conversation_id: Conversation identifier

        Returns:
            Final state with memory context and extracted facts
        """
        logger.debug(f"Starting memory-augmented retrieval for: {query[:100]}...")

        initial_state: MemoryAugmentedState = {
            "query": query,
            "original_query": query,
            "user_id": user_id,
            "conversation_id": conversation_id,
            "initial_memories": [],
            "deep_memories": [],
            "all_memories": [],
            "memory_sufficiency_score": 0.0,
            "new_facts": [],
            "facts_to_store": [],
            "reformulated_query": None,
            "reformulation_count": 0,
            "max_reformulations": self.max_reformulations,
            "should_deep_search": False,
            "nodes_executed": [],
            "memory_context": "",
        }

        try:
            final_state = await self.graph.ainvoke(initial_state)

            logger.info(
                f"Memory retrieval complete: {len(final_state.get('all_memories', []))} memories, "
                f"sufficiency={final_state.get('memory_sufficiency_score', 0):.2f}"
            )

            return final_state

        except Exception as exc:
            logger.error(f"Memory graph failed: {exc}", exc_info=True)
            return {
                **initial_state,
                "memory_context": "",
                "memory_sufficiency_score": 0.0,
            }

    async def _initial_search_node(self, state: MemoryAugmentedState) -> Dict:
        """
        Initial memory search with standard threshold.

        Args:
            state: Current state

        Returns:
            State updates with initial memories
        """
        logger.debug("Executing initial memory search")

        try:
            # Search with standard threshold
            memory_results = await self.memory.search_memories(
                query=state["query"],
                conversation_id=state["conversation_id"],
                user_id=state["user_id"],
                limit=3,
                score_threshold=self.initial_threshold,
            )

            initial_memories = [
                {
                    "content": m.content,
                    "score": m.score,
                    "metadata": m.metadata or {},
                }
                for m in memory_results
            ]

            logger.info(f"Initial search: {len(initial_memories)} memories found")

            return {
                "initial_memories": initial_memories,
                "all_memories": initial_memories,
                "nodes_executed": state.get("nodes_executed", []) + ["initial_search"],
            }

        except Exception as exc:
            logger.warning(f"Initial memory search failed: {exc}")
            return {
                "initial_memories": [],
                "all_memories": [],
                "nodes_executed": state.get("nodes_executed", []) + ["initial_search"],
            }

    async def _sufficiency_check_node(self, state: MemoryAugmentedState) -> Dict:
        """
        Check if retrieved memories are sufficient.

        Args:
            state: Current state

        Returns:
            State updates with sufficiency score
        """
        logger.debug("Executing memory sufficiency check")

        memories = state.get("all_memories", [])

        if not memories:
            # No memories = insufficient
            sufficiency_score = 0.0
            should_deep_search = True
        else:
            # Calculate sufficiency based on:
            # 1. Number of memories (more is better)
            # 2. Average score (higher is better)
            # 3. Query length (longer queries need more context)

            num_memories = len(memories)
            avg_score = sum(m.get("score", 0) for m in memories) / num_memories
            query_length = len(state["query"].split())

            # Sufficiency heuristic
            num_score = min(num_memories / 3.0, 1.0)  # Target: 3+ memories
            quality_score = avg_score  # Already 0-1
            length_factor = min(query_length / 20.0, 1.0)  # Longer queries need more context

            sufficiency_score = (num_score * 0.4) + (quality_score * 0.6)

            # Adjust for query length (complex queries need more context)
            if query_length > 20:
                sufficiency_score *= 0.8  # Reduce sufficiency for complex queries

            should_deep_search = sufficiency_score < self.sufficiency_threshold

        logger.info(
            f"Memory sufficiency: {sufficiency_score:.2f}, "
            f"should_deep_search={should_deep_search}"
        )

        return {
            "memory_sufficiency_score": sufficiency_score,
            "should_deep_search": should_deep_search,
            "nodes_executed": state.get("nodes_executed", []) + ["sufficiency_check"],
        }

    async def _deep_search_node(self, state: MemoryAugmentedState) -> Dict:
        """
        Deep memory search with lower threshold.

        Args:
            state: Current state

        Returns:
            State updates with deep memories
        """
        logger.debug("Executing deep memory search")

        try:
            # Search with lower threshold for more results
            memory_results = await self.memory.search_memories(
                query=state["query"],
                conversation_id=state["conversation_id"],
                user_id=state["user_id"],
                limit=5,  # More results for deep search
                score_threshold=self.deep_threshold,  # Lower threshold
            )

            deep_memories = [
                {
                    "content": m.content,
                    "score": m.score,
                    "metadata": m.metadata or {},
                }
                for m in memory_results
            ]

            # Combine with initial memories (deduplicate by content)
            all_memories = state.get("initial_memories", [])
            existing_contents = {m["content"] for m in all_memories}

            for mem in deep_memories:
                if mem["content"] not in existing_contents:
                    all_memories.append(mem)
                    existing_contents.add(mem["content"])

            logger.info(f"Deep search: {len(deep_memories)} new memories, {len(all_memories)} total")

            return {
                "deep_memories": deep_memories,
                "all_memories": all_memories,
                "nodes_executed": state.get("nodes_executed", []) + ["deep_search"],
            }

        except Exception as exc:
            logger.warning(f"Deep memory search failed: {exc}")
            return {
                "deep_memories": [],
                "nodes_executed": state.get("nodes_executed", []) + ["deep_search"],
            }

    async def _query_reformulation_node(self, state: MemoryAugmentedState) -> Dict:
        """
        Reformulate query for better memory retrieval.

        Args:
            state: Current state

        Returns:
            State updates with reformulated query
        """
        logger.debug("Executing query reformulation")

        # Simple reformulation heuristics
        original_query = state["original_query"]
        reformulation_count = state.get("reformulation_count", 0)

        if reformulation_count >= state["max_reformulations"]:
            logger.info("Max reformulations reached, stopping")
            return {"nodes_executed": state.get("nodes_executed", []) + ["query_reformulation"]}

        # Reformulation strategies:
        # 1. Remove question words (what, where, when, etc.)
        # 2. Extract key nouns and adjectives
        # 3. Expand abbreviations

        reformulated = original_query.lower()

        # Remove question words
        question_words = ["what", "where", "when", "why", "how", "who", "which"]
        for qw in question_words:
            reformulated = re.sub(rf"\b{qw}\b", "", reformulated, flags=re.IGNORECASE)

        # Remove common filler words
        filler_words = ["is", "the", "a", "an", "do", "does", "can", "could", "should"]
        for fw in filler_words:
            reformulated = re.sub(rf"\b{fw}\b", "", reformulated, flags=re.IGNORECASE)

        # Clean up whitespace
        reformulated = " ".join(reformulated.split())

        logger.info(f"Reformulated query: '{original_query}' → '{reformulated}'")

        return {
            "reformulated_query": reformulated,
            "reformulation_count": reformulation_count + 1,
            "nodes_executed": state.get("nodes_executed", []) + ["query_reformulation"],
        }

    async def _fact_extraction_node(self, state: MemoryAugmentedState) -> Dict:
        """
        Extract facts from conversation for storage.

        Args:
            state: Current state

        Returns:
            State updates with extracted facts
        """
        logger.debug("Executing fact extraction")

        # Simple fact extraction heuristics
        query = state["query"]
        facts = []

        # Pattern 1: "My X is Y"
        my_pattern = r"my\s+(\w+)\s+(?:is|are)\s+(.+?)(?:\.|,|$)"
        matches = re.findall(my_pattern, query, re.IGNORECASE)
        for subject, value in matches:
            facts.append(f"User's {subject} is {value}")

        # Pattern 2: "I prefer X"
        prefer_pattern = r"I\s+prefer\s+(.+?)(?:\.|,|$)"
        matches = re.findall(prefer_pattern, query, re.IGNORECASE)
        for preference in matches:
            facts.append(f"User prefers {preference}")

        # Pattern 3: "I'm working on X"
        working_pattern = r"I(?:'m| am)\s+working\s+on\s+(.+?)(?:\.|,|$)"
        matches = re.findall(working_pattern, query, re.IGNORECASE)
        for project in matches:
            facts.append(f"User is working on {project}")

        # Create structured facts for storage
        facts_to_store = [
            {
                "content": fact,
                "metadata": {
                    "type": "extracted_fact",
                    "source_query": query[:100],
                    "conversation_id": state["conversation_id"],
                },
            }
            for fact in facts
        ]

        if facts:
            logger.info(f"Extracted {len(facts)} facts from conversation")
        else:
            logger.debug("No facts extracted from current query")

        return {
            "new_facts": facts,
            "facts_to_store": facts_to_store,
            "nodes_executed": state.get("nodes_executed", []) + ["fact_extraction"],
        }

    async def _context_formatting_node(self, state: MemoryAugmentedState) -> Dict:
        """
        Format memories into context string for LLM prompts.

        Args:
            state: Current state

        Returns:
            State updates with formatted memory context
        """
        logger.debug("Executing context formatting")

        memories = state.get("all_memories", [])

        if not memories:
            memory_context = ""
        else:
            # Format memories with scores and metadata
            memory_lines = []
            for i, mem in enumerate(memories):
                score = mem.get("score", 0)
                content = mem.get("content", "")
                metadata = mem.get("metadata", {})

                # Format with score and source
                source = metadata.get("source", "conversation")
                memory_lines.append(f"[Memory {i+1} | score={score:.2f} | {source}]: {content}")

            memory_context = "\n".join(memory_lines)

        logger.info(f"Formatted memory context: {len(memories)} memories, {len(memory_context)} chars")

        return {
            "memory_context": memory_context,
            "nodes_executed": state.get("nodes_executed", []) + ["context_formatting"],
        }

    def _should_deep_search(self, state: MemoryAugmentedState) -> Literal["deep_search", "fact_extraction"]:
        """
        Decision function: Should we perform deep search?

        Args:
            state: Current state

        Returns:
            Next node name
        """
        # Only deep search once (check if already executed)
        if "deep_search" in state.get("nodes_executed", []):
            logger.debug("Deep search already executed, proceeding to fact extraction")
            return "fact_extraction"

        if state.get("should_deep_search", False):
            logger.debug("Memory insufficient, performing deep search")
            return "deep_search"

        logger.debug("Memory sufficient, proceeding to fact extraction")
        return "fact_extraction"


async def create_memory_graph(
    memory_client: MemoryClient,
    initial_score_threshold: float = 0.75,
    deep_score_threshold: float = 0.60,
    sufficiency_threshold: float = 0.70,
    max_reformulations: int = 2,
) -> MemoryGraph:
    """
    Factory function to create configured memory graph.

    Args:
        memory_client: Memory search client
        initial_score_threshold: Threshold for initial search
        deep_score_threshold: Lower threshold for deep search
        sufficiency_threshold: Minimum score for sufficient memory
        max_reformulations: Maximum query reformulation attempts

    Returns:
        Initialized MemoryGraph
    """
    return MemoryGraph(
        memory_client=memory_client,
        initial_score_threshold=initial_score_threshold,
        deep_score_threshold=deep_score_threshold,
        sufficiency_threshold=sufficiency_threshold,
        max_reformulations=max_reformulations,
    )
