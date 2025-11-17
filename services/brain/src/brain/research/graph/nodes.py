"""
Research Graph Nodes

Each node represents a step in the autonomous research workflow.
"""

import logging
from typing import Dict, Any
from decimal import Decimal

from .state import (
    ResearchState,
    ResearchStatus,
    increment_iteration,
    set_status,
    record_error,
    add_finding,
    add_source,
    record_tool_execution,
    record_model_call,
)

# Import components from other phases
from ..orchestration import (
    create_strategy,
    ResearchStrategy,
    StrategyContext,
)
from ..models import (
    get_model_registry,
    ModelCoordinator,
    ModelCapability,
    ConsultationTier,
    ConsultationRequest,
    BudgetManager,
    BudgetConfig,
)
from ..validation import (
    create_research_output_pipeline,
)
from ..metrics import (
    RAGASEvaluator,
    ConfidenceScorer,
    SaturationDetector,
    GapDetector,
    StoppingCriteria,
)

logger = logging.getLogger(__name__)


async def initialize_research(state: ResearchState) -> ResearchState:
    """
    Initialize research session.

    Sets up:
    - Strategy
    - Budget manager
    - Model coordinator
    - Quality evaluators
    """
    logger.info(f"Initializing research for query: {state['query'][:100]}")

    try:
        # Set status
        state = set_status(state, ResearchStatus.ACTIVE)

        # Initialize strategy
        strategy_type = ResearchStrategy(state["strategy"])
        state["strategy_context"] = {
            "strategy_type": strategy_type.value,
            "initialized": True,
        }

        # Store initial metadata
        state["metadata"]["initialized_at"] = __import__("datetime").datetime.now().isoformat()

        logger.info("Research initialized successfully")

    except Exception as e:
        logger.error(f"Failed to initialize research: {e}")
        state = record_error(state, str(e), {"node": "initialize_research"})
        state = set_status(state, ResearchStatus.FAILED)

    return state


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
    import json
    from datetime import datetime

    # Skip if not enabled or already decomposed
    if not state["config"].get("enable_hierarchical", False):
        logger.info("Hierarchical mode disabled, skipping decomposition")
        return state

    if state.get("sub_questions"):
        logger.info("Question already decomposed, skipping")
        return state

    # Get components
    from .components import get_global_components
    components = get_global_components()

    if not components or not components.model_coordinator:
        logger.warning("Model coordinator not available, disabling hierarchical mode")
        state["config"]["enable_hierarchical"] = False
        return state

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
        task_description=prompt,
        required_capabilities={ModelCapability.REASONING, ModelCapability.CREATIVITY},
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

    try:
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

    except Exception as e:
        logger.error(f"Exception during decomposition: {e}", exc_info=True)
        state = record_error(state, str(e), {"node": "decompose_question"})
        # Fall back to non-hierarchical mode
        state["config"]["enable_hierarchical"] = False

    return state


async def select_strategy(state: ResearchState) -> ResearchState:
    """
    Select and configure research strategy for this iteration.

    Routes to hierarchical or flat strategy selection based on configuration.
    """
    # Check if we're in hierarchical mode
    if state.get("sub_questions") and state["config"].get("enable_hierarchical"):
        return await _select_strategy_hierarchical(state)
    else:
        return await _select_strategy_flat(state)


async def _select_strategy_flat(state: ResearchState) -> ResearchState:
    """
    Original flat strategy selection.

    Determines:
    - Which tools to use
    - Search parameters
    - Exploration vs exploitation
    """
    logger.info(f"Selecting strategy for iteration {state['current_iteration']} (flat mode)")

    try:
        # Get strategy
        strategy_type = ResearchStrategy(state["config"]["strategy"])
        strategy = create_strategy(strategy_type)

        # Build strategy context
        from ..orchestration.strategies import StrategyContext as OrchestrationType

        strategy_context = OrchestrationType(
            session_id=state["session_id"],
            original_query=state["query"],
            max_depth=state["config"]["max_depth"],
            max_breadth=state["config"]["max_breadth"],
            max_iterations=state["config"]["max_iterations"],
            min_sources=5,
            budget_remaining=float(state["budget_remaining"]),
            external_calls_remaining=state["external_calls_remaining"],
            base_priority=state["config"].get("base_priority"),  # Pass priority override if set
            nodes_explored=state["current_iteration"],
            findings=[f for f in state["findings"]],
            sources=set(s.get("url", "") for s in state["sources"])
        )

        # Plan next iteration
        tasks = await strategy.plan(state["query"], strategy_context)

        # Store tasks in state
        state["strategy_context"]["current_tasks"] = [
            {
                "task_id": t.task_id,
                "query": t.query,
                "priority": t.priority,
                "depth": t.depth,
            }
            for t in tasks
        ]

        logger.info(f"Planned {len(tasks)} tasks for iteration")

    except Exception as e:
        logger.error(f"Failed to select strategy: {e}")
        state = record_error(state, str(e), {"node": "select_strategy"})

    return state


async def _select_strategy_hierarchical(state: ResearchState) -> ResearchState:
    """
    Plan tasks for hierarchical research.

    Selects next sub-question to research and creates targeted tasks.
    """
    logger.info("Selecting strategy in hierarchical mode")

    try:
        # Get current sub-question
        current_sq_id = state.get("current_sub_question_id")

        if not current_sq_id:
            # Select next sub-question to research
            pending = [sq for sq in state["sub_questions"] if sq["status"] == "pending"]

            if not pending:
                # All sub-questions complete, proceed to final synthesis
                logger.info("All sub-questions completed, no tasks to plan")
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
        strategy_type = ResearchStrategy.BREADTH_FIRST  # Use breadth-first for most sub-questions
        strategy = create_strategy(strategy_type)

        # Build context specific to this sub-question
        from ..orchestration.strategies import StrategyContext as OrchestrationType

        sq_context = OrchestrationType(
            session_id=state["session_id"],
            original_query=next_sq["question_text"],  # Use sub-question as query
            max_depth=state["config"]["max_depth"],
            max_breadth=state["config"]["max_breadth"],
            max_iterations=sq_budget,
            min_sources=3,  # Fewer sources needed per sub-question
            budget_remaining=float(state["budget_remaining"]),
            external_calls_remaining=state["external_calls_remaining"],
            nodes_explored=next_sq["iteration_count"],
            findings=next_sq["findings"],  # Sub-question specific findings
            sources=set(s.get("url", "") for s in state["sources"] if s.get("sub_question_id") == next_sq["sub_question_id"])
        )

        # Plan tasks for this sub-question
        tasks = await strategy.plan(next_sq["question_text"], sq_context)

        # Tag all tasks with sub-question ID
        for task in tasks:
            task.context = task.context or {}
            task.context["sub_question_id"] = next_sq["sub_question_id"]
            task.context["sub_question_text"] = next_sq["question_text"]

        # Store in strategy context
        state["strategy_context"]["current_tasks"] = [
            {
                "task_id": task.task_id,
                "query": task.query,
                "priority": task.priority,
                "depth": task.depth,
                "context": task.context
            }
            for task in tasks
        ]

        logger.info(f"Planned {len(tasks)} tasks for sub-question {next_sq['sub_question_id']}")

    except Exception as e:
        logger.error(f"Failed to select hierarchical strategy: {e}", exc_info=True)
        state = record_error(state, str(e), {"node": "select_strategy_hierarchical"})

    return state


async def execute_iteration(state: ResearchState) -> ResearchState:
    """
    Execute one iteration of research.

    Performs:
    - Tool selection and execution
    - Model consultation
    - Result collection
    """
    logger.info(f"Executing iteration {state['current_iteration']}")

    try:
        # Increment iteration
        state = increment_iteration(state)

        # Get planned tasks from strategy
        tasks = state["strategy_context"].get("current_tasks", [])

        if not tasks:
            logger.warning(
                f"No tasks planned for iteration {state['current_iteration']}. "
                f"Strategy context: {state.get('strategy_context', {}).keys()}"
            )
            return state

        logger.info(
            f"Found {len(tasks)} tasks to execute: "
            f"{[t.get('query', 'unknown')[:50] for t in tasks[:3]]}"
        )

        # Get components for real tool execution
        from .components import get_global_components
        components = get_global_components()

        # Execute tasks using real tool executor if available
        if components and components.tool_executor:
            logger.info(
                f"Executing {len(tasks)} tasks with real tool executor "
                f"(type: {type(components.tool_executor).__name__})"
            )
            await _execute_tasks_real(state, tasks, components)
        else:
            logger.warning(
                f"Tool executor not available (components={components}), "
                f"using simulated execution"
            )
            await _execute_tasks_simulated(state, tasks)

        logger.info(
            f"Iteration {state['current_iteration']} executed: "
            f"{len(state['findings'])} total findings, "
            f"{len(state['sources'])} total sources, "
            f"{state.get('external_calls_used', 0)} external calls used"
        )

    except Exception as e:
        logger.error(f"Failed to execute iteration: {e}", exc_info=True)
        state = record_error(state, str(e), {"node": "execute_iteration"})

    return state


async def _execute_tasks_real(state: ResearchState, tasks: list, components):
    """
    Execute tasks using real ResearchToolExecutor.

    Args:
        state: Current research state
        tasks: List of tasks to execute
        components: ResearchComponents with tool_executor
    """
    from ..tools.mcp_integration import ToolExecutionContext, ToolType

    logger.info(f"Starting _execute_tasks_real with {len(tasks)} tasks")

    for idx, task in enumerate(tasks[:3]):  # Execute up to 3 tasks per iteration
        try:
            logger.info(
                f"Task {idx+1}/3: query='{task.get('query', 'unknown')[:100]}', "
                f"priority={task.get('priority', 0.0)}"
            )

            # Build execution context from state
            context = ToolExecutionContext(
                session_id=state["session_id"],
                user_id=state["user_id"],
                iteration=state["current_iteration"],
                budget_remaining=state["budget_remaining"],
                external_calls_remaining=state["external_calls_remaining"],
                perplexity_enabled=True,  # From I/O Control
                offline_mode=False,  # From I/O Control
                cloud_routing_enabled=True
            )

            # Determine tool type based on task priority and budget
            # High priority or deep research: use research_deep (paid)
            # Normal priority: use web_search (free)
            if task["priority"] >= 0.7 and state["budget_remaining"] > Decimal("0.10"):
                tool_name = ToolType.RESEARCH_DEEP
                arguments = {
                    "query": task["query"],
                    "depth": task.get("depth", "medium")
                }
            else:
                tool_name = ToolType.WEB_SEARCH
                arguments = {"query": task["query"]}

            logger.info(f"Executing tool: {tool_name} with args: {arguments}")

            # Execute tool
            try:
                result = await components.tool_executor.execute(
                    tool_name=tool_name,
                    arguments=arguments,
                    context=context
                )
                logger.info(f"✅ Tool execution completed: success={result.success}")
            except Exception as tool_exc:
                logger.error(f"❌ Tool execution FAILED: {tool_exc}", exc_info=True)
                raise

            # Process results
            logger.info(
                f"Tool execution result: success={result.success}, "
                f"data_keys={list(result.data.keys()) if hasattr(result, 'data') and result.data else 'none'}"
            )

            if result.success:
                # Get sub-question ID from task context (if hierarchical mode)
                sq_id = task.get("context", {}).get("sub_question_id")

                # Extract findings from tool result
                if tool_name == ToolType.RESEARCH_DEEP:
                    # Deep research returns comprehensive output
                    finding = {
                        "id": f"finding_{state['current_iteration']}_{task['task_id']}",
                        "content": result.data.get("research", ""),
                        "task_id": task["task_id"],
                        "iteration": state["current_iteration"],
                        "confidence": 0.85,  # Higher confidence for deep research
                        "tool": "research_deep",
                        "citations": result.data.get("citations", [])
                    }

                    # Tag with sub-question if hierarchical
                    if sq_id:
                        finding["sub_question_id"] = sq_id

                    # Add citations as sources
                    for citation_url in result.data.get("citations", []):
                        source = {
                            "url": citation_url,
                            "title": f"Citation from deep research",
                            "relevance": task["priority"],
                            "tool": "research_deep"
                        }
                        # Tag source with sub-question
                        if sq_id:
                            source["sub_question_id"] = sq_id
                        state = add_source(state, source)

                elif tool_name == ToolType.WEB_SEARCH:
                    # Web search returns multiple results
                    search_results = result.data.get("results", [])

                    logger.info(
                        f"WEB_SEARCH returned {len(search_results)} results, "
                        f"total_results={result.data.get('total_results')}, "
                        f"filtered_count={result.data.get('filtered_count')}"
                    )

                    if search_results:
                        # Create finding from top results
                        finding = {
                            "id": f"finding_{state['current_iteration']}_{task['task_id']}",
                            "content": f"Found {len(search_results)} results for: {task['query']}",
                            "task_id": task["task_id"],
                            "iteration": state["current_iteration"],
                            "confidence": 0.70,
                            "tool": "web_search",
                            "result_count": len(search_results)
                        }

                        # Tag with sub-question if hierarchical
                        if sq_id:
                            finding["sub_question_id"] = sq_id

                        # Add search results as sources
                        for search_result in search_results[:5]:  # Top 5 results
                            source = {
                                "url": search_result.get("url", ""),
                                "title": search_result.get("title", ""),
                                "snippet": search_result.get("description", ""),
                                "relevance": task["priority"],
                                "tool": "web_search"
                            }
                            # Tag source with sub-question
                            if sq_id:
                                source["sub_question_id"] = sq_id
                            state = add_source(state, source)
                            logger.info(f"Added source: {source.get('title', 'untitled')}")
                    else:
                        # No results found
                        finding = {
                            "id": f"finding_{state['current_iteration']}_{task['task_id']}",
                            "content": f"No results found for: {task['query']}",
                            "task_id": task["task_id"],
                            "iteration": state["current_iteration"],
                            "confidence": 0.0,
                            "tool": "web_search"
                        }

                        # Tag with sub-question if hierarchical
                        if sq_id:
                            finding["sub_question_id"] = sq_id

                # Extract topics and entities from finding content
                content_for_extraction = finding.get("content", "")

                # For web_search, also include top result snippets for richer extraction
                if tool_name == ToolType.WEB_SEARCH and 'result_count' in finding:
                    search_results = result.data.get("results", [])
                    snippets = [r.get("description", "") for r in search_results[:3]]
                    content_for_extraction = f"{content_for_extraction}\n\n{' '.join(snippets)}"

                extraction = await _extract_topics_from_content(
                    content=content_for_extraction,
                    query=state["query"],
                    components=components
                )

                # Add extracted topics/entities to finding
                finding["topics"] = extraction.get("topics", [])
                finding["entities"] = extraction.get("entities", [])
                finding["depth"] = task.get("depth", 0)  # Also add depth for strategy planning

                logger.info(
                    f"📝 Adding finding: {finding['id']}, content_length={len(finding.get('content', ''))}, "
                    f"topics={len(finding.get('topics', []))}, entities={len(finding.get('entities', []))}"
                )

                # Associate finding with sub-question if hierarchical
                if sq_id:
                    # Add to sub_question_findings dict
                    if "sub_question_findings" not in state:
                        state["sub_question_findings"] = {}
                    if sq_id not in state["sub_question_findings"]:
                        state["sub_question_findings"][sq_id] = []
                    state["sub_question_findings"][sq_id].append(finding)

                    # Update sub-question object
                    for sq in state.get("sub_questions", []):
                        if sq["sub_question_id"] == sq_id:
                            sq["findings"].append(finding)
                            sq["iteration_count"] += 1
                            logger.info(
                                f"Added finding to sub-question {sq_id}: {finding.get('content', '')[:100]}"
                            )
                            break

                # Also add to global findings
                state = add_finding(state, finding)
                logger.info(f"✅ Finding added! Total findings now: {len(state.get('findings', []))}")

                # Record tool execution success
                state = record_tool_execution(
                    state,
                    tool_name=result.tool_name,
                    result={"success": True},
                    cost=result.cost_usd,
                    success=True
                )

                # Update budget tracking
                state["budget_remaining"] -= result.cost_usd
                if result.is_external:
                    state["external_calls_remaining"] -= 1

                logger.info(
                    f"Task {task['task_id']} executed with {result.tool_name}: "
                    f"cost=${result.cost_usd}, budget remaining=${state['budget_remaining']}"
                )

            else:
                # Tool execution failed
                logger.warning(f"Task {task['task_id']} failed: {result.error}")
                state = record_tool_execution(
                    state,
                    tool_name=result.tool_name,
                    result={"error": result.error},
                    cost=Decimal("0.0"),
                    success=False
                )

        except Exception as e:
            logger.error(
                f"Error executing task {task.get('task_id')}: {e}",
                exc_info=True,
                extra={
                    "task_id": task.get("task_id"),
                    "query": task.get("query", "")[:100],
                    "iteration": state.get("current_iteration")
                }
            )
            state = record_error(state, str(e), {"node": "execute_iteration", "task": task})


async def _execute_tasks_simulated(state: ResearchState, tasks: list):
    """
    Execute tasks using simulated data (fallback).

    Args:
        state: Current research state
        tasks: List of tasks to execute
    """
    logger.info("Using simulated task execution (tool executor not available)")

    for task in tasks[:3]:  # Execute up to 3 tasks
        # Simulate finding
        finding = {
            "id": f"finding_{state['current_iteration']}_{task['task_id']}",
            "content": f"[SIMULATED] Research finding for: {task['query']}",
            "task_id": task["task_id"],
            "iteration": state["current_iteration"],
            "confidence": 0.75,
            "tool": "simulated"
        }

        state = add_finding(state, finding)

        # Simulate source
        source = {
            "url": f"https://example.com/source_{state['current_iteration']}",
            "title": f"Source for {task['query'][:50]}",
            "relevance": task["priority"],
            "tool": "simulated"
        }

        state = add_source(state, source)

        # Record tool execution
        state = record_tool_execution(
            state,
            tool_name="web_search_simulated",
            result={"findings": 1, "sources": 1},
            cost=Decimal("0.0"),  # Local execution
            success=True
        )


async def validate_findings(state: ResearchState) -> ResearchState:
    """
    Validate findings from iteration.

    Checks:
    - Schema validity
    - Format correctness
    - Quality metrics
    - Hallucination detection
    """
    logger.info("Validating findings")

    try:
        # Get validation pipeline
        pipeline = create_research_output_pipeline(
            min_completeness=state["config"]["min_quality_score"]
        )

        # Validate recent findings
        recent_findings = state["findings"][-5:]  # Last 5 findings

        validated_count = 0
        for finding in recent_findings:
            # Validate finding content
            result = await pipeline.validate(
                data=finding,
                context={
                    "query": state["query"],
                    "sources": state["sources"]
                }
            )

            if result.valid:
                validated_count += 1
            else:
                logger.warning(
                    f"Finding validation issues: {len(result.issues)} issues found"
                )

        logger.info(f"Validated {validated_count}/{len(recent_findings)} findings")

    except Exception as e:
        logger.error(f"Failed to validate findings: {e}")
        state = record_error(state, str(e), {"node": "validate_findings"})

    return state


async def score_quality(state: ResearchState) -> ResearchState:
    """
    Score quality of research findings.

    Computes:
    - RAGAS metrics
    - Confidence scores
    - Saturation status
    - Knowledge gaps
    """
    logger.info("Scoring research quality")

    try:
        # Initialize evaluators
        ragas_eval = RAGASEvaluator(use_full_ragas=True)
        confidence_scorer = ConfidenceScorer(
            min_confidence=state["config"]["min_confidence"]
        )
        saturation_detector = SaturationDetector(
            saturation_threshold=state["config"]["saturation_threshold"]
        )
        gap_detector = GapDetector()

        # Restore saturation detector state if exists
        if state.get("novelty_history"):
            saturation_detector.novelty_scores = state["novelty_history"]

        # Score recent findings
        if state["findings"]:
            # RAGAS evaluation (simplified for Phase 5)
            latest_finding = state["findings"][-1]
            ragas_result = await ragas_eval.evaluate(
                question=state["query"],
                answer=latest_finding.get("content", ""),
                contexts=[s.get("snippet", "") for s in state["sources"][-5:]]
            )

            state["ragas_results"].append(ragas_result.metrics.to_dict())

            # Confidence scoring
            confidence_result = await confidence_scorer.score_finding(
                finding=latest_finding,
                sources=state["sources"][-5:]
            )

            state["confidence_scores"].append(confidence_result.to_dict())

            # Overall quality score (average of RAGAS and confidence)
            quality_score = (ragas_result.metrics.average() + confidence_result.overall) / 2
            state["quality_scores"].append(quality_score)

            logger.info(
                f"Quality scores - RAGAS: {ragas_result.metrics.average():.2f}, "
                f"Confidence: {confidence_result.overall:.2f}, "
                f"Overall: {quality_score:.2f}"
            )

        # Saturation detection
        iteration_findings = [
            f for f in state["findings"]
            if f.get("iteration") == state["current_iteration"]
        ]

        saturation_status = saturation_detector.add_iteration_findings(iteration_findings)
        state["saturation_status"] = saturation_status.to_dict()
        state["novelty_history"] = saturation_detector.get_novelty_history()

        logger.info(
            f"Saturation: {saturation_status.saturation_score:.2f}, "
            f"Novelty rate: {saturation_status.novelty_rate:.2%}"
        )

        # Knowledge gap detection
        gaps = await gap_detector.detect_gaps(
            query=state["query"],
            findings=state["findings"],
            sources=state["sources"]
        )

        state["knowledge_gaps"] = [g.to_dict() for g in gaps]

        logger.info(f"Detected {len(gaps)} knowledge gaps")

    except Exception as e:
        logger.error(f"Failed to score quality: {e}")
        state = record_error(state, str(e), {"node": "score_quality"})

    return state


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

    # Get components
    from .components import get_global_components
    components = get_global_components()

    if not components or not components.model_coordinator:
        logger.error("Model coordinator not available")
        sub_question["synthesis"] = "Synthesis failed: Model coordinator not available"
        sub_question["status"] = "completed"
        state["current_sub_question_id"] = None
        return state

    # Consult model (MEDIUM tier for sub-question synthesis)
    request = ConsultationRequest(
        task_description=prompt,
        required_capabilities={ModelCapability.SYNTHESIS, ModelCapability.REASONING},
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

    try:
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

    except Exception as e:
        logger.error(f"Exception during sub-question synthesis: {e}", exc_info=True)
        state = record_error(state, str(e), {"node": "synthesize_sub_question", "sub_question_id": sq_id})
        sub_question["synthesis"] = f"Synthesis failed: {str(e)}"
        sub_question["status"] = "completed"
        state["current_sub_question_id"] = None

    return state


async def check_stopping(state: ResearchState) -> ResearchState:
    """
    Check if research should stop.

    Routes to hierarchical or flat stopping logic based on configuration.
    """
    # Check if we're in hierarchical mode
    if state.get("sub_questions") and state["config"].get("enable_hierarchical"):
        return await _check_stopping_hierarchical(state)
    else:
        return await _check_stopping_flat(state)


async def _check_stopping_flat(state: ResearchState) -> ResearchState:
    """
    Original flat stopping logic.

    Evaluates:
    - Iteration limits
    - Quality thresholds
    - Saturation levels
    - Budget constraints
    - Knowledge gaps
    """
    logger.info("Checking stopping criteria (flat mode)")

    try:
        # Initialize stopping criteria
        criteria = StoppingCriteria(
            min_quality_score=state["config"]["min_quality_score"],
            min_confidence=state["config"]["min_confidence"],
            min_ragas_score=state["config"]["min_ragas_score"],
            max_saturation=state["config"]["saturation_threshold"],
            min_novelty_rate=state["config"]["min_novelty_rate"],
            max_iterations=state["config"]["max_iterations"],
            max_time_seconds=state["config"].get("max_time_seconds"),
            require_critical_gaps_resolved=state["config"]["require_critical_gaps_resolved"]
        )

        # Parse saturation status
        from ..metrics.saturation import SaturationStatus
        saturation_dict = state.get("saturation_status", {})
        saturation_status = SaturationStatus(
            is_saturated=saturation_dict.get("is_saturated", False),
            novelty_rate=saturation_dict.get("novelty_rate", 1.0),
            iterations_checked=saturation_dict.get("iterations_checked", 0),
            findings_total=saturation_dict.get("findings_total", 0),
            findings_novel=saturation_dict.get("findings_novel", 0),
            repeated_findings=saturation_dict.get("repeated_findings", 0),
            saturation_score=saturation_dict.get("saturation_score", 0.0),
            explanation=saturation_dict.get("explanation", ""),
            recommendation=saturation_dict.get("recommendation", "")
        )

        # Parse confidence scores
        from ..metrics.confidence import ConfidenceScore, ConfidenceFactors
        confidence_objects = []
        for conf_dict in state["confidence_scores"]:
            factors_dict = conf_dict.get("factors", {})
            factors = ConfidenceFactors(
                source_quality=factors_dict.get("source_quality", 0.0),
                source_diversity=factors_dict.get("source_diversity", 0.0),
                claim_support=factors_dict.get("claim_support", 0.0),
                model_agreement=factors_dict.get("model_agreement", 0.0),
                citation_strength=factors_dict.get("citation_strength", 0.0),
                recency=factors_dict.get("recency", 0.0)
            )
            confidence_objects.append(
                ConfidenceScore(
                    overall=conf_dict.get("overall", 0.0),
                    factors=factors,
                    explanation=conf_dict.get("explanation", ""),
                    warnings=conf_dict.get("warnings", [])
                )
            )

        # Parse RAGAS results
        from ..metrics.ragas_metrics import RAGASMetrics
        ragas_objects = []
        for ragas_dict in state["ragas_results"]:
            ragas_objects.append(
                RAGASMetrics(
                    faithfulness=ragas_dict.get("faithfulness", 0.0),
                    answer_relevancy=ragas_dict.get("answer_relevancy", 0.0),
                    context_precision=ragas_dict.get("context_precision", 0.0),
                    context_recall=ragas_dict.get("context_recall", 0.0)
                )
            )

        # Parse knowledge gaps
        from ..metrics.knowledge_gaps import KnowledgeGap, GapType, GapPriority
        gap_objects = []
        for gap_dict in state["knowledge_gaps"]:
            gap_objects.append(
                KnowledgeGap(
                    gap_id=gap_dict.get("gap_id", ""),
                    gap_type=GapType(gap_dict.get("gap_type", "missing_context")),
                    priority=GapPriority(gap_dict.get("priority", "medium")),
                    description=gap_dict.get("description", ""),
                    suggested_action=gap_dict.get("suggested_action", ""),
                    related_findings=gap_dict.get("related_findings", []),
                    missing_topics=gap_dict.get("missing_topics", []),
                    confidence=gap_dict.get("confidence", 0.0),
                    resolved=gap_dict.get("resolved", False)
                )
            )

        # Make stopping decision
        decision = await criteria.should_stop(
            current_iteration=state["current_iteration"],
            start_time=state["start_time"],
            quality_scores=state["quality_scores"],
            confidence_scores=confidence_objects,
            ragas_results=ragas_objects,
            saturation_status=saturation_status,
            knowledge_gaps=gap_objects,
            budget_remaining=state["budget_remaining"],
            external_calls_remaining=state["external_calls_remaining"]
        )

        state["stopping_decision"] = decision.to_dict()

        logger.info(
            f"Stopping decision: should_stop={decision.should_stop}, "
            f"reasons={[r.value for r in decision.reasons]}, "
            f"confidence={decision.confidence:.2f}"
        )

    except Exception as e:
        logger.error(f"Failed to check stopping criteria: {e}")
        state = record_error(state, str(e), {"node": "check_stopping"})

        # CRITICAL: Always set a stopping_decision, even on error
        # This prevents infinite loops if check_stopping fails
        from ..metrics.stopping_criteria import StoppingDecision, StoppingReason
        state["stopping_decision"] = StoppingDecision(
            should_stop=True,
            reasons=[StoppingReason.ERROR],
            confidence=1.0,
            current_iteration=state.get("current_iteration", 0),
            explanation=f"Stopping due to error in check_stopping: {str(e)}"
        ).to_dict()

        logger.warning("Set emergency stopping decision due to error")

    return state


async def _check_stopping_hierarchical(state: ResearchState) -> ResearchState:
    """
    Check stopping criteria in hierarchical mode.

    Determines:
    1. Should we continue researching current sub-question?
    2. Should we synthesize current sub-question?
    3. Are all sub-questions complete?
    """
    logger.info("Checking stopping criteria (hierarchical mode)")

    try:
        from ..metrics.stopping_criteria import StoppingDecision, StoppingReason

        current_sq_id = state.get("current_sub_question_id")

        # Check global stopping criteria (budget, time, errors)
        if state["current_iteration"] >= state["config"]["max_iterations"]:
            logger.info("Max iterations reached")
            state["stopping_decision"] = StoppingDecision(
                should_stop=True,
                reasons=[StoppingReason.MAX_ITERATIONS],
                confidence=1.0,
                current_iteration=state["current_iteration"],
                explanation="Maximum iterations reached"
            ).to_dict()
            return state

        if state["budget_remaining"] <= Decimal("0.0"):
            logger.info("Budget exhausted")
            state["stopping_decision"] = StoppingDecision(
                should_stop=True,
                reasons=[StoppingReason.BUDGET_EXHAUSTED],
                confidence=1.0,
                current_iteration=state["current_iteration"],
                explanation="Research budget exhausted"
            ).to_dict()
            return state

        if state["external_calls_remaining"] <= 0:
            logger.info("External calls exhausted")
            state["stopping_decision"] = StoppingDecision(
                should_stop=True,
                reasons=[StoppingReason.BUDGET_EXHAUSTED],
                confidence=1.0,
                current_iteration=state["current_iteration"],
                explanation="External API calls exhausted"
            ).to_dict()
            return state

        # If we're currently researching a sub-question
        if current_sq_id:
            sub_question = next(
                (sq for sq in state["sub_questions"] if sq["sub_question_id"] == current_sq_id),
                None
            )

            if sub_question:
                sq_iteration_count = sub_question.get("iteration_count", 0)
                sq_findings_count = len(sub_question.get("findings", []))
                max_sq_iterations = state["config"]["sub_question_max_iterations"]
                min_sq_iterations = state["config"]["sub_question_min_iterations"]

                # Check if sub-question research is complete
                should_synthesize = False

                if sq_iteration_count >= max_sq_iterations:
                    logger.info(f"Sub-question {current_sq_id} reached max iterations ({max_sq_iterations})")
                    should_synthesize = True
                elif sq_iteration_count >= min_sq_iterations and sq_findings_count >= 2:
                    logger.info(f"Sub-question {current_sq_id} has sufficient findings ({sq_findings_count})")
                    should_synthesize = True

                if should_synthesize:
                    # Don't stop the overall research, but signal to synthesize this sub-question
                    state["stopping_decision"] = StoppingDecision(
                        should_stop=False,  # Continue to synthesis
                        reasons=[StoppingReason.QUALITY_THRESHOLD_MET],
                        confidence=0.8,
                        current_iteration=state["current_iteration"],
                        explanation=f"Sub-question {current_sq_id} ready for synthesis"
                    ).to_dict()
                    return state

        # Check if all sub-questions are completed
        all_completed = all(
            sq.get("status") == "completed"
            for sq in state.get("sub_questions", [])
        )

        if all_completed:
            logger.info("All sub-questions completed, ready for final synthesis")
            state["stopping_decision"] = StoppingDecision(
                should_stop=True,  # Stop iteration, move to final synthesis
                reasons=[StoppingReason.QUALITY_THRESHOLD_MET],
                confidence=1.0,
                current_iteration=state["current_iteration"],
                explanation="All sub-questions completed and synthesized"
            ).to_dict()
            return state

        # Continue researching
        state["stopping_decision"] = StoppingDecision(
            should_stop=False,
            reasons=[],
            confidence=0.5,
            current_iteration=state["current_iteration"],
            explanation="Continuing hierarchical research"
        ).to_dict()

    except Exception as e:
        logger.error(f"Failed to check hierarchical stopping criteria: {e}", exc_info=True)
        state = record_error(state, str(e), {"node": "check_stopping_hierarchical"})

        # Emergency stop on error
        from ..metrics.stopping_criteria import StoppingDecision, StoppingReason
        state["stopping_decision"] = StoppingDecision(
            should_stop=True,
            reasons=[StoppingReason.ERROR],
            confidence=1.0,
            current_iteration=state.get("current_iteration", 0),
            explanation=f"Stopping due to error: {str(e)}"
        ).to_dict()

    return state


async def synthesize_results(state: ResearchState) -> ResearchState:
    """
    Synthesize final research results.

    Routes to hierarchical or flat synthesis based on configuration.
    """
    # Check if we're in hierarchical mode
    if state.get("sub_questions") and state["config"].get("enable_hierarchical"):
        return await _synthesize_results_hierarchical(state)
    else:
        return await _synthesize_results_flat(state)


async def _synthesize_results_hierarchical(state: ResearchState) -> ResearchState:
    """
    Hierarchical meta-synthesis.

    Combines all sub-question syntheses into a comprehensive final answer.
    """
    logger.info("Synthesizing results (hierarchical mode)")

    try:
        # Get all sub-question syntheses
        sub_syntheses = []
        for sq in state.get("sub_questions", []):
            if sq.get("synthesis"):
                sub_syntheses.append({
                    "question": sq["question_text"],
                    "synthesis": sq["synthesis"],
                    "priority": sq.get("priority", 0.5),
                    "findings_count": len(sq.get("findings", []))
                })

        if not sub_syntheses:
            logger.warning("No sub-question syntheses available")
            state["final_answer"] = "No synthesis available - no sub-questions were completed."
            return state

        # Build meta-synthesis prompt
        sub_syntheses_text = "\n\n---\n\n".join([
            f"**Sub-Question {i+1}** (Priority: {s['priority']:.2f}, Findings: {s['findings_count']})\n"
            f"Q: {s['question']}\n\n"
            f"A: {s['synthesis']}"
            for i, s in enumerate(sub_syntheses)
        ])

        prompt = f"""You are synthesizing the final comprehensive answer to a research question by integrating answers from multiple sub-questions.

**Original Question**: {state["query"]}

**Sub-Question Analyses**:
{sub_syntheses_text}

**Your Task**:
Create a comprehensive, cohesive answer to the original question by synthesizing the sub-question answers above.

**Requirements**:
1. Directly answer the original question (not just summarize sub-answers)
2. Integrate insights from all sub-questions into a unified narrative
3. Highlight key points, agreements, and contradictions
4. Maintain logical flow and coherence
5. Preserve important evidence and source references from sub-answers
6. Be comprehensive but concise

**Format**:
Provide a well-structured answer with:
- Clear introduction addressing the main question
- Integrated analysis drawing from all sub-questions
- Key findings and conclusions
- Important caveats or limitations (if any)
"""

        # Get components
        from .components import get_global_components
        components = get_global_components()

        if not components or not components.model_coordinator:
            logger.error("Model coordinator not available for meta-synthesis")
            state["final_answer"] = "Meta-synthesis failed: Model coordinator unavailable"
            return state

        # Consult model (HIGH tier for final synthesis)
        request = ConsultationRequest(
            task_description=prompt,
            required_capabilities={ModelCapability.SYNTHESIS, ModelCapability.REASONING},
            tier=ConsultationTier.HIGH,
            max_cost=Decimal("0.20"),
            prefer_local=state["config"]["prefer_local"],
            context={
                "task": "hierarchical_meta_synthesis",
                "query": state["query"],
                "sub_questions_count": len(sub_syntheses)
            }
        )

        response = await components.model_coordinator.consult(request)

        if response.success:
            state["final_answer"] = response.result
            state["hierarchical_synthesis"] = response.result

            logger.info(
                f"✅ Meta-synthesis complete ({len(response.result)} chars, "
                f"model: {response.model_used})"
            )

            # Record model usage
            state = record_model_call(
                state,
                model_id=response.model_used,
                cost=response.cost,
                latency_ms=response.latency_ms,
                success=True
            )
        else:
            logger.error(f"Meta-synthesis failed: {response.error}")
            state["final_answer"] = f"Meta-synthesis failed: {response.error}"

        # Build hierarchical synthesis metadata
        state["synthesis"] = {
            "query": state["query"],
            "decomposition_strategy": state.get("decomposition_tree", {}).get("strategy", "unknown"),
            "total_sub_questions": len(state.get("sub_questions", [])),
            "sub_questions_completed": len([sq for sq in state.get("sub_questions", []) if sq.get("status") == "completed"]),
            "total_iterations": state["current_iteration"],
            "total_findings": len(state["findings"]),
            "total_sources": len(state["sources"]),
            "sub_question_details": [
                {
                    "question": sq["question_text"],
                    "priority": sq.get("priority", 0.5),
                    "findings_count": len(sq.get("findings", [])),
                    "iteration_count": sq.get("iteration_count", 0),
                    "status": sq.get("status", "unknown"),
                    "synthesis_length": len(sq.get("synthesis", ""))
                }
                for sq in state.get("sub_questions", [])
            ],
            "budget_usage": {
                "total_cost_usd": float(state["total_cost_usd"]),
                "external_calls_used": state["external_calls_used"],
                "models_used": state["models_used"]
            }
        }

    except Exception as e:
        logger.error(f"Failed to synthesize hierarchical results: {e}", exc_info=True)
        state = record_error(state, str(e), {"node": "synthesize_results_hierarchical"})
        state["final_answer"] = f"Synthesis failed: {str(e)}"

    return state


async def _synthesize_results_flat(state: ResearchState) -> ResearchState:
    """
    Original flat synthesis logic.

    Creates:
    - AI-generated final answer via ModelCoordinator
    - Summary of findings
    - Source attribution
    - Quality report
    """
    logger.info("Synthesizing research results (flat mode)")

    try:
        # Build synthesis metadata
        synthesis = {
            "query": state["query"],
            "total_iterations": state["current_iteration"],
            "total_findings": len(state["findings"]),
            "total_sources": len(state["sources"]),
            "findings_summary": [
                {
                    "content": f.get("content", "")[:200],
                    "confidence": f.get("confidence", 0.0)
                }
                for f in state["findings"][-10:]  # Last 10 findings
            ],
            "sources_used": [
                {
                    "url": s.get("url", ""),
                    "title": s.get("title", "")
                }
                for s in state["sources"][-20:]  # Last 20 sources
            ],
            "quality_metrics": {
                "average_quality": sum(state["quality_scores"]) / len(state["quality_scores"]) if state["quality_scores"] else 0.0,
                "average_confidence": sum(c["overall"] for c in state["confidence_scores"]) / len(state["confidence_scores"]) if state["confidence_scores"] else 0.0,
                "final_saturation": state["saturation_status"].get("saturation_score", 0.0) if state["saturation_status"] else 0.0,
            },
            "budget_usage": {
                "total_cost_usd": float(state["total_cost_usd"]),
                "external_calls_used": state["external_calls_used"],
                "models_used": state["models_used"]
            },
            "knowledge_gaps": state["knowledge_gaps"],
        }

        # Generate AI synthesis using ModelCoordinator
        from .components import get_global_components
        components = get_global_components()

        if components and components.model_coordinator:
            logger.info("Generating AI synthesis using ModelCoordinator")
            final_answer = await _generate_ai_synthesis(state, components)
        else:
            logger.warning("ModelCoordinator not available, using basic synthesis")
            final_answer = _generate_basic_synthesis(state)

        state["final_answer"] = final_answer
        state["synthesis"] = synthesis

        # Mark as completed
        state = set_status(state, ResearchStatus.COMPLETED)

        logger.info("Research synthesis complete")

    except Exception as e:
        logger.error(f"Failed to synthesize results: {e}")
        state = record_error(state, str(e), {"node": "synthesize_results"})
        state = set_status(state, ResearchStatus.FAILED)

    return state


async def _extract_topics_from_content(content: str, query: str, components) -> Dict[str, Any]:
    """
    Extract topics and entities from finding content using LLM.

    Args:
        content: Finding content to analyze
        query: Original research query for context
        components: ResearchComponents with model_coordinator

    Returns:
        Dict with "topics" and "entities" lists
    """
    from ..models.coordinator import ConsultationRequest, ConsultationTier
    import json

    # Skip extraction if no model coordinator or content too short
    if not components or not components.model_coordinator:
        return {"topics": [], "entities": []}

    if len(content.strip()) < 20:
        return {"topics": [], "entities": []}

    try:
        # Construct extraction prompt
        prompt = f"""Extract key topics and named entities from the following research finding.

Original Query: {query}

Finding Content:
{content[:800]}

Please respond with ONLY a JSON object in this exact format:
{{
  "topics": ["topic1", "topic2", "topic3"],
  "entities": ["entity1", "entity2"]
}}

Topics: 3-5 key concepts, themes, or subject areas mentioned
Entities: Specific names (people, places, organizations, products, technologies)

Keep items concise (2-4 words max). Return ONLY the JSON, no other text."""

        # Create consultation request (LOW tier for quick extraction)
        request = ConsultationRequest(
            task_description=prompt,
            required_capabilities={ModelCapability.EXTRACTION},
            tier=ConsultationTier.LOW,
            max_cost=Decimal("0.01"),  # Very cheap extraction
            prefer_local=True,  # Prefer local models for speed
            context={
                "query": query,
                "task": "topic_extraction"
            }
        )

        # Consult model
        response = await components.model_coordinator.consult(request)

        if response.success and response.result:
            # Parse JSON response
            try:
                result_text = response.result.strip()
                # Remove markdown code blocks if present
                if result_text.startswith("```"):
                    result_text = result_text.split("```")[1]
                    if result_text.startswith("json"):
                        result_text = result_text[4:]

                extracted = json.loads(result_text)

                # Validate structure
                topics = extracted.get("topics", [])[:5]  # Max 5 topics
                entities = extracted.get("entities", [])[:5]  # Max 5 entities

                logger.info(f"Extracted {len(topics)} topics and {len(entities)} entities from content")
                return {"topics": topics, "entities": entities}

            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse topic extraction JSON: {e}")
                return {"topics": [], "entities": []}
        else:
            logger.warning("Topic extraction failed or returned no result")
            return {"topics": [], "entities": []}

    except Exception as e:
        logger.error(f"Error in topic extraction: {e}", exc_info=True)
        return {"topics": [], "entities": []}


async def _generate_ai_synthesis(state: ResearchState, components) -> str:
    """
    Generate AI synthesis using ModelCoordinator.

    Args:
        state: Research state with findings
        components: ResearchComponents with model_coordinator

    Returns:
        AI-generated synthesis
    """
    from ..models.coordinator import ConsultationRequest, ConsultationTier

    try:
        # Build context from findings and sources
        findings_text = "\n\n".join([
            f"Finding {i+1} (confidence: {f.get('confidence', 0):.2f}):\n{f.get('content', '')}"
            for i, f in enumerate(state["findings"])
        ])

        # Format sources with snippets and relevance for LLM analysis
        sources_with_content = []
        for i, s in enumerate(state["sources"][:20], 1):  # Top 20 sources
            source_entry = f"{i}. **{s.get('title', 'Untitled')}**"
            source_entry += f"\n   URL: {s.get('url', 'N/A')}"
            if s.get('snippet'):
                source_entry += f"\n   Content: {s.get('snippet')[:300]}"  # Limit snippet length
            if s.get('relevance'):
                source_entry += f"\n   Relevance: {s.get('relevance'):.2f}"
            source_entry += f"\n   Tool: {s.get('tool', 'unknown')}"
            sources_with_content.append(source_entry)

        sources_text = "\n\n".join(sources_with_content) if sources_with_content else "No sources available"

        # Construct synthesis prompt
        prompt = f"""Synthesize the following research findings into a comprehensive, well-structured answer.

Original Query: {state["query"]}

Research Findings:
{findings_text}

Sources Consulted (with content excerpts):
{sources_text}

IMPORTANT: Analyze the actual source content provided above. Reference specific information, quotes, and evidence from the source snippets when constructing your synthesis. Evaluate source quality, relevance, and consistency.

Please provide:
1. A direct answer to the query based on source analysis
2. Key insights with specific evidence from sources (cite by title or URL)
3. Analysis of source quality and consistency
4. Important caveats, limitations, or conflicting evidence
5. Properly attributed citations and quotes where appropriate

Format the response in a clear, professional manner with proper source attribution."""

        # Determine consultation tier based on quality and budget
        avg_quality = sum(state["quality_scores"]) / len(state["quality_scores"]) if state["quality_scores"] else 0.0

        if avg_quality >= 0.9:
            # High quality research, use medium tier for synthesis
            tier = ConsultationTier.MEDIUM
        elif avg_quality >= 0.7:
            # Good quality, use low tier
            tier = ConsultationTier.LOW
        else:
            # Lower quality, might need critical tier review
            tier = ConsultationTier.HIGH

        # Create consultation request
        request = ConsultationRequest(
            task_description=prompt,
            required_capabilities={ModelCapability.SYNTHESIS, ModelCapability.REASONING},
            tier=tier,
            max_cost=state["budget_remaining"],
            prefer_local=state["budget_remaining"] < Decimal("0.50"),
            context={
                "query": state["query"],
                "findings_count": len(state["findings"]),
                "sources_count": len(state["sources"]),
                "session_id": state["session_id"]
            }
        )

        # Consult model
        response = await components.model_coordinator.consult(request)

        if response.success:
            # Record model usage
            state = record_model_call(
                state,
                model_id=response.model_used,
                result={"synthesis": "success"},
                cost=response.cost,
                success=True
            )

            # Update budget
            state["budget_remaining"] -= response.cost

            logger.info(
                f"AI synthesis generated using {response.model_used} "
                f"(tier: {tier.value}, cost: ${response.cost})"
            )

            return response.response
        else:
            logger.warning(f"AI synthesis failed: {response.error}, using fallback")
            return _generate_basic_synthesis(state)

    except Exception as e:
        logger.error(f"Error generating AI synthesis: {e}")
        return _generate_basic_synthesis(state)


def _generate_basic_synthesis(state: ResearchState) -> str:
    """
    Generate basic text synthesis (fallback).

    Args:
        state: Research state with findings

    Returns:
        Basic text synthesis
    """
    final_answer = f"Research completed for query: '{state['query']}'\n\n"
    final_answer += f"Found {len(state['findings'])} findings across {state['current_iteration']} iterations.\n\n"

    if state["findings"]:
        final_answer += "Key Findings:\n"
        for i, finding in enumerate(state["findings"][-5:], 1):
            content = finding.get('content', '')
            confidence = finding.get('confidence', 0.0)
            final_answer += f"{i}. (Confidence: {confidence:.2f}) {content[:200]}...\n\n"

    if state["sources"]:
        final_answer += "\nTop Sources:\n"
        for i, source in enumerate(state["sources"][:10], 1):
            final_answer += f"{i}. {source.get('title', 'Untitled')}: {source.get('url', '')}\n"

    return final_answer


async def handle_error(state: ResearchState) -> ResearchState:
    """
    Handle errors during research.

    Determines:
    - If error is recoverable
    - If should retry
    - If should abort
    """
    logger.error(f"Handling error: {state.get('last_error', 'Unknown error')}")

    try:
        # Check retry limit
        if state["retry_count"] >= 3:
            logger.error("Max retries exceeded, aborting research")
            state = set_status(state, ResearchStatus.FAILED)
        else:
            logger.info(f"Retry {state['retry_count']}/3")
            # Could implement retry logic here

    except Exception as e:
        logger.error(f"Error in error handler: {e}")
        state = set_status(state, ResearchStatus.FAILED)

    return state
