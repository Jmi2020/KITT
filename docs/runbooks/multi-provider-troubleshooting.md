# Multi-Provider Troubleshooting Runbook

**Last Updated:** November 15, 2025
**Audience:** KITT operators and administrators
**Purpose:** Diagnose and fix common multi-provider issues

---

## Quick Diagnosis

Use this decision tree to identify your issue:

```
Problem?
├─ Provider shows "disabled" in /providers
│  └─ → Section 1: Provider Not Enabled
├─ Query falls back to local unexpectedly
│  └─ → Section 2: Automatic Fallback Issues
├─ High costs
│  └─ → Section 3: Cost Management
├─ Slow responses
│  └─ → Section 4: Performance Issues
├─ Error messages
│  └─ → Section 5: API Errors
└─ Other
   └─ → Section 6: Advanced Diagnostics
```

---

## Section 1: Provider Not Enabled

### Symptoms
- `/providers` shows provider as disabled (✗)
- Queries always use local Q4
- "Provider X is disabled" in logs

### Root Causes

#### 1.1 Feature Flag Not Set

**Diagnosis:**
```bash
grep ENABLE_OPENAI_COLLECTIVE .env
```

**Expected:** `ENABLE_OPENAI_COLLECTIVE=true`
**Actual:** `ENABLE_OPENAI_COLLECTIVE=false` or missing

**Solution:**
```bash
# Edit .env
nano .env

# Add or change
ENABLE_OPENAI_COLLECTIVE=true

# Restart brain service
docker compose restart brain
```

**Verification:**
```bash
kitty-cli shell
/providers
# Should show: ✓ openai (gpt-4o-mini, ...)
```

---

#### 1.2 API Key Missing or Invalid

**Diagnosis:**
```bash
grep OPENAI_API_KEY .env
```

**Expected:** `OPENAI_API_KEY=sk-proj-...` (51+ characters)
**Actual:** Empty, `***`, or too short

**Solution:**
```bash
# Get new API key from https://platform.openai.com/api-keys
# Add to .env
OPENAI_API_KEY=sk-proj-your-actual-key-here

# Restart brain service
docker compose restart brain
```

**Verification:**
```bash
# Check health
curl http://localhost:8000/api/providers/available | jq '.providers.openai.enabled'
# Expected: true
```

---

#### 1.3 Wrong API Key Format

**Diagnosis:**
Check key format for each provider:

| Provider | Format | Example |
|----------|--------|---------|
| OpenAI | `sk-...` or `sk-proj-...` | `sk-proj-abc123...` |
| Anthropic | `sk-ant-...` | `sk-ant-api123...` |
| Mistral | No specific prefix | `abc123...` |
| Perplexity | `pplx-...` | `pplx-abc123...` |
| Gemini | No specific prefix | `AIza...` |

**Solution:**
- Regenerate API key from provider dashboard
- Copy entire key (no truncation)
- Remove any whitespace or quotes

---

## Section 2: Automatic Fallback Issues

### Symptoms
- Query uses local Q4 instead of requested provider
- "Fallback occurred" in metadata
- Warning in reasoning logs

### Root Causes

#### 2.1 Provider Temporarily Unavailable

**Diagnosis:**
```bash
# Check reasoning logs
tail -20 .logs/reasoning.log | grep fallback

# Expected pattern:
# [WARN] Cloud provider 'openai' failed: ... Falling back to local Q4
```

**Common Causes:**
- Network timeout
- Provider API downtime
- Rate limiting
- Invalid response

**Solution:**
```bash
# Test provider API directly
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY"

# If fails:
# 1. Check internet connection
# 2. Verify API key is valid
# 3. Check provider status page
# 4. Try again in 1 minute (rate limits)
```

---

#### 2.2 any-llm SDK Not Installed

**Diagnosis:**
```bash
docker exec brain python -c "import any_llm"
```

**Expected:** No output (success)
**Actual:** `ModuleNotFoundError: No module named 'any_llm'`

**Solution:**
```bash
# Add to brain service requirements
echo "any-llm-sdk>=1.0.0" >> services/brain/requirements.txt

# Rebuild brain service
docker compose build brain
docker compose restart brain
```

---

#### 2.3 Network Connectivity Issues

**Diagnosis:**
```bash
# From KITT host, test connectivity
curl -I https://api.openai.com
curl -I https://api.anthropic.com

# From inside brain container
docker exec brain curl -I https://api.openai.com
```

**Solution:**
- Check firewall rules
- Verify DNS resolution
- Test proxy settings (if applicable)
- Check docker network configuration

---

## Section 3: Cost Management

### Symptoms
- Higher than expected cloud costs
- Rapid budget depletion
- Unexpected charges

### Root Causes

#### 3.1 Autonomous Mode Running Uncontrolled

**Diagnosis:**
```bash
grep AUTONOMOUS_ENABLED .env
grep AUTONOMOUS_DAILY_BUDGET_USD .env

# Check autonomous logs
docker logs brain | grep autonomous
```

**Solution:**
```bash
# Disable autonomous temporarily
AUTONOMOUS_ENABLED=false

# Or lower budget
AUTONOMOUS_DAILY_BUDGET_USD=1.00

# Restart
docker compose restart brain
```

---

#### 3.2 Large Context Windows

**Diagnosis:**
```bash
# Check recent query token counts
tail -50 .logs/reasoning.jsonl | jq '.tokens_used'
```

**Solution:**
- Use `/reset` in CLI to clear conversation history
- Avoid pasting large documents into queries
- Use local provider for simple queries

---

#### 3.3 Expensive Model Selected

**Diagnosis:**
```bash
# Check which models are being used
tail -50 .logs/reasoning.jsonl | jq '.model_used'
```

**Cost per 1M tokens:**
- gpt-4o-mini: $0.15 in, $0.60 out ✅ Cheap
- gpt-4o: $2.50 in, $10.00 out ⚠️ Expensive
- claude-3-5-sonnet: $3.00 in, $15.00 out ⚠️ Very Expensive

**Solution:**
```bash
# Use cheaper models
/model gpt-4o-mini  # Not gpt-4o
/model claude-3-5-haiku  # Not claude-3-5-sonnet
```

---

## Section 4: Performance Issues

### Symptoms
- Slow response times
- Timeouts
- High latency

### Root Causes

#### 4.1 Normal Cloud Latency

**Diagnosis:**
Cloud queries are expected to be slower due to network round-trip time.

**Benchmarks:**
| Query Type | Expected Latency |
|------------|------------------|
| Local Q4 | 200-2000ms |
| Cloud (OpenAI) | 500-3000ms |
| Cloud (Anthropic) | 800-4000ms |

**Solution:**
- This is normal behavior
- Use local for latency-sensitive queries
- Reserve cloud for quality-critical tasks

---

#### 4.2 Rate Limiting

**Diagnosis:**
```bash
# Look for 429 errors in logs
docker logs brain | grep "429"
```

**Solution:**
- Reduce query rate
- Upgrade provider tier (higher limits)
- Implement exponential backoff (already done in client)

---

#### 4.3 Connection Pooling Issues

**Diagnosis:**
```bash
# Check if connections are being reused
docker logs brain | grep "Initialized provider"
```

**Expected:** Only once per provider
**Actual:** Many times (connection not pooled)

**Solution:**
- Ensure using latest any-llm SDK
- Restart brain service to reset connections

---

## Section 5: API Errors

### Common Error Messages

#### 5.1 "Invalid API Key"

**Error:** `401 Unauthorized` or `Invalid API key`

**Solution:**
1. Regenerate API key from provider dashboard
2. Update `.env` with new key
3. Restart brain service
4. Test with simple query

---

#### 5.2 "Insufficient Quota"

**Error:** `429 Too Many Requests` or `Quota exceeded`

**Solution:**
1. Check provider billing dashboard
2. Add payment method or increase quota
3. Temporarily disable provider
4. Use local fallback

---

#### 5.3 "Model Not Found"

**Error:** `404 Not Found` or `Model does not exist`

**Common Mistake:**
- `gpt-4o-mini` (correct) vs `gpt4-o-mini` (wrong)
- `claude-3-5-haiku-20241022` (correct) vs `claude-haiku` (wrong)

**Solution:**
Use exact model names from provider docs:
```bash
# Check available models
curl http://localhost:8000/api/providers/available | jq '.providers.openai.models'
```

---

#### 5.4 "Context Length Exceeded"

**Error:** `Maximum context length exceeded`

**Solution:**
```bash
# Clear conversation history
/reset

# Or split large queries into smaller chunks
```

---

## Section 6: Advanced Diagnostics

### 6.1 Enable Debug Logging

**Temporary:**
```bash
# Set log level to DEBUG
export REASONING_LOG_LEVEL=DEBUG

# Restart brain service
docker compose restart brain

# View detailed logs
tail -f .logs/reasoning.log
```

**Permanent:**
```bash
# Edit .env
REASONING_LOG_LEVEL=DEBUG

# Restart
docker compose restart brain
```

---

### 6.2 Test Provider Registry Directly

**Python REPL:**
```python
# SSH into brain container
docker exec -it brain python

# Test provider registry
from brain.llm_client import ProviderRegistry

registry = ProviderRegistry()

# Check if provider is enabled
print(registry.is_enabled("openai"))  # Should be True

# Try to get provider
provider = registry.get_provider("openai")
print(provider)  # Should not be None
```

---

### 6.3 Check Brain Service Health

**HTTP Health Check:**
```bash
curl http://localhost:8000/health
# Expected: {"status": "ok"}

curl http://localhost:8000/api/providers/available
# Expected: JSON with providers list
```

**Docker Status:**
```bash
docker ps | grep brain
# Expected: STATUS = Up

docker logs brain --tail 50
# Look for errors
```

---

### 6.4 Verify Environment Variables

**Inside Container:**
```bash
docker exec brain env | grep ENABLE_
docker exec brain env | grep API_KEY

# Verify keys are loaded correctly (redacted)
docker exec brain python -c "import os; print('OpenAI:', 'sk-' in os.getenv('OPENAI_API_KEY', ''))"
```

---

## Common Fixes Quick Reference

| Problem | Quick Fix | Time |
|---------|-----------|------|
| Provider disabled | Set `ENABLE_X_COLLECTIVE=true` in .env | 1 min |
| Invalid API key | Regenerate from provider dashboard | 3 min |
| High costs | Lower budget or disable autonomous | 1 min |
| Slow queries | Use local for simple queries | 0 min |
| Fallback errors | Check reasoning.log, restart brain | 2 min |
| Module not found | Install any-llm-sdk, rebuild | 5 min |

---

## Escalation Path

If issue persists after troubleshooting:

1. **Gather Diagnostic Info:**
   ```bash
   # Create support bundle
   tar czf kitty-debug-$(date +%Y%m%d).tar.gz \
     .logs/reasoning.log \
     .logs/reasoning.jsonl \
     .env.example \
     docker-compose.yml
   ```

2. **Check Known Issues:**
   - GitHub issues: https://github.com/anthropics/claude-code/issues
   - Provider status pages
   - KITTY docs: `docs/multi-provider-*.md`

3. **Create Issue Report:**
   - Include symptoms
   - Include relevant log excerpts
   - Include steps to reproduce
   - Redact API keys!

---

## Prevention

**Best Practices to Avoid Issues:**

1. ✅ Test with `/providers` after enabling
2. ✅ Monitor costs daily for first week
3. ✅ Use inline syntax (`@openai:`) for testing
4. ✅ Keep API keys in password manager
5. ✅ Set budget limits before autonomous mode
6. ✅ Review reasoning.log weekly
7. ✅ Update any-llm SDK quarterly

---

## Maintenance Schedule

**Daily:**
- Check cost dashboard
- Review error logs

**Weekly:**
- Rotate API keys (if high usage)
- Clear old conversation histories
- Review provider usage patterns

**Monthly:**
- Update any-llm SDK
- Review and adjust budgets
- Test fallback mechanisms

**Quarterly:**
- Rotate all API keys
- Audit enabled providers
- Performance benchmark comparison

---

## Emergency Procedures

### "Costs Too High - Emergency Shutdown"

```bash
# IMMEDIATE: Disable all cloud providers
sed -i '' 's/ENABLE_.*_COLLECTIVE=true/ENABLE_.*_COLLECTIVE=false/g' .env

# Restart brain
docker compose restart brain

# Verify all disabled
kitty-cli shell
/providers
# All should show ✗ disabled
```

### "Provider Compromised - Key Rotation"

```bash
# 1. Revoke old key at provider dashboard
# 2. Generate new key
# 3. Update .env immediately
# 4. Restart brain service
# 5. Test with simple query
# 6. Monitor logs for 24h
```

---

**Remember:** When in doubt, fallback to local Q4 is always safe and free!
