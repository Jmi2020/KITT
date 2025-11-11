"""
F16 Deep Reasoner Agent - Precision reasoning with multi-step chain-of-thought.

Handles complex queries escalated from Q4 router when:
- Confidence < 0.75
- Complexity > 0.7
- Explicit deep reasoning required
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Literal

from langgraph.graph import END, StateGraph

from brain.memory import MemoryClient
from brain.routing.multi_server_client import MultiServerLlamaCppClient
from brain.tools.mcp_client import MCPClient
from common.db.models import RoutingTier

from .states import DeepReasonerState, ToolResult

logger = logging.getLogger(__name__)


class DeepReasonerGraph:
    """
    F16-based deep reasoning agent using LangGraph.

    Workflow:
    1. Context Synthesis: Combine Q4 attempt + memories + tool results
    2. Problem Decomposition: Break complex query into sub-problems
    3. Chain-of-Thought: Multi-step reasoning with explicit steps
    4. Tool Refinement: Re-execute tools with refined parameters
    5. Synthesis: Combine all evidence into comprehensive answer
    6. Self-Evaluation: Assess answer quality and confidence
    7. Response Crafting: Detailed, verified response
    """

    def __init__(
        self,
        llm_client: MultiServerLlamaCppClient,
        memory_client: MemoryClient,
        mcp_client: MCPClient,
        max_reasoning_steps: int = 5,
    ) -> None:
        """
        Initialize deep reasoner graph.

        Args:
            llm_client: Multi-server llama.cpp client (will use F16 alias)
            memory_client: Memory search client
            mcp_client: MCP client for tool execution
            max_reasoning_steps: Maximum chain-of-thought steps
        """
        self.llm = llm_client
        self.memory = memory_client
        self.mcp = mcp_client
        self.max_reasoning_steps = max_reasoning_steps

        # Build graph
        self.graph = self._build_graph()

        logger.info("DeepReasonerGraph initialized with F16 precision reasoning")

    def _build_graph(self) -> StateGraph:
        """Build LangGraph state machine for deep reasoning."""
        workflow = StateGraph(DeepReasonerState)

        # Add nodes
        workflow.add_node("context_synthesis", self._context_synthesis_node)
        workflow.add_node("problem_decomposition", self._problem_decomposition_node)
        workflow.add_node("chain_of_thought", self._chain_of_thought_node)
        workflow.add_node("tool_refinement", self._tool_refinement_node)
        workflow.add_node("evidence_synthesis", self._evidence_synthesis_node)
        workflow.add_node("self_evaluation", self._self_evaluation_node)
        workflow.add_node("response_crafting", self._response_crafting_node)

        # Entry point
        workflow.set_entry_point("context_synthesis")

        # Linear flow through reasoning nodes
        workflow.add_edge("context_synthesis", "problem_decomposition")
        workflow.add_edge("problem_decomposition", "chain_of_thought")

        # Conditional: chain_of_thought → tool_refinement or evidence_synthesis
        workflow.add_conditional_edges(
            "chain_of_thought",
            self._should_refine_tools,
            {
                "tool_refinement": "tool_refinement",
                "evidence_synthesis": "evidence_synthesis",
            },
        )

        workflow.add_edge("tool_refinement", "evidence_synthesis")
        workflow.add_edge("evidence_synthesis", "self_evaluation")

        # Conditional: self_evaluation → retry or response
        workflow.add_conditional_edges(
            "self_evaluation",
            self._should_retry_reasoning,
            {
                "chain_of_thought": "chain_of_thought",  # Retry reasoning
                "response_crafting": "response_crafting",  # Proceed to response
            },
        )

        # End after response
        workflow.add_edge("response_crafting", END)

        return workflow.compile()

    async def run(
        self,
        query: str,
        user_id: str,
        conversation_id: str,
        request_id: str,
        q4_attempt: str | None = None,
        q4_confidence: float = 0.0,
        memories: list | None = None,
        tool_results: Dict[str, ToolResult] | None = None,
        complexity_score: float = 0.0,
    ) -> DeepReasonerState:
        """
        Execute deep reasoning workflow.

        Args:
            query: Original user query
            user_id: User identifier
            conversation_id: Conversation identifier
            request_id: Request identifier
            q4_attempt: Previous Q4 attempt (if any)
            q4_confidence: Q4's confidence score
            memories: Retrieved memories from Qdrant
            tool_results: Previous tool execution results
            complexity_score: Query complexity score

        Returns:
            Final DeepReasonerState with response and metadata
        """
        logger.info(f"Starting deep reasoner for query: {query[:100]}...")

        initial_state: DeepReasonerState = {
            "query": query,
            "original_query": query,
            "user_id": user_id,
            "conversation_id": conversation_id,
            "request_id": request_id,
            "q4_attempt": q4_attempt,
            "q4_confidence": q4_confidence,
            "memories": memories or [],
            "previous_tool_results": tool_results or {},
            "complexity_score": complexity_score,
            "reasoning_steps": [],
            "reasoning_step_count": 0,
            "max_reasoning_steps": self.max_reasoning_steps,
            "sub_problems": [],
            "refined_tool_results": {},
            "evidence": [],
            "self_evaluation_score": 0.0,
            "retry_count": 0,
            "max_retries": 1,
            "nodes_executed": [],
            "total_tokens": 0,
            "cost_usd": 0.0,
            "latency_ms": 0,
        }

        try:
            start_time = time.time()
            final_state = await self.graph.ainvoke(initial_state)
            final_state["latency_ms"] = int((time.time() - start_time) * 1000)

            logger.info(
                f"Deep reasoner completed: confidence={final_state.get('confidence', 0):.2f}, "
                f"reasoning_steps={len(final_state.get('reasoning_steps', []))}, "
                f"latency={final_state['latency_ms']}ms"
            )

            return final_state

        except Exception as exc:
            logger.error(f"Deep reasoner failed: {exc}", exc_info=True)
            return {
                **initial_state,
                "response": f"Deep reasoning error: {exc}",
                "confidence": 0.0,
                "tier_used": RoutingTier.LOCAL,
            }

    async def _context_synthesis_node(self, state: DeepReasonerState) -> Dict:
        """
        Context synthesis node: Combine Q4 attempt + memories + tool results.

        Args:
            state: Current state

        Returns:
            State updates with synthesized context
        """
        logger.debug("Executing context synthesis node")

        context_parts = []

        # Add Q4 attempt if available
        if state.get("q4_attempt"):
            context_parts.append(f"Q4 Attempt (confidence: {state['q4_confidence']:.2f}):\\n{state['q4_attempt']}")

        # Add memories if available
        if state.get("memories"):
            memory_text = "\\n".join([f"- {m.get('content', '')}" for m in state["memories"]])
            context_parts.append(f"Relevant Context:\\n{memory_text}")

        # Add previous tool results if available
        if state.get("previous_tool_results"):
            tool_text = "\\n".join([
                f"- {name}: {result.get('output', result.get('error', 'No result'))}"
                for name, result in state["previous_tool_results"].items()
            ])
            context_parts.append(f"Tool Results:\\n{tool_text}")

        synthesized_context = "\\n\\n".join(context_parts) if context_parts else "No additional context available."

        logger.info(f"Synthesized context from {len(context_parts)} sources")

        return {
            "synthesized_context": synthesized_context,
            "nodes_executed": state.get("nodes_executed", []) + ["context_synthesis"],
        }

    async def _problem_decomposition_node(self, state: DeepReasonerState) -> Dict:
        """
        Problem decomposition node: Break query into sub-problems.

        Args:
            state: Current state

        Returns:
            State updates with sub-problems
        """
        logger.debug("Executing problem decomposition node")

        # Build prompt for F16 to decompose problem
        prompt = f"""<query>
{state['query']}
</query>

<context>
{state.get('synthesized_context', '')}
</context>

<task>
Decompose this query into 2-4 logical sub-problems that need to be solved.
Each sub-problem should be a clear, answerable question.

Format:
1. [First sub-problem]
2. [Second sub-problem]
...
</task>"""

        try:
            # Use F16 model for decomposition
            result = await self.llm.generate(
                prompt=prompt,
                model="kitty-f16",  # F16 alias
            )

            decomposition_text = result.get("response", "")

            # Parse sub-problems (simple line splitting)
            sub_problems = [
                line.strip()[3:]  # Remove "1. " prefix
                for line in decomposition_text.split("\\n")
                if line.strip() and line.strip()[0].isdigit()
            ]

            logger.info(f"Decomposed into {len(sub_problems)} sub-problems")

            return {
                "sub_problems": sub_problems,
                "decomposition_text": decomposition_text,
                "nodes_executed": state.get("nodes_executed", []) + ["problem_decomposition"],
            }

        except Exception as exc:
            logger.error(f"Problem decomposition failed: {exc}")
            return {
                "sub_problems": [state["query"]],  # Fallback: treat whole query as single problem
                "nodes_executed": state.get("nodes_executed", []) + ["problem_decomposition"],
            }

    async def _chain_of_thought_node(self, state: DeepReasonerState) -> Dict:
        """
        Chain-of-thought node: Multi-step reasoning with explicit steps.

        Args:
            state: Current state

        Returns:
            State updates with reasoning steps
        """
        logger.debug("Executing chain-of-thought node")

        reasoning_steps = state.get("reasoning_steps", [])
        step_count = state.get("reasoning_step_count", 0)

        # Build prompt for F16 reasoning
        sub_problems_text = "\\n".join([f"{i+1}. {p}" for i, p in enumerate(state.get("sub_problems", []))])

        prompt = f"""<query>
{state['query']}
</query>

<sub_problems>
{sub_problems_text}
</sub_problems>

<context>
{state.get('synthesized_context', '')}
</context>

<task>
Provide detailed chain-of-thought reasoning to answer this query.
Think step by step, addressing each sub-problem systematically.

Current reasoning step: {step_count + 1}/{state['max_reasoning_steps']}
</task>"""

        try:
            # Use F16 model for deep reasoning
            result = await self.llm.generate(
                prompt=prompt,
                model="kitty-f16",
                tools=None,  # No tools during pure reasoning
            )

            reasoning_text = result.get("response", "")
            reasoning_steps.append({
                "step": step_count + 1,
                "content": reasoning_text,
            })

            logger.info(f"Completed reasoning step {step_count + 1}/{state['max_reasoning_steps']}")

            return {
                "reasoning_steps": reasoning_steps,
                "reasoning_step_count": step_count + 1,
                "nodes_executed": state.get("nodes_executed", []) + ["chain_of_thought"],
            }

        except Exception as exc:
            logger.error(f"Chain-of-thought failed: {exc}")
            return {
                "reasoning_steps": reasoning_steps,
                "reasoning_step_count": step_count + 1,
                "nodes_executed": state.get("nodes_executed", []) + ["chain_of_thought"],
            }

    async def _tool_refinement_node(self, state: DeepReasonerState) -> Dict:
        """
        Tool refinement node: Re-execute tools with refined parameters.

        Args:
            state: Current state

        Returns:
            State updates with refined tool results
        """
        logger.debug("Executing tool refinement node")

        # For now, this is a placeholder for future tool re-execution
        # In Phase 3, this will intelligently retry failed tools or refine parameters

        refined_results = {}
        logger.info("Tool refinement: No tools to refine in current implementation")

        return {
            "refined_tool_results": refined_results,
            "nodes_executed": state.get("nodes_executed", []) + ["tool_refinement"],
        }

    async def _evidence_synthesis_node(self, state: DeepReasonerState) -> Dict:
        """
        Evidence synthesis node: Combine reasoning + tool results into evidence.

        Args:
            state: Current state

        Returns:
            State updates with synthesized evidence
        """
        logger.debug("Executing evidence synthesis node")

        evidence = []

        # Add reasoning steps as evidence
        for step in state.get("reasoning_steps", []):
            evidence.append({
                "type": "reasoning",
                "content": step["content"],
                "weight": 0.8,  # High weight for F16 reasoning
            })

        # Add tool results as evidence
        for tool_name, result in state.get("previous_tool_results", {}).items():
            if result.get("success"):
                evidence.append({
                    "type": "tool_result",
                    "tool": tool_name,
                    "content": result.get("output", ""),
                    "weight": 0.9,  # Very high weight for successful tool results
                })

        # Add refined tool results
        for tool_name, result in state.get("refined_tool_results", {}).items():
            if result.get("success"):
                evidence.append({
                    "type": "refined_tool_result",
                    "tool": tool_name,
                    "content": result.get("output", ""),
                    "weight": 1.0,  # Maximum weight for refined results
                })

        logger.info(f"Synthesized {len(evidence)} pieces of evidence")

        return {
            "evidence": evidence,
            "nodes_executed": state.get("nodes_executed", []) + ["evidence_synthesis"],
        }

    async def _self_evaluation_node(self, state: DeepReasonerState) -> Dict:
        """
        Self-evaluation node: Assess answer quality and confidence.

        Args:
            state: Current state

        Returns:
            State updates with evaluation score
        """
        logger.debug("Executing self-evaluation node")

        # Build summary of reasoning for evaluation
        reasoning_summary = "\\n".join([
            f"Step {i+1}: {step['content'][:200]}..."
            for i, step in enumerate(state.get("reasoning_steps", []))
        ])

        prompt = f"""<query>
{state['query']}
</query>

<reasoning>
{reasoning_summary}
</reasoning>

<evidence>
Collected {len(state.get('evidence', []))} pieces of evidence
</evidence>

<task>
Evaluate the quality of this reasoning on a scale of 0.0 to 1.0:
- 0.0-0.3: Poor reasoning, significant gaps
- 0.4-0.6: Adequate reasoning, some gaps
- 0.7-0.8: Good reasoning, minor gaps
- 0.9-1.0: Excellent reasoning, comprehensive

Provide just the score (e.g., "0.85")
</task>"""

        try:
            # Use F16 for self-evaluation
            result = await self.llm.generate(
                prompt=prompt,
                model="kitty-f16",
            )

            eval_text = result.get("response", "0.5").strip()
            # Extract first float from response
            try:
                eval_score = float(eval_text.split()[0])
                eval_score = max(0.0, min(1.0, eval_score))  # Clamp to [0, 1]
            except ValueError:
                eval_score = 0.5  # Default to medium confidence

            logger.info(f"Self-evaluation score: {eval_score:.2f}")

            return {
                "self_evaluation_score": eval_score,
                "confidence": eval_score,  # Use eval score as confidence
                "nodes_executed": state.get("nodes_executed", []) + ["self_evaluation"],
            }

        except Exception as exc:
            logger.error(f"Self-evaluation failed: {exc}")
            return {
                "self_evaluation_score": 0.5,
                "confidence": 0.5,
                "nodes_executed": state.get("nodes_executed", []) + ["self_evaluation"],
            }

    async def _response_crafting_node(self, state: DeepReasonerState) -> Dict:
        """
        Response crafting node: Create detailed, verified response.

        Args:
            state: Current state

        Returns:
            State updates with final response
        """
        logger.debug("Executing response crafting node")

        # Combine all reasoning into final response prompt
        reasoning_summary = "\\n\\n".join([
            f"**Step {i+1}:**\\n{step['content']}"
            for i, step in enumerate(state.get("reasoning_steps", []))
        ])

        prompt = f"""<query>
{state['query']}
</query>

<reasoning>
{reasoning_summary}
</reasoning>

<evaluation>
Quality score: {state.get('self_evaluation_score', 0.5):.2f}
</evaluation>

<task>
Craft a comprehensive, detailed response to the query based on the reasoning above.
The response should:
- Directly address the user's question
- Be clear and well-structured
- Reference key insights from the reasoning
- Be appropriately detailed given the complexity
</task>"""

        try:
            # Use F16 for final response crafting
            result = await self.llm.generate(
                prompt=prompt,
                model="kitty-f16",
            )

            response_text = result.get("response", "Unable to generate response")

            logger.info(f"Crafted final response: {len(response_text)} chars")

            return {
                "response": response_text,
                "tier_used": RoutingTier.FRONTIER,  # F16 is FRONTIER tier equivalent
                "nodes_executed": state.get("nodes_executed", []) + ["response_crafting"],
            }

        except Exception as exc:
            logger.error(f"Response crafting failed: {exc}")
            return {
                "response": f"Failed to craft response: {exc}",
                "tier_used": RoutingTier.LOCAL,
                "nodes_executed": state.get("nodes_executed", []) + ["response_crafting"],
            }

    def _should_refine_tools(self, state: DeepReasonerState) -> Literal["tool_refinement", "evidence_synthesis"]:
        """
        Decision function: Should we refine tool execution?

        Args:
            state: Current state

        Returns:
            Next node name
        """
        # Check if there are failed tools that could be retried
        has_failed_tools = any(
            not result.get("success", True)
            for result in state.get("previous_tool_results", {}).values()
        )

        if has_failed_tools:
            logger.debug("Routing to tool_refinement (failed tools detected)")
            return "tool_refinement"

        logger.debug("Routing to evidence_synthesis (no tool refinement needed)")
        return "evidence_synthesis"

    def _should_retry_reasoning(
        self, state: DeepReasonerState
    ) -> Literal["chain_of_thought", "response_crafting"]:
        """
        Decision function: Should we retry reasoning?

        Args:
            state: Current state

        Returns:
            Next node name
        """
        retry_count = state.get("retry_count", 0)
        max_retries = state.get("max_retries", 1)
        eval_score = state.get("self_evaluation_score", 0.5)

        # Retry if evaluation is poor and under retry limit
        if eval_score < 0.6 and retry_count < max_retries:
            logger.info(f"Retrying reasoning (eval score: {eval_score:.2f}, attempt {retry_count + 1}/{max_retries})")
            return "chain_of_thought"

        logger.debug("Proceeding to response crafting")
        return "response_crafting"


async def create_deep_reasoner_graph(
    llm_client: MultiServerLlamaCppClient,
    memory_client: MemoryClient,
    mcp_client: MCPClient,
    max_reasoning_steps: int = 5,
) -> DeepReasonerGraph:
    """
    Factory function to create configured deep reasoner graph.

    Args:
        llm_client: Multi-server llama.cpp client (F16)
        memory_client: Memory search client
        mcp_client: MCP tool client
        max_reasoning_steps: Maximum reasoning steps

    Returns:
        Initialized DeepReasonerGraph
    """
    return DeepReasonerGraph(
        llm_client=llm_client,
        memory_client=memory_client,
        mcp_client=mcp_client,
        max_reasoning_steps=max_reasoning_steps,
    )
