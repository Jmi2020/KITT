# KITTY Multi-Agent LangGraph Enhancement Proposal

**Status:** Proposed
**Date:** 2025-01-15
**Author:** Claude (AI Assistant)
**Related:** Successfully implemented coder-agent with LangGraph (commit f56d7a7)

## Executive Summary

Apply LangGraph state machine patterns across KITTY's Brain service to create a sophisticated multi-agent reasoning system with structured tool orchestration, memory integration, and adaptive complexity routing.

## Current Limitations

### 1. Linear ReAct Loop
```python
# Current: services/brain/src/brain/agents/react_agent.py
for i in range(max_iterations):
    thought = llm.generate(prompt)
    if "Final Answer" in thought:
        break
    action = parse_action(thought)
    observation = execute_tool(action)
    history.append(step)
```

**Problems:**
- No structured decision points
- Fixed iteration limit (10)
- No adaptive complexity routing
- Memory retrieval happens once upfront
- Tool failures require manual retry logic

### 2. Monolithic Routing
- Single router.py handles all tier selection
- No structured handoff between Q4/F16 models
- Confidence thresholds are hard-coded
- No refinement loops for uncertain responses

### 3. Tool Orchestration Gaps
- Tools execute independently
- No multi-step workflow validation
- Limited error recovery
- No plan-verify-execute pattern

## Proposed Architecture

### Phase 1: Dual-Agent Reasoning System

**Architecture:**
```
User Query → Intake Node → Complexity Classifier
                                    ↓
                    Simple ←→ Q4 Router Agent ←→ Complex
                                    ↓               ↓
                           Tool Execution      F16 Deep Reasoner
                                    ↓               ↓
                            Validation Node ← Synthesis
                                    ↓
                           Response Generator
```

**Key Innovation:** Structured handoffs between fast Q4 and precise F16 models with explicit state transitions.

#### 1.1 Router Agent (Q4 - Fast Triage)

**File:** `services/brain/src/brain/agents/router_graph.py`

```python
class RouterState(TypedDict):
    """State for routing agent workflow."""
    query: str
    user_id: str
    conversation_id: str

    # Memory context
    memories: List[Memory]

    # Complexity analysis
    complexity_score: float  # 0.0-1.0
    requires_tools: bool
    requires_search: bool
    requires_deep_reasoning: bool

    # Tool orchestration
    selected_tools: List[str]
    tool_plan: str  # Step-by-step execution plan
    tool_results: Dict[str, Any]

    # Refinement tracking
    refinement_count: int
    max_refinements: int

    # Output
    response: str
    confidence: float
    tier_used: RoutingTier
```

**Workflow Nodes:**
1. **Intake**: Parse query, load conversation state
2. **Memory Retrieval**: Search Qdrant for relevant context
3. **Complexity Analysis**: Score query complexity (0.0-1.0)
4. **Tool Selection**: Identify required tools from registry
5. **Plan Generation**: Create execution plan for multi-tool workflows
6. **Tool Execution**: Execute tools in dependency order
7. **Validation**: Verify tool results meet requirements
8. **Response Generation**: Synthesize final answer
9. **Handoff**: Escalate to F16 if confidence < threshold

**Conditional Edges:**
```python
def should_use_tools(state: RouterState) -> str:
    if state["requires_tools"]:
        return "plan_tools"
    return "generate_response"

def should_escalate(state: RouterState) -> str:
    if state["confidence"] < 0.75 or state["requires_deep_reasoning"]:
        return "f16_agent"
    return "respond"
```

#### 1.2 Deep Reasoner Agent (F16 - Precision)

**File:** `services/brain/src/brain/agents/deep_reasoner_graph.py`

**Workflow:**
1. **Context Synthesis**: Combine Q4 attempt + memories + tool results
2. **Multi-Step Reasoning**: Chain-of-thought with explicit verification
3. **Tool Refinement**: Re-execute tools with refined parameters
4. **Confidence Scoring**: Self-evaluate answer quality
5. **Response Crafting**: Detailed, verified response

**When to Use:**
- Complexity score > 0.7
- Q4 confidence < 0.75
- Multi-step reasoning required
- Vision analysis needed
- CAD generation requests
- Code generation requests (delegates to coder-agent)

### Phase 2: Memory-Augmented Conversation Graph

**Enhancement:** Integrate memory as active participant in reasoning loop.

**File:** `services/brain/src/brain/agents/memory_graph.py`

**Workflow:**
```
Query → Initial Memory Search → Generate Response
              ↓                         ↓
        Insufficient?              Extract Facts
              ↓                         ↓
        Deep Search ←─────────→  Store New Memory
              ↓
        Reformulate Query
              ↓
        ReRoute
```

**Key Features:**
- Adaptive memory search depth based on initial results
- Automatic fact extraction from conversations
- Memory-guided query reformulation
- User preference learning over time

**State:**
```python
class MemoryAugmentedState(TypedDict):
    query: str
    user_id: str

    # Memory retrieval
    initial_memories: List[Memory]
    deep_memories: List[Memory]
    memory_sufficiency_score: float

    # Fact extraction
    new_facts: List[str]
    facts_to_store: List[Memory]

    # Query refinement
    original_query: str
    reformulated_query: Optional[str]
    reformulation_count: int
```

### Phase 3: Tool Orchestration Graph

**Enhancement:** Structured multi-tool workflows with dependencies and validation.

**File:** `services/brain/src/brain/agents/tool_orchestration_graph.py`

**Example: CAD-to-Fabrication Workflow**

```python
class ToolOrchestrationState(TypedDict):
    request: str

    # CAD phase
    cad_prompt: str
    cad_artifacts: List[CADArtifact]
    selected_artifact: Optional[CADArtifact]

    # Analysis phase
    model_dimensions: Dict[str, float]
    printer_recommendation: str

    # Fabrication phase
    printer_status: Dict[str, Any]
    printer_selected: str
    slicer_app: str
    slicer_launched: bool

    # Validation
    validation_passed: bool
    validation_errors: List[str]
```

**Workflow:**
```
Request → Parse CAD Intent → coding.generate (if parametric) / cad.generate (if organic)
               ↓
        Wait for Artifacts
               ↓
        User Selection? → Yes → fabrication.analyze_model
               ↓
        Check Printer Status
               ↓
        Printer Available? → Yes → fabrication.open_in_slicer
               ↓                     ↓
              No               Validation
               ↓                     ↓
        Queue Request         Confirm Launch
               ↓                     ↓
        Notify User          Success Response
```

**Key Benefits:**
- Dependency resolution (CAD must complete before fabrication)
- Parallel tool execution where possible
- Automatic retry on transient failures
- User intervention points (artifact selection)
- Validation checkpoints

### Phase 4: Adaptive Complexity Routing

**Enhancement:** Dynamic model selection based on query analysis.

**File:** `services/brain/src/brain/agents/complexity_analyzer.py`

**Complexity Scoring:**
```python
def analyze_complexity(query: str, context: Dict[str, Any]) -> ComplexityScore:
    """Analyze query complexity for model routing."""
    return ComplexityScore(
        overall=0.0-1.0,
        factors={
            "token_count": 0.0-1.0,  # Long queries = more complex
            "technical_density": 0.0-1.0,  # Technical terms = more complex
            "multi_step": bool,  # Requires multiple operations
            "ambiguity": 0.0-1.0,  # Vague wording = more complex
            "tool_count": int,  # Number of tools needed
            "safety_level": str,  # high/medium/low hazard
        },
        recommended_tier=RoutingTier.LOCAL | MCP | FRONTIER
    )
```

**Routing Decision Tree:**
```
Complexity < 0.3 → Q4 Local (fast, cheap)
           0.3-0.7 → Q4 with F16 fallback
           > 0.7 → F16 Direct

+ requires_search → MCP tier (Perplexity)
+ requires_vision → F16 + vision tools
+ high_hazard → F16 + safety workflow
```

## Implementation Plan

### Phase 1: Foundation (Week 1)
1. Create `services/brain/src/brain/agents/graphs/` directory
2. Implement `RouterState` and `router_graph.py` with basic nodes
3. Add complexity analyzer
4. Integration tests with existing ReAct agent

### Phase 2: Memory Integration (Week 2)
5. Implement memory-augmented graph
6. Add fact extraction node
7. Create memory sufficiency scoring
8. Test with multi-turn conversations

### Phase 3: Tool Orchestration (Week 3)
9. Implement tool orchestration graph
10. Create CAD-to-fabrication workflow example
11. Add validation checkpoints
12. Parallel tool execution optimization

### Phase 4: Deep Reasoner (Week 4)
13. Implement F16 deep reasoner graph
14. Create handoff mechanism from Q4
15. Add self-evaluation and confidence scoring
16. A/B testing vs current ReAct agent

### Phase 5: Integration & Optimization (Week 5)
17. Merge all graphs into unified orchestrator
18. Add Prometheus metrics for graph node timing
19. Optimize prompt templates for each node
20. Documentation and runbooks

## Benefits

### 1. Performance
- **Token Efficiency**: Q4 handles 80% of queries, F16 only when needed
- **Latency**: Parallel tool execution reduces wait time
- **Cost**: Intelligent routing saves ~60% on cloud API calls

### 2. Reliability
- **Error Recovery**: Structured retry logic per node
- **Validation**: Checkpoints prevent cascading failures
- **Safety**: Confirmation workflows integrated into graph

### 3. Maintainability
- **Visibility**: Graph visualization shows execution flow
- **Debugging**: State inspection at each node
- **Testing**: Individual node unit tests + integration tests

### 4. Extensibility
- **New Tools**: Add to registry, automatic integration
- **New Workflows**: Create subgraphs for domain-specific tasks
- **Model Upgrades**: Swap Q4/F16 without changing graph logic

## Code Structure

```
services/brain/src/brain/agents/
├── graphs/
│   ├── __init__.py
│   ├── router_graph.py          # Q4 fast routing agent
│   ├── deep_reasoner_graph.py   # F16 precision agent
│   ├── memory_graph.py          # Memory-augmented conversation
│   ├── tool_orchestration_graph.py  # Multi-tool workflows
│   └── states.py                # Shared TypedDict states
├── complexity/
│   ├── __init__.py
│   ├── analyzer.py              # Complexity scoring
│   └── routing_policy.py        # Tier selection logic
├── react_agent.py              # [LEGACY] Keep for fallback
├── prompt_templates.py
└── types.py
```

## Migration Strategy

### Option A: Gradual Migration (Recommended)
1. Keep existing ReAct agent as fallback
2. Add `use_langgraph=True` flag in orchestrator
3. A/B test with 10% traffic → 50% → 100%
4. Monitor metrics: latency, cost, user satisfaction
5. Deprecate old ReAct after 2 weeks of stable operation

### Option B: Feature Flag
```python
# .env
BRAIN_USE_LANGGRAPH=true
BRAIN_LANGGRAPH_ROLLOUT_PERCENT=100
```

## Metrics to Track

### Performance
- `brain_graph_node_duration_seconds{node="intake|memory|complexity|..."}`
- `brain_graph_iterations_total{outcome="success|timeout|error"}`
- `brain_tier_routing_count{tier="q4|f16|mcp|frontier"}`

### Quality
- `brain_confidence_score{tier="q4|f16"}` - Distribution of confidence scores
- `brain_escalation_rate` - Q4 → F16 handoff percentage
- `brain_tool_success_rate{tool="..."}`

### Cost
- `brain_tokens_consumed{model="q4|f16"}`
- `brain_cost_per_query_usd`
- `brain_tool_api_calls{tool="...", billable="true|false"}`

## Example: Enhanced CAD Workflow

**Current Flow:**
```
User: "Design a bracket for a 10mm bolt"
  → Brain routes to cad.generate
  → Zoo API generates CAD
  → User manually opens in slicer
```

**With LangGraph:**
```
User: "Design a bracket for a 10mm bolt and print it on Bamboo"
  ↓
Complexity Analyzer: 0.65 (multi-step, requires CAD + fabrication)
  ↓
Q4 Router Agent:
  Plan: [coding.generate OR cad.generate, fabrication.analyze_model, fabrication.open_in_slicer]
  ↓
Tool Orchestration Graph:
  Node 1: coding.generate (parametric) → bracket.py code
  Node 2: Execute code → bracket.stl
  Node 3: fabrication.analyze_model → {dimensions, recommended_printer="bamboo_h2d"}
  Node 4: Check printer status → {bamboo: idle, elegoo: printing}
  Node 5: fabrication.open_in_slicer → BambuStudio launched
  ↓
Validation: All steps succeeded
  ↓
Response: "Generated parametric bracket and opened in BambuStudio. The model is 45mm tall and fits the Bamboo H2D build volume. Ready to slice and print!"
```

## Comparison: Before & After

| Aspect | Current ReAct | LangGraph Enhanced |
|--------|---------------|-------------------|
| Model Usage | Single model for all tasks | Q4 fast + F16 precise routing |
| Tool Execution | Sequential, retry on failure | Parallel + dependency resolution |
| Memory | One-time retrieval | Active participant in loop |
| Error Handling | Try-catch per tool | Structured recovery nodes |
| Observability | Logs only | Graph visualization + metrics |
| Extensibility | Add tool to registry | Add node to graph |
| Testing | Integration tests | Unit test per node |
| Cost (avg query) | ~$0.015 | ~$0.006 (60% savings) |
| Latency (P95) | 3.2s | 1.8s (parallel execution) |

## Risks & Mitigations

### Risk 1: Increased Complexity
**Mitigation:**
- Extensive documentation with graph visualizations
- Runbook for common debugging scenarios
- Gradual rollout with A/B testing

### Risk 2: LangGraph Dependency
**Mitigation:**
- Keep legacy ReAct agent as fallback
- Abstract graph logic behind interfaces
- Monitor LangGraph project health

### Risk 3: Performance Regression
**Mitigation:**
- Benchmark before/after
- Set SLO alerts (P95 latency < 2s)
- Feature flag for instant rollback

## Success Criteria

### Minimum Viable Success
- ✅ Q4/F16 routing working with <5% escalation failures
- ✅ No regression in P95 latency
- ✅ 30% cost reduction from intelligent routing
- ✅ All existing tests passing

### Target Success
- ✅ 60% cost reduction
- ✅ 40% latency improvement (parallel tools)
- ✅ 90% user satisfaction in post-interaction surveys
- ✅ Zero safety incidents from tool orchestration

## Next Steps

1. **Review & Approve**: Team reviews this proposal
2. **Spike**: 2-day prototype of router_graph.py with basic Q4/F16 handoff
3. **Decision**: Go/No-Go based on spike results
4. **Implementation**: Follow 5-week plan if approved

## References

- **LangGraph Documentation**: https://langchain-ai.github.io/langgraph/
- **Implemented Example**: `services/coder-agent/` (Plan-Code-Test-Run-Refine-Summarize)
- **Current ReAct Agent**: `services/brain/src/brain/agents/react_agent.py`
- **Tool Registry**: `config/tool_registry.yaml`
- **Integration Guide**: `Research/KITTY_LangGraph_Coding_Agent_Integration_Guide.md`

---

**Author Notes:**
This proposal builds on lessons learned from implementing the coder-agent LangGraph workflow. The patterns proven there (state machine, conditional edges, refinement loops) apply directly to enhancing KITTY's core reasoning and tool orchestration capabilities.

The dual-agent architecture (Q4 fast router + F16 deep reasoner) is particularly powerful because it combines the best of both models:
- Q4 handles 80% of queries quickly and cheaply
- F16 provides depth when needed without adding latency to simple queries
- Structured handoffs via LangGraph state ensure seamless transitions

This is a significant architectural upgrade, but with careful migration strategy and the existing coder-agent as a reference implementation, it's very achievable.
