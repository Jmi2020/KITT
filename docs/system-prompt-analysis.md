# KITTY System Prompt Analysis & Recommendations

**Date**: 2025-01-07
**Scope**: Unified system prompting strategy for voice and CLI interfaces

---

## Executive Summary

KITTY currently has **fragmented prompting systems** that create inconsistency between voice and CLI interfaces. The VOICE_SYSTEM_PROMPT is comprehensive but unused by the CLI, while the expert_system.py prompts lack tool calling infrastructure and hallucination prevention. This analysis provides a roadmap to unify the architecture using best practices from Research/ToolCallingPrompts.md.

---

## Current State Analysis

### 1. VOICE_SYSTEM_PROMPT (.env:106)

**Strengths**:
- ✅ Comprehensive operational manual (~2000 words)
- ✅ Complete tool contracts (device.control, printer.start, cad.generate, etc.)
- ✅ Safety model (SAFE | CAUTION | HAZARDOUS classification)
- ✅ Routing policy (local → MCP → frontier)
- ✅ Role-based authorization (owner/operator/guest)
- ✅ Environment variable substitution ({USER_NAME}, {VERBOSITY}, etc.)

**Gaps**:
- ❌ **No explicit JSON tool calling format** - Uses natural language instead of structured `{"tool": "name", "parameters": {...}}`
- ❌ **No hallucination prevention instructions** - Doesn't tell model what NOT to do
- ❌ **No chain-of-thought reasoning framework** - No explicit reasoning steps
- ❌ **No temperature guidance** - Doesn't specify deterministic behavior (temp=0)
- ❌ **No validation requirements** - Doesn't mention parameter validation
- ❌ **Not actually used by brain/CLI** - Voice service specific, see services/voice/src/voice/dependencies.py:20

### 2. Expert System Prompts (services/brain/src/brain/prompts/expert_system.py)

**Strengths**:
- ✅ Lightweight reasoning framework (4-step analysis)
- ✅ Verbosity control (1-5 scale)
- ✅ Mode switching (spoken vs written)
- ✅ CAD/fabrication domain awareness

**Gaps**:
- ❌ **No tool definitions** - Conceptual mentions only
- ❌ **No tool calling format** - Generic reasoning, no structured output
- ❌ **No hallucination prevention** - No explicit constraints
- ❌ **No confidence thresholds** - No uncertainty quantification
- ❌ **No validation requirements** - Assumes responses are valid

### 3. ReAct Agent (services/brain/src/brain/agents/react_agent.py)

**Strengths**:
- ✅ ReAct pattern implementation (Thought → Action → Observation)
- ✅ Tool calling with llama.cpp native format
- ✅ Multi-iteration reasoning loop
- ✅ Model format detection (Qwen, Hermes, Llama, etc.)
- ✅ Tool execution via MCP client

**Gaps**:
- ❌ **No hallucination prevention in prompt** - Line 102-132 lacks explicit constraints
- ❌ **No confidence-based decision making** - Always attempts tool use if available
- ❌ **No explicit temperature control** - Doesn't enforce temp=0 in prompt
- ❌ **Weak "Final Answer" detection** - Simple string match, not robust
- ❌ **No parameter validation before execution** - Executes tool calls without validation

### 4. Tool Formatter (services/brain/src/brain/prompts/tool_formatter.py)

**Strengths**:
- ✅ Formats tool schemas into human-readable docs
- ✅ Marks required vs optional parameters
- ✅ Compact and verbose formats

**Gaps**:
- ❌ **No hallucination prevention examples** - Just formats, doesn't guide behavior
- ❌ **No JSON schema examples** - Doesn't show proper tool call format
- ❌ **No error recovery prompts** - No validation failure recovery

---

## Key Findings from Research/ToolCallingPrompts.md

### Critical Best Practices

1. **Temperature Control**: Always use `temperature=0` for tool calling (deterministic output)
2. **Explicit Constraints**: State what model should NOT do (hallucinate, make up tools)
3. **Chain-of-Thought**: Encourage reasoning before tool calls
4. **Validation**: Validate tool calls before execution
5. **no_op Pattern**: Provide explicit path for out-of-scope queries
6. **Confidence Thresholds**: Quantify uncertainty (0.9+ = call tool, 0.5-0.7 = ask user)
7. **Error Recovery**: Retry logic with specific error messages
8. **JSON Schema Compliance**: Match parameter types exactly

### Example System Prompt Structure (from research)

```
## Core Directives
- NEVER hallucinate or make up tool calls that don't exist
- Only call a tool when necessary
- Always provide tool name and parameters in exact JSON format

## Decision Process
1. Analyze the Request
2. Check Available Tools
3. Make a Decision
4. Response

## Tool Calling Format
{"tool": "tool_name", "parameters": {"param_name": "param_value"}}

## Temperature Setting
Use temperature = 0 for maximum consistency
```

---

## Gap Analysis

| Feature | VOICE_PROMPT | expert_system.py | ReAct Agent | ToolCallingPrompts.md | Priority |
|---------|-------------|-----------------|-------------|----------------------|----------|
| Tool call format | ❌ Natural lang | ❌ None | ✅ Model-specific | ✅ JSON standard | **HIGH** |
| Hallucination prevention | ❌ Missing | ❌ Missing | ❌ Weak | ✅ Comprehensive | **CRITICAL** |
| Chain-of-thought | ❌ Missing | ✅ Basic | ✅ ReAct | ✅ Explicit | **HIGH** |
| Temperature guidance | ❌ Missing | ❌ Missing | ❌ Missing | ✅ temp=0 | **HIGH** |
| Parameter validation | ❌ Missing | ❌ Missing | ❌ Missing | ✅ JSON Schema | **MEDIUM** |
| Confidence thresholds | ✅ 0.80 | ❌ Missing | ❌ Missing | ✅ Quantified | **MEDIUM** |
| Error recovery | ✅ Basic | ❌ Missing | ❌ Missing | ✅ Retry logic | **MEDIUM** |
| no_op pattern | ❌ Missing | ❌ Missing | ❌ Missing | ✅ Defined | **LOW** |

---

## Recommended Architecture

### Unified System Prompt Structure

```
┌─────────────────────────────────────────────────────┐
│         KITTY Unified System Prompt                 │
├─────────────────────────────────────────────────────┤
│                                                     │
│  1. IDENTITY & MISSION                             │
│     - Name: KITTY (calm, precise, witty)           │
│     - Role: Warehouse copilot                      │
│     - Mission: Offline-first fabrication           │
│                                                     │
│  2. HALLUCINATION PREVENTION (NEW)                 │
│     - NEVER make up tools or parameters            │
│     - ONLY call tools explicitly provided          │
│     - If uncertain, ask user                       │
│     - Temperature = 0 for tool calling             │
│                                                     │
│  3. DECISION FRAMEWORK (NEW)                       │
│     - Step 1: Analyze user request                │
│     - Step 2: Check available tools                │
│     - Step 3: Assess confidence (0.9+/0.7/0.5)    │
│     - Step 4: Execute or escalate                 │
│                                                     │
│  4. TOOL CALLING FORMAT (NEW)                      │
│     - Standard: {"tool": "name", "parameters": {}} │
│     - Model-specific: Athene/Qwen/Hermes formats  │
│     - Validation: Required params, type checking   │
│                                                     │
│  5. ROUTING POLICY (EXISTING)                      │
│     - Local first (confidence ≥ 0.80)             │
│     - MCP for freshness                            │
│     - Frontier for complexity                      │
│     - Budget enforcement                           │
│                                                     │
│  6. SAFETY MODEL (EXISTING)                        │
│     - SAFE | CAUTION | HAZARDOUS                   │
│     - Confirmation phrase required                 │
│     - Interlocks and audit logs                    │
│                                                     │
│  7. TOOL REGISTRY (DYNAMIC)                        │
│     - Tools injected based on context              │
│     - Parameter schemas with required/optional     │
│     - Examples for each tool                       │
│                                                     │
│  8. VERBOSITY & UX (EXISTING)                      │
│     - V=1-5 scale                                  │
│     - Mode: spoken vs written                      │
│     - Markdown formatting                          │
│                                                     │
└─────────────────────────────────────────────────────┘
```

### Three-Tier Prompt System

```python
# services/brain/src/brain/prompts/unified.py

class KittySystemPrompt:
    """Unified system prompt builder for all KITTY interfaces."""

    def __init__(self, config: KittyConfig):
        self.identity = load_identity_section()      # From VOICE_SYSTEM_PROMPT
        self.safety = load_safety_section()          # From VOICE_SYSTEM_PROMPT
        self.routing = load_routing_section()        # From VOICE_SYSTEM_PROMPT
        self.hallucination = load_hallucination_section()  # From ToolCallingPrompts.md
        self.reasoning = load_reasoning_section()    # From expert_system.py + research

    def build(self,
             mode: str = "cli",           # cli, voice, agent
             tools: List[Tool] = None,
             verbosity: int = 3,
             model_format: str = "qwen") -> str:
        """Build system prompt adapted for interface and model."""

        sections = [
            self.identity,
            self.hallucination,  # NEW: Prevent hallucinations
            self.reasoning,      # NEW: Chain-of-thought framework
        ]

        if tools:
            sections.append(self.build_tool_section(tools, model_format))

        if mode == "voice":
            sections.append(self.build_voice_ux())
        elif mode == "agent":
            sections.append(self.build_react_pattern())

        sections.extend([
            self.routing,
            self.safety,
            self.build_verbosity_section(verbosity),
        ])

        return "\n\n".join(sections)
```

---

## Specific Recommendations

### 1. Create Unified Prompt Module (Priority: CRITICAL)

**File**: `services/brain/src/brain/prompts/unified.py`

**Action Items**:
- Extract identity, safety, routing from VOICE_SYSTEM_PROMPT
- Add hallucination prevention section (from ToolCallingPrompts.md)
- Add chain-of-thought decision framework
- Implement mode switching (cli/voice/agent)
- Add model format detection (Athene, Qwen, Hermes, Llama)

**Example Hallucination Prevention Section**:
```python
HALLUCINATION_PREVENTION = """
## Core Constraints (CRITICAL)

1. NEVER make up tool names, function calls, or parameters
2. ONLY call tools that are explicitly provided in the tool registry below
3. NEVER fabricate IDs, values, or results
4. If uncertain about a tool or parameter, ASK the user for clarification
5. Use temperature=0 for all tool calling (deterministic behavior)

## Decision Guidelines

Before calling ANY tool, verify:
- ✓ Tool exists in the available tools list
- ✓ You have ALL required parameters
- ✓ Parameter values are not guessed or assumed
- ✓ Your confidence is ≥ 0.7 for this tool choice

If ANY check fails → Ask user for clarification instead of proceeding
"""
```

### 2. Enhance ReAct Agent Prompt (Priority: HIGH)

**File**: `services/brain/src/brain/agents/react_agent.py:102-132`

**Current**:
```python
prompt = f"""You are an expert in composing functions...
Available Tools:
{tools_text}
"""
```

**Recommended**:
```python
prompt = f"""You are KITTY, a warehouse fabrication AI assistant.

## CRITICAL RULES - Tool Calling
- NEVER make up tool names or parameter values
- ONLY use tools from the Available Tools list below
- If you lack required parameters, ASK the user
- Use temperature=0 for deterministic tool calling
- Format: {self._get_tool_format_example()}

## Decision Framework
Before each action, assess:
1. Confidence: Do I understand the request? (≥0.7 to proceed)
2. Tool Match: Does a tool clearly apply?
3. Parameters: Do I have all required values?
4. Decision: Call tool | Ask user | Answer directly

Available Tools:
{tools_text}

{tool_examples}

When you have enough information:
Thought: I now know the final answer
Final Answer: [answer]

Current Query: {query}
{history_text}
"""
```

### 3. Add Temperature Enforcement (Priority: HIGH)

**File**: `services/brain/src/brain/routing/llama_cpp_client.py`

**Action**: Enforce `temperature=0.0` for all tool calling requests

```python
async def generate(self, prompt: str, tools: List[Dict] = None, **kwargs):
    """Generate response with automatic temperature control for tool calling."""

    # Enforce temperature=0 for tool calling
    if tools:
        kwargs.setdefault('temperature', 0.0)
        kwargs.setdefault('top_p', 1.0)
        logger.info("Tool calling mode: temperature=0.0 (deterministic)")

    # ... rest of implementation
```

### 4. Implement Validation Layer (Priority: MEDIUM)

**File**: `services/brain/src/brain/routing/tool_validator.py` (NEW)

```python
from typing import Dict, List, Tuple
import jsonschema

class ToolCallValidator:
    """Validates tool calls against schemas before execution."""

    def __init__(self, tool_schemas: Dict[str, Dict]):
        self.schemas = tool_schemas

    def validate(self, tool_call: Dict) -> Tuple[bool, str]:
        """Validate tool call.

        Returns:
            (is_valid, error_message)
        """
        tool_name = tool_call.get("tool")
        parameters = tool_call.get("parameters", {})

        # Check tool exists
        if tool_name not in self.schemas:
            return False, f"Tool '{tool_name}' does not exist. Available tools: {list(self.schemas.keys())}"

        schema = self.schemas[tool_name]["parameters"]

        # Validate against JSON schema
        try:
            jsonschema.validate(instance=parameters, schema=schema)
            return True, "Valid"
        except jsonschema.ValidationError as e:
            return False, f"Parameter validation failed: {e.message}"

    def should_retry(self, error: str) -> bool:
        """Determine if error is retryable."""
        retryable = {"missing", "required", "type", "enum"}
        return any(err in error.lower() for err in retryable)
```

### 5. Add Confidence-Based Routing (Priority: MEDIUM)

**File**: `services/brain/src/brain/agents/react_agent.py`

**Add confidence assessment**:
```python
def _assess_confidence(self, thought: str, tools: List[Dict]) -> float:
    """Assess confidence in tool selection.

    Returns confidence score 0.0-1.0 based on:
    - Clarity of user intent
    - Tool availability
    - Parameter availability
    """
    # Simple heuristic - can be ML-based later
    confidence = 0.5

    # Boost if specific tool mentioned
    if any(tool["function"]["name"] in thought.lower() for tool in tools):
        confidence += 0.3

    # Boost if confident language
    if any(word in thought.lower() for word in ["clearly", "obviously", "definitely"]):
        confidence += 0.2

    # Reduce if uncertain language
    if any(word in thought.lower() for word in ["maybe", "might", "possibly", "unsure"]):
        confidence -= 0.3

    return max(0.0, min(1.0, confidence))
```

### 6. Unify Voice and CLI Prompts (Priority: HIGH)

**File**: `services/voice/src/voice/dependencies.py:20-42`

**Current**: Voice service uses VOICE_SYSTEM_PROMPT directly

**Recommended**: Use unified prompt builder

```python
from brain.prompts.unified import KittySystemPrompt

@lru_cache(maxsize=1)
def get_parser() -> VoiceParser:
    """Get voice parser with unified system prompt."""
    prompt_builder = KittySystemPrompt(settings)

    # Build voice-specific prompt
    rendered = prompt_builder.build(
        mode="voice",
        tools=get_tools_for_voice(),  # Voice-specific tool subset
        verbosity=settings.verbosity,
        model_format="qwen",  # Or detect from settings
    )

    return VoiceParser(rendered)
```

---

## Implementation Roadmap

### Phase 1: Foundation (Week 1)
1. ✅ Create `services/brain/src/brain/prompts/unified.py`
2. ✅ Extract sections from VOICE_SYSTEM_PROMPT
3. ✅ Add hallucination prevention section
4. ✅ Add chain-of-thought decision framework
5. ✅ Implement mode switching (cli/voice/agent)

### Phase 2: Integration (Week 2)
1. ✅ Update ReAct agent to use unified prompts
2. ✅ Update expert_system.py to use unified prompts
3. ✅ Add temperature enforcement in llama_cpp_client
4. ✅ Create tool call validator
5. ✅ Add validation to ReAct agent execution

### Phase 3: Testing & Refinement (Week 3)
1. ✅ Test CLI with unified prompts
2. ✅ Test voice with unified prompts
3. ✅ Compare tool calling accuracy (before/after)
4. ✅ Measure hallucination rate reduction
5. ✅ Tune confidence thresholds based on metrics

### Phase 4: Voice Integration (Week 4)
1. ✅ Migrate voice service to unified prompts
2. ✅ Ensure TTS-friendly output mode works
3. ✅ Test voice → tool calling → response flow
4. ✅ Update documentation

---

## Success Metrics

| Metric | Baseline | Target | How to Measure |
|--------|----------|--------|----------------|
| Tool call accuracy | Unknown | ≥95% | Valid JSON format, correct parameters |
| Hallucination rate | Unknown | <5% | Non-existent tools, fabricated params |
| Confidence accuracy | N/A | ≥80% | Predicted conf vs actual success rate |
| Voice/CLI consistency | 0% | ≥90% | Same query → same tool selection |
| Temperature compliance | Unknown | 100% | All tool calls use temp=0 |

---

## References

- Research/ToolCallingPrompts.md - Best practices for offline tool calling
- services/brain/src/brain/prompts/expert_system.py - Current expert system
- services/brain/src/brain/agents/react_agent.py - Current ReAct implementation
- .env.example:106 - Current VOICE_SYSTEM_PROMPT
- https://docs.anthropic.com/claude/docs/tool-use - Tool calling patterns
- https://platform.openai.com/docs/guides/function-calling - Function calling guide

---

## Next Steps

1. **Review this document** with team for alignment
2. **Create unified.py module** with first iteration
3. **Run A/B test**: Old prompts vs new unified prompts
4. **Measure metrics**: Tool call accuracy, hallucination rate
5. **Iterate based on results**: Tune confidence thresholds, add examples
6. **Migrate voice service** once CLI is proven
7. **Document best practices** in CLAUDE.md for future reference

---

**End of Analysis**
