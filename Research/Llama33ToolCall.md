# Llama 3.3 Tool Calling Implementation Guide

## 1. Official Tool Calling Format for Llama 3.3

### Format Overview

Llama 3.3 supports **two different tool calling formats**:

#### A. Pythonic Format (Recommended for Llama 3.2+)
The newer pythonic format uses Python-style function calls enclosed in square brackets:

```
[get_weather(city='San Francisco', metric='celsius'), get_weather(city='Seattle', metric='celsius')]
```

**Key characteristics:**
- Wrapped in square brackets `[...]`
- Multiple parallel tool calls supported
- Parameters use Python keyword argument syntax: `param_name=value`
- String values wrapped in quotes
- No JSON wrapper needed

#### B. JSON Format (Traditional for Llama 3.1/3.2)

For zero-shot function calling, Llama 3.3 outputs JSON format:

```json
{
  "name": "function_name",
  "parameters": {
    "key1": "value1",
    "key2": "value2"
  }
}
```

**Key characteristics:**
- Uses standard JSON schema format
- Specifies function name in `"name"` field
- Parameters in `"parameters"` dictionary
- Single function call per response
- Clean separation of function name and arguments

### Official Documentation Quote

From the Llama 3.3 model card:

> "If you decide to invoke any of the function(s), you MUST put it in the format of `[func_name1(params_name1=params_value1, params_name2=params_value2...), func_name2(params)]`"
> 
> "You SHOULD NOT include any other text in the response if you call a function."

---

## 2. ReAct Agent System Prompt Format

### ReAct System Prompt Structure

The ReAct agent constructs the system prompt as follows:

```
You are an expert in composing functions. You are given a question and a set of possible functions.

Based on the question, you will need to make one or more function/tool calls to achieve the purpose.

If none of the functions can be used, point it out. You should only return the function call in tools call sections.

If you decide to invoke any of the function(s), you MUST put it in the format of:
[func_name1(params_name1=params_value1, params_name2=params_value2...), func_name2(params)]

You SHOULD NOT include any other text in the response.

Here is a list of functions in JSON format that you can invoke:
[function_definitions_here]
```

### Tool Schema Format (OpenAI Compatible)

Tools are provided to llama.cpp in OpenAI-compatible format:

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
          "unit": {
            "type": "string",
            "enum": ["celsius", "fahrenheit"],
            "default": "celsius"
          }
        },
        "required": ["location"]
      }
    }
  }
]
```

### Chat Template Integration

The llama3.3 chat template in llama.cpp formats tools like this:

```
<|begin_of_text|><|start_header_id|>system<|end_header_id|>
You are an expert in composing functions...
[Function definitions in JSON]<|eot_id|>
<|start_header_id|>user<|end_header_id|>
What's the weather in San Francisco and Seattle?<|eot_id|>
<|start_header_id|>assistant<|end_header_id|>
```

---

## 3. Actual Model Output Examples

### Example 1: Pythonic Format Output

**Request:**
```
What's the weather in San Francisco and Seattle?
```

**Model Output (Pythonic):**
```
[get_weather(city='San Francisco', unit='celsius'), get_weather(city='Seattle', unit='celsius')]
```

**Parsing strategy:**
- Look for opening `[` and closing `]`
- Extract function names and parameters
- Parse `param=value` pairs separated by commas
- Handle nested quotes and complex types

### Example 2: JSON Format Output

**Request:**
```
Can you retrieve the details for user ID 7890 with black as their special request?
```

**Model Output (JSON):**
```json
{
  "name": "get_user_info",
  "parameters": {
    "user_id": 7890,
    "special": "black"
  }
}
```

**Parsing strategy:**
- Extract `"name"` field for function name
- Extract `"parameters"` dictionary for arguments
- No text before or after the JSON object

### Example 3: Real vLLM Output

From vLLM tool calling documentation:

```
Function called: get_weather
Arguments: {"location": "San Francisco, CA", "unit": "fahrenheit"}
Result: Getting the weather for San Francisco, CA in fahrenheit...
```

---

## 4. Parser Implementation Guidance

### Pythonic Format Parser

```python
import re
import ast

def parse_pythonic_tool_calls(text):
    """Parse [func_name(arg1=val1, arg2=val2), ...] format"""
    
    # Extract content between [ and ]
    match = re.search(r'\[(.*?)\]', text, re.DOTALL)
    if not match:
        return []
    
    content = match.group(1)
    tool_calls = []
    
    # Split by function calls - look for pattern: func_name(...)
    # Use regex to find function calls
    func_pattern = r'(\w+)\((.*?)\)(?=,\s*\w+\(|\])'
    
    for func_match in re.finditer(func_pattern, content):
        func_name = func_match.group(1)
        params_str = func_match.group(2)
        
        # Parse parameters: key=value, key='string', etc.
        params = {}
        # Split by commas not inside quotes
        param_parts = re.split(r',\s*(?=\w+=)', params_str)
        
        for part in param_parts:
            if '=' in part:
                key, value = part.split('=', 1)
                key = key.strip()
                value = value.strip()
                
                # Try to evaluate the value (handles strings, numbers, etc.)
                try:
                    params[key] = ast.literal_eval(value)
                except (ValueError, SyntaxError):
                    params[key] = value
        
        tool_calls.append({
            "name": func_name,
            "parameters": params
        })
    
    return tool_calls


def parse_json_tool_calls(text):
    """Parse {"name": "func", "parameters": {...}} format"""
    
    import json
    
    try:
        obj = json.loads(text.strip())
        if "name" in obj and "parameters" in obj:
            return [{
                "name": obj["name"],
                "parameters": obj["parameters"]
            }]
    except json.JSONDecodeError:
        pass
    
    return []


def parse_tool_calls(text):
    """Auto-detect and parse tool calls in either format"""
    
    # Try pythonic format first
    if '[' in text and ']' in text:
        calls = parse_pythonic_tool_calls(text)
        if calls:
            return calls
    
    # Try JSON format
    calls = parse_json_tool_calls(text)
    if calls:
        return calls
    
    return []
```

---

## 5. Context Size Configuration in llama.cpp

### Parameters That Control Context Size

When making requests to llama.cpp server, the following parameters control context behavior:

| Parameter | Type | Default | Purpose |
|-----------|------|---------|---------|
| `n_ctx` | int | 2048 (or from model) | Maximum context window size |
| `n_predict` | int | -1 (infinite) | Maximum tokens to generate |
| `n_keep` | int | 0 | Tokens to keep when context shifts |
| `ctx_size` | int | from model | Actual context size loaded |

### Server Configuration for Tools

**llama-server startup command for tool calling:**

```bash
llama-server \
  -m model.gguf \
  -c 8192 \
  -n 4096 \
  --chat-template llama3 \
  -ngl 32
```

**Parameters explained:**
- `-c 8192`: Set context size to 8192 tokens (max available)
- `-n 4096`: Allow up to 4096 tokens for generation
- `--chat-template llama3`: Use Llama 3.x chat template
- `-ngl 32`: Use 32 GPU layers

### API Request with Context Size

**POST /v1/chat/completions:**

```json
{
  "model": "Llama-3.3-70B",
  "messages": [
    {
      "role": "system",
      "content": "You are an assistant with tool calling..."
    },
    {
      "role": "user",
      "content": "What's the weather?"
    }
  ],
  "tools": [...],
  "tool_choice": "auto",
  "temperature": 0.7,
  "top_p": 0.9,
  "max_tokens": 1000,
  "frequency_penalty": 0,
  "presence_penalty": 0
}
```

### Troubleshooting Context Issues

**Problem: Getting 1365 tokens but server has 8192**

This typically happens when:

1. **Chat template not set correctly**
   ```bash
   # Check available templates
   llama-server --help | grep template
   
   # Explicitly set template
   llama-server -m model.gguf --chat-template llama3
   ```

2. **Context shifts due to context overflow**
   ```bash
   # Prevent context shifting (keeps full history)
   llama-server -c 8192 --no-context-shift
   ```

3. **n_predict interfering with n_ctx**
   ```bash
   # Make sure n_predict doesn't exceed available context
   # If n_ctx=8192 and prompt=1000 tokens
   # Then max n_predict = 7192
   ```

4. **Token counting in prompts**
   - Llama 3.x uses `<|begin_of_text|>`, `<|start_header_id|>`, `<|eot_id|>` special tokens
   - These add ~10-15 tokens per turn
   - Tool definitions add significant token overhead

---

## 6. Complete Working Example

### Full Integration Example

```python
import requests
import json
from typing import Any, Dict, List

class Llama33ToolCaller:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
    
    def get_tools_schema(self) -> List[Dict[str, Any]]:
        """Define tools in OpenAI format"""
        return [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get weather information for a location",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "location": {
                                "type": "string",
                                "description": "City name"
                            },
                            "unit": {
                                "type": "string",
                                "enum": ["celsius", "fahrenheit"],
                                "default": "celsius"
                            }
                        },
                        "required": ["location"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_user_info",
                    "description": "Retrieve user information",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "user_id": {
                                "type": "integer",
                                "description": "User ID"
                            }
                        },
                        "required": ["user_id"]
                    }
                }
            }
        ]
    
    def call_model(self, user_message: str) -> Dict[str, Any]:
        """Make API call with tool definitions"""
        
        response = requests.post(
            f"{self.base_url}/v1/chat/completions",
            json={
                "model": "Llama-3.3-70B",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a helpful assistant with access to tools."
                    },
                    {
                        "role": "user",
                        "content": user_message
                    }
                ],
                "tools": self.get_tools_schema(),
                "tool_choice": "auto",
                "temperature": 0.7,
                "max_tokens": 1000
            }
        )
        
        return response.json()
    
    def parse_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Parse model response and extract tool calls"""
        
        content = response["choices"][0]["message"]["content"]
        
        # Try parsing as tool calls
        tool_calls = self.parse_tool_calls(content)
        
        return {
            "raw_content": content,
            "tool_calls": tool_calls,
            "has_tool_calls": len(tool_calls) > 0
        }
    
    def parse_tool_calls(self, text: str) -> List[Dict[str, Any]]:
        """Parse tool calls from model output"""
        
        import re
        import ast
        
        # Try pythonic format first: [func_name(args), ...]
        if '[' in text and ']' in text:
            match = re.search(r'\[(.*)\]', text, re.DOTALL)
            if match:
                return self._parse_pythonic(match.group(1))
        
        # Try JSON format: {"name": "...", "parameters": {...}}
        try:
            obj = json.loads(text.strip())
            if "name" in obj and "parameters" in obj:
                return [obj]
        except json.JSONDecodeError:
            pass
        
        return []
    
    def _parse_pythonic(self, content: str) -> List[Dict[str, Any]]:
        """Parse pythonic function format"""
        
        import re
        import ast
        
        tool_calls = []
        
        # Match function calls: func_name(args)
        pattern = r'(\w+)\(([^)]*)\)'
        
        for match in re.finditer(pattern, content):
            func_name = match.group(1)
            params_str = match.group(2)
            
            # Parse parameters
            params = {}
            if params_str.strip():
                # Split parameters by comma (outside quotes)
                param_pairs = re.split(r',\s*(?=[a-zA-Z_]+=)', params_str)
                
                for pair in param_pairs:
                    if '=' in pair:
                        key, value = pair.split('=', 1)
                        key = key.strip()
                        value = value.strip()
                        
                        try:
                            params[key] = ast.literal_eval(value)
                        except (ValueError, SyntaxError):
                            params[key] = value
            
            tool_calls.append({
                "name": func_name,
                "parameters": params
            })
        
        return tool_calls


# Usage example
if __name__ == "__main__":
    caller = Llama33ToolCaller()
    
    # Make a request
    response = caller.call_model("What's the weather in San Francisco?")
    
    # Parse the response
    result = caller.parse_response(response)
    
    print("Raw content:", result["raw_content"])
    print("Tool calls:", result["tool_calls"])
    print("Has tool calls:", result["has_tool_calls"])
```

---

## 7. Key Takeaways

### For Llama 3.3 Tool Calling:

1. **Format Detection**: Always check for `[` first (pythonic), then fall back to JSON parsing
2. **Parameter Names**: In JSON format use `"parameters"`, not `"arguments"`
3. **Clean Output**: Model will ONLY output the tool call with no surrounding text
4. **Context Size**: Set `-c` flag high (8192) and monitor actual token usage
5. **Chat Template**: Always specify `--chat-template llama3` for proper formatting
6. **Tool Definitions**: Provide in OpenAI format for best compatibility with llama.cpp

### Parameter Reference:

- **"name"** vs **"function"**: Llama uses `"name"` for the function name
- **"parameters"** vs **"arguments"**: Llama uses `"parameters"` as the dictionary key
- **Pythonic calls**: `func_name(key=value)` format with automatic type inference
- **JSON calls**: Standard `{"name": "...", "parameters": {...}}` format