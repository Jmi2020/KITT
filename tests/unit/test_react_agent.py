# ruff: noqa: E402
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT / "services/common/src"))
sys.path.append(str(ROOT / "services/brain/src"))

os.environ.setdefault("SETTINGS_MODULE", "services.common.config")

pytest.importorskip("pydantic_settings")

from brain.agents.react_agent import AgentStep, ReActAgent  # type: ignore[import]
from brain.tools.parser import ToolCall  # type: ignore[import]


class DummyLlamaClient:
    def __init__(self, responses: List[Dict[str, Any]]) -> None:
        self._responses = responses
        self.call_count = 0

    async def generate(self, prompt: str, tools: List[Dict[str, Any]] | None = None) -> Dict[str, Any]:
        if self.call_count >= len(self._responses):
            raise AssertionError("No more mock responses available")
        response = self._responses[self.call_count]
        self.call_count += 1
        return response


class DummyMCPClient:
    def __init__(self) -> None:
        self.executed: List[Dict[str, Any]] = []
        self._tools = [
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "Search the public web for fresh information.",
                    "parameters": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                    },
                },
                "server": "research",
            }
        ]

    def get_tools_for_prompt(self) -> List[Dict[str, Any]]:
        return self._tools

    async def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        self.executed.append({"tool": tool_name, "arguments": arguments})
        return {
            "success": True,
            "data": {"hits": [{"title": "Mock result", "url": "https://example.com"}]},
            "error": None,
            "metadata": {"tool": tool_name},
        }


def _tool_call(name: str, **arguments: Any) -> ToolCall:
    return ToolCall(name=name, arguments=arguments, raw_xml="<tool_call />")


@pytest.mark.asyncio
async def test_agent_executes_tool_even_with_inline_final_answer():
    """Ensure tool calls run before honoring a Final Answer."""
    llama = DummyLlamaClient(
        responses=[
            {
                "response": "Thought: I should search.\nFinal Answer: Placeholder text",
                "tool_calls": [_tool_call("web_search", query="3I/ATLAS distance")],
                "raw": {},
            },
            {
                "response": "Thought: Summarize findings.\nFinal Answer: 3I/ATLAS passed about 76 million miles from Earth.",
                "tool_calls": [],
                "raw": {},
            },
        ]
    )
    mcp = DummyMCPClient()
    agent = ReActAgent(llm_client=llama, mcp_client=mcp, max_iterations=3, model_alias="qwen2.5")

    result = await agent.run("How close did 3I/ATLAS get to Earth?", freshness_required=True)

    assert llama.call_count == 2, "Agent should re-query after running a tool"
    assert len(mcp.executed) == 1
    assert mcp.executed[0]["tool"] == "web_search"
    assert result.success
    assert any(step.action == "web_search" for step in result.steps)
    assert "76 million miles" in result.answer


@pytest.mark.asyncio
async def test_agent_forces_web_search_when_no_tool_used():
    """Freshness-required questions should trigger a fallback search."""
    llama = DummyLlamaClient(
        responses=[
            {
                "response": "Thought: Maybe I already know this.\nFinal Answer: It was around 70 million miles.",
                "tool_calls": [],
                "raw": {},
            },
            {
                "response": "Thought: After searching I can answer.\nFinal Answer: Verified distance was 76 million miles.",
                "tool_calls": [],
                "raw": {},
            },
        ]
    )
    mcp = DummyMCPClient()
    agent = ReActAgent(llm_client=llama, mcp_client=mcp, max_iterations=3, model_alias="qwen2.5")

    result = await agent.run("Need latest comet pass distance", freshness_required=True)

    assert llama.call_count == 2
    assert len(mcp.executed) == 1, "Forced fallback should run web_search once"
    assert result.success
    assert any(step.action == "web_search" for step in result.steps)


def test_history_window_trims_prompt_history():
    llama = DummyLlamaClient(responses=[])
    mcp = DummyMCPClient()
    agent = ReActAgent(llm_client=llama, mcp_client=mcp, max_iterations=1, model_alias="qwen2.5")
    agent._history_window = 2

    history = [
        AgentStep(thought="first"),
        AgentStep(thought="second"),
        AgentStep(thought="third"),
    ]

    trimmed = agent._history_for_prompt(history)
    assert len(trimmed) == 2
    assert [step.thought for step in trimmed] == ["second", "third"]
