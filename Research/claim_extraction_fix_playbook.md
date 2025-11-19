# Claim Extraction Fix Playbook

**Date Started**: 2025-11-18
**Issue**: Claim extraction code exists and looks correct, but never executes (0 claims extracted)
**Evidence**: Execution jumps from nodes.py:846 → 853, skipping lines 847-850

---

## Background

### What's Working ✅
- Web search and webpage fetching (7,000+ chars retrieved per session)
- LangGraph orchestration and state management
- Planning, synthesis, and finalization nodes
- Database persistence for sessions, findings, sources
- Evidence-first extraction code in extraction.py (well-written)
- Types defined (Claim, EvidenceSpan) with full implementation

### What's Broken ❌
- Claim extraction never executes despite being called
- Debug logs in nodes.py:847-850 never appear
- extraction.py logs never appear
- Pattern suggests code path isn't being taken

### Root Cause Hypothesis
**Uvicorn worker module caching** - Container runs with `--workers 2`; workers cache imported modules in memory and don't reload when source files change.

**Evidence:**
1. Container uses: `python -m uvicorn brain.app:app --host 0.0.0.0 --port 8000 --workers 2`
2. No bytecode files exist (verified)
3. Code changes verified in both host and container
4. Container restarts don't fix the issue
5. Execution pattern physically impossible unless running different code

---

## Fix Strategy

### Phase 1: Simple Fixes (30 minutes)
Try least invasive changes first, in order:

1. **Single Worker Mode** (most likely fix)
2. **Force Rebuild with --no-cache**
3. **Add --reload Flag** (development mode)
4. **Explicit Module Reload** (last resort)

### Phase 2: Targeted Refactor (if Phase 1 fails)
- Extract claim extraction to separate HTTP endpoint
- Call via HTTP instead of direct import
- Guarantees fresh execution

### Phase 3: Full Rewrite (only if all else fails)
- Not recommended - 95% of pipeline works fine
- Would take 2 weeks vs 2 hours for targeted fix

---

## Execution Log

### Step 1: Switch to Single Worker Mode

**Date**: 2025-11-18
**Time**: [CURRENT]
**Hypothesis**: Multiple uvicorn workers are caching modules; single worker will reload properly

**Files to Modify:**
1. `services/brain/Dockerfile` - Check CMD/ENTRYPOINT
2. OR `infra/compose/docker-compose.yml` - Add command override

**Procedure:**

#### 1a. Check where uvicorn command is defined

```bash
# Check Dockerfile
cat services/brain/Dockerfile | grep -A 5 CMD

# Check docker-compose.yml for command override
grep -A 10 "brain:" infra/compose/docker-compose.yml | grep command
```

**Result**: [TO BE FILLED]

#### 1b. Find and modify the uvicorn command

**Current**: `python -m uvicorn brain.app:app --host 0.0.0.0 --port 8000 --workers 2`
**Change to**: `python -m uvicorn brain.app:app --host 0.0.0.0 --port 8000 --workers 1`

OR for development, add reload:
`python -m uvicorn brain.app:app --host 0.0.0.0 --port 8000 --reload`

**File Modified**: [TO BE FILLED]
**Lines Changed**: [TO BE FILLED]

#### 1c. Restart the brain service

```bash
docker compose -f /Users/Shared/Coding/KITT/infra/compose/docker-compose.yml restart brain
```

**Wait time**: ~10 seconds for service to restart

#### 1d. Verify single worker is running

```bash
docker exec compose-brain-1 ps aux | grep uvicorn
```

**Expected**: Should see only 1 uvicorn worker process (plus master)
**Result**: [TO BE FILLED]

#### 1e. Test with a research query

```bash
kitty-cli research "Test: What are the health benefits of vitamin D?" --no-config 2>&1 | tee /tmp/fix_test_step1.log
```

**Wait for completion**: ~5-8 minutes

#### 1f. Check for claim extraction logs

```bash
# Get session ID from test output
SESSION_ID="[FROM_OUTPUT]"

# Check if DEBUG_CLAIM logs appear
docker exec compose-brain-1 grep "$SESSION_ID" .logs/reasoning.log | grep -E "(🔬|DEBUG_CLAIM|📄|Extracting claims)" | head -20

# Check if extraction.py logs appear
docker exec compose-brain-1 grep "$SESSION_ID" .logs/reasoning.log | grep "Extracted.*claims from content"
```

**Expected Success Indicators:**
- ✅ "DEBUG_CLAIM_1" appears in logs
- ✅ "DEBUG_CLAIM_1b" appears in logs
- ✅ "Extracting claims from content" appears
- ✅ "Extracted N claims from content" appears (N > 0)

**Result**: [TO BE FILLED]

**Claims Extracted**: [TO BE FILLED]

**Decision:**
- [ ] ✅ FIXED - Move to cleanup and documentation
- [ ] ❌ STILL BROKEN - Proceed to Step 2

---

### Step 2: Force Rebuild with --no-cache

**Date**: [TO BE FILLED]
**Time**: [TO BE FILLED]
**Hypothesis**: Docker layer cache may contain old module state

**Procedure:**

#### 2a. Stop the brain service

```bash
docker compose -f /Users/Shared/Coding/KITT/infra/compose/docker-compose.yml stop brain
```

#### 2b. Build with no cache

```bash
docker compose -f /Users/Shared/Coding/KITT/infra/compose/docker-compose.yml build --no-cache brain 2>&1 | tee /tmp/rebuild_no_cache.log
```

**Wait time**: ~5-10 minutes (full rebuild)

#### 2c. Start the service

```bash
docker compose -f /Users/Shared/Coding/KITT/infra/compose/docker-compose.yml up -d brain
```

#### 2d. Test with research query

```bash
kitty-cli research "Test 2: Benefits of omega-3 fatty acids" --no-config 2>&1 | tee /tmp/fix_test_step2.log
```

#### 2e. Check logs (same as Step 1f)

**Result**: [TO BE FILLED]

**Decision:**
- [ ] ✅ FIXED - Move to cleanup
- [ ] ❌ STILL BROKEN - Proceed to Step 3

---

### Step 3: Add --reload Flag (Development Mode)

**Date**: [TO BE FILLED]
**Time**: [TO BE FILLED]
**Hypothesis**: --reload forces uvicorn to watch for file changes

**Procedure:**

#### 3a. Modify uvicorn command

**Change**: Add `--reload` flag
**File**: [Dockerfile or docker-compose.yml]

**Note**: `--reload` is incompatible with `--workers 2`, so use:
```
python -m uvicorn brain.app:app --host 0.0.0.0 --port 8000 --reload
```

#### 3b. Restart and test

```bash
docker compose -f /Users/Shared/Coding/KITT/infra/compose/docker-compose.yml restart brain

kitty-cli research "Test 3: Benefits of probiotics" --no-config 2>&1 | tee /tmp/fix_test_step3.log
```

#### 3c. Check logs

**Result**: [TO BE FILLED]

**Decision:**
- [ ] ✅ FIXED - Document solution
- [ ] ❌ STILL BROKEN - Proceed to Step 4

---

### Step 4: Explicit Module Reload in nodes.py

**Date**: [TO BE FILLED]
**Time**: [TO BE FILLED]
**Hypothesis**: Force Python to reload the extraction module before calling

**Procedure:**

#### 4a. Add module reload to nodes.py

**File**: `services/brain/src/brain/research/graph/nodes.py`
**Location**: Just before line 862 (where extract_claims_from_content is called)

```python
# Add at top of file
import importlib
import sys

# Add before calling extract_claims_from_content (around line 860)
# Force reload of extraction module to pick up latest code
if 'brain.research.extraction' in sys.modules:
    importlib.reload(sys.modules['brain.research.extraction'])
    from brain.research.extraction import extract_claims_from_content
```

#### 4b. Restart and test

```bash
docker compose restart brain
kitty-cli research "Test 4: Benefits of meditation" --no-config 2>&1 | tee /tmp/fix_test_step4.log
```

#### 4c. Check logs

**Result**: [TO BE FILLED]

**Decision:**
- [ ] ✅ FIXED - Document solution and remove debug code
- [ ] ❌ STILL BROKEN - Escalate to Phase 2 (Targeted Refactor)

---

## Phase 2: Targeted Refactor (If Needed)

### Option A: Extraction Service Endpoint

Create a new FastAPI endpoint specifically for claim extraction:

**New file**: `services/brain/src/brain/routes/extraction_endpoint.py`

```python
@router.post("/extract-claims")
async def extract_claims_endpoint(request: ExtractionRequest):
    """Dedicated endpoint for claim extraction."""
    return await extract_claims_from_content(...)
```

**Modify nodes.py**: Call via HTTP instead of import

```python
response = await httpx.post(
    "http://localhost:8000/api/extract-claims",
    json={...}
)
```

This guarantees fresh execution every time.

### Option B: Move Extraction to Separate Container

Create `services/extraction/` with its own service.

---

## Success Criteria

- [ ] Research query extracts > 0 claims
- [ ] All DEBUG_CLAIM_1 through DEBUG_CLAIM_9 logs appear
- [ ] extraction.py logs appear ("Extracting claims...", "Extracted N claims")
- [ ] Claims are persisted to database
- [ ] Subsequent queries continue to extract claims (not a one-time fix)

---

## Rollback Plan

If changes break the system:

1. **Revert docker-compose.yml** or **Dockerfile** to original
2. **Restart brain service**
3. **Document failure mode** in this playbook

Original configuration:
```yaml
command: python -m uvicorn brain.app:app --host 0.0.0.0 --port 8000 --workers 2
```

---

## Post-Fix Tasks

Once fixed:

1. [ ] Remove all DEBUG_CLAIM_* logs from nodes.py
2. [ ] Remove print() statement from nodes.py:847
3. [ ] Update research_pipeline_architecture.md with fix details
4. [ ] Update KITT_Research_System_Fixes.md to remove blocker
5. [ ] Create GitHub issue documenting the problem and solution
6. [ ] Add unit test that verifies claim extraction executes
7. [ ] Consider adding health check that validates extraction is callable

---

## References

- **Architecture Doc**: `/Users/Shared/Coding/KITT/Research/research_pipeline_architecture.md`
- **Session 2 Investigation**: `/Users/Shared/Coding/KITT/Research/claim_extraction_investigation_session2.md`
- **Fixes Doc**: `/Users/Shared/Coding/KITT/Research/KITT_Research_System_Fixes.md`
- **Code**: `services/brain/src/brain/research/graph/nodes.py:840-895`
- **Extraction**: `services/brain/src/brain/research/extraction.py`

---

## Notes

- Keep this document updated with exact results as we execute each step
- Include timestamps, session IDs, and log excerpts
- Document any unexpected behavior
- If a step works, mark it clearly and proceed to cleanup
