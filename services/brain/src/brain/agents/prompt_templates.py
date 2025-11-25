# noqa: D401
"""Model-specific prompt templates for tool calling."""

from __future__ import annotations

from ..tools.model_config import ToolCallFormat


def get_tool_call_examples(format_type: ToolCallFormat) -> str:
    """Return model-specific tool call examples and instructions.

    Args:
        format_type: Tool calling format for the model

    Returns:
        String containing format-specific instructions and examples
    """
    if format_type == ToolCallFormat.QWEN_XML:
        return _get_qwen_xml_examples()
    elif format_type == ToolCallFormat.LLAMA_JSON:
        return _get_llama_json_examples()
    elif format_type == ToolCallFormat.ATHENE_JSON:
        return _get_athene_json_examples()
    elif format_type == ToolCallFormat.MISTRAL_JSON:
        return _get_mistral_json_examples()
    elif format_type == ToolCallFormat.GEMMA_FUNCTION:
        return _get_gemma_function_examples()
    else:
        # Generic fallback (tries multiple formats)
        return _get_generic_examples()


def _get_qwen_xml_examples() -> str:
    """Get Qwen2.5/3 XML format examples."""
    return """IMPORTANT: When you need to use a tool, output EXACTLY this XML format:
<tool_call>{{"name": "tool_name", "arguments": {{"param": "value"}}}}</tool_call>

Example - Generate a CAD model:
Thought: The user wants a 3D model of a sphere. I should use the generate_cad_model tool.
<tool_call>{{"name": "generate_cad_model", "arguments": {{"prompt": "sphere 2 inches diameter"}}}}</tool_call>

Example - Control a device:
Thought: The user wants to turn on the living room lights. I'll use the control_device tool.
<tool_call>{{"name": "control_device", "arguments": {{"domain": "light", "service": "turn_on", "entity_id": "light.living_room"}}}}</tool_call>

Example - Search the web:
Thought: I need to find information about GPU optimization. I'll search the web.
<tool_call>{{"name": "web_search", "arguments": {{"query": "llama.cpp Metal GPU optimization", "max_results": 5}}}}</tool_call>

DO NOT make up URLs or fake results. ALWAYS use tools when the user requests an action that requires them."""


def _get_llama_json_examples() -> str:
    """Get Llama 3.1+/3.3 function calling format examples."""
    return """IMPORTANT: When you need to use a tool, you MUST put it in square brackets:
[func_name(param1=value1, param2=value2)]

For multiple tool calls:
[func_name1(param1=value1), func_name2(param2=value2)]

You MUST NOT include any other text if you call a function.

Example - Search the web:
[web_search(query='llama.cpp Metal GPU optimization', max_results=5)]

Example - Generate a CAD model:
[generate_cad_model(prompt='sphere 2 inches diameter')]

Example - Control a device:
[control_device(domain='light', service='turn_on', entity_id='light.living_room')]

Example - Multiple calls:
[web_search(query='PLA filament density'), web_search(query='PLA print temperature')]

DO NOT make up URLs or fake results. ALWAYS use tools when the user requests an action that requires them.
If your knowledge is outdated or you need current information, USE web_search tool BEFORE declining to answer."""


def _get_athene_json_examples() -> str:
    """Get Athene V2 Agent JSON format examples.

    Athene V2 uses a custom JSON format with 'tool' and 'parameters' keys.
    Based on Qwen2.5 but fine-tuned for agentic function calling.
    """
    return """IMPORTANT: When you need to use a tool, output a JSON object with this EXACT format:
{{"tool": "tool_name", "parameters": {{"param": "value"}}}}

Output ONLY the JSON object on its own line. No other text before or after.

Example - Search the web:
{{"tool": "web_search", "parameters": {{"query": "llama.cpp Metal GPU optimization", "max_results": 5}}}}

Example - Generate a CAD model:
{{"tool": "generate_cad_model", "parameters": {{"prompt": "sphere 2 inches diameter"}}}}

Example - Control a device:
{{"tool": "control_device", "parameters": {{"domain": "light", "service": "turn_on", "entity_id": "light.living_room"}}}}

Example - Chat response (no tool needed):
{{"tool": "chat", "parameters": {{"message": "I'll help you with that question."}}}}

CRITICAL RULES:
1. Use "tool" and "parameters" keys (NOT "name" and "arguments")
2. Output the JSON object on its own line with no surrounding text
3. If no tool is needed, use the "chat" tool to respond conversationally
4. DO NOT make up URLs or fake results
5. ALWAYS use web_search when you need current/updated information"""


def _get_mistral_json_examples() -> str:
    """Get Mistral JSON format examples."""
    return """IMPORTANT: When you need to use a tool, output EXACTLY this format:
[TOOL_CALLS] [{{"name": "tool_name", "arguments": {{"param": "value"}}}}]

Example - Generate a CAD model:
Thought: The user wants a 3D model of a sphere. I should use the generate_cad_model tool.
[TOOL_CALLS] [{{"name": "generate_cad_model", "arguments": {{"prompt": "sphere 2 inches diameter"}}}}]

Example - Control a device:
Thought: The user wants to turn on the living room lights. I'll use the control_device tool.
[TOOL_CALLS] [{{"name": "control_device", "arguments": {{"domain": "light", "service": "turn_on", "entity_id": "light.living_room"}}}}]

Example - Search the web:
Thought: I need to find information about GPU optimization. I'll search the web.
[TOOL_CALLS] [{{"name": "web_search", "arguments": {{"query": "llama.cpp Metal GPU optimization", "max_results": 5}}}}]

DO NOT make up URLs or fake results. ALWAYS use tools when the user requests an action that requires them."""


def _get_gemma_function_examples() -> str:
    """Get Gemma function format examples."""
    return """IMPORTANT: When you need to use a tool, call it like this:
<function_call>
{{"name": "tool_name", "parameters": {{"param": "value"}}}}
</function_call>

Example - Generate a CAD model:
Thought: The user wants a 3D model of a sphere. I should use the generate_cad_model tool.
<function_call>
{{"name": "generate_cad_model", "parameters": {{"prompt": "sphere 2 inches diameter"}}}}
</function_call>

Example - Control a device:
Thought: The user wants to turn on the living room lights. I'll use the control_device tool.
<function_call>
{{"name": "control_device", "parameters": {{"domain": "light", "service": "turn_on", "entity_id": "light.living_room"}}}}
</function_call>

Example - Search the web:
Thought: I need to find information about GPU optimization. I'll search the web.
<function_call>
{{"name": "web_search", "parameters": {{"query": "llama.cpp Metal GPU optimization", "max_results": 5}}}}
</function_call>

Note: Use "parameters" not "arguments" for Gemma models.
DO NOT make up URLs or fake results. ALWAYS use tools when the user requests an action that requires them."""


def _get_generic_examples() -> str:
    """Get generic examples that work across multiple formats."""
    return """IMPORTANT: When you need to use a tool, use one of these formats:

Format 1 (Qwen/Generic):
<tool_call>{{"name": "tool_name", "arguments": {{"param": "value"}}}}</tool_call>

Format 2 (Mistral):
[TOOL_CALLS] [{{"name": "tool_name", "arguments": {{"param": "value"}}}}]

Format 3 (Gemma):
<function_call>
{{"name": "tool_name", "parameters": {{"param": "value"}}}}
</function_call>

Example - Generate a CAD model:
Thought: The user wants a 3D model of a sphere. I should use the generate_cad_model tool.
<tool_call>{{"name": "generate_cad_model", "arguments": {{"prompt": "sphere 2 inches diameter"}}}}</tool_call>

Example - Control a device:
Thought: The user wants to turn on the living room lights. I'll use the control_device tool.
<tool_call>{{"name": "control_device", "arguments": {{"domain": "light", "service": "turn_on", "entity_id": "light.living_room"}}}}</tool_call>

DO NOT make up URLs or fake results. ALWAYS use tools when the user requests an action that requires them."""


__all__ = ["get_tool_call_examples"]
