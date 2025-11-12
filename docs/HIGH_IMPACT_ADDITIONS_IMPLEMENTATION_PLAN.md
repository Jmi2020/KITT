# KITTY High-Impact Additions - Implementation Plan

## Executive Summary

This plan implements 4 high-impact additions to enhance KITTY's multi-agent collective and LangGraph workflows while maintaining offline-first architecture:

1. **Dedicated Coder Model** - Qwen2.5-Coder-32B-Instruct for specialized code generation
2. **Enhanced Memory Retrieval** - BAAI/bge embeddings + reranker for better context quality
3. **Diversity Seat** - Second model family (Mistral-7B) to reduce correlated failures
4. **Judge Concurrency** (Optional) - Second F16 server for parallel judging

**Implementation Priority**: P0 (Coder) → P1 (Memory) → P2 (Diversity) → P3 (Judge Concurrency)

---

## Current State Analysis

### ✅ Already Implemented

1. **Environment Configuration**
   - Coder model paths configured (`.env.example` lines 81-82)
   - Dual-model architecture (Q4 @ 8083, F16 @ 8082)
   - Collective proposer blinding with tag-aware filtering
   - Memory MCP with Qdrant and sentence-transformers

2. **Memory Service**
   - Tag-aware filtering (`include_tags`/`exclude_tags`) fully implemented
   - Qdrant vector storage operational
   - FastAPI endpoints: `/memory/add`, `/memory/search`
   - 3x fetch multiplier for tag filtering

3. **Collective Meta-Agent**
   - Async and sync graphs (33% performance improvement)
   - Diversity metrics (Jaccard similarity)
   - Context policy with proposer blinding
   - Prometheus metrics integration

### ❌ Needs Implementation

1. **CODER Model Routing**
   - `llm_client.py` only supports Q4, F16
   - No `which="CODER"` option available
   - Coder-agent service not yet integrated with collective

2. **Memory Embeddings**
   - Currently uses `sentence-transformers/all-MiniLM-L6-v2` (384-dim)
   - Should upgrade to `BAAI/bge-small-en-v1.5` (384-dim, better quality)
   - No reranker implemented (should add `BAAI/bge-reranker-base`)

3. **Diversity Seat**
   - Only Qwen models used (single family)
   - No Q4B server or routing
   - Council uses same model for all specialists

4. **Judge Concurrency**
   - Single F16 server (port 8082)
   - No load balancing for concurrent judging

---

## Implementation Phases

### Phase 1: Dedicated Coder Model (P0 - Critical) 🔴

**Goal**: Enable specialized code generation in collective and coder-agent workflows

**Estimated Time**: 2-3 hours
**Complexity**: Low
**Dependencies**: None

#### Tasks

1. **Update llm_client.py** (services/brain/src/brain/llm_client.py)
   - Add `"CODER"` to model_map in `chat_async()` (line 79-82)
   - Add `"CODER"` to model_map in `chat()` (line 131-135)
   - Map to `"kitty-coder"` alias

2. **Update collective graphs** (if needed for code-related tasks)
   - Modify `graph.py` and `graph_async.py` to support `which="CODER"`
   - Add optional parameter for specialist role types

3. **Environment verification**
   - Confirm `LLAMACPP_CODER_BASE` is set (or defaults to F16)
   - Verify coder model is downloaded and accessible

4. **Testing**
   - Unit test: `chat_async()` with `which="CODER"`
   - Integration test: Call collective with code generation task
   - Smoke test: `/collective council k=2 Write a prime sieve function`

**Files to Modify**:
- `services/brain/src/brain/llm_client.py` (~10 lines)
- `tests/unit/test_llm_client.py` (new file, ~50 lines)

**Definition of Done**:
- [ ] `which="CODER"` works in `chat_async()` and `chat()`
- [ ] Coder model alias `kitty-coder` resolves correctly
- [ ] Unit tests pass
- [ ] Integration test with collective passes
- [ ] Documentation updated

---

### Phase 2: Enhanced Memory Retrieval (P1 - High Priority) 🟠

**Goal**: Improve context quality for planning and judging with better embeddings and reranking

**Estimated Time**: 3-4 hours
**Complexity**: Medium
**Dependencies**: None

#### Tasks

1. **Update mem0-mcp dependencies** (services/mem0-mcp/requirements.txt)
   - Add specific versions:
     ```
     qdrant-client>=1.8.0
     sentence-transformers>=3.0.0
     ```

2. **Update embedding model** (services/mem0-mcp/src/mem0_mcp/app.py)
   - Change default from `all-MiniLM-L6-v2` to `BAAI/bge-small-en-v1.5`
   - Update EMBEDDING_DIM to match (should still be 384)
   - Test backwards compatibility

3. **Add reranker support** (services/mem0-mcp/src/mem0_mcp/app.py)
   - Import `CrossEncoder` from sentence-transformers
   - Load reranker model in lifespan (optional, with try/except)
   - Modify `/memory/search` to rerank results when reranker available
   - Fetch 3x results, rerank, return top k

4. **Update .env configuration**
   - Set `EMBEDDING_MODEL=BAAI/bge-small-en-v1.5`
   - Set `RERANKER_MODEL=BAAI/bge-reranker-base`
   - Update .env.example

5. **Testing**
   - Unit test: Embedding generation
   - Unit test: Reranking logic (mock CrossEncoder)
   - Integration test: Search with reranker enabled
   - Integration test: Search with reranker disabled (fallback)
   - Smoke test: Compare search quality before/after

**Files to Modify**:
- `services/mem0-mcp/requirements.txt` (~2 lines)
- `services/mem0-mcp/src/mem0_mcp/app.py` (~60 lines)
- `.env.example` (~2 lines)
- `tests/integration/test_memory_reranker.py` (new file, ~120 lines)

**Definition of Done**:
- [ ] BGE embeddings loaded successfully
- [ ] Reranker loads successfully (or falls back gracefully)
- [ ] Search quality improved (measured by score distribution)
- [ ] Tag filtering still works correctly
- [ ] Backwards compatible with existing memories
- [ ] Documentation updated

---

### Phase 3: Diversity Seat for Councils (P2 - Nice to Have) 🟡

**Goal**: Reduce correlated failures by adding a second model family for one council seat

**Estimated Time**: 4-5 hours
**Complexity**: Medium-High
**Dependencies**: Phase 1 complete (CODER routing pattern)

#### Tasks

1. **Download diversity model**
   ```bash
   huggingface-cli download TheBloke/Mistral-7B-Instruct-v0.2-GGUF \
     --local-dir /Users/Shared/Coding/models/Mistral-7B-Instruct-GGUF \
     --include "*q4_k_m.gguf"
   ```

2. **Configure startup script** (ops/scripts/start-kitty.sh)
   - Add optional third llama.cpp server on port 8084
   - Conditional start if `LLAMACPP_Q4B_MODEL` is set
   - Log output to `.logs/llamacpp-q4b.log`

3. **Update llm_client.py**
   - Add `"Q4B"` to model_map
   - Map to `kitty-q4b` alias or fallback to Q4
   - Add environment variable: `LLAMACPP_Q4B_BASE`

4. **Update collective graphs** (graph.py, graph_async.py)
   - Modify `n_propose_council` to use Q4B for specialist_1
   - Add temperature variation (0.7-0.9) across specialists
   - Add max_tokens variation (400-600)

5. **Update .env configuration**
   - Add `LLAMACPP_Q4B_BASE=http://host.docker.internal:8084`
   - Add `LLAMACPP_Q4B_MODEL=Mistral-7B-Instruct-GGUF/mistral-7b-instruct-v0.2.Q4_K_M.gguf`
   - Add `LLAMACPP_Q4B_ALIAS=kitty-q4b`
   - Add `LLAMACPP_Q4B_PORT=8084`

6. **Testing**
   - Unit test: Q4B routing
   - Integration test: Council with mixed models
   - Diversity metrics: Compare k=3 (single family) vs k=3 (mixed family)
   - Measure avg_diversity improvement
   - Smoke test: Full council execution

**Files to Modify**:
- `services/brain/src/brain/llm_client.py` (~5 lines)
- `services/brain/src/brain/agents/collective/graph.py` (~15 lines)
- `services/brain/src/brain/agents/collective/graph_async.py` (~15 lines)
- `ops/scripts/start-kitty.sh` (~30 lines)
- `.env.example` (~8 lines)
- `tests/integration/test_diversity_seat.py` (new file, ~150 lines)

**Definition of Done**:
- [ ] Q4B server starts automatically if configured
- [ ] `which="Q4B"` routes correctly
- [ ] Council uses Q4B for at least one specialist
- [ ] Diversity metrics show improvement (>0.05 avg_diversity increase)
- [ ] Graceful fallback if Q4B not available
- [ ] Documentation updated

---

### Phase 4: Judge Concurrency (P3 - Optional) 🟢

**Goal**: Reduce latency for concurrent judging operations

**Estimated Time**: 3-4 hours
**Complexity**: Medium
**Dependencies**: RAM availability (70B F16 requires ~160GB)

**Note**: Only implement if M3 Ultra has sufficient RAM headroom. Monitor RAM usage during council operations first.

#### Tasks

1. **RAM assessment**
   - Measure current RAM usage during council operations
   - Calculate available headroom (192GB - current usage)
   - Determine if 160GB is available for second F16

2. **Configure startup script** (if RAM available)
   - Add optional fourth llama.cpp server on port 8085
   - Conditional start if `LLAMACPP_F16_B_MODEL` is set
   - Log output to `.logs/llamacpp-f16b.log`

3. **Update llm_client.py**
   - Add round-robin load balancer for F16 requests
   - Use `itertools.cycle` to alternate between F16 and F16_B
   - Preserve single-F16 behavior if F16_B not configured

4. **Update .env configuration**
   - Add `LLAMACPP_F16_B_BASE=http://host.docker.internal:8085`
   - Add `LLAMACPP_F16_B_MODEL` (same as F16)
   - Add `LLAMACPP_F16_B_PORT=8085`

5. **Testing**
   - Unit test: Round-robin logic
   - Integration test: Concurrent F16 calls
   - Performance test: Parallel judging latency
   - Smoke test: Council with concurrent judges

**Files to Modify**:
- `services/brain/src/brain/llm_client.py` (~25 lines)
- `ops/scripts/start-kitty.sh` (~30 lines)
- `.env.example` (~5 lines)
- `tests/integration/test_judge_concurrency.py` (new file, ~100 lines)

**Definition of Done**:
- [ ] RAM headroom sufficient (>170GB free)
- [ ] F16_B server starts automatically if configured
- [ ] Round-robin load balancing works
- [ ] Concurrent judging shows latency improvement (>20%)
- [ ] Single-F16 fallback works if F16_B unavailable
- [ ] Documentation updated

**Alternative (if RAM insufficient)**:
- Increase F16 `LLAMACPP_PARALLEL` from 4 to 6-8
- Increase `LLAMACPP_BATCH_SIZE` to 8192
- Tune `LLAMACPP_N_PREDICT` for faster completion

---

## Implementation Checklist

### Pre-Implementation

- [ ] Review current state analysis
- [ ] Backup .env and services before changes
- [ ] Create feature branch: `feature/high-impact-additions`
- [ ] Set up test environment

### Phase 1: Coder Model

- [ ] Task 1.1: Update llm_client.py with CODER support
- [ ] Task 1.2: Update collective graphs (if needed)
- [ ] Task 1.3: Verify environment configuration
- [ ] Task 1.4: Write and run tests
- [ ] Task 1.5: Update documentation
- [ ] Commit: `feat(llm): Add CODER model support to llm_client`
- [ ] Push and test on workstation

### Phase 2: Memory Enhancement

- [ ] Task 2.1: Update mem0-mcp dependencies
- [ ] Task 2.2: Update embedding model to BGE
- [ ] Task 2.3: Implement reranker support
- [ ] Task 2.4: Update .env configuration
- [ ] Task 2.5: Write and run tests
- [ ] Task 2.6: Validate backwards compatibility
- [ ] Commit: `feat(memory): Add BGE embeddings and reranker support`
- [ ] Push and test on workstation

### Phase 3: Diversity Seat

- [ ] Task 3.1: Download Mistral-7B model
- [ ] Task 3.2: Update start-kitty.sh for Q4B server
- [ ] Task 3.3: Add Q4B support to llm_client.py
- [ ] Task 3.4: Update collective graphs for mixed models
- [ ] Task 3.5: Update .env configuration
- [ ] Task 3.6: Write and run tests
- [ ] Task 3.7: Measure diversity improvement
- [ ] Commit: `feat(collective): Add diversity seat with Mistral-7B`
- [ ] Push and test on workstation

### Phase 4: Judge Concurrency (Optional)

- [ ] Task 4.1: Assess RAM availability
- [ ] **Decision Point**: Proceed if >170GB free, else skip
- [ ] Task 4.2: Update start-kitty.sh for F16_B server
- [ ] Task 4.3: Implement round-robin in llm_client.py
- [ ] Task 4.4: Update .env configuration
- [ ] Task 4.5: Write and run tests
- [ ] Task 4.6: Measure latency improvement
- [ ] Commit: `feat(llm): Add F16 judge concurrency with round-robin`
- [ ] Push and test on workstation

### Post-Implementation

- [ ] Run full test suite
- [ ] Update all documentation
- [ ] Create integration guide
- [ ] Add to CLAUDE.md
- [ ] Merge feature branch to main
- [ ] Create memory for this implementation

---

## Testing Strategy

### Unit Tests

1. **llm_client.py**
   - Test CODER routing
   - Test Q4B routing
   - Test F16 round-robin
   - Test fallback behavior

2. **mem0-mcp**
   - Test embedding generation
   - Test reranker (mocked)
   - Test tag filtering with reranking
   - Test backwards compatibility

3. **collective graphs**
   - Test mixed model council
   - Test temperature variation
   - Test diversity metrics calculation

### Integration Tests

1. **End-to-end collective with CODER**
   - Council with code generation task
   - Verify CODER model used

2. **Memory search quality**
   - Compare before/after reranker
   - Measure score distribution
   - Validate tag filtering

3. **Diversity seat effectiveness**
   - Run council k=3 (single family)
   - Run council k=3 (mixed family)
   - Compare avg_diversity (expect >0.05 improvement)

4. **Judge concurrency** (if implemented)
   - Measure parallel judging latency
   - Compare vs single judge

### Smoke Tests

```bash
# Phase 1: Coder model
curl -X POST http://localhost:8080/api/collective/run \
  -H 'Content-Type: application/json' \
  -d '{"task":"Write a Python function to check if a number is prime","pattern":"council","k":2}' | jq

# Phase 2: Memory reranking
curl -X POST http://localhost:8080/api/memory/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"PETG vs ABS outdoor furniture","limit":5}' | jq

# Phase 3: Diversity seat
curl -X POST http://localhost:8080/api/collective/run \
  -H 'Content-Type: application/json' \
  -d '{"task":"Compare PETG vs ABS for Voron 0.2mm","pattern":"council","k":3}' | jq '.aux.diversity'

# Phase 4: Judge concurrency
# Run multiple councils in parallel and measure latency
```

---

## Rollback Plan

### If Phase 1 Fails
- Revert llm_client.py changes
- Remove CODER tests
- Continue with Phase 2

### If Phase 2 Fails
- Revert mem0-mcp changes
- Keep old embedding model
- Restore requirements.txt
- Continue with Phase 3

### If Phase 3 Fails
- Stop Q4B server
- Revert collective graph changes
- Remove Q4B from llm_client.py
- Continue with Phase 4 (or skip if desired)

### If Phase 4 Fails
- Stop F16_B server
- Revert round-robin logic
- Use single F16

**Safety Net**: All changes are backwards compatible. If a feature fails, disable via environment variables without code rollback.

---

## Resource Requirements

### Disk Space

- Coder model (Qwen2.5-Coder-32B Q4): ~18GB
- Diversity model (Mistral-7B Q4): ~4GB
- Judge model (Llama-3.3-70B F16): ~140GB (already downloaded)
- **Total additional**: ~22GB

### RAM Requirements

- Coder model: ~20GB (shares F16 server or dedicated)
- Diversity model (Q4B): ~6GB
- Judge concurrency (F16_B): ~160GB
- **Total additional**: 6-166GB (depending on Phase 4)

### Model Downloads

Time estimates on 1Gbps connection:
- Qwen2.5-Coder-32B: ~3 minutes
- Mistral-7B: ~1 minute
- **Total**: ~4 minutes

### Development Time

- Phase 1 (Coder): 2-3 hours
- Phase 2 (Memory): 3-4 hours
- Phase 3 (Diversity): 4-5 hours
- Phase 4 (Judge, optional): 3-4 hours
- **Total**: 12-16 hours (9-12 hours without Phase 4)

---

## Success Metrics

### Phase 1: Coder Model

- ✅ CODER routing works without errors
- ✅ Collective can complete code generation tasks
- ✅ Tests pass (unit + integration)

### Phase 2: Memory Enhancement

- ✅ Search quality improved (higher avg scores)
- ✅ Reranker improves top-3 relevance
- ✅ Tag filtering works with reranking
- ✅ No performance regression

### Phase 3: Diversity Seat

- ✅ Mixed-family council executes successfully
- ✅ avg_diversity increases by >0.05
- ✅ Proposals show different perspectives
- ✅ Graceful fallback if Q4B unavailable

### Phase 4: Judge Concurrency

- ✅ Parallel judging latency reduced by >20%
- ✅ Round-robin distributes load evenly
- ✅ No quality degradation
- ✅ Graceful fallback to single F16

---

## Documentation Updates

### Files to Update

1. **CLAUDE.md**
   - Add CODER model usage
   - Update memory service capabilities
   - Document diversity seat configuration

2. **docs/project-overview.md**
   - Update brain service section
   - Update memory MCP section
   - Add Q4B server details

3. **COLLECTIVE_META_AGENT_DEPLOYMENT.md**
   - Add diversity seat configuration
   - Update performance benchmarks
   - Add CODER integration examples

4. **New Files**
   - `docs/MEMORY_RERANKING.md`: Reranker configuration and tuning
   - `docs/DIVERSITY_SEAT.md`: Multi-family council setup

---

## Next Steps After Implementation

1. **Monitor Metrics**
   - Watch `collective_proposal_diversity` histogram
   - Track memory search quality scores
   - Measure council latency improvements

2. **Tune Parameters**
   - Adjust reranker threshold
   - Fine-tune diversity seat temperature
   - Optimize judge concurrency batch sizes

3. **Add to Memory**
   - Create consequential memories for each phase
   - Tag with `meta`, `dev`, `collective`
   - Retag using `scripts/retag_dev_memories.py`

4. **User Testing**
   - Test council with code generation
   - Compare search quality before/after
   - Validate diversity improvement

5. **Production Deployment**
   - Merge to main branch
   - Update production .env
   - Restart services
   - Monitor for 24 hours

---

## Questions and Decisions

### Q1: Should CODER be a dedicated server or share F16?

**Decision**: Start with shared F16 (fallback), add dedicated server later if needed.

**Rationale**:
- F16 has 65K context (sufficient for code)
- Reduces RAM pressure initially
- Can upgrade to dedicated later without code changes

### Q2: Which diversity model should we use?

**Options**:
- Mistral-7B-Instruct-v0.2 (7B, fast)
- Gemma-2-9B-Instruct (9B, high quality)
- Phi-3-medium-128K (14B, long context)

**Decision**: Mistral-7B-Instruct-v0.2

**Rationale**:
- Well-tested, stable
- Fast inference (~20-30 tok/s on M3 Ultra)
- Good balance of quality and speed

### Q3: Should we implement Phase 4 (Judge Concurrency)?

**Decision**: Assess RAM during Phase 3, decide then.

**Rationale**:
- Need to measure actual RAM usage first
- May not be necessary if single F16 is fast enough
- Can always add later if bottleneck identified

---

## Risks and Mitigations

### Risk 1: RAM Exhaustion

**Impact**: High
**Probability**: Medium (if Phase 4 implemented)

**Mitigation**:
- Monitor RAM usage during Phase 3
- Skip Phase 4 if <170GB free
- Use alternative tuning (increase parallelism)

### Risk 2: Model Download Failures

**Impact**: Low
**Probability**: Low

**Mitigation**:
- Use `--resume-download` flag
- Verify checksums after download
- Keep backups of .gguf files

### Risk 3: Backwards Compatibility Issues

**Impact**: Medium
**Probability**: Low

**Mitigation**:
- All features use environment flags
- Graceful fallbacks for missing models
- Tag filtering already tested

### Risk 4: Diversity Metrics Don't Improve

**Impact**: Low
**Probability**: Medium

**Mitigation**:
- Acceptable result (no regression)
- Can tune temperature/top_p
- Can try different diversity model

---

## Implementation Order Justification

### Why CODER first?

1. **Low complexity**: Simple routing change
2. **High value**: Enables code generation tasks
3. **No dependencies**: Can implement immediately
4. **Low risk**: Fallback to F16 if issues

### Why Memory second?

1. **Benefits all agents**: Improves context quality globally
2. **Medium complexity**: Well-defined scope
3. **Independent**: No dependencies on Phase 1
4. **Backwards compatible**: Existing memories still work

### Why Diversity third?

1. **Higher complexity**: Requires model download + startup script changes
2. **Depends on CODER pattern**: Uses similar routing logic
3. **Lower priority**: Current council works, this is optimization
4. **More testing needed**: Need to validate diversity improvement

### Why Judge Concurrency last?

1. **Optional**: May not be needed
2. **Resource intensive**: Requires significant RAM
3. **Depends on metrics**: Need Phase 3 data to decide
4. **Alternative solutions**: Can tune single F16 instead

---

## Timeline

**Week 1:**
- Day 1: Phase 1 (Coder Model) - 3 hours
- Day 2: Phase 2 (Memory Enhancement) - 4 hours
- Day 3: Phase 3 (Diversity Seat) - 5 hours
- Day 4: Testing and validation - 3 hours
- Day 5: Documentation and cleanup - 2 hours

**Total**: 17 hours (2-3 days of focused work)

**Week 2 (Optional):**
- Phase 4 (Judge Concurrency) if RAM allows

---

## Conclusion

This implementation plan provides a structured approach to adding high-impact features to KITTY while maintaining offline-first architecture and backwards compatibility. Each phase delivers independent value and can be deployed incrementally.

**Recommended Start**: Phase 1 (Coder Model) - highest value, lowest risk, fastest implementation.

**Status**: Ready for implementation
**Branch**: `feature/high-impact-additions`
**Assignee**: Claude Code
**Start Date**: TBD
