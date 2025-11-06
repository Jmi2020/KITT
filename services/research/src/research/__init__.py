"""Research service for web search and content analysis."""

from .citations import CitationTracker
from .search_tool import SearchTool
from .simhash import SimHashDeduplicator
from .web_tool import WebTool

__all__ = [
    "CitationTracker",
    "SearchTool",
    "SimHashDeduplicator",
    "WebTool",
]
