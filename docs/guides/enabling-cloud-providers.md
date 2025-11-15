# User Guide: Enabling Cloud Providers in KITT

**Last Updated:** November 15, 2025
**Audience:** KITT operators and administrators
**Difficulty:** Beginner

---

## Overview

KITT supports multiple cloud LLM providers to enhance collective meta-agent diversity while maintaining offline-first operation. This guide shows you how to enable and use cloud providers like OpenAI, Anthropic, Mistral, Perplexity, and Google Gemini.

**Key Benefits:**
- 🎯 **3x Opinion Diversity**: Get different perspectives in council/debate patterns
- 💰 **Cost Control**: Default OFF, only pay when you use it
- 🔄 **Automatic Fallback**: Always falls back to local Q4 if cloud unavailable
- ⚡ **Zero Overhead**: Lazy loading means no performance impact when disabled

---

## Prerequisites

Before enabling cloud providers, ensure:

1. ✅ KITT is running (`./ops/scripts/start-kitty.sh`)
2. ✅ You have budget allocated for cloud API calls
3. ✅ You have API keys from desired providers
4. ✅ You've read the cost warnings in I/O Control Dashboard

---

## Step 1: Get API Keys

### OpenAI (Recommended for Beginners)

**Cost:** $0.15/1M input tokens, $0.60/1M output tokens (gpt-4o-mini)

1. Visit https://platform.openai.com/api-keys
2. Click "Create new secret key"
3. Name it "KITTY" and copy the key (starts with `sk-`)
4. **Store securely** - you won't see it again!

### Anthropic (Claude)

**Cost:** $0.25/1M input tokens, $1.25/1M output tokens (claude-3-5-haiku)

1. Visit https://console.anthropic.com/settings/keys
2. Click "Create Key"
3. Name it "KITTY" and copy the key (starts with `sk-ant-`)

### Mistral AI

**Cost:** $0.10/1M input tokens, $0.30/1M output tokens (mistral-small)

1. Visit https://console.mistral.ai/api-keys
2. Click "Create new key"
3. Copy the key

### Perplexity

**Cost:** $0.20/1M tokens (combined input+output)

1. Visit https://www.perplexity.ai/settings/api
2. Generate API key
3. Copy the key (starts with `pplx-`)

### Google Gemini

**Cost:** $0.075/1M input tokens, $0.30/1M output tokens (gemini-1.5-flash)

1. Visit https://aistudio.google.com/app/apikey
2. Create API key
3. Copy the key

---

## Step 2: Add API Keys to .env

1. **Stop KITT Services:**
   ```bash
   ./ops/scripts/stop-kitty.sh
   ```

2. **Edit .env file:**
   ```bash
   nano /Users/Shared/Coding/KITT/.env
   ```

3. **Add your API keys:**
   ```bash
   # Add to .env (example for OpenAI)
   OPENAI_API_KEY=sk-proj-your-actual-key-here

   # Example for Anthropic
   ANTHROPIC_API_KEY=sk-ant-your-actual-key-here

   # Example for Mistral
   MISTRAL_API_KEY=your-mistral-key-here

   # Example for Perplexity
   PERPLEXITY_API_KEY=pplx-your-actual-key-here

   # Example for Gemini
   GEMINI_API_KEY=your-gemini-key-here
   ```

4. **Save and exit** (Ctrl+O, Enter, Ctrl+X)

---

## Step 3: Enable Providers

### Option A: Environment Variables (Recommended)

**Edit .env again:**
```bash
# Enable providers (set to true)
ENABLE_OPENAI_COLLECTIVE=true
ENABLE_ANTHROPIC_COLLECTIVE=false  # Leave others disabled initially
ENABLE_MISTRAL_COLLECTIVE=false
ENABLE_PERPLEXITY_COLLECTIVE=false
ENABLE_GEMINI_COLLECTIVE=false
```

### Option B: I/O Control Dashboard (Runtime)

1. Start KITT: `./ops/scripts/start-kitty.sh`
2. Access I/O Control Dashboard (TUI)
3. Navigate to "Collective Providers" category
4. Toggle "OpenAI Collective" to ENABLED
5. Confirm cost warning
6. Changes apply immediately (hot-reload)

---

## Step 4: Restart KITT

```bash
./ops/scripts/start-kitty.sh
```

**Verify startup logs:**
```
[INFO] Initialized provider 'openai' for collective meta-agent
[INFO] Brain service ready
```

---

## Step 5: Test Provider Access

### CLI Test

```bash
kitty-cli shell

# Check available providers
/providers

# Expected output:
Available providers:
  ✓ local (Q4, F16, CODER, Q4B) - Always available
  ✓ openai (gpt-4o-mini, gpt-4o, o1-mini, o1-preview)
  ✗ anthropic (ENABLE_ANTHROPIC_COLLECTIVE=false)
  ...

# Set provider
/provider openai
✓ Provider set to: openai (gpt-4o-mini)

# Test query
What is 2+2?

# Expected output:
[Using: openai/gpt-4o-mini | Tokens: 15 | Cost: $0.0001]
4
```

### API Test

```bash
curl -X GET http://localhost:8000/api/providers/available | jq '.providers.openai.enabled'
# Expected: true

curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{
    "conversationId": "test-123",
    "userId": "test-user",
    "intent": "conversation.chat",
    "prompt": "Say: OK",
    "provider": "openai"
  }'
```

---

## Usage Patterns

### 1. Persistent Provider Selection (CLI)

```bash
kitty-cli shell

# Set provider for whole session
/provider openai

# All subsequent queries use OpenAI
What is quantum computing?
Explain photosynthesis.

# Reset to local
/provider local
```

### 2. Inline Syntax (One-Off Override)

```bash
# Use OpenAI for one query only
@openai: What is the capital of France?

# Use specific model
#gpt-4o-mini: Explain relativity

# Next query uses default (local)
What is 1+1?
```

### 3. Web UI Dropdown (Future)

- Click provider selector in chat input
- Choose provider from dropdown
- Selection persists for session

### 4. API Parameters (Programmatic)

```python
import httpx

response = httpx.post("http://localhost:8000/api/query", json={
    "conversationId": "my-conv",
    "userId": "my-user",
    "intent": "conversation.chat",
    "prompt": "Explain AI",
    "provider": "openai",  # Override provider
    "model": "gpt-4o-mini",  # Optional: specify model
})
```

---

## Cost Management

### Monitor Usage

**Check reasoning logs:**
```bash
tail -f .logs/reasoning.jsonl | grep provider_used
```

**View cost per query:**
```bash
kitty-cli shell
/usage
```

### Set Budget Limits

**Edit .env:**
```bash
# Daily budget for autonomous operations
AUTONOMOUS_DAILY_BUDGET_USD=5.00

# Budget per task (advisory)
BUDGET_PER_TASK_USD=0.50
```

### Estimate Costs

| Use Case | Queries/Day | Provider | Estimated Daily Cost |
|----------|-------------|----------|----------------------|
| Light (CLI only) | 20-50 | OpenAI | $0.01-0.05 |
| Moderate (Mixed) | 100-200 | OpenAI | $0.05-0.15 |
| Heavy (Autonomous) | 500+ | OpenAI | $0.50+ |

**Formula:**
`Cost = (Input Tokens × $0.15 + Output Tokens × $0.60) / 1,000,000`

---

## Troubleshooting

### "Provider X is disabled"

**Cause:** Feature flag not enabled or API key missing

**Solution:**
1. Check `.env`: `ENABLE_OPENAI_COLLECTIVE=true`
2. Check API key: `OPENAI_API_KEY=sk-...`
3. Restart brain service

### "Fallback to local Q4"

**Cause:** Provider temporarily unavailable (network issue, rate limit, invalid key)

**Solution:**
- Check reasoning logs: `tail -f .logs/reasoning.log`
- Verify API key is valid
- Check network connectivity
- Check provider status page

### High Costs

**Cause:** Too many cloud queries or large conversations

**Solution:**
1. Review `reasoning.jsonl` for usage patterns
2. Lower `BUDGET_PER_TASK_USD`
3. Disable autonomous mode temporarily
4. Switch to cheaper provider (Mistral)
5. Use inline syntax for specific queries only

### Slow Responses

**Cause:** Network latency to cloud provider

**Expected:** Cloud queries are slower than local (200-500ms network overhead)

**Solution:**
- Use local provider for simple queries
- Reserve cloud for complex tasks
- Check internet connection

---

## Best Practices

### 1. Start Conservative

- ✅ Enable ONE provider initially (OpenAI recommended)
- ✅ Test with small queries first
- ✅ Monitor costs for 1 week before expanding

### 2. Use Inline Syntax for Experiments

```bash
# Compare answers without changing defaults
@openai: Explain quantum mechanics
@anthropic: Explain quantum mechanics
Regular query (uses default local)
```

### 3. Reserve Cloud for Complex Tasks

**Good Use Cases:**
- Council/debate patterns (diverse opinions)
- Research queries requiring fresh data
- Complex reasoning tasks
- Coding tasks with specific models

**Bad Use Cases:**
- Simple math (2+2)
- Frequently asked questions
- Offline-capable queries
- Testing/debugging

### 4. Monitor and Adjust

**Weekly Review:**
1. Check total cloud costs: `kitty-cli /usage`
2. Review cost per query type
3. Adjust provider selection strategy
4. Disable unused providers

---

## Security Reminders

🔒 **DO:**
- Store API keys in `.env` (gitignored)
- Rotate keys every 90 days
- Use read-only keys when available
- Monitor usage for anomalies

❌ **DON'T:**
- Commit API keys to git
- Share keys via email/chat
- Use root keys (use scoped keys)
- Leave keys in logs

---

## Getting Help

**If you need assistance:**

1. Check troubleshooting runbook: `docs/runbooks/multi-provider-troubleshooting.md`
2. Review reasoning logs: `.logs/reasoning.log`
3. Search issues: https://github.com/anthropics/claude-code/issues
4. Ask in CLI: `kitty-cli say "How do I enable OpenAI?"`

---

## Summary Checklist

Before enabling cloud providers, verify:

- [x] Read cost warnings
- [x] Obtained API key from provider
- [x] Added key to `.env`
- [x] Enabled provider flag
- [x] Restarted KITT services
- [x] Tested with simple query
- [x] Monitored first few queries
- [x] Set budget limits

**Estimated Setup Time:** 10-15 minutes
**Recommended First Provider:** OpenAI (cheap, reliable, well-documented)

---

**Next Steps:** Once comfortable with one provider, explore multi-provider councils for maximum diversity!
