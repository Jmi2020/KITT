"""Template selection for research pipeline (resolves ethics/academic/product mismatches)."""

from __future__ import annotations

import logging
import re
from typing import Dict, List

logger = logging.getLogger(__name__)


class TemplateSelector:
    """Select appropriate research template based on query analysis."""

    def __init__(self) -> None:
        # Base templates map to config knobs used by the research graph
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
                "strategy": "breadth_first",
                "enable_hierarchical": True,
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
                "strategy": "breadth_first",
                "enable_hierarchical": True,
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
                "strategy": "breadth_first",
                "enable_hierarchical": False,
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
                "strategy": "depth_first",
                "enable_hierarchical": False,
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
                "strategy": "breadth_first",
                "enable_hierarchical": False,
            },
            # Additional intents to reduce template mismatches
            "comparative_analysis": {
                "keywords": ["compare", "versus", "vs", "difference", "tradeoff", "alternatives", "pros", "cons"],
                "search_keywords": ["compare", "versus", "alternatives", "pros and cons", "benchmark"],
                "min_sources": 8,
                "max_iterations": 12,
                "decompose": True,
                "escalation_threshold": 0.65,
                "strategy": "breadth_first",
                "enable_hierarchical": True,
            },
            "controversy_analysis": {
                "keywords": ["conflict", "disagree", "debate", "controversy", "opposing", "critics", "risks"],
                "search_keywords": ["criticism", "risks", "concerns", "debate", "arguments"],
                "min_sources": 10,
                "max_iterations": 14,
                "decompose": True,
                "escalation_threshold": 0.55,
                "strategy": "breadth_first",
                "enable_hierarchical": True,
            },
            "landscape_review": {
                "keywords": ["overview", "state of", "survey", "landscape", "taxonomy", "market", "ecosystem", "trends"],
                "search_keywords": ["overview", "landscape", "survey", "market", "trends", "landscape report"],
                "min_sources": 12,
                "max_iterations": 12,
                "decompose": True,
                "escalation_threshold": 0.7,
                "strategy": "breadth_first",
                "enable_hierarchical": True,
            },
            "howto_playbook": {
                "keywords": ["how do", "how to", "steps", "implementation", "set up", "configure", "build", "recipe", "checklist"],
                "search_keywords": ["guide", "step by step", "implementation", "configuration", "example", "reference"],
                "min_sources": 5,
                "max_iterations": 9,
                "decompose": False,
                "escalation_threshold": 0.75,
                "strategy": "depth_first",
                "enable_hierarchical": False,
            },
        }

        # Deterministic intent rules run before scoring to avoid obvious mismatches
        self.intent_rules = [
            {
                "name": "comparative_analysis",
                "patterns": [r"\bcompare\b", r"\bversus\b", r"\bvs\b", r"\bdifference", r"\btrade[- ]?off"],
            },
            {
                "name": "controversy_analysis",
                "patterns": [r"\bcontrovers(y|ies)\b", r"\bconflict", r"\bdebate", r"\bcritic", r"\bopposing"],
            },
            {
                "name": "landscape_review",
                "patterns": [r"state of", r"survey", r"landscape", r"market", r"ecosystem", r"trends"],
            },
            {
                "name": "howto_playbook",
                "patterns": [r"how to", r"how do i", r"step[- ]by[- ]step", r"set up", r"configure", r"implementation"],
            },
            {
                "name": "ethics_research",
                "patterns": [r"ethic", r"moral", r"philosoph", r"viewpoint", r"perspective"],
            },
        ]

    def select_template(self, query: str) -> Dict:
        query_lower = query.lower().strip()

        # Stage 1: deterministic intent matchers (avoids picking product template for ethics, etc.)
        rule_match = self._apply_intent_rules(query_lower)
        if rule_match:
            template_name = rule_match
            base_config = self.templates[template_name].copy()
            logger.info(f"Intent rule matched template='{template_name}' for query='{query_lower[:80]}'")
        else:
            # Stage 2: heuristic scoring across templates
            scores = {name: self._score_template(query_lower, cfg) for name, cfg in self.templates.items()}
            best_template = max(scores, key=scores.get)
            best_template = self._disambiguate(query_lower, best_template, scores)
            best_score = scores.get(best_template, 0.0)
            base_config = self.templates[best_template].copy()
            template_name = best_template
            logger.info(f"Template selection scores: {scores}")
            logger.info(f"Selected template: {best_template} (score: {best_score:.2f})")

        tuned_config = self._post_process_config(query_lower, base_config)

        return {
            "name": template_name,
            "config": tuned_config,
            "score": tuned_config.get("score", 0.0),
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

    def _apply_intent_rules(self, query_lower: str) -> str | None:
        """Hard-match common intents to avoid misclassification."""
        for rule in self.intent_rules:
            for pattern in rule["patterns"]:
                if re.search(pattern, query_lower):
                    return rule["name"]
        return None

    def _post_process_config(self, query_lower: str, config: Dict) -> Dict:
        """Lightweight tuning to encourage decomposition and better search depth."""
        tuned = config.copy()

        # Encourage hierarchical search for long or multi-part queries
        if len(query_lower.split()) > 18 or re.search(r"[?].+\b(and|or)\b.+[?]", query_lower):
            tuned["enable_hierarchical"] = True
            tuned.setdefault("min_sub_questions", 2)
            tuned.setdefault("max_sub_questions", 5)

        # Lift minimum sources for broader intents
        if any(word in query_lower for word in ["overview", "landscape", "survey", "state of"]):
            tuned["min_sources"] = max(tuned.get("min_sources", 6), 10)
            tuned["max_iterations"] = max(tuned.get("max_iterations", 10), 12)

        # High-stakes ethics → reduce saturation threshold to keep digging for viewpoints
        if "ethic" in query_lower or "moral" in query_lower:
            tuned["saturation_threshold"] = min(tuned.get("saturation_threshold", 0.75), 0.7)
            tuned["min_novelty_rate"] = min(tuned.get("min_novelty_rate", 0.15), 0.12)

        # Store score hint for logging/telemetry
        tuned["score"] = tuned.get("score", 1.0)
        return tuned
