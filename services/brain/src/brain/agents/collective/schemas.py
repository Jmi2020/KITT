"""Schemas for two-phase collective proposal generation with search access.

This module defines the data models for the two-phase proposal process:
1. Phase 1: Specialists output structured search requests
2. Central Fetch: Orchestrator executes deduplicated searches
3. Phase 2: Specialists generate full proposals with search results
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    """A single search request from a specialist."""

    query: str = Field(
        ...,
        min_length=3,
        max_length=200,
        description="The search query to execute",
    )
    purpose: str = Field(
        ...,
        max_length=300,
        description="Why this search is needed for the proposal",
    )
    priority: int = Field(
        default=2,
        ge=1,
        le=3,
        description="Priority: 1=high (critical), 2=medium (helpful), 3=low (nice-to-have)",
    )


class Phase1Output(BaseModel):
    """Phase 1 output from a specialist - search requests and initial assessment."""

    specialist_id: str = Field(..., description="Identifier for the specialist")
    search_requests: List[SearchRequest] = Field(
        default_factory=list,
        max_length=3,
        description="Search queries needed (max 3)",
    )
    initial_assessment: str = Field(
        ...,
        max_length=1000,
        description="Brief initial analysis of the task (2-3 sentences)",
    )
    confidence_without_search: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence in providing a good answer without search (0.0-1.0)",
    )


@dataclass
class DeduplicatedSearch:
    """A deduplicated search query with metadata from all requesters."""

    query: str
    normalized_query: str
    requesting_specialists: List[str] = field(default_factory=list)
    max_priority: int = 3  # Lower is higher priority
    purposes: List[str] = field(default_factory=list)


@dataclass
class SearchResult:
    """Result from executing a search query."""

    query: str
    success: bool
    results: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None
    execution_time_ms: float = 0.0
    result_count: int = 0

    def __post_init__(self):
        if self.results:
            self.result_count = len(self.results)


class Phase2Input(BaseModel):
    """Input for Phase 2 proposal generation."""

    task: str = Field(..., description="The original task/question")
    kb_context: str = Field(..., description="Knowledge base context")
    search_results: str = Field(
        default="",
        description="Formatted search results from Phase 1 requests",
    )
    phase1_assessment: str = Field(
        default="",
        description="Initial assessment from Phase 1",
    )
    specialist_id: str = Field(..., description="Identifier for the specialist")


# JSON schema for Phase 1 structured output
PHASE1_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "search_requests": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "minLength": 3,
                        "maxLength": 200,
                        "description": "Search query to execute",
                    },
                    "purpose": {
                        "type": "string",
                        "maxLength": 300,
                        "description": "Why this search is needed",
                    },
                    "priority": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 3,
                        "description": "1=high, 2=medium, 3=low priority",
                    },
                },
                "required": ["query", "purpose"],
            },
            "maxItems": 3,
        },
        "initial_assessment": {
            "type": "string",
            "maxLength": 1000,
            "description": "Brief initial analysis (2-3 sentences)",
        },
        "confidence_without_search": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
            "description": "Confidence without search (0.0-1.0)",
        },
    },
    "required": ["search_requests", "initial_assessment", "confidence_without_search"],
}
