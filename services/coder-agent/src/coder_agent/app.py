"""
FastAPI application for coder-agent service.

Provides REST API for LLM-powered code generation with test-driven refinement.
"""

import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from prometheus_client import Counter, Histogram, generate_latest

from .graph import CoderGraph, create_coder_graph
from .llm_client import CoderLLMClient
from .models import GenerateCodeRequest, GenerateCodeResponse, HealthCheckResponse

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
