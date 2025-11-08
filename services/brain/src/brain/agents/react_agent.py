# noqa: D401
"""ReAct (Reasoning + Acting) agent controller for tool-aware workflows."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from brain.routing.llama_cpp_client import LlamaCppClient
from brain.routing.tool_validator import ToolCallValidator
from brain.tools.mcp_client import MCPClient
from brain.tools.model_config import detect_model_format
from brain.logging_config import log_agent_step
from brain.prompts.unified import KittySystemPrompt

from .prompt_templates import get_tool_call_examples

logger = logging.getLogger("brain.agent")


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
    truncated: bool = False
    stop_reason: Optional[str] = None


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
        # Keep a dedicated reference for direct tool execution / fallbacks
        self._tool_mcp = mcp_client
        self._max_iterations = max_iterations
        self._history_window = max(int(os.getenv("AGENT_HISTORY_STEPS", "4")), 0)
        self._observation_limit = max(int(os.getenv("AGENT_OBSERVATION_CHARS", "2000")), 256)

        # Detect model format for tool calling (default to Qwen if not specified)
        self._model_format = detect_model_format(model_alias or "qwen2.5")
        logger.info(f"ReAct agent initialized with format: {self._model_format.value}")

        # Initialize unified prompt builder
        self._prompt_builder = KittySystemPrompt()

    def _build_react_prompt(
        self,
        query: str,
        tools: List[Dict[str, Any]],
        history: List[AgentStep],
        freshness_required: bool = False,
    ) -> str:
        """Build ReAct prompt with query, tools, and history.

        Args:
            query: User query
            tools: Available tools
            history: Previous reasoning steps

        Returns:
            Formatted ReAct prompt using unified KittySystemPrompt
        """
        # Format history for context
        history_text = ""
        for i, step in enumerate(history, 1):
            history_text += f"\nIteration {i}:\n"
            history_text += f"Thought: {step.thought}\n"
            if step.action:
                history_text += f"Action: {step.action}\n"
                history_text += f"Action Input: {step.action_input}\n"
                history_text += f"Observation: {step.observation}\n"

        # Add history to context if exists
        context = None
        if history_text:
            context = f"Previous reasoning steps:{history_text}"

        # Use unified prompt builder with agent mode
        prompt = self._prompt_builder.build(
            mode="agent",
            tools=tools,
            verbosity=3,  # Default to detailed verbosity for agent mode
            model_format=self._model_format.value,
            context=context,
            query=query,
            freshness_required=freshness_required,
        )

        return prompt

    def _history_for_prompt(self, history: List[AgentStep]) -> List[AgentStep]:
        """Limit history injected into the prompt to avoid blowing context."""
        if self._history_window <= 0 or len(history) <= self._history_window:
            return history
        return history[-self._history_window :]

    def _summarize_tool_observation(self, action: str, result: Dict[str, Any]) -> str:
        """Condense tool output so we do not exceed llama.cpp context limits."""
        if not result.get("success"):
            message = result.get("error") or "unknown error"
            return self._truncate_observation(f"{action} failed: {message}")

        data = result.get("data")
        if isinstance(data, dict):
            metadata = data.get("metadata") or {}
            provider = metadata.get("provider") or (result.get("metadata") or {}).get("server")
            prefix = f"{action} via {provider}" if provider else action

            results = data.get("results")
            if isinstance(results, list) and results:
                snippets = []
                for item in results[:3]:
                    title = (item.get("title") or item.get("url") or "untitled").strip()
                    source = item.get("source") or ""
                    entry = title
                    if source:
                        entry += f" ({source})"
                    snippets.append(entry[:120])
                summary = "; ".join(snippets)
                total = data.get("total_results")
                if isinstance(total, int):
                    summary = f"{summary} (total {total})"
                return self._truncate_observation(f"{prefix}: {summary}")

            return self._truncate_observation(f"{prefix}: {str(data)[:300]}")

        if isinstance(data, list):
            preview = "; ".join(str(item) for item in data[:3])
            return self._truncate_observation(f"{action} returned list: {preview}")

        return self._truncate_observation(f"{action} success: {str(data)}")

    def _truncate_observation(self, text: str) -> str:
        if len(text) <= self._observation_limit:
            return text
        return text[: self._observation_limit - 3] + "..."

    async def run(
        self, query: str, freshness_required: bool = False, allow_paid: bool = True
    ) -> AgentResult:
        """Execute ReAct loop to answer query.

        Args:
            query: User question

        Returns:
            Agent result with answer and reasoning steps
        """
        # Get available tools
        tools = self._mcp.get_tools_for_prompt()
        if not allow_paid:
            tools = [
                tool
                for tool in tools
                if tool.get("function", {}).get("name") not in {"research_deep"}
            ]
        if freshness_required:
            research_only = [tool for tool in tools if tool.get("server") == "research"]
            if research_only:
                tools = research_only

        if not tools:
            # No tools available - just answer directly
            response = await self._llm.generate(query)
            return AgentResult(
                answer=response["response"],
                steps=[],
                success=True,
                iterations=0,
                truncated=response.get("truncated", False),
                stop_reason=response.get("stop_type"),
            )

        # ReAct loop
        history: List[AgentStep] = []

        tools_used = 0

        truncated_flag = False
        stop_reason: Optional[str] = None

        for iteration in range(self._max_iterations):
            logger.info(f"ReAct iteration {iteration + 1}/{self._max_iterations}")

            # Build prompt with current history
            prompt_history = self._history_for_prompt(history)
            prompt = self._build_react_prompt(
                query, tools, prompt_history, freshness_required=freshness_required
            )

            # Get LLM response with tools
            response = await self._llm.generate(prompt=prompt, tools=tools)
            if response.get("truncated"):
                truncated_flag = True
            if response.get("stop_type"):
                stop_reason = response.get("stop_type")

            # Parse response
            text = response["response"]
            tool_calls = response["tool_calls"]

            # Extract thought
            thought = text.strip()

            # Check for tool calls
            if tool_calls:
                tool_call = tool_calls[0]  # Use first tool call
                action = tool_call.name
                action_input = tool_call.arguments

                # Validate tool call before execution
                validator = ToolCallValidator(tools)
                validation = validator.validate_tool_call(action, action_input)

                if not validation.valid:
                    # Validation failed - use error as observation to guide model
                    observation = f"Tool call validation failed: {validation.error_message}"
                    logger.warning(f"Invalid tool call: {action}({action_input}) - {validation.error_message}")

                else:
                    # Validation passed - execute tool
                    logger.info(f"Executing tool: {action}({action_input})")

                    try:
                        result = await self._mcp.execute_tool(action, action_input)
                        observation = self._summarize_tool_observation(action, result)
                    except Exception as e:
                        logger.error(f"Tool execution failed: {e}")
                        observation = self._truncate_observation(f"Tool execution failed: {str(e)}")

                # Log agent step with action
                log_agent_step(
                    logger=logger,
                    iteration=iteration + 1,
                    thought=thought,
                    action=f"{action}({action_input})",
                    observation=observation,
                    model=self._model_format.value,
                )

                # Record step
                history.append(
                    AgentStep(
                        thought=thought,
                        action=action,
                        action_input=action_input,
                        observation=observation,
                    )
                )
                tools_used += 1
                # Run next iteration to let the model observe tool output before answering
                continue

            # Check if final answer (only when no tool call to execute)
            if "Final Answer:" in text:
                if freshness_required and tools_used == 0 and self._tool_mcp:
                    logger.info("Freshness required but no tools used; forcing web_search fallback.")
                    try:
                        forced = await self._tool_mcp.execute_tool("web_search", {"query": query})
                        observation = self._summarize_tool_observation("web_search", forced)
                    except Exception as exc:  # noqa: BLE001
                        observation = f"Forced web_search failed: {exc}"
                        logger.error(observation)
                        observation = self._truncate_observation(observation)

                    log_agent_step(
                        logger=logger,
                        iteration=iteration + 1,
                        thought=thought,
                        action="web_search({'query': query})",
                        observation=observation,
                        model=self._model_format.value,
                    )
                    history.append(
                        AgentStep(
                            thought="Forced web_search due to freshness requirement.",
                            action="web_search",
                            action_input={"query": query},
                            observation=observation,
                        )
                    )
                    tools_used += 1
                    continue

                if tools_used > 0 or not freshness_required:
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
                        truncated=truncated_flag,
                        stop_reason=stop_reason,
                    )
                continue

            else:
                # No tool call and no final answer - just reasoning
                # Log agent step without action
                log_agent_step(
                    logger=logger,
                    iteration=iteration + 1,
                    thought=thought,
                    action=None,
                    observation=None,
                    model=self._model_format.value,
                )

                history.append(
                    AgentStep(
                        thought=thought,
                    )
                )

        if freshness_required and tools_used == 0 and self._tool_mcp:
            logger.info("Max iterations reached without tool usage; forcing final web_search.")
            forced = await self.run_single_action(query, "web_search", {"query": query})
            forced.steps = history + forced.steps
            forced.iterations = self._max_iterations
            return forced

        # Max iterations reached
        return AgentResult(
            answer="Maximum reasoning iterations reached without finding an answer.",
            steps=history,
            success=False,
            error="Max iterations exceeded",
            iterations=self._max_iterations,
            truncated=truncated_flag,
            stop_reason=stop_reason,
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
            result = await self._tool_mcp.execute_tool(tool_name, tool_args)

            success = bool(result.get("success"))
            observation = self._summarize_tool_observation(tool_name, result)
            error = result.get("error") if not success else None

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
