# noqa: D401
"""ReAct (Reasoning + Acting) agent controller for tool-aware workflows."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from brain.routing.llama_cpp_client import LlamaCppClient
from brain.tools.mcp_client import MCPClient
from brain.tools.model_config import detect_model_format

from .prompt_templates import get_tool_call_examples

logger = logging.getLogger(__name__)


@dataclass
class AgentStep:
    """A single step in the ReAct loop."""

    thought: str
    action: Optional[str] = None
    action_input: Optional[Dict[str, Any]] = None
    observation: Optional[str] = None
    is_final: bool = False


@dataclass
class AgentResult:
    """Final result from agent execution."""

    answer: str
    steps: List[AgentStep]
    success: bool
    error: Optional[str] = None
    iterations: int = 0


class ReActAgent:
    """ReAct agent implementing iterative reasoning and tool use."""

    def __init__(
        self,
        llm_client: LlamaCppClient,
        mcp_client: MCPClient,
        max_iterations: int = 10,
        model_alias: Optional[str] = None,
    ) -> None:
        """Initialize ReAct agent.

        Args:
            llm_client: LLM client for reasoning
            mcp_client: MCP client for tool execution
            max_iterations: Maximum reasoning iterations
            model_alias: Optional model identifier for format detection (e.g., "kitty-coder")
        """
        self._llm = llm_client
        self._mcp = mcp_client
        self._max_iterations = max_iterations

        # Detect model format for tool calling (default to Qwen if not specified)
        self._model_format = detect_model_format(model_alias or "qwen2.5")
        logger.info(f"ReAct agent initialized with format: {self._model_format.value}")

    def _build_react_prompt(
        self, query: str, tools: List[Dict[str, Any]], history: List[AgentStep]
    ) -> str:
        """Build ReAct prompt with query, tools, and history.

        Args:
            query: User query
            tools: Available tools
            history: Previous reasoning steps

        Returns:
            Formatted ReAct prompt
        """
        # Format tools
        tools_desc = []
        for tool in tools:
            func = tool["function"]
            tools_desc.append(f"- {func['name']}: {func['description']}")

        tools_text = "\n".join(tools_desc)

        # Format history
        history_text = ""
        for i, step in enumerate(history, 1):
            history_text += f"\nIteration {i}:\n"
            history_text += f"Thought: {step.thought}\n"
            if step.action:
                history_text += f"Action: {step.action}\n"
                history_text += f"Action Input: {step.action_input}\n"
                history_text += f"Observation: {step.observation}\n"

        # Get model-specific tool call examples
        tool_examples = get_tool_call_examples(self._model_format)

        prompt = f"""You are an AI assistant with access to tools. Answer the user's question by reasoning step-by-step and using tools when needed.

Available Tools:
{tools_text}

{tool_examples}

When you have enough information to answer:
Thought: I now know the final answer
Final Answer: [your answer to the user]

User Question: {query}
{history_text}
"""
        return prompt

    async def run(self, query: str) -> AgentResult:
        """Execute ReAct loop to answer query.

        Args:
            query: User question

        Returns:
            Agent result with answer and reasoning steps
        """
        # Get available tools
        tools = self._mcp.get_tools_for_prompt()

        if not tools:
            # No tools available - just answer directly
            response = await self._llm.generate(query)
            return AgentResult(
                answer=response["response"],
                steps=[],
                success=True,
                iterations=0,
            )

        # ReAct loop
        history: List[AgentStep] = []

        for iteration in range(self._max_iterations):
            logger.info(f"ReAct iteration {iteration + 1}/{self._max_iterations}")

            # Build prompt with current history
            prompt = self._build_react_prompt(query, tools, history)

            # Get LLM response with tools
            response = await self._llm.generate(prompt=prompt, tools=tools)

            # Parse response
            text = response["response"]
            tool_calls = response["tool_calls"]

            # Extract thought
            thought = text.strip()

            # Check if final answer
            if "Final Answer:" in text:
                # Extract final answer
                final_answer = text.split("Final Answer:")[-1].strip()
                history.append(
                    AgentStep(
                        thought=thought,
                        is_final=True,
                    )
                )
                return AgentResult(
                    answer=final_answer,
                    steps=history,
                    success=True,
                    iterations=iteration + 1,
                )

            # Check for tool calls
            if tool_calls:
                tool_call = tool_calls[0]  # Use first tool call
                action = tool_call.name
                action_input = tool_call.arguments

                logger.info(f"Executing tool: {action}({action_input})")

                # Execute tool
                try:
                    result = await self._mcp.execute_tool(action, action_input)

                    if result["success"]:
                        observation = f"Success: {result['data']}"
                    else:
                        observation = f"Error: {result['error']}"

                except Exception as e:
                    logger.error(f"Tool execution failed: {e}")
                    observation = f"Tool execution failed: {str(e)}"

                # Record step
                history.append(
                    AgentStep(
                        thought=thought,
                        action=action,
                        action_input=action_input,
                        observation=observation,
                    )
                )

            else:
                # No tool call and no final answer - just reasoning
                history.append(
                    AgentStep(
                        thought=thought,
                    )
                )

        # Max iterations reached
        return AgentResult(
            answer="Maximum reasoning iterations reached without finding an answer.",
            steps=history,
            success=False,
            error="Max iterations exceeded",
            iterations=self._max_iterations,
        )

    async def run_single_action(
        self, query: str, tool_name: str, tool_args: Dict[str, Any]
    ) -> AgentResult:
        """Execute a single tool action without ReAct loop.

        Args:
            query: User query
            tool_name: Tool to execute
            tool_args: Tool arguments

        Returns:
            Agent result
        """
        try:
            result = await self._mcp.execute_tool(tool_name, tool_args)

            if result["success"]:
                observation = f"Success: {result['data']}"
                success = True
                error = None
            else:
                observation = f"Error: {result['error']}"
                success = False
                error = result["error"]

            step = AgentStep(
                thought=f"Executing {tool_name}",
                action=tool_name,
                action_input=tool_args,
                observation=observation,
            )

            return AgentResult(
                answer=observation,
                steps=[step],
                success=success,
                error=error,
                iterations=1,
            )

        except Exception as e:
            logger.error(f"Single action execution failed: {e}")
            return AgentResult(
                answer=f"Failed to execute {tool_name}: {str(e)}",
                steps=[],
                success=False,
                error=str(e),
                iterations=1,
            )


__all__ = ["ReActAgent", "AgentStep", "AgentResult"]
