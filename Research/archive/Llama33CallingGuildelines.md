# Llama 3.3 70B Tool Calling Configuration Guide for llama.cpp

## Table of Contents
1. [Overview](#overview)
2. [Tool Calling Format Requirements](#tool-calling-format-requirements)
3. [ReAct Agent Configuration](#react-agent-configuration)
4. [llama.cpp Configuration](#llamacpp-configuration)
5. [Chat Template Details](#chat-template-details)
6. [Model Output Format](#model-output-format)
7. [Debugging Approach](#debugging-approach)
8. [Common Issues](#common-issues)

---

## Overview

Llama 3.3 70B supports **zero-shot and few-shot function calling** using a square bracket format (e.g., `[func_name(param=value)]`). This is different from OpenAI's JSON format (`{"name": "func", "parameters": {...}}`). The llama.cpp project now supports tool calling through Jinja template rendering with the `--jinja` flag.

**Key Compatibility Note**: Llama 3.3 uses the **same function-calling format as Llama 3.2**. The format is designed to be more flexible than Llama 3.1, allowing functions to be defined in either system or user messages.

---

## Tool Calling Format Requirements

### 1. Llama 3.3 Output Format

**Output Format**: `[func_name1(param1=value1, param2=value2), func_name2(param=value)]`

- Uses square brackets with function names
- Parameters are key=value pairs
- Supports multiple parallel function calls
- String values should be quoted
- Ends with `<|eot_id|>` token

### 2. System Prompt Structure

**Recommended System Prompt** (from Meta Llama documentation):

```
You are an expert in composing functions. You are given a question and a set of possible functions.

Based on the question, you will need to make one or more function/tool calls to achieve the purpose.

If none of the functions can be used, point it out.

If the given question lacks the parameters required by the function, also point it out.

You should only return the function call in tools call sections.

If you decide to invoke any of the function(s), you MUST put it in the format of [func_name1(params_name1=params_value1, params_name2=params_value2...), func_name2(params)]
```

**Critical**: Include the explicit instruction about the square bracket format. This is NOT optionalâ€”without it, the model may output JSON or natural language instead.

### 3. Zero-Shot vs Few-Shot

**Zero-Shot Approach**:
- Provide only the system message and tool definitions
- Works well with Llama 3.3's instruction-tuned nature
- Most efficient (fewer tokens)

**Few-Shot Approach** (recommended for complex scenarios):
- Add 1-2 examples before the actual task
- Each example should show: user query â†’ function call output
- Format examples as message exchanges

#### Few-Shot Example Structure:

```
System: [Your system prompt with function calling instructions]

Example 1:
User: Can you add 5 and 3?
Assistant: [add(a=5, b=3)]

Example 2:
User: Get the weather and convert to Celsius
Assistant: [get_weather(location="New York"), celsius_convert(fahrenheit=72)]

Actual Task:
User: [Your actual query]
Assistant: [expected function calls]
```

---

## ReAct Agent Configuration

### Basic ReAct Agent Prompt Template

```
You are a helpful assistant that uses the ReAct (Reason + Act) framework.

Available tools:
{tool_descriptions}

Use the following format:
Thought: Your reasoning steps (what do I need to do?)
Action: The function to call from the available tools
Action Input: The input to the function

If you need to call multiple functions, list them as:
Action: [func1(param=value1), func2(param=value2)]
Action Input: (leave blank if parameters are already in function names)

Observation: (This will be provided to you after you call the function)
Thought: (repeat if needed)
Final Answer: Your final response to the user

{function_definitions}

Begin!
```

### Tool Description Format

```json
[
  {
    "type": "function",
    "function": {
      "name": "get_weather",
      "description": "Get the current weather in a given location",
      "parameters": {
        "type": "object",
        "properties": {
          "location": {
            "type": "string",
            "description": "City and state, e.g., 'San Francisco, CA'"
          },
          "metric": {
            "type": "string",
            "enum": ["celsius", "fahrenheit"],
            "description": "Temperature unit"
          }
        },
        "required": ["location"]
      }
    }
  }
]
```

### ReAct Loop Implementation

The ReAct loop should follow this pattern:

1. **Format prompt** with system message, tool definitions, and accumulated history
2. **Send to model** and parse response
3. **Detect action markers**:
   - If response contains `[func_name(...)` pattern â†’ extract and execute
   - If "Final Answer:" â†’ terminate loop
4. **Execute function** and append result to conversation
5. **Loop** (max 10-20 iterations to prevent infinite loops)

---

## llama.cpp Configuration

### Starting llama-server with Tool Calling

**Basic Command** (with Jinja support):

```bash
./llama-server \
  -m model.gguf \
  --jinja \
  -ngl 99 \
  -c 4096 \
  --verbose-prompt
```

**Flags Explained**:

| Flag | Purpose |
|------|---------|
| `--jinja` | **REQUIRED** - Enables experimental Jinja templating engine for tool support |
| `-m` | Model file path (GGUF format) |
| `-ngl` | GPU layers to offload (99 = all) |
| `-c` | Context size |
| `--verbose-prompt` | **Debugging** - Prints the actual prompt before generation |
| `--chat-template` | Use built-in template (e.g., `llama3`, `llama2`) |
| `--chat-template-file` | Use custom Jinja template file (requires `--jinja`) |

### Chat Template File Flag

If using a custom chat template file:

```bash
./llama-server \
  -m model.gguf \
  --jinja \
  --chat-template-file ./custom_template.jinja \
  -ngl 99
```

**Note**: llama.cpp automatically extracts and uses the chat template embedded in GGUF metadata. You only need to specify a custom template if the model's built-in template is incorrect or unsupported.

### OpenAI-Compatible API Endpoint

llama-server runs on `http://localhost:8080/v1/chat/completions` by default.

**Python Example** (using OpenAI client):

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8080/v1",
    api_key="not-needed"
)

tools = [
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "Evaluate a mathematical expression",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string"}
                },
                "required": ["expression"]
            }
        }
    }
]

response = client.chat.completions.create(
    model="any",
    messages=[
        {
            "role": "system",
            "content": "You are an expert in composing functions..."
        },
        {
            "role": "user",
            "content": "What is 25 * 4 + 10?"
        }
    ],
    tools=tools,
    tool_choice="auto",
    max_tokens=1024
)

print(response.choices[0].message.content)
```

---

## Chat Template Details

### Llama 3.3 Chat Template Overview

Llama 3.3's chat template:

1. **Detects tools** in system or user message
2. **Routes tool calls** through a special `tool` role handler
3. **Supports both inline and separate tool definitions**
4. **Outputs in square bracket format**

### Template Extraction from GGUF

The GGUF file contains metadata with the chat template stored as `tokenizer.chat_template`.

**Checking if template is available**:

```bash
# Using llama-cpp-python
python3 -c "
from llama_cpp import Llama
llm = Llama(model_path='./model.gguf', verbose=True)
print(llm.metadata)
" 2>&1 | grep chat_template
```

**Automatic vs Manual Template Selection**:

- **Automatic** (recommended): llama.cpp reads template from GGUF metadata
- **Manual override**: Use `--chat-template llama3` for built-in templates
- **Custom file**: Use `--chat-template-file` with `--jinja` flag

### When --jinja Flag is Required

The `--jinja` flag is **mandatory** when:

1. Using custom Jinja template files
2. Model uses non-standard template syntax
3. Implementing tool calling with complex templates
4. Models use features like tool roles, parallel calls, or advanced control flow

---

## Model Output Format

### 1. Expected Output Format

**For function calls**:
```
[get_weather(city='San Francisco', metric='celsius'), get_weather(city='Seattle', metric='celsius')]<|eot_id|>
```

**For text response**:
```
I would be happy to help. Here's what I found...<|eot_id|>
```

### 2. Format Differences (70B vs Smaller Models)

**Llama 3.3 70B vs 70B Quantized**:

- **Q8_0, Q6_K_M**: Nearly identical to full precision (recommended for reliability)
- **Q5_K_M**: Minor quality loss, still reliable (~95% quality)
- **Q4_K_M and lower**: Increased hallucination risk with function calls
- **IQ4 and below**: Not recommended for tool calling

**Quantization Impact on Tool Calling**:

The research shows a **monotonic degradation**:
- BF16 â†’ GPTQ-INT8: <2% accuracy loss
- BF16 â†’ GPTQ-INT4: 3-6% accuracy loss
- BF16 â†’ Q4_K_M (GGUF): 5-10% accuracy loss (model-dependent)

### 3. Quirks and Model-Specific Behaviors

**Known Issues with Llama 3.3 Tool Calling**:

1. **Format confusion**: If system prompt is unclear, model may output JSON instead of square brackets
2. **Parameter omission**: Model may omit optional parameters, even when required
3. **Quantization sensitivity**: Lower quantization levels (Q4, Q3) produce less reliable tool calls
4. **Token streaming**: When streaming responses, function calls may be broken across chunks
5. **Multiple calls**: The model supports parallel function calls but may have trouble with >3 simultaneous calls

**System Prompt Requirement**:

The model **absolutely requires** explicit instruction about square bracket format. Generic prompts like "use tools" are insufficient. Without the exact format specification, it will:
- Fall back to natural language
- Output JSON format instead
- Refuse to call functions

---

## Debugging Approach

### 1. Inspect llama.cpp Prompt Rendering

**Method 1: Using --verbose-prompt**

```bash
./llama-server -m model.gguf --jinja --verbose-prompt [other flags]
```

The server will print the **exact rendered prompt** before feeding it to the model. This shows:
- How the Jinja template processes your messages
- How tools are formatted
- What special tokens are inserted

**Sample Output**:
```
verbose: post_data={"messages":[{"role":"user","content":"..."}]}
verbose: template: llama3.3
verbose: prompt: 
<|begin_of_text|><|start_header_id|>system<|end_header_id|>

You are an expert in composing functions. You are given a set of tools...

<|eot_id|><|start_header_id|>user<|end_header_id|>

What is 25 * 4 + 10?

<|eot_id|><|start_header_id|>assistant<|end_header_id|>
```

### 2. Capture Raw Model Input/Output

**Method 2: Logging to File**

```bash
./llama-server \
  -m model.gguf \
  --jinja \
  --log-file ./llama.log \
  --log-level debug
```

Check `./llama.log` for detailed rendering steps.

**Method 3: Python Logging** (with llama-cpp-python)

```python
import logging
logging.basicConfig(level=logging.DEBUG)

from llama_cpp import Llama

llm = Llama(
    model_path="./model.gguf",
    verbose=True
)

response = llm.create_chat_completion(
    messages=[...],
    temperature=0
)
```

### 3. Common Inspection Points

**Check these in order**:

1. **Tool definitions reach the model**: Verify JSON schema is in prompt
2. **Format instruction is present**: Confirm system message includes square bracket format
3. **Chat template processes correctly**: Use `--verbose-prompt` to inspect
4. **Model sees tools parameter**: In llama-server logs, confirm `tools` passed to API
5. **Output doesn't have formatting errors**: Look for malformed brackets or incomplete JSON

---

## Common Issues

### Issue 1: Model Not Outputting Function Calls

**Symptoms**:
- Model returns natural language instead of `[func_name(...)]` format
- Model outputs JSON format instead of square brackets
- No function calls despite correct setup

**Causes**:
1. âŒ System prompt doesn't explicitly mention square bracket format
2. âŒ Tools parameter not passed to `--jinja` enabled server
3. âŒ Chat template not loading (model metadata missing)
4. âŒ Quantization too aggressive (Q3_K or lower)

**Solutions**:

```python
# âœ“ CORRECT: Explicit format instruction
system_prompt = """You are an expert in composing functions.
...
If you decide to invoke any of the function(s), you MUST put it in the format of [func_name(param=param_value)]"""

# âœ“ CORRECT: Pass tools to API
response = client.chat.completions.create(
    messages=[...],
    tools=tools,  # Required!
    tool_choice="auto"
)

# âœ“ CORRECT: Enable Jinja
# llama-server -m model.gguf --jinja
```

### Issue 2: `--jinja` Flag Errors

**Error**: `error: the supplied chat template is not supported: ... note: llama.cpp was started without --jinja`

**Solution**:
```bash
# âœ— WRONG
./llama-server -m model.gguf --chat-template-file custom.jinja

# âœ“ CORRECT
./llama-server -m model.gguf --jinja --chat-template-file custom.jinja
```

### Issue 3: Model Generates Malformed Function Calls

**Example**: `[func_name(param="value"` (incomplete)

**Causes**:
1. Too low `max_tokens` setting
2. Temperature too high (>0.3 for tool calling)
3. Aggressive quantization

**Solutions**:

```python
# âœ“ Increase max_tokens
response = client.chat.completions.create(
    messages=[...],
    max_tokens=512,  # At least 256 for tool calls
    temperature=0.1  # Low temperature for tool calling
)

# âœ“ Use higher quality quantization
# Q6_K_M or Q8_0 preferred for tool calling
```

### Issue 4: Chat Template Not Loading

**Symptom**: Model ignores formatting, or output is inconsistent

**Debug**:

```python
from llama_cpp import Llama

llm = Llama(model_path="model.gguf", verbose=True)

# Check if template loaded
if "tokenizer.chat_template" in llm.metadata:
    print("âœ“ Chat template found in metadata")
else:
    print("âœ— No chat template in GGUF metadata")

# Force template if needed
if llm.chat_handler is None:
    print("Chat handler not initialized - using fallback format")
```

### Issue 5: Llama 3.3 Inconsistent vs OpenAI API Format

**Issue**: You have code working with OpenAI but fails with Llama 3.3

**Root Cause**: Different output formats

```python
# OpenAI returns tool_calls as structured objects
response.choices[0].message.tool_calls
# [ToolCall(id='call_123', function=Function(name='func', arguments='...'))]

# Llama 3.3 with square bracket format needs custom parsing
import re

def extract_tool_calls(text):
    # Pattern: [func_name(param=value, ...)]
    pattern = r'\[([a-zA-Z_][a-zA-Z0-9_]*)\((.*?)\)\]'
    matches = re.findall(pattern, text)
    
    tool_calls = []
    for func_name, params_str in matches:
        # Parse key=value pairs
        params = {}
        for param in params_str.split(','):
            key, value = param.split('=')
            params[key.strip()] = value.strip().strip('"\'')
        
        tool_calls.append({
            'function': {'name': func_name},
            'arguments': params
        })
    
    return tool_calls
```

---

## Summary Table

| Aspect | Llama 3.3 Requirement | Details |
|--------|----------------------|---------|
| **Output Format** | `[func(param=val)]` | Square brackets, not JSON |
| **System Prompt** | Explicit format instruction | Must mention square bracket syntax |
| **Few-Shot Examples** | Optional but recommended | 1-2 examples before main task |
| **llama.cpp Flag** | `--jinja` required | For tool calling support |
| **Chat Template** | Auto-loaded from GGUF | Override with `--chat-template-file` |
| **Temperature** | 0.0-0.2 | Low values for tool calling |
| **Max Tokens** | â‰¥256 | Minimum for function calls |
| **Quantization** | Q6_K_M or better | Higher quality for reliability |
| **API Parameter** | Pass `tools` array | Required for tool routing |

---

## References

- **Meta Llama 3.3 Documentation**: Function-calling format specification
- **llama.cpp GitHub**: Jinja template support and tool calling implementation
- **OpenAI API**: Tool calling compatibility (conceptual reference)