# KITTY LangGraph Architecture - Quick Reference

## Current vs Enhanced Architecture

### **BEFORE: Linear ReAct Loop**
```
User Query → ReAct Agent (10 iterations max)
                  ↓
            Parse Thought
                  ↓
            Execute Tool
                  ↓
            Add to History
                  ↓
            Repeat or Final Answer
```
**Problems:** Fixed iterations, no structured decisions, single model, sequential tools

---

### **AFTER: Multi-Agent LangGraph System**

```
┌─────────────────────────────────────────────────────────────────┐
│                        USER QUERY                                 │
└───────────────────────────┬─────────────────────────────────────┘
                            ↓
                    ┌───────────────┐
                    │  Intake Node  │ Load state, parse query
                    └───────┬───────┘
                            ↓
                ┌───────────────────────┐
                │  Memory Retrieval     │ Search Qdrant
                │  Node                 │ (3 relevant memories)
                └───────────┬───────────┘
                            ↓
                ┌───────────────────────┐
                │ Complexity Analyzer   │ Score: 0.0-1.0
                │ Node                  │ Identify: tools, search, vision
                └───────────┬───────────┘
                            ↓
              ┌─────────────┴─────────────┐
              ↓                           ↓
    ┌──────────────────┐        ┌──────────────────┐
    │  Q4 Router Agent │        │ F16 Deep Reasoner│
    │  (Fast, 80%)     │        │ (Precise, 20%)   │
    └────────┬─────────┘        └────────┬─────────┘
             ↓                           ↓
    Simple queries              Complex/uncertain
             ↓                           ↓
    ┌────────────────┐          ┌──────────────────┐
    │ Tool Selection │          │ Multi-Step       │
    │ & Planning     │          │ Reasoning        │
    └────────┬───────┘          └────────┬─────────┘
             ↓                           ↓
    ┌────────────────┐          ┌──────────────────┐
    │ Tool Execution │          │ Tool Refinement  │
    │ (Parallel)     │          │ (Retry/Improve)  │
    └────────┬───────┘          └────────┬─────────┘
             ↓                           ↓
             └─────────────┬─────────────┘
                           ↓
                  ┌────────────────┐
                  │ Validation     │ Verify results
                  │ Node           │ Check confidence
                  └────────┬───────┘
                           ↓
              ┌────────────┴────────────┐
              ↓                         ↓
    Confidence >= 0.75        Confidence < 0.75
              ↓                         ↓
    ┌──────────────────┐      ┌──────────────────┐
    │ Response         │      │ Escalate to F16  │
    │ Generator        │      │ or Refine        │
    └────────┬─────────┘      └────────┬─────────┘
             ↓                         ↓
             └──────────────┬──────────┘
                            ↓
                  ┌──────────────────┐
                  │ Store New Memory │
                  │ & Facts          │
                  └────────┬─────────┘
                           ↓
                  ┌──────────────────┐
                  │  FINAL RESPONSE  │
                  └──────────────────┘
```

---

## State Flow Example: "Design and print a bracket"

```python
# Initial State
{
  "query": "Design a bracket for 10mm bolt and print on Bamboo",
  "complexity_score": 0.65,  # Multi-step
  "requires_tools": True,
  "selected_tools": ["coding.generate", "fabrication.analyze_model", "fabrication.open_in_slicer"],
}

# After Tool Planning Node
{
  "tool_plan": """
    1. coding.generate → parametric bracket code
    2. Execute generated code → bracket.stl
    3. fabrication.analyze_model → dimensions + printer recommendation
    4. Check printer status → availability
    5. fabrication.open_in_slicer → launch BambuStudio
  """,
  "tool_results": {},
}

# After Tool Execution Node (parallel where possible)
{
  "tool_results": {
    "coding.generate": {
      "code": "def bracket(bolt_dia=10): ...",
      "stl_path": "/artifacts/bracket.stl"
    },
    "fabrication.analyze_model": {
      "dimensions": {"height": 45, "width": 30},
      "recommended_printer": "bamboo_h2d"
    },
    "fabrication.open_in_slicer": {
      "success": True,
      "app": "BambuStudio"
    }
  }
}

# After Validation Node
{
  "validation_passed": True,
  "confidence": 0.92,
  "tier_used": "Q4"
}

# Final Response
"Generated parametric bracket (45mm tall) and opened in BambuStudio. Model fits Bamboo H2D build volume. Ready to slice!"
```

---

## Graph Nodes Reference

### Core Nodes (All Workflows)

| Node | Purpose | Model | Inputs | Outputs |
|------|---------|-------|--------|---------|
| **Intake** | Parse query, load state | - | query, user_id, conversation_id | RouterState |
| **Memory Retrieval** | Search Qdrant | - | query, user_id | memories[] |
| **Complexity Analyzer** | Score 0.0-1.0 | Q4 | query, memories | complexity_score, requires_* |
| **Tool Selection** | Choose tools from registry | Q4 | query, complexity | selected_tools[], tool_plan |
| **Tool Execution** | Execute in parallel/sequence | - | tool_plan | tool_results{} |
| **Validation** | Verify results | Q4 | tool_results | validation_passed, confidence |
| **Response Generator** | Synthesize answer | Q4 | all_state | response |

### Specialized Nodes

| Node | Purpose | Model | When Used |
|------|---------|-------|-----------|
| **F16 Deep Reasoner** | Multi-step reasoning | F16 | complexity > 0.7 OR confidence < 0.75 |
| **Tool Refinement** | Retry with improved params | F16 | tool validation failed |
| **Memory Sufficiency Check** | Decide if more memories needed | Q4 | initial_memories insufficient |
| **Fact Extraction** | Extract facts to store | Q4 | End of conversation |

---

## Conditional Edges

```python
# From Complexity Analyzer
def route_by_complexity(state: RouterState) -> str:
    if state["complexity_score"] > 0.7:
        return "f16_deep_reasoner"
    return "q4_router"

# From Tool Execution
def check_tool_success(state: RouterState) -> str:
    if all(t.get("success") for t in state["tool_results"].values()):
        return "validation"
    if state["refinement_count"] < 2:
        return "tool_refinement"
    return "validation"  # Give up after 2 refinements

# From Validation
def check_confidence(state: RouterState) -> str:
    if state["confidence"] >= 0.75:
        return "respond"
    if state["refinement_count"] < state["max_refinements"]:
        return "f16_deep_reasoner"
    return "respond"  # Best effort
```

---

## Model Routing Decision Tree

```
Query Complexity Analysis
         │
         ├─ < 0.3 → Q4 Direct (simple lookup, status check)
         │          ↓
         │          Fast response (200-500ms)
         │
         ├─ 0.3-0.7 → Q4 with F16 Fallback
         │             ↓
         │             Try Q4 first
         │             ↓
         │             Confidence check
         │             ├─ >= 0.75 → Done
         │             └─ < 0.75 → Escalate to F16
         │
         └─ > 0.7 → F16 Direct (multi-step, technical, CAD)
                    ↓
                    Deep reasoning (1-3s)
                    ↓
                    High confidence output

Additional Factors:
+ requires_search → Add MCP tier (Perplexity)
+ requires_vision → F16 + vision tools
+ high_hazard → F16 + safety workflow + confirmation
```

---

## Tool Orchestration Patterns

### Pattern 1: Sequential (Dependencies)
```
CAD Generation → Analysis → Fabrication
(must wait)      (must wait)  (final)
```

### Pattern 2: Parallel (Independent)
```
┌─ web_search ─┐
├─ fetch_page ─┤  → All results → Synthesize
└─ image_search┘
```

### Pattern 3: Conditional (Decision Points)
```
Printer Status Check
   ├─ Available → Open Slicer
   └─ Busy → Queue Request → Notify User
```

### Pattern 4: Retry with Refinement
```
Tool Execution → Validation
   ├─ Success → Continue
   └─ Failure → Refine Parameters → Retry (max 2x)
```

---

## Key Metrics

```python
# Latency (P95)
brain_graph_duration_seconds{workflow="router"} < 1.5s
brain_graph_duration_seconds{workflow="deep_reasoner"} < 3.0s

# Model Usage
brain_tier_usage_ratio{tier="q4"} >= 0.80  # 80% Q4
brain_tier_usage_ratio{tier="f16"} <= 0.20  # 20% F16

# Tool Success
brain_tool_success_rate{tool="*"} >= 0.95

# Cost
brain_cost_per_query_usd{tier="q4"} ~= $0.002
brain_cost_per_query_usd{tier="f16"} ~= $0.015
brain_avg_cost_per_query_usd <= $0.006  # Blended average
```

---

## Implementation Checklist

### Phase 1: Foundation
- [ ] Create `services/brain/src/brain/agents/graphs/` directory
- [ ] Implement `RouterState` TypedDict
- [ ] Create `router_graph.py` with basic Q4 routing
- [ ] Add complexity analyzer
- [ ] Unit tests for each node
- [ ] Integration test with mock tools

### Phase 2: Tool Orchestration
- [ ] Implement tool execution node with parallel support
- [ ] Add validation node
- [ ] Create tool refinement logic
- [ ] Test with CAD→Fabrication workflow
- [ ] Add retry policies

### Phase 3: F16 Integration
- [ ] Implement `deep_reasoner_graph.py`
- [ ] Create handoff mechanism from Q4
- [ ] Add confidence scoring
- [ ] Test escalation scenarios
- [ ] Benchmark latency impact

### Phase 4: Memory Enhancement
- [ ] Implement memory retrieval node
- [ ] Add fact extraction
- [ ] Create memory sufficiency logic
- [ ] Test multi-turn conversations
- [ ] Verify memory loop convergence

### Phase 5: Production Rollout
- [ ] Feature flag: `BRAIN_USE_LANGGRAPH=true`
- [ ] Prometheus metrics
- [ ] Grafana dashboards
- [ ] A/B test with 10% traffic
- [ ] Monitor for 1 week
- [ ] Gradual rollout to 100%

---

## Comparison with Coder-Agent

The coder-agent implementation provides a proven template:

| Aspect | Coder-Agent | Brain Multi-Agent |
|--------|-------------|-------------------|
| **Purpose** | Code generation | Reasoning + Tool orchestration |
| **Workflow** | Plan→Code→Test→Run→Refine→Summarize | Intake→Analyze→Route→Execute→Validate→Respond |
| **Models** | Q4 (plan/test), F16 (code) | Q4 (routing), F16 (deep reasoning) |
| **Refinement Loop** | Max 2 iterations on test failure | Max 2 iterations on low confidence |
| **Validation** | Pytest in sandbox | Tool result validation + confidence check |
| **State Type** | `CoderState` (7 fields) | `RouterState` (12 fields) |
| **Nodes** | 6 nodes | 8-10 nodes (extensible) |

**Key Lesson:** The LangGraph pattern scales from domain-specific (coding) to general-purpose (reasoning) workflows seamlessly.

---

## Quick Start Guide (After Implementation)

```python
# Enable LangGraph routing
# In .env
BRAIN_USE_LANGGRAPH=true
BRAIN_LANGGRAPH_ROLLOUT_PERCENT=100

# Query will automatically use enhanced routing
response = await brain_orchestrator.generate_response(
    conversation_id="conv-123",
    request_id="req-456",
    prompt="Design a bracket and print it on Bamboo",
    user_id="user-789"
)

# Response includes graph execution metadata
{
    "output": "Generated parametric bracket...",
    "tier": "Q4",
    "confidence": 0.92,
    "graph_execution": {
        "nodes_executed": ["intake", "memory", "complexity", "q4_router", "tool_plan", "tool_exec", "validation", "respond"],
        "total_duration_ms": 1847,
        "tools_used": ["coding.generate", "fabrication.analyze_model", "fabrication.open_in_slicer"]
    }
}
```

---

**See Full Proposal:** `Research/KITTY_LangGraph_Multi_Agent_Enhancement.md`
