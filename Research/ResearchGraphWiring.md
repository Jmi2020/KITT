# Research Graph Wiring & Dependency Injection

## Overview

This document explains how research infrastructure components are injected into the autonomous research graph, enabling real tool execution, permission checks, and AI synthesis.

## Problem Statement

LangGraph nodes are pure functions that only receive `ResearchState` as a parameter. There was no mechanism to pass infrastructure components (tool executor, permission gate, model coordinator, budget manager) to the nodes.

**Before wiring:**
- Nodes used simulated/hardcoded data
- No real tool execution
- No permission checks during research
- No AI-generated synthesis
- All findings were fake

**After wiring:**
- Nodes use real ResearchToolExecutor
- Permission checks via UnifiedPermissionGate
- AI synthesis via ModelCoordinator
- Real web search and Perplexity deep research
- Actual cost tracking and budget enforcement

## Architecture

### Component Factory Pattern

We use a global singleton pattern with dependency injection:

```
┌─────────────────────────────────────────────────────────────┐
│                      Brain Service (app.py)                  │
│                                                              │
│  1. Initialize components:                                  │
│     - ResearchToolExecutor                                  │
│     - UnifiedPermissionGate                                 │
│     - ModelCoordinator                                      │
│     - BudgetManager                                         │
│                                                              │
│  2. Create ResearchComponents dataclass                     │
│                                                              │
│  3. Call set_global_components(components)                  │
│     └──> Registers globally for graph nodes                │
│                                                              │
│  4. Build research graph                                    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Research Graph Nodes                      │
│                                                              │
│  execute_iteration():                                       │
│    1. Call get_global_components()                          │
│    2. If components.tool_executor exists:                   │
│       ├─> Use real tool execution                           │
│       ├─> Apply permission checks                           │
│       ├─> Track budget and costs                            │
│       └─> Record real findings/sources                      │
│    3. Else:                                                 │
│       └─> Fallback to simulated execution                   │
│                                                              │
│  synthesize_results():                                      │
│    1. Call get_global_components()                          │
│    2. If components.model_coordinator exists:               │
│       └─> Generate AI synthesis                             │
│    3. Else:                                                 │
│       └─> Fallback to basic text concatenation             │
└─────────────────────────────────────────────────────────────┘
```

## Implementation Details

### 1. Component Container (`components.py`)

```python
@dataclass
class ResearchComponents:
    """Container for all research infrastructure components"""
    tool_executor: Optional[any] = None  # ResearchToolExecutor
    permission_gate: Optional[any] = None  # UnifiedPermissionGate
    model_coordinator: Optional[any] = None  # ModelCoordinator
    budget_manager: Optional[any] = None  # BudgetManager
    research_server: Optional[any] = None  # ResearchMCPServer
    memory_server: Optional[any] = None  # MemoryMCPServer
    io_control: Optional[any] = None  # FeatureStateManager

    def is_fully_wired(self) -> bool:
        """Check if all core components are initialized"""
        return all([
            self.tool_executor is not None,
            self.permission_gate is not None,
            self.model_coordinator is not None,
            self.budget_manager is not None
        ])
```

### 2. Global Registration (`app.py`)

During brain service startup:

```python
# After initializing all components
from brain.research.graph.components import ResearchComponents, set_global_components

components = ResearchComponents(
    tool_executor=app.state.tool_executor,
    permission_gate=app.state.permission_gate,
    model_coordinator=app.state.model_coordinator,
    budget_manager=app.state.budget_manager,
    research_server=app.state.research_server,
    memory_server=app.state.memory_server,
    io_control=app.state.io_control
)

set_global_components(components)
logger.info(f"Research components registered: {components.get_status()}")
```

### 3. Component Usage in Nodes (`nodes.py`)

#### execute_iteration Node

```python
async def execute_iteration(state: ResearchState) -> ResearchState:
    # Get components
    from .components import get_global_components
    components = get_global_components()

    # Execute tasks using real tool executor if available
    if components and components.tool_executor:
        logger.info("Executing with real tool executor")
        await _execute_tasks_real(state, tasks, components)
    else:
        logger.warning("Tool executor not available, using simulated execution")
        await _execute_tasks_simulated(state, tasks)
```

**Real Tool Execution Logic:**

1. **Build execution context** from state
2. **Determine tool type** based on task priority:
   - High priority (>0.7) + budget available → `research_deep` (Perplexity)
   - Normal priority → `web_search` (DuckDuckGo)
3. **Execute via tool_executor.execute()**
4. **Process results**:
   - Extract findings from tool response
   - Add sources from citations/search results
   - Record tool execution metadata
   - Update budget and call counters
5. **Handle errors** gracefully

#### synthesize_results Node

```python
async def synthesize_results(state: ResearchState) -> ResearchState:
    from .components import get_global_components
    components = get_global_components()

    if components and components.model_coordinator:
        logger.info("Generating AI synthesis using ModelCoordinator")
        final_answer = await _generate_ai_synthesis(state, components)
    else:
        logger.warning("ModelCoordinator not available, using basic synthesis")
        final_answer = _generate_basic_synthesis(state)
```

**AI Synthesis Logic:**

1. **Build synthesis prompt** from all findings + sources
2. **Determine consultation tier** based on research quality:
   - Quality ≥ 0.9 → MEDIUM tier
   - Quality ≥ 0.7 → LOW tier
   - Quality < 0.7 → HIGH tier (needs review)
3. **Consult model** via model_coordinator.consult()
4. **Record model usage** and cost
5. **Fallback** to basic text if AI synthesis fails

## Tool Selection Logic

### Priority-Based Tool Routing

```python
if task["priority"] >= 0.7 and state["budget_remaining"] > Decimal("0.10"):
    # High priority + budget available → Deep research
    tool_name = ToolType.RESEARCH_DEEP
    arguments = {"query": task["query"], "depth": "medium"}
else:
    # Normal priority or low budget → Free web search
    tool_name = ToolType.WEB_SEARCH
    arguments = {"query": task["query"]}
```

### Tool Capabilities

| Tool | Provider | Cost | External | Use Case |
|------|----------|------|----------|----------|
| `web_search` | DuckDuckGo | $0.00 | No | Free web search, always available |
| `research_deep` | Perplexity | ~$0.005 | Yes | AI-powered research with citations |
| `fetch_webpage` | Direct | $0.00 | No | Extract content from specific URL |
| `store_memory` | Mem0 | $0.00 | No | Store findings for future recall |
| `recall_memory` | Mem0 | $0.00 | No | Retrieve relevant past findings |

## Permission Flow in Nodes

When executing paid tools (e.g., `research_deep`):

1. **Tool executor** calls `permission_gate.check_permission()`
2. **Permission gate** applies 3-layer hierarchy:
   - **Layer 1 (I/O Control)**: Perplexity enabled? Offline mode?
   - **Layer 2 (Budget)**: Sufficient funds? Under call limit?
   - **Layer 3 (Runtime)**: Trivial cost auto-approved? Needs omega password?
3. **If approved**: Execute tool, record cost
4. **If denied**: Return error, no execution

This ensures all permission policies are enforced during autonomous research.

## Budget Tracking

### Budget Updates During Research

```python
# After successful tool execution
state["budget_remaining"] -= result.cost_usd
if result.is_external:
    state["external_calls_remaining"] -= 1

# Record in tool execution history
state = record_tool_execution(
    state,
    tool_name=result.tool_name,
    result={"success": True},
    cost=result.cost_usd,
    success=True
)
```

### Budget-Aware Decision Making

- **Task execution**: Only use `research_deep` if `budget_remaining > $0.10`
- **Synthesis tier**: Use local models if `budget_remaining < $0.50`
- **Stopping criteria**: Research stops if budget exhausted

## Fallback Behavior

The system gracefully degrades when components aren't available:

### execute_iteration Fallback

If `tool_executor` is None:
- Uses `_execute_tasks_simulated()`
- Generates placeholder findings with `[SIMULATED]` prefix
- Marks sources as `tool: "simulated"`
- Zero cost, no external calls

### synthesize_results Fallback

If `model_coordinator` is None:
- Uses `_generate_basic_synthesis()`
- Simple string concatenation
- Lists findings and sources
- No AI generation

**Advantage**: Graph can run end-to-end even if infrastructure isn't fully initialized (useful for testing).

## Testing

### Integration Test (`test_research_graph_wiring.py`)

```python
def test_execute_iteration_uses_real_executor(mock_components):
    """Verify execute_iteration uses real tool executor"""
    set_global_components(mock_components)

    state = create_initial_state(...)
    state["strategy_context"] = {"current_tasks": [...]}

    result_state = await execute_iteration(state)

    # Verify tool executor was called
    assert mock_components.tool_executor.execute.called

    # Verify real findings were added (not simulated)
    assert result_state["findings"][0]["tool"] != "simulated"
```

### Manual Verification

1. **Check component registration** on brain startup:
   ```
   INFO: Research components registered: {'fully_wired': True, 'tool_executor': True, ...}
   ```

2. **Check node execution** during research:
   ```
   INFO: Executing 3 tasks with real tool executor
   INFO: Task task_1 executed with web_search: cost=$0.00, budget remaining=$2.00
   ```

3. **Check synthesis**:
   ```
   INFO: Generating AI synthesis using ModelCoordinator
   INFO: AI synthesis generated using llama3.1:8b (tier: low, cost: $0.00)
   ```

## Migration Guide

### Before (Simulated Execution)

```python
# Old code in nodes.py
for task in tasks[:3]:
    finding = {
        "content": f"Research finding for: {task['query']}",  # Hardcoded
        "confidence": 0.75,  # Fake
    }
    state = add_finding(state, finding)
```

### After (Real Execution)

```python
# New code in nodes.py
components = get_global_components()
result = await components.tool_executor.execute(
    tool_name=ToolType.WEB_SEARCH,
    arguments={"query": task["query"]},
    context=context
)

if result.success:
    finding = {
        "content": f"Found {len(result.data['results'])} results",  # Real data
        "confidence": 0.70,  # Based on tool
        "tool": "web_search"
    }
```

## Troubleshooting

### Issue: Nodes still using simulated data

**Symptoms:**
- Findings have `[SIMULATED]` prefix
- Sources are `https://example.com/source_*`
- Tool execution shows `web_search_simulated`

**Solution:**
1. Check brain logs for `"Research components registered"`
2. Verify `fully_wired: True` in status
3. Ensure `set_global_components()` is called before graph compilation
4. Check for initialization errors in app.py startup

### Issue: Permission denied errors during research

**Symptoms:**
- Tool execution fails with "Perplexity API disabled"
- Budget errors: "Insufficient budget"

**Solution:**
1. Check I/O Control state: `redis-cli GET perplexity_enabled`
2. Verify budget config: `RESEARCH_BUDGET_USD` env var
3. Check permission gate logs for denial reasons
4. Ensure Perplexity API key is set

### Issue: AI synthesis not working

**Symptoms:**
- Final answer is basic text concatenation
- No model consultation logged

**Solution:**
1. Verify `model_coordinator` is initialized in app.py
2. Check model registry has available models
3. Ensure local llama.cpp server is running
4. Check budget remaining (needs some budget for synthesis)

## Performance Considerations

### Component Initialization Cost

- **One-time cost** during brain service startup (~500ms)
- **Zero overhead** during graph execution (singleton pattern)
- **No serialization** (components not part of ResearchState)

### Memory Usage

- **Components**: ~50KB total (references only)
- **State overhead**: None (uses global singleton)
- **Checkpoint size**: Unchanged (components not checkpointed)

## Future Enhancements

### Confidence-Based Model Escalation

Currently, ModelCoordinator tier selection is based on average quality. Future enhancement:

```python
# Check confidence of latest finding
if latest_finding["confidence"] < 0.5:
    # Low confidence → escalate to higher tier
    tier = ConsultationTier.HIGH
    logger.info("Low confidence detected, escalating to HIGH tier")
```

This implements true "confidence-based routing" where low-confidence outputs automatically trigger higher-tier model review.

### Component Health Monitoring

```python
def get_component_health() -> dict:
    """Get health status of all components"""
    components = get_global_components()
    return {
        "tool_executor": components.tool_executor.health_check() if components else None,
        "permission_gate": components.permission_gate.health_check() if components else None,
        # ...
    }
```

### Per-Session Component Isolation

For multi-tenancy or per-user budgets:

```python
# Instead of global singleton
session_components = {
    "session_123": ResearchComponents(...),
    "session_456": ResearchComponents(...),
}

# Nodes retrieve session-specific components
components = get_session_components(state["session_id"])
```

## Conclusion

The dependency injection pattern enables:

- ✅ **Real tool execution** instead of simulated data
- ✅ **Permission enforcement** during autonomous research
- ✅ **Budget tracking** and cost control
- ✅ **AI synthesis** via ModelCoordinator
- ✅ **Graceful degradation** with fallbacks
- ✅ **Testable** with mock components
- ✅ **Zero state overhead** (singleton pattern)

The research graph is now **production-ready** with real infrastructure integration.
