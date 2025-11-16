"""
Common validation schemas for research tools.

Provides Pydantic models for validating tool inputs/outputs.
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, HttpUrl
from datetime import datetime


class SourceDocument(BaseModel):
    """A source document with citation information"""
    url: str
    title: Optional[str] = None
    snippet: Optional[str] = None
    relevance_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    retrieved_at: Optional[datetime] = None


class SearchToolInput(BaseModel):
    """Input schema for web search tool"""
    query: str = Field(..., min_length=1, max_length=500)
    max_results: int = Field(10, ge=1, le=50)
    search_type: str = Field("general", pattern="^(general|academic|news|image)$")


class SearchToolOutput(BaseModel):
    """Output schema for web search tool"""
    query: str
    results: List[SourceDocument]
    total_found: int
    search_time_ms: float


class FetchToolInput(BaseModel):
    """Input schema for web page fetch tool"""
    url: str
    extract_text: bool = True
    max_length: int = Field(10000, ge=100, le=50000)


class FetchToolOutput(BaseModel):
    """Output schema for web page fetch tool"""
    url: str
    title: Optional[str] = None
    content: str
    word_count: int
    fetch_time_ms: float
    status_code: int = 200


class AnalysisToolInput(BaseModel):
    """Input schema for content analysis tool"""
    content: str = Field(..., min_length=10)
    analysis_type: str = Field("summary", pattern="^(summary|extract|qa|sentiment)$")
    target_length: Optional[int] = Field(None, ge=50, le=5000)
    query: Optional[str] = None  # For QA mode


class AnalysisToolOutput(BaseModel):
    """Output schema for content analysis tool"""
    original_length: int
    result: str
    analysis_type: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    processing_time_ms: float


class SynthesisToolInput(BaseModel):
    """Input schema for synthesis tool"""
    sources: List[SourceDocument]
    query: str
    synthesis_mode: str = Field("comprehensive", pattern="^(comprehensive|comparative|chronological)$")
    min_sources: int = Field(2, ge=1, le=20)


class SynthesisToolOutput(BaseModel):
    """Output schema for synthesis tool"""
    synthesis: str
    sources_used: List[str]  # URLs or source IDs
    confidence: float = Field(..., ge=0.0, le=1.0)
    completeness: float = Field(..., ge=0.0, le=1.0)
    citations: List[int] = []  # Citation indices


class ResearchFinding(BaseModel):
    """A structured research finding"""
    content: str = Field(..., min_length=10)
    sources: List[SourceDocument] = []
    confidence: float = Field(..., ge=0.0, le=1.0)
    importance: float = Field(..., ge=0.0, le=1.0)
    novelty: float = Field(..., ge=0.0, le=1.0)
    tags: List[str] = []
    timestamp: datetime = Field(default_factory=datetime.now)


class ToolExecutionContext(BaseModel):
    """Context passed to tool validators"""
    session_id: str
    query: str
    previous_results: Dict[str, Any] = {}
    budget_remaining: float
    external_calls_remaining: int


# Validation rule sets for FormatValidator
SEARCH_OUTPUT_RULES = {
    "query": {"type": str, "required": True, "min_length": 1},
    "results": {"type": list, "required": True},
    "total_found": {"type": int, "required": True, "min_value": 0},
    "search_time_ms": {"type": float, "required": True, "min_value": 0}
}

FETCH_OUTPUT_RULES = {
    "url": {"type": str, "required": True, "pattern": r"^https?://"},
    "content": {"type": str, "required": True, "min_length": 10},
    "word_count": {"type": int, "required": True, "min_value": 0},
    "status_code": {"type": int, "required": True, "min_value": 100, "max_value": 599}
}

ANALYSIS_OUTPUT_RULES = {
    "result": {"type": str, "required": True, "min_length": 10},
    "confidence": {"type": float, "required": True, "min_value": 0.0, "max_value": 1.0},
    "analysis_type": {"type": str, "required": True}
}

SYNTHESIS_OUTPUT_RULES = {
    "synthesis": {"type": str, "required": True, "min_length": 50},
    "sources_used": {"type": list, "required": True},
    "confidence": {"type": float, "required": True, "min_value": 0.0, "max_value": 1.0},
    "completeness": {"type": float, "required": True, "min_value": 0.0, "max_value": 1.0}
}
