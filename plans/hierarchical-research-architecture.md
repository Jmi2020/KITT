# Hierarchical Research Architecture Plan

## Document Information
- **Created**: 2025-11-17
- **Status**: Planning Phase
- **Implementation Phase**: 1/10 Complete (State Management)

---

## 1. Overview & Motivation

### Current Problem
The research system synthesizes findings at the end without breaking down complex questions into manageable parts. This leads to:
- Unfocused web searches that don't target specific aspects
- Generic synthesis that doesn't deeply analyze each component
- Difficulty answering multi-faceted questions comprehensively
- No iterative refinement at sub-component level

### Proposed Solution
**Hierarchical research with multi-stage synthesis**:
1. **Decompose** complex questions into 2-5 meaningful sub-questions using LLM
2. **Research** each sub-question independently with dedicated iteration budget
3. **Synthesize** findings for each sub-question into focused answers
4. **Meta-synthesize** all sub-answers into comprehensive final response

### Example Transformation

**Query**: "Three experts disagree on climate tipping points: Expert A cites 2030 deadline, Expert B cites 2050, Expert C says timelines are unknowable. Evaluate each position and explain which evidence is stronger and why."

**Current Flow** (Single-Stage):
```
Query → Research (15 iterations, unfocused) → Single synthesis
```

**New Flow** (Hierarchical):
```
Query
  ↓
Decompose into:
  1. What is Expert A's position and evidence? (priority: 0.9)
  2. What is Expert B's position and evidence? (priority: 0.9)
  3. What is Expert C's position and evidence? (priority: 0.9)
  4. What does scientific literature say? (priority: 1.0)
  ↓
Research each (3-4 iterations per sub-question):
  Sub-Q1: 3 findings → Synthesis: "Expert A argues..."
  Sub-Q2: 3 findings → Synthesis: "Expert B contends..."
  Sub-Q3: 3 findings → Synthesis: "Expert C claims..."
  Sub-Q4: 4 findings → Synthesis: "Literature shows..."
  ↓
Meta-synthesis: "Evaluating the three positions against the scientific literature, Expert B's 2050 timeline has stronger support because... However, Expert A's urgency is partially validated by... Expert C's skepticism highlights..."
```

---

## 2. Current System Analysis

### 2.1 Graph Structure

**File**: `services/brain/src/brain/research/graph/graph.py`

**Current Flow**:
```
initialize → select_strategy → execute_iteration → validate → score_quality → check_stopping
                                      ↑                                              ↓
                                      └──────────────[continue]────────────────────┘
                                                                    ↓
                                                              [synthesize] → END
```

**Nodes**:
1. `initialize_research`: Sets up session, strategy, budget, model coordinator
2. `select_strategy`: Plans tasks for iteration using strategy (breadth/depth/hybrid)
3. `execute_iteration`: Executes 1-3 tasks using tool executor
4. `validate_findings`: Validates schema and quality
5. `score_quality`: Computes RAGAS metrics, confidence, saturation, gaps
6. `check_stopping`: Evaluates stopping criteria (quality/budget/iterations/gaps)
7. `synthesize_results`: Creates final answer using ModelCoordinator

### 2.2 State Management

**File**: `services/brain/src/brain/research/graph/state.py`

**Current State**:
- Tracks findings, sources, quality metrics globally
- Single iteration counter for entire research
- Budget tracking at session level
- No sub-question awareness
- Single synthesis at end

### 2.3 Strategy System

**File**: `services/brain/src/brain/research/orchestration/strategies.py`

**Current Strategies**:
- **BreadthFirstStrategy**: Explores many topics shallowly
- **DepthFirstStrategy**: Deep dive into single topic
- **TaskDecompositionStrategy**: Simple heuristic decomposition (compare, "and", how/why)
- **HybridStrategy**: Combines approaches

**Limitation**: `TaskDecompositionStrategy` uses simple heuristics, not LLM-based intelligent decomposition

### 2.4 Gaps Identified

1. **No LLM-based query decomposition**: Current decomposition is heuristic-based
2. **No sub-question tracking**: State doesn't track parent-child relationships
3. **No per-subtask synthesis**: Synthesis only happens once at the end
4. **No hierarchical synthesis**: No mechanism for meta-synthesis
5. **Limited iteration control**: Can't allocate iterations per sub-question
6. **No sub-question quality assessment**: Can't evaluate if sub-question is sufficiently answered

---

## 3. Proposed Architecture

### 3.1 New State Fields

**File**: `services/brain/src/brain/research/graph/state.py`

#### 3.1.1 Configuration Options

```python
class ResearchConfig(TypedDict, total=False):
    # ... existing fields ...

    # Hierarchical decomposition
    enable_hierarchical: bool  # Default: False (opt-in)
    min_sub_questions: int  # Default: 2
    max_sub_questions: int  # Default: 5
    sub_question_min_iterations: int  # Default: 2
    sub_question_max_iterations: int  # Default: 5
```

**Defaults**:
```python
DEFAULT_RESEARCH_CONFIG: ResearchConfig = {
    # ... existing defaults ...
    "enable_hierarchical": False,  # Opt-in
    "min_sub_questions": 2,
    "max_sub_questions": 5,
    "sub_question_min_iterations": 2,
    "sub_question_max_iterations": 5,
}
```

#### 3.1.2 State Fields

```python
class ResearchState(TypedDict):
    # ... existing fields ...

    # Hierarchical decomposition
    sub_questions: List[Dict[str, Any]]  # List of sub-questions
    sub_question_findings: Dict[str, List[Dict]]  # Findings per sub-question
    sub_question_syntheses: Dict[str, str]  # Synthesis per sub-question
    current_sub_question_id: Optional[str]  # Currently researching
    hierarchical_synthesis: Optional[str]  # Final meta-synthesis
    decomposition_tree: Optional[Dict[str, Any]]  # Decomposition metadata
```

**Sub-question Structure**:
```python
{
    "sub_question_id": "sq_001",
    "parent_question_id": None,  # For nested decomposition (future)
    "question_text": "What are the key features of X?",
    "depth_level": 0,  # 0 = top-level
    "priority": 0.8,  # 0.0-1.0, higher = more important
    "rationale": "This addresses the core functionality aspect",
    "status": "pending",  # pending | researching | completed
    "iteration_count": 0,
    "findings": [],
    "synthesis": None,
    "quality_score": 0.0,
    "created_at": "2025-11-17T...",
}
```

**✅ Status**: Implemented in Phase 1

---

## 4. Implementation Phases

### Phase 1: State Management Enhancement ✅

**Status**: COMPLETED

**Files Modified**:
- `services/brain/src/brain/research/graph/state.py`

**Changes**:
1. Added hierarchical config options to `ResearchConfig`
2. Added hierarchical state fields to `ResearchState`
3. Updated `DEFAULT_RESEARCH_CONFIG` with hierarchical defaults
4. Updated `create_initial_state()` to initialize hierarchical fields

**Code Added**:
```python
# Configuration
enable_hierarchical: bool
min_sub_questions: int
max_sub_questions: int
sub_question_min_iterations: int
sub_question_max_iterations: int

# State
sub_questions: List[Dict[str, Any]]
sub_question_findings: Dict[str, List[Dict[str, Any]]]
sub_question_syntheses: Dict[str, str]
current_sub_question_id: Optional[str]
hierarchical_synthesis: Optional[str]
decomposition_tree: Optional[Dict[str, Any]]
```

---

### Phase 2: Question Decomposition Node

**Status**: PENDING

**Files to Modify**:
- `services/brain/src/brain/research/graph/nodes.py`

**Implementation**:

```python
async def decompose_question(state: ResearchState) -> ResearchState:
    """
    Decompose main question into hierarchical sub-questions using LLM.

    Uses ModelCoordinator (MEDIUM tier) to analyze query and create 2-5
    meaningful sub-questions that comprehensively cover all aspects.

    Args:
        state: Research state

    Returns:
        Updated state with sub_questions populated
    """
    from ..models.coordinator import ConsultationRequest, ConsultationTier
    import json

    # Skip if not enabled or already decomposed
    if not state["config"].get("enable_hierarchical", False):
        logger.info("Hierarchical mode disabled, skipping decomposition")
        return state

    if state.get("sub_questions"):
        logger.info("Question already decomposed, skipping")
        return state

    # Get components
    components = get_global_components()

    # Build decomposition prompt
    min_sq = state["config"]["min_sub_questions"]
    max_sq = state["config"]["max_sub_questions"]

    prompt = f"""Analyze the following research question and decompose it into {min_sq}-{max_sq} meaningful sub-questions.

**Main Question**: {state["query"]}

**Your Task**:
1. Identify the distinct aspects or components of this question
2. Create specific, researchable sub-questions that together comprehensively answer the main question
3. Assign priority (0.0-1.0) based on importance to answering the main question
4. Provide rationale for why each sub-question is important

**Requirements**:
- Each sub-question should be focused and independently researchable
- Sub-questions should not significantly overlap
- Cover all important aspects of the main question
- Prioritize sub-questions that are critical to the answer
- Aim for {min_sq}-{max_sq} sub-questions total

**Output Format** (JSON):
{{
  "decomposition_strategy": "comparison | multi-faceted | causal | temporal | evaluative | ...",
  "sub_questions": [
    {{
      "question": "Specific sub-question here?",
      "priority": 0.9,
      "rationale": "Why this sub-question is important"
    }},
    ...
  ]
}}

**Examples**:

Main: "Compare React vs Vue.js"
Strategy: comparison
Sub-questions:
1. What are React's key features and strengths? (priority: 0.9)
2. What are Vue.js's key features and strengths? (priority: 0.9)
3. What are the performance differences? (priority: 0.8)

Main: "Explain the causes, effects, and solutions to climate change"
Strategy: multi-faceted
Sub-questions:
1. What are the primary causes of climate change? (priority: 1.0)
2. What are the observable effects of climate change? (priority: 0.9)
3. What solutions have been proposed or implemented? (priority: 0.8)

Provide ONLY the JSON response, no additional text.
"""

    # Consult model
    request = ConsultationRequest(
        prompt=prompt,
        tier=ConsultationTier.MEDIUM,
        max_cost=Decimal("0.05"),
        prefer_local=state["config"]["prefer_local"],
        context={
            "task": "question_decomposition",
            "query": state["query"],
            "session_id": state["session_id"]
        }
    )

    logger.info(f"Decomposing question: {state['query']}")
    response = await components.model_coordinator.consult(request)

    if response.success:
        try:
            # Parse JSON response
            decomposition = json.loads(response.result)

            # Validate structure
            if "sub_questions" not in decomposition:
                raise ValueError("Missing 'sub_questions' in response")

            sub_questions_data = decomposition["sub_questions"]

            # Enforce limits
            if len(sub_questions_data) < min_sq:
                logger.warning(f"Only {len(sub_questions_data)} sub-questions generated, minimum is {min_sq}")
            if len(sub_questions_data) > max_sq:
                logger.warning(f"Truncating {len(sub_questions_data)} sub-questions to max {max_sq}")
                sub_questions_data = sub_questions_data[:max_sq]

            # Create sub-question objects
            sub_questions = []
            for i, sq_data in enumerate(sub_questions_data):
                sub_question = {
                    "sub_question_id": f"sq_{i+1:03d}",
                    "parent_question_id": None,
                    "question_text": sq_data["question"],
                    "depth_level": 0,
                    "priority": float(sq_data.get("priority", 0.5)),
                    "rationale": sq_data.get("rationale", ""),
                    "status": "pending",
                    "iteration_count": 0,
                    "findings": [],
                    "synthesis": None,
                    "quality_score": 0.0,
                    "created_at": datetime.now().isoformat()
                }
                sub_questions.append(sub_question)

            # Update state
            state["sub_questions"] = sub_questions
            state["decomposition_tree"] = {
                "strategy": decomposition.get("decomposition_strategy", "unknown"),
                "total_sub_questions": len(sub_questions),
                "created_at": datetime.now().isoformat()
            }

            logger.info(
                f"✅ Decomposed query into {len(sub_questions)} sub-questions "
                f"(strategy: {state['decomposition_tree']['strategy']})"
            )

            for sq in sub_questions:
                logger.info(f"  - [{sq['priority']:.2f}] {sq['question_text']}")

            # Record model usage
            state = record_model_call(
                state,
                model_id=response.model_used,
                cost=response.cost,
                latency_ms=response.latency_ms,
                success=True
            )

        except (json.JSONDecodeError, ValueError, KeyError) as e:
            logger.error(f"Failed to parse decomposition response: {e}")
            logger.error(f"Response was: {response.result[:500]}")
            # Fall back to non-hierarchical mode
            state["config"]["enable_hierarchical"] = False
    else:
        logger.error(f"Decomposition failed: {response.error}")
        # Fall back to non-hierarchical mode
        state["config"]["enable_hierarchical"] = False

    return state
```

**Integration Point**: Insert after `initialize` node, before `select_strategy`

**Error Handling**:
- If decomposition fails, disable hierarchical mode and continue with flat research
- If JSON parsing fails, log error and fall back
- If sub-questions < min, warn but continue
- If sub-questions > max, truncate

---

### Phase 3: Modified Strategy Selection

**Status**: PENDING

**Files to Modify**:
- `services/brain/src/brain/research/graph/nodes.py`

**Changes**:

```python
async def select_strategy(state: ResearchState) -> ResearchState:
    """Select strategy for current iteration, considering hierarchical mode."""

    # Check if we're in hierarchical mode
    if state.get("sub_questions") and state["config"].get("enable_hierarchical"):
        return await _select_strategy_hierarchical(state)
    else:
        # Original behavior for non-hierarchical mode
        return await _select_strategy_flat(state)


async def _select_strategy_flat(state: ResearchState) -> ResearchState:
    """Original flat strategy selection (existing code)."""
    # Move existing select_strategy logic here
    # ... (existing implementation)
    pass


async def _select_strategy_hierarchical(state: ResearchState) -> ResearchState:
    """
    Plan tasks for hierarchical research.

    Selects next sub-question to research and creates targeted tasks.
    """
    logger.info("Selecting strategy in hierarchical mode")

    # Get current sub-question
    current_sq_id = state.get("current_sub_question_id")

    if not current_sq_id:
        # Select next sub-question to research
        pending = [sq for sq in state["sub_questions"] if sq["status"] == "pending"]

        if not pending:
            # All sub-questions complete, proceed to final synthesis
            logger.info("All sub-questions completed")
            state["strategy_context"]["current_tasks"] = []
            return state

        # Sort by priority (highest first)
        pending.sort(key=lambda x: x["priority"], reverse=True)
        next_sq = pending[0]

        # Set as current
        state["current_sub_question_id"] = next_sq["sub_question_id"]
        next_sq["status"] = "researching"

        logger.info(
            f"Starting research on sub-question {next_sq['sub_question_id']}: "
            f"{next_sq['question_text']} (priority: {next_sq['priority']:.2f})"
        )
    else:
        # Continue with current sub-question
        next_sq = next(
            sq for sq in state["sub_questions"]
            if sq["sub_question_id"] == current_sq_id
        )
        logger.info(f"Continuing research on {current_sq_id}")

    # Calculate iteration budget for this sub-question
    total_iterations = state["config"]["max_iterations"]
    num_sub_questions = len(state["sub_questions"])

    # Reserve iterations for decomposition (1) and synthesis (1 per sq + 1 final)
    reserved = 1 + num_sub_questions + 1
    research_iterations = total_iterations - reserved

    # Divide fairly, weighted by priority
    total_priority = sum(sq["priority"] for sq in state["sub_questions"])
    sq_budget = int((next_sq["priority"] / total_priority) * research_iterations)
    sq_budget = max(
        state["config"]["sub_question_min_iterations"],
        min(sq_budget, state["config"]["sub_question_max_iterations"])
    )

    logger.info(f"Sub-question iteration budget: {sq_budget}")

    # Create strategy for this sub-question
    from ..orchestration.strategies import create_strategy, ResearchStrategy
    from ..orchestration.base import StrategyContext

    # Use breadth-first for most sub-questions
    strategy = create_strategy(ResearchStrategy.BREADTH_FIRST)

    # Build context specific to this sub-question
    sq_context = StrategyContext(
        session_id=state["session_id"],
        original_query=next_sq["question_text"],  # Use sub-question as query
        max_depth=state["config"]["max_depth"],
        max_breadth=state["config"]["max_breadth"],
        max_iterations=sq_budget,
        budget_remaining=float(state["budget_remaining"]),
        external_calls_remaining=state["external_calls_remaining"],
        nodes_explored=next_sq["iteration_count"],
        findings=next_sq["findings"],  # Sub-question specific findings
        sources=state["sources"]  # Global sources list
    )

    # Plan tasks for this sub-question
    tasks = await strategy.plan(next_sq["question_text"], sq_context)

    # Tag all tasks with sub-question ID
    for task in tasks:
        task.context["sub_question_id"] = next_sq["sub_question_id"]
        task.context["sub_question_text"] = next_sq["question_text"]

    # Store in strategy context
    state["strategy_context"]["current_tasks"] = [
        {
            "id": task.id,
            "tool": task.tool,
            "query": task.query,
            "priority": task.priority,
            "context": task.context
        }
        for task in tasks
    ]

    logger.info(f"Planned {len(tasks)} tasks for sub-question {next_sq['sub_question_id']}")

    return state
```

**Key Logic**:
1. Check if hierarchical mode is enabled and sub-questions exist
2. If current_sub_question_id is None, select highest-priority pending sub-question
3. Calculate iteration budget per sub-question (weighted by priority)
4. Create tasks targeting only the current sub-question
5. Tag all tasks with sub_question_id for tracking

---

### Phase 4: Finding Association

**Status**: PENDING

**Files to Modify**:
- `services/brain/src/brain/research/graph/nodes.py`

**Changes to `execute_iteration`**:

```python
async def execute_iteration(state: ResearchState) -> ResearchState:
    """Execute iteration, tracking sub-question associations."""

    state = increment_iteration(state)
    tasks = state["strategy_context"].get("current_tasks", [])

    logger.info(f"Executing iteration {state['current_iteration']} with {len(tasks)} tasks")

    # Execute tasks
    for task_dict in tasks:
        try:
            # Reconstruct task
            from ..orchestration.base import Task
            task = Task(
                id=task_dict["id"],
                tool=task_dict["tool"],
                query=task_dict["query"],
                priority=task_dict["priority"],
                context=task_dict.get("context", {})
            )

            # Execute task (existing logic)
            result = await execute_task(task, state)

            # Extract findings from result
            findings = result.get("findings", [])

            # Get sub-question ID from task context
            sq_id = task.context.get("sub_question_id")

            for finding in findings:
                # Tag finding with sub-question ID if hierarchical
                if sq_id:
                    finding["sub_question_id"] = sq_id

                    # Add to sub-question specific findings
                    if sq_id not in state.get("sub_question_findings", {}):
                        state["sub_question_findings"][sq_id] = []
                    state["sub_question_findings"][sq_id].append(finding)

                    # Update sub-question object
                    for sq in state["sub_questions"]:
                        if sq["sub_question_id"] == sq_id:
                            sq["findings"].append(finding)
                            sq["iteration_count"] += 1
                            logger.info(
                                f"Added finding to {sq_id}: {finding.get('content', '')[:100]}"
                            )
                            break

                # Also add to global findings
                state = add_finding(state, finding)

            # Add sources
            sources = result.get("sources", [])
            for source in sources:
                # Tag with sub-question if applicable
                if sq_id:
                    source["sub_question_id"] = sq_id
                state = add_source(state, source)

            # Record tool execution
            state = record_tool_execution(
                state,
                tool_name=task.tool,
                result=result,
                cost=result.get("cost", Decimal("0.0")),
                success=True
            )

        except Exception as e:
            logger.error(f"Task {task_dict['id']} failed: {e}")
            state = record_error(state, str(e), {"task_id": task_dict["id"]})

    return state
```

**Key Changes**:
1. Extract `sub_question_id` from task context
2. Associate findings with specific sub-question
3. Maintain both per-sub-question and global finding lists
4. Update sub-question iteration count
5. Tag sources with sub-question ID

---

### Phase 5: Sub-Question Synthesis Node

**Status**: PENDING

**Files to Modify**:
- `services/brain/src/brain/research/graph/nodes.py`

**New Node**:

```python
async def synthesize_sub_question(state: ResearchState) -> ResearchState:
    """
    Synthesize findings for the current sub-question.

    Creates a focused answer that addresses the sub-question specifically,
    which will later be integrated into the final meta-synthesis.

    Args:
        state: Research state

    Returns:
        Updated state with sub-question synthesis added
    """
    from ..models.coordinator import ConsultationRequest, ConsultationTier

    sq_id = state.get("current_sub_question_id")
    if not sq_id:
        logger.warning("No current sub-question to synthesize")
        return state

    # Get sub-question data
    sub_question = next(
        (sq for sq in state["sub_questions"] if sq["sub_question_id"] == sq_id),
        None
    )

    if not sub_question:
        logger.error(f"Sub-question {sq_id} not found")
        return state

    # Get findings for this sub-question
    sq_findings = state.get("sub_question_findings", {}).get(sq_id, [])

    if not sq_findings:
        logger.warning(f"No findings for sub-question {sq_id}, using empty synthesis")
        sub_question["synthesis"] = "No findings available for this sub-question."
        sub_question["status"] = "completed"
        state["current_sub_question_id"] = None
        return state

    # Build synthesis prompt
    findings_text = "\n\n".join([
        f"Finding {i+1} (confidence: {f.get('confidence', 0):.2f}):\n{f.get('content', '')}"
        for i, f in enumerate(sq_findings)
    ])

    # Get relevant sources (sources tagged with this sub-question)
    sq_sources = [s for s in state["sources"] if s.get("sub_question_id") == sq_id]
    sources_text = "\n\n".join([
        f"{i+1}. **{s.get('title', 'Untitled')}**\n"
        f"   URL: {s.get('url', 'N/A')}\n"
        + (f"   Content: {s.get('snippet', '')[:200]}\n" if s.get('snippet') else "")
        + (f"   Relevance: {s.get('relevance', 0):.2f}" if s.get('relevance') else "")
        for i, s in enumerate(sq_sources[:10])
    ])

    if not sources_text:
        sources_text = "No specific sources tagged for this sub-question"

    prompt = f"""Synthesize the research findings to answer this specific sub-question.

**Sub-Question**: {sub_question["question_text"]}

**Context**: This is part of answering the broader question: "{state["query"]}"

**Research Findings**:
{findings_text}

**Sources Consulted**:
{sources_text}

**Your Task**:
Provide a clear, focused answer to the sub-question based on the findings and sources.

**Requirements**:
1. Direct answer to the sub-question (not the main question)
2. Key supporting evidence from the findings
3. Reference specific sources where appropriate
4. Acknowledge important caveats or limitations
5. State your confidence level (high/medium/low) and reasoning
6. Keep it focused and concise (this will be integrated into a larger synthesis)

**Format**:
Structure your response clearly with:
- Direct answer statement
- Supporting evidence
- Source citations
- Caveats (if any)
- Confidence assessment
"""

    logger.info(f"Synthesizing sub-question {sq_id}: {sub_question['question_text']}")

    # Consult model (MEDIUM tier for sub-question synthesis)
    components = get_global_components()
    request = ConsultationRequest(
        prompt=prompt,
        tier=ConsultationTier.MEDIUM,
        max_cost=Decimal("0.10"),
        prefer_local=state["config"]["prefer_local"],
        context={
            "task": "sub_question_synthesis",
            "sub_question_id": sq_id,
            "sub_question": sub_question["question_text"],
            "findings_count": len(sq_findings)
        }
    )

    response = await components.model_coordinator.consult(request)

    if response.success:
        # Store synthesis
        synthesis = response.result
        sub_question["synthesis"] = synthesis
        sub_question["status"] = "completed"

        # Add to syntheses dict
        if "sub_question_syntheses" not in state:
            state["sub_question_syntheses"] = {}
        state["sub_question_syntheses"][sq_id] = synthesis

        logger.info(
            f"✅ Synthesized sub-question {sq_id} "
            f"({len(synthesis)} chars, model: {response.model_used})"
        )

        # Clear current sub-question to move to next
        state["current_sub_question_id"] = None

        # Record model usage
        state = record_model_call(
            state,
            model_id=response.model_used,
            cost=response.cost,
            latency_ms=response.latency_ms,
            success=True
        )
    else:
        logger.error(f"Sub-question synthesis failed: {response.error}")
        # Mark as completed anyway to avoid blocking
        sub_question["synthesis"] = f"Synthesis failed: {response.error}"
        sub_question["status"] = "completed"
        state["current_sub_question_id"] = None

    return state
```

**Integration Point**: Called conditionally from `check_stopping` when sub-question research is complete

---

### Phase 6: Enhanced Stopping Logic

**Status**: PENDING

**Files to Modify**:
- `services/brain/src/brain/research/graph/nodes.py`

**Changes to `check_stopping`**:

```python
async def check_stopping(state: ResearchState) -> ResearchState:
    """Check stopping criteria, considering hierarchical mode."""

    if state.get("sub_questions") and state["config"].get("enable_hierarchical"):
        return await _check_stopping_hierarchical(state)
    else:
        # Original flat stopping logic (existing code)
        return await _check_stopping_flat(state)


async def _check_stopping_flat(state: ResearchState) -> ResearchState:
    """Original flat stopping logic (existing code)."""
    # Move existing check_stopping logic here
    # ... (existing implementation)
    pass


async def _check_stopping_hierarchical(state: ResearchState) -> ResearchState:
    """
    Check stopping criteria in hierarchical mode.

    Determines:
    1. Should we stop researching current sub-question?
    2. Should we synthesize current sub-question?
    3. Should we proceed to final synthesis?
    """
    logger.info("Checking stopping criteria (hierarchical mode)")

    # Safety: Always stop if max iterations reached
    if state["current_iteration"] >= state["config"]["max_iterations"]:
        logger.warning("Max iterations reached, forcing final synthesis")
        state["stopping_decision"] = {
            "should_stop": True,
            "reasons": ["max_iterations_reached"],
            "confidence": 1.0,
            "action": "synthesize_final"
        }
        return state

    # Safety: Stop if budget exhausted
    if state["budget_remaining"] < Decimal("0.05"):
        logger.warning("Budget exhausted, forcing final synthesis")
        state["stopping_decision"] = {
            "should_stop": True,
            "reasons": ["budget_exhausted"],
            "confidence": 1.0,
            "action": "synthesize_final"
        }
        return state

    sq_id = state.get("current_sub_question_id")

    if not sq_id:
        # No current sub-question - check if all are complete
        all_complete = all(
            sq["status"] == "completed"
            for sq in state["sub_questions"]
        )

        if all_complete:
            # All sub-questions done, proceed to final synthesis
            logger.info("All sub-questions completed, proceeding to final synthesis")
            state["stopping_decision"] = {
                "should_stop": True,
                "reasons": ["all_sub_questions_complete"],
                "confidence": 1.0,
                "action": "synthesize_final"
            }
        else:
            # More sub-questions to research
            logger.info("Pending sub-questions remain, continuing")
            state["stopping_decision"] = {
                "should_stop": False,
                "reasons": ["more_sub_questions_pending"],
                "confidence": 1.0
            }

        return state

    # Check stopping criteria for current sub-question
    sub_question = next(
        sq for sq in state["sub_questions"]
        if sq["sub_question_id"] == sq_id
    )

    sq_findings = sub_question["findings"]
    sq_iterations = sub_question["iteration_count"]

    # Stopping criteria for sub-question
    should_stop_sq = False
    reasons = []

    # Criterion 1: Sufficient findings
    if len(sq_findings) >= 3:
        should_stop_sq = True
        reasons.append("sufficient_findings")

    # Criterion 2: Max iterations for this sub-question
    max_sq_iterations = state["config"]["sub_question_max_iterations"]
    if sq_iterations >= max_sq_iterations:
        should_stop_sq = True
        reasons.append("sub_question_max_iterations")

    # Criterion 3: Minimum iterations not met, keep going
    min_sq_iterations = state["config"]["sub_question_min_iterations"]
    if sq_iterations < min_sq_iterations:
        should_stop_sq = False
        reasons = ["min_iterations_not_met"]

    # Criterion 4: Check quality if we have findings
    if sq_findings:
        avg_confidence = sum(f.get("confidence", 0) for f in sq_findings) / len(sq_findings)
        if avg_confidence >= 0.7 and len(sq_findings) >= 2:
            should_stop_sq = True
            reasons.append("high_quality_findings")

    if should_stop_sq:
        logger.info(
            f"Sub-question {sq_id} complete: {', '.join(reasons)} "
            f"({len(sq_findings)} findings, {sq_iterations} iterations)"
        )
        state["stopping_decision"] = {
            "should_stop": True,
            "reasons": reasons,
            "confidence": 0.8,
            "action": "synthesize_sub_question"
        }
    else:
        logger.info(
            f"Sub-question {sq_id} continuing: {', '.join(reasons)} "
            f"({len(sq_findings)} findings, {sq_iterations} iterations)"
        )
        state["stopping_decision"] = {
            "should_stop": False,
            "reasons": reasons,
            "confidence": 0.8
        }

    return state
```

**Key Logic**:
1. If no current sub-question, check if all are complete → final synthesis
2. If current sub-question exists, check per-sub-question criteria:
   - 3+ findings OR
   - Max iterations per sub-question reached OR
   - High quality (avg confidence ≥ 0.7 with 2+ findings)
3. Set action: "synthesize_sub_question" or "synthesize_final"

---

### Phase 7: Meta-Synthesis

**Status**: PENDING

**Files to Modify**:
- `services/brain/src/brain/research/graph/nodes.py`

**Changes to `synthesize_results`**:

```python
async def synthesize_results(state: ResearchState) -> ResearchState:
    """Create final synthesis, using hierarchical approach if applicable."""

    if state.get("sub_questions") and state["config"].get("enable_hierarchical"):
        return await _synthesize_hierarchical(state)
    else:
        # Original flat synthesis (existing code)
        return await _synthesize_flat(state)


async def _synthesize_flat(state: ResearchState) -> ResearchState:
    """Original flat synthesis (existing code)."""
    # Move existing synthesize_results logic here
    # ... (existing implementation with source analysis from earlier)
    pass


async def _synthesize_hierarchical(state: ResearchState) -> ResearchState:
    """
    Create meta-synthesis from sub-question syntheses.

    Integrates all sub-question answers into a comprehensive,
    well-structured final response.

    Args:
        state: Research state

    Returns:
        Updated state with hierarchical_synthesis and final_answer
    """
    from ..models.coordinator import ConsultationRequest, ConsultationTier

    logger.info("Creating hierarchical meta-synthesis")

    components = get_global_components()

    # Gather all sub-question syntheses
    sub_syntheses = []
    for sq in state["sub_questions"]:
        if sq["synthesis"]:
            sub_syntheses.append({
                "sub_question_id": sq["sub_question_id"],
                "question": sq["question_text"],
                "priority": sq["priority"],
                "synthesis": sq["synthesis"],
                "findings_count": len(sq["findings"]),
                "iteration_count": sq["iteration_count"]
            })

    if not sub_syntheses:
        logger.error("No sub-question syntheses available for meta-synthesis")
        state["final_answer"] = "Research completed but no syntheses were generated."
        state = set_status(state, ResearchStatus.FAILED)
        return state

    # Sort by priority for display
    sub_syntheses.sort(key=lambda x: x["priority"], reverse=True)

    # Build meta-synthesis prompt
    syntheses_text = "\n\n---\n\n".join([
        f"**Sub-Question {i+1}** (Priority: {s['priority']:.2f}, {s['findings_count']} findings)\n\n"
        f"**Q**: {s['question']}\n\n"
        f"**A**: {s['synthesis']}"
        for i, s in enumerate(sub_syntheses)
    ])

    # Research metadata summary
    total_findings = len(state["findings"])
    total_sources = len(state["sources"])
    total_iterations = state["current_iteration"]

    prompt = f"""Create a comprehensive, well-structured answer by synthesizing the following sub-question analyses.

**Original Question**: {state["query"]}

**Research Summary**:
- Total iterations: {total_iterations}
- Total findings: {total_findings}
- Total sources: {total_sources}
- Sub-questions addressed: {len(sub_syntheses)}
- Decomposition strategy: {state.get('decomposition_tree', {}).get('strategy', 'unknown')}

**Sub-Question Analyses**:

{syntheses_text}

---

**Your Task**:
Create a comprehensive, unified answer to the original question that:

1. **Integrates all sub-question insights** into a cohesive narrative
2. **Structures the response clearly** with appropriate sections/headings based on sub-questions
3. **Identifies connections and cross-references** between sub-answers
4. **Synthesizes** rather than concatenates - show how the parts relate to the whole
5. **Provides an overall conclusion** that addresses the original question directly
6. **Acknowledges limitations** or areas needing further research if applicable

**Important**:
- This should read as a unified, professional response, NOT just a list of sub-answers
- Show how insights from different sub-questions complement or contrast with each other
- Address the original question comprehensively
- Use clear structure with headers/sections as appropriate
- Maintain academic/professional tone

Provide ONLY the comprehensive answer, no meta-commentary.
"""

    # Use HIGH tier for meta-synthesis (most important synthesis)
    request = ConsultationRequest(
        prompt=prompt,
        tier=ConsultationTier.HIGH,
        max_cost=state["budget_remaining"],
        prefer_local=state["config"]["prefer_local"],
        context={
            "task": "meta_synthesis",
            "query": state["query"],
            "sub_questions_count": len(state["sub_questions"]),
            "session_id": state["session_id"]
        }
    )

    response = await components.model_coordinator.consult(request)

    if response.success:
        meta_synthesis = response.result

        # Store in multiple places for compatibility
        state["hierarchical_synthesis"] = meta_synthesis
        state["final_answer"] = meta_synthesis

        # Create detailed synthesis metadata
        state["synthesis"] = {
            "query": state["query"],
            "approach": "hierarchical",
            "decomposition_strategy": state.get("decomposition_tree", {}).get("strategy", "unknown"),
            "sub_questions_count": len(state["sub_questions"]),
            "total_iterations": total_iterations,
            "total_findings": total_findings,
            "total_sources": total_sources,
            "sub_syntheses": [
                {
                    "question": s["question"],
                    "priority": s["priority"],
                    "findings_count": s["findings_count"],
                    "synthesis_length": len(s["synthesis"])
                }
                for s in sub_syntheses
            ],
            "meta_synthesis_length": len(meta_synthesis),
            "model_used": response.model_used,
            "synthesis_cost": float(response.cost)
        }

        logger.info(
            f"✅ Meta-synthesis complete: {len(meta_synthesis)} chars, "
            f"integrated {len(sub_syntheses)} sub-syntheses, "
            f"model: {response.model_used}"
        )

        # Record model usage
        state = record_model_call(
            state,
            model_id=response.model_used,
            cost=response.cost,
            latency_ms=response.latency_ms,
            success=True
        )

        state = set_status(state, ResearchStatus.COMPLETED)
    else:
        logger.error(f"Meta-synthesis failed: {response.error}")
        # Fall back to concatenating sub-syntheses
        fallback = "\n\n---\n\n".join([
            f"## {s['question']}\n\n{s['synthesis']}"
            for s in sub_syntheses
        ])
        state["final_answer"] = fallback
        state["hierarchical_synthesis"] = fallback
        state = set_status(state, ResearchStatus.FAILED)

    return state
```

**Key Features**:
1. Gathers all sub-question syntheses
2. Sorts by priority for logical flow
3. Uses HIGH tier model for best quality
4. Instructs LLM to integrate, not concatenate
5. Stores detailed metadata about decomposition and synthesis
6. Fallback to concatenation if meta-synthesis fails

---

### Phase 8: Graph Structure Update

**Status**: PENDING

**Files to Modify**:
- `services/brain/src/brain/research/graph/graph.py`

**Changes**:

```python
def _build_graph(self) -> StateGraph:
    """Build the research graph with hierarchical support."""

    graph = StateGraph(ResearchState)

    # Add nodes
    graph.add_node("initialize", initialize_research)
    graph.add_node("decompose_question", decompose_question)  # NEW
    graph.add_node("select_strategy", select_strategy)
    graph.add_node("execute_iteration", execute_iteration)
    graph.add_node("validate", validate_findings)
    graph.add_node("score_quality", score_quality)
    graph.add_node("check_stopping", check_stopping)
    graph.add_node("synthesize_sub_question", synthesize_sub_question)  # NEW
    graph.add_node("synthesize", synthesize_results)
    graph.add_node("handle_error", handle_error)

    # Define edges
    graph.set_entry_point("initialize")

    # NEW: Decomposition after initialization
    graph.add_edge("initialize", "decompose_question")
    graph.add_edge("decompose_question", "select_strategy")

    # Existing flow
    graph.add_edge("select_strategy", "execute_iteration")
    graph.add_edge("execute_iteration", "validate")
    graph.add_edge("validate", "score_quality")
    graph.add_edge("score_quality", "check_stopping")

    # Enhanced conditional routing from check_stopping
    graph.add_conditional_edges(
        "check_stopping",
        self._should_continue,
        {
            "continue": "select_strategy",           # Continue current sub-q or next sub-q
            "synthesize_sub_question": "synthesize_sub_question",  # NEW
            "synthesize": "synthesize",              # Final synthesis
            "error": "handle_error"
        }
    )

    # After sub-question synthesis, go back to select next sub-question
    graph.add_edge("synthesize_sub_question", "select_strategy")

    # Terminal nodes
    graph.add_edge("synthesize", END)
    graph.add_edge("handle_error", END)

    return graph


def _should_continue(self, state: ResearchState) -> str:
    """
    Enhanced conditional routing for hierarchical mode.

    Returns:
        - "continue": Keep researching (current or next sub-question)
        - "synthesize_sub_question": Synthesize current sub-question
        - "synthesize": Final meta-synthesis
        - "error": Error occurred
    """
    # Safety checks
    if state["current_iteration"] >= state["config"]["max_iterations"]:
        logger.warning("Max iterations reached, proceeding to final synthesis")
        return "synthesize"

    if state.get("last_error"):
        logger.error(f"Error detected: {state['last_error']}")
        return "error"

    stopping_decision = state.get("stopping_decision", {})

    if not stopping_decision:
        return "continue"

    # Check for explicit action from hierarchical stopping logic
    action = stopping_decision.get("action")

    if action == "synthesize_sub_question":
        return "synthesize_sub_question"
    elif action == "synthesize_final":
        return "synthesize"

    # Fallback to original logic
    if stopping_decision.get("should_stop"):
        return "synthesize"
    else:
        return "continue"
```

**Flow Diagram**:

```
                    initialize
                        ↓
                decompose_question (NEW)
                        ↓
                  select_strategy ←──────────────┐
                        ↓                         │
                 execute_iteration                │
                        ↓                         │
                     validate                     │
                        ↓                         │
                   score_quality                  │
                        ↓                         │
                  check_stopping                  │
                        ↓                         │
           ┌────────────┼────────────┐            │
           │            │            │            │
      [continue]  [synthesize_sq] [synthesize]   │
           │            │            │            │
           └────────────┤            │            │
                        ↓            │            │
              synthesize_sub_question (NEW)      │
                        │            │            │
                        └────────────┘            │
                                     ↓            │
                                 synthesize → END
```

---

### Phase 9: Template Configuration

**Status**: PENDING

**Files to Modify**:
- `services/brain/src/brain/research/templates.py`

**Changes**:

Add new hierarchical template:

```python
HIERARCHICAL_TEMPLATE = ResearchTemplate(
    name="hierarchical",
    description="Multi-stage hierarchical decomposition with per-part synthesis",
    config={
        "strategy": "hybrid",
        "max_iterations": 20,  # More iterations for multi-stage
        "max_depth": 3,
        "max_breadth": 8,
        "min_quality_score": 0.7,
        "min_confidence": 0.7,
        "min_ragas_score": 0.75,
        "saturation_threshold": 0.75,
        "min_novelty_rate": 0.15,
        "max_total_cost_usd": 3.0,  # Higher budget for decomposition + synthesis
        "max_external_calls": 15,
        "max_time_seconds": None,
        "prefer_local": True,
        "allow_external": True,
        "enable_debate": False,
        "require_critical_gaps_resolved": True,

        # Hierarchical settings
        "enable_hierarchical": True,
        "min_sub_questions": 2,
        "max_sub_questions": 4,
        "sub_question_min_iterations": 3,
        "sub_question_max_iterations": 6,
    },
    use_cases=[
        "Multi-faceted questions with distinct aspects",
        "Comparison questions (A vs B vs C)",
        "Questions requiring evaluation of multiple perspectives",
        "Complex analytical questions",
        "Questions with multiple dependent parts"
    ]
)

# Update TEMPLATES dict
TEMPLATES = {
    "quick_fact": QUICK_FACT_TEMPLATE,
    "general": GENERAL_TEMPLATE,
    "deep_dive": DEEP_DIVE_TEMPLATE,
    "technical_docs": TECHNICAL_DOCS_TEMPLATE,
    "comparison": COMPARISON_TEMPLATE,
    "troubleshooting": TROUBLESHOOTING_TEMPLATE,
    "product_research": PRODUCT_RESEARCH_TEMPLATE,
    "academic": ACADEMIC_TEMPLATE,
    "hierarchical": HIERARCHICAL_TEMPLATE,  # NEW
}
```

Update `apply_template()` to detect hierarchical queries:

```python
def apply_template(query: str, template_type: Optional[str] = None) -> ResearchConfig:
    """Apply template or auto-detect based on query."""

    if template_type:
        # ... existing logic
        pass
    else:
        # Auto-detection logic
        query_lower = query.lower()

        # Check for hierarchical patterns
        hierarchical_patterns = [
            r"compare .+ (and|vs|versus)",  # Compare A and B and C
            r"explain .+ and .+ and",  # Explain X and Y and Z
            r"evaluate .+ position",  # Evaluate multiple positions
            r"expert [a-z] .+ expert [a-z]",  # Multiple expert opinions
            r"what are .+ causes .+ effects .+ solutions",  # Multi-faceted
        ]

        for pattern in hierarchical_patterns:
            if re.search(pattern, query_lower):
                logger.info(f"Auto-detected hierarchical query: {pattern}")
                return TEMPLATES["hierarchical"].config.copy()

        # ... existing auto-detection logic
```

---

### Phase 10: Testing & Validation

**Status**: PENDING

**Test Queries**:

1. **Simple** (should NOT use hierarchical):
   ```
   "What is quantum computing?"
   → Expected: Flat research
   ```

2. **Comparison** (should use hierarchical):
   ```
   "Compare React, Vue, and Angular for building web applications"
   → Expected: 3-4 sub-questions (features, performance, ecosystem, use cases)
   ```

3. **Multi-faceted**:
   ```
   "Explain the causes, effects, and solutions to climate change"
   → Expected: 3 sub-questions (causes, effects, solutions)
   ```

4. **Evaluative** (original example):
   ```
   "Three experts disagree on climate tipping points: Expert A cites 2030 deadline,
    Expert B cites 2050, Expert C says timelines are unknowable. Evaluate each
    position and explain which evidence is stronger and why."
   → Expected: 4 sub-questions (3 expert positions + literature review)
   ```

5. **Complex analytical**:
   ```
   "How does machine learning work, what are its applications in healthcare,
    and what are the ethical concerns?"
   → Expected: 3 sub-questions (how it works, healthcare apps, ethics)
   ```

**Validation Checklist**:

- [ ] Decomposition produces 2-5 meaningful sub-questions
- [ ] Sub-questions cover all aspects of main question
- [ ] Priority weighting makes sense
- [ ] Each sub-question gets researched independently
- [ ] Findings are correctly associated with sub-questions
- [ ] Sub-question syntheses are focused and relevant
- [ ] Meta-synthesis integrates sub-answers coherently
- [ ] Budget is allocated fairly across sub-questions
- [ ] Iteration limits are respected per sub-question
- [ ] Final answer addresses original question comprehensively
- [ ] Quality is better than flat research for complex queries
- [ ] Flat research still works for simple queries

**Metrics to Track**:

- Decomposition quality (manual eval)
- Sub-question coverage (does it cover all aspects?)
- Synthesis coherence (sub-question and meta)
- Final answer quality vs flat baseline
- Cost efficiency ($/quality ratio)
- Iteration distribution across sub-questions

---

## 5. Budget & Iteration Management

### 5.1 Iteration Allocation

**Total iterations**: 20 (hierarchical template)

**Allocation**:
```
1 iteration: Initial decomposition
16 iterations: Research (distributed across 4 sub-questions = 4 each)
3 iterations: Synthesis (3 sub-questions synthesized in parallel with research)
1 iteration: Meta-synthesis
---
21 total (slight over, but check_stopping will enforce max)
```

**Per sub-question budget**:
```python
total_iterations = 20
num_sub_questions = 4
reserved = 1 (decomposition) + 1 (meta-synthesis)
research_budget = 20 - 2 = 18

# Distribute by priority weight
sub_q_1 (priority 1.0): 18 * (1.0 / 3.8) = 4.7 → 5 iterations
sub_q_2 (priority 0.9): 18 * (0.9 / 3.8) = 4.3 → 4 iterations
sub_q_3 (priority 0.9): 18 * (0.9 / 3.8) = 4.3 → 4 iterations
sub_q_4 (priority 1.0): 18 * (1.0 / 3.8) = 4.7 → 5 iterations
```

**Constraints**:
- `sub_question_min_iterations = 3` (minimum per sub-q)
- `sub_question_max_iterations = 6` (maximum per sub-q)

### 5.2 Cost Allocation

**Total budget**: $3.00 (hierarchical template)

**Allocation**:
```
$0.05: Decomposition (MEDIUM tier LLM)
$2.10: Research ($0.50 per sub-question × 4)
$0.40: Sub-question synthesis ($0.10 per sub-q × 4)
$0.15: Meta-synthesis (HIGH tier LLM)
$0.30: Buffer for quality scoring, gap detection, etc.
---
$3.00 total
```

**Reserve budget for synthesis**:
```python
decomposition_cost = Decimal("0.05")
per_sub_q_synthesis = Decimal("0.10")
meta_synthesis_cost = Decimal("0.15")

reserved_synthesis = (
    decomposition_cost +
    (num_sub_questions * per_sub_q_synthesis) +
    meta_synthesis_cost
)

research_budget = total_budget - reserved_synthesis
budget_per_sub_q = research_budget / num_sub_questions
```

---

## 6. Quality Management

### 6.1 Quality Gates

**Per Sub-Question**:
- Minimum findings: 2-3
- Minimum confidence: 0.6
- At least 2 sources
- Quality score: 0.6+

**Final Synthesis**:
- All sub-questions completed
- At least 70% have medium/high confidence
- No critical gaps in high-priority sub-questions

### 6.2 Gap Detection

Enhance gap detector for sub-questions:

```python
# In check_stopping_hierarchical
gap_detector = GapDetector()
gaps = await gap_detector.detect_gaps(
    query=sub_question["question_text"],
    findings=sq_findings,
    sources=state["sources"],
    context={"sub_question_id": sq_id}
)

critical_gaps = [g for g in gaps if g.priority == GapPriority.CRITICAL]

if critical_gaps and sq_iterations < max_iterations:
    # Don't stop yet, continue researching
    should_stop_sq = False
    reasons.append("critical_gaps_remain")
```

### 6.3 Synthesis Quality Evaluation

Future enhancement: Evaluate synthesis quality and re-generate if low

```python
synthesis_quality = await _evaluate_synthesis_quality(
    question=sub_question["question_text"],
    synthesis=response.result,
    findings=sq_findings
)

if synthesis_quality < 0.7 and state["budget_remaining"] > Decimal("0.10"):
    logger.info(f"Low synthesis quality ({synthesis_quality}), retrying")
    # Retry with more specific guidance
```

---

## 7. Rollout Plan

### Phase 1: Core Implementation ✅
- ✅ State management (completed)
- ⏳ Decomposition node
- ⏳ Modified strategy selection
- ⏳ Finding association
- ⏳ Sub-question synthesis
- ⏳ Enhanced stopping logic
- ⏳ Meta-synthesis
- ⏳ Graph routing

### Phase 2: Configuration & Testing
- Template configuration
- Auto-detection logic
- Test suite for hierarchical queries
- Comparison vs flat baseline

### Phase 3: Advanced Features (Future)
- Parallel sub-question execution
- Dynamic sub-question refinement
- Nested decomposition (sub-sub-questions)
- Synthesis quality retry logic
- Cross-sub-question knowledge transfer

---

## 8. Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Decomposition timing** | After initialization | Entire research uses hierarchical structure |
| **Decomposition method** | LLM-based (ModelCoordinator) | More intelligent than heuristics |
| **Sub-question execution** | Sequential, priority-ordered | Simpler, allows cross-pollination, easier budgeting |
| **Synthesis levels** | Per sub-q + meta-synthesis | Focused answers + coherent final |
| **State tracking** | Sub-q findings + global findings | Granular and aggregate views |
| **Iteration control** | Divided by priority | Fair resource allocation |
| **Opt-in vs default** | Opt-in via config flag | Backward compatibility |
| **Model tiers** | MEDIUM (decomp/sub-synthesis), HIGH (meta-synthesis) | Balance cost and quality |

---

## 9. Implementation Files Summary

| File | Changes | Status |
|------|---------|--------|
| `graph/state.py` | Add hierarchical state fields | ✅ Complete |
| `graph/nodes.py` | Add decompose_question, synthesize_sub_question; modify select_strategy, execute_iteration, check_stopping, synthesize_results | ⏳ Pending |
| `graph/graph.py` | Update graph structure with new nodes and routing | ⏳ Pending |
| `templates.py` | Add hierarchical template, auto-detection | ⏳ Pending |
| `orchestration/strategies.py` | Enhance for sub-question awareness (optional) | 🔮 Future |
| `metrics/knowledge_gaps.py` | Add sub-question gap detection (optional) | 🔮 Future |

---

## 10. Success Criteria

**Functional**:
- ✅ Decomposition produces meaningful sub-questions
- ✅ Each sub-question researched independently
- ✅ Sub-question syntheses are focused and relevant
- ✅ Meta-synthesis integrates sub-answers coherently
- ✅ Budget and iterations managed correctly
- ✅ Backward compatible (flat research still works)

**Quality**:
- Final answers are more comprehensive than flat research
- Better structure and organization
- Clearer attribution of evidence to sub-components
- Higher user satisfaction for complex queries

**Performance**:
- Similar or lower cost per query
- Comparable total iterations
- Reasonable execution time (< 5 minutes for most queries)

---

## 11. Future Enhancements

1. **Parallel Sub-Question Execution**
   - Research multiple sub-questions simultaneously
   - Requires complex state management
   - Significant performance improvement

2. **Dynamic Sub-Question Refinement**
   - Add new sub-questions mid-research if gaps detected
   - Split sub-questions if too broad
   - Merge sub-questions if overlapping

3. **Nested Decomposition**
   - Sub-questions can have sub-sub-questions
   - Tree structure of questions
   - Hierarchical synthesis at multiple levels

4. **Cross-Sub-Question Learning**
   - Findings from one sub-q inform research on others
   - Knowledge transfer between sub-questions
   - Dependency tracking

5. **Adaptive Iteration Allocation**
   - Dynamically adjust iteration budget based on sub-q complexity
   - Reallocate unused iterations from completed sub-qs

---

## Appendix A: Example Execution Trace

**Query**: "Three experts disagree on climate tipping points..."

```
[Iteration 0] initialize
  → Session created, budget set

[Iteration 1] decompose_question
  → LLM decomposes into:
    1. Expert A position (priority: 0.9)
    2. Expert B position (priority: 0.9)
    3. Expert C position (priority: 0.9)
    4. Scientific literature (priority: 1.0)

[Iteration 2-4] Research Sub-Q 4 (highest priority: 1.0)
  → select_strategy: Plan tasks for "What does scientific literature say?"
  → execute_iteration: Web search, gather findings
  → validate, score_quality, check_stopping

[Iteration 5] synthesize_sub_question (Sub-Q 4)
  → Synthesis: "Scientific literature shows consensus on accelerated warming..."

[Iteration 6-8] Research Sub-Q 1 (priority: 0.9)
  → Tasks for "What is Expert A's position?"
  → Findings gathered

[Iteration 9] synthesize_sub_question (Sub-Q 1)
  → Synthesis: "Expert A argues for 2030 deadline based on..."

[Iteration 10-12] Research Sub-Q 2
[Iteration 13] synthesize_sub_question (Sub-Q 2)

[Iteration 14-16] Research Sub-Q 3
[Iteration 17] synthesize_sub_question (Sub-Q 3)

[Iteration 18] check_stopping
  → All sub-questions complete, proceed to meta-synthesis

[Iteration 19] synthesize (meta-synthesis)
  → LLM integrates 4 sub-syntheses
  → Final answer: "Evaluating the three expert positions against
                  the scientific literature consensus..."

[Complete] Status: COMPLETED
```

**Result Structure**:
```json
{
  "final_answer": "Evaluating the three expert positions...",
  "hierarchical_synthesis": "Evaluating the three expert positions...",
  "synthesis": {
    "approach": "hierarchical",
    "sub_questions_count": 4,
    "total_iterations": 19,
    "sub_syntheses": [
      {
        "question": "What does scientific literature say?",
        "priority": 1.0,
        "synthesis_length": 1234
      },
      ...
    ]
  },
  "sub_questions": [
    {
      "sub_question_id": "sq_001",
      "question_text": "What is Expert A's position?",
      "status": "completed",
      "synthesis": "Expert A argues...",
      "findings": [...]
    },
    ...
  ]
}
```

---

**End of Plan**
