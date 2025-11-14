"""Unit tests for PrintOutcomeTracker (Phase 4 Fabrication Intelligence).

Tests print outcome capture, human feedback workflow, and query operations.
"""

from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from common.db.models import Base, FailureReason, Material, PrintOutcome
from fabrication.monitoring.outcome_tracker import (
    HumanFeedback,
    PrintOutcomeData,
    PrintOutcomeTracker,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture(scope="function")
def db_session():
    """Create in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    # Add test material
    material = Material(
        id="pla_black_esun",
        material_type="pla",
        color="black",
        manufacturer="eSUN",
        cost_per_kg_usd=Decimal("21.99"),
        density_g_cm3=Decimal("1.24"),
        nozzle_temp_min_c=190,
        nozzle_temp_max_c=220,
        bed_temp_min_c=50,
        bed_temp_max_c=70,
        properties={},
        sustainability_score=75,
    )
    session.add(material)
    session.commit()

    yield session

    session.close()


@pytest.fixture
def mock_mqtt():
    """Mock MQTT client."""
    mqtt = MagicMock()
    mqtt.publish = MagicMock()
    return mqtt


@pytest.fixture
def outcome_tracker(db_session, mock_mqtt):
    """PrintOutcomeTracker instance with mocked MQTT."""
    return PrintOutcomeTracker(db=db_session, mqtt_client=mock_mqtt)


@pytest.fixture
def outcome_tracker_no_mqtt(db_session):
    """PrintOutcomeTracker instance without MQTT client."""
    return PrintOutcomeTracker(db=db_session, mqtt_client=None)


@pytest.fixture
def sample_outcome_data():
    """Sample print outcome data."""
    return PrintOutcomeData(
        job_id="job123",
        printer_id="snapmaker_artisan",
        material_id="pla_black_esun",
        started_at=datetime(2025, 11, 14, 10, 0, 0),
        completed_at=datetime(2025, 11, 14, 14, 30, 0),
        actual_duration_hours=4.5,
        actual_cost_usd=2.15,
        material_used_grams=98.5,
        print_settings={
            "nozzle_temp": 210,
            "bed_temp": 60,
            "speed": 60,
            "layer_height": 0.2,
            "infill": 20,
        },
        initial_snapshot_url="minio://prints/job123/start_20251114_100000.jpg",
        final_snapshot_url="minio://prints/job123/complete_20251114_143000.jpg",
        snapshot_urls=[
            "minio://prints/job123/progress_20251114_110000.jpg",
            "minio://prints/job123/progress_20251114_120000.jpg",
            "minio://prints/job123/progress_20251114_130000.jpg",
        ],
        video_url="minio://prints/job123/timelapse.mp4",
    )


@pytest.fixture
def sample_human_feedback():
    """Sample human feedback (successful print)."""
    return HumanFeedback(
        success=True,
        defect_types=[],
        quality_scores={"layer_consistency": 9, "surface_finish": 8},
        notes="Excellent print quality",
        reviewed_by="john_doe",
    )


@pytest.fixture
def sample_failed_feedback():
    """Sample human feedback (failed print)."""
    return HumanFeedback(
        success=False,
        failure_reason=FailureReason.first_layer_adhesion,
        defect_types=["first_layer_lifted", "corners_warped"],
        quality_scores={"layer_consistency": 3, "surface_finish": 2},
        notes="Bed not level, poor adhesion",
        reviewed_by="jane_smith",
    )


# ============================================================================
# Outcome Capture Tests
# ============================================================================


def test_capture_outcome_success(outcome_tracker, sample_outcome_data):
    """Test capturing print outcome without human feedback."""
    outcome = outcome_tracker.capture_outcome(sample_outcome_data)

    assert outcome is not None
    assert outcome.job_id == "job123"
    assert outcome.printer_id == "snapmaker_artisan"
    assert outcome.material_id == "pla_black_esun"
    assert outcome.success is True  # Default when no feedback
    assert outcome.quality_score == Decimal("0.0")  # Default when no feedback
    assert outcome.human_reviewed is False
    assert outcome.initial_snapshot_url == sample_outcome_data.initial_snapshot_url
    assert outcome.final_snapshot_url == sample_outcome_data.final_snapshot_url
    assert len(outcome.snapshot_urls) == 3
    assert outcome.video_url == sample_outcome_data.video_url


def test_capture_outcome_with_feedback(outcome_tracker, sample_outcome_data, sample_human_feedback):
    """Test capturing print outcome with human feedback."""
    outcome = outcome_tracker.capture_outcome(sample_outcome_data, sample_human_feedback)

    assert outcome.success is True
    assert outcome.quality_score == Decimal("85.0")  # (9+8)/2 * 10
    assert outcome.human_reviewed is True
    assert outcome.reviewed_by == "john_doe"
    assert outcome.reviewed_at is not None


def test_capture_outcome_failed_print(outcome_tracker, sample_outcome_data, sample_failed_feedback):
    """Test capturing failed print outcome."""
    outcome = outcome_tracker.capture_outcome(sample_outcome_data, sample_failed_feedback)

    assert outcome.success is False
    assert outcome.failure_reason == FailureReason.first_layer_adhesion
    assert outcome.quality_score == Decimal("0.0")  # Failed prints = 0
    assert outcome.human_reviewed is True


def test_capture_outcome_duplicate_job_id(outcome_tracker, sample_outcome_data):
    """Test capturing outcome with duplicate job_id raises error."""
    outcome_tracker.capture_outcome(sample_outcome_data)

    with pytest.raises(ValueError, match="Print outcome already exists"):
        outcome_tracker.capture_outcome(sample_outcome_data)


def test_capture_outcome_minimal_data(outcome_tracker):
    """Test capturing outcome with minimal data (no snapshots)."""
    minimal_data = PrintOutcomeData(
        job_id="job_minimal",
        printer_id="bamboo_h2d",
        material_id="pla_black_esun",
        started_at=datetime(2025, 11, 14, 10, 0, 0),
        completed_at=datetime(2025, 11, 14, 12, 0, 0),
        actual_duration_hours=2.0,
        actual_cost_usd=1.50,
        material_used_grams=68.0,
        print_settings={"nozzle_temp": 210, "bed_temp": 60},
    )

    outcome = outcome_tracker.capture_outcome(minimal_data)

    assert outcome.job_id == "job_minimal"
    assert outcome.initial_snapshot_url is None
    assert outcome.final_snapshot_url is None
    assert outcome.snapshot_urls == []
    assert outcome.video_url is None


# ============================================================================
# Human Feedback Tests
# ============================================================================


def test_request_human_review_success(outcome_tracker, sample_outcome_data):
    """Test requesting human review via MQTT."""
    outcome_tracker.capture_outcome(sample_outcome_data)

    success = outcome_tracker.request_human_review("job123")

    assert success is True

    # Verify MQTT publish called
    outcome_tracker.mqtt_client.publish.assert_called_once()
    call_args = outcome_tracker.mqtt_client.publish.call_args
    topic, payload = call_args[0]

    assert topic == "kitty/fabrication/print/job123/review_request"
    assert payload["job_id"] == "job123"
    assert payload["printer_id"] == "snapmaker_artisan"

    # Verify outcome updated
    outcome = outcome_tracker.get_outcome("job123")
    assert outcome.review_requested_at is not None


def test_request_human_review_not_found(outcome_tracker):
    """Test requesting review for non-existent outcome."""
    success = outcome_tracker.request_human_review("nonexistent_job")

    assert success is False
    outcome_tracker.mqtt_client.publish.assert_not_called()


def test_request_human_review_already_reviewed(outcome_tracker, sample_outcome_data, sample_human_feedback):
    """Test requesting review for already reviewed outcome."""
    outcome_tracker.capture_outcome(sample_outcome_data, sample_human_feedback)

    success = outcome_tracker.request_human_review("job123")

    assert success is False
    outcome_tracker.mqtt_client.publish.assert_not_called()


def test_request_human_review_no_mqtt(outcome_tracker_no_mqtt, sample_outcome_data):
    """Test requesting review without MQTT client."""
    outcome_tracker_no_mqtt.capture_outcome(sample_outcome_data)

    success = outcome_tracker_no_mqtt.request_human_review("job123")

    assert success is False


def test_record_human_feedback_success(outcome_tracker, sample_outcome_data, sample_human_feedback):
    """Test recording human feedback for outcome."""
    outcome_tracker.capture_outcome(sample_outcome_data)

    outcome = outcome_tracker.record_human_feedback("job123", sample_human_feedback)

    assert outcome.success is True
    assert outcome.quality_score == Decimal("85.0")
    assert outcome.human_reviewed is True
    assert outcome.reviewed_by == "john_doe"
    assert outcome.reviewed_at is not None
    assert outcome.quality_metrics["layer_consistency"] == 9
    assert outcome.quality_metrics["surface_finish"] == 8
    assert outcome.quality_metrics["human_notes"] == "Excellent print quality"


def test_record_human_feedback_failed_print(outcome_tracker, sample_outcome_data, sample_failed_feedback):
    """Test recording feedback for failed print."""
    outcome_tracker.capture_outcome(sample_outcome_data)

    outcome = outcome_tracker.record_human_feedback("job123", sample_failed_feedback)

    assert outcome.success is False
    assert outcome.failure_reason == FailureReason.first_layer_adhesion
    assert outcome.quality_score == Decimal("0.0")
    assert len(outcome.visual_defects) == 2
    assert "first_layer_lifted" in outcome.visual_defects


def test_record_human_feedback_not_found(outcome_tracker, sample_human_feedback):
    """Test recording feedback for non-existent outcome raises error."""
    with pytest.raises(ValueError, match="Print outcome not found"):
        outcome_tracker.record_human_feedback("nonexistent_job", sample_human_feedback)


def test_record_human_feedback_already_reviewed(outcome_tracker, sample_outcome_data, sample_human_feedback):
    """Test recording feedback for already reviewed outcome raises error."""
    outcome_tracker.capture_outcome(sample_outcome_data, sample_human_feedback)

    with pytest.raises(ValueError, match="already reviewed"):
        outcome_tracker.record_human_feedback("job123", sample_human_feedback)


# ============================================================================
# Query Tests
# ============================================================================


def test_get_outcome_success(outcome_tracker, sample_outcome_data):
    """Test retrieving outcome by job_id."""
    outcome_tracker.capture_outcome(sample_outcome_data)

    outcome = outcome_tracker.get_outcome("job123")

    assert outcome is not None
    assert outcome.job_id == "job123"


def test_get_outcome_not_found(outcome_tracker):
    """Test retrieving non-existent outcome returns None."""
    outcome = outcome_tracker.get_outcome("nonexistent_job")

    assert outcome is None


def test_list_outcomes_pending_review(outcome_tracker):
    """Test listing outcomes pending human review."""
    # Create multiple outcomes
    for i in range(3):
        data = PrintOutcomeData(
            job_id=f"job{i}",
            printer_id="snapmaker_artisan",
            material_id="pla_black_esun",
            started_at=datetime(2025, 11, 14, 10, 0, 0),
            completed_at=datetime(2025, 11, 14, 14, 0, 0),
            actual_duration_hours=4.0,
            actual_cost_usd=2.0,
            material_used_grams=90.0,
            print_settings={"nozzle_temp": 210},
        )
        outcome_tracker.capture_outcome(data)

    # Review one outcome
    feedback = HumanFeedback(success=True, reviewed_by="test_user")
    outcome_tracker.record_human_feedback("job0", feedback)

    # List pending reviews
    pending = outcome_tracker.list_outcomes_pending_review()

    assert len(pending) == 2
    assert all(not o.human_reviewed for o in pending)


def test_list_outcomes_all(outcome_tracker):
    """Test listing all outcomes."""
    # Create 3 outcomes
    for i in range(3):
        data = PrintOutcomeData(
            job_id=f"job{i}",
            printer_id="snapmaker_artisan",
            material_id="pla_black_esun",
            started_at=datetime(2025, 11, 14, 10, 0, 0),
            completed_at=datetime(2025, 11, 14, 14, 0, 0),
            actual_duration_hours=4.0,
            actual_cost_usd=2.0,
            material_used_grams=90.0,
            print_settings={"nozzle_temp": 210},
        )
        outcome_tracker.capture_outcome(data)

    outcomes = outcome_tracker.list_outcomes()

    assert len(outcomes) == 3


def test_list_outcomes_filter_by_printer(outcome_tracker):
    """Test listing outcomes filtered by printer_id."""
    # Create outcomes for different printers
    for printer in ["snapmaker_artisan", "bamboo_h2d", "snapmaker_artisan"]:
        data = PrintOutcomeData(
            job_id=f"job_{printer}_{id(printer)}",
            printer_id=printer,
            material_id="pla_black_esun",
            started_at=datetime(2025, 11, 14, 10, 0, 0),
            completed_at=datetime(2025, 11, 14, 14, 0, 0),
            actual_duration_hours=4.0,
            actual_cost_usd=2.0,
            material_used_grams=90.0,
            print_settings={"nozzle_temp": 210},
        )
        outcome_tracker.capture_outcome(data)

    outcomes = outcome_tracker.list_outcomes(printer_id="snapmaker_artisan")

    assert len(outcomes) == 2
    assert all(o.printer_id == "snapmaker_artisan" for o in outcomes)


def test_list_outcomes_filter_by_success(outcome_tracker):
    """Test listing outcomes filtered by success status."""
    # Create successful and failed outcomes
    for i in range(3):
        data = PrintOutcomeData(
            job_id=f"job{i}",
            printer_id="snapmaker_artisan",
            material_id="pla_black_esun",
            started_at=datetime(2025, 11, 14, 10, 0, 0),
            completed_at=datetime(2025, 11, 14, 14, 0, 0),
            actual_duration_hours=4.0,
            actual_cost_usd=2.0,
            material_used_grams=90.0,
            print_settings={"nozzle_temp": 210},
        )

        if i == 0:
            # Failed print
            feedback = HumanFeedback(
                success=False, failure_reason=FailureReason.warping, reviewed_by="test_user"
            )
            outcome_tracker.capture_outcome(data, feedback)
        else:
            # Successful print
            feedback = HumanFeedback(success=True, reviewed_by="test_user")
            outcome_tracker.capture_outcome(data, feedback)

    # Query successful prints
    successful = outcome_tracker.list_outcomes(success=True)
    assert len(successful) == 2
    assert all(o.success for o in successful)

    # Query failed prints
    failed = outcome_tracker.list_outcomes(success=False)
    assert len(failed) == 1
    assert not failed[0].success


# ============================================================================
# Helper Method Tests
# ============================================================================


def test_classify_failure_first_layer_adhesion(outcome_tracker):
    """Test classifying first layer adhesion failure."""
    failure = outcome_tracker.classify_failure({"first_layer_lifted": True})
    assert failure == FailureReason.first_layer_adhesion

    failure = outcome_tracker.classify_failure({"bed_adhesion_fail": True})
    assert failure == FailureReason.first_layer_adhesion


def test_classify_failure_filament_runout(outcome_tracker):
    """Test classifying filament runout failure."""
    failure = outcome_tracker.classify_failure({"filament_runout": True})
    assert failure == FailureReason.filament_runout


def test_classify_failure_layer_shift(outcome_tracker):
    """Test classifying layer shift failure."""
    failure = outcome_tracker.classify_failure({"layer_shift_detected": True})
    assert failure == FailureReason.layer_shift


def test_classify_failure_nozzle_clog(outcome_tracker):
    """Test classifying nozzle clog failure."""
    failure = outcome_tracker.classify_failure({"nozzle_clogged": True})
    assert failure == FailureReason.nozzle_clog


def test_classify_failure_warping(outcome_tracker):
    """Test classifying warping failure."""
    failure = outcome_tracker.classify_failure({"warping_detected": True})
    assert failure == FailureReason.warping


def test_classify_failure_spaghetti(outcome_tracker):
    """Test classifying spaghetti failure."""
    failure = outcome_tracker.classify_failure({"spaghetti_detected": True})
    assert failure == FailureReason.spaghetti


def test_classify_failure_other(outcome_tracker):
    """Test classifying unknown failure as 'other'."""
    failure = outcome_tracker.classify_failure({"unknown_indicator": True})
    assert failure == FailureReason.other


def test_calculate_quality_score_success_with_scores(outcome_tracker):
    """Test quality score calculation for successful print with scores."""
    feedback = HumanFeedback(
        success=True,
        quality_scores={"layer_consistency": 9, "surface_finish": 8, "dimensional_accuracy": 7},
    )

    score = outcome_tracker._calculate_quality_score(feedback)

    # (9 + 8 + 7) / 3 = 8.0, scaled to 80.0
    assert score == 80.0


def test_calculate_quality_score_success_no_scores(outcome_tracker):
    """Test quality score calculation for successful print without scores."""
    feedback = HumanFeedback(success=True)

    score = outcome_tracker._calculate_quality_score(feedback)

    # Default for success without scores
    assert score == 80.0


def test_calculate_quality_score_failure(outcome_tracker):
    """Test quality score calculation for failed print."""
    feedback = HumanFeedback(
        success=False,
        failure_reason=FailureReason.warping,
        quality_scores={"layer_consistency": 3},
    )

    score = outcome_tracker._calculate_quality_score(feedback)

    # Failed prints always get 0
    assert score == 0.0


# ============================================================================
# Integration Tests
# ============================================================================


def test_full_outcome_workflow(outcome_tracker, sample_outcome_data, sample_human_feedback):
    """Test complete outcome capture and review workflow."""
    # 1. Capture outcome
    outcome = outcome_tracker.capture_outcome(sample_outcome_data)
    assert not outcome.human_reviewed

    # 2. Request human review
    success = outcome_tracker.request_human_review("job123")
    assert success

    # 3. Verify in pending review list
    pending = outcome_tracker.list_outcomes_pending_review()
    assert len(pending) == 1
    assert pending[0].job_id == "job123"

    # 4. Record human feedback
    outcome = outcome_tracker.record_human_feedback("job123", sample_human_feedback)
    assert outcome.human_reviewed

    # 5. Verify no longer in pending list
    pending = outcome_tracker.list_outcomes_pending_review()
    assert len(pending) == 0

    # 6. Verify in completed list
    completed = outcome_tracker.list_outcomes(success=True)
    assert len(completed) == 1
    assert completed[0].job_id == "job123"
