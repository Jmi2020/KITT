"""KITTY integration modules for kitty-code."""

from __future__ import annotations

from kitty_code.integrations.mcp_kitty import (
    KITTY_MCP_SERVERS,
    discover_kitty_services,
    get_all_kitty_mcp_servers,
    get_kitty_mcp_servers,
    is_kitty_environment,
)

__all__ = [
    "KITTY_MCP_SERVERS",
    "discover_kitty_services",
    "get_all_kitty_mcp_servers",
    "get_kitty_mcp_servers",
    "is_kitty_environment",
]
