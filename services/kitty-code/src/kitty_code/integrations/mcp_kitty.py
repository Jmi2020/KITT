"""
KITTY MCP server integration for kitty-code.

Auto-discovers and configures KITTY services as MCP servers when running
in the KITTY environment. Users can enable/disable individual services
via the config file.

This module provides full MCP server support (HTTP and STDIO transports)
like mistral-vibe, enabling kitty-code to connect to external MCP servers.
"""

from __future__ import annotations

import os
from pathlib import Path

import httpx

# Import directly from config module to avoid triggering full agent stack
from kitty_code.core.config import MCPHttp  # noqa: E402


def is_kitty_environment() -> bool:
    """
    Check if we're running in a KITTY environment.

    Returns True if:
    - KITTY_USER_ID env var is set
    - KITTY project directory exists
    - Running from within KITTY services directory
    """
    # Check env var
    if os.getenv("KITTY_USER_ID"):
        return True

    # Check if KITTY project exists
    kitty_path = Path("/Users/Shared/Coding/KITT")
    if kitty_path.exists() and (kitty_path / ".env").exists():
        return True

    # Check if running from KITTY directory
    cwd = Path.cwd()
    if "KITT" in str(cwd) and (cwd / "services").exists():
        return True

    return False


# Pre-defined KITTY MCP server configurations
KITTY_MCP_SERVERS: list[dict] = [
    {
        "name": "kitty_brain",
        "transport": "http",
        "url": "http://localhost:8000/mcp",
        "prompt": "KITTY brain service for orchestration, queries, and tool routing",
    },
    {
        "name": "kitty_cad",
        "transport": "http",
        "url": "http://localhost:8200/mcp",
        "prompt": "CAD generation via Zoo, Tripo, and CadQuery",
    },
    {
        "name": "kitty_fab",
        "transport": "http",
        "url": "http://localhost:8300/mcp",
        "prompt": "Fabrication control for 3D printers and CNC machines",
    },
    {
        "name": "kitty_mem",
        "transport": "http",
        "url": "http://localhost:8765/mcp",
        "prompt": "Semantic memory with vector embeddings (Mem0)",
    },
    {
        "name": "kitty_discovery",
        "transport": "http",
        "url": "http://localhost:8500/mcp",
        "prompt": "Network device discovery and scanning",
    },
]


async def discover_kitty_services(timeout: float = 1.0) -> list[dict]:
    """
    Discover which KITTY services are currently running and healthy.

    Args:
        timeout: HTTP request timeout in seconds

    Returns:
        List of MCP server configs for healthy services
    """
    if not is_kitty_environment():
        return []

    available = []

    async with httpx.AsyncClient(timeout=timeout) as client:
        for server in KITTY_MCP_SERVERS:
            try:
                # Check health endpoint (MCP servers typically have /health or /healthz)
                health_url = server["url"].replace("/mcp", "/healthz")
                resp = await client.get(health_url)

                if resp.status_code == 200:
                    available.append(server)

            except (httpx.ConnectError, httpx.TimeoutException):
                # Service not running
                pass
            except Exception:
                # Other errors - skip this service
                pass

    return available


def discover_kitty_services_sync(timeout: float = 1.0) -> list[dict]:
    """
    Synchronous version of discover_kitty_services.

    For use in non-async contexts like config loading.
    """
    if not is_kitty_environment():
        return []

    available = []

    with httpx.Client(timeout=timeout) as client:
        for server in KITTY_MCP_SERVERS:
            try:
                health_url = server["url"].replace("/mcp", "/healthz")
                resp = client.get(health_url)

                if resp.status_code == 200:
                    available.append(server)

            except (httpx.ConnectError, httpx.TimeoutException):
                pass
            except Exception:
                pass

    return available


def get_kitty_mcp_config() -> list[dict]:
    """
    Get MCP server configurations for available KITTY services.

    This is the main entry point for integrating KITTY services.
    Returns configs suitable for adding to KittyCodeConfig.mcp_servers.

    DEPRECATED: Use get_kitty_mcp_servers() instead which returns MCPHttp objects.
    """
    return discover_kitty_services_sync()


def get_kitty_mcp_servers() -> list[MCPHttp]:
    """
    Return discovered KITTY services as MCPHttp objects.

    This is the preferred method for integrating KITTY services with the
    ToolManager. Returns properly typed MCPHttp objects that can be directly
    added to KittyCodeConfig.mcp_servers.

    Returns:
        List of MCPHttp objects for healthy KITTY services
    """
    servers: list[MCPHttp] = []
    for srv in discover_kitty_services_sync():
        servers.append(
            MCPHttp(
                name=srv["name"],
                transport="http",
                url=srv["url"],
                prompt=srv.get("prompt", ""),
            )
        )
    return servers


def get_all_kitty_mcp_servers() -> list[MCPHttp]:
    """
    Return all KITTY MCP server configurations as MCPHttp objects.

    Unlike get_kitty_mcp_servers(), this returns all known servers without
    checking if they're currently healthy. Useful for configuration display
    or when you want to attempt connection regardless of health status.

    Returns:
        List of MCPHttp objects for all known KITTY services
    """
    if not is_kitty_environment():
        return []

    return [
        MCPHttp(
            name=srv["name"],
            transport="http",
            url=srv["url"],
            prompt=srv.get("prompt", ""),
        )
        for srv in KITTY_MCP_SERVERS
    ]
