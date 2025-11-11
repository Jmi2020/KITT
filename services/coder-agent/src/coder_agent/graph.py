"""
LangGraph state machine for test-driven code generation.

Implements Plan-Code-Test-Run-Refine-Summarize workflow with LLM-powered
code generation and automated testing feedback loop.
"""

from __future__ import annotations

import logging
from typing import Literal, TypedDict

from langgraph.graph import END, StateGraph

from .llm_client import CoderLLMClient
from .prompts import (
    CODE_PROMPT_TEMPLATE,
    CODER_SYSTEM,
    MAX_CODE_LENGTH,
    PLAN_PROMPT,
    REFINE_PROMPT_TEMPLATE,
    SUMMARIZE_PROMPT_TEMPLATE,
    TEST_PROMPT_TEMPLATE,
)
from .sandbox import TestRunner

logger = logging.getLogger(__name__)


class CoderState(TypedDict, total=False):
    """
    State for code generation workflow.

    Tracks progress through Plan-Code-Test-Run-Refine-Summarize loop.
    """

    # Inputs
    user_request: str  # Original coding request

    # Plan phase
    plan: str  # Implementation plan

    # Code phase
    code: str  # Generated Python code

    # Test phase
    test_code: str  # Generated pytest tests

    # Run phase
    run_success: bool  # Did tests pass?
    run_stdout: str  # Test execution stdout
    run_stderr: str  # Test execution stderr
    run_exit_code: int  # Test exit code

    # Refine phase
    refinement_count: int  # Number of refinement iterations
    max_refinements: int  # Maximum allowed refinements

    # Summarize phase
    summary: str  # Final markdown summary

    # Metadata
    error: str  # Error message if workflow fails


class CoderGraph:
    """
    LangGraph-based code generation workflow.

    Orchestrates Plan → Code → Tests → Run → (Refine if needed) → Summarize.
    """

    def __init__(
        self,
        llm_client: CoderLLMClient,
        test_runner: TestRunner,
        max_refinements: int = 2,
    ) -> None:
        """
        Initialize coder graph.

        Args:
            llm_client: LLM client for code generation
            test_runner: Sandbox test runner
            max_refinements: Maximum refinement iterations
        """
        self.llm_client = llm_client
        self.test_runner = test_runner
        self.max_refinements = max_refinements

        # Build graph
        self.graph = self._build_graph()

        logger.info(f"Initialized CoderGraph with max_refinements={max_refinements}")

    def _build_graph(self) -> StateGraph:
        """
        Build LangGraph state machine.

        Returns:
            Compiled StateGraph
        """
        workflow = StateGraph(CoderState)

        # Add nodes
        workflow.add_node("plan", self._plan_node)
        workflow.add_node("code", self._code_node)
        workflow.add_node("tests", self._tests_node)
        workflow.add_node("run", self._run_node)
        workflow.add_node("refine", self._refine_node)
        workflow.add_node("summarize", self._summarize_node)

        # Entry point
        workflow.set_entry_point("plan")

        # Linear flow: plan → code → tests → run
        workflow.add_edge("plan", "code")
        workflow.add_edge("code", "tests")
        workflow.add_edge("tests", "run")

        # Conditional: run → refine (if failed) or summarize (if passed)
        workflow.add_conditional_edges(
            "run",
            self._should_refine,
            {
                "refine": "refine",
                "summarize": "summarize",
            },
        )

        # After refine: tests → run (retry loop)
        workflow.add_edge("refine", "tests")

        # End after summarize
        workflow.add_edge("summarize", END)

        return workflow.compile()

    async def run(self, user_request: str) -> CoderState:
        """
        Execute code generation workflow.

        Args:
            user_request: User's coding request

        Returns:
            Final state with code, tests, and summary
        """
        logger.info(f"Starting code generation: {user_request[:100]}...")

        initial_state: CoderState = {
            "user_request": user_request,
            "refinement_count": 0,
            "max_refinements": self.max_refinements,
        }

        try:
            final_state = await self.graph.ainvoke(initial_state)
            logger.info("Code generation completed successfully")
            return final_state

        except Exception as exc:
            logger.error(f"Code generation failed: {exc}", exc_info=True)
            return {
                **initial_state,
                "error": str(exc),
            }

    async def _plan_node(self, state: CoderState) -> dict:
        """
        Plan phase: Generate implementation plan.

        Args:
            state: Current workflow state

        Returns:
            State update with plan
        """
        logger.info("Generating implementation plan...")

        plan = await self.llm_client.plan(
            user_request=PLAN_PROMPT + "\n\n" + state["user_request"],
            system_prompt=CODER_SYSTEM,
        )

        logger.debug(f"Plan generated: {len(plan)} chars")

        return {"plan": plan}

    async def _code_node(self, state: CoderState) -> dict:
        """
        Code phase: Generate Python module.

        Args:
            state: Current workflow state

        Returns:
            State update with code
        """
        logger.info("Generating code...")

        prompt = CODE_PROMPT_TEMPLATE.format(
            user_request=state["user_request"],
            plan=state["plan"],
        )

        code = await self.llm_client.code(
            prompt=prompt,
            system_prompt=CODER_SYSTEM,
        )

        # Strip markdown code fences if present
        code = self._clean_code_output(code)

        # Validate length
        if len(code) > MAX_CODE_LENGTH:
            logger.warning(f"Code exceeds max length: {len(code)} > {MAX_CODE_LENGTH}")
            code = code[:MAX_CODE_LENGTH]

        logger.debug(f"Code generated: {len(code)} chars")

        return {"code": code}

    async def _tests_node(self, state: CoderState) -> dict:
        """
        Tests phase: Generate pytest tests.

        Args:
            state: Current workflow state

        Returns:
            State update with test_code
        """
        logger.info("Generating tests...")

        prompt = TEST_PROMPT_TEMPLATE.format(
            code=state["code"],
            user_request=state["user_request"],
        )

        test_code = await self.llm_client.tests(
            prompt=prompt,
            system_prompt=CODER_SYSTEM,
        )

        # Strip markdown code fences if present
        test_code = self._clean_code_output(test_code)

        logger.debug(f"Tests generated: {len(test_code)} chars")

        return {"test_code": test_code}

    async def _run_node(self, state: CoderState) -> dict:
        """
        Run phase: Execute tests in sandbox.

        Args:
            state: Current workflow state

        Returns:
            State update with test results
        """
        logger.info("Running tests in sandbox...")

        result = self.test_runner.run_single_test(
            code=state["code"],
            test_code=state["test_code"],
        )

        logger.info(
            f"Tests {'passed' if result.success else 'failed'} "
            f"(exit_code={result.exit_code})"
        )

        return {
            "run_success": result.success,
            "run_stdout": result.stdout,
            "run_stderr": result.stderr,
            "run_exit_code": result.exit_code,
        }

    async def _refine_node(self, state: CoderState) -> dict:
        """
        Refine phase: Fix code based on test failures.

        Args:
            state: Current workflow state

        Returns:
            State update with refined code and incremented counter
        """
        refinement_num = state["refinement_count"] + 1
        logger.info(f"Refining code (iteration {refinement_num})...")

        prompt = REFINE_PROMPT_TEMPLATE.format(
            user_request=state["user_request"],
            code=state["code"],
            stdout=state["run_stdout"],
            stderr=state["run_stderr"],
        )

        refined_code = await self.llm_client.refine(
            prompt=prompt,
            system_prompt=CODER_SYSTEM,
        )

        # Strip markdown code fences if present
        refined_code = self._clean_code_output(refined_code)

        # Validate length
        if len(refined_code) > MAX_CODE_LENGTH:
            logger.warning(
                f"Refined code exceeds max length: {len(refined_code)} > {MAX_CODE_LENGTH}"
            )
            refined_code = refined_code[:MAX_CODE_LENGTH]

        logger.debug(f"Refined code: {len(refined_code)} chars")

        return {
            "code": refined_code,
            "refinement_count": refinement_num,
        }

    async def _summarize_node(self, state: CoderState) -> dict:
        """
        Summarize phase: Generate markdown summary with usage.

        Args:
            state: Current workflow state

        Returns:
            State update with summary
        """
        logger.info("Generating summary...")

        prompt = SUMMARIZE_PROMPT_TEMPLATE.format(
            user_request=state["user_request"],
            plan=state["plan"],
            passed=state["run_success"],
            run_stdout=state["run_stdout"],
        )

        summary = await self.llm_client.summarize(
            prompt=prompt,
            system_prompt=CODER_SYSTEM,
        )

        logger.debug(f"Summary generated: {len(summary)} chars")

        return {"summary": summary}

    def _should_refine(
        self, state: CoderState
    ) -> Literal["refine", "summarize"]:
        """
        Decision function: Should we refine or summarize?

        Args:
            state: Current workflow state

        Returns:
            "refine" if tests failed and under limit, else "summarize"
        """
        # If tests passed, go to summary
        if state["run_success"]:
            logger.info("Tests passed → proceeding to summary")
            return "summarize"

        # If refinement limit reached, go to summary anyway
        if state["refinement_count"] >= state["max_refinements"]:
            logger.warning(
                f"Refinement limit reached ({state['max_refinements']}) → "
                "proceeding to summary despite failures"
            )
            return "summarize"

        # Otherwise, refine
        logger.info(
            f"Tests failed ({state['refinement_count']}/{state['max_refinements']} "
            "refinements) → refining code"
        )
        return "refine"

    @staticmethod
    def _clean_code_output(code: str) -> str:
        """
        Strip markdown code fences and extra whitespace.

        Args:
            code: Raw LLM output

        Returns:
            Cleaned Python code
        """
        code = code.strip()

        # Remove markdown code fences
        if code.startswith("```python"):
            code = code[9:]  # len("```python") = 9
        elif code.startswith("```"):
            code = code[3:]

        if code.endswith("```"):
            code = code[:-3]

        return code.strip()


async def create_coder_graph(
    max_refinements: int = 2,
    timeout_seconds: int = 20,
) -> CoderGraph:
    """
    Factory function to create configured coder graph.

    Args:
        max_refinements: Maximum refinement iterations
        timeout_seconds: Sandbox execution timeout

    Returns:
        Initialized CoderGraph
    """
    llm_client = CoderLLMClient()
    test_runner = TestRunner(timeout_seconds=timeout_seconds)

    return CoderGraph(
        llm_client=llm_client,
        test_runner=test_runner,
        max_refinements=max_refinements,
    )
