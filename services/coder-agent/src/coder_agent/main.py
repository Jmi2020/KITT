"""
Main entry point for coder-agent service.

Runs FastAPI application with uvicorn.
"""

import os

import uvicorn

if __name__ == "__main__":
    port = int(os.getenv("CODER_PORT", "8092"))
    host = os.getenv("CODER_HOST", "0.0.0.0")
    workers = int(os.getenv("CODER_WORKERS", "1"))

    uvicorn.run(
        "coder_agent.app:app",
        host=host,
        port=port,
        workers=workers,
        log_level="info",
    )
