"""Print outcome tracking with visual evidence and human feedback.

Tracks print job outcomes with camera snapshots, requests human feedback,
and stores results for future intelligence and learning.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional
from uuid import uuid4

from sqlalchemy.orm import Session

from common.db.models import FailureReason, PrintOutcome
from common.logging import get_logger

LOGGER = get_logger(__name__)


@dataclass
class HumanFeedback:
    """Human feedback for print outcome."""

    success: bool
    failure_reason: Optional[FailureReason] = None
    defect_types: List[str] = None  # Multi-select defects
    quality_scores: Dict[str, int] = None  # layer_consistency, surface_finish (1-10)
    notes: Optional[str] = None
    reviewed_by: Optional[str] = None


@dataclass
class PrintOutcomeData:
    """Data for creating print outcome record."""

    job_id: str
    printer_id: str
    material_id: str
    started_at: datetime
    completed_at: datetime

    # Actuals
    actual_duration_hours: float
    actual_cost_usd: float
    material_used_grams: float

    # Settings
    print_settings: dict  # temp, speed, layer_height, infill

    # Visual evidence (optional)
    initial_snapshot_url: Optional[str] = None
    final_snapshot_url: Optional[str] = None
    snapshot_urls: List[str] = None
    video_url: Optional[str] = None

    # Optional fields
    goal_id: Optional[str] = None
    quality_metrics: Optional[dict] = None


class PrintOutcomeTracker:
    """Track print job outcomes with visual evidence and human feedback.

    Phase 1: Human-in-Loop
    - Capture snapshots during print
    - Request human feedback after completion
    - Store outcomes with visual evidence

    Future Phases:
    - Phase 2: KITTY researches failure types
    - Phase 3: Simple anomaly detection with alerts
    - Phase 4: Autonomous CV-based failure detection
    """

    def __init__(
        self,
        db: Session,
        mqtt_client=None,  # MQTT client for human feedback requests (optional for testing)
    ):
        """Initialize print outcome tracker.

        Args:
            db: Database session
            mqtt_client: MQTT client for publishing review requests (optional)
        """
        self.db = db
        self.mqtt_client = mqtt_client

    # ========================================================================
    # Outcome Capture
    # ========================================================================

    def capture_outcome(
        self,
        outcome_data: PrintOutcomeData,
        human_feedback: Optional[HumanFeedback] = None,
    ) -> PrintOutcome:
        """Capture print outcome with visual evidence.

        Args:
            outcome_data: Print outcome data
            human_feedback: Optional human feedback (if already collected)

        Returns:
            Created PrintOutcome record

        Raises:
            ValueError: If job_id already exists or material_id not found
        """
        # Check for duplicate job_id
        existing = self.db.query(PrintOutcome).filter_by(job_id=outcome_data.job_id).first()
        if existing:
            raise ValueError(f"Print outcome already exists for job: {outcome_data.job_id}")

        # Calculate quality score (default to 0 if no feedback yet)
        quality_score = 0.0
        if human_feedback:
            quality_score = self._calculate_quality_score(human_feedback)

        # Create outcome record
        outcome = PrintOutcome(
            id=str(uuid4()),
            job_id=outcome_data.job_id,
            goal_id=outcome_data.goal_id,
            printer_id=outcome_data.printer_id,
            material_id=outcome_data.material_id,
            # Outcome (placeholder if no feedback yet)
            success=human_feedback.success if human_feedback else True,
            failure_reason=human_feedback.failure_reason if human_feedback else None,
            quality_score=Decimal(str(quality_score)),
            # Actuals
            actual_duration_hours=Decimal(str(outcome_data.actual_duration_hours)),
            actual_cost_usd=Decimal(str(outcome_data.actual_cost_usd)),
            material_used_grams=Decimal(str(outcome_data.material_used_grams)),
            # Settings
            print_settings=outcome_data.print_settings,
            quality_metrics=outcome_data.quality_metrics or {},
            # Timestamps
            started_at=outcome_data.started_at,
            completed_at=outcome_data.completed_at,
            measured_at=datetime.utcnow(),
            # Visual evidence
            initial_snapshot_url=outcome_data.initial_snapshot_url,
            final_snapshot_url=outcome_data.final_snapshot_url,
            snapshot_urls=outcome_data.snapshot_urls or [],
            video_url=outcome_data.video_url,
            # Human feedback
            human_reviewed=human_feedback is not None,
            reviewed_at=datetime.utcnow() if human_feedback else None,
            reviewed_by=human_feedback.reviewed_by if human_feedback else None,
        )

        self.db.add(outcome)
        self.db.commit()

        LOGGER.info(
            "Captured print outcome",
            job_id=outcome_data.job_id,
            printer_id=outcome_data.printer_id,
            success=outcome.success,
            quality_score=float(outcome.quality_score),
            human_reviewed=outcome.human_reviewed,
            snapshots_count=len(outcome_data.snapshot_urls or []),
        )

        return outcome

    def request_human_review(self, job_id: str) -> bool:
        """Request human feedback for print outcome via MQTT.

        Publishes notification to MQTT topic for UI to display review form.

        Args:
            job_id: Print job identifier

        Returns:
            True if request published successfully, False otherwise
        """
        outcome = self.db.query(PrintOutcome).filter_by(job_id=job_id).first()
        if not outcome:
            LOGGER.error("Print outcome not found", job_id=job_id)
            return False

        if outcome.human_reviewed:
            LOGGER.warning("Print outcome already reviewed", job_id=job_id)
            return False

        # Update review requested timestamp
        outcome.review_requested_at = datetime.utcnow()
        self.db.commit()

        # Publish MQTT notification
        if self.mqtt_client:
            topic = f"kitty/fabrication/print/{job_id}/review_request"
            payload = {
                "job_id": job_id,
                "printer_id": outcome.printer_id,
                "material_id": outcome.material_id,
                "duration_hours": float(outcome.actual_duration_hours),
                "initial_snapshot": outcome.initial_snapshot_url,
                "final_snapshot": outcome.final_snapshot_url,
                "snapshots": outcome.snapshot_urls,
                "video": outcome.video_url,
                "requested_at": outcome.review_requested_at.isoformat(),
            }

            try:
                self.mqtt_client.publish(topic, payload)
                LOGGER.info("Published human review request", job_id=job_id, topic=topic)
                return True
            except Exception as e:
                LOGGER.error(
                    "Failed to publish review request", job_id=job_id, error=str(e), exc_info=True
                )
                return False
        else:
            LOGGER.warning("MQTT client not configured, cannot publish review request")
            return False

    def record_human_feedback(self, job_id: str, feedback: HumanFeedback) -> PrintOutcome:
        """Record human feedback for print outcome.

        Args:
            job_id: Print job identifier
            feedback: Human feedback data

        Returns:
            Updated PrintOutcome record

        Raises:
            ValueError: If outcome not found or already reviewed
        """
        outcome = self.db.query(PrintOutcome).filter_by(job_id=job_id).first()
        if not outcome:
            raise ValueError(f"Print outcome not found: {job_id}")

        if outcome.human_reviewed:
            raise ValueError(f"Print outcome already reviewed: {job_id}")

        # Update outcome with human feedback
        outcome.success = feedback.success
        outcome.failure_reason = feedback.failure_reason
        outcome.quality_score = Decimal(str(self._calculate_quality_score(feedback)))

        # Store defect types in visual_defects
        if feedback.defect_types:
            outcome.visual_defects = feedback.defect_types

        # Update quality metrics with human scores
        if feedback.quality_scores:
            outcome.quality_metrics = {
                **outcome.quality_metrics,
                **feedback.quality_scores,
            }

        # Add notes to quality metrics
        if feedback.notes:
            outcome.quality_metrics["human_notes"] = feedback.notes

        # Mark as reviewed
        outcome.human_reviewed = True
        outcome.reviewed_at = datetime.utcnow()
        outcome.reviewed_by = feedback.reviewed_by

        self.db.commit()

        LOGGER.info(
            "Recorded human feedback",
            job_id=job_id,
            success=outcome.success,
            failure_reason=outcome.failure_reason.value if outcome.failure_reason else None,
            quality_score=float(outcome.quality_score),
            reviewed_by=feedback.reviewed_by,
        )

        return outcome

    # ========================================================================
    # Query Methods
    # ========================================================================

    def get_outcome(self, job_id: str) -> Optional[PrintOutcome]:
        """Retrieve print outcome by job ID.

        Args:
            job_id: Print job identifier

        Returns:
            PrintOutcome or None if not found
        """
        outcome = self.db.query(PrintOutcome).filter_by(job_id=job_id).first()

        if outcome:
            LOGGER.debug(
                "Retrieved print outcome",
                job_id=job_id,
                success=outcome.success,
                human_reviewed=outcome.human_reviewed,
            )
        else:
            LOGGER.warning("Print outcome not found", job_id=job_id)

        return outcome

    def list_outcomes_pending_review(self) -> List[PrintOutcome]:
        """List print outcomes pending human review.

        Returns:
            List of outcomes with human_reviewed=False, sorted by completed_at
        """
        outcomes = (
            self.db.query(PrintOutcome)
            .filter(PrintOutcome.human_reviewed == False)  # noqa: E712
            .order_by(PrintOutcome.completed_at.desc())
            .all()
        )

        LOGGER.debug("Listed outcomes pending review", count=len(outcomes))

        return outcomes

    def list_outcomes(
        self,
        printer_id: Optional[str] = None,
        material_id: Optional[str] = None,
        success: Optional[bool] = None,
        limit: int = 100,
    ) -> List[PrintOutcome]:
        """List print outcomes with optional filters.

        Args:
            printer_id: Filter by printer
            material_id: Filter by material
            success: Filter by success status
            limit: Maximum number of results

        Returns:
            List of matching outcomes, sorted by completed_at descending
        """
        query = self.db.query(PrintOutcome)

        if printer_id:
            query = query.filter(PrintOutcome.printer_id == printer_id)

        if material_id:
            query = query.filter(PrintOutcome.material_id == material_id)

        if success is not None:
            query = query.filter(PrintOutcome.success == success)

        outcomes = query.order_by(PrintOutcome.completed_at.desc()).limit(limit).all()

        LOGGER.debug(
            "Listed print outcomes",
            count=len(outcomes),
            printer_id=printer_id,
            material_id=material_id,
            success=success,
        )

        return outcomes

    # ========================================================================
    # Helper Methods
    # ========================================================================

    def classify_failure(self, indicators: Dict[str, any]) -> Optional[FailureReason]:
        """Classify failure reason from indicators (future use).

        Args:
            indicators: Dictionary of failure indicators
                Examples:
                - {"first_layer_lifted": True}
                - {"filament_runout": True}
                - {"layer_shift_detected": True}

        Returns:
            Classified FailureReason or None if cannot determine
        """
        # Simple rule-based classification
        # Future: Replace with ML model

        if indicators.get("first_layer_lifted") or indicators.get("bed_adhesion_fail"):
            return FailureReason.first_layer_adhesion

        if indicators.get("filament_runout"):
            return FailureReason.filament_runout

        if indicators.get("layer_shift_detected"):
            return FailureReason.layer_shift

        if indicators.get("nozzle_clogged"):
            return FailureReason.nozzle_clog

        if indicators.get("warping_detected"):
            return FailureReason.warping

        if indicators.get("spaghetti_detected"):
            return FailureReason.spaghetti

        if indicators.get("user_cancelled"):
            return FailureReason.user_cancelled

        if indicators.get("power_failure"):
            return FailureReason.power_failure

        # Cannot classify
        return FailureReason.other

    def _calculate_quality_score(self, feedback: HumanFeedback) -> float:
        """Calculate quality score from human feedback.

        Formula:
        - If success: Average of quality_scores, default 80 if no scores
        - If failed: 0

        Args:
            feedback: Human feedback data

        Returns:
            Quality score (0-100)
        """
        if not feedback.success:
            return 0.0

        # If quality scores provided, calculate average (scale: 1-10 → 0-100)
        if feedback.quality_scores:
            scores = list(feedback.quality_scores.values())
            if scores:
                avg_score = sum(scores) / len(scores)
                return round(avg_score * 10, 2)  # Scale 1-10 to 0-100

        # Default: success without detailed scores = 80
        return 80.0
