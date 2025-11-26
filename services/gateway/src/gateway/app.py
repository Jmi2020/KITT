from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from .middleware.remote_mode import RemoteModeMiddleware
from .routes.routing import router as routing_router
from .routes.token import router as token_router
# from .routes.devices import router as devices_router  # Temporarily disabled due to import conflict
from .routes.remote import router as remote_router
from .routes.vision import router as vision_router
from .routes.images import router as images_router
from .routes.fabrication import router as fabrication_router
from .routes.cad import router as cad_router
from .routes.coding import router as coding_router
from .routes.collective import router as collective_router
from .routes.io_control import router as io_control_router
from .routes.providers import router as providers_router
from .routes.research import router as research_router
from .routes.projects_local import router as projects_local_router
from .routes.brain_proxy import router as brain_proxy_router

app = FastAPI(title="KITTY Gateway")

# Add CORS middleware to allow web UI access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:4173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(RemoteModeMiddleware)
app.include_router(token_router)
app.include_router(routing_router)
# app.include_router(devices_router)  # Temporarily disabled due to import conflict
app.include_router(remote_router)
app.include_router(vision_router)
app.include_router(images_router)
app.include_router(fabrication_router)
app.include_router(cad_router)  # CAD generation and artifact serving
app.include_router(coding_router)
app.include_router(collective_router)
app.include_router(io_control_router)  # I/O Control Dashboard API
app.include_router(providers_router)  # Provider information
app.include_router(research_router)  # Research sessions and results
app.include_router(projects_local_router)  # Local STL listing/downloading
app.include_router(brain_proxy_router)  # Proxy to brain service (query, conversations, autonomy, etc.)

storage_root = Path(os.getenv("KITTY_STORAGE_ROOT", "storage"))
storage_root.mkdir(parents=True, exist_ok=True)
app.mount("/storage", StaticFiles(directory=storage_root), name="storage")


@app.get("/healthz")
async def health() -> dict[str, str]:
    """Basic health check for load balancer."""
    return {"status": "ok"}


@app.get("/health/detailed")
async def health_detailed() -> dict:
    """
    Detailed health check including backend connectivity.

    Used by monitoring systems to verify full system health.
    Load balancer uses /healthz for simple liveness check.
    """
    import httpx

    health_status = {
        "status": "healthy",
        "service": "gateway",
        "backends": {}
    }

    # Check brain service
    try:
        brain_url = os.getenv("UPSTREAM_BRAIN_URL", "http://brain:8000")
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(f"{brain_url}/health")
            health_status["backends"]["brain"] = {
                "status": "up" if response.status_code == 200 else "degraded",
                "url": brain_url
            }
    except Exception as e:
        health_status["backends"]["brain"] = {
            "status": "down",
            "error": str(e)
        }
        health_status["status"] = "degraded"

    # Check fabrication service
    try:
        fab_url = os.getenv("FABRICATION_BASE", "http://fabrication:8300")
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(f"{fab_url}/health")
            health_status["backends"]["fabrication"] = {
                "status": "up" if response.status_code == 200 else "degraded",
                "url": fab_url
            }
    except Exception as e:
        health_status["backends"]["fabrication"] = {
            "status": "down",
            "error": str(e)
        }

    # Check discovery service
    try:
        disc_url = os.getenv("DISCOVERY_BASE", "http://discovery:8500")
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(f"{disc_url}/health")
            health_status["backends"]["discovery"] = {
                "status": "up" if response.status_code == 200 else "degraded",
                "url": disc_url
            }
    except Exception as e:
        health_status["backends"]["discovery"] = {
            "status": "down",
            "error": str(e)
        }

    return health_status
