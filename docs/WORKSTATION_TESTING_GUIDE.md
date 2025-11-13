# Workstation Testing Guide - Perplexity Enhancements

**Date**: 2025-11-13
**Commits to Test**: 4 commits (161b113 → aff2084)
**Purpose**: Validate Perplexity API enhancements before Phase 3

---

## What's Being Tested

### Commits Since Last Workstation Test (65507e9)

1. **161b113** - `fix(autonomous): Change project_generation_cycle to daily cron schedule`
   - Changed from 4-hour interval to daily at 4:30am PST
   - Removes redundant time window check

2. **ac46055** - `docs: Add comprehensive Perplexity API integration analysis`
   - 489-line analysis document
   - No code changes

3. **cf01062** - `feat(perplexity): Implement HIGH priority enhancements`
   - Enhanced citations extraction (multiple fallback locations)
   - Token-based cost calculation (accurate per-model pricing)
   - Model configuration in .env.example and Settings class

4. **aff2084** - `feat(perplexity): Implement MEDIUM/LOW priority enhancements`
   - Search parameter support (domain filter, recency, etc.)
   - Dynamic model selection based on budget
   - Streaming support (future UI integration)
   - Async completion pattern documentation

---

## Pre-Testing Checklist

### 1. Pull Latest Code

```bash
cd ~/KITT
git fetch origin
git checkout claude/kitty-001-access-011CUybyHrDBaPsk6JaCEBRL
git pull origin claude/kitty-001-access-011CUybyHrDBaPsk6JaCEBRL
```

### 2. Verify Environment

```bash
# Check Perplexity API key is set
grep PERPLEXITY_API_KEY .env

# If not set, add it:
echo "PERPLEXITY_API_KEY=your_key_here" >> .env
```

### 3. Install Dependencies (if needed)

```bash
# Activate virtual environment
source venv/bin/activate  # or your venv path

# Install/update dependencies
pip install -e services/brain/
pip install -e services/common/
```

---

## Test Execution

### Test 1: Unit Tests (Regression Check)

**Purpose**: Ensure no existing tests broke

```bash
# Run all autonomous unit tests
pytest tests/unit/test_autonomous_*.py -v

# Expected: 24/26 passing (same as before)
# The 2 failing tests are pre-existing mock/API signature issues
```

**Success Criteria**:
- ✅ Still 24/26 tests passing (no regression)
- ✅ Same 2 tests failing as before
- ❌ If new tests fail → investigate

### Test 2: Integration Tests (Full Workflow)

**Purpose**: Verify end-to-end autonomous workflow still works

```bash
# Run integration tests
pytest tests/integration/test_autonomous_workflow.py -v

# Expected: All 3 integration tests passing
```

**Success Criteria**:
- ✅ test_full_autonomous_workflow - Passes
- ✅ test_dependency_tracking - Passes
- ✅ test_failure_handling - Passes

### Test 3: Perplexity API Validation (NEW)

**Purpose**: Validate real Perplexity API integration with enhancements

```bash
# Run manual validation script
python tests/manual/test_perplexity_enhancements.py
```

**What This Tests**:
1. **Citations Extraction** - Verifies citations appear in response
2. **Token Usage Tracking** - Confirms usage data extraction
3. **Search Parameters** - Tests domain filter, recency, related questions
4. **Model Override** - Validates sonar vs sonar-pro switching

**Expected Output**:
```
======================================================================
PERPLEXITY API ENHANCEMENTS - VALIDATION TEST SUITE
======================================================================

TEST 1: Citations Extraction
✓ Top-level citations: 10-15 found
✅ PASS: Citations extraction

TEST 2: Token Usage Tracking & Cost Calculation
✓ Usage data found: True
  Total tokens: 400-600
  Cost calculation validation:
    sonar: $0.000080 ✅
    sonar-pro: $0.003600 ✅
✅ PASS: Token usage tracking

TEST 3: Search Parameters
✓ Related questions returned: 3-5
✅ PASS: Search parameters

TEST 4: Model Override & Dynamic Selection
✓ Sonar response: 500-800 chars
✓ Sonar-pro response: 800-1500 chars
✅ PASS: Model override

======================================================================
TEST SUMMARY
======================================================================
✅ PASS: test_1_citations
✅ PASS: test_2_usage
✅ PASS: test_3_search
✅ PASS: test_4_model

Total: 4/4 tests passed (100%)

🎉 ALL TESTS PASSED - Perplexity enhancements validated!
✅ Production ready for autonomous research workflows
```

**Success Criteria**:
- ✅ All 4 Perplexity tests pass
- ✅ Citations extraction finds 10+ citations
- ✅ Usage data includes total_tokens > 0
- ✅ Cost calculation matches expected rates
- ✅ Related questions returned (3-5 questions)
- ✅ Model override works (sonar vs sonar-pro)

---

## Critical Validations

### 1. Citations Format Verification

**What to check**:
- Citations appear in `response.citations` (top-level)
- OR in `response.choices[0].metadata.citations`
- Format is array of strings (URLs) or objects

**How to verify**:
```bash
# Check test output for:
✓ Top-level citations: X found
✓ Choice metadata citations: Y found
```

**If fails**:
- Note actual response structure
- Check if citations are in different location
- May need to update extraction logic

### 2. Token Usage & Cost Accuracy

**What to check**:
- `usage.total_tokens` exists
- `usage.prompt_tokens` and `usage.completion_tokens` present
- Cost calculation matches: (tokens / 1M) × rate

**Pricing validation**:
- sonar: $0.20 per 1M tokens
- sonar-pro: $9.00 per 1M tokens (avg of $3 input + $15 output)

**How to verify**:
```bash
# Check test output for:
  Total tokens: 465
  sonar: $0.000093 (rate: $0.20/1M) ✅
  sonar-pro: $0.004185 (rate: $9.00/1M) ✅
```

### 3. Search Parameters

**What to check**:
- Domain filter applied (indirect - check citations)
- Recency filter applied (indirect - check result freshness)
- Related questions returned (direct validation)

**How to verify**:
```bash
# Check test output for:
✓ Related questions returned: 5
  Sample questions:
    1. What are the best sustainable materials?
    2. How does PLA compare to PETG?
```

### 4. Model Selection Logic

**What to check**:
- Budget > $2.00 → uses sonar-pro
- Budget ≤ $2.00 → uses sonar
- Model override in payload works

**How to verify**:
```python
# Check project_generator.py logic (lines 309-313)
budget = float(goal.estimated_budget)
perplexity_model = "sonar-pro" if budget > 2.0 else "sonar"
```

---

## Troubleshooting

### Issue: Test 1 (Citations) Fails

**Symptoms**: No citations found in response

**Possible Causes**:
1. Perplexity changed response format
2. Citations in different location than expected

**Debug Steps**:
```python
# Add debug output to test script (line 77):
print(f"DEBUG: Full raw response keys: {raw.keys()}")
print(f"DEBUG: Choices structure: {raw.get('choices', [{}])[0].keys()}")
```

**Resolution**:
- Update citation extraction logic in task_executor.py
- Add new fallback location if needed

### Issue: Test 2 (Usage) Fails

**Symptoms**: No usage data in response

**Possible Causes**:
1. API key doesn't have access to usage data
2. Free tier limitations

**Debug Steps**:
```python
# Check raw response:
print(f"DEBUG: Raw response: {raw}")
```

**Resolution**:
- Verify API key has proper tier access
- Check Perplexity account status

### Issue: Test 3 (Search Params) Partial Pass

**Symptoms**: Parameters accepted but no related questions

**Possible Causes**:
1. Query doesn't trigger related questions
2. Feature requires specific model (sonar-pro)

**Resolution**:
- Try with sonar-pro model explicitly
- Check if feature requires higher tier

### Issue: API Rate Limit

**Symptoms**: HTTPError 429

**Resolution**:
```bash
# Wait 60 seconds between test runs
sleep 60
python tests/manual/test_perplexity_enhancements.py
```

---

## Success Checklist

Before approving for production:

- [ ] Unit tests: 24/26 passing (no regression)
- [ ] Integration tests: 3/3 passing
- [ ] Perplexity Test 1 (Citations): ✅ PASS
- [ ] Perplexity Test 2 (Usage/Cost): ✅ PASS
- [ ] Perplexity Test 3 (Search Params): ✅ PASS or ⚠️ PARTIAL
- [ ] Perplexity Test 4 (Model Override): ✅ PASS
- [ ] Citations format documented
- [ ] Cost calculation validated
- [ ] No critical errors in logs

---

## Reporting Results

### If All Tests Pass

Create a summary comment:
```
✅ Testing Complete - All Systems GO

Test Results Summary:
- Commits Tested: 4 (161b113 → aff2084)
- Unit Tests: 24/26 Passing (no regression)
- Integration Tests: 3/3 Passing
- Perplexity Validation: 4/4 Passing

Key Validations:
✅ Citations: 13 found at top level
✅ Usage: 465 tokens tracked
✅ Cost: 100% accurate across all models
✅ Search params: Domain filter + related questions working
✅ Model override: sonar vs sonar-pro validated

Status: PRODUCTION READY
```

### If Tests Fail

Create a detailed report:
```
⚠️ Testing Issues Found

Failed Tests:
- [Test Name]: [Reason]

Details:
[Paste error messages, unexpected output]

Impact:
[HIGH/MEDIUM/LOW]

Recommended Action:
[Fix before deploy / Acceptable for now / Investigate further]
```

---

## Next Steps After Testing

1. **If all tests pass**: Ready for Phase 3 (Outcome Tracking)
2. **If minor issues**: Document and proceed with known limitations
3. **If critical failures**: Fix before Phase 3

**Phase 3 Preview**: Outcome tracking, effectiveness metrics, feedback loops

---

## Quick Reference Commands

```bash
# Full test suite
pytest tests/unit/test_autonomous_*.py -v
pytest tests/integration/test_autonomous_workflow.py -v
python tests/manual/test_perplexity_enhancements.py

# Check logs
tail -f .logs/reasoning.jsonl | jq 'select(.event | contains("perplexity"))'

# Verify scheduling fix
grep "add_cron_job" services/brain/src/brain/app.py
```
