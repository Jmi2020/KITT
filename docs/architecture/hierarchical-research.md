# Hierarchical Research Architecture

## Overview

The hierarchical research system implements multi-stage query decomposition and synthesis for complex, multi-faceted research questions. This document provides a technical overview of the architecture, implementation, and design decisions.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                     Research Session Start                   │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
            ┌────────────────┐
            │   initialize   │
            └────────┬───────┘
                     │
                     ▼
            ┌────────────────┐
            │    decompose   │──────► LLM analyzes query
            │   (optional)   │        Creates 2-5 sub-questions
            └────────┬───────┘        Assigns priorities
                     │
                     ▼
            ┌────────────────┐
      ┌────►│select_strategy │
      │     └────────┬───────┘
      │              │
      │              │ Hierarchical: Select next sub-question by priority
      │              │ Flat: Use original query
      │              │
      │              ▼
      │     ┌────────────────┐
      │     │execute_iteration│──────► Execute 1-3 tasks
      │     └────────┬───────┘        Tag findings with sub_question_id
      │              │
      │              ▼
      │     ┌────────────────┐
      │     │    validate    │
      │     └────────┬───────┘
      │              │
      │              ▼
      │     ┌────────────────┐
      │     │ score_quality  │
      │     └────────┬───────┘
      │              │
      │              ▼
      │     ┌────────────────┐
      │     │check_stopping  │──────► Hierarchical: Check sub-question complete
      │     └────────┬───────┘        Flat: Standard stopping criteria
      │              │
      │              ├─── continue ──────┘
      │              │
      │              ├─── synthesize_sub_question ───┐
      │              │                                │
      │              │                                ▼
      │              │                   ┌──────────────────────┐
      │              │                   │synthesize_sub_question│
      │              │                   └──────────┬───────────┘
      │              │                              │
      │              │                              └────────────┘
      │              │
      │              └─── synthesize (all complete) ───┐
      │                                                 │
      │                                                 ▼
      │                                    ┌──────────────────┐
      │                                    │   synthesize     │
      │                                    │  (final/meta)    │
      │                                    └────────┬─────────┘
      │                                             │
      │                                             ▼
      │                                    ┌──────────────────┐
      └────────────────────────────────────│       END        │
                                           └──────────────────┘
```

## State Management

### ResearchState Extensions

```python
class ResearchConfig(TypedDict, total=False):
    # Hierarchical configuration
    enable_hierarchical: bool          # Opt-in flag
    min_sub_questions: int             # Min decomposition
    max_sub_questions: int             # Max decomposition
    sub_question_min_iterations: int   # Min per sub-question
    sub_question_max_iterations: int   # Max per sub-question

class ResearchState(TypedDict):
    # Hierarchical state
    sub_questions: List[Dict[str, Any]]              # Sub-question objects
    sub_question_findings: Dict[str, List[Dict]]     # Findings per sub-question
    sub_question_syntheses: Dict[str, str]           # Synthesis per sub-question
    current_sub_question_id: Optional[str]           # Currently researching
    hierarchical_synthesis: Optional[str]            # Final meta-synthesis
    decomposition_tree: Optional[Dict[str, Any]]     # Decomposition metadata
```

### Sub-Question Structure

```python
{
    "sub_question_id": "sq_001",
    "parent_question_id": None,  # For future nested decomposition
    "question_text": "What are the key features of X?",
    "depth_level": 0,            # 0 = top-level
    "priority": 0.8,             # 0.0-1.0 importance weight
    "rationale": "This addresses the core functionality aspect",
    "status": "pending",         # pending | researching | completed
    "iteration_count": 0,
    "findings": [],              # Sub-question specific findings
    "synthesis": None,           # Sub-question synthesis text
    "quality_score": 0.0,
    "created_at": "2025-11-17T..."
}
```

## Node Implementation

### 1. decompose_question

**Location**: `services/brain/src/brain/research/graph/nodes.py:87-270`

**Purpose**: LLM-based query decomposition

**Logic**:
```python
async def decompose_question(state: ResearchState) -> ResearchState:
    # Skip if not enabled
    if not state["config"].get("enable_hierarchical", False):
        return state

    # Build decomposition prompt
    prompt = f"""Analyze and decompose this question into {min}-{max} sub-questions:
    {state["query"]}

    Output JSON:
    {{
      "decomposition_strategy": "comparison | multi-faceted | ...",
      "sub_questions": [
        {{
          "question": "Sub-question text?",
          "priority": 0.9,
          "rationale": "Why this is important"
        }}
      ]
    }}
    """

    # Consult LLM (MEDIUM tier)
    response = await model_coordinator.consult(request)

    # Parse JSON, create sub-question objects
    # Fall back to flat mode on error
```

**Error Handling**:
- JSON parse failure → disable hierarchical mode
- LLM failure → disable hierarchical mode
- Sub-questions < min → warn, continue
- Sub-questions > max → truncate

### 2. select_strategy (Hierarchical)

**Location**: `services/brain/src/brain/research/graph/nodes.py:343-451`

**Purpose**: Select next sub-question and plan tasks

**Logic**:
```python
async def _select_strategy_hierarchical(state: ResearchState) -> ResearchState:
    current_sq_id = state.get("current_sub_question_id")

    if not current_sq_id:
        # Select highest-priority pending sub-question
        pending = [sq for sq in state["sub_questions"] if sq["status"] == "pending"]
        pending.sort(key=lambda x: x["priority"], reverse=True)
        next_sq = pending[0]
        state["current_sub_question_id"] = next_sq["sub_question_id"]
        next_sq["status"] = "researching"

    # Calculate iteration budget for this sub-question
    total_priority = sum(sq["priority"] for sq in state["sub_questions"])
    sq_budget = int((next_sq["priority"] / total_priority) * research_iterations)
    sq_budget = clamp(sq_budget, min_iterations, max_iterations)

    # Plan tasks using sub-question as query
    tasks = await strategy.plan(next_sq["question_text"], sq_context)

    # Tag all tasks with sub_question_id
    for task in tasks:
        task.context["sub_question_id"] = next_sq["sub_question_id"]
```

**Iteration Budget Allocation**:
```
Total budget = max_iterations
Reserved = 1 (decomp) + num_sub_questions (synth) + 1 (meta-synth)
Research budget = Total - Reserved

Per sub-question:
  weight = sub_question.priority / sum(all_priorities)
  allocation = int(weight * research_budget)
  clamped = clamp(allocation, min_sq_iterations, max_sq_iterations)
```

### 3. execute_iteration (Hierarchical)

**Location**: `services/brain/src/brain/research/graph/nodes.py:454-716`

**Purpose**: Execute tasks and associate findings with sub-questions

**Logic**:
```python
async def _execute_tasks_real(state, tasks, components):
    for task in tasks:
        # Get sub-question ID from task context
        sq_id = task.get("context", {}).get("sub_question_id")

        # Execute tool (web_search or research_deep)
        result = await tool_executor.execute(...)

        # Create finding
        finding = {
            "id": f"finding_{iteration}_{task_id}",
            "content": ...,
            "confidence": 0.70,
            "tool": "web_search"
        }

        # Tag with sub-question
        if sq_id:
            finding["sub_question_id"] = sq_id

        # Associate with sub-question
        if sq_id:
            state["sub_question_findings"][sq_id].append(finding)
            for sq in state["sub_questions"]:
                if sq["sub_question_id"] == sq_id:
                    sq["findings"].append(finding)
                    sq["iteration_count"] += 1

        # Also add to global findings
        state = add_finding(state, finding)
```

### 4. synthesize_sub_question

**Location**: `services/brain/src/brain/research/graph/nodes.py:942-1102`

**Purpose**: Create focused synthesis for current sub-question

**Logic**:
```python
async def synthesize_sub_question(state: ResearchState) -> ResearchState:
    sq_id = state.get("current_sub_question_id")
    sub_question = get_sub_question(state, sq_id)
    sq_findings = state["sub_question_findings"][sq_id]
    sq_sources = [s for s in state["sources"] if s.get("sub_question_id") == sq_id]

    prompt = f"""Synthesize findings for this sub-question:

    Sub-Question: {sub_question["question_text"]}
    Context: Part of answering "{state["query"]}"

    Findings: {findings_text}
    Sources: {sources_text}

    Provide focused answer with:
    - Direct answer
    - Supporting evidence
    - Source citations
    - Caveats
    - Confidence assessment
    """

    # Consult LLM (MEDIUM tier)
    response = await model_coordinator.consult(request)

    # Store synthesis
    sub_question["synthesis"] = response.result
    sub_question["status"] = "completed"
    state["sub_question_syntheses"][sq_id] = response.result

    # Clear current sub-question to move to next
    state["current_sub_question_id"] = None
```

### 5. check_stopping (Hierarchical)

**Location**: `services/brain/src/brain/research/graph/nodes.py:1253-1377`

**Purpose**: Determine if sub-question complete or all done

**Logic**:
```python
async def _check_stopping_hierarchical(state: ResearchState) -> ResearchState:
    # Global checks (budget, iterations)
    if state["current_iteration"] >= max_iterations:
        return StoppingDecision(should_stop=True, ...)

    # Sub-question completion check
    if current_sq_id:
        sq_iteration_count = sub_question["iteration_count"]
        sq_findings_count = len(sub_question["findings"])

        should_synthesize = (
            sq_iteration_count >= max_sq_iterations or
            (sq_iteration_count >= min_sq_iterations and sq_findings_count >= 2)
        )

        if should_synthesize:
            # Signal to synthesize, don't stop overall research
            return StoppingDecision(
                should_stop=False,
                explanation="Sub-question ready for synthesis"
            )

    # All sub-questions complete check
    all_completed = all(sq["status"] == "completed" for sq in state["sub_questions"])

    if all_completed:
        return StoppingDecision(
            should_stop=True,
            explanation="All sub-questions completed"
        )

    # Continue researching
    return StoppingDecision(should_stop=False)
```

### 6. synthesize_results (Hierarchical)

**Location**: `services/brain/src/brain/research/graph/nodes.py:1393-1529`

**Purpose**: Meta-synthesis integrating all sub-question answers

**Logic**:
```python
async def _synthesize_results_hierarchical(state: ResearchState) -> ResearchState:
    # Collect all sub-question syntheses
    sub_syntheses = [
        {
            "question": sq["question_text"],
            "synthesis": sq["synthesis"],
            "priority": sq["priority"],
            "findings_count": len(sq["findings"])
        }
        for sq in state["sub_questions"]
        if sq.get("synthesis")
    ]

    # Build meta-synthesis prompt
    prompt = f"""Synthesize final answer by integrating sub-question analyses:

    Original Question: {state["query"]}

    Sub-Question Analyses:
    {format_sub_syntheses(sub_syntheses)}

    Requirements:
    1. Directly answer the original question
    2. Integrate insights from all sub-questions
    3. Highlight agreements and contradictions
    4. Maintain logical flow
    5. Preserve evidence and sources
    """

    # Consult LLM (HIGH tier for final synthesis)
    response = await model_coordinator.consult(request)

    state["final_answer"] = response.result
    state["hierarchical_synthesis"] = response.result
```

## Graph Routing

### Conditional Edges

```python
def _should_continue(state: ResearchState) -> str:
    """Route based on stopping decision and hierarchical status"""

    # Safety: max iterations
    if current_iteration >= max_iterations:
        return "synthesize"

    # Hierarchical mode
    if is_hierarchical:
        current_sq_id = state.get("current_sub_question_id")

        # Check if sub-question ready for synthesis
        if current_sq_id and "ready for synthesis" in explanation:
            return "synthesize_sub_question"

        # Check if all sub-questions complete
        if should_stop and all_sub_questions_completed:
            return "synthesize"

        # Continue to next sub-question or iteration
        return "continue"

    # Flat mode
    return "synthesize" if should_stop else "continue"
```

### Graph Flow

1. **Flat Mode**: `initialize → decompose (skip) → select_strategy → ... → synthesize`
2. **Hierarchical Mode**: `initialize → decompose → select_strategy → execute → ... → synthesize_sub_question → select_strategy → ... → synthesize (meta)`

## Model Tier Usage

| Node | Tier | Cost | Rationale |
|------|------|------|-----------|
| `decompose_question` | MEDIUM | $0.01-0.05 | Balance quality/cost for decomposition |
| `synthesize_sub_question` | MEDIUM | $0.05-0.10 | Per-sub-question synthesis |
| `synthesize_results` (meta) | HIGH | $0.10-0.20 | Critical final synthesis |

**Cost Optimization**:
- Use `prefer_local: true` to use local models for MEDIUM tier
- Reserve external models (Claude, GPT-4) for HIGH tier meta-synthesis
- Total hierarchical cost: ~$0.50-2.00 vs $0.10-0.50 for flat

## Database Schema

### New Columns (Already Migrated)

```sql
-- research_sessions table
ALTER TABLE research_sessions ADD COLUMN final_synthesis TEXT;
ALTER TABLE research_sessions ADD COLUMN hierarchical_synthesis TEXT;

-- research_findings table (sources column already JSONB)
-- Findings.sources now stores full source objects:
[
  {
    "url": "https://...",
    "title": "Source Title",
    "snippet": "Content excerpt...",
    "relevance": 0.85,
    "tool": "web_search",
    "sub_question_id": "sq_001"  // For hierarchical mode
  }
]
```

## Testing Strategy

### Unit Tests

```python
# Test decomposition
async def test_decompose_question():
    state = create_initial_state(...)
    state["config"]["enable_hierarchical"] = True

    result = await decompose_question(state)

    assert len(result["sub_questions"]) >= 2
    assert len(result["sub_questions"]) <= 5
    assert all(0.0 <= sq["priority"] <= 1.0 for sq in result["sub_questions"])

# Test hierarchical strategy selection
async def test_select_strategy_hierarchical():
    state = create_state_with_sub_questions(...)

    result = await select_strategy(state)

    assert result["current_sub_question_id"] is not None
    tasks = result["strategy_context"]["current_tasks"]
    assert all(t["context"]["sub_question_id"] for t in tasks)

# Test finding association
async def test_execute_iteration_hierarchical():
    state = create_state_with_current_sub_question(...)

    result = await execute_iteration(state)

    sq_id = state["current_sub_question_id"]
    assert sq_id in result["sub_question_findings"]
    assert len(result["sub_question_findings"][sq_id]) > 0
```

### Integration Tests

```bash
# Test complete hierarchical flow
./tests/integration/test_hierarchical_research.sh

# Validates:
# - Query decomposition
# - Sub-question research
# - Per-sub-question synthesis
# - Meta-synthesis
# - Results persistence
```

### Smoke Tests

```bash
# Quick validation
curl -X POST http://localhost:8000/api/research/sessions \
  -d '{
    "query": "Compare React vs Vue.js",
    "config": {"enable_hierarchical": true, "max_iterations": 15}
  }'

# Check results
curl http://localhost:8000/api/research/sessions/{id}/results

# Should show:
# - 2-4 sub-questions
# - Findings per sub-question
# - Individual syntheses
# - Meta-synthesis
```

## Performance Characteristics

### Time Complexity

- **Flat Mode**: O(iterations)
- **Hierarchical Mode**: O(decomp + sub_questions × iterations_per_sq + syntheses)

### Space Complexity

- **Additional State**: O(sub_questions × findings_per_sq)
- **Per Sub-Question**: ~1-5 findings, ~3-10 sources
- **Total Overhead**: Minimal (~10-50KB extra per session)

### Scalability

- **Bottleneck**: Sequential sub-question processing
- **Future**: Parallel sub-question research (requires graph refactor)
- **Current**: 2-5 sub-questions × 2-5 iterations = 4-25 sub-iterations

## Future Enhancements

### 1. Nested Decomposition

Allow sub-questions to be further decomposed:

```
Q: "Analyze the economic, political, and social factors"
  ├─ Economic factors
  │   ├─ Microeconomic impacts
  │   └─ Macroeconomic implications
  ├─ Political factors
  │   ├─ Domestic policy effects
  │   └─ International relations
  └─ Social factors
      ├─ Cultural changes
      └─ Demographic shifts
```

### 2. Parallel Sub-Question Research

Research multiple sub-questions concurrently:
- Requires graph refactor for parallel execution
- Needs budget coordination across branches
- Faster completion for independent sub-questions

### 3. Interactive Decomposition

Allow user to:
- Review and edit LLM-generated sub-questions
- Add/remove sub-questions
- Adjust priorities
- Re-decompose if unsatisfactory

### 4. Custom Decomposition Strategies

User-defined strategies:
- Temporal decomposition (past, present, future)
- Spatial decomposition (regions, countries)
- Stakeholder decomposition (perspectives)
- Custom templates

### 5. Adaptive Iteration Allocation

Dynamic budget reallocation:
- Allocate more iterations to challenging sub-questions
- Reduce budget for quickly saturated sub-questions
- Real-time quality assessment

## Related Documentation

- [User Guide: Hierarchical Research](../user-guides/hierarchical-research.md)
- [Planning: Implementation Details](../../plans/hierarchical-research-architecture.md)
- [API: Research Endpoints](../api/research-api.md)
- [Development: Testing Guide](../development/testing.md)

## References

- LangGraph Documentation: https://langchain-ai.github.io/langgraph/
- RAGAS Metrics: https://docs.ragas.io/
- Research Pipeline: `services/brain/src/brain/research/`
