# Brain LangGraph Integration

## Overview

This directory contains LangGraph-based state machines for enhancing Brain's core reasoning and tool orchestration capabilities.

## Architecture

### Phase 1: Core Reasoning Enhancement (Current)
**Location:** `services/brain/src/brain/agents/graphs/`

Enhances Brain's conversational router with structured state machines:
- **router_graph.py**: Q4-based fast routing with tool orchestration
- **complexity/analyzer.py**: Query complexity scoring for intelligent model selection
- **states.py**: Shared TypedDict definitions for graph state

**Purpose:** Improve ALL queries through:
- Intelligent Q4/F16 model routing based on complexity
- Memory-augmented conversation loops
- Structured tool orchestration with validation
- Adaptive confidence-based escalation

### Phase 2: Domain-Specific Agents (Future)
**Location:** `services/agent-runtime/` (separate service)

Task-specific agent workflows per Work Order:
- **graph_coding.py**: Code generation with test-refine loop
- **graph_research.py**: Research workflows (offline)
- **graph_cad_assist.py**: CAD assistance workflows
- **graph_fabrication.py**: Fabrication planning

**Purpose:** Handle specialized tasks that Brain delegates to.

## How They Work Together

```
User Query
    ↓
router_graph.py (Brain - Phase 1)
    ├─ Complexity < 0.3 → Q4 direct response
    ├─ Complexity 0.3-0.7 → Q4 with F16 fallback
    ├─ Complexity > 0.7 → F16 direct
    └─ Requires specialized agent → Delegate to agent-runtime
                                        ↓
                                  agent-runtime service (Phase 2)
                                        ├─ coding mode
                                        ├─ research mode
                                        ├─ cad mode
                                        └─ fabrication mode
```

## Usage

### Enable LangGraph Routing (Phase 1)

```bash
# In .env
BRAIN_USE_LANGGRAPH=true
BRAIN_LANGGRAPH_ROLLOUT_PERCENT=100
```

### Query Flow Example

```python
# Simple query (Q4 direct)
"What's the status of Bamboo printer?"
→ Complexity: 0.15
→ router_graph uses Q4
→ Response: <200ms

# Medium complexity (Q4 with F16 fallback)
"Design a bracket and check if it fits Bamboo"
→ Complexity: 0.55
→ router_graph uses Q4
→ Confidence check
→ Escalates to F16 if needed

# Complex query (F16 direct)
"Plan a multi-step fabrication workflow with CAD generation and printer selection"
→ Complexity: 0.85
→ router_graph uses F16 directly
→ Deep reasoning + tool orchestration
```

## State Flow

```python
RouterState = {
    "query": "Design a bracket",
    "complexity_score": 0.55,
    "requires_tools": True,
    "selected_tools": ["coding.generate", "fabrication.analyze_model"],
    "tool_results": {...},
    "confidence": 0.82,
    "tier_used": RoutingTier.LOCAL,
    "response": "Generated parametric bracket..."
}
```

## Current Status

- [x] Phase 1: router_graph.py implemented
- [x] Complexity analyzer working
- [ ] Integration with BrainOrchestrator
- [ ] Unit tests
- [ ] Feature flag
- [ ] Phase 2: agent-runtime service (future)

## References

- **Proposal**: `Research/KITTY_LangGraph_Multi_Agent_Enhancement.md`
- **Quick Reference**: `Research/KITTY_LangGraph_Architecture_Quick_Reference.md`
- **Work Order**: See recent work order for agent-runtime service details
- **Reference Implementation**: `services/coder-agent/` (LangGraph example)
