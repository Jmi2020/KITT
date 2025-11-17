"""
Autonomous Research LangGraph

Defines the state graph that orchestrates autonomous research.
"""

import logging
from typing import Optional
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from .state import ResearchState, create_initial_state
from .nodes import (
    initialize_research,
    decompose_question,
    select_strategy,
    execute_iteration,
    validate_findings,
    score_quality,
    check_stopping,
    synthesize_sub_question,
    synthesize_results,
    handle_error,
)

logger = logging.getLogger(__name__)


class ResearchGraph:
    """
    Wrapper for the research StateGraph.

    Provides:
    - Graph construction
    - Execution interface
    - State management
    """

    def __init__(self, checkpointer: Optional[AsyncPostgresSaver] = None):
        """
        Initialize research graph.

        Args:
            checkpointer: Optional checkpointer for fault tolerance
        """
        self.checkpointer = checkpointer
        self.graph = self._build_graph()
        self.compiled_graph = None

    def _build_graph(self) -> StateGraph:
        """Build the research state graph"""
        # Create graph
        graph = StateGraph(ResearchState)

        # Add nodes
        graph.add_node("initialize", initialize_research)
        graph.add_node("decompose", decompose_question)
        graph.add_node("select_strategy", select_strategy)
        graph.add_node("execute_iteration", execute_iteration)
        graph.add_node("validate", validate_findings)
        graph.add_node("score_quality", score_quality)
        graph.add_node("check_stopping", check_stopping)
        graph.add_node("synthesize_sub_question", synthesize_sub_question)
        graph.add_node("synthesize", synthesize_results)
        graph.add_node("handle_error", handle_error)

        # Define edges
        # 1. Start with initialization
        graph.set_entry_point("initialize")

        # 2. After initialization, decompose question (hierarchical mode will handle it)
        graph.add_edge("initialize", "decompose")

        # 3. After decomposition, select strategy
        graph.add_edge("decompose", "select_strategy")

        # 4. After strategy selection, execute iteration
        graph.add_edge("select_strategy", "execute_iteration")

        # 5. After execution, validate findings
        graph.add_edge("execute_iteration", "validate")

        # 6. After validation, score quality
        graph.add_edge("validate", "score_quality")

        # 7. After scoring, check stopping criteria
        graph.add_edge("score_quality", "check_stopping")

        # 8. Conditional routing from stopping check
        graph.add_conditional_edges(
            "check_stopping",
            self._should_continue,
            {
                "continue": "select_strategy",           # Loop back for next iteration
                "synthesize_sub_question": "synthesize_sub_question",  # Synthesize current sub-question
                "synthesize": "synthesize",              # Move to final synthesis
                "error": "handle_error"                  # Handle error
            }
        )

        # 9. After sub-question synthesis, go back to select next sub-question
        graph.add_edge("synthesize_sub_question", "select_strategy")

        # 10. After final synthesis, end
        graph.add_edge("synthesize", END)

        # 11. After error handling, end
        graph.add_edge("handle_error", END)

        logger.info("Research graph built successfully")

        return graph

    def _should_continue(self, state: ResearchState) -> str:
        """
        Conditional routing based on stopping criteria.

        Returns:
            "continue" - Continue research
            "synthesize_sub_question" - Synthesize current sub-question (hierarchical mode)
            "synthesize" - Stop and synthesize final result
            "error" - Handle error
        """
        # Safety check: Force stop if iteration exceeds max_iterations
        # This prevents infinite loops if stopping criteria fail to trigger
        current_iteration = state.get("current_iteration", 0)
        max_iterations = state.get("config", {}).get("max_iterations", 15)

        if current_iteration >= max_iterations:
            logger.warning(
                f"Max iterations ({max_iterations}) reached, forcing synthesis"
            )
            return "synthesize"

        # Check for errors
        if state.get("last_error"):
            logger.warning("Error detected, routing to error handler")
            return "error"

        # Check stopping decision
        stopping_decision = state.get("stopping_decision")

        if not stopping_decision:
            # No decision yet, continue
            # Log this as it may indicate check_stopping node failed
            logger.warning(
                f"No stopping decision at iteration {current_iteration}, continuing"
            )
            return "continue"

        should_stop = stopping_decision.get("should_stop", False)
        explanation = stopping_decision.get("explanation", "")

        # Check if in hierarchical mode
        is_hierarchical = (
            state.get("sub_questions") and
            state.get("config", {}).get("enable_hierarchical", False)
        )

        if is_hierarchical:
            # Check if current sub-question is ready for synthesis
            current_sq_id = state.get("current_sub_question_id")

            if current_sq_id and not should_stop:
                # Sub-question research continuing
                # Check explanation for synthesis signal
                if "ready for synthesis" in explanation.lower():
                    logger.info(f"Sub-question {current_sq_id} ready for synthesis")
                    return "synthesize_sub_question"

            if should_stop:
                # Check if all sub-questions are done
                all_completed = all(
                    sq.get("status") == "completed"
                    for sq in state.get("sub_questions", [])
                )

                if all_completed:
                    logger.info("All sub-questions complete, moving to final synthesis")
                    return "synthesize"
                else:
                    # Some sub-questions still pending, continue
                    logger.info("Some sub-questions pending, continuing")
                    return "continue"

        # Standard flat mode or hierarchical final synthesis
        if should_stop:
            logger.info("Stopping criteria met, moving to synthesis")
            return "synthesize"
        else:
            logger.info("Continuing research")
            return "continue"

    def compile(self):
        """Compile the graph with checkpointer"""
        if self.checkpointer:
            self.compiled_graph = self.graph.compile(checkpointer=self.checkpointer)
            logger.info("Graph compiled with checkpointer")
        else:
            self.compiled_graph = self.graph.compile()
            logger.info("Graph compiled without checkpointer")

        return self.compiled_graph

    async def run(
        self,
        session_id: str,
        user_id: str,
        query: str,
        config: Optional[dict] = None
    ) -> ResearchState:
        """
        Run autonomous research.

        Args:
            session_id: Session ID
            user_id: User ID
            query: Research query
            config: Optional configuration

        Returns:
            Final ResearchState
        """
        if not self.compiled_graph:
            self.compile()

        # Create initial state
        initial_state = create_initial_state(
            session_id=session_id,
            user_id=user_id,
            query=query,
            config=config
        )

        # Prepare config for LangGraph
        # Calculate recursion_limit dynamically based on max_iterations
        # Formula: (max_iterations + buffer) × nodes_per_iteration
        # Each iteration uses ~5-6 nodes (select_strategy, execute, validate, score, check_stopping)
        # Add buffer for initialization, synthesis, and error handling
        max_iterations = config.get("max_iterations", 15) if config else 15
        recursion_limit = (max_iterations + 3) * 6  # 3-iteration buffer for safety

        graph_config = {
            "configurable": {
                "thread_id": f"research_{session_id}"
            },
            "recursion_limit": recursion_limit
        }

        logger.info(
            f"Starting research for session {session_id} "
            f"(max_iterations={max_iterations}, recursion_limit={recursion_limit})"
        )

        # Run graph and accumulate state
        # astream yields {node_name: partial_state} for each node
        # We need to accumulate to get the full final state
        full_state = initial_state.copy()
        async for state_update in self.compiled_graph.astream(initial_state, config=graph_config):
            # Log progress
            if isinstance(state_update, dict):
                for node_name, node_state in state_update.items():
                    logger.debug(f"Node '{node_name}' completed")
                    # Merge node state into full state
                    if isinstance(node_state, dict):
                        full_state.update(node_state)

        logger.info(f"Research completed for session {session_id}")
        logger.info(f"Final state has {len(full_state.get('findings', []))} findings, {len(full_state.get('sources', []))} sources")

        return full_state

    async def stream(
        self,
        session_id: str,
        user_id: str,
        query: str,
        config: Optional[dict] = None
    ):
        """
        Stream research progress.

        Yields state updates as research progresses.

        Args:
            session_id: Session ID
            user_id: User ID
            query: Research query
            config: Optional configuration

        Yields:
            State updates
        """
        if not self.compiled_graph:
            self.compile()

        # Create initial state
        initial_state = create_initial_state(
            session_id=session_id,
            user_id=user_id,
            query=query,
            config=config
        )

        # Prepare config for LangGraph
        # Calculate recursion_limit dynamically based on max_iterations
        max_iterations = config.get("max_iterations", 15) if config else 15
        recursion_limit = (max_iterations + 3) * 6  # 3-iteration buffer for safety

        graph_config = {
            "configurable": {
                "thread_id": f"research_{session_id}"
            },
            "recursion_limit": recursion_limit
        }

        logger.info(
            f"Starting streaming research for session {session_id} "
            f"(max_iterations={max_iterations}, recursion_limit={recursion_limit})"
        )

        # Stream graph execution
        async for state in self.compiled_graph.astream(initial_state, config=graph_config):
            yield state

        logger.info(f"Streaming research completed for session {session_id}")

    async def resume(
        self,
        session_id: str,
        additional_input: Optional[dict] = None
    ) -> ResearchState:
        """
        Resume research from checkpoint.

        Args:
            session_id: Session ID to resume
            additional_input: Optional additional input

        Returns:
            Final ResearchState
        """
        if not self.compiled_graph:
            self.compile()

        if not self.checkpointer:
            raise ValueError("Cannot resume without checkpointer")

        # Get latest checkpoint first to extract config
        temp_config = {
            "configurable": {
                "thread_id": f"research_{session_id}"
            }
        }
        checkpoint = await self.checkpointer.aget(temp_config)

        if not checkpoint:
            raise ValueError(f"No checkpoint found for session {session_id}")

        # Extract max_iterations from checkpoint state to calculate recursion limit
        checkpoint_state = checkpoint.get("channel_values", {})
        max_iterations = checkpoint_state.get("config", {}).get("max_iterations", 15)
        recursion_limit = (max_iterations + 3) * 6  # 3-iteration buffer for safety

        # Prepare final config with calculated recursion limit
        graph_config = {
            "configurable": {
                "thread_id": f"research_{session_id}"
            },
            "recursion_limit": recursion_limit
        }

        logger.info(
            f"Resuming research for session {session_id} "
            f"(max_iterations={max_iterations}, recursion_limit={recursion_limit})"
        )

        # Resume from checkpoint
        resume_input = additional_input or {}

        final_state = None
        async for state in self.compiled_graph.astream(resume_input, config=graph_config):
            final_state = state

        logger.info(f"Research resumed and completed for session {session_id}")

        return final_state


def build_research_graph(checkpointer: Optional[AsyncPostgresSaver] = None) -> ResearchGraph:
    """
    Build and return a ResearchGraph instance.

    Args:
        checkpointer: Optional AsyncPostgresSaver for fault tolerance

    Returns:
        ResearchGraph instance
    """
    graph = ResearchGraph(checkpointer=checkpointer)
    graph.compile()
    return graph
