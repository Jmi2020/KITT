"""
Multi-layer validation for research tools and outputs.

Provides:
- Schema validation (Pydantic)
- Format validation
- Quality validation
- Hallucination detection
- Chain validation (tool output compatibility)
"""

__version__ = "0.1.0"

from .pipeline import (
    ValidationPipeline,
    ValidationResult,
    ValidationIssue,
    ValidationSeverity,
    BaseValidator,
    SchemaValidator,
    FormatValidator,
    QualityValidator,
    HallucinationDetector,
    ChainValidator,
    create_research_output_pipeline,
)

from .schemas import (
    SourceDocument,
    SearchToolInput,
    SearchToolOutput,
    FetchToolInput,
    FetchToolOutput,
    AnalysisToolInput,
    AnalysisToolOutput,
    SynthesisToolInput,
    SynthesisToolOutput,
    ResearchFinding,
    ToolExecutionContext,
    SEARCH_OUTPUT_RULES,
    FETCH_OUTPUT_RULES,
    ANALYSIS_OUTPUT_RULES,
    SYNTHESIS_OUTPUT_RULES,
)

__all__ = [
    # Pipeline classes
    "ValidationPipeline",
    "ValidationResult",
    "ValidationIssue",
    "ValidationSeverity",
    "BaseValidator",
    "SchemaValidator",
    "FormatValidator",
    "QualityValidator",
    "HallucinationDetector",
    "ChainValidator",
    "create_research_output_pipeline",
    # Schemas
    "SourceDocument",
    "SearchToolInput",
    "SearchToolOutput",
    "FetchToolInput",
    "FetchToolOutput",
    "AnalysisToolInput",
    "AnalysisToolOutput",
    "SynthesisToolInput",
    "SynthesisToolOutput",
    "ResearchFinding",
    "ToolExecutionContext",
    # Format rules
    "SEARCH_OUTPUT_RULES",
    "FETCH_OUTPUT_RULES",
    "ANALYSIS_OUTPUT_RULES",
    "SYNTHESIS_OUTPUT_RULES",
]
