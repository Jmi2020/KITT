"""
Knowledge Gap Detection

Identifies gaps in research coverage and suggests areas for further investigation.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class GapType(str, Enum):
    """Types of knowledge gaps"""
    MISSING_CONTEXT = "missing_context"      # Important context not covered
    CONFLICTING_INFO = "conflicting_info"    # Conflicting information found
    INCOMPLETE_ANSWER = "incomplete_answer"  # Answer doesn't fully address query
    MISSING_PERSPECTIVE = "missing_perspective"  # Missing viewpoint/angle
    TEMPORAL_GAP = "temporal_gap"            # Missing recent information
    DEPTH_GAP = "depth_gap"                  # Superficial coverage, needs depth


class GapPriority(str, Enum):
    """Priority levels for addressing gaps"""
    CRITICAL = "critical"  # Must address
    HIGH = "high"          # Should address
    MEDIUM = "medium"      # Nice to address
    LOW = "low"            # Optional


@dataclass
class KnowledgeGap:
    """A detected knowledge gap"""
    gap_id: str
    gap_type: GapType
    priority: GapPriority
    description: str
    suggested_action: str

    # Context
    related_findings: List[str] = field(default_factory=list)
    missing_topics: List[str] = field(default_factory=list)
    confidence: float = 0.0

    # Metadata
    detected_at: datetime = field(default_factory=datetime.now)
    resolved: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "gap_id": self.gap_id,
            "gap_type": self.gap_type.value,
            "priority": self.priority.value,
            "description": self.description,
            "suggested_action": self.suggested_action,
            "related_findings": self.related_findings,
            "missing_topics": self.missing_topics,
            "confidence": self.confidence,
            "detected_at": self.detected_at.isoformat(),
            "resolved": self.resolved
        }


class GapDetector:
    """
    Detects knowledge gaps in research findings.

    Analyzes:
    - Query coverage (are all aspects addressed?)
    - Information conflicts
    - Missing perspectives
    - Depth of coverage
    """

    def __init__(
        self,
        min_confidence: float = 0.6,
        min_sources_per_topic: int = 2
    ):
        """
        Initialize gap detector.

        Args:
            min_confidence: Minimum confidence for gap detection
            min_sources_per_topic: Minimum sources needed per topic
        """
        self.min_confidence = min_confidence
        self.min_sources_per_topic = min_sources_per_topic

        self.detected_gaps: List[KnowledgeGap] = []
        self._next_gap_id = 1

    async def detect_gaps(
        self,
        query: str,
        findings: List[Dict[str, Any]],
        sources: List[Dict[str, Any]],
        context: Optional[Dict[str, Any]] = None
    ) -> List[KnowledgeGap]:
        """
        Detect knowledge gaps in research.

        Args:
            query: Original research query
            findings: Research findings so far
            sources: Sources used
            context: Additional context

        Returns:
            List of detected KnowledgeGap objects
        """
        gaps = []

        # Check 1: Query coverage
        coverage_gaps = self._detect_coverage_gaps(query, findings)
        gaps.extend(coverage_gaps)

        # Check 2: Conflicting information
        conflict_gaps = self._detect_conflicts(findings)
        gaps.extend(conflict_gaps)

        # Check 3: Missing perspectives
        perspective_gaps = self._detect_missing_perspectives(query, findings, sources)
        gaps.extend(perspective_gaps)

        # Check 4: Temporal gaps
        temporal_gaps = self._detect_temporal_gaps(sources)
        gaps.extend(temporal_gaps)

        # Check 5: Depth gaps
        depth_gaps = self._detect_depth_gaps(query, findings)
        gaps.extend(depth_gaps)

        # Store detected gaps
        self.detected_gaps.extend(gaps)

        logger.info(f"Detected {len(gaps)} knowledge gaps")
        for gap in gaps:
            logger.debug(
                f"  - {gap.gap_type.value} ({gap.priority.value}): {gap.description}"
            )

        return gaps

    def _detect_coverage_gaps(
        self,
        query: str,
        findings: List[Dict[str, Any]]
    ) -> List[KnowledgeGap]:
        """
        Detect gaps in query coverage.

        Checks if all aspects of the query are addressed.
        """
        gaps = []

        # Extract query aspects (simple heuristic)
        query_aspects = self._extract_query_aspects(query)

        if not query_aspects:
            return gaps

        # Check which aspects are covered by findings
        findings_text = " ".join(
            f.get("content", "") for f in findings
        ).lower()

        uncovered_aspects = []
        for aspect in query_aspects:
            if aspect.lower() not in findings_text:
                uncovered_aspects.append(aspect)

        if uncovered_aspects:
            gap = KnowledgeGap(
                gap_id=self._generate_gap_id(),
                gap_type=GapType.INCOMPLETE_ANSWER,
                priority=GapPriority.HIGH,
                description=f"Query aspects not fully addressed: {', '.join(uncovered_aspects)}",
                suggested_action=f"Research: {', '.join(uncovered_aspects)}",
                missing_topics=uncovered_aspects,
                confidence=0.7
            )
            gaps.append(gap)

        return gaps

    def _detect_conflicts(
        self,
        findings: List[Dict[str, Any]]
    ) -> List[KnowledgeGap]:
        """
        Detect conflicting information in findings.

        Looks for contradictory statements.
        """
        gaps = []

        # Simple conflict detection: look for negation patterns
        conflict_indicators = [
            ("is", "is not"),
            ("are", "are not"),
            ("can", "cannot"),
            ("will", "will not"),
            ("does", "does not"),
        ]

        findings_texts = [f.get("content", "") for f in findings]

        for i, text1 in enumerate(findings_texts):
            for text2 in findings_texts[i+1:]:
                # Check for contradictions
                for positive, negative in conflict_indicators:
                    if positive in text1.lower() and negative in text2.lower():
                        # Potential conflict
                        gap = KnowledgeGap(
                            gap_id=self._generate_gap_id(),
                            gap_type=GapType.CONFLICTING_INFO,
                            priority=GapPriority.MEDIUM,
                            description="Potential conflicting information detected",
                            suggested_action="Verify conflicting claims with additional sources",
                            related_findings=[findings[i].get("id", ""), findings[i+1].get("id", "")],
                            confidence=0.5
                        )
                        gaps.append(gap)
                        break  # Only report once per pair

        return gaps

    def _detect_missing_perspectives(
        self,
        query: str,
        findings: List[Dict[str, Any]],
        sources: List[Dict[str, Any]]
    ) -> List[KnowledgeGap]:
        """
        Detect missing perspectives.

        Checks source diversity and coverage of different viewpoints.
        """
        gaps = []

        # Extract source types
        source_types = set()
        for source in sources:
            url = source.get("url", "").lower()

            if ".edu" in url or "scholar" in url:
                source_types.add("academic")
            elif ".gov" in url:
                source_types.add("government")
            elif "news" in url or "blog" in url:
                source_types.add("media")
            else:
                source_types.add("other")

        # Check for missing perspectives
        expected_types = {"academic", "media"}  # Minimum expected
        missing_types = expected_types - source_types

        if missing_types:
            gap = KnowledgeGap(
                gap_id=self._generate_gap_id(),
                gap_type=GapType.MISSING_PERSPECTIVE,
                priority=GapPriority.MEDIUM,
                description=f"Missing source perspectives: {', '.join(missing_types)}",
                suggested_action=f"Find {', '.join(missing_types)} sources",
                missing_topics=list(missing_types),
                confidence=0.6
            )
            gaps.append(gap)

        return gaps

    def _detect_temporal_gaps(
        self,
        sources: List[Dict[str, Any]]
    ) -> List[KnowledgeGap]:
        """
        Detect temporal gaps.

        Checks if sources are recent enough.
        """
        gaps = []

        from datetime import datetime, timedelta

        current_year = datetime.now().year

        # Check for recent sources
        has_recent = False
        for source in sources:
            pub_date = source.get("publication_date")
            if pub_date:
                try:
                    if isinstance(pub_date, str):
                        pub_year = int(pub_date[:4])
                    else:
                        pub_year = pub_date.year

                    if current_year - pub_year <= 1:
                        has_recent = True
                        break
                except:
                    pass

        if not has_recent and len(sources) > 0:
            gap = KnowledgeGap(
                gap_id=self._generate_gap_id(),
                gap_type=GapType.TEMPORAL_GAP,
                priority=GapPriority.MEDIUM,
                description="No recent sources found (within last year)",
                suggested_action="Search for recent publications or updates",
                confidence=0.7
            )
            gaps.append(gap)

        return gaps

    def _detect_depth_gaps(
        self,
        query: str,
        findings: List[Dict[str, Any]]
    ) -> List[KnowledgeGap]:
        """
        Detect depth gaps.

        Checks if findings provide sufficient depth.
        """
        gaps = []

        # Heuristic: check average finding length
        if findings:
            avg_length = sum(len(f.get("content", "")) for f in findings) / len(findings)

            if avg_length < 200:  # Very short findings
                gap = KnowledgeGap(
                    gap_id=self._generate_gap_id(),
                    gap_type=GapType.DEPTH_GAP,
                    priority=GapPriority.LOW,
                    description="Findings appear superficial, lacking detail",
                    suggested_action="Seek more detailed sources or analysis",
                    confidence=0.6
                )
                gaps.append(gap)

        return gaps

    def _extract_query_aspects(self, query: str) -> List[str]:
        """
        Extract key aspects from query.

        Simple heuristic: look for "and", question words, etc.
        """
        aspects = []

        # Split on "and"
        parts = [p.strip() for p in query.split(" and ")]

        for part in parts:
            # Extract key phrases (very simple)
            words = part.split()
            if len(words) > 2:
                # Take last 2-3 words as aspect
                aspect = " ".join(words[-3:])
                aspects.append(aspect)

        return aspects

    def _generate_gap_id(self) -> str:
        """Generate unique gap ID"""
        gap_id = f"gap_{self._next_gap_id:04d}"
        self._next_gap_id += 1
        return gap_id

    def get_gaps_by_priority(self, priority: GapPriority) -> List[KnowledgeGap]:
        """Get gaps of a specific priority"""
        return [g for g in self.detected_gaps if g.priority == priority and not g.resolved]

    def get_unresolved_gaps(self) -> List[KnowledgeGap]:
        """Get all unresolved gaps"""
        return [g for g in self.detected_gaps if not g.resolved]

    def mark_gap_resolved(self, gap_id: str):
        """Mark a gap as resolved"""
        for gap in self.detected_gaps:
            if gap.gap_id == gap_id:
                gap.resolved = True
                logger.info(f"Marked gap {gap_id} as resolved")
                break

    def get_gap_summary(self) -> Dict[str, Any]:
        """Get summary of detected gaps"""
        by_type = {}
        by_priority = {}

        for gap in self.detected_gaps:
            # Count by type
            gap_type = gap.gap_type.value
            if gap_type not in by_type:
                by_type[gap_type] = 0
            by_type[gap_type] += 1

            # Count by priority
            priority = gap.priority.value
            if priority not in by_priority:
                by_priority[priority] = 0
            by_priority[priority] += 1

        unresolved = len(self.get_unresolved_gaps())

        return {
            "total_gaps": len(self.detected_gaps),
            "unresolved_gaps": unresolved,
            "gaps_by_type": by_type,
            "gaps_by_priority": by_priority,
            "critical_gaps": len(self.get_gaps_by_priority(GapPriority.CRITICAL)),
            "high_priority_gaps": len(self.get_gaps_by_priority(GapPriority.HIGH)),
        }
