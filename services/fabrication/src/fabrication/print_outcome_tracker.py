"""Print Outcome Tracker - Phase 4.

Tracks print job outcomes with camera snapshots, quality metrics, and human feedback.
Supports both camera sources (Bamboo Labs MQTT, Raspberry Pi HTTP) and MinIO upload.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from common.config import settings
from common.db.models import FailureReason, PrintOutcome
from common.logging import get_logger

LOGGER = get_logger(__name__)


class PrintOutcomeData:
    """Print outcome data container."""

    def __init__(
        self,
        job_id: str,
        printer_id: str,
        material_id: str,
        success: bool,
        quality_score: float,
        actual_duration_hours: float,
        actual_cost_usd: float,
        material_used_grams: float,
        print_settings: Dict,
        started_at: datetime,
        completed_at: datetime,
        failure_reason: Optional[FailureReason] = None,
        quality_metrics: Optional[Dict] = None,
        initial_snapshot_url: Optional[str] = None,
        final_snapshot_url: Optional[str] = None,
        snapshot_urls: Optional[List[str]] = None,
        video_url: Optional[str] = None,
        goal_id: Optional[str] = None,
    ):
        """Initialize print outcome data.

        Args:
            job_id: Unique job identifier
            printer_id: Printer that executed the job (bamboo_h2d, elegoo_giga, snapmaker_artisan)
            material_id: Material catalog ID
            success: Whether print succeeded
            quality_score: Quality rating 0-100
            actual_duration_hours: Print duration in hours
            actual_cost_usd: Total print cost
            material_used_grams: Material consumed in grams
            print_settings: Print settings (temp, speed, layer height, infill)
            started_at: Print start timestamp
            completed_at: Print completion timestamp
            failure_reason: Failure classification if not successful
            quality_metrics: Optional quality metrics (layer_consistency, surface_finish)
            initial_snapshot_url: First layer snapshot URL
            final_snapshot_url: Completed print snapshot URL
            snapshot_urls: All periodic snapshot URLs
            video_url: Optional timelapse video URL
            goal_id: Optional goal ID if autonomous
        """
        self.job_id = job_id
        self.printer_id = printer_id
        self.material_id = material_id
        self.success = success
        self.quality_score = quality_score
        self.actual_duration_hours = actual_duration_hours
        self.actual_cost_usd = actual_cost_usd
        self.material_used_grams = material_used_grams
        self.print_settings = print_settings
        self.started_at = started_at
        self.completed_at = completed_at
        self.failure_reason = failure_reason
        self.quality_metrics = quality_metrics or {}
        self.initial_snapshot_url = initial_snapshot_url
        self.final_snapshot_url = final_snapshot_url
        self.snapshot_urls = snapshot_urls or []
        self.video_url = video_url
        self.goal_id = goal_id


class PrintOutcomeTracker:
    """Tracks print outcomes for intelligence and learning.

    Phase 4: Human-in-Loop implementation with camera capture and feedback requests.
    """

    def __init__(
        self,
        db: Session,
        camera_capture=None,
        mqtt_client=None,
    ):
        """Initialize outcome tracker.

        Args:
            db: Database session
            camera_capture: Optional CameraCapture service for snapshots
            mqtt_client: Optional MQTT client for feedback requests
        """
        self.db = db
        self.camera_capture = camera_capture
        self.mqtt_client = mqtt_client

        LOGGER.info(
            "PrintOutcomeTracker initialized",
            enable_tracking=settings.enable_print_outcome_tracking,
            enable_camera=settings.enable_camera_capture,
            enable_feedback=settings.enable_human_feedback_requests,
        )

    def record_outcome(self, outcome_data: PrintOutcomeData) -> PrintOutcome:
        """Record a print outcome to database.

        Args:
            outcome_data: Print outcome data

        Returns:
            Created PrintOutcome model

        Raises:
            ValueError: If print outcome tracking disabled or invalid data
        """
        # Check feature flag
        if not settings.enable_print_outcome_tracking:
            LOGGER.debug("Print outcome tracking disabled by feature flag")
            raise ValueError("Print outcome tracking is disabled")

        # Validate quality score
        if not 0 <= outcome_data.quality_score <= 100:
            raise ValueError(f"Quality score must be 0-100, got {outcome_data.quality_score}")

        # Create outcome record
        outcome_id = str(uuid.uuid4())

        outcome = PrintOutcome(
            id=outcome_id,
            job_id=outcome_data.job_id,
            goal_id=outcome_data.goal_id,
            printer_id=outcome_data.printer_id,
            material_id=outcome_data.material_id,
            success=outcome_data.success,
            failure_reason=outcome_data.failure_reason,
            quality_score=Decimal(str(outcome_data.quality_score)),
            actual_duration_hours=Decimal(str(outcome_data.actual_duration_hours)),
            actual_cost_usd=Decimal(str(outcome_data.actual_cost_usd)),
            material_used_grams=Decimal(str(outcome_data.material_used_grams)),
            print_settings=outcome_data.print_settings,
            quality_metrics=outcome_data.quality_metrics,
            started_at=outcome_data.started_at,
            completed_at=outcome_data.completed_at,
            measured_at=datetime.utcnow(),
            initial_snapshot_url=outcome_data.initial_snapshot_url,
            final_snapshot_url=outcome_data.final_snapshot_url,
            snapshot_urls=outcome_data.snapshot_urls,
            video_url=outcome_data.video_url,
            human_reviewed=False,
            anomaly_detected=False,
            auto_stopped=False,
        )

        self.db.add(outcome)
        self.db.commit()
        self.db.refresh(outcome)

        LOGGER.info(
            "Recorded print outcome",
            outcome_id=outcome_id,
            job_id=outcome_data.job_id,
            success=outcome_data.success,
            quality_score=outcome_data.quality_score,
        )

        # Request human feedback if enabled
        if settings.enable_human_feedback_requests and settings.human_feedback_auto_request:
            self._request_human_feedback(outcome)

        return outcome

    def get_outcome(self, outcome_id: str) -> Optional[PrintOutcome]:
        """Get outcome by ID.

        Args:
            outcome_id: Outcome UUID

        Returns:
            PrintOutcome or None if not found
        """
        return self.db.query(PrintOutcome).filter(PrintOutcome.id == outcome_id).first()

    def get_outcome_by_job(self, job_id: str) -> Optional[PrintOutcome]:
        """Get outcome by job ID.

        Args:
            job_id: Job identifier

        Returns:
            PrintOutcome or None if not found
        """
        return self.db.query(PrintOutcome).filter(PrintOutcome.job_id == job_id).first()

    def list_outcomes(
        self,
        printer_id: Optional[str] = None,
        material_id: Optional[str] = None,
        success: Optional[bool] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[PrintOutcome]:
        """List print outcomes with filters.

        Args:
            printer_id: Filter by printer
            material_id: Filter by material
            success: Filter by success status
            limit: Max results
            offset: Pagination offset

        Returns:
            List of PrintOutcome models
        """
        query = self.db.query(PrintOutcome)

        if printer_id:
            query = query.filter(PrintOutcome.printer_id == printer_id)

        if material_id:
            query = query.filter(PrintOutcome.material_id == material_id)

        if success is not None:
            query = query.filter(PrintOutcome.success == success)

        query = query.order_by(PrintOutcome.completed_at.desc())
        query = query.limit(limit).offset(offset)

        return query.all()

    def update_human_review(
        self,
        outcome_id: str,
        reviewed_by: str,
        quality_score: Optional[float] = None,
        failure_reason: Optional[FailureReason] = None,
        notes: Optional[str] = None,
    ) -> PrintOutcome:
        """Update outcome with human review.

        Args:
            outcome_id: Outcome UUID
            reviewed_by: Reviewer user ID
            quality_score: Optional updated quality score
            failure_reason: Optional updated failure reason
            notes: Optional review notes

        Returns:
            Updated PrintOutcome

        Raises:
            ValueError: If outcome not found
        """
        outcome = self.get_outcome(outcome_id)
        if not outcome:
            raise ValueError(f"Outcome not found: {outcome_id}")

        outcome.human_reviewed = True
        outcome.reviewed_at = datetime.utcnow()
        outcome.reviewed_by = reviewed_by

        if quality_score is not None:
            if not 0 <= quality_score <= 100:
                raise ValueError(f"Quality score must be 0-100, got {quality_score}")
            outcome.quality_score = Decimal(str(quality_score))

        if failure_reason is not None:
            outcome.failure_reason = failure_reason

        # Store notes in quality_metrics
        if notes:
            metrics = outcome.quality_metrics or {}
            metrics["review_notes"] = notes
            outcome.quality_metrics = metrics

        self.db.commit()
        self.db.refresh(outcome)

        LOGGER.info(
            "Updated human review",
            outcome_id=outcome_id,
            reviewed_by=reviewed_by,
            quality_score=quality_score,
        )

        return outcome

    def get_statistics(
        self,
        printer_id: Optional[str] = None,
        material_id: Optional[str] = None,
    ) -> Dict:
        """Get outcome statistics.

        Args:
            printer_id: Optional filter by printer
            material_id: Optional filter by material

        Returns:
            Statistics dict with success_rate, avg_quality, total_outcomes
        """
        query = self.db.query(PrintOutcome)

        if printer_id:
            query = query.filter(PrintOutcome.printer_id == printer_id)

        if material_id:
            query = query.filter(PrintOutcome.material_id == material_id)

        outcomes = query.all()

        if not outcomes:
            return {
                "total_outcomes": 0,
                "success_rate": 0.0,
                "avg_quality_score": 0.0,
                "avg_duration_hours": 0.0,
                "total_cost_usd": 0.0,
            }

        total = len(outcomes)
        successes = sum(1 for o in outcomes if o.success)
        avg_quality = sum(float(o.quality_score) for o in outcomes) / total
        avg_duration = sum(float(o.actual_duration_hours) for o in outcomes) / total
        total_cost = sum(float(o.actual_cost_usd) for o in outcomes)

        return {
            "total_outcomes": total,
            "success_rate": round(successes / total, 3),
            "avg_quality_score": round(avg_quality, 2),
            "avg_duration_hours": round(avg_duration, 2),
            "total_cost_usd": round(total_cost, 2),
        }

    def _request_human_feedback(self, outcome: PrintOutcome) -> bool:
        """Request human feedback via MQTT.

        Args:
            outcome: PrintOutcome to review

        Returns:
            True if request sent successfully
        """
        if not self.mqtt_client:
            LOGGER.warning("MQTT client not available, skipping feedback request")
            return False

        try:
            topic = f"{settings.topic_prefix}/fabrication/review/request"
            payload = {
                "outcome_id": outcome.id,
                "job_id": outcome.job_id,
                "printer_id": outcome.printer_id,
                "success": outcome.success,
                "quality_score": float(outcome.quality_score),
                "final_snapshot_url": outcome.final_snapshot_url,
                "requested_at": datetime.utcnow().isoformat(),
            }

            self.mqtt_client.publish(topic, payload)

            # Update database
            outcome.review_requested_at = datetime.utcnow()
            self.db.commit()

            LOGGER.info(
                "Requested human feedback",
                outcome_id=outcome.id,
                job_id=outcome.job_id,
                topic=topic,
            )

            return True

        except Exception as e:
            LOGGER.error("Failed to request human feedback", error=str(e), exc_info=True)
            return False
