Below is a deeply technical, fully markdown-formatted `.md` guide tailored for a coding agent (e.g., Claude, Codex) to follow. It explains Perplexity API usage and local LLM integration, with explicit sections for prerequisites, code actions, architecture choices, and patterns for robust AI workflow integration.

***

# Perplexity API Integration Deep Dive

A comprehensive technical guide for integrating the Perplexity API into local LLM workflows, designed for advanced coding agents and developers.

***

## Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Authentication & Setup](#authentication--setup)
- [API Usage Basics](#api-usage-basics)
- [Model Selection & Features](#model-selection--features)
- [Advanced Parameters](#advanced-parameters)
- [Streaming and Async Patterns](#streaming-and-async-patterns)
- [OpenAI-Compatible Integration](#openai-compatible-integration)
- [Proxy Layer (LiteLLM) Setup](#proxy-layer-litellm-setup)
- [Direct Hybrid LLM Routing](#direct-hybrid-llm-routing)
- [Tool/Agent Pattern](#toolagent-pattern)
- [Security & Best Practices](#security--best-practices)
- [Error Handling Patterns](#error-handling-patterns)
- [Resources](#resources)

***

## Overview

Perplexity API delivers state-of-the-art, real-time web-grounded LLM capabilities with OpenAI compatibility and search-augmented answers. Integrating it with local LLMs such as those hosted via Ollama or LM Studio enables hybrid workflows for privacy, performance, and current real-world knowledge[1][2][3][4][5][6].

***

## Prerequisites

- Python 3.8+
- An API key from [Perplexity](https://perplexity.ai/)
- Local LLM runtime (e.g., Ollama, vLLM, LM Studio), accessible via OpenAI-compatible API
- Familiarity with `.env` or environment variables, Docker (optional)
- OpenAI or Perplexity Python SDKs installed

```bash
pip install perplexity openai litellm
```
or, for a broader agent stack:
```bash
pip install langchain langchain-openai fastapi
```

***

## Authentication & Setup

1. **Acquire Perplexity API Key:**
   - Sign up or log in at Perplexity → Go to API Settings → Register payment method.
   - Purchase API credits if prompted.
   - Generate and copy your API key[2][7][8].

2. **Store API Key Securely:**
   - Add to shell startup or project `.env`:
     ```env
     PERPLEXITY_API_KEY=sk-xxxxxxxxxxxxxxxxxxxx
     ```
   - In your Python environment, load this securely:
     ```python
     import os
     api_key = os.environ["PERPLEXITY_API_KEY"]
     ```

***

## API Usage Basics

**First API Call (Perplexity SDK):**
```python
from perplexity import Perplexity

client = Perplexity()
resp = client.chat.completions.create(
    model="sonar-pro",
    messages=[{"role": "user", "content": "Latest stable release of Python?"}]
)
print(resp.choices[0].message.content)
```

**OpenAI SDK, Perplexity Compatible:**
```python
from openai import OpenAI
client = OpenAI(
    api_key=api_key,
    base_url="https://api.perplexity.ai"
)
resp = client.chat.completions.create(
    model="sonar-pro",
    messages=[{"role": "user", "content": "Show breaking news in AI"}]
)
print(resp.choices[0].message.content)
```

***

## Model Selection & Features

Perplexity supports these models[9][10][11]:

| Model                | Context Window | Use Case                        | Pricing (per 1M tokens)         |
|----------------------|---------------|----------------------------------|---------------------------------|
| `sonar`              | 128K          | Fast, general search             | $0.2/input, $0.2/output         |
| `sonar-pro`          | 200K          | Deep research, multi-step        | $3/input, $15/output            |
| `sonar-reasoning`    | 128K          | Chain-of-thought, logic          | $1/input, $5/output             |
| `sonar-reasoning-pro`| 128K          | CoT + DeepSeek, visible steps    | $2/input, $8/output             |
| `sonar-deep-research`| 128K          | Complex, async queries           | [Contact for pricing]           |

***

## Advanced Parameters

You can pass search-specific parameters in `extra_body` (Perplexity SDK) or `openai_extra_body` (OpenAI SDK):

- `search_domain_filter`: domains to include/exclude
- `search_recency_filter`: `"week"`, `"month"` etc.
- `return_images`: `true`/`false`
- `return_related_questions`: `true`/`false`

**Example:**
```python
resp = client.chat.completions.create(
    model="sonar-pro",
    messages=[{"role": "user", "content": "New materials in battery tech"}],
    extra_body={
        "search_domain_filter": ["nature.com", "science.org"],
        "search_recency_filter": "month",
        "return_related_questions": True
    }
)
print(resp.choices[0].message.content)
```

***

## Streaming and Async Patterns

**Token Streaming:**
```python
stream = client.chat.completions.create(
    model="sonar",
    messages=[{"role": "user", "content": "Summarize GPT-5 vs GPT-4"}],
    stream=True
)

for chunk in stream:
    print(chunk.choices[0].delta.content, end='', flush=True)
```

**Async Queries:**
- Use `/async/chat/completions` endpoint for long research tasks; poll for results[12].

***

## OpenAI-Compatible Integration

You can drop Perplexity into code written for OpenAI-style APIs by swapping the base URL:

```python
client = OpenAI(
    api_key=os.environ["PERPLEXITY_API_KEY"],
    base_url="https://api.perplexity.ai"
)
```

***

## Proxy Layer (LiteLLM) Setup

**Recommended for hybrid (local + Perplexity) routing using OpenAI client interface across all models.**

1. **Install and configure `litellm`:**

   _config.yaml_:
   ```yaml
   model_list:
    - model_name: local-llama
      litellm_params:
        model: ollama/llama3
        api_base: http://localhost:11434
    - model_name: perplexity-web
      litellm_params:
        model: perplexity/sonar-pro
        api_key: ${PERPLEXITY_API_KEY}
   ```

2. **Run the proxy locally:**
   ```bash
   litellm --config ./config.yaml
   # Proxy is now at http://localhost:4000
   ```

3. **Access via OpenAI interface:**
   ```python
   client = OpenAI(api_key="sk-1234", base_url="http://localhost:4000")
   resp = client.chat.completions.create(
       model="perplexity-web",  # Or "local-llama"
       messages=[{"role": "user", "content": "What's new in Python 3.13?"}]
   )
   ```

***

## Direct Hybrid LLM Routing

**Pattern to select either local LLM or Perplexity based on query context:**

```python
class HybridLLM:
    def __init__(self):
        self.local_client = OpenAI(api_key="-", base_url="http://localhost:1234/v1")
        self.pplx_client = Perplexity()

    def needs_web(self, query):
        keywords = ["latest", "news", "price", "update", "who won"]
        return any(k in query.lower() for k in keywords)

    def run(self, prompt):
        if self.needs_web(prompt):
            return self.pplx_client.chat.completions.create(
                model="sonar-pro",
                messages=[{"role": "user", "content": prompt}]
            ).choices[0].message.content
        else:
            return self.local_client.chat.completions.create(
                model="local-model",
                messages=[{"role": "user", "content": prompt}]
            ).choices[0].message.content
```

***

## Tool/Agent Pattern

**Expose Perplexity as a tool in your agent framework (e.g., LangChain, function-calling agents):**

```python
from openai import AsyncOpenAI
from agents import Agent, function_tool

perplexity_client = AsyncOpenAI(
    base_url="https://api.perplexity.ai",
    api_key=os.environ["PERPLEXITY_API_KEY"]
)

@function_tool
def search_web(query: str) -> str:
    resp = perplexity_client.chat.completions.create(
        model="sonar-pro",
        messages=[{"role": "user", "content": query}]
    )
    return resp.choices[0].message.content
```

***

## Security & Best Practices

- Never hardcode API keys; use environment secrets or secret managers.
- Rotate API keys every 90 days. Monitor usage for abuse[8].
- Use exponential backoff for error/retry logic and observe rate limits[13].
- Choose appropriate models for balancing cost, speed, and depth[10][11].
- Cache or log responses (with privacy in mind) to minimize API usage cost.

***

## Error Handling Patterns

**Structured Error Handling:**
```python
from perplexity import Perplexity, APIConnectionError, RateLimitError, APIStatusError

client = Perplexity()
try:
    resp = client.chat.completions.create( # ... )
except APIConnectionError as e:
    print(f"Network failed: {e}")
except RateLimitError:
    # Implement backoff/retry
    pass
except APIStatusError as e:
    print(f"API error ({e.status_code}): {e.response}")
except Exception as e:
    print(f"Unknown error: {e}")
```

***

## Resources

- [Perplexity API Docs](https://docs.perplexity.ai/)  
- [LiteLLM Docs for Gateway Setup](https://docs.litellm.ai/)  
- [Ollama Local Model Hosting](https://ollama.com/)  
- [LangChain OpenAI Integration](https://python.langchain.com/v0.1/docs/integrations/llms/openai/)  
- [Security Best Practices - Perplexity Docs][8]

***

_Note: Replace environment/config paths, model names, and port numbers as appropriate for your local deployments._

Sources
[1] Search API - Perplexity https://docs.perplexity.ai/guides/search-guide
[2] Quickstart - Perplexity https://docs.perplexity.ai/getting-started/quickstart
[3] Streaming Responses - Perplexity https://docs.perplexity.ai/guides/streaming-responses
[4] OpenAI Compatibility - Perplexity https://docs.perplexity.ai/guides/chat-completions-guide
[5] 14 Perplexity AI Use Cases https://learnprompting.org/blog/perplexity_use_cases
[6] Perplexity AI Search - LiteLLM https://docs.litellm.ai/docs/search/perplexity
[7] API settings | Perplexity Help Center https://www.perplexity.ai/help-center/en/articles/10352995-api-settings
[8] API Key Management - Perplexity https://docs.perplexity.ai/guides/api-key-management
[9] Perplexity AI All Models Available: list, categories, usage, etc https://www.datastudios.org/post/perplexity-ai-all-models-available-list-categories-usage-etc
[10] Sonar pro - Perplexity https://docs.perplexity.ai/getting-started/models/models/sonar-pro
[11] complete list with Sonar family, GPT-5, Claude, Gemini and more. https://www.datastudios.org/post/all-perplexity-models-available-in-2025-complete-list-with-sonar-family-gpt-5-claude-gemini-and
[12] https://docs.perplexity.ai/llms-full.txt https://docs.perplexity.ai/llms-full.txt
[13] Rate Limits and Usage Tiers - Perplexity https://docs.perplexity.ai/guides/usage-tiers
