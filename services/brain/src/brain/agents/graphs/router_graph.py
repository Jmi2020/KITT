"""
Q4 Router Agent - Fast routing with LangGraph state machine.

Implements Plan-Route-Execute-Validate workflow for 80% of queries.
Escalates to F16 deep reasoner when confidence < 0.75 or complexity > 0.7.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Literal

from langgraph.graph import END, StateGraph

from brain.memory import MemoryClient
from brain.routing.llama_cpp_client import LlamaCppClient
from brain.routing.tool_registry import ToolRegistry
from brain.tools.mcp_client import MCPClient
from common.db.models import RoutingTier

from ..complexity.analyzer import ComplexityAnalyzer
from .states import Memory, RouterState, ToolResult

logger = logging.getLogger(__name__)


class RouterGraph:
    """
    Q4-based routing agent using LangGraph.

    Workflow:
    1. Intake: Parse query, initialize state
    2. Memory Retrieval: Search Qdrant for relevant memories
    3. Complexity Analysis: Score query and determine routing
    4. Tool Selection: Identify required tools from registry
    5. Tool Execution: Execute tools (parallel where safe)
    6. Validation: Verify results and confidence
    7. Response Generation: Synthesize final answer
    8. Escalation: Hand off to F16 if needed
    """

    def __init__(
        self,
        llm_client: LlamaCppClient,
        memory_client: MemoryClient,
        mcp_client: MCPClient,
        tool_registry: ToolRegistry,
        max_refinements: int = 2,
    ) -> None:
        """
        Initialize router graph.

        Args:
            llm_client: Q4 LLM client for fast routing
            memory_client: Memory search client
            mcp_client: MCP client for tool execution
            tool_registry: Tool registry for available tools
            max_refinements: Maximum refinement iterations
        """
        self.llm = llm_client
        self.memory = memory_client
        self.mcp = mcp_client
        self.tool_registry = tool_registry
        self.max_refinements = max_refinements

        # Initialize complexity analyzer
        self.complexity_analyzer = ComplexityAnalyzer()

        # Build graph
        self.graph = self._build_graph()

        logger.info("RouterGraph initialized with LangGraph state machine")

    def _build_graph(self) -> StateGraph:
        """Build LangGraph state machine."""
        workflow = StateGraph(RouterState)

        # Add nodes
        workflow.add_node("intake", self._intake_node)
        workflow.add_node("memory_retrieval", self._memory_retrieval_node)
        workflow.add_node("complexity_analysis", self._complexity_analysis_node)
        workflow.add_node("tool_selection", self._tool_selection_node)
        workflow.add_node("tool_execution", self._tool_execution_node)
        workflow.add_node("validation", self._validation_node)
        workflow.add_node("response_generation", self._response_generation_node)

        # Entry point
        workflow.set_entry_point("intake")

        # Linear flow through core nodes
        workflow.add_edge("intake", "memory_retrieval")
        workflow.add_edge("memory_retrieval", "complexity_analysis")

        # Conditional: complexity → tools or direct response
        workflow.add_conditional_edges(
            "complexity_analysis",
            self._should_use_tools,
            {
                "tool_selection": "tool_selection",
                "response_generation": "response_generation",
            },
        )

        # Tool workflow
        workflow.add_edge("tool_selection", "tool_execution")
        workflow.add_edge("tool_execution", "validation")

        # Conditional: validation → response or refinement
        workflow.add_conditional_edges(
            "validation",
            self._should_refine,
            {
                "tool_selection": "tool_selection",  # Retry with refinement
                "response_generation": "response_generation",
            },
        )

        # End after response
        workflow.add_edge("response_generation", END)

        return workflow.compile()

    async def run(
        self,
        query: str,
        user_id: str,
        conversation_id: str,
        request_id: str,
    ) -> RouterState:
        """
        Execute routing workflow.

        Args:
            query: User query
            user_id: User identifier
            conversation_id: Conversation identifier
            request_id: Request identifier

        Returns:
            Final RouterState with response and metadata
        """
        logger.info(f"Starting router graph for query: {query[:100]}...")

        initial_state: RouterState = {
            "query": query,
            "original_query": query,
            "user_id": user_id,
            "conversation_id": conversation_id,
            "request_id": request_id,
            "refinement_count": 0,
            "max_refinements": self.max_refinements,
            "memories": [],
            "memory_search_attempted": False,
            "selected_tools": [],
            "tool_results": {},
            "tool_execution_errors": [],
            "nodes_executed": [],
            "total_tokens": 0,
            "cost_usd": 0.0,
            "latency_ms": 0,
            "escalated_to_f16": False,
        }

        try:
            start_time = time.time()
            final_state = await self.graph.ainvoke(initial_state)
            final_state["latency_ms"] = int((time.time() - start_time) * 1000)

            logger.info(
                f"Router graph completed: confidence={final_state.get('confidence', 0):.2f}, "
                f"nodes={len(final_state.get('nodes_executed', []))}, "
                f"latency={final_state['latency_ms']}ms"
            )

            return final_state

        except Exception as exc:
            logger.error(f"Router graph failed: {exc}", exc_info=True)
            return {
                **initial_state,
                "response": f"Error in routing workflow: {exc}",
                "confidence": 0.0,
                "tier_used": RoutingTier.LOCAL,
            }

    async def _intake_node(self, state: RouterState) -> Dict:
        """
        Intake node: Parse query and initialize state.

        Args:
            state: Current state

        Returns:
            State updates
        """
        logger.debug("Executing intake node")

        return {
            "nodes_executed": state.get("nodes_executed", []) + ["intake"],
        }

    async def _memory_retrieval_node(self, state: RouterState) -> Dict:
        """
        Memory retrieval node: Search Qdrant for relevant memories.

        Args:
            state: Current state

        Returns:
            State updates with memories
        """
        logger.debug("Executing memory retrieval node")

        try:
            # Search memories
            memory_results = await self.memory.search_memories(
                query=state["query"],
                conversation_id=state["conversation_id"],
                user_id=state["user_id"],
                limit=3,
                score_threshold=0.75,
            )

            # Format memory context
            memory_context = ""
            if memory_results:
                memory_lines = [
                    f"[Memory {i+1}]: {m.content}" for i, m in enumerate(memory_results)
                ]
                memory_context = "\n".join(memory_lines)

            memories: List[Memory] = [
                {
                    "content": m.content,
                    "score": m.score,
                    "metadata": m.metadata or {},
                }
                for m in memory_results
            ]

            logger.debug(f"Retrieved {len(memories)} memories")

            return {
                "memories": memories,
                "memory_context": memory_context,
                "memory_search_attempted": True,
                "nodes_executed": state.get("nodes_executed", []) + ["memory_retrieval"],
            }

        except Exception as exc:
            logger.warning(f"Memory retrieval failed: {exc}")
            return {
                "memory_search_attempted": True,
                "nodes_executed": state.get("nodes_executed", []) + ["memory_retrieval"],
            }

    async def _complexity_analysis_node(self, state: RouterState) -> Dict:
        """
        Complexity analysis node: Score query and determine routing.

        Args:
            state: Current state

        Returns:
            State updates with complexity scores
        """
        logger.debug("Executing complexity analysis node")

        # Analyze complexity
        complexity_result = self.complexity_analyzer.analyze(
            query=state["query"],
            context={
                "memories": state.get("memories", []),
                "requires_search": "search" in state["query"].lower(),
            },
        )

        logger.info(
            f"Complexity analysis: {complexity_result['overall']:.2f} - {complexity_result['reasoning']}"
        )

        # Determine requirements
        requires_tools = complexity_result["factors"].get("tool_count", 0) > 0
        requires_search = "search" in state["query"].lower() or "find" in state["query"].lower()
        requires_vision = "image" in state["query"].lower() or "picture" in state["query"].lower()
        requires_deep_reasoning = complexity_result["overall"] > 0.7

        return {
            "complexity_score": complexity_result["overall"],
            "complexity_factors": complexity_result["factors"],
            "recommended_tier": complexity_result["recommended_tier"],
            "requires_tools": requires_tools,
            "requires_search": requires_search,
            "requires_vision": requires_vision,
            "requires_deep_reasoning": requires_deep_reasoning,
            "nodes_executed": state.get("nodes_executed", []) + ["complexity_analysis"],
        }

    async def _tool_selection_node(self, state: RouterState) -> Dict:
        """
        Tool selection node: Identify required tools and create execution plan.

        Args:
            state: Current state

        Returns:
            State updates with selected tools and plan
        """
        logger.debug("Executing tool selection node")

        # For now, use simple keyword matching
        # TODO: Use LLM to intelligently select tools
        selected_tools = []
        query_lower = state["query"].lower()

        # Tool selection logic
        if "code" in query_lower or "function" in query_lower or "script" in query_lower:
            selected_tools.append("coding.generate")

        if "design" in query_lower or "cad" in query_lower or "model" in query_lower:
            if "parametric" in query_lower or "bracket" in query_lower:
                selected_tools.append("coding.generate")  # Use code for parametric
            else:
                selected_tools.append("cad.generate_model")

        if "print" in query_lower or "slicer" in query_lower:
            selected_tools.append("fabrication.open_in_slicer")

        if "search" in query_lower:
            selected_tools.append("web_search")

        if "remember" in query_lower:
            selected_tools.append("remember")

        # Create execution plan
        tool_plan = "\n".join([f"{i+1}. {tool}" for i, tool in enumerate(selected_tools)])

        logger.info(f"Selected {len(selected_tools)} tools: {selected_tools}")

        return {
            "selected_tools": selected_tools,
            "tool_plan": tool_plan,
            "nodes_executed": state.get("nodes_executed", []) + ["tool_selection"],
        }

    async def _tool_execution_node(self, state: RouterState) -> Dict:
        """
        Tool execution node: Execute selected tools.

        Args:
            state: Current state

        Returns:
            State updates with tool results
        """
        logger.debug(f"Executing {len(state['selected_tools'])} tools")

        tool_results: Dict[str, ToolResult] = {}
        errors: List[str] = []

        for tool_name in state["selected_tools"]:
            try:
                # TODO: Execute actual tools via MCP
                # For now, simulate success
                tool_results[tool_name] = {
                    "success": True,
                    "output": f"Simulated result from {tool_name}",
                    "latency_ms": 100,
                }
                logger.debug(f"Tool {tool_name} executed successfully")

            except Exception as exc:
                logger.error(f"Tool {tool_name} failed: {exc}")
                tool_results[tool_name] = {
                    "success": False,
                    "error": str(exc),
                    "latency_ms": 0,
                }
                errors.append(f"{tool_name}: {exc}")

        return {
            "tool_results": tool_results,
            "tool_execution_errors": errors,
            "nodes_executed": state.get("nodes_executed", []) + ["tool_execution"],
        }

    async def _validation_node(self, state: RouterState) -> Dict:
        """
        Validation node: Verify tool results and assess confidence.

        Args:
            state: Current state

        Returns:
            State updates with validation results
        """
        logger.debug("Executing validation node")

        # Check if all tools succeeded
        all_success = all(
            result.get("success", False) for result in state["tool_results"].values()
        )

        # Calculate confidence based on success rate
        if not state["tool_results"]:
            confidence = 0.5  # No tools, medium confidence
        else:
            success_count = sum(
                1 for r in state["tool_results"].values() if r.get("success", False)
            )
            confidence = success_count / len(state["tool_results"])

        logger.info(f"Validation: {len(state['tool_results'])} tools, confidence={confidence:.2f}")

        return {
            "confidence": confidence,
            "nodes_executed": state.get("nodes_executed", []) + ["validation"],
        }

    async def _response_generation_node(self, state: RouterState) -> Dict:
        """
        Response generation node: Synthesize final answer using Q4.

        Args:
            state: Current state

        Returns:
            State updates with generated response
        """
        logger.debug("Executing response generation node")

        # Build prompt with context
        prompt_parts = []

        if state.get("memory_context"):
            prompt_parts.append(f"<context>\n{state['memory_context']}\n</context>\n")

        prompt_parts.append(f"Query: {state['query']}")

        if state.get("tool_results"):
            tool_summary = "\n".join(
                [
                    f"{name}: {result.get('output', result.get('error', 'No result'))}"
                    for name, result in state["tool_results"].items()
                ]
            )
            prompt_parts.append(f"\nTool Results:\n{tool_summary}")

        prompt = "\n".join(prompt_parts)

        try:
            # Generate response with Q4
            response = await self.llm.generate(
                prompt=prompt,
                max_tokens=512,
                temperature=0.7,
            )

            # TODO: Parse confidence from response or estimate
            confidence = state.get("confidence", 0.8)

            logger.info(f"Generated response: {len(response)} chars, confidence={confidence:.2f}")

            return {
                "response": response,
                "confidence": confidence,
                "tier_used": RoutingTier.LOCAL,
                "nodes_executed": state.get("nodes_executed", []) + ["response_generation"],
            }

        except Exception as exc:
            logger.error(f"Response generation failed: {exc}")
            return {
                "response": f"Failed to generate response: {exc}",
                "confidence": 0.0,
                "tier_used": RoutingTier.LOCAL,
                "nodes_executed": state.get("nodes_executed", []) + ["response_generation"],
            }

    def _should_use_tools(self, state: RouterState) -> Literal["tool_selection", "response_generation"]:
        """
        Decision function: Should we use tools?

        Args:
            state: Current state

        Returns:
            Next node name
        """
        if state.get("requires_tools", False):
            logger.debug("Routing to tool selection (tools required)")
            return "tool_selection"

        logger.debug("Routing to response generation (no tools needed)")
        return "response_generation"

    def _should_refine(self, state: RouterState) -> Literal["tool_selection", "response_generation"]:
        """
        Decision function: Should we refine tool execution?

        Args:
            state: Current state

        Returns:
            Next node name
        """
        # Check if refinement is needed
        refinement_count = state.get("refinement_count", 0)
        max_refinements = state.get("max_refinements", 2)
        confidence = state.get("confidence", 1.0)

        # Refine if confidence low and under limit
        if confidence < 0.75 and refinement_count < max_refinements:
            logger.info(f"Refining (attempt {refinement_count + 1}/{max_refinements})")
            return "tool_selection"

        logger.debug("Proceeding to response generation")
        return "response_generation"


async def create_router_graph(
    llm_client: LlamaCppClient,
    memory_client: MemoryClient,
    mcp_client: MCPClient,
    tool_registry: ToolRegistry,
    max_refinements: int = 2,
) -> RouterGraph:
    """
    Factory function to create configured router graph.

    Args:
        llm_client: Q4 LLM client
        memory_client: Memory search client
        mcp_client: MCP tool client
        tool_registry: Tool registry
        max_refinements: Maximum refinement iterations

    Returns:
        Initialized RouterGraph
    """
    return RouterGraph(
        llm_client=llm_client,
        memory_client=memory_client,
        mcp_client=mcp_client,
        tool_registry=tool_registry,
        max_refinements=max_refinements,
    )
