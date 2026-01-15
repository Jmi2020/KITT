"""
Main orchestrator for the Tiered Collective Architecture.

Coordinates the Planner → Executor → Judge workflow with state
machine transitions, error handling, and graceful degradation.
"""

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, AsyncIterator, Callable, Dict, List, Optional

from .backends import BackendInstance, BackendPool
from .config import CollectiveConfig
from .models import (
    ExecutionResult,
    Judgment,
    JudgmentVerdict,
    TaskPlan,
    TaskStep,
    ToolCall,
)
from .prompts import (
    EXECUTOR_SYSTEM_PROMPT,
    JUDGE_SYSTEM_PROMPT,
    PLANNER_SYSTEM_PROMPT,
    filter_context_for_executor,
    format_executor_revision_prompt,
    format_executor_user_prompt,
    format_judge_user_prompt,
    format_planner_user_prompt,
)
from .router import ComplexityRouter, RoutingDecision
from .state import CollectiveContext, CollectiveState

logger = logging.getLogger("kitty-code")


@dataclass
class OrchestrationResult:
    """Result of collective orchestration."""

    # Whether orchestration succeeded
    success: bool

    # Final output for user
    output: str = ""

    # The plan that was executed (if any)
    plan: Optional[TaskPlan] = None

    # All execution results
    executions: List[ExecutionResult] = field(default_factory=list)

    # All judgments
    judgments: List[Judgment] = field(default_factory=list)

    # Error message (if failed)
    error: Optional[str] = None

    # Timing
    duration_ms: int = 0

    # Whether collective was used or bypassed
    used_collective: bool = False

    # Routing decision
    routing: Optional[RoutingDecision] = None


class CollectiveOrchestrator:
    """
    Orchestrates the Planner → Executor → Judge workflow.

    This is the main entry point for collective processing. It:
    1. Routes tasks to direct or collective execution
    2. Runs the Planner to create a task plan
    3. Executes each step with the Executor
    4. Validates output with the Judge
    5. Handles revisions and escalations
    6. Returns the final result
    """

    def __init__(
        self,
        config: CollectiveConfig,
        backend_pool: BackendPool,
        tool_executor: Optional[Callable] = None,
    ):
        """
        Initialize the orchestrator.

        Args:
            config: Collective configuration
            backend_pool: Pool of backend instances for each role
            tool_executor: Callable to execute tools (injected from Agent)
        """
        self.config = config
        self.backend_pool = backend_pool
        self.tool_executor = tool_executor
        self.router = ComplexityRouter(config.routing)
        self.context = CollectiveContext()

    async def process(
        self,
        user_input: str,
        conversation_context: Optional[str] = None,
    ) -> OrchestrationResult:
        """
        Process a user request through collective orchestration.

        Args:
            user_input: The user's request
            conversation_context: Optional conversation history

        Returns:
            OrchestrationResult with output and metadata
        """
        start_time = time.time()

        # Reset context for new request
        self.context.reset_for_new_request(user_input)

        try:
            # Step 1: Route the request
            self.context.transition_to(CollectiveState.ROUTING, "Processing user input")
            routing = self.router.route(user_input)
            self.context.routing_confidence = routing.confidence
            self.context.routing_mode = routing.mode

            logger.info(
                f"Routing decision: {routing.mode} (confidence: {routing.confidence:.2f})"
            )

            # Step 2: Direct execution or collective
            if routing.is_direct():
                result = await self._direct_execute(user_input, conversation_context)
                result.routing = routing
                result.used_collective = False
            else:
                result = await self._collective_execute(user_input, conversation_context)
                result.routing = routing
                result.used_collective = True

            result.duration_ms = int((time.time() - start_time) * 1000)
            return result

        except Exception as e:
            logger.error(f"Orchestration error: {e}", exc_info=True)
            self.context.transition_to(CollectiveState.ERROR, f"Error: {e}")
            self.context.error_message = str(e)

            return OrchestrationResult(
                success=False,
                error=str(e),
                duration_ms=int((time.time() - start_time) * 1000),
            )

    async def _direct_execute(
        self,
        user_input: str,
        context: Optional[str],
    ) -> OrchestrationResult:
        """
        Direct execution (bypass collective).

        Used for simple tasks that don't need planning/review.
        """
        self.context.transition_to(CollectiveState.DIRECT_EXECUTE, "Simple task")

        # Use executor backend for direct execution
        backend = self.backend_pool.get_executor_backend()

        if not backend.healthy:
            # Try fallback
            backend = self.backend_pool.get_fallback_backend("executor")
            if backend is None:
                return OrchestrationResult(
                    success=False,
                    error="No healthy backend available for direct execution",
                )

        # Execute with executor
        result = await self._call_model(
            backend,
            EXECUTOR_SYSTEM_PROMPT,
            user_input,
        )

        self.context.transition_to(CollectiveState.COMPLETE, "Direct execution complete")

        return OrchestrationResult(
            success=True,
            output=result.get("content", ""),
            used_collective=False,
        )

    async def _collective_execute(
        self,
        user_input: str,
        context: Optional[str],
    ) -> OrchestrationResult:
        """
        Full collective execution (Planner → Executor → Judge).
        """
        # Step 1: Planning
        self.context.transition_to(CollectiveState.PLANNING, "Creating task plan")
        plan = await self._run_planner(user_input, context)

        if plan is None:
            self.context.transition_to(CollectiveState.ERROR, "Planning failed")
            return OrchestrationResult(
                success=False,
                error="Failed to create task plan",
            )

        self.context.current_plan = plan
        logger.info(f"Plan created with {len(plan.steps)} steps")

        # Step 2: Execute each step
        all_executions = []
        all_judgments = []

        for step_idx, step in enumerate(plan.steps):
            self.context.current_step_index = step_idx
            logger.info(f"Executing step {step_idx + 1}/{len(plan.steps)}: {step.description}")

            # Execute step
            self.context.transition_to(CollectiveState.EXECUTING, f"Step {step_idx + 1}")
            execution = await self._run_executor(step, plan.summary, all_executions)
            all_executions.append(execution)
            self.context.execution_results.append(execution)

            if not execution.success:
                # Executor failed, try escalation
                if self.context.can_escalate(self.config.judgment.max_escalations):
                    self.context.record_escalation()
                    self.context.transition_to(CollectiveState.ESCALATE, "Executor failed")
                    # Re-plan starting from this step
                    continue
                else:
                    self.context.transition_to(CollectiveState.ERROR, "Max escalations reached")
                    return OrchestrationResult(
                        success=False,
                        error=f"Executor failed on step {step_idx + 1}: {execution.error}",
                        plan=plan,
                        executions=all_executions,
                    )

            # Judge the execution
            self.context.transition_to(CollectiveState.JUDGING, f"Reviewing step {step_idx + 1}")
            judgment = await self._run_judge(plan, step, execution)
            all_judgments.append(judgment)
            self.context.judgments.append(judgment)

            # Handle judgment
            if judgment.is_approved():
                logger.info(f"Step {step_idx + 1} approved")
                continue

            elif judgment.needs_revision():
                # Revision loop
                revision_count = 0
                while (
                    judgment.needs_revision()
                    and self.context.can_revise(self.config.judgment.max_revision_cycles)
                ):
                    self.context.record_revision()
                    revision_count += 1
                    logger.info(f"Revision {revision_count} for step {step_idx + 1}")

                    self.context.transition_to(CollectiveState.REVISING, f"Revision {revision_count}")

                    # Get feedback
                    feedback = ""
                    if judgment.revision_feedback:
                        feedback = "\n".join(judgment.revision_feedback.issues)
                        feedback += "\n" + "\n".join(judgment.revision_feedback.suggestions)

                    # Re-execute with feedback
                    self.context.transition_to(CollectiveState.EXECUTING, "Re-executing")
                    execution = await self._run_executor_revision(step, execution, feedback)
                    all_executions.append(execution)

                    # Re-judge
                    self.context.transition_to(CollectiveState.JUDGING, "Re-reviewing")
                    judgment = await self._run_judge(plan, step, execution)
                    all_judgments.append(judgment)

                if judgment.is_rejected():
                    # Max revisions or final rejection
                    if self.context.can_escalate(self.config.judgment.max_escalations):
                        self.context.record_escalation()
                        self.context.transition_to(CollectiveState.ESCALATE, "Judge rejected")
                        continue
                    else:
                        self.context.transition_to(CollectiveState.ERROR, "Rejected after revisions")
                        return OrchestrationResult(
                            success=False,
                            error=f"Step {step_idx + 1} rejected after {revision_count} revisions",
                            plan=plan,
                            executions=all_executions,
                            judgments=all_judgments,
                        )

            elif judgment.is_rejected():
                # Immediate rejection
                if self.context.can_escalate(self.config.judgment.max_escalations):
                    self.context.record_escalation()
                    self.context.transition_to(CollectiveState.ESCALATE, "Immediate rejection")
                    continue
                else:
                    self.context.transition_to(CollectiveState.ERROR, "Max escalations reached")
                    return OrchestrationResult(
                        success=False,
                        error=f"Step {step_idx + 1} rejected: {judgment.reasoning}",
                        plan=plan,
                        executions=all_executions,
                        judgments=all_judgments,
                    )

        # All steps complete
        self.context.transition_to(CollectiveState.COMPLETE, "All steps approved")

        # Compile final output
        output = self._compile_output(plan, all_executions, all_judgments)

        return OrchestrationResult(
            success=True,
            output=output,
            plan=plan,
            executions=all_executions,
            judgments=all_judgments,
            used_collective=True,
        )

    async def _run_planner(
        self,
        user_input: str,
        context: Optional[str],
    ) -> Optional[TaskPlan]:
        """Run the Planner to create a task plan."""
        backend = self.backend_pool.get_planner_backend()

        if not backend.healthy:
            backend = self.backend_pool.get_fallback_backend("planner")
            if backend is None:
                logger.error("No healthy backend for Planner")
                return None

        user_prompt = format_planner_user_prompt(user_input, context)

        result = await self._call_model(
            backend,
            PLANNER_SYSTEM_PROMPT,
            user_prompt,
        )

        content = result.get("content", "")

        # Parse JSON from response
        try:
            # Extract JSON from markdown code block if present
            if "```json" in content:
                json_start = content.index("```json") + 7
                json_end = content.index("```", json_start)
                json_str = content[json_start:json_end].strip()
            elif "```" in content:
                json_start = content.index("```") + 3
                json_end = content.index("```", json_start)
                json_str = content[json_start:json_end].strip()
            else:
                json_str = content

            plan_data = json.loads(json_str)
            plan = TaskPlan.from_json(plan_data)
            plan.user_request = user_input
            plan.model = backend.model_config.name

            return plan

        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to parse plan: {e}")
            logger.debug(f"Raw content: {content}")
            return None

    async def _run_executor(
        self,
        step: TaskStep,
        plan_summary: str,
        previous_results: List[ExecutionResult],
    ) -> ExecutionResult:
        """Run the Executor to implement a step."""
        backend = self.backend_pool.get_executor_backend()
        start_time = datetime.now()

        if not backend.healthy:
            backend = self.backend_pool.get_fallback_backend("executor")
            if backend is None:
                return ExecutionResult(
                    step_id=step.step_id,
                    success=False,
                    error="No healthy backend for Executor",
                )

        user_prompt = format_executor_user_prompt(step, plan_summary, previous_results)

        # Filter context for executor (context blinding)
        filtered_prompt = filter_context_for_executor(user_prompt)

        result = await self._call_model(
            backend,
            EXECUTOR_SYSTEM_PROMPT,
            filtered_prompt,
        )

        execution = ExecutionResult(
            step_id=step.step_id,
            response_text=result.get("content", ""),
            tool_calls=result.get("tool_calls", []),
            success=result.get("success", True),
            error=result.get("error"),
            started_at=start_time,
            model=backend.model_config.name,
            prompt_tokens=result.get("prompt_tokens", 0),
            completion_tokens=result.get("completion_tokens", 0),
        )
        execution.complete()

        return execution

    async def _run_executor_revision(
        self,
        step: TaskStep,
        previous_result: ExecutionResult,
        feedback: str,
    ) -> ExecutionResult:
        """Run the Executor with revision feedback."""
        backend = self.backend_pool.get_executor_backend()
        start_time = datetime.now()

        if not backend.healthy:
            backend = self.backend_pool.get_fallback_backend("executor")
            if backend is None:
                return ExecutionResult(
                    step_id=step.step_id,
                    success=False,
                    error="No healthy backend for Executor revision",
                )

        user_prompt = format_executor_revision_prompt(step, previous_result, feedback)

        result = await self._call_model(
            backend,
            EXECUTOR_SYSTEM_PROMPT,
            user_prompt,
        )

        execution = ExecutionResult(
            step_id=step.step_id,
            response_text=result.get("content", ""),
            tool_calls=result.get("tool_calls", []),
            success=result.get("success", True),
            error=result.get("error"),
            started_at=start_time,
            model=backend.model_config.name,
        )
        execution.complete()

        return execution

    async def _run_judge(
        self,
        plan: TaskPlan,
        step: TaskStep,
        execution: ExecutionResult,
    ) -> Judgment:
        """Run the Judge to validate execution."""
        backend = self.backend_pool.get_judge_backend()

        if not backend.healthy:
            # Judge failure → auto-approve with warning
            logger.warning("Judge backend unhealthy, auto-approving")
            return Judgment(
                step_id=step.step_id,
                verdict=JudgmentVerdict.APPROVE,
                confidence=0.5,
                reasoning="Auto-approved due to Judge backend failure",
            )

        user_prompt = format_judge_user_prompt(plan, step, execution)

        result = await self._call_model(
            backend,
            JUDGE_SYSTEM_PROMPT,
            user_prompt,
        )

        content = result.get("content", "")

        # Parse JSON from response
        try:
            if "```json" in content:
                json_start = content.index("```json") + 7
                json_end = content.index("```", json_start)
                json_str = content[json_start:json_end].strip()
            elif "```" in content:
                json_start = content.index("```") + 3
                json_end = content.index("```", json_start)
                json_str = content[json_start:json_end].strip()
            else:
                json_str = content

            judgment_data = json.loads(json_str)
            judgment = Judgment.from_json(judgment_data, step.step_id)
            judgment.model = backend.model_config.name

            return judgment

        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to parse judgment: {e}")
            # Default to approve on parse failure
            return Judgment(
                step_id=step.step_id,
                verdict=JudgmentVerdict.APPROVE,
                confidence=0.6,
                reasoning=f"Auto-approved due to parse error: {e}",
            )

    async def _call_model(
        self,
        backend: BackendInstance,
        system_prompt: str,
        user_prompt: str,
    ) -> Dict[str, Any]:
        """
        Call a model backend.

        This is a placeholder - actual implementation will depend on
        the backend interface (OpenAI-compatible, Ollama, etc.)
        """
        start_time = time.time()

        try:
            # This would be replaced with actual backend call
            # For now, return empty result
            if backend.backend is None:
                return {
                    "content": "",
                    "success": False,
                    "error": "Backend not initialized",
                }

            # Actual call would look something like:
            # response = await backend.backend.chat(
            #     messages=[
            #         {"role": "system", "content": system_prompt},
            #         {"role": "user", "content": user_prompt},
            #     ],
            # )

            # For now, return placeholder
            duration_ms = int((time.time() - start_time) * 1000)
            backend.record_request(True, duration_ms)

            return {
                "content": "",
                "success": True,
                "prompt_tokens": 0,
                "completion_tokens": 0,
            }

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            backend.record_request(False, duration_ms, error=str(e))
            backend.mark_unhealthy(str(e))

            return {
                "content": "",
                "success": False,
                "error": str(e),
            }

    def _compile_output(
        self,
        plan: TaskPlan,
        executions: List[ExecutionResult],
        judgments: List[Judgment],
    ) -> str:
        """Compile final output from all executions."""
        output_parts = []

        # Summary
        output_parts.append(f"## Completed: {plan.summary}\n")

        # Steps summary
        for i, (execution, judgment) in enumerate(zip(executions, judgments)):
            status = "✓" if judgment.is_approved() else "⚠"
            output_parts.append(f"{status} Step {i + 1}: {execution.response_text[:200]}...")

        # Combine execution outputs
        combined = "\n\n".join(e.response_text for e in executions if e.success)
        if combined:
            output_parts.append(f"\n{combined}")

        return "\n".join(output_parts)

    def get_status(self) -> Dict[str, Any]:
        """Get current orchestration status."""
        return {
            "state": self.context.state.name,
            "routing": {
                "mode": self.context.routing_mode,
                "confidence": self.context.routing_confidence,
            },
            "progress": {
                "current_step": self.context.current_step_index,
                "total_steps": len(self.context.current_plan.steps) if self.context.current_plan else 0,
                "revisions": self.context.revision_count,
                "escalations": self.context.escalation_count,
            },
            "timing": {
                "elapsed_ms": self.context.get_elapsed_time_ms(),
            },
            "backends": self.backend_pool.get_aggregate_stats(),
        }
