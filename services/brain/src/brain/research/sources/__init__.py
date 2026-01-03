"""
Academic source integration for paper harvesting.

This module provides clients for harvesting papers from various academic sources:
- arXiv (free, no API key required)
- Semantic Scholar (free tier: 100 req/5min)
- PubMed Central (free with API key for higher limits)
- CORE (free tier available)
"""

from .base import (
    AcademicSource,
    PaperMetadata,
    RateLimitConfig,
    SourcePriority,
)
from .arxiv import ArxivSource
from .semantic_scholar import SemanticScholarSource
from .pubmed import PubMedSource
from .core import CORESource
from .registry import (
    SourceRegistry,
    get_source_registry,
)

__all__ = [
    # Base classes
    "AcademicSource",
    "PaperMetadata",
    "RateLimitConfig",
    "SourcePriority",
    # Source implementations
    "ArxivSource",
    "SemanticScholarSource",
    "PubMedSource",
    "CORESource",
    # Registry
    "SourceRegistry",
    "get_source_registry",
]
