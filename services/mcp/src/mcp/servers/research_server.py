# noqa: D401
"""Research MCP Server providing web search and content analysis tools."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict

# Add services/research to path
research_path = Path(__file__).parent.parent.parent.parent.parent / "research" / "src"
if str(research_path) not in sys.path:
    sys.path.insert(0, str(research_path))

try:
    from research import CitationTracker, SearchTool, SimHashDeduplicator, WebTool
except ImportError:
    # Research service not available - disable tools
    SearchTool = WebTool = SimHashDeduplicator = CitationTracker = None  # type: ignore[assignment, misc]

from ..server import MCPServer, ResourceDefinition, ToolDefinition, ToolResult

logger = logging.getLogger(__name__)


class ResearchMCPServer(MCPServer):
    """MCP server for web research and content analysis.

    Provides tools for:
    - Web search using DuckDuckGo
    - Web page fetching and parsing
    - Content deduplication with SimHash
    - Citation tracking for source attribution

    These tools enable the ReAct agent to perform web research with
    proper source tracking and deduplication.
    """

    def __init__(self, perplexity_client: Any = None) -> None:
        """Initialize Research MCP server.

        Args:
            perplexity_client: Optional Perplexity MCP client for premium web search.
                              If provided, web_search will try Perplexity first, then fallback to DuckDuckGo.
        """
        super().__init__(
            name="research",
            description="Web research and content analysis tools with citation tracking",
        )

        # Initialize research tools
        searx_base = os.getenv("SEARXNG_BASE_URL")
        brave_key = os.getenv("BRAVE_SEARCH_API_KEY")
        self._search_tool = (
            SearchTool(searxng_url=searx_base, brave_api_key=brave_key)
            if SearchTool
            else None
        )
        self._web_tool = WebTool() if WebTool else None
        self._deduplicator = SimHashDeduplicator() if SimHashDeduplicator else None
        self._citations = CitationTracker() if CitationTracker else None

        # Optional Perplexity client for premium search
        self._perplexity_client = perplexity_client

        # Register tools if available
        if self._search_tool and self._web_tool:
            self._register_tools()
            self._register_resources()

    def _register_tools(self) -> None:
        """Register research tools."""
        # web_search tool (DuckDuckGo - free, fast)
        self.register_tool(
            ToolDefinition(
                name="web_search",
                description=(
                    "Search the web using DuckDuckGo (free). Returns list of search results with titles, URLs, and descriptions. "
                    "Use this for quick, general web searches. For deeper research requiring RAG-augmented analysis, use research_deep instead. "
                    "Automatically deduplicates similar results using SimHash."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query string (e.g., 'llama.cpp Metal GPU optimization')",
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of results to return (default: 10)",
                            "minimum": 1,
                            "maximum": 20,
                            "default": 10,
                        },
                    },
                    "required": ["query"],
                },
            )
        )

        # research_deep tool (Perplexity - paid, deep research)
        if self._perplexity_client:
            self.register_tool(
                ToolDefinition(
                    name="research_deep",
                    description=(
                        "Perform deep research using Perplexity AI (paid API, uses credits). "
                        "Provides RAG-augmented, synthesized answers with web sources. "
                        "Use this when web_search results are insufficient or when you need comprehensive, "
                        "authoritative information with citation-backed analysis. "
                        "Cost: ~$0.001-0.005 per query."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Research query requiring deep analysis (e.g., 'comprehensive comparison of Metal vs CUDA GPU acceleration for LLM inference')",
                            },
                        },
                        "required": ["query"],
                    },
                )
            )

        # fetch_webpage tool
        self.register_tool(
            ToolDefinition(
                name="fetch_webpage",
                description=(
                    "Fetch and parse a web page into clean markdown content. "
                    "Extracts title, description, author, and main content while removing ads, navigation, and scripts. "
                    "Use this after web_search to read the actual content of relevant pages. "
                    "Automatically tracks citations for source attribution."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "URL of the web page to fetch (must be http:// or https://)",
                        },
                    },
                    "required": ["url"],
                },
            )
        )

        # get_citations tool
        self.register_tool(
            ToolDefinition(
                name="get_citations",
                description=(
                    "Get formatted citations for all sources used in current research session. "
                    "Returns citations in markdown format with titles, URLs, authors, and access dates. "
                    "Use this to provide proper source attribution in your response."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "format": {
                            "type": "string",
                            "description": "Citation format: 'markdown' or 'bibtex' (default: markdown)",
                            "enum": ["markdown", "bibtex"],
                            "default": "markdown",
                        },
                        "max_citations": {
                            "type": "integer",
                            "description": "Maximum number of citations to return (default: all)",
                            "minimum": 1,
                        },
                    },
                },
            )
        )

        # reset_research_session tool
        self.register_tool(
            ToolDefinition(
                name="reset_research_session",
                description=(
                    "Clear all research session data including citations and deduplication cache. "
                    "Use this to start a fresh research session for a new query."
                ),
                parameters={"type": "object", "properties": {}},
            )
        )

    def _register_resources(self) -> None:
        """Register research resources."""
        self.register_resource(
            ResourceDefinition(
                uri="research://stats",
                name="Research Session Statistics",
                description="Current research session statistics including citation count and deduplication metrics",
                mime_type="application/json",
            )
        )

    async def execute_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> ToolResult:
        """Execute a research tool.

        Args:
            tool_name: Name of the tool to execute
            arguments: Tool arguments

        Returns:
            ToolResult with success status and data
        """
        if not self._search_tool or not self._web_tool:
            return ToolResult(
                success=False,
                error="Research tools not available - research service not installed",
                metadata={"tool": tool_name},
            )

        try:
            if tool_name == "web_search":
                return await self._web_search(arguments)
            elif tool_name == "research_deep":
                return await self._research_deep(arguments)
            elif tool_name == "fetch_webpage":
                return await self._fetch_webpage(arguments)
            elif tool_name == "get_citations":
                return await self._get_citations(arguments)
            elif tool_name == "reset_research_session":
                return await self._reset_research_session(arguments)
            else:
                return ToolResult(
                    success=False,
                    error=f"Unknown tool: {tool_name}",
                    metadata={"tool": tool_name},
                )

        except Exception as exc:  # noqa: BLE001
            logger.error("Error executing tool %s: %s", tool_name, exc)
            return ToolResult(
                success=False,
                error=f"Tool execution failed: {str(exc)}",
                metadata={"tool": tool_name, "exception": str(exc)},
            )

    async def _web_search(self, arguments: Dict[str, Any]) -> ToolResult:
        """Execute web search using DuckDuckGo.

        Args:
            arguments: Tool arguments with 'query' and optional 'max_results'

        Returns:
            ToolResult with search results
        """
        query = arguments["query"]
        max_results = arguments.get("max_results", 10)

        logger.info("web_search for: %s", query)
        search_result = await self._search_tool.search(query, max_results=max_results)

        if not search_result["success"]:
            return ToolResult(
                success=False,
                error=search_result.get("error", "Search failed"),
                metadata={"query": query},
            )

        provider = (search_result.get("metadata") or {}).get("provider", "duckduckgo")

        # Filter duplicates using SimHash
        results = search_result["results"]
        filtered_results = []

        for result in results:
            url = result["url"]
            description = result["description"]

            # Check if content is duplicate
            if self._deduplicator.is_duplicate(description, url):
                continue

            # Add to deduplicator
            self._deduplicator.add(description, url)
            filtered_results.append(result)

        enriched_results = []
        for entry in filtered_results[:3]:
            content_snippet = None
            fetch_result = await self._web_tool.fetch(entry["url"])
            if fetch_result["success"]:
                content_snippet = fetch_result.get("content")
            enriched_results.append(
                {
                    **entry,
                    "content_snippet": content_snippet,
                }
            )

        return ToolResult(
            success=True,
            data={
                "query": query,
                "results": enriched_results,
                "total_results": len(filtered_results),
                "filtered_count": len(results) - len(filtered_results),
                "provider": provider,
            },
            metadata={
                "tool": "web_search",
                "query": query,
                "total_found": len(results),
                "after_dedup": len(filtered_results),
                "provider": provider,
            },
        )

    async def _research_deep(self, arguments: Dict[str, Any]) -> ToolResult:
        """Execute deep research using Perplexity AI.

        Args:
            arguments: Tool arguments with 'query'

        Returns:
            ToolResult with research findings
        """
        query = arguments["query"]

        if not self._perplexity_client:
            return ToolResult(
                success=False,
                error="Perplexity API not configured (requires PERPLEXITY_API_KEY)",
                metadata={"query": query},
            )

        try:
            logger.info("Perplexity deep research for: %s", query)
            perplexity_result = await self._perplexity_client.query({"query": query})

            if not perplexity_result or not perplexity_result.get("output"):
                return ToolResult(
                    success=False,
                    error="Perplexity returned empty response",
                    metadata={"query": query},
                )

            output = perplexity_result["output"]
            raw = perplexity_result.get("raw", {})

            # Extract citations from multiple possible locations
            citations = (
                raw.get("citations", []) or
                (raw.get("choices", [{}])[0].get("metadata", {}).get("citations", []) if raw.get("choices") else [])
            )

            # Extract usage data for cost tracking
            usage = raw.get("usage", {})

            logger.info("Perplexity research completed (%d chars, %d citations, %d tokens)",
                       len(output), len(citations), usage.get("total_tokens", 0))

            return ToolResult(
                success=True,
                data={
                    "query": query,
                    "research": output,
                    "source": "perplexity",
                    "citations": citations,
                    "usage": usage,
                },
                metadata={
                    "tool": "research_deep",
                    "query": query,
                    "content_length": len(output),
                    "citation_count": len(citations),
                    "tokens_used": usage.get("total_tokens", 0),
                },
            )

        except Exception as exc:  # noqa: BLE001
            logger.error("Perplexity research failed: %s", exc)
            return ToolResult(
                success=False,
                error=f"Perplexity API error: {str(exc)}",
                metadata={"query": query, "exception": str(exc)},
            )

    async def _fetch_webpage(self, arguments: Dict[str, Any]) -> ToolResult:
        """Fetch and parse web page.

        Args:
            arguments: Tool arguments with 'url'

        Returns:
            ToolResult with page content
        """
        url = arguments["url"]

        # Fetch page
        fetch_result = await self._web_tool.fetch(url)

        if not fetch_result["success"]:
            return ToolResult(
                success=False,
                error=fetch_result.get("error", "Fetch failed"),
                metadata={"url": url},
            )

        # Extract content
        title = fetch_result["title"]
        description = fetch_result["description"]
        author = fetch_result["author"]
        content = fetch_result["content"]

        # Add citation
        citation = self._citations.add_citation(
            url=url,
            title=title,
            description=description,
            author=author,
            relevance_score=1.0,  # Can be enhanced with relevance scoring
        )

        return ToolResult(
            success=True,
            data={
                "url": url,
                "title": title,
                "description": description,
                "author": author,
                "content": content,
                "citation_added": True,
            },
            metadata={
                "tool": "fetch_webpage",
                "url": url,
                "content_length": len(content),
            },
        )

    async def _get_citations(self, arguments: Dict[str, Any]) -> ToolResult:
        """Get formatted citations.

        Args:
            arguments: Tool arguments with optional 'format' and 'max_citations'

        Returns:
            ToolResult with formatted citations
        """
        format_type = arguments.get("format", "markdown")
        max_citations = arguments.get("max_citations")

        # Get citations
        if format_type == "markdown":
            citations_text = self._citations.to_markdown(max_citations=max_citations)
        elif format_type == "bibtex":
            citations_text = self._citations.to_bibtex(max_citations=max_citations)
        else:
            return ToolResult(
                success=False,
                error=f"Unknown format: {format_type}",
                metadata={},
            )

        # Get stats
        stats = self._citations.get_stats()

        return ToolResult(
            success=True,
            data={
                "citations": citations_text,
                "format": format_type,
                "stats": stats,
            },
            metadata={"tool": "get_citations", "total_citations": stats["total_citations"]},
        )

    async def _reset_research_session(self, arguments: Dict[str, Any]) -> ToolResult:
        """Reset research session.

        Args:
            arguments: Tool arguments (none required)

        Returns:
            ToolResult with success status
        """
        # Reset deduplicator
        self._deduplicator.reset()

        # Reset citations
        self._citations.reset()

        return ToolResult(
            success=True,
            data={"message": "Research session reset successfully"},
            metadata={"tool": "reset_research_session"},
        )

    async def fetch_resource(self, uri: str) -> Dict[str, Any]:
        """Fetch research session statistics.

        Args:
            uri: Resource URI (e.g., 'research://stats')

        Returns:
            Resource data dictionary

        Raises:
            ValueError: If resource not found
        """
        if uri == "research://stats":
            return {
                "deduplication": self._deduplicator.get_stats() if self._deduplicator else {},
                "citations": self._citations.get_stats() if self._citations else {},
            }

        raise ValueError(f"Resource not found: {uri}")

    def get_tool(self, tool_name: str) -> ToolDefinition | None:
        """Get tool definition by name.

        Args:
            tool_name: Tool name

        Returns:
            ToolDefinition if found, None otherwise
        """
        return self._tools.get(tool_name)


__all__ = ["ResearchMCPServer"]
