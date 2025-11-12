# LangGraph Integration - Code Bookmarks Reference

This document tracks all important variables, configuration points, and integration interfaces for easy navigation in VS Code.

---

## 🔧 Configuration Variables

### Environment Variables (.env)

**File**: `.env` (repository root)

| Variable | Purpose | Location | Default |
|----------|---------|----------|---------|
| `BRAIN_USE_LANGGRAPH` | Enable/disable LangGraph routing | `.env:257` | `false` |
| `BRAIN_LANGGRAPH_ROLLOUT_PERCENT` | A/B testing rollout percentage (0-100) | `.env:258` | `0` |
| `LLAMACPP_Q4_HOST` | Q4 llama.cpp server endpoint | `.env:261` | `http://localhost:8083` |
| `LLAMACPP_Q4_ALIAS` | Q4 model alias for requests | `.env:262` | `kitty-q4` |
| `LLAMACPP_F16_HOST` | F16 llama.cpp server endpoint | `.env:263` | `http://localhost:8082` |
| `LLAMACPP_F16_ALIAS` | F16 model alias for requests | `.env:264` | `kitty-f16` |

**VS Code Bookmark**: `.env` lines 257-264

---

## 🎯 Integration Points

### 1. BrainOrchestrator Integration

**File**: `services/brain/src/brain/orchestrator.py`

**Key Integration Point** (line ~236-244):
```python
# Check if LangGraph routing should be used
if self._langgraph and await self._langgraph.should_use_langgraph(routing_request):
    logger.info("Using LangGraph routing for this request")
    try:
        result = await self._langgraph.route_with_langgraph(routing_request)
    except Exception as exc:
        logger.error(f"LangGraph routing failed, falling back to traditional: {exc}")
        result = await self._router.route(routing_request)
else:
    result = await self._router.route(routing_request)
```

**VS Code Bookmarks**:
- `orchestrator.py:236-244` - Main LangGraph routing decision point
- `orchestrator.py:115-120` - LangGraph initialization in `__init__`

---

### 2. LangGraph Integration Layer

**File**: `services/brain/src/brain/agents/graphs/integration.py`

**Class**: `LangGraphRoutingIntegration`

**Important Methods**:

| Method | Line | Purpose |
|--------|------|---------|
| `__init__` | 43-61 | Initialize with llm_client, memory_client, mcp_client |
| `should_use_langgraph` | 63-79 | A/B testing decision (hash-based rollout) |
| `route_with_langgraph` | 81-155 | Main routing workflow orchestration |
| `_run_router_graph` | 157-175 | Execute Q4 router graph |
| `_convert_to_routing_result` | 177-196 | Convert LangGraph state to RoutingResult |

**Key Variables**:
- `self.enabled` (line 57) - Feature flag from `BRAIN_USE_LANGGRAPH`
- `self.rollout_percent` (line 58) - Rollout % from `BRAIN_LANGGRAPH_ROLLOUT_PERCENT`
- `hash_val` (line 72) - Hash-based A/B test value (0-99)

**VS Code Bookmarks**:
- `integration.py:43` - LangGraphRoutingIntegration.__init__
- `integration.py:63` - should_use_langgraph (A/B testing logic)
- `integration.py:81` - route_with_langgraph (main entry point)

---

### 3. Router Graph (Q4 Primary)

**File**: `services/brain/src/brain/agents/graphs/router_graph.py`

**Class**: `RouterGraph`

**Key Nodes** (workflow execution order):

| Node | Method | Line | Purpose |
|------|--------|------|---------|
| intake | `_intake_node` | 133-153 | Initialize state from request |
| memory_retrieval | `_memory_retrieval_node` | 155-190 | Retrieve conversation context |
| complexity_analysis | `_complexity_analysis_node` | 192-219 | Score query complexity (0.0-1.0) |
| tool_identification | `_tool_identification_node` | 221-254 | Identify needed tools |
| tool_execution | `_tool_execution_node` | 256-296 | Execute tools in parallel |
| validation | `_validation_node` | 298-330 | Validate tool results |
| response_generation | `_response_generation_node` | 332-393 | Generate Q4 response |
| f16_escalation | `_f16_escalation_node` | 395-426 | Delegate to F16 deep reasoner |

**Escalation Decision** (line 471-485):
```python
def _should_escalate_to_f16(self, state: RouterState) -> Literal["f16_escalation", END]:
    confidence = state.get("confidence", 1.0)
    complexity = state.get("complexity_score", 0.0)
    requires_deep_reasoning = state.get("requires_deep_reasoning", False)

    should_escalate = (
        confidence < 0.75  # Low confidence trigger
        or complexity > 0.7  # High complexity trigger
        or requires_deep_reasoning  # Explicit trigger
    )
```

**VS Code Bookmarks**:
- `router_graph.py:133` - _intake_node (workflow start)
- `router_graph.py:192` - _complexity_analysis_node (complexity scoring)
- `router_graph.py:332` - _response_generation_node (Q4 inference)
- `router_graph.py:395` - _f16_escalation_node (F16 delegation)
- `router_graph.py:471` - _should_escalate_to_f16 (escalation decision)
- `router_graph.py:628` - compile() (LangGraph graph construction)

---

### 4. Deep Reasoner Graph (F16 Secondary)

**File**: `services/brain/src/brain/agents/graphs/deep_reasoner_graph.py`

**Class**: `DeepReasonerGraph`

**Key Nodes** (7-node workflow):

| Node | Method | Line | Purpose |
|------|--------|------|---------|
| context_synthesis | `_context_synthesis_node` | 125-162 | Combine Q4 + memories + tools |
| problem_decomposition | `_problem_decomposition_node` | 164-200 | Break into 2-4 sub-problems |
| chain_of_thought | `_chain_of_thought_node` | 202-270 | Multi-step reasoning (max 5 steps) |
| tool_refinement | `_tool_refinement_node` | 272-323 | Re-execute failed tools |
| evidence_synthesis | `_evidence_synthesis_node` | 325-373 | Combine reasoning + tools |
| self_evaluation | `_self_evaluation_node` | 375-427 | Quality assessment (0.0-1.0) |
| response_crafting | `_response_crafting_node` | 429-488 | Final detailed response |

**Important Variables**:
- `max_reasoning_steps` (line 116) - Default: 5, controls chain-of-thought depth
- `self_evaluation_score` (line 400) - Parsed from F16 response, 0.0-1.0
- `reasoning_steps` (line 235) - List of reasoning step dictionaries

**VS Code Bookmarks**:
- `deep_reasoner_graph.py:125` - _context_synthesis_node (F16 workflow start)
- `deep_reasoner_graph.py:164` - _problem_decomposition_node (break into sub-problems)
- `deep_reasoner_graph.py:202` - _chain_of_thought_node (multi-step reasoning)
- `deep_reasoner_graph.py:375` - _self_evaluation_node (quality score)
- `deep_reasoner_graph.py:429` - _response_crafting_node (final F16 response)
- `deep_reasoner_graph.py:656` - compile() (LangGraph graph construction)

---

### 5. Complexity Analyzer

**File**: `services/brain/src/brain/agents/complexity/analyzer.py`

**Class**: `ComplexityAnalyzer`

**5-Factor Scoring** (line 63-97):

| Factor | Method | Line | Weight | Description |
|--------|--------|------|--------|-------------|
| Token Count | `_score_token_count` | 99-112 | 15% | Query length |
| Technical Density | `_score_technical_density` | 114-131 | 30% | CAD/technical terms |
| Multi-Step | `_score_multi_step` | 133-146 | 25% | "then", "after", "also" |
| Ambiguity | `_score_ambiguity` | 148-161 | 15% | "maybe", "somehow" |
| Tool Count | `_score_tool_count` | 163-176 | 15% | Estimated tools |

**Technical Keywords** (line 24-41):
```python
self.technical_keywords = {
    "cad", "parametric", "topology", "mesh", "stl", "step", "iges",
    "assembly", "constraint", "extrude", "revolve", "loft", "sweep",
    "fabrication", "print", "laser", "cnc", "mill", "lathe",
    "material", "aluminum", "steel", "plastic", "abs", "pla", "petg",
    # ... (42 total keywords)
}
```

**VS Code Bookmarks**:
- `analyzer.py:24-41` - technical_keywords (CAD/fabrication terms)
- `analyzer.py:63-97` - analyze() (main 5-factor scoring)
- `analyzer.py:114-131` - _score_technical_density (highest weight: 30%)

---

### 6. Memory Graph (Adaptive Retrieval)

**File**: `services/brain/src/brain/agents/graphs/memory_graph.py`

**Class**: `MemoryAugmentedGraph`

**Key Nodes**:

| Node | Method | Line | Purpose |
|------|--------|------|---------|
| initial_search | `_initial_search_node` | 99-132 | Threshold: 0.75, Limit: 3 |
| sufficiency_check | `_sufficiency_check_node` | 134-172 | Score: (num/3 * 0.4) + (avg * 0.6) |
| deep_search | `_deep_search_node` | 174-208 | Threshold: 0.60, Limit: 5 |
| fact_extraction | `_fact_extraction_node` | 210-275 | Extract facts for storage |
| context_formatting | `_context_formatting_node` | 277-311 | Format for LLM consumption |

**Thresholds**:
- `initial_threshold` (line 79) - 0.75 for initial search
- `deep_threshold` (line 80) - 0.60 for deep search
- `sufficiency_threshold` (line 81) - 0.70 for sufficiency check

**Sufficiency Formula** (line 156-159):
```python
num_score = min(num_memories / 3.0, 1.0)  # Target: 3+ memories
quality_score = avg_score  # Already 0-1
sufficiency_score = (num_score * 0.4) + (quality_score * 0.6)
```

**VS Code Bookmarks**:
- `memory_graph.py:79-81` - Memory search thresholds
- `memory_graph.py:99` - _initial_search_node (first retrieval)
- `memory_graph.py:134` - _sufficiency_check_node (decide deep search)
- `memory_graph.py:210` - _fact_extraction_node (pattern matching)

---

### 7. Tool Orchestrator

**File**: `services/brain/src/brain/agents/orchestration/tool_orchestrator.py`

**Class**: `ToolOrchestrator`

**Key Methods**:

| Method | Line | Purpose |
|--------|------|---------|
| `execute_tools` | 67-142 | Main entry point, parallel execution |
| `_topological_sort` | 144-181 | Dependency resolution, batch grouping |
| `_execute_batch_parallel` | 183-199 | Parallel execution with semaphore |
| `_execute_tool_with_retry` | 201-250 | Retry logic with exponential backoff |

**Important Variables**:
- `max_parallel` (line 57) - Default: 3 concurrent tool executions
- `retry_delays` (line 204) - `[1, 2, 4, 8]` seconds exponential backoff
- `max_retries` (line 213-216) - CRITICAL/HIGH: 2, MEDIUM/LOW: 1

**Dependency Examples** (line 108-111):
```python
dependencies = {
    "analyze_model": ["generate_cad"],
    "optimize_model": ["analyze_model"],
    "slice_model": ["generate_cad"],
}
```

**VS Code Bookmarks**:
- `tool_orchestrator.py:67` - execute_tools (main entry)
- `tool_orchestrator.py:144` - _topological_sort (dependency resolution)
- `tool_orchestrator.py:201` - _execute_tool_with_retry (retry logic)

---

### 8. LangGraph Metrics

**File**: `services/brain/src/brain/agents/metrics/langgraph_metrics.py`

**Prometheus Metrics** (15+ metrics):

| Metric | Line | Type | Purpose |
|--------|------|------|---------|
| `GRAPH_NODE_DURATION` | 11-17 | Histogram | Node execution time |
| `GRAPH_EXECUTION_TOTAL` | 19-24 | Counter | Graph runs by status |
| `GRAPH_TOTAL_DURATION` | 26-31 | Histogram | Total graph duration |
| `TIER_ROUTING_COUNT` | 35-39 | Counter | Local/MCP/Frontier routing |
| `ESCALATION_COUNT` | 41-45 | Counter | F16 escalations by reason |
| `ESCALATION_STATUS` | 47-51 | Counter | Success/fallback status |
| `CONFIDENCE_DISTRIBUTION` | 55-60 | Histogram | Confidence scores 0.0-1.0 |
| `COMPLEXITY_SCORE` | 62-66 | Histogram | Complexity scores 0.0-1.0 |
| `TOOL_EXECUTION_TOTAL` | 70-74 | Counter | Tool runs by status |
| `TOOL_EXECUTION_DURATION` | 76-81 | Histogram | Tool execution time |
| `TOOL_RETRY_TOTAL` | 83-87 | Counter | Tool retry counts |
| `MEMORY_RETRIEVAL_DURATION` | 91-96 | Histogram | Memory search time |
| `MEMORY_HIT_TOTAL` | 98-102 | Counter | Initial/deep searches |
| `MEMORY_SUFFICIENCY_SCORE` | 104-108 | Histogram | Sufficiency scores |
| `FACT_EXTRACTION_TOTAL` | 110-113 | Counter | Facts extracted |

**Context Managers** (for easy instrumentation):

| Manager | Line | Purpose |
|---------|------|---------|
| `track_node_execution` | 152-161 | Auto-track node duration |
| `track_graph_execution` | 163-177 | Auto-track full graph |
| `track_tool_execution` | 179-194 | Auto-track tool execution |

**VS Code Bookmarks**:
- `langgraph_metrics.py:11-113` - All Prometheus metric definitions
- `langgraph_metrics.py:152` - track_node_execution context manager
- `langgraph_metrics.py:163` - track_graph_execution context manager

---

## 📊 State Definitions

**File**: `services/brain/src/brain/agents/graphs/states.py`

**TypedDict Classes**:

| State Class | Line | Used By | Key Fields |
|-------------|------|---------|------------|
| `RouterState` | 14-44 | RouterGraph | query, complexity_score, confidence, tier_used |
| `DeepReasonerState` | 46-78 | DeepReasonerGraph | reasoning_steps, self_evaluation_score, q4_attempt |
| `MemoryAugmentedState` | 80-106 | MemoryAugmentedGraph | all_memories, memory_sufficiency_score, facts_extracted |

**Important Fields**:

**RouterState** (line 14-44):
- `complexity_score` (line 28) - Float 0.0-1.0 from ComplexityAnalyzer
- `confidence` (line 31) - Float 0.0-1.0 from Q4 response
- `tier_used` (line 33) - RoutingTier enum (LOCAL, MCP, FRONTIER)
- `escalated_to_f16` (line 39) - Bool, true if F16 was used

**DeepReasonerState** (line 46-78):
- `reasoning_steps` (line 63) - List of reasoning dictionaries
- `self_evaluation_score` (line 69) - Float 0.0-1.0 from F16
- `q4_confidence` (line 55) - Original Q4 confidence (for comparison)

**MemoryAugmentedState** (line 80-106):
- `memory_sufficiency_score` (line 93) - Float 0.0-1.0 from sufficiency check
- `should_deep_search` (line 94) - Bool, triggers deep search node
- `facts_extracted` (line 96) - List of fact strings for storage

**VS Code Bookmarks**:
- `states.py:14-44` - RouterState (Q4 workflow state)
- `states.py:46-78` - DeepReasonerState (F16 workflow state)
- `states.py:80-106` - MemoryAugmentedState (memory workflow state)

---

## 🎛️ LLM Client Integration

**File**: `services/brain/src/brain/llm/multi_server_client.py` (assumed path)

**Key Methods for Q4/F16 Routing**:

| Method | Purpose | Model Alias |
|--------|---------|-------------|
| `generate(model="kitty-q4")` | Q4 fast inference | Uses `LLAMACPP_Q4_HOST` |
| `generate(model="kitty-f16")` | F16 precise inference | Uses `LLAMACPP_F16_HOST` |

**Example Usage** (from router_graph.py:354):
```python
result = await self.llm.generate(
    prompt=prompt,
    model="kitty-q4",  # Routes to LLAMACPP_Q4_HOST
    temperature=0.7,
    max_tokens=1000,
)
```

---

## 🔍 Quick Navigation by Feature

### A/B Testing & Feature Flags
- `.env:257-258` - Feature flag configuration
- `integration.py:57-58` - Feature flag initialization
- `integration.py:63-79` - Hash-based A/B testing logic
- `orchestrator.py:236-244` - Feature flag check before routing

### Escalation Decision Logic
- `router_graph.py:471-485` - _should_escalate_to_f16 (3 triggers)
- `analyzer.py:63-97` - Complexity scoring (5 factors)
- `router_graph.py:332-393` - Q4 confidence extraction

### Memory Retrieval
- `memory_graph.py:79-81` - Search thresholds (initial/deep/sufficiency)
- `memory_graph.py:99-132` - Initial search node
- `memory_graph.py:134-172` - Sufficiency check logic
- `memory_graph.py:174-208` - Deep search node

### Tool Orchestration
- `tool_orchestrator.py:67-142` - Main execution workflow
- `tool_orchestrator.py:144-181` - Topological sort for dependencies
- `tool_orchestrator.py:183-199` - Parallel execution with semaphore
- `tool_orchestrator.py:201-250` - Retry logic with exponential backoff

### Metrics & Observability
- `langgraph_metrics.py:11-113` - All metric definitions
- `langgraph_metrics.py:152-194` - Context managers for tracking
- `router_graph.py:617-626` - Metrics instrumentation in run()
- `deep_reasoner_graph.py:645-654` - Metrics instrumentation in run()

---

## 📝 VS Code Bookmark Recommendations

### Critical Integration Points (Must Bookmark)
1. `orchestrator.py:236` - Main LangGraph routing decision
2. `integration.py:81` - route_with_langgraph entry point
3. `router_graph.py:471` - F16 escalation decision
4. `.env:257` - Feature flags (BRAIN_USE_LANGGRAPH)

### Workflow Entry Points
5. `router_graph.py:133` - RouterGraph intake (Q4 start)
6. `deep_reasoner_graph.py:125` - DeepReasonerGraph context synthesis (F16 start)
7. `memory_graph.py:99` - Memory initial search (memory start)
8. `tool_orchestrator.py:67` - Tool execution orchestration

### Configuration & Thresholds
9. `router_graph.py:471-485` - Escalation thresholds (0.75, 0.7)
10. `memory_graph.py:79-81` - Memory search thresholds (0.75, 0.60, 0.70)
11. `analyzer.py:24-41` - Technical keywords for complexity
12. `tool_orchestrator.py:57` - max_parallel = 3

### Metrics & Monitoring
13. `langgraph_metrics.py:11` - Prometheus metrics start
14. `langgraph_metrics.py:152` - track_node_execution
15. `router_graph.py:617` - Metrics collection in Q4

### State Management
16. `states.py:14` - RouterState definition
17. `states.py:46` - DeepReasonerState definition
18. `states.py:80` - MemoryAugmentedState definition

---

## 🧪 Test File References

### Unit Tests

**File**: `tests/unit/test_complexity_analyzer.py`
- Line 15-425: 15 test classes, 230 assertions
- Key: `test_technical_density` (line ~50), `test_multi_step_detection` (line ~120)

**File**: `tests/unit/test_router_graph.py`
- Line 15-436: 14 test classes, 70+ assertions
- Key: `test_complete_workflow_simple_query` (line ~80), `test_f16_escalation` (line ~200)

---

## 🔗 External Integrations

### llama.cpp Servers
- Q4 server: `http://localhost:8083` (configured in `.env:261`)
- F16 server: `http://localhost:8082` (configured in `.env:263`)
- Health endpoint: `/health`
- Inference endpoint: `/v1/chat/completions` (OpenAI-compatible)

### Prometheus Metrics
- Metrics endpoint: `http://localhost:8000/metrics`
- Query examples in `IMPLEMENTATION_SUMMARY.md:425-443`

### Grafana Dashboards
- 4 JSON files in `infra/grafana/dashboards/`
- Import via Grafana UI: Dashboards → Import → Upload JSON

---

**Last Updated**: 2025-11-12
**Total Bookmarks Recommended**: 18 critical points
**Use in VS Code**: Bookmarks extension or built-in marks (Ctrl+K Ctrl+K)
