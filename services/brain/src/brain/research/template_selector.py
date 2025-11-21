"""Template selection for research pipeline (resolves ethics/academic/product mismatches)."""

from __future__ import annotations

import logging
import re
from typing import Dict, List

logger = logging.getLogger(__name__)


class TemplateSelector:
    """Select appropriate research template based on query analysis."""

    def __init__(self) -> None:
        self.templates: Dict[str, Dict] = {
            "academic_research": {
                "keywords": [
                    "published", "paper", "study", "research", "journal",
                    "academic", "scholar", "peer-reviewed", "last year",
                    "findings", "evidence", "literature"
                ],
                "search_keywords": [
                    "academic", "study", "research", "published",
                    "paper", "journal", "scholar"
                ],
                "min_sources": 8,
                "max_iterations": 12,
                "decompose": True,
                "escalation_threshold": 0.6,
            },
            "ethics_research": {
                "keywords": [
                    "ethics", "ethical", "morality", "moral", "values",
                    "principles", "viewpoints", "perspectives", "conflicting",
                    "debate", "arguments", "framework", "philosophy"
                ],
                "search_keywords": [
                    "ethics", "ethical", "morality", "philosophical",
                    "debate", "arguments", "values", "principles"
                ],
                "min_sources": 10,
                "max_iterations": 15,
                "decompose": True,
                "escalation_threshold": 0.5,
            },
            "product_research": {
                "keywords": [
                    "product", "buy", "purchase", "price", "cost",
                    "specifications", "specs", "features", "compare",
                    "best", "recommendation", "which should i"
                ],
                "search_keywords": [
                    "review", "price", "specs", "features",
                    "buy", "product", "comparison"
                ],
                "min_sources": 5,
                "max_iterations": 8,
                "decompose": False,
                "escalation_threshold": 0.8,
            },
            "technical_research": {
                "keywords": [
                    "implementation", "algorithm", "code", "architecture",
                    "technical", "engineering", "system", "how to",
                    "tutorial", "guide", "documentation", "api"
                ],
                "search_keywords": [
                    "implementation", "tutorial", "documentation",
                    "guide", "howto", "technical", "code"
                ],
                "min_sources": 6,
                "max_iterations": 10,
                "decompose": True,
                "escalation_threshold": 0.7,
            },
            "current_events": {
                "keywords": [
                    "latest", "recent", "today", "this week", "breaking",
                    "news", "current", "happening now", "update"
                ],
                "search_keywords": [
                    "news", "latest", "recent", "2024", "2025", "current"
                ],
                "min_sources": 8,
                "max_iterations": 8,
                "decompose": False,
                "escalation_threshold": 0.9,
            },
        }

    def select_template(self, query: str) -> Dict:
        query_lower = query.lower()
        scores = {name: self._score_template(query_lower, cfg) for name, cfg in self.templates.items()}
        best_template = max(scores, key=scores.get)
        best_template = self._disambiguate(query_lower, best_template, scores)
        best_score = scores.get(best_template, 0.0)

        logger.info(f"Template selection scores: {scores}")
        logger.info(f"Selected template: {best_template} (score: {best_score:.2f})")

        return {
            "name": best_template,
            "config": self.templates[best_template],
            "score": best_score,
        }

    def _score_template(self, query_lower: str, template_config: Dict) -> float:
        keywords: List[str] = template_config["keywords"]
        score = 0.0
        for kw in keywords:
            if kw in query_lower:
                score += 1.0
                if f" {kw} " in f" {query_lower} ":
                    score += 0.5
                if query_lower.startswith(kw):
                    score += 0.3
        return score / len(keywords)

    def _disambiguate(self, query_lower: str, current_best: str, scores: Dict[str, float]) -> str:
        # Rule 1: "review/list top N" → if idea signals present, flip to ethics/academic
        if re.search(r"\b(review|find|list)\s+(?:the\s+)?top\s+\d+\b", query_lower):
            idea_signals = [
                "viewpoint", "perspective", "argument", "theory",
                "framework", "approach", "method", "position",
            ]
            if any(sig in query_lower for sig in idea_signals):
                if "ethics" in query_lower or "philosophy" in query_lower:
                    return "ethics_research"
                if "published" in query_lower or "paper" in query_lower:
                    return "academic_research"

        # Rule 2: ethics vs academic → prefer ethics if both are present
        if scores.get("ethics_research", 0) > 0.3 and scores.get("academic_research", 0) > 0.3:
            return "ethics_research"

        return current_best
