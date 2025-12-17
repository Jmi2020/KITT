# Cloud LLM Providers for Collective Intelligence

Last updated: December 2025

This document details the cloud LLM providers available for the Collective Intelligence multi-agent deliberation system.

## Overview

The Collective system supports mixing local and cloud LLM specialists to form a council for deliberation tasks. Cloud providers are integrated via the **litellm** SDK.

## Required Environment Variables

```bash
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
PERPLEXITY_API_KEY=pplx-...
GOOGLE_API_KEY=AIza...
```

These are configured in `.env` and passed to the brain container via `docker-compose.yml`.

---

## OpenAI Models

| Model ID | Display Name | Description | Cost (per 1M tokens) |
|----------|--------------|-------------|----------------------|
| `gpt-5` | GPT-5 | Latest flagship with full reasoning | $1.25 in / $10.00 out |
| `gpt-5.2` | GPT-5.2 | Cutting-edge with 400K context | $1.75 in / $14.00 out |
| `gpt-5-mini` | GPT-5-mini | Cost-effective GPT-5 variant | $0.25 in / $2.00 out |
| `gpt-4o-mini` | GPT-4o-mini | Fast affordable legacy model | $0.15 in / $0.60 out |

**Litellm format:** Model name directly (e.g., `gpt-5.2`)

---

## Anthropic Models

| Model ID | Display Name | Description | Cost (per 1M tokens) |
|----------|--------------|-------------|----------------------|
| `claude-sonnet-4-5` | Claude Sonnet 4.5 | Best coding and agentic model | $3.00 in / $15.00 out |
| `claude-opus-4-5` | Claude Opus 4.5 | Frontier model for difficult reasoning | $5.00 in / $25.00 out |
| `claude-haiku-4-5` | Claude Haiku 4.5 | Fast cost-effective Claude 4 | $1.00 in / $5.00 out |

**Litellm format:** `anthropic/{model}` (e.g., `anthropic/claude-sonnet-4-5`)

**Note:** Released Nov-Dec 2025. Requires active Anthropic API credits.

---

## Perplexity Models

| Model ID | Display Name | Description | Cost (per 1M tokens) |
|----------|--------------|-------------|----------------------|
| `sonar` | Sonar | Search-augmented with real-time citations | $1.00 in / $1.00 out |
| `sonar-pro` | Sonar Pro | Advanced search reasoning | $3.00 in / $15.00 out |

**Litellm format:** `perplexity/{model}` (e.g., `perplexity/sonar`)

**Note:** Responses include citation markers like `[1][2]` referencing web sources.

---

## Google Gemini Models

| Model ID | Display Name | Description | Cost (per 1M tokens) |
|----------|--------------|-------------|----------------------|
| `gemini-3-pro-preview` | Gemini 3 Pro | Newest generation, 1M context | $2.00 in / $12.00 out |
| `gemini-2.5-pro` | Gemini 2.5 Pro | Advanced thinking, multimodal | $1.25 in / $5.00 out |
| `gemini-2.5-flash` | Gemini 2.5 Flash | Fast with 1M context | $0.15 in / $0.60 out |

**Litellm format:** `gemini/{model}` (e.g., `gemini/gemini-2.5-flash`)

**Note:** Free tier has strict quota limits. Paid billing recommended for production use.

---

## Local Models (Free)

| Model ID | Display Name | llama.cpp Port | Description |
|----------|--------------|----------------|-------------|
| `Q4` | Athene V2 | 8083 | Tool orchestration and general reasoning |
| `CODER` | Qwen 2.5 Coder 32B | 8087 | Code generation and analysis |
| `Q4B` | Mistral 7B | 8084 | Fast responses and diverse perspectives |

---

## Integration Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Collective System                         │
├─────────────────────────────────────────────────────────────┤
│  providers.py          → Specialist configs (id, model, cost)│
│  graph_async.py        → generate_proposal_for_specialist()  │
│  llm_client.py         → chat_async() with litellm routing   │
└─────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
         ┌─────────┐    ┌──────────┐    ┌─────────┐
         │ OpenAI  │    │Anthropic │    │ Gemini  │
         │   API   │    │   API    │    │   API   │
         └─────────┘    └──────────┘    └─────────┘
```

## Cost Estimation

The system estimates costs before running based on:
- ~2000 input tokens per proposal (system + user prompt)
- ~2000 output tokens per proposal (specialist response)

Example for 4 specialists (GPT-5.2 + Sonnet 4.5 + Sonar + Gemini 2.5 Pro):
- GPT-5.2: (2000/1M × $1.75) + (2000/1M × $14.00) = $0.0315
- Sonnet 4.5: (2000/1M × $3.00) + (2000/1M × $15.00) = $0.036
- Sonar: (2000/1M × $1.00) + (2000/1M × $1.00) = $0.004
- Gemini 2.5 Pro: (2000/1M × $1.25) + (2000/1M × $5.00) = $0.0125

**Total estimated: ~$0.084 per deliberation**

---

## Troubleshooting

### "Model not found" errors
- Verify the exact model ID matches the provider's API
- Check litellm documentation for correct format

### "Credit balance too low" (Anthropic)
- Purchase credits at https://console.anthropic.com/settings/billing

### "Quota exceeded" (Gemini)
- Enable billing in Google Cloud Console
- Wait for rate limit reset (shown in error message)

### Fallback behavior
- If a cloud provider fails, the system falls back to local models
- Check `metadata["fallback_occurred"]` in responses
