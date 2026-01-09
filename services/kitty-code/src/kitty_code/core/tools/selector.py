"""Semantic tool selection for kitty-code.

Reduces context usage by only loading tools relevant to the user's query.
Uses keyword matching to determine which tool categories are needed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kitty_code.core.llm.types import AvailableTool


@dataclass
class ToolCategory:
    """A category of tools with associated keywords."""

    name: str
    keywords: list[str]
    patterns: list[re.Pattern] = field(default_factory=list)
    tool_prefixes: list[str] = field(default_factory=list)  # MCP server prefixes

    def matches(self, query: str) -> bool:
        """Check if query matches this category."""
        query_lower = query.lower()

        # Check keywords
        for kw in self.keywords:
            if kw in query_lower:
                return True

        # Check regex patterns
        for pattern in self.patterns:
            if pattern.search(query_lower):
                return True

        return False


# Define tool categories with keywords that trigger them
TOOL_CATEGORIES = [
    ToolCategory(
        name="search",
        keywords=[
            "search", "find", "look up", "lookup", "google", "research",
            "what is", "who is", "when did", "latest", "current", "news",
            "perplexity", "web search"
        ],
        tool_prefixes=["perplexity", "kitty_brain"],
    ),
    ToolCategory(
        name="filesystem",
        keywords=[
            "file", "files", "folder", "directory", "read", "write", "save",
            "create file", "edit file", "open", "path", "desktop", "downloads"
        ],
        tool_prefixes=["filesystem", "read_file", "write_file", "search_replace"],
    ),
    ToolCategory(
        name="code",
        keywords=[
            "code", "program", "function", "class", "debug", "fix", "implement",
            "refactor", "test", "compile", "run", "execute", "script", "grep"
        ],
        tool_prefixes=["bash", "grep", "read_file", "write_file", "search_replace"],
    ),
    ToolCategory(
        name="browser",
        keywords=[
            "browser", "chrome", "webpage", "website", "click", "navigate",
            "screenshot", "devtools", "inspect", "dom", "html"
        ],
        tool_prefixes=["chrome", "devtools"],
    ),
    ToolCategory(
        name="memory",
        keywords=[
            "remember", "memory", "recall", "store", "save for later",
            "knowledge", "note", "memorize"
        ],
        tool_prefixes=["memory", "kitty_mem", "mem0"],
    ),
    ToolCategory(
        name="cad",
        keywords=[
            "cad", "3d", "model", "design", "stl", "mesh", "print", "fabricate",
            "part", "object", "shape"
        ],
        tool_prefixes=["kitty_cad", "cad"],
    ),
    ToolCategory(
        name="fabrication",
        keywords=[
            "print", "printer", "3d print", "cnc", "fabricate", "manufacture",
            "slice", "gcode", "bed", "nozzle"
        ],
        tool_prefixes=["kitty_fab", "fab"],
    ),
    ToolCategory(
        name="discovery",
        keywords=[
            "network", "device", "scan", "discover", "ip", "hostname",
            "iot", "smart home", "home assistant"
        ],
        tool_prefixes=["kitty_discovery", "discovery"],
    ),
    ToolCategory(
        name="security",
        keywords=[
            "security", "scan", "nmap", "vulnerability", "pentest", "exploit",
            "hexstrike", "nuclei", "sqlmap", "nikto", "gobuster", "burp",
            "recon", "osint", "ctf", "hack", "port scan", "web security",
            "cloud security", "binary analysis", "forensics"
        ],
        tool_prefixes=["hexstrike"],
    ),
]

# Tools that should always be available (core functionality)
ALWAYS_AVAILABLE_PREFIXES = [
    "bash",
    "grep",
    "read_file",
    "write_file",
    "search_replace",
    "todo",
]

# Categories where bash should be excluded (has dedicated tools)
EXCLUDE_BASH_CATEGORIES = {"search", "browser"}

# Maximum tools to include (to stay under context limits)
# Reduced from 20 to 10 to avoid context overflow with large tool schemas
MAX_TOOLS = 10


class ToolSelector:
    """Selects relevant tools based on user query."""

    def __init__(
        self,
        categories: list[ToolCategory] | None = None,
        always_available: list[str] | None = None,
        max_tools: int = MAX_TOOLS,
    ):
        self.categories = categories or TOOL_CATEGORIES
        self.always_available = always_available or ALWAYS_AVAILABLE_PREFIXES
        self.max_tools = max_tools

    def select_tools(
        self,
        query: str,
        available_tools: list[AvailableTool],
    ) -> list[AvailableTool]:
        """Select tools relevant to the query.

        Args:
            query: The user's query
            available_tools: All available tools

        Returns:
            Filtered list of relevant tools
        """
        if not query or not available_tools:
            return available_tools[:self.max_tools]

        # Find matching categories
        matching_categories = [cat for cat in self.categories if cat.matches(query)]
        matching_names = {cat.name for cat in matching_categories}

        # Check if we should exclude bash (when dedicated tools exist)
        exclude_bash = bool(matching_names & EXCLUDE_BASH_CATEGORIES)

        # Collect relevant tool prefixes
        relevant_prefixes = set(self.always_available)
        for cat in matching_categories:
            relevant_prefixes.update(cat.tool_prefixes)

        # Remove bash when dedicated tools exist for the query type
        if exclude_bash:
            relevant_prefixes.discard("bash")

        # Filter tools
        selected = []
        for tool in available_tools:
            tool_name = tool.function.name.lower()

            # Check if tool matches any relevant prefix
            for prefix in relevant_prefixes:
                if tool_name.startswith(prefix.lower()) or prefix.lower() in tool_name:
                    selected.append(tool)
                    break

        # If no specific matches, include all always-available tools
        if not selected:
            for tool in available_tools:
                tool_name = tool.function.name.lower()
                for prefix in self.always_available:
                    if tool_name.startswith(prefix.lower()):
                        selected.append(tool)
                        break

        # Enforce max tools limit
        return selected[:self.max_tools]

    def get_matched_categories(self, query: str) -> list[str]:
        """Get names of categories matching the query (for debugging)."""
        return [cat.name for cat in self.categories if cat.matches(query)]


# Global instance
_selector: ToolSelector | None = None


def get_tool_selector() -> ToolSelector:
    """Get the global tool selector instance."""
    global _selector
    if _selector is None:
        _selector = ToolSelector()
    return _selector


def select_tools_for_query(
    query: str,
    available_tools: list[AvailableTool],
) -> list[AvailableTool]:
    """Convenience function to select tools for a query."""
    return get_tool_selector().select_tools(query, available_tools)
