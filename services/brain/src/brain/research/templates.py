"""
Research Templates

Pre-configured research strategies for common query patterns.
Templates optimize research configuration based on query type.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class ResearchTemplateType(str, Enum):
    """Types of research templates"""
    TECHNICAL_DOCS = "technical_docs"
    COMPARISON = "comparison"
    TROUBLESHOOTING = "troubleshooting"
    PRODUCT_RESEARCH = "product_research"
    ACADEMIC = "academic"
    QUICK_FACT = "quick_fact"
    DEEP_DIVE = "deep_dive"
    GENERAL = "general"


@dataclass
class ResearchTemplate:
    """Research template configuration"""
    name: str
    description: str
    strategy: str
    max_iterations: int
    min_sources: int
    min_confidence: float
    min_ragas_score: float
    saturation_threshold: float
    use_debate: bool
    search_keywords: Optional[list] = None
    preferred_tools: Optional[list] = None


# Template definitions
TEMPLATES: Dict[ResearchTemplateType, ResearchTemplate] = {
    ResearchTemplateType.TECHNICAL_DOCS: ResearchTemplate(
        name="Technical Documentation",
        description="Research technical documentation, APIs, libraries, and frameworks",
        strategy="comprehensive",
        max_iterations=5,
        min_sources=4,
        min_confidence=0.8,
        min_ragas_score=0.75,
        saturation_threshold=0.85,
        use_debate=False,
        search_keywords=["documentation", "API", "tutorial", "guide", "reference"],
        preferred_tools=["web_search", "web_fetch"]
    ),

    ResearchTemplateType.COMPARISON: ResearchTemplate(
        name="Comparison Research",
        description="Compare products, technologies, or approaches",
        strategy="comprehensive",
        max_iterations=7,
        min_sources=6,
        min_confidence=0.75,
        min_ragas_score=0.75,
        saturation_threshold=0.8,
        use_debate=True,  # Debate helps with balanced comparison
        search_keywords=["comparison", "vs", "versus", "difference", "pros and cons"],
        preferred_tools=["web_search", "web_fetch"]
    ),

    ResearchTemplateType.TROUBLESHOOTING: ResearchTemplate(
        name="Troubleshooting",
        description="Debug issues, find solutions to problems",
        strategy="focused",
        max_iterations=5,
        min_sources=3,
        min_confidence=0.7,
        min_ragas_score=0.7,
        saturation_threshold=0.75,
        use_debate=False,
        search_keywords=["error", "fix", "solution", "troubleshoot", "issue", "problem"],
        preferred_tools=["web_search", "web_fetch"]
    ),

    ResearchTemplateType.PRODUCT_RESEARCH: ResearchTemplate(
        name="Product Research",
        description="Research products, reviews, specifications",
        strategy="comprehensive",
        max_iterations=6,
        min_sources=5,
        min_confidence=0.75,
        min_ragas_score=0.75,
        saturation_threshold=0.8,
        use_debate=False,
        search_keywords=["review", "specs", "specifications", "price", "features"],
        preferred_tools=["web_search", "web_fetch"]
    ),

    ResearchTemplateType.ACADEMIC: ResearchTemplate(
        name="Academic Research",
        description="Research academic topics, papers, theories",
        strategy="comprehensive",
        max_iterations=8,
        min_sources=7,
        min_confidence=0.85,
        min_ragas_score=0.8,
        saturation_threshold=0.85,
        use_debate=True,  # Debate helps verify academic claims
        search_keywords=["paper", "study", "research", "journal", "academic"],
        preferred_tools=["web_search", "web_fetch"]
    ),

    ResearchTemplateType.QUICK_FACT: ResearchTemplate(
        name="Quick Fact Check",
        description="Fast fact checking and simple queries",
        strategy="focused",
        max_iterations=2,
        min_sources=2,
        min_confidence=0.7,
        min_ragas_score=0.7,
        saturation_threshold=0.7,
        use_debate=False,
        search_keywords=None,  # No specific keywords
        preferred_tools=["web_search"]
    ),

    ResearchTemplateType.DEEP_DIVE: ResearchTemplate(
        name="Deep Dive",
        description="Comprehensive research on complex topics",
        strategy="comprehensive",
        max_iterations=10,
        min_sources=10,
        min_confidence=0.85,
        min_ragas_score=0.8,
        saturation_threshold=0.9,
        use_debate=True,
        search_keywords=None,  # No specific keywords
        preferred_tools=["web_search", "web_fetch"]
    ),

    ResearchTemplateType.GENERAL: ResearchTemplate(
        name="General Research",
        description="General purpose research for most queries",
        strategy="balanced",
        max_iterations=5,
        min_sources=4,
        min_confidence=0.75,
        min_ragas_score=0.75,
        saturation_threshold=0.8,
        use_debate=False,
        search_keywords=None,
        preferred_tools=["web_search", "web_fetch"]
    ),
}


class TemplateSelector:
    """Automatically select appropriate research template based on query"""

    @staticmethod
    def detect_template(query: str) -> ResearchTemplateType:
        """
        Detect appropriate research template from query.

        Args:
            query: Research query

        Returns:
            Best matching template type
        """
        query_lower = query.lower()

        # Technical documentation indicators
        if any(kw in query_lower for kw in ["api", "documentation", "docs", "library", "framework", "sdk", "how to", "tutorial"]):
            return ResearchTemplateType.TECHNICAL_DOCS

        # Comparison indicators
        if any(kw in query_lower for kw in ["vs", "versus", "compare", "comparison", "difference between", "which is better"]):
            return ResearchTemplateType.COMPARISON

        # Troubleshooting indicators
        if any(kw in query_lower for kw in ["error", "fix", "not working", "issue", "problem", "troubleshoot", "debug", "broken"]):
            return ResearchTemplateType.TROUBLESHOOTING

        # Product research indicators
        if any(kw in query_lower for kw in ["review", "price", "buy", "best", "top", "product", "recommendation"]):
            return ResearchTemplateType.PRODUCT_RESEARCH

        # Academic indicators
        if any(kw in query_lower for kw in ["research", "study", "paper", "theory", "academic", "journal", "scientific"]):
            return ResearchTemplateType.ACADEMIC

        # Quick fact indicators
        if any(kw in query_lower for kw in ["what is", "who is", "when did", "where is", "define"]) and len(query.split()) < 10:
            return ResearchTemplateType.QUICK_FACT

        # Deep dive indicators
        if any(kw in query_lower for kw in ["comprehensive", "detailed", "in-depth", "deep dive", "everything about"]):
            return ResearchTemplateType.DEEP_DIVE

        # Default to general
        return ResearchTemplateType.GENERAL

    @staticmethod
    def get_template(template_type: ResearchTemplateType) -> ResearchTemplate:
        """
        Get template by type.

        Args:
            template_type: Template type

        Returns:
            Research template configuration
        """
        return TEMPLATES.get(template_type, TEMPLATES[ResearchTemplateType.GENERAL])

    @staticmethod
    def get_config_overrides(template: ResearchTemplate) -> Dict[str, Any]:
        """
        Get configuration overrides from template.

        Args:
            template: Research template

        Returns:
            Configuration dictionary
        """
        config = {
            "strategy": template.strategy,
            "max_iterations": template.max_iterations,
            "min_sources": template.min_sources,
            "min_confidence": template.min_confidence,
            "min_ragas_score": template.min_ragas_score,
            "saturation_threshold": template.saturation_threshold,
            "use_debate": template.use_debate,
        }

        if template.search_keywords:
            config["search_keywords"] = template.search_keywords

        if template.preferred_tools:
            config["preferred_tools"] = template.preferred_tools

        return config


def apply_template(query: str, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Apply appropriate template to query and merge with provided config.

    Args:
        query: Research query
        config: Optional user-provided configuration (overrides template)

    Returns:
        Merged configuration with template applied
    """
    # Detect template
    template_type = TemplateSelector.detect_template(query)
    template = TemplateSelector.get_template(template_type)

    logger.info(f"Selected template: {template.name} for query: {query[:50]}...")

    # Get template config
    template_config = TemplateSelector.get_config_overrides(template)

    # Merge with user config (user config takes precedence)
    if config:
        template_config.update(config)

    # Add template metadata
    template_config["template"] = {
        "type": template_type.value,
        "name": template.name,
        "description": template.description,
    }

    return template_config


__all__ = [
    "ResearchTemplateType",
    "ResearchTemplate",
    "TemplateSelector",
    "apply_template",
    "TEMPLATES",
]
