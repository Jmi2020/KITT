"""
FastAPI application for coder-agent service.

Provides REST API for LLM-powered code generation with test-driven refinement.
"""

import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

import json
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from prometheus_client import Counter, Histogram, generate_latest

from .graph import CoderGraph, create_coder_graph
from .llm_client import CoderLLMClient
from .models import GenerateCodeRequest, GenerateCodeResponse, HealthCheckResponse, StreamRequest

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Global state
coder_graph: Optional[CoderGraph] = None
llm_client: Optional[CoderLLMClient] = None

# Prometheus metrics
generation_counter = Counter(
    "coder_generations_total",
    "Total code generation requests",
    ["status"],
)

generation_duration = Histogram(
    "coder_generation_duration_seconds",
    "Code generation request duration",
)

refinement_counter = Counter(
    "coder_refinements_total",
    "Total refinement iterations",
)

test_pass_counter = Counter(
    "coder_tests_passed_total",
    "Total tests passed vs failed",
    ["result"],
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global coder_graph, llm_client

    # Load configuration
    max_refinements = int(os.getenv("CODER_MAX_REFINEMENTS", "2"))
    timeout_seconds = int(os.getenv("CODER_TIMEOUT_SECONDS", "20"))

    logger.info(
        f"Initializing coder-agent: max_refinements={max_refinements}, "
        f"timeout={timeout_seconds}s"
    )

    # Initialize graph
    coder_graph = await create_coder_graph(
        max_refinements=max_refinements,
        timeout_seconds=timeout_seconds,
    )

    # Initialize LLM client for health checks
    llm_client = CoderLLMClient()

    logger.info("Coder-agent service started")

    yield

    # Cleanup
    if llm_client:
        await llm_client.close()
        logger.info("LLM client closed")


# Create FastAPI app
app = FastAPI(
    title="KITTY Coder Agent",
    description="LLM-powered code generation with test-driven refinement",
    version="1.0.0",
    lifespan=lifespan,
)


# ==============================================================================
# Health Check
# ==============================================================================


@app.get("/healthz", response_model=HealthCheckResponse)
async def health_check() -> HealthCheckResponse:
    """
    Health check endpoint.

    Returns service status and llama.cpp server health.
    """
    try:
        # Check LLM server health
        llm_health = await llm_client.health_check()

        # Service is healthy if at least one LLM server is up
        healthy = any(llm_health.values())

        return HealthCheckResponse(
            status="ok" if healthy else "degraded",
            llm_servers=llm_health,
        )

    except Exception as exc:
        logger.error(f"Health check failed: {exc}", exc_info=True)
        return HealthCheckResponse(
            status="error",
            llm_servers=None,
        )


# ==============================================================================
# Code Generation
# ==============================================================================


@app.post("/api/coding/generate", response_model=GenerateCodeResponse)
async def generate_code(request: GenerateCodeRequest) -> GenerateCodeResponse:
    """
    Generate Python code from natural language request.

    Implements Plan-Code-Test-Run-Refine-Summarize workflow with
    automated testing and refinement up to max_refinements iterations.

    Args:
        request: Code generation parameters

    Returns:
        Generated code, tests, summary, and execution results
    """
    try:
        logger.info(f"Code generation request: {request.request[:100]}...")

        # Create graph with custom parameters if needed
        graph = coder_graph
        if (
            request.max_refinements != 2
            or request.timeout_seconds != 20
        ):
            # Create custom graph for this request
            from .graph import create_coder_graph

            graph = await create_coder_graph(
                max_refinements=request.max_refinements,
                timeout_seconds=request.timeout_seconds,
            )

        # Run workflow
        with generation_duration.time():
            state = await graph.run(user_request=request.request)

        # Track metrics
        success = state.get("run_success", False)
        generation_counter.labels(status="success" if success else "failed").inc()

        if "refinement_count" in state:
            refinement_counter.inc(state["refinement_count"])

        test_pass_counter.labels(result="pass" if success else "fail").inc()

        # Build response
        response = GenerateCodeResponse(
            success=not bool(state.get("error")),
            code=state.get("code"),
            test_code=state.get("test_code"),
            tests_passed=state.get("run_success", False),
            refinement_count=state.get("refinement_count", 0),
            summary=state.get("summary"),
            plan=state.get("plan"),
            test_output=(
                f"STDOUT:\n{state.get('run_stdout', '')}\n\n"
                f"STDERR:\n{state.get('run_stderr', '')}"
                if "run_stdout" in state
                else None
            ),
            error=state.get("error"),
        )

        logger.info(
            f"Code generation {'succeeded' if response.success else 'failed'}: "
            f"tests_passed={response.tests_passed}, "
            f"refinements={response.refinement_count}"
        )

        return response

    except Exception as exc:
        logger.error(f"Code generation failed: {exc}", exc_info=True)
        generation_counter.labels(status="error").inc()

        return GenerateCodeResponse(
            success=False,
            error=str(exc),
        )


# ==============================================================================
# SSE Streaming Code Generation
# ==============================================================================


@app.post("/api/coding/stream")
async def stream_generate_code(request: StreamRequest) -> StreamingResponse:
    """
    Stream code generation with Server-Sent Events.

    Provides real-time updates as the Plan→Code→Test→Run→Refine→Summarize
    workflow progresses. Each phase emits events with partial results.

    SSE Event Types:
        - started: Session started
        - plan_start/plan_chunk/plan_complete: Planning phase
        - code_start/code_chunk/code_complete: Code generation phase
        - test_start/test_chunk/test_complete: Test generation phase
        - run_start/run_output/run_complete: Test execution phase
        - refine_start/refine_chunk/refine_complete: Refinement phase
        - summary_start/summary_chunk/summary_complete: Summary phase
        - complete: Workflow complete
        - error: Error occurred

    Args:
        request: Stream request with coding request and options

    Returns:
        StreamingResponse with text/event-stream media type
    """
    session_id = str(uuid.uuid4())
    logger.info(f"[{session_id}] Starting streaming code generation: {request.request[:100]}...")

    async def event_generator():
        """Generate SSE events for each workflow phase."""
        try:
            # Emit session started
            yield f"data: {json.dumps({'type': 'started', 'sessionId': session_id})}\n\n"

            # Create graph for this request
            from .graph import create_coder_graph
            graph = await create_coder_graph(
                max_refinements=request.max_refinements,
                timeout_seconds=request.timeout_seconds,
            )

            # Track state for events
            state = {
                "user_request": request.request,
                "refinement_count": 0,
                "max_refinements": request.max_refinements,
            }

            # Phase 1: Plan
            yield f"data: {json.dumps({'type': 'plan_start'})}\n\n"
            plan = await graph.llm_client.plan(
                user_request=request.request,
                system_prompt="You are an expert Python developer. Generate a detailed implementation plan.",
            )
            state["plan"] = plan
            yield f"data: {json.dumps({'type': 'plan_complete', 'plan': plan})}\n\n"

            # Phase 2: Code
            yield f"data: {json.dumps({'type': 'code_start'})}\n\n"
            code = await graph.llm_client.code(
                prompt=f"User request: {request.request}\n\nPlan:\n{plan}\n\nGenerate complete Python code:",
                system_prompt="You are an expert Python developer. Generate clean, tested code.",
            )
            code = graph._clean_code_output(code)
            state["code"] = code
            yield f"data: {json.dumps({'type': 'code_complete', 'code': code})}\n\n"

            # Phase 3: Tests
            yield f"data: {json.dumps({'type': 'test_start'})}\n\n"
            test_code = await graph.llm_client.tests(
                prompt=f"Code:\n{code}\n\nGenerate pytest tests for the above code.",
                system_prompt="You are an expert Python developer. Generate comprehensive pytest tests.",
            )
            test_code = graph._clean_code_output(test_code)
            state["test_code"] = test_code
            yield f"data: {json.dumps({'type': 'test_complete', 'testCode': test_code})}\n\n"

            # Phase 4: Run tests (potentially multiple iterations with refinement)
            for iteration in range(request.max_refinements + 1):
                yield f"data: {json.dumps({'type': 'run_start', 'iteration': iteration})}\n\n"

                result = graph.test_runner.run_single_test(
                    code=state["code"],
                    test_code=state["test_code"],
                )

                # Emit test output
                if result.stdout:
                    yield f"data: {json.dumps({'type': 'run_output', 'stdout': result.stdout})}\n\n"
                if result.stderr:
                    yield f"data: {json.dumps({'type': 'run_output', 'stderr': result.stderr})}\n\n"

                yield f"data: {json.dumps({'type': 'run_complete', 'testsPassed': result.success, 'exitCode': result.exit_code})}\n\n"

                state["run_success"] = result.success
                state["run_stdout"] = result.stdout
                state["run_stderr"] = result.stderr

                # Track metrics
                test_pass_counter.labels(result="pass" if result.success else "fail").inc()

                if result.success:
                    break  # Tests passed, move to summary

                # Need to refine?
                if iteration < request.max_refinements:
                    state["refinement_count"] = iteration + 1
                    refinement_counter.inc()

                    yield f"data: {json.dumps({'type': 'refine_start', 'iteration': iteration + 1})}\n\n"

                    refined_code = await graph.llm_client.refine(
                        prompt=f"Original request: {request.request}\n\nCode that failed tests:\n{state['code']}\n\nError output:\n{result.stdout}\n{result.stderr}\n\nFix the code:",
                        system_prompt="You are an expert Python developer. Fix the code to pass tests.",
                    )
                    refined_code = graph._clean_code_output(refined_code)
                    state["code"] = refined_code

                    yield f"data: {json.dumps({'type': 'refine_complete', 'code': refined_code})}\n\n"

            # Phase 5: Summarize
            yield f"data: {json.dumps({'type': 'summary_start'})}\n\n"
            summary = await graph.llm_client.summarize(
                prompt=f"Request: {request.request}\nPlan: {state['plan']}\nTests passed: {state.get('run_success', False)}\n\nGenerate a markdown summary:",
                system_prompt="You are an expert technical writer. Create a clear summary with usage examples.",
            )
            state["summary"] = summary
            yield f"data: {json.dumps({'type': 'summary_complete', 'summary': summary})}\n\n"

            # Complete
            yield f"data: {json.dumps({'type': 'complete', 'success': True, 'testsPassed': state.get('run_success', False), 'refinementCount': state.get('refinement_count', 0)})}\n\n"

            # Track success
            generation_counter.labels(status="success" if state.get("run_success") else "failed").inc()

            logger.info(f"[{session_id}] Streaming complete: tests_passed={state.get('run_success')}")

        except Exception as exc:
            logger.error(f"[{session_id}] Streaming error: {exc}", exc_info=True)
            generation_counter.labels(status="error").inc()
            yield f"data: {json.dumps({'type': 'error', 'error': str(exc)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


# ==============================================================================
# Metrics
# ==============================================================================


@app.get("/metrics")
async def metrics():
    """
    Prometheus metrics endpoint.

    Returns metrics in Prometheus exposition format.
    """
    return generate_latest()


# ==============================================================================
# Error Handlers
# ==============================================================================


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Handle HTTP exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail},
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Handle unexpected exceptions."""
    logger.error(f"Unexpected error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"},
    )


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("CODER_PORT", "8092"))
    uvicorn.run(app, host="0.0.0.0", port=port)
