"""
Confidence Scoring for Research Findings

Computes confidence scores based on multiple factors:
- Source quality and diversity
- Claim support and verification
- Model agreement (when using debate)
- Citation strength
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Set
from decimal import Decimal

logger = logging.getLogger(__name__)


@dataclass
class ConfidenceFactors:
    """Individual factors contributing to confidence score"""
    source_quality: float = 0.0      # 0.0-1.0: Quality of sources
    source_diversity: float = 0.0    # 0.0-1.0: Diversity of sources
    claim_support: float = 0.0       # 0.0-1.0: How well claims are supported
    model_agreement: float = 0.0     # 0.0-1.0: Agreement among models
    citation_strength: float = 0.0   # 0.0-1.0: Strength of citations
    recency: float = 0.0            # 0.0-1.0: Recency of information

    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary"""
        return {
            "source_quality": self.source_quality,
            "source_diversity": self.source_diversity,
            "claim_support": self.claim_support,
            "model_agreement": self.model_agreement,
            "citation_strength": self.citation_strength,
            "recency": self.recency,
        }


@dataclass
class ConfidenceScore:
    """Overall confidence score with breakdown"""
    overall: float = 0.0  # 0.0-1.0: Overall confidence
    factors: ConfidenceFactors = field(default_factory=ConfidenceFactors)
    explanation: str = ""
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "overall": self.overall,
            "factors": self.factors.to_dict(),
            "explanation": self.explanation,
            "warnings": self.warnings
        }


class ConfidenceScorer:
    """
    Computes confidence scores for research findings.

    Weights:
    - Source quality: 25%
    - Source diversity: 15%
    - Claim support: 25%
    - Model agreement: 20%
    - Citation strength: 10%
    - Recency: 5%
    """

    def __init__(
        self,
        min_sources: int = 3,
        min_confidence: float = 0.7,
        weights: Optional[Dict[str, float]] = None
    ):
        """
        Initialize confidence scorer.

        Args:
            min_sources: Minimum number of sources for high confidence
            min_confidence: Minimum acceptable confidence score
            weights: Custom weights for factors (must sum to 1.0)
        """
        self.min_sources = min_sources
        self.min_confidence = min_confidence

        # Default weights
        self.weights = weights or {
            "source_quality": 0.25,
            "source_diversity": 0.15,
            "claim_support": 0.25,
            "model_agreement": 0.20,
            "citation_strength": 0.10,
            "recency": 0.05
        }

        # Validate weights sum to 1.0
        total_weight = sum(self.weights.values())
        if abs(total_weight - 1.0) > 0.01:
            logger.warning(f"Weights sum to {total_weight}, normalizing")
            self.weights = {k: v / total_weight for k, v in self.weights.items()}

    async def score_finding(
        self,
        finding: Dict[str, Any],
        sources: List[Dict[str, Any]],
        context: Optional[Dict[str, Any]] = None
    ) -> ConfidenceScore:
        """
        Score confidence of a research finding.

        Args:
            finding: Finding dict with keys:
                - content: str
                - claims: List[str] (optional)
                - model_scores: List[float] (optional, from debate)
            sources: List of source dicts with keys:
                - url: str
                - title: str (optional)
                - relevance: float (optional)
                - publication_date: str (optional)
            context: Additional context

        Returns:
            ConfidenceScore with overall score and factor breakdown
        """
        factors = ConfidenceFactors()
        warnings = []

        # Factor 1: Source quality
        factors.source_quality = self._compute_source_quality(sources)
        if factors.source_quality < 0.5:
            warnings.append("Low source quality detected")

        # Factor 2: Source diversity
        factors.source_diversity = self._compute_source_diversity(sources)
        if len(sources) < self.min_sources:
            warnings.append(f"Only {len(sources)} sources (minimum {self.min_sources} recommended)")

        # Factor 3: Claim support
        factors.claim_support = self._compute_claim_support(
            finding.get("content", ""),
            finding.get("claims", []),
            sources
        )
        if factors.claim_support < 0.6:
            warnings.append("Some claims lack strong support")

        # Factor 4: Model agreement
        if "model_scores" in finding:
            factors.model_agreement = self._compute_model_agreement(
                finding["model_scores"]
            )
        else:
            factors.model_agreement = 0.8  # Default when no debate

        # Factor 5: Citation strength
        factors.citation_strength = self._compute_citation_strength(
            finding.get("content", ""),
            sources
        )
        if factors.citation_strength < 0.5:
            warnings.append("Weak citation coverage")

        # Factor 6: Recency
        factors.recency = self._compute_recency(sources)

        # Compute overall score
        overall = (
            factors.source_quality * self.weights["source_quality"] +
            factors.source_diversity * self.weights["source_diversity"] +
            factors.claim_support * self.weights["claim_support"] +
            factors.model_agreement * self.weights["model_agreement"] +
            factors.citation_strength * self.weights["citation_strength"] +
            factors.recency * self.weights["recency"]
        )

        # Generate explanation
        explanation = self._generate_explanation(overall, factors, len(sources))

        return ConfidenceScore(
            overall=overall,
            factors=factors,
            explanation=explanation,
            warnings=warnings
        )

    def _compute_source_quality(self, sources: List[Dict[str, Any]]) -> float:
        """
        Compute source quality score.

        Considers:
        - Domain authority (heuristic-based)
        - Source relevance scores
        """
        if not sources:
            return 0.0

        quality_scores = []

        for source in sources:
            score = 0.5  # Base score

            # Check for academic/authoritative domains
            url = source.get("url", "").lower()
            if any(domain in url for domain in [".edu", ".gov", "scholar.google", "arxiv.org"]):
                score += 0.3

            # Check for peer-reviewed indicators
            if any(indicator in url for indicator in ["journal", "peer-review", "published"]):
                score += 0.2

            # Use relevance score if available
            if "relevance" in source:
                score = (score + source["relevance"]) / 2

            quality_scores.append(min(1.0, score))

        avg_quality = sum(quality_scores) / len(quality_scores)

        logger.debug(f"Source quality: {avg_quality:.2f} from {len(sources)} sources")
        return avg_quality

    def _compute_source_diversity(self, sources: List[Dict[str, Any]]) -> float:
        """
        Compute source diversity score.

        Considers:
        - Number of unique domains
        - Geographic/institutional diversity (heuristic)
        """
        if not sources:
            return 0.0

        # Extract domains
        domains = set()
        for source in sources:
            url = source.get("url", "")
            # Extract domain from URL
            domain = url.split("//")[-1].split("/")[0] if url else ""
            if domain:
                domains.add(domain)

        # Score based on unique domains
        unique_ratio = len(domains) / len(sources)

        # Bonus for having minimum diverse sources
        diversity_score = unique_ratio

        if len(domains) >= 3:
            diversity_score = min(1.0, diversity_score + 0.2)

        logger.debug(
            f"Source diversity: {diversity_score:.2f} "
            f"({len(domains)} unique domains from {len(sources)} sources)"
        )
        return diversity_score

    def _compute_claim_support(
        self,
        content: str,
        claims: List[str],
        sources: List[Dict[str, Any]]
    ) -> float:
        """
        Compute claim support score.

        Measures how well claims in the finding are supported by sources.
        """
        if not content:
            return 0.0

        # If explicit claims provided, use them
        if claims:
            claims_to_check = claims
        else:
            # Extract claims from content (simple sentence splitting)
            claims_to_check = [
                s.strip() for s in content.split(".")
                if s.strip() and len(s.strip()) > 20
            ]

        if not claims_to_check:
            return 0.7  # Default if can't extract claims

        # Check each claim against sources
        supported_claims = 0

        for claim in claims_to_check:
            # Simple heuristic: check if claim keywords appear in sources
            claim_words = set(
                w.lower() for w in claim.split()
                if len(w) > 4  # Significant words
            )

            if not claim_words:
                continue

            # Check if any source supports this claim
            for source in sources:
                source_text = (
                    source.get("title", "") + " " +
                    source.get("snippet", "") + " " +
                    source.get("content", "")
                ).lower()

                # Count word matches
                matches = sum(1 for w in claim_words if w in source_text)
                if matches / len(claim_words) > 0.4:  # 40% of keywords found
                    supported_claims += 1
                    break

        support_score = supported_claims / len(claims_to_check)

        logger.debug(
            f"Claim support: {supported_claims}/{len(claims_to_check)} "
            f"claims supported = {support_score:.2f}"
        )

        return support_score

    def _compute_model_agreement(self, model_scores: List[float]) -> float:
        """
        Compute model agreement score.

        When multiple models evaluated the finding (e.g., via debate),
        compute agreement level.
        """
        if not model_scores:
            return 0.8  # Default when no debate

        if len(model_scores) == 1:
            return model_scores[0]  # Single model confidence

        # Calculate variance
        avg_score = sum(model_scores) / len(model_scores)
        variance = sum((s - avg_score) ** 2 for s in model_scores) / len(model_scores)
        std_dev = variance ** 0.5

        # Agreement score: high average + low std dev = high agreement
        agreement = avg_score * (1.0 - min(0.3, std_dev))

        logger.debug(
            f"Model agreement: avg={avg_score:.2f}, std_dev={std_dev:.2f}, "
            f"agreement={agreement:.2f}"
        )

        return agreement

    def _compute_citation_strength(
        self,
        content: str,
        sources: List[Dict[str, Any]]
    ) -> float:
        """
        Compute citation strength score.

        Checks how well the content cites its sources.
        """
        if not content or not sources:
            return 0.0

        # Count citation markers in content
        citation_count = content.count("[") + content.count("(")

        # Expected citations: at least 1 per 2 sources
        expected_citations = len(sources) / 2

        if expected_citations == 0:
            return 0.5

        citation_ratio = min(1.0, citation_count / expected_citations)

        logger.debug(
            f"Citation strength: {citation_count} citations for {len(sources)} sources "
            f"= {citation_ratio:.2f}"
        )

        return citation_ratio

    def _compute_recency(self, sources: List[Dict[str, Any]]) -> float:
        """
        Compute recency score.

        Newer sources generally more valuable for current research.
        """
        if not sources:
            return 0.5  # Default

        from datetime import datetime, timedelta

        current_year = datetime.now().year
        recency_scores = []

        for source in sources:
            pub_date = source.get("publication_date")

            if pub_date:
                try:
                    # Try parsing year
                    if isinstance(pub_date, str):
                        pub_year = int(pub_date[:4])
                    else:
                        pub_year = pub_date.year

                    years_old = current_year - pub_year

                    # Score: 1.0 for current year, decreasing
                    if years_old == 0:
                        score = 1.0
                    elif years_old <= 1:
                        score = 0.9
                    elif years_old <= 3:
                        score = 0.7
                    elif years_old <= 5:
                        score = 0.5
                    else:
                        score = 0.3

                    recency_scores.append(score)
                except:
                    recency_scores.append(0.6)  # Unknown date
            else:
                recency_scores.append(0.6)  # No date provided

        avg_recency = sum(recency_scores) / len(recency_scores)

        logger.debug(f"Recency score: {avg_recency:.2f}")
        return avg_recency

    def _generate_explanation(
        self,
        overall: float,
        factors: ConfidenceFactors,
        num_sources: int
    ) -> str:
        """Generate human-readable explanation of confidence score"""
        if overall >= 0.85:
            level = "Very high"
        elif overall >= 0.75:
            level = "High"
        elif overall >= 0.60:
            level = "Moderate"
        elif overall >= 0.45:
            level = "Low"
        else:
            level = "Very low"

        explanation = f"{level} confidence ({overall:.2f}) based on {num_sources} sources. "

        # Highlight strengths
        strengths = []
        if factors.source_quality >= 0.8:
            strengths.append("high-quality sources")
        if factors.source_diversity >= 0.7:
            strengths.append("diverse sources")
        if factors.claim_support >= 0.8:
            strengths.append("well-supported claims")
        if factors.model_agreement >= 0.85:
            strengths.append("strong model agreement")

        if strengths:
            explanation += "Strengths: " + ", ".join(strengths) + ". "

        # Highlight weaknesses
        weaknesses = []
        if factors.source_quality < 0.6:
            weaknesses.append("low source quality")
        if factors.source_diversity < 0.5:
            weaknesses.append("limited source diversity")
        if factors.claim_support < 0.6:
            weaknesses.append("weak claim support")

        if weaknesses:
            explanation += "Weaknesses: " + ", ".join(weaknesses) + "."

        return explanation

    def is_acceptable(self, score: ConfidenceScore) -> bool:
        """Check if confidence score meets minimum threshold"""
        return score.overall >= self.min_confidence
