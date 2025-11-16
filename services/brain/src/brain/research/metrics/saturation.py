"""
Saturation Detection and Novelty Tracking

Monitors research progress to detect when diminishing returns occur.
Tracks novelty rate to determine when to stop iterating.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Any
from datetime import datetime
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class SaturationStatus:
    """Current saturation status"""
    is_saturated: bool
    novelty_rate: float  # 0.0-1.0: Rate of new information
    iterations_checked: int
    findings_total: int
    findings_novel: int
    repeated_findings: int
    saturation_score: float  # 0.0-1.0: Higher = more saturated

    explanation: str = ""
    recommendation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "is_saturated": self.is_saturated,
            "novelty_rate": self.novelty_rate,
            "iterations_checked": self.iterations_checked,
            "findings_total": self.findings_total,
            "findings_novel": self.findings_novel,
            "repeated_findings": self.repeated_findings,
            "saturation_score": self.saturation_score,
            "explanation": self.explanation,
            "recommendation": self.recommendation
        }


class NoveltyTracker:
    """
    Tracks novelty of findings across iterations.

    Uses content similarity and keyword extraction to identify
    when new findings are adding significant new information.
    """

    def __init__(
        self,
        similarity_threshold: float = 0.7,
        min_content_length: int = 50
    ):
        """
        Initialize novelty tracker.

        Args:
            similarity_threshold: Threshold for considering content similar
            min_content_length: Minimum content length to consider
        """
        self.similarity_threshold = similarity_threshold
        self.min_content_length = min_content_length

        # Track seen content
        self.seen_contents: List[str] = []
        self.seen_keywords: Set[str] = set()
        self.keyword_frequency: Dict[str, int] = defaultdict(int)

    def is_novel(self, content: str) -> tuple[bool, float]:
        """
        Check if content is novel.

        Args:
            content: Content to check

        Returns:
            (is_novel, similarity_score)
        """
        if len(content) < self.min_content_length:
            return False, 0.0

        # Extract keywords
        keywords = self._extract_keywords(content)

        if not self.seen_contents:
            # First content is always novel
            self._add_content(content, keywords)
            return True, 0.0

        # Check similarity against existing content
        max_similarity = 0.0

        for seen_content in self.seen_contents:
            similarity = self._compute_similarity(content, seen_content)
            max_similarity = max(max_similarity, similarity)

            if similarity >= self.similarity_threshold:
                # Too similar to existing content
                logger.debug(
                    f"Content not novel (similarity={similarity:.2f} to existing)"
                )
                return False, similarity

        # Check keyword novelty
        new_keywords = keywords - self.seen_keywords
        keyword_novelty = len(new_keywords) / len(keywords) if keywords else 0.0

        if keyword_novelty < 0.2:  # Less than 20% new keywords
            logger.debug(
                f"Content not novel (only {keyword_novelty:.1%} new keywords)"
            )
            return False, max_similarity

        # Novel!
        self._add_content(content, keywords)
        logger.debug(
            f"Content is novel (similarity={max_similarity:.2f}, "
            f"keyword_novelty={keyword_novelty:.1%})"
        )
        return True, max_similarity

    def _add_content(self, content: str, keywords: Set[str]):
        """Add content to seen set"""
        self.seen_contents.append(content)
        self.seen_keywords.update(keywords)

        for keyword in keywords:
            self.keyword_frequency[keyword] += 1

    def _extract_keywords(self, content: str) -> Set[str]:
        """
        Extract keywords from content.

        Simple approach: filter by length and frequency.
        """
        # Common stopwords
        stopwords = {
            "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
            "of", "with", "by", "from", "as", "is", "was", "are", "were", "been",
            "be", "have", "has", "had", "do", "does", "did", "will", "would",
            "could", "should", "may", "might", "can", "this", "that", "these",
            "those", "i", "you", "he", "she", "it", "we", "they", "what", "which",
            "who", "when", "where", "why", "how"
        }

        words = content.lower().split()

        keywords = {
            word for word in words
            if len(word) > 4 and word not in stopwords
        }

        return keywords

    def _compute_similarity(self, content1: str, content2: str) -> float:
        """
        Compute similarity between two content pieces.

        Uses simple Jaccard similarity on keywords.
        """
        keywords1 = self._extract_keywords(content1)
        keywords2 = self._extract_keywords(content2)

        if not keywords1 or not keywords2:
            return 0.0

        intersection = keywords1 & keywords2
        union = keywords1 | keywords2

        similarity = len(intersection) / len(union)
        return similarity

    def get_top_keywords(self, n: int = 10) -> List[tuple[str, int]]:
        """Get top N most frequent keywords"""
        sorted_keywords = sorted(
            self.keyword_frequency.items(),
            key=lambda x: x[1],
            reverse=True
        )
        return sorted_keywords[:n]

    def reset(self):
        """Reset tracker"""
        self.seen_contents.clear()
        self.seen_keywords.clear()
        self.keyword_frequency.clear()


class SaturationDetector:
    """
    Detects when research has reached saturation.

    Saturation indicators:
    - Low novelty rate (few new findings)
    - Repeated findings across iterations
    - Declining quality scores
    - High similarity in consecutive iterations
    """

    def __init__(
        self,
        saturation_threshold: float = 0.75,
        min_iterations: int = 5,
        window_size: int = 5
    ):
        """
        Initialize saturation detector.

        Args:
            saturation_threshold: Saturation score threshold (0.0-1.0)
            min_iterations: Minimum iterations before saturation can occur
            window_size: Number of recent iterations to consider
        """
        self.saturation_threshold = saturation_threshold
        self.min_iterations = min_iterations
        self.window_size = window_size

        self.novelty_tracker = NoveltyTracker()

        # Tracking data
        self.iteration_findings: List[List[Dict[str, Any]]] = []
        self.novelty_scores: List[float] = []

    def add_iteration_findings(
        self,
        findings: List[Dict[str, Any]]
    ) -> SaturationStatus:
        """
        Add findings from an iteration and check saturation.

        Args:
            findings: List of findings from iteration
                Each finding should have 'content' key

        Returns:
            SaturationStatus with updated status
        """
        self.iteration_findings.append(findings)

        # Check novelty of each finding
        novel_count = 0
        repeated_count = 0

        for finding in findings:
            content = finding.get("content", "")
            if not content:
                continue

            is_novel, similarity = self.novelty_tracker.is_novel(content)

            if is_novel:
                novel_count += 1
            else:
                repeated_count += 1

        # Calculate novelty rate for this iteration
        total_findings = len(findings)
        if total_findings > 0:
            iteration_novelty = novel_count / total_findings
        else:
            iteration_novelty = 0.0

        self.novelty_scores.append(iteration_novelty)

        logger.info(
            f"Iteration {len(self.iteration_findings)}: "
            f"{novel_count} novel, {repeated_count} repeated "
            f"(novelty rate={iteration_novelty:.2%})"
        )

        # Check saturation
        return self.check_saturation()

    def check_saturation(self) -> SaturationStatus:
        """
        Check if research has reached saturation.

        Returns:
            SaturationStatus with determination
        """
        iterations_checked = len(self.iteration_findings)

        if iterations_checked < self.min_iterations:
            # Not enough iterations yet
            return SaturationStatus(
                is_saturated=False,
                novelty_rate=1.0,
                iterations_checked=iterations_checked,
                findings_total=sum(len(f) for f in self.iteration_findings),
                findings_novel=len(self.novelty_tracker.seen_contents),
                repeated_findings=0,
                saturation_score=0.0,
                explanation=f"Only {iterations_checked} iterations (minimum {self.min_iterations})",
                recommendation="Continue research"
            )

        # Calculate metrics over recent window
        recent_novelty = self.novelty_scores[-self.window_size:]
        avg_novelty = sum(recent_novelty) / len(recent_novelty)

        # Calculate novelty trend (declining?)
        if len(self.novelty_scores) >= 3:
            recent_trend = self.novelty_scores[-3:]
            is_declining = all(
                recent_trend[i] >= recent_trend[i+1]
                for i in range(len(recent_trend) - 1)
            )
        else:
            is_declining = False

        # Calculate total findings
        total_findings = sum(len(f) for f in self.iteration_findings)
        novel_findings = len(self.novelty_tracker.seen_contents)
        repeated_findings = total_findings - novel_findings

        # Saturation score components
        # 1. Low novelty rate (weight: 50%)
        novelty_component = (1.0 - avg_novelty) * 0.5

        # 2. Declining trend (weight: 25%)
        trend_component = 0.25 if is_declining else 0.0

        # 3. High repetition rate (weight: 25%)
        if total_findings > 0:
            repetition_rate = repeated_findings / total_findings
            repetition_component = repetition_rate * 0.25
        else:
            repetition_component = 0.0

        saturation_score = novelty_component + trend_component + repetition_component

        # Determine if saturated
        is_saturated = saturation_score >= self.saturation_threshold

        # Generate explanation
        if is_saturated:
            explanation = (
                f"Research appears saturated after {iterations_checked} iterations. "
                f"Recent novelty rate: {avg_novelty:.1%}. "
            )

            if is_declining:
                explanation += "Novelty declining. "

            if repetition_rate > 0.5:
                explanation += f"{repetition_rate:.1%} findings are repetitive. "

            recommendation = "Consider stopping research or changing approach"
        else:
            explanation = (
                f"Research continuing productively after {iterations_checked} iterations. "
                f"Novelty rate: {avg_novelty:.1%}. "
            )
            recommendation = "Continue research"

        logger.info(
            f"Saturation check: score={saturation_score:.2f}, "
            f"saturated={is_saturated}, novelty={avg_novelty:.2%}"
        )

        return SaturationStatus(
            is_saturated=is_saturated,
            novelty_rate=avg_novelty,
            iterations_checked=iterations_checked,
            findings_total=total_findings,
            findings_novel=novel_findings,
            repeated_findings=repeated_findings,
            saturation_score=saturation_score,
            explanation=explanation,
            recommendation=recommendation
        )

    def get_novelty_history(self) -> List[float]:
        """Get novelty rate history"""
        return self.novelty_scores.copy()

    def get_trending_keywords(self, n: int = 10) -> List[tuple[str, int]]:
        """Get trending keywords across all findings"""
        return self.novelty_tracker.get_top_keywords(n)

    def reset(self):
        """Reset detector"""
        self.iteration_findings.clear()
        self.novelty_scores.clear()
        self.novelty_tracker.reset()
