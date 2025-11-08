# System Prompts for Reliable Tool Calling in Offline AI Models

Complete, production-ready examples for Athena V2, llama.cpp, and other local LLMs to enable reliable tool calling with hallucination prevention.

---

## Table of Contents
1. [Athena V2 Agent Examples](#athena-v2-agent-examples)
2. [Hallucination Prevention Strategies](#hallucination-prevention-strategies)
3. [llama.cpp Structured Output](#llamacpp-structured-output)
4. [Complete Implementation Example](#complete-implementation-example)
5. [Validation & Error Handling](#validation--error-handling)

---

## Athena V2 Agent Examples

### Basic Tool Calling

```
SYSTEM_PROMPT = """You are an advanced AI agent capable of using tools to accomplish tasks.

## Core Directives
- You MUST analyze the user's request carefully before deciding to call a tool
- Only call a tool when necessary to answer the user's question
- NEVER hallucinate or make up tool calls that don't exist
- If unsure whether a tool is needed, attempt to answer from your knowledge first
- Always provide the tool name and parameters in the exact JSON format specified

## Tool Calling Format
When you need to call a tool, respond ONLY with valid JSON in this exact format:
{"tool": "tool_name", "parameters": {"param_name": "param_value"}}

Do not include any other text before or after the JSON.
If no tool is needed, provide a direct text response.

## Temperature Setting
Use temperature = 0 for maximum consistency and predictability."""
```

### With Chat Tool for Conversational Fallback

```
SYSTEM_PROMPT = """You are a helpful AI agent with access to specialized tools.

## Available Tool Usage
- Use function tools to retrieve or process data
- Use the 'chat' tool for asking clarification or responding to the user

## Chat Tool
Call the 'chat' tool when you need to:
- Ask for more information
- Provide your final answer to the user
- Explain why a tool cannot help

## Format Requirements
Tool calls MUST be JSON: {"tool": "name", "parameters": {...}}
Chat responses use: {"tool": "chat", "parameters": {"message": "your message"}}

## Critical Rules
- Tool names are case-sensitive
- Do not chat when you should be calling a tool
- Do not call tools when you should be chatting
- Parameters must match the tool's schema exactly"""
```

### Handling Out-of-Domain Queries (no_op Pattern)

```
SYSTEM_PROMPT = """You are an intelligent agent with access to specific tools.

IMPORTANT: If the user's request cannot be answered by ANY of the provided tools, 
you MUST call the 'no_op' function to indicate the query is outside your scope.

DO NOT attempt to answer questions outside your tool domain using general knowledge.
The no_op function signals that you cannot help with this request.

Available patterns:
1. User request matches available tools â†’ Call the appropriate tool
2. User request is unclear â†’ Call chat tool to ask for clarification
3. User request is out of scope â†’ Call no_op function with explanation"""
```

**no_op Tool Schema:**
```json
{
  "type": "function",
  "function": {
    "name": "no_op",
    "description": "Call this when no other provided function can answer the user's question.",
    "parameters": {
      "type": "object",
      "properties": {
        "user_query_span": {
          "type": "string",
          "description": "The specific part of the user query that cannot be answered."
        }
      },
      "required": ["user_query_span"]
    }
  }
}
```

---

## Hallucination Prevention Strategies

### Strategy 1: Explicit Constraints

```
SYSTEM_PROMPT = """You are a factual AI assistant designed to prevent hallucinations.

## Core Constraints
1. NEVER make up information, tool names, or function calls
2. ONLY call tools that are explicitly provided to you
3. NEVER fabricate parameter values or IDs
4. If uncertain, explain your reasoning before deciding to call a tool
5. Be honest about knowledge limitations

## Response Guidelines
- If you don't know something, say "I don't have that information"
- If a tool fails or returns an error, acknowledge it rather than making up results
- Never assume parameter values; ask the user for clarification if needed
- Always cite the source when information comes from a tool

## Tool Constraints
- Call tools ONLY when you have sufficient information to populate required parameters
- Do not call a tool while guessing about parameter values
- If a tool requires an ID or specific value you don't have, ask the user first

## Temperature and Determinism
- Use temperature 0 for all calls
- Set top_p to 1.0
- Use greedy decoding (no sampling)"""
```

### Strategy 2: Chain-of-Thought Reasoning

```
SYSTEM_PROMPT = """You are an analytical AI assistant.

## Decision Process (Required)
BEFORE responding, you MUST follow these steps:

### Step 1: Analyze the Request
- What exactly is the user asking?
- What information do I already know?
- Do I need external information to answer?

### Step 2: Check Available Tools
- Review the list of available tools
- Which tool(s), if any, match this request?
- Do I have all required parameters for the tool?

### Step 3: Make a Decision
- Tool needed + have all parameters â†’ Call the tool
- Tool needed + missing parameters â†’ Ask the user for clarification
- No tool needed â†’ Provide direct answer from knowledge

### Step 4: Response
- If tool was called â†’ Use its result to answer the user
- If no tool was called â†’ Provide your answer directly

## Formatting
- Tool calls: {"tool": "name", "parameters": {params}}
- Never mix reasoning text and JSON in the same response
- Keep reasoning brief (1-2 sentences per step)

## Guardrails
- If at any step you're uncertain, err on the side of asking the user
- Do not proceed with a tool call if you lack confidence"""
```

### Strategy 3: Uncertainty Quantification

```
SYSTEM_PROMPT = """You are a confident yet cautious AI agent.

## Decision Framework
Before calling any tool, assess your confidence:

CONFIDENCE LEVELS:
- 0.9+ (Very High): Tool definitely applies, all parameters available â†’ Call tool
- 0.7-0.89 (High): Tool likely applies, minor uncertainties â†’ Ask user for confirmation
- 0.5-0.69 (Medium): Tool might apply, some parameters unclear â†’ Ask user
- Below 0.5 (Low): Tool doesn't clearly apply â†’ Explain limitation

## When Calling Tools
Only call a tool when your confidence is 0.7 or higher for relevance AND 
you have all required parameters with high confidence.

## When to Ask Instead
Ask the user for clarification when:
- You're unsure if a tool is the right fit
- You lack required parameters
- Your confidence is below 0.7

## Example Format
User: "Show me my orders"
Analysis: Order history tool is clearly relevant (0.95 confidence), but I need 
the user ID or account number which I don't have.
Response: Ask user for their account ID."""
```

---

## llama.cpp Structured Output

### GBNF Grammar Optimization

```
SYSTEM_PROMPT = """You are an AI assistant with access to structured tools.

## Response Format (REQUIRED)
Your response MUST be one of:

1. TEXT RESPONSE: Normal language response when no tool is needed
2. TOOL CALL: {"tool": "tool_name", "parameters": {key: value}}

## Critical Format Rules
- Tool calls MUST be valid JSON (use double quotes, proper escaping)
- Tool names MUST match EXACTLY (case-sensitive, no typos)
- All required parameters MUST be included
- Parameter values must match their specified types:
  - Strings: "value"
  - Numbers: 123 or 45.67
  - Booleans: true or false
  - Arrays: [item1, item2]
  - Objects: {"key": "value"}

## Enforcement Rules
- Do NOT call non-existent tools
- Do NOT invent parameter values
- Do NOT include comments or extra text with JSON
- Do NOT use single quotes in JSON
- Temperature: 0 (for maximum determinism)

## Examples

BAD (will cause errors):
{"tool": get_weather, ...}  # Missing quotes
{"tool": "get_Weather", ...}  # Wrong case
{"tool": "search", "query": Seattle}  # Missing quotes on value

GOOD:
{"tool": "search", "parameters": {"query": "Seattle"}}</status>
```

### With llama-cpp-python Integration

```
SYSTEM_PROMPT = """You are a structured output assistant.

Available tools and their schemas are documented below.
You MUST follow the JSON schema exactly when calling tools.

## Response Rules
- Always respond with EXACTLY one of: text response OR tool call (never both)
- Tool calls must be complete JSON objects, not fragments
- Match parameter types exactly: string, number, boolean, array, object
- Required fields must be present
- Unknown or inferred values should not be added

## Temperature Setting
- Use temperature=0.15 for tool calling (very low randomness)
- Use top_p=0.0 or 1.0 (disable nucleus sampling)

## Grammar Constraints
Response format is constrained by GBNF grammar.
If response seems truncated or invalid, it's likely a grammar issue."""
```

---

## Complete Implementation Example

### Full Python Implementation with Error Handling

```python
import json
import re
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass

@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: Dict[str, Any]
    
    def required_params(self) -> list:
        return self.parameters.get("required", [])
    
    def to_schema(self) -> Dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters
            }
        }


class ToolCallingAgent:
    def __init__(self, model, tools: list[ToolDefinition], temperature: float = 0.0):
        self.model = model
        self.tools = {tool.name: tool for tool in tools}
        self.temperature = temperature
        self.system_prompt = self._build_system_prompt()
    
    def _build_system_prompt(self) -> str:
        """Build comprehensive system prompt with all tool definitions."""
        tool_descriptions = "\n".join([
            f"- {tool.name}: {tool.description}"
            for tool in self.tools.values()
        ])
        
        prompt = f"""You are an AI agent with access to the following tools:

{tool_descriptions}

## Tool Calling Requirements
1. Analyze the user's request carefully
2. Determine if a tool call is necessary
3. If no tool is needed, provide a direct answer
4. If a tool is needed:
   - Ensure you have all required parameters
   - Use the exact JSON format: {{"tool": "name", "parameters": {{...}}}}
   - Do not hallucinate tool names or parameters

## Critical Rules
- NEVER call tools that don't exist in the list above
- NEVER make up parameter values
- ONLY call a tool when you have all required parameters
- Do NOT include explanatory text with tool calls
- Temperature: {self.temperature} (deterministic output)

## Response Format
If calling a tool: {{"tool": "tool_name", "parameters": {{...}}}}
If not calling a tool: Provide your response directly as text"""
        
        return prompt
    
    def _extract_tool_call(self, response: str) -> Optional[Dict[str, Any]]:
        """Extract tool call from LLM response with validation."""
        # Try to find JSON in the response
        json_pattern = r'\{[^{}]*"tool"[^{}]*\}'
        matches = re.findall(json_pattern, response)
        
        if not matches:
            return None
        
        for match in matches:
            try:
                parsed = json.loads(match)
                # Validate structure
                if "tool" not in parsed or "parameters" not in parsed:
                    continue
                return parsed
            except json.JSONDecodeError:
                continue
        
        return None
    
    def _validate_tool_call(self, tool_call: Dict) -> tuple[bool, str]:
        """Validate tool call against available tools and schemas."""
        tool_name = tool_call.get("tool")
        parameters = tool_call.get("parameters", {})
        
        # Check tool exists
        if tool_name not in self.tools:
            return False, f"Tool '{tool_name}' does not exist"
        
        tool = self.tools[tool_name]
        
        # Check required parameters
        missing = set(tool.required_params()) - set(parameters.keys())
        if missing:
            return False, f"Missing required parameters: {missing}"
        
        # Validate parameter types (basic validation)
        props = tool.parameters.get("properties", {})
        for param_name, param_value in parameters.items():
            if param_name not in props:
                return False, f"Unknown parameter: {param_name}"
            
            expected_type = props[param_name].get("type")
            actual_type = type(param_value).__name__
            
            # Type mapping
            type_map = {
                "string": str,
                "number": (int, float),
                "integer": int,
                "boolean": bool,
                "array": list,
                "object": dict
            }
            
            if expected_type in type_map:
                expected = type_map[expected_type]
                if not isinstance(param_value, expected):
                    return False, (
                        f"Parameter '{param_name}' should be {expected_type}, "
                        f"got {actual_type}"
                    )
        
        return True, "Valid"
    
    def call(self, user_message: str, max_retries: int = 3) -> Dict[str, Any]:
        """Execute agent with automatic retry on validation failure."""
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_message}
        ]
        
        for attempt in range(max_retries):
            # Get model response
            response = self.model.generate(
                messages=messages,
                temperature=self.temperature,
                top_p=1.0 if self.temperature == 0 else 0.95
            )
            
            # Try to extract tool call
            tool_call = self._extract_tool_call(response.text)
            
            if tool_call is None:
                # No tool call requested
                return {
                    "type": "text",
                    "content": response.text,
                    "tool_called": False
                }
            
            # Validate tool call
            valid, error_msg = self._validate_tool_call(tool_call)
            
            if valid:
                return {
                    "type": "tool_call",
                    "tool": tool_call["tool"],
                    "parameters": tool_call["parameters"],
                    "tool_called": True,
                    "validation_passed": True
                }
            
            # Validation failed, add error to conversation and retry
            if attempt < max_retries - 1:
                messages.append({"role": "assistant", "content": response.text})
                messages.append({
                    "role": "system",
                    "content": f"Tool call validation failed: {error_msg}. "
                              f"Please provide a corrected tool call or direct answer."
                })
        
        # Max retries exceeded, return the last response
        return {
            "type": "error",
            "message": "Max retries exceeded",
            "last_response": response.text,
            "tool_called": False
        }


# Example usage:
if __name__ == "__main__":
    # Define tools
    weather_tool = ToolDefinition(
        name="get_weather",
        description="Get current weather for a location",
        parameters={
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": "City name"},
                "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]}
            },
            "required": ["location", "unit"]
        }
    )
    
    search_tool = ToolDefinition(
        name="search",
        description="Search the internet",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"}
            },
            "required": ["query"]
        }
    )
    
    # Create agent
    # agent = ToolCallingAgent(model=your_model, tools=[weather_tool, search_tool])
    
    # Call agent
    # result = agent.call("What's the weather in Seattle?")
```

---

## Validation & Error Handling

### JSON Schema Validation Pattern

```python
import jsonschema
from typing import Dict, Any

class StructuredOutputValidator:
    """Validates tool calls against JSON schemas."""
    
    def __init__(self, tool_schemas: Dict[str, Dict]):
        self.schemas = tool_schemas
    
    def validate_tool_call(self, tool_call: Dict) -> tuple[bool, str]:
        """Validate tool call against its schema."""
        tool_name = tool_call.get("tool")
        parameters = tool_call.get("parameters", {})
        
        if tool_name not in self.schemas:
            return False, f"Unknown tool: {tool_name}"
        
        schema = self.schemas[tool_name]["parameters"]
        
        try:
            jsonschema.validate(instance=parameters, schema=schema)
            return True, "Valid"
        except jsonschema.ValidationError as e:
            return False, f"Validation error: {e.message}"
        except jsonschema.SchemaError as e:
            return False, f"Schema error: {e.message}"
    
    def should_retry(self, error: str) -> bool:
        """Determine if error is retryable."""
        retryable_errors = {
            "missing",
            "required",
            "type",
            "enum",
            "invalid json"
        }
        return any(err in error.lower() for err in retryable_errors)
```

### Recovery Prompts for Invalid Outputs

```
ERROR_RECOVERY_SYSTEM_PROMPT = """You previously provided an invalid response.

## Issues Found
{validation_errors}

## Corrective Action Required
1. Do NOT repeat the same error
2. Review the tool requirements carefully
3. Either:
   a) Call a tool with corrected parameters
   b) Provide a direct text answer if no tool is appropriate

Remember:
- All required parameters must be provided
- Parameter types must match exactly
- Tool names must be spelled correctly
- JSON must be valid"""
```

---

## Key Takeaways

1. **Temperature Control**: Always use `temperature=0` for tool calling to ensure deterministic, consistent output
2. **Explicit Constraints**: Clearly state what the model should NOT do (hallucinate, make up tools, etc.)
3. **Validation Before Execution**: Never execute tool calls without validating format and parameters
4. **Chain-of-Thought**: Encourage reasoning before tool calls to reduce errors
5. **Fallback Mechanisms**: Provide explicit paths for out-of-scope queries (no_op function)
6. **Error Recovery**: Implement retry logic with specific error messages for the model
7. **Schema Matching**: Ensure all tool definitions are complete with required parameters clearly marked

---

## References

- Athena V2 Model: https://huggingface.co/Nexusflow/Athene-V2-Agent
- Prompt Engineering Guide: https://promptingguide.ai/techniques/fewshot
- vLLM Tool Calling: https://docs.vllm.ai/en/latest/features/tool_calling.html
- JSON Schema Validation: https://json-schema.org/