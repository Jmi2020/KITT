# Multi-Model Tool Calling Design

## Overview

This document outlines the design for supporting multiple LLM models with different tool calling formats in KITTY's ReAct agent system.

## Current State

**Current Implementation (Qwen2.5 Only):**
- Parser expects XML format: `<tool_call>{"name": "...", "arguments": {...}}</tool_call>`
- ReAct prompt shows XML examples
- llama-server started with `--jinja -fa` flags
- Single format assumption throughout codebase

**Limitation:** System only works with Qwen2.5 family models

## Goals

1. Support all models in `/Users/Shared/Coding/models`:
   - Qwen2.5 (72B, 32B Coder) - XML format
   - Qwen3 (30B) - XML format (similar to Qwen2.5)
   - Mistral 7B v0.3 - JSON format
   - Gemma 3 27B - Function call format
   - GPT-OSS 120B - TBD format

2. Automatic model detection and configuration
3. Zero breaking changes to existing Qwen2.5 workflows
4. Easy to add new models in the future

## Architecture Design

### 1. Model Detection & Configuration Layer

**File:** `services/brain/src/brain/tools/model_config.py` (✅ CREATED)

**Purpose:** Detect model type from path/alias and provide configuration

```python
class ToolCallFormat(Enum):
    QWEN_XML = "qwen_xml"          # <tool_call>{...}</tool_call>
    MISTRAL_JSON = "mistral_json"  # [TOOL_CALLS] {...}
    GEMMA_FUNCTION = "gemma_function"  # <function_call>...</function_call>
    GENERIC_XML = "generic_xml"    # Fallback
```

**Functions:**
- `detect_model_format(model_path_or_alias)` - Pattern match on model name
- `get_model_config(model_path_or_alias)` - Return ModelConfig with flags

**ModelConfig includes:**
- `format: ToolCallFormat` - Which parser to use
- `requires_jinja: bool` - Whether to add `--jinja` flag
- `requires_function_auth: bool` - Whether to add `-fa` flag
- `supports_parallel_calls: bool` - Can handle multiple tool calls at once

### 2. Multi-Format Parser

**File:** `services/brain/src/brain/tools/parser.py` (TO UPDATE)

**Current:** Single `parse_tool_calls()` function for Qwen XML

**New Design:**

```python
def parse_tool_calls(
    text: str,
    format_type: ToolCallFormat = ToolCallFormat.QWEN_XML
) -> tuple[List[ToolCall], str]:
    """Parse tool calls using format-specific parser."""

    if format_type == ToolCallFormat.QWEN_XML:
        return _parse_qwen_xml(text)
    elif format_type == ToolCallFormat.MISTRAL_JSON:
        return _parse_mistral_json(text)
    elif format_type == ToolCallFormat.GEMMA_FUNCTION:
        return _parse_gemma_function(text)
    else:
        return _parse_generic_xml(text)

def _parse_qwen_xml(text: str) -> tuple[List[ToolCall], str]:
    """Parse Qwen2.5/3 XML format: <tool_call>{...}</tool_call>"""
    # Current implementation

def _parse_mistral_json(text: str) -> tuple[List[ToolCall], str]:
    """Parse Mistral JSON format: [TOOL_CALLS] [{...}]"""
    pattern = r'\[TOOL_CALLS\]\s*(\[.*?\])'
    # Extract JSON array of tool calls

def _parse_gemma_function(text: str) -> tuple[List[ToolCall], str]:
    """Parse Gemma function format: <function_call>...</function_call>"""
    pattern = r'<function_call>(.*?)</function_call>'
    # Extract function calls

def _parse_generic_xml(text: str) -> tuple[List[ToolCall], str]:
    """Generic XML parser for unknown models"""
    # Try both <tool_call> and <function_call> patterns
```

### 3. Model-Specific Prompt Templates

**File:** `services/brain/src/brain/agents/prompt_templates.py` (NEW)

**Purpose:** Store format-specific prompt examples

```python
def get_tool_call_examples(format_type: ToolCallFormat) -> str:
    """Return model-specific tool call examples."""

    if format_type == ToolCallFormat.QWEN_XML:
        return """
IMPORTANT: When you need to use a tool, output EXACTLY this XML format:
<tool_call>{"name": "tool_name", "arguments": {"param": "value"}}</tool_call>

Example - Generate a CAD model:
Thought: The user wants a 3D model of a sphere. I should use the generate_cad_model tool.
<tool_call>{"name": "generate_cad_model", "arguments": {"prompt": "sphere 2 inches diameter"}}</tool_call>
"""

    elif format_type == ToolCallFormat.MISTRAL_JSON:
        return """
IMPORTANT: When you need to use a tool, output EXACTLY this format:
[TOOL_CALLS] [{"name": "tool_name", "arguments": {"param": "value"}}]

Example - Generate a CAD model:
Thought: The user wants a 3D model of a sphere. I should use the generate_cad_model tool.
[TOOL_CALLS] [{"name": "generate_cad_model", "arguments": {"prompt": "sphere 2 inches diameter"}}]
"""

    elif format_type == ToolCallFormat.GEMMA_FUNCTION:
        return """
IMPORTANT: When you need to use a tool, call it like this:
<function_call>
{"name": "tool_name", "parameters": {"param": "value"}}
</function_call>

Example - Generate a CAD model:
Thought: The user wants a 3D model of a sphere. I should use the generate_cad_model tool.
<function_call>
{"name": "generate_cad_model", "parameters": {"prompt": "sphere 2 inches diameter"}}
</function_call>
"""

    else:
        # Generic fallback
        return "..."
```

### 4. Updated ReAct Agent

**File:** `services/brain/src/brain/agents/react_agent.py` (TO UPDATE)

**Changes:**

```python
class ReActAgent:
    def __init__(
        self,
        llm_client: LlamaCppClient,
        mcp_client: MCPClient,
        max_iterations: int = 10,
        model_alias: Optional[str] = None,  # NEW: Model identifier
    ):
        self._llm = llm_client
        self._mcp = mcp_client
        self._max_iterations = max_iterations

        # NEW: Detect model format
        self._model_format = detect_model_format(model_alias or "qwen2.5")

    def _build_react_prompt(self, query, tools, history):
        """Build ReAct prompt with model-specific tool call examples."""

        # ... existing code ...

        # NEW: Get model-specific examples
        tool_examples = get_tool_call_examples(self._model_format)

        prompt = f"""You are an AI assistant with access to tools.

Available Tools:
{tools_text}

{tool_examples}

DO NOT make up URLs or fake results. ALWAYS use tools when needed.
...
"""
        return prompt
```

### 5. Updated llama.cpp Client

**File:** `services/brain/src/brain/routing/llama_cpp_client.py` (TO UPDATE)

**Changes:**

```python
class LlamaCppClient:
    def __init__(self, config: Optional[LlamaCppConfig] = None):
        cfg = config or get_routing_config().llamacpp
        self._config = cfg
        self._base_url = cfg.host.rstrip("/")

        # NEW: Detect model format for parsing
        self._model_format = detect_model_format(cfg.model_alias)

    async def generate(self, prompt, model=None, tools=None):
        """Invoke completion endpoint."""

        # ... existing request code ...

        # NEW: Pass format to parser
        if tools and completion:
            tool_calls, cleaned_text = parse_tool_calls(
                completion,
                format_type=self._model_format  # NEW
            )
```

### 6. Updated llama-server Startup Script

**File:** `ops/scripts/start-llamacpp.sh` (TO UPDATE)

**Changes:**

```bash
#!/usr/bin/env bash

# ... existing variable setup ...

# NEW: Detect model format and set appropriate flags
detect_model_type() {
    local model_path="$1"
    local model_lower=$(echo "$model_path" | tr '[:upper:]' '[:lower:]')

    if [[ "$model_lower" =~ qwen ]]; then
        echo "qwen"
    elif [[ "$model_lower" =~ mistral ]]; then
        echo "mistral"
    elif [[ "$model_lower" =~ gemma ]]; then
        echo "gemma"
    else
        echo "generic"
    fi
}

MODEL_TYPE=$(detect_model_type "$PRIMARY_MODEL")

# ... build command array ...

# NEW: Add model-specific flags
if [[ "$TOOL_CALLING" == "1" || "$TOOL_CALLING" == "true" ]]; then
    case "$MODEL_TYPE" in
        qwen)
            cmd+=(--jinja -fa)
            echo "Qwen model detected: --jinja -fa"
            ;;
        mistral)
            cmd+=(--jinja -fa)
            echo "Mistral model detected: --jinja -fa"
            ;;
        gemma)
            # Gemma doesn't need special flags
            echo "Gemma model detected: no special flags"
            ;;
        *)
            cmd+=(--jinja -fa)
            echo "Generic model: --jinja -fa"
            ;;
    esac
fi
```

## Tool Call Format Reference

### Qwen2.5/3 (XML Format)

**Output:**
```xml
<tool_call>{"name": "generate_cad_model", "arguments": {"prompt": "sphere"}}</tool_call>
```

**Parser Pattern:**
```python
r'<tool_call>(.*?)</tool_call>'
```

### Mistral (JSON Format)

**Output:**
```json
[TOOL_CALLS] [{"name": "generate_cad_model", "arguments": {"prompt": "sphere"}}]
```

**Parser Pattern:**
```python
r'\[TOOL_CALLS\]\s*(\[.*?\])'
```

### Gemma (Function Format)

**Output:**
```xml
<function_call>
{"name": "generate_cad_model", "parameters": {"prompt": "sphere"}}
</function_call>
```

**Parser Pattern:**
```python
r'<function_call>(.*?)</function_call>'
```

Note: Gemma uses "parameters" instead of "arguments"

## Implementation Plan

### Phase 1: Foundation (No Breaking Changes)
1. ✅ Create model_config.py with detection logic
2. ⏳ Update parser.py with format-specific parsers (keep default=QWEN_XML)
3. ⏳ Create prompt_templates.py with format-specific examples
4. ⏳ Add tests for each parser format

### Phase 2: Integration
5. ⏳ Update ReAct agent to use model-aware prompts
6. ⏳ Update llama_cpp_client to pass format to parser
7. ⏳ Update start-llamacpp.sh with model detection
8. ⏳ Update configuration to track model alias

### Phase 3: Testing & Validation
9. ⏳ Test Qwen2.5 (ensure no regression)
10. ⏳ Test Mistral 7B
11. ⏳ Test Gemma 3
12. ⏳ Document model-specific configuration
13. ⏳ Add model switching guide to README

## Backward Compatibility

**Guarantee:** Existing Qwen2.5 workflows work exactly as before

**How:**
- Default format = `ToolCallFormat.QWEN_XML`
- If no model specified, assume Qwen
- All existing prompts still valid
- Parser falls back to Qwen XML if format not specified

## Testing Strategy

### Unit Tests
- Test each parser independently with sample outputs
- Test model detection with various paths/aliases
- Test prompt template generation

### Integration Tests
- Test full ReAct loop with each model
- Test model switching
- Test mixed model usage (different models on different ports)

### Regression Tests
- Ensure Qwen2.5 behavior unchanged
- Verify all existing tests still pass

## Future Extensibility

**Adding a New Model:**

1. Add detection pattern to `model_config.py`
2. Add parser function to `parser.py`
3. Add prompt template to `prompt_templates.py`
4. Add startup flags to `start-llamacpp.sh`
5. Test and document

**Example: Adding Llama 3.1**

```python
# model_config.py
elif "llama" in model_lower and "3.1" in model_lower:
    return ToolCallFormat.LLAMA_31_FUNCTION

# parser.py
def _parse_llama_31_function(text):
    pattern = r'<function=(\w+)>(.*?)</function>'
    # ...

# prompt_templates.py
elif format_type == ToolCallFormat.LLAMA_31_FUNCTION:
    return "<function=tool_name>{...}</function> examples..."
```

## Configuration Example

**Multi-Model Setup:**

```bash
# Port 8080: Qwen2.5 (primary reasoning)
LLAMACPP_PRIMARY_MODEL="Qwen2.5-72B-Instruct-GGUF/qwen2.5-72b-instruct.gguf"
LLAMACPP_PRIMARY_ALIAS="kitty-primary"
LLAMACPP_PORT="8080"
LLAMACPP_TOOL_CALLING="1"

# Port 8081: Mistral (fast tool calling)
LLAMACPP_PRIMARY_MODEL="Mistral-7B-v0.3/mistral-7b.gguf"
LLAMACPP_PRIMARY_ALIAS="kitty-mistral"
LLAMACPP_PORT="8081"
LLAMACPP_TOOL_CALLING="1"

# Port 8082: Gemma (experimental)
LLAMACPP_PRIMARY_MODEL="gemma-3-27b-it-GGUF/gemma-3-27b.gguf"
LLAMACPP_PRIMARY_ALIAS="kitty-gemma"
LLAMACPP_PORT="8082"
LLAMACPP_TOOL_CALLING="1"
```

## Open Questions

1. **GPT-OSS 120B Format:** Need to verify which tool calling format it uses
2. **Performance:** Should we benchmark tool calling latency per model?
3. **Model Aliases:** Should we maintain a registry of tested model aliases?
4. **Fallback Behavior:** If parser fails, should we retry with different format?
5. **Logging:** Should we log which format was detected for debugging?

## Success Criteria

- ✅ All existing Qwen2.5 tests pass
- ✅ Can successfully call tools with Mistral 7B
- ✅ Can successfully call tools with Gemma 3
- ✅ Parser auto-detects format from model path
- ✅ llama-server starts with correct flags per model
- ✅ Documentation explains how to add new models
- ✅ Zero breaking changes to existing deployments

## References

- Qwen2.5 Tool Calling: https://qwen.readthedocs.io/en/latest/framework/function_call.html
- Mistral Function Calling: https://docs.mistral.ai/capabilities/function_calling/
- Gemma Documentation: https://ai.google.dev/gemma/docs
- llama.cpp Tool Support: https://github.com/ggerganov/llama.cpp/discussions/7700
