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
    select_strategy,
    execute_iteration,
    validate_findings,
    score_quality,
    check_stopping,
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
        graph.add_node("select_strategy", select_strategy)
        graph.add_node("execute_iteration", execute_iteration)
        graph.add_node("validate", validate_findings)
        graph.add_node("score_quality", score_quality)
        graph.add_node("check_stopping", check_stopping)
        graph.add_node("synthesize", synthesize_results)
        graph.add_node("handle_error", handle_error)

        # Define edges
        # 1. Start with initialization
        graph.set_entry_point("initialize")

        # 2. After initialization, select strategy
        graph.add_edge("initialize", "select_strategy")

        # 3. After strategy selection, execute iteration
        graph.add_edge("select_strategy", "execute_iteration")

        # 4. After execution, validate findings
        graph.add_edge("execute_iteration", "validate")

        # 5. After validation, score quality
        graph.add_edge("validate", "score_quality")

        # 6. After scoring, check stopping criteria
        graph.add_edge("score_quality", "check_stopping")

        # 7. Conditional routing from stopping check
        graph.add_conditional_edges(
            "check_stopping",
            self._should_continue,
            {
                "continue": "select_strategy",  # Loop back for next iteration
                "synthesize": "synthesize",      # Move to synthesis
                "error": "handle_error"          # Handle error
            }
        )

        # 8. After synthesis, end
        graph.add_edge("synthesize", END)

        # 9. After error handling, end
        graph.add_edge("handle_error", END)

        logger.info("Research graph built successfully")

        return graph

    def _should_continue(self, state: ResearchState) -> str:
        """
        Conditional routing based on stopping criteria.

        Returns:
            "continue" - Continue research
            "synthesize" - Stop and synthesize
            "error" - Handle error
        """
        # Check for errors
        if state.get("last_error"):
            logger.warning("Error detected, routing to error handler")
            return "error"

        # Check stopping decision
        stopping_decision = state.get("stopping_decision")

        if not stopping_decision:
            # No decision yet, continue
            return "continue"

        should_stop = stopping_decision.get("should_stop", False)

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
        graph_config = {
            "configurable": {
                "thread_id": f"research_{session_id}"
            }
        }

        logger.info(f"Starting research for session {session_id}")

        # Run graph
        final_state = None
        async for state in self.compiled_graph.astream(initial_state, config=graph_config):
            final_state = state
            # Log progress
            if isinstance(state, dict):
                for node_name, node_state in state.items():
                    logger.debug(f"Node '{node_name}' completed")

        logger.info(f"Research completed for session {session_id}")

        return final_state

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
        graph_config = {
            "configurable": {
                "thread_id": f"research_{session_id}"
            }
        }

        logger.info(f"Starting streaming research for session {session_id}")

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

        # Prepare config
        graph_config = {
            "configurable": {
                "thread_id": f"research_{session_id}"
            }
        }

        logger.info(f"Resuming research for session {session_id}")

        # Get latest checkpoint
        checkpoint = await self.checkpointer.aget(graph_config)

        if not checkpoint:
            raise ValueError(f"No checkpoint found for session {session_id}")

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
