# How Athene V2 Agent Calls Functions: A Detailed Technical Writeup

## Overview

**Athene V2 Agent** is purpose-built for agentic workflows and uses a highly specialized approach to function calling that differs from standard models like Llama 3.1. The model employs a **custom prompting style with baked-in extraction logic** that makes it exceptionally accurate at determining which functions to call, extracting correct parameters, and reasoning through multi-step dependencies.[1][2]

Key distinguishing features:

- **18% better performance than GPT-4o** on single function calling tasks[3][1]
- **Deep reasoning capability** for complex, nested tool dependencies[4][1]
- **Built on Qwen 2.5 72B** with specialized fine-tuning for agents[5][1]
- **Highly controllable** through system prompts and tool definitions[1]

***

## Function Calling Format

### Core Architecture: Chat Template

Athene V2 Agent uses **the exact same chat template as Qwen 2.5**, which is based on the **Qwen Instruct format**. This is a critical detail for your integration. The message format follows:[5]

```
<|im_start|>system
{system_instructions}<|im_end|>
<|im_start|>user
{user_query}<|im_end|>
<|im_start|>assistant
```

When working with llama.cpp or Python transformers, the chat template is **automatically applied** if the model metadata is properly loaded, but understanding it is essential for debugging.

### Tool Definition Schema (JSON)

Athene V2 Agent expects tools to be defined in **OpenAI-compatible JSON schema format**, similar to standard function calling. Each tool definition contains:[6][1]

```json
{
  "type": "function",
  "function": {
    "name": "get_weather",
    "description": "Get the current weather in a specific location. Provides detailed weather information including temperature, conditions, and forecasts.",
    "parameters": {
      "type": "object",
      "properties": {
        "location": {
          "type": "string",
          "description": "The city and state/country, e.g., 'Seattle, WA' or 'London, UK'"
        },
        "units": {
          "type": "string",
          "enum": ["celsius", "fahrenheit"],
          "description": "Temperature units for the response"
        },
        "forecast_days": {
          "type": "integer",
          "description": "Number of days to forecast (1-7)",
          "minimum": 1,
          "maximum": 7
        }
      },
      "required": ["location"]
    }
  }
}
```

### Function Call Output Format

When Athene V2 Agent generates a function call, it outputs a **structured JSON format**. The model produces output in the following pattern:

```json
{
  "name": "get_weather",
  "parameters": {
    "location": "Seattle, WA",
    "units": "fahrenheit",
    "forecast_days": 3
  }
}
```

Or for **multiple parallel function calls** (one of Athene's strengths):

```json
{
  "type": "parallel_calls",
  "calls": [
    {
      "name": "get_weather",
      "parameters": {"location": "Seattle, WA"}
    },
    {
      "name": "get_news",
      "parameters": {"topic": "weather events"}
    }
  ]
}
```

***

## System Prompt Architecture for Athene V2 Agent

Unlike standard models, **Athene V2 Agent is highly tuned to be controllable through system prompts**. Your system prompt should establish clear behavioral constraints and tool instructions. Here's the recommended structure:[1]

### Core System Prompt Template

```
You are an AI agent that can call functions to accomplish tasks. You have access to the following tools:

{TOOLS_DEFINITION_HERE}

## Instructions

- Analyze the user's query carefully and determine which tool(s) to call
- Extract all necessary parameters from the user's request
- Provide detailed, well-indented docstrings and descriptions for tools—this helps accuracy significantly
- You can call multiple tools in parallel when appropriate
- Always use exact parameter names and types as specified in the tool schemas
- If information is missing, ask the user clarifying questions using the `chat` tool
- For irrelevant queries, use the `no_relevant_function` tool

## Important Constraints

- Set temperature to 0 (deterministic mode for consistent tool calls)
- Use sampling=False for maximum reliability
- Do not hallucinate parameters—only use values present in the user query
```

### Handling Chat vs. Tool Calling

Athene V2 Agent is tuned to **prefer tool calling over chatting by default**. If you want it to handle both conversational queries and tool calls, define a `chat` tool:[1]

```json
{
  "type": "function",
  "function": {
    "name": "chat",
    "description": "Call this tool when you want to communicate with the user or ask clarifying questions. Use this when you need more information or to provide final results.",
    "parameters": {
      "type": "object",
      "properties": {
        "message": {
          "type": "string",
          "description": "The message or response to send to the user"
        }
      },
      "required": ["message"]
    }
  }
}
```

Then in your system prompt:

```
You can use the chat tool to ask the user for more information, request clarification, 
and send final results back to the user.
```

### Handling Irrelevant/Out-of-Domain Queries

By default, Athene V2 Agent tries its best to issue relevant tool calls even for out-of-domain queries. To make it reject irrelevant queries, define a **no-op function**:[1]

```json
{
  "type": "function",
  "function": {
    "name": "no_relevant_function",
    "description": "Call this when no other provided function can answer the user's query or when the query is out of scope.",
    "parameters": {
      "type": "object",
      "properties": {
        "reason": {
          "type": "string",
          "description": "Brief explanation of why this query cannot be answered by available tools"
        }
      },
      "required": ["reason"]
    }
  }
}
```

***

## Critical Prompting Tricks for Athene V2 Agent

The Athene V2 Agent documentation emphasizes several key techniques that significantly improve performance:[1]

### 1. **Detailed, Well-Indented Docstrings**

Provide **comprehensive, professionally formatted docstrings** for each tool. The model uses these to make better decisions:

```
"description": "Retrieve real-time weather information for a specified location.
  
  This tool fetches current weather conditions including temperature, 
  humidity, wind speed, and atmospheric pressure. It can also provide 
  hourly and multi-day forecasts.
  
  Use this tool when the user asks about:
  - Current weather conditions
  - Temperature or weather forecasts
  - Precipitation probability
  - Wind or weather alerts
  
  This tool does NOT provide historical weather data or climate averages."
```

### 2. **Set Temperature to 0**

Always use **temperature=0** (deterministic sampling) when calling Athene V2 Agent for function calling:[1]

```python
response = client.chat.completions.create(
    model="Athene-V2-Agent",
    messages=messages,
    tools=tools,
    temperature=0.0,  # CRITICAL: deterministic mode
    top_p=1.0,
    max_tokens=2048
)
```

### 3. **Set Sampling to False**

When using llama.cpp or lower-level APIs, explicitly disable sampling:[1]

```bash
llama-server -m athene-v2-agent.gguf \
  --port 8000 \
  --sampling-method none \
  --temperature 0
```

### 4. **Use Tool_Choice="auto"**

Let the model decide whether to call a tool or respond conversationally, rather than forcing tool use:

```python
response = client.chat.completions.create(
    model="Athene-V2-Agent",
    messages=messages,
    tools=tools,
    tool_choice="auto",  # Model decides when to call tools
    temperature=0.0
)
```

***

## Execution Loop: From Function Calls to Results

Athene V2 Agent operates in a **multi-step agentic loop** where function calls are extracted, executed, and results are fed back to the model for refinement. Here's the complete execution architecture:[2][7]

### Step 1: Initial Prompt with Tools

```python
system_prompt = """You are an AI agent with function calling capabilities.
Available tools: [list of tools in JSON schema format]"""

messages = [
    {"role": "system", "content": system_prompt},
    {"role": "user", "content": "What's the weather in Seattle and show me news about it?"}
]
```

### Step 2: Generate Function Calls

```python
response = client.chat.completions.create(
    model="Athene-V2-Agent",
    messages=messages,
    tools=tools,
    temperature=0.0,
    tool_choice="auto"
)

# Extract tool calls from response
tool_calls = response.choices[0].message.tool_calls  # May be empty or contain multiple calls
```

The model outputs something like:

```json
{
  "tool_calls": [
    {
      "id": "call_1",
      "function": {
        "name": "get_weather",
        "arguments": "{\"location\": \"Seattle, WA\", \"units\": \"fahrenheit\"}"
      }
    },
    {
      "id": "call_2",
      "function": {
        "name": "search_news",
        "arguments": "{\"query\": \"Seattle weather\"}"
      }
    }
  ]
}
```

### Step 3: Parse and Execute Tools

```python
import json

executed_results = {}

for tool_call in tool_calls:
    tool_name = tool_call.function.name
    tool_args = json.loads(tool_call.function.arguments)
    tool_id = tool_call.id
    
    # Execute the actual function
    if tool_name == "get_weather":
        result = get_weather(**tool_args)
    elif tool_name == "search_news":
        result = search_news(**tool_args)
    # ... etc
    
    executed_results[tool_id] = {
        "tool_name": tool_name,
        "result": result
    }
```

### Step 4: Feed Results Back to Agent

```python
# Add assistant response with tool calls to conversation
messages.append({
    "role": "assistant",
    "content": "",
    "tool_calls": tool_calls
})

# Add tool results for each execution
for tool_call in tool_calls:
    tool_id = tool_call.id
    result = executed_results[tool_id]["result"]
    
    messages.append({
        "role": "tool",
        "tool_call_id": tool_id,
        "content": json.dumps(result)  # Convert result to JSON string
    })

# Get final synthesis/response from agent
final_response = client.chat.completions.create(
    model="Athene-V2-Agent",
    messages=messages,
    tools=tools,
    temperature=0.0
)

print(final_response.choices[0].message.content)
```

***

## Example: Complete Weather + News Agent

Here's a complete, production-ready example:

```python
from openai import OpenAI
import json

# Initialize client (assuming llama.cpp server on localhost:8000)
client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="not-needed"
)

# Define tools
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get current weather information for a location. Provides temperature, conditions, humidity, and wind.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "City and state/country"},
                    "units": {"type": "string", "enum": ["celsius", "fahrenheit"], "description": "Temperature units"}
                },
                "required": ["location"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_news",
            "description": "Search for recent news articles on a topic.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query for news"},
                    "max_results": {"type": "integer", "description": "Maximum number of articles (1-10)"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "chat",
            "description": "Send a message or response to the user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "The message to send"}
                },
                "required": ["message"]
            }
        }
    }
]

# Mock tool implementations
def get_weather(location: str, units: str = "fahrenheit") -> dict:
    return {
        "location": location,
        "temperature": 65,
        "condition": "Partly Cloudy",
        "humidity": 60,
        "wind_speed": "8 mph"
    }

def search_news(query: str, max_results: int = 3) -> dict:
    return {
        "query": query,
        "articles": [
            {"title": f"Article 1 about {query}", "url": "http://example.com/1"},
            {"title": f"Article 2 about {query}", "url": "http://example.com/2"}
        ]
    }

def execute_tool(tool_name: str, tool_args: dict) -> dict:
    if tool_name == "get_weather":
        return get_weather(**tool_args)
    elif tool_name == "search_news":
        return search_news(**tool_args)
    else:
        return {"error": f"Unknown tool: {tool_name}"}

# System prompt
system_prompt = """You are an expert AI agent with access to real-time tools.
You can look up weather information and search for news articles.

Use tools to answer user queries accurately. When you have gathered enough information,
use the chat tool to provide a comprehensive response to the user."""

# User query
user_query = "What's the weather in Seattle and what's happening there in the news?"

# Initialize conversation
messages = [
    {"role": "system", "content": system_prompt},
    {"role": "user", "content": user_query}
]

# Agent loop
max_iterations = 5
iteration = 0

while iteration < max_iterations:
    iteration += 1
    
    # Call Athene V2 Agent
    response = client.chat.completions.create(
        model="Athene-V2-Agent",
        messages=messages,
        tools=tools,
        tool_choice="auto",
        temperature=0.0,
        max_tokens=2048
    )
    
    # Check if model wants to respond without tools
    if not response.choices[0].message.tool_calls:
        final_message = response.choices[0].message.content
        print(f"Agent: {final_message}")
        break
    
    # Extract and execute tool calls
    tool_calls = response.choices[0].message.tool_calls
    
    # Add assistant message with tool calls
    messages.append({
        "role": "assistant",
        "content": "",
        "tool_calls": tool_calls
    })
    
    # Execute tools and collect results
    for tool_call in tool_calls:
        tool_name = tool_call.function.name
        tool_args = json.loads(tool_call.function.arguments)
        
        print(f"→ Calling {tool_name}({tool_args})")
        
        # Execute the tool
        result = execute_tool(tool_name, tool_args)
        
        # Add result to messages
        messages.append({
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": json.dumps(result)
        })
    
    print(f"Iteration {iteration}: {len(tool_calls)} tool(s) called\n")
```

***

## Architecture Integration with llama.cpp

When running Athene V2 Agent 72B Q4_K_M with llama.cpp, ensure proper configuration:[2][1]

```bash
# Start llama.cpp server with OpenAI-compatible API
llama-server \
  -m athene-v2-agent-72b-q4_k_m.gguf \
  --port 8000 \
  --ctx-size 8192 \
  --n-gpu-layers 60 \
  --temperature 0 \
  --no-mmap
```

Key parameters:

- **--temperature 0**: Deterministic function calling (CRITICAL)
- **--ctx-size 8192**: Sufficient for reasoning through tool dependencies
- **--n-gpu-layers**: Offload layers to GPU (60-80 on Mac Studio M3 Ultra)[3]
- **--no-mmap**: Disable memory mapping for better performance on Metal

***

## Best Practices for Your Architecture

1. **Always set temperature=0** when calling Athene V2 Agent for function calling[1]
2. **Provide detailed, multi-line descriptions** for each tool—this dramatically improves accuracy[1]
3. **Include the `chat` tool** if you want conversational capability alongside function calling[1]
4. **Use `tool_choice="auto"`** to let the model decide when tools are necessary[1]
5. **Implement robust error handling** for tool execution failures and feed errors back to the model[8]
6. **Keep the context window efficient** by summarizing or truncating old tool results in long conversations
7. **Test with zero-shot examples** first—Athene V2 Agent generalizes well to unseen functions[4][1]

***

## Summary

Athene V2 Agent uses a **sophisticated architecture combining OpenAI-compatible tool schemas with Qwen-style chat templates**. The key to reliably triggering function calls is **detailed prompting, deterministic sampling (temperature=0), and well-structured JSON schemas**. With your Mac Studio M3 Ultra running llama.cpp, you can deploy Athene V2 Agent 72B Q4_K_M as a highly capable agentic system that will integrate seamlessly with MCP servers, web search APIs, and custom tools.[2][3][1]

Sources
[1] Nexusflow/Athene-V2-Agent - Hugging Face https://huggingface.co/Nexusflow/Athene-V2-Agent
[2] nexusflowai/NexusBench: Nexusflow function call, tool use ... - GitHub https://github.com/nexusflowai/NexusBench
[3] Athene V2 Agent - Agent LLM for Function Calling and ... - YouTube https://www.youtube.com/watch?v=64AqNKQRfJ0
[4] Athene V2 Agent 4.5bpw H8 Exl2 · Models - Dataloop https://dataloop.ai/library/model/ibrahimkettaneh_athene-v2-agent-45bpw-h8-exl2/
[5] Nexusflow/Athene-V2-Chat - Hugging Face https://huggingface.co/Nexusflow/Athene-V2-Chat
[6] The guide to structured outputs and function calling with LLMs https://agenta.ai/blog/the-guide-to-structured-outputs-and-function-calling-with-llms
[7] Athene V2 Agent · Models - Dataloop https://dataloop.ai/library/model/nexusflow_athene-v2-agent/
[8] LangChain Agent Executor Deep Dive - Aurelio AI https://www.aurelio.ai/learn/langchain-agent-executor
[9] Advanced prompt templates - Amazon Bedrock https://docs.aws.amazon.com/bedrock/latest/userguide/advanced-prompts-templates.html
[10] Function schema - OpenAI Agents SDK https://openai.github.io/openai-agents-python/ref/function_schema/
[11] Nexusflow release Athene-V2-Chat and Athene-V2-Agent - Reddit https://www.reddit.com/r/LocalLLaMA/comments/1grcx0h/nexusflow_release_athenev2chat_and_athenev2agent/
[12] Agent Function Calling Eval | Arize Phoenix https://arize.com/docs/phoenix/evaluation/running-pre-tested-evals/tool-calling-eval
[13] [Bug]: Tool calling and JSON schema guided generation not working ... https://github.com/vllm-project/vllm/issues/17481
[14] Open-Weight alternative to GPT-4o Realtime, Athene-V2 ... - AI Brews https://aibrews.substack.com/p/open-weight-alternative-to-gpt-4o
[15] How to implement function calling using only prompt? : r/LocalLLaMA https://www.reddit.com/r/LocalLLaMA/comments/1anaatm/how_to_implement_function_calling_using_only/
[16] AI Model Catalog | Azure AI Foundry Models https://ai.azure.com/catalog/models/nexusflow-athene-v2-agent
[17] Code Execution - AG2 docs https://docs.ag2.ai/latest/docs/user-guide/advanced-concepts/code-execution/
[18] Athene V2 Agent GGUF · Models - Dataloop https://dataloop.ai/library/model/bartowski_athene-v2-agent-gguf/
