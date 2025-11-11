# LangGraph Routing Architecture

## Design Principles

### 1. llama.cpp-First Architecture

**Core Principle**: llama.cpp is **ALWAYS** the primary inference engine for KITTY. All routing decisions, tool orchestration, and reasoning workflows use local llama.cpp models as the default and preferred option.

**Rationale**:
- **Offline-first**: KITTY must function without internet connectivity
- **Low latency**: Local inference is 10-100x faster than API calls
- **Privacy**: Sensitive data never leaves the local network
- **Cost efficiency**: Zero per-request costs for local inference
- **Control**: Full control over model selection, prompts, and parameters

### 2. Multi-Server Q4/F16 Architecture

The `MultiServerLlamaCppClient` routes between two local llama.cpp servers:

- **Q4 Server (Port 8083)**: Fast tool orchestrator for 80% of queries
  - Model: Qwen2.5-72B-Instruct-Q4_K_M
  - Temperature: 0.1 (deterministic for tool calling)
  - Use case: Quick responses, tool selection, simple queries

- **F16 Server (Port 8082)**: Precision reasoning engine for 20% of queries
  - Model: Llama-3.3-70B-Instruct-F16
  - Temperature: 0.2 (slightly creative for nuanced reasoning)
  - Use case: Complex analysis, deep reasoning, ambiguous queries

**No cloud API is used for primary routing**. The F16 model provides the "second opinion" level of reasoning, not external APIs.

### 3. OpenAI-Compatible API (Optional, Future)

Future work may add an OpenAI-compatible API endpoint for:
- **Development debugging**: Compare local vs cloud responses
- **Quality assessment**: Benchmark local models against GPT-4/Claude
- **Fallback for unsupported features**: Vision tasks not yet supported by llama.cpp

**Critical constraints**:
- OpenAI API is **NEVER** the primary path
- It is **OPTIONAL** and disabled by default
- Use only for "second opinions" or explicit user requests
- Requires explicit feature flag: `ENABLE_OPENAI_SECOND_OPINION=true`

### 4. Graceful Degradation

If any component fails, the system degrades gracefully:

1. LangGraph routing fails → Fall back to traditional BrainRouter
2. Q4 server fails → Use F16 server for all queries
3. F16 server fails → Use Q4 server for all queries
4. Both llama.cpp servers fail → Return error (no silent cloud fallback)

## LangGraph Integration Flow

```
┌─────────────────────────────────────────────────────────────┐
│  BrainOrchestrator.generate_response()                      │
└───────────────────┬─────────────────────────────────────────┘
                    │
                    ▼
        ┌───────────────────────┐
        │ Feature Flag Check    │
        │ BRAIN_USE_LANGGRAPH   │
        └───────┬───────────────┘
                │
       ┌────────┴────────┐
       │                 │
       ▼                 ▼
   Enabled          Disabled
       │                 │
       │                 │
       ▼                 ▼
┌──────────────┐   ┌──────────────────┐
│ A/B Test     │   │ BrainRouter      │
│ conversation │   │ (Traditional)    │
│ hash % 100   │   └──────────────────┘
└──────┬───────┘
       │
    ┌──┴───┐
    │      │
    ▼      ▼
 Use     Skip
LangGraph
    │
    ▼
┌─────────────────────────────────────────────┐
│ LangGraphRoutingIntegration                 │
│  .route_with_langgraph()                    │
└─────────────────┬───────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────┐
│ RouterGraph.run()                           │
│  ├─ intake                                  │
│  ├─ memory_retrieval (Qdrant local)        │
│  ├─ complexity_analysis                     │
│  ├─ [tool_selection]                        │
│  ├─ [tool_execution via ToolMCPClient]     │
│  ├─ [validation]                            │
│  └─ response_generation (Q4/F16)           │
└─────────────────┬───────────────────────────┘
                  │
                  ▼
            RoutingResult
         (compatible format)
```

## Component Responsibilities

### LangGraphRoutingIntegration (`integration.py`)
- **Purpose**: Feature-flagged bridge between LangGraph and BrainOrchestrator
- **Responsibilities**:
  - Check `BRAIN_USE_LANGGRAPH` feature flag
  - Perform A/B testing via hash-based rollout percentage
  - Convert `RoutingRequest` → `RouterState` → `RoutingResult`
  - Graceful error handling with fallback to traditional router

### RouterGraph (`router_graph.py`)
- **Purpose**: LangGraph state machine for structured reasoning workflow
- **Responsibilities**:
  - 7-node workflow: intake → memory → complexity → tools → validation → response
  - Complexity analysis to determine Q4 vs F16 routing
  - Tool selection and execution orchestration
  - Refinement loops (max 2 iterations) for low-confidence results

### ComplexityAnalyzer (`complexity/analyzer.py`)
- **Purpose**: Score queries 0.0-1.0 to route between Q4 and F16
- **Responsibilities**:
  - 5-factor scoring: token_count, technical_density, multi_step, ambiguity, tool_count
  - Routing recommendations: <0.3 → Q4, 0.3-0.7 → Q4+F16 fallback, >0.7 → F16 direct
  - No external API calls; all heuristic-based

## Configuration

### Feature Flags (.env)

```bash
# Enable LangGraph routing (default: false)
BRAIN_USE_LANGGRAPH=false

# Gradual rollout percentage 0-100 (default: 0)
# Hash-based on conversation_id for consistent per-user experience
BRAIN_LANGGRAPH_ROLLOUT_PERCENT=0
```

### Multi-Server llama.cpp Configuration

```bash
# Q4 Tool Orchestrator
LLAMACPP_Q4_HOST=http://localhost:8083
LLAMACPP_Q4_ALIAS=kitty-q4
LLAMACPP_Q4_TEMPERATURE=0.1

# F16 Reasoning Engine
LLAMACPP_F16_HOST=http://localhost:8082
LLAMACPP_F16_ALIAS=kitty-f16
LLAMACPP_F16_TEMPERATURE=0.2
```

## Migration Path (Gradual Rollout)

### Phase 1: Internal Testing (Current)
- `BRAIN_USE_LANGGRAPH=false` (disabled by default)
- `BRAIN_LANGGRAPH_ROLLOUT_PERCENT=0`
- Manual enable for testing: `BRAIN_USE_LANGGRAPH=true`, `ROLLOUT_PERCENT=100`

### Phase 2: Canary Deployment (Week 2)
- `BRAIN_USE_LANGGRAPH=true`
- `BRAIN_LANGGRAPH_ROLLOUT_PERCENT=10` (10% of conversations)
- Monitor: latency, cost, confidence, errors

### Phase 3: Gradual Rollout (Week 3)
- Increase rollout: 10% → 25% → 50% → 75%
- Compare metrics: LangGraph vs traditional router
- Adjust based on results

### Phase 4: Full Deployment (Week 4)
- `BRAIN_LANGGRAPH_ROLLOUT_PERCENT=100`
- Deprecate traditional router path (keep as fallback)
- Document success metrics and lessons learned

## Success Metrics

### Performance
- **Token efficiency**: Q4 handles 80%+ of queries, F16 only when needed
- **Latency P95**: ≤1.5s for local Q4 queries, ≤3.0s for F16
- **Cost**: Zero per-request cost (all local inference)

### Quality
- **Confidence**: ≥0.85 for Q4 responses, ≥0.90 for F16 responses
- **Tool success rate**: ≥95% for tool execution via MCPClient
- **Escalation rate**: 15-20% Q4 → F16 escalations (indicates good routing)

### Reliability
- **Error rate**: <1% LangGraph failures
- **Fallback usage**: <5% fallback to traditional router
- **Availability**: 99.9% uptime for llama.cpp servers

## Testing Strategy

### Unit Tests
- `test_complexity_analyzer.py`: 5-factor scoring logic
- `test_integration.py`: Feature flag, A/B testing, state conversion
- `test_router_graph.py`: Node execution, conditional edges, state transitions

### Integration Tests
- End-to-end workflow with mock LLM responses
- Verify Q4/F16 routing based on complexity scores
- Test refinement loops and tool execution

### Load Tests
- 1000 concurrent requests with 50/50 Q4/F16 split
- Measure P50, P95, P99 latency
- Ensure no memory leaks in long-running conversations

## Future Enhancements (Phase 2+)

### Deep Reasoner Graph (`deep_reasoner_graph.py`)
- Multi-step chain-of-thought reasoning with F16
- Self-evaluation and confidence scoring
- Synthesis of Q4 attempts + memories + tool results

### Memory-Augmented Conversation (`memory_graph.py`)
- Adaptive memory search depth
- Automatic fact extraction from conversations
- Memory-guided query reformulation

### Tool Orchestration Graph (`tool_orchestration_graph.py`)
- Dependency resolution (CAD → analysis → fabrication)
- Parallel tool execution where safe
- Validation checkpoints and user intervention points

## References

- **Proposal**: `Research/KITTY_LangGraph_Multi_Agent_Enhancement.md`
- **Quick Reference**: `Research/KITTY_LangGraph_Architecture_Quick_Reference.md`
- **Coder Agent Example**: `services/coder-agent/` (successful LangGraph implementation)
- **Integration Guide**: `Research/KITTY_LangGraph_Coding_Agent_Integration_Guide.md`
