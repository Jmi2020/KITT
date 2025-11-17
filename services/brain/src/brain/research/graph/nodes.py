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


async def select_strategy(state: ResearchState) -> ResearchState:
    """
    Select and configure research strategy for this iteration.

    Determines:
    - Which tools to use
    - Search parameters
    - Exploration vs exploitation
    """
    logger.info(f"Selecting strategy for iteration {state['current_iteration']}")

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
            logger.warning("No tasks planned, skipping iteration")
            return state

        # Get components for real tool execution
        from .components import get_global_components
        components = get_global_components()

        # Execute tasks using real tool executor if available
        if components and components.tool_executor:
            logger.info(f"Executing {len(tasks)} tasks with real tool executor")
            await _execute_tasks_real(state, tasks, components)
        else:
            logger.warning("Tool executor not available, using simulated execution")
            await _execute_tasks_simulated(state, tasks)

        logger.info(
            f"Iteration {state['current_iteration']} executed: "
            f"{len(state['findings'])} total findings, "
            f"{len(state['sources'])} total sources"
        )

    except Exception as e:
        logger.error(f"Failed to execute iteration: {e}")
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

    for task in tasks[:3]:  # Execute up to 3 tasks per iteration
        try:
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

            # Execute tool
            result = await components.tool_executor.execute(
                tool_name=tool_name,
                arguments=arguments,
                context=context
            )

            # Process results
            if result.success:
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

                    # Add citations as sources
                    for citation_url in result.data.get("citations", []):
                        source = {
                            "url": citation_url,
                            "title": f"Citation from deep research",
                            "relevance": task["priority"],
                            "tool": "research_deep"
                        }
                        state = add_source(state, source)

                elif tool_name == ToolType.WEB_SEARCH:
                    # Web search returns multiple results
                    search_results = result.data.get("results", [])

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

                        # Add search results as sources
                        for search_result in search_results[:5]:  # Top 5 results
                            source = {
                                "url": search_result.get("url", ""),
                                "title": search_result.get("title", ""),
                                "snippet": search_result.get("description", ""),
                                "relevance": task["priority"],
                                "tool": "web_search"
                            }
                            state = add_source(state, source)
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

                state = add_finding(state, finding)

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
            logger.error(f"Error executing task {task.get('task_id')}: {e}")
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


async def check_stopping(state: ResearchState) -> ResearchState:
    """
    Check if research should stop.

    Evaluates:
    - Iteration limits
    - Quality thresholds
    - Saturation levels
    - Budget constraints
    - Knowledge gaps
    """
    logger.info("Checking stopping criteria")

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

    return state


async def synthesize_results(state: ResearchState) -> ResearchState:
    """
    Synthesize final research results.

    Creates:
    - AI-generated final answer via ModelCoordinator
    - Summary of findings
    - Source attribution
    - Quality report
    """
    logger.info("Synthesizing research results")

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

        sources_text = "\n".join([
            f"- {s.get('title', 'Untitled')}: {s.get('url', '')}"
            for s in state["sources"][:20]  # Top 20 sources
        ])

        # Construct synthesis prompt
        prompt = f"""Synthesize the following research findings into a comprehensive, well-structured answer.

Original Query: {state["query"]}

Research Findings:
{findings_text}

Sources Consulted:
{sources_text}

Please provide:
1. A direct answer to the query
2. Key insights and supporting evidence
3. Important caveats or limitations
4. Source citations where appropriate

Format the response in a clear, professional manner."""

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
            prompt=prompt,
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
