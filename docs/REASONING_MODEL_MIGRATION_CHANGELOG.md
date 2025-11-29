# Reasoning Model Migration Changelog

**Migration: Llama 3.3 70B F16 (llama.cpp) -> GPTOSS 120B (Ollama)**

**Date:** 2025-11-29
**Branch:** `claude/migrate-reasoning-model-01NUZboyaoGNmXKMs2jmsoXQ`

---

## Summary

This document tracks all changes made during the migration from Llama 3.3 70B F16 (running on llama.cpp port 8082) to GPTOSS 120B (running on Ollama port 11434) as the primary reasoning model.

---

## Changes Made

### 1. `.env.example`

**File:** `/home/user/KITT/.env.example`

| Section | Change |
|---------|--------|
| Ollama config | Added header comments clarifying GPTOSS 120B as PRIMARY reasoning engine |
| F16 config | Added DEPRECATED notice explaining F16 is fallback only |

**Before:**
```
# Ollama (GPT-OSS)
OLLAMA_HOST=http://localhost:11434
...

# F16 (deep reasoner; used when LOCAL_REASONER_PROVIDER=llamacpp)
LLAMACPP_F16_HOST=http://localhost:8082
...
```

**After:**
```
# ==============================================================================
# Ollama Reasoning Model (GPTOSS 120B) - PRIMARY REASONING ENGINE
# ==============================================================================
# GPTOSS 120B is the primary reasoning model with thinking mode support.
# It replaces the previous Llama 3.3 70B F16 (llama.cpp) reasoner.
OLLAMA_HOST=http://localhost:11434
...

# ==============================================================================
# DEPRECATED: F16 llama.cpp server (Llama 3.3 70B)
# The primary reasoning model is now GPTOSS 120B via Ollama (see OLLAMA_* above).
# F16 llama.cpp is only used when LOCAL_REASONER_PROVIDER=llamacpp as a fallback.
# These settings will be removed in a future release.
# ==============================================================================
LLAMACPP_F16_HOST=http://localhost:8082
...
```

---

### 2. `config/tool_registry.yaml`

**File:** `/home/user/KITT/config/tool_registry.yaml`

| Change | Description |
|--------|-------------|
| Added `reason_deep` tool | New primary reasoning tool referencing GPTOSS 120B |
| Deprecated `reason_with_f16` | Kept as backward-compatible alias with deprecation notice |
| Updated categories | Added `reason_deep` to reasoning category |

**New tool definition:**
```yaml
reason_deep:
  server: reasoning
  description: "Delegate complex reasoning to GPTOSS 120B deep reasoning model (Ollama)"
  hazard_class: none
  requires_confirmation: false
  budget_tier: free
  enabled: true
  note: "Used by Q4 agent to request deep analysis from the reasoning engine. Supports thinking mode for detailed reasoning traces."

# DEPRECATED: Legacy alias for reason_deep (will be removed in future release)
reason_with_f16:
  server: reasoning
  description: "[DEPRECATED] Use reason_deep instead. Alias for backward compatibility."
  ...
```

---

### 3. `services/brain/src/brain/routing/config.py`

**File:** `/home/user/KITT/services/brain/src/brain/routing/config.py`

| Line | Change |
|------|--------|
| 22 | Removed Llama 3.3 reference from temperature comment |
| 51 | Changed default `local_reasoner_provider` from `"llamacpp"` to `"ollama"` |

**Before:**
```python
temperature: float = Field(default=0.1, ge=0.0)  # Low temperature (0.0-0.2) required for reliable Llama 3.3 tool calling
...
local_reasoner_provider: str = Field(default="llamacpp")  # ollama | llamacpp
```

**After:**
```python
temperature: float = Field(default=0.1, ge=0.0)  # Low temperature (0.0-0.2) for reliable tool calling
...
local_reasoner_provider: str = Field(default="ollama")  # ollama (GPTOSS 120B) | llamacpp (deprecated Llama 3.3 fallback)
```

---

### 4. `services/brain/src/brain/tools/model_config.py`

**File:** `/home/user/KITT/services/brain/src/brain/tools/model_config.py`

| Change | Description |
|--------|-------------|
| Added `GPTOSS_JSON` format | New tool call format for GPTOSS models |
| Added detection pattern | Detect gpt-oss/gptoss and kitty-f16 in model names |
| Added ModelConfig for GPTOSS | Config with `requires_jinja=False`, `supports_parallel_calls=True` |

---

### 5. `ops/scripts/start-all.sh`

**File:** `/home/user/KITT/ops/scripts/start-all.sh`

| Line | Change |
|------|--------|
| 155 | Changed default `LOCAL_REASONER_PROVIDER` from `"llamacpp"` to `"ollama"` |
| 158 | Updated log message to say "GPTOSS 120B - primary reasoning model" |
| 197 | Updated health check label to "GPTOSS 120B reasoner" |
| 200-203 | Added deprecation comment for F16 health check |

---

### 6. `ops/scripts/llama/start.sh`

**File:** `/home/user/KITT/ops/scripts/llama/start.sh`

| Change | Description |
|--------|-------------|
| Lines 51-55 | Added DEPRECATED header block for F16 Server section |
| Line 125 | Changed default `LOCAL_REASONER_PROVIDER` from `"llamacpp"` to `"ollama"` |
| Line 128 | Updated skip message to reference GPTOSS 120B |
| Line 130 | Added notice when using deprecated F16 server |

---

### 7. `README.md`

**File:** `/home/user/KITT/README.md`

| Line | Change |
|------|--------|
| 40 | Updated "Fallback Reasoner" row to show "*(DEPRECATED)* Legacy fallback only" |
| 422-424 | Updated architecture diagram: "F16 DEPR" and "(Fallback)" labels |
| 503-506 | Commented out F16 config example with deprecation note |

---

## Rollback Instructions

If issues occur during testing, revert by:

1. **Immediate fix:** Set `LOCAL_REASONER_PROVIDER=llamacpp` in environment
2. **Full rollback:** Revert this branch's commits

```bash
# Quick environment override
export LOCAL_REASONER_PROVIDER=llamacpp

# Or revert commits
git revert HEAD~N  # where N is number of commits to revert
```

---

## Testing Checklist

- [ ] Verify `LOCAL_REASONER_PROVIDER=ollama` connects to Ollama successfully
- [ ] Verify `reason_deep` tool is callable
- [ ] Verify `reason_with_f16` (deprecated) still works for backward compatibility
- [ ] Verify fallback to llama.cpp when `LOCAL_REASONER_PROVIDER=llamacpp`
- [ ] Verify thinking mode traces are captured
- [ ] Run integration tests

### 8. `KITTY_OperationsManual.md`

**File:** `/home/user/KITT/KITTY_OperationsManual.md`

| Section | Change |
|---------|--------|
| Startup summary | Added Ollama to startup description |
| Log viewing | Added ollama.log, marked F16 as deprecated fallback |
| Architecture diagram | Added Ollama section, marked F16 as deprecated |
| Dual-model section | Renamed to "Multi-Model", added GPTOSS 120B, deprecated F16 |
| Critical variables | Added `LOCAL_REASONER_PROVIDER`, `OLLAMA_*` vars |

---

### 9. Archived Documentation

| File | New Location |
|------|--------------|
| `Research/Llama33ToolCall.md` | `Research/archive/Llama33ToolCall.md` |
| `Research/Llama33CallingGuildelines.md` | `Research/archive/Llama33CallingGuildelines.md` |
| `docs/F16_PARALLELISM_TUNING_GUIDE.md` | `docs/archive/F16_PARALLELISM_TUNING_GUIDE.md` |

Added `README.md` files in both archive directories explaining the migration.

---

### 10. Test Files

**File:** `/home/user/KITT/tests/langgraph_system_test.sh`

| Line | Change |
|------|--------|
| 3 | Updated header to reference Q4/GPTOSS instead of Q4/F16 |
| 4 | Added note about GPTOSS 120B being primary, F16 deprecated |
| 259 | Updated F16 check to say "F16 (Deprecated Fallback)" |

---

## Files Modified

| File | Type |
|------|------|
| `.env.example` | Configuration |
| `config/tool_registry.yaml` | Tool definitions |
| `services/brain/src/brain/routing/config.py` | Routing logic |
| `services/brain/src/brain/tools/model_config.py` | Model detection |
| `ops/scripts/start-all.sh` | Startup script |
| `ops/scripts/llama/start.sh` | Llama.cpp startup |
| `README.md` | Documentation |
| `KITTY_OperationsManual.md` | Documentation |
| `tests/langgraph_system_test.sh` | Test script |
| `Research/Llama33*.md` | Archived |
| `docs/F16_PARALLELISM_TUNING_GUIDE.md` | Archived |
| `docs/REASONING_MODEL_MIGRATION_CHANGELOG.md` | Created |
| `Research/archive/README.md` | Created |
| `docs/archive/README.md` | Created |
