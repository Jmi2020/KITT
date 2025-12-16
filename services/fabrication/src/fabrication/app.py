"""FastAPI application for the fabrication service."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
from decimal import Decimal
import re
from pathlib import Path
from typing import Dict, List, Optional

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from common.config import settings
from common.db import get_db
from common.db.models import (
    InventoryStatus,
    Material as MaterialModel,
    InventoryItem as InventoryItemModel,
    PrintOutcome as PrintOutcomeModel,
    FailureReason,
)
from common.logging import configure_logging, get_logger

from .analysis.stl_analyzer import STLAnalyzer, ModelDimensions
from .selector.printer_selector import PrinterSelector, PrintMode, SelectionResult
from .status.printer_status import PrinterStatusChecker, PrinterStatus
from .launcher.slicer_launcher import SlicerLauncher
from .intelligence.material_inventory import MaterialInventory, InventoryFilters
from .monitoring.outcome_tracker import PrintOutcomeTracker, PrintOutcomeData
from .monitoring.camera_capture import CameraCapture
from .coordinator.queue_optimizer import QueueOptimizer
from .coordinator.scheduler import ParallelJobScheduler
from .coordinator.distributor import JobDistributor
from .routes.bambu import router as bambu_router
from .routes.segmentation import router as segmentation_router

# Configure logging
configure_logging()
LOGGER = get_logger(__name__)

UNIT_FACTORS = {
    "mm": 1.0,
    "millimeter": 1.0,
    "millimeters": 1.0,
    "cm": 10.0,
    "centimeter": 10.0,
    "centimeters": 10.0,
    "m": 1000.0,
    "meter": 1000.0,
    "meters": 1000.0,
    "in": 25.4,
    "inch": 25.4,
    "inches": 25.4,
    "\"": 25.4,
    "ft": 304.8,
    "foot": 304.8,
    "feet": 304.8,
}


def _parse_height_to_mm(raw_value: Optional[str]) -> Optional[float]:
    """Parse a human-friendly height string (e.g., '6 in', '150mm') to millimeters."""
    if not raw_value:
        return None

    normalized = (
        raw_value.strip()
        .lower()
        .replace("″", "\"")
        .replace("”", "\"")
        .replace("′", "'")
        .replace("’", "'")
    )
    pattern = re.compile(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*([a-z\"']*)\s*$")
    match = pattern.match(normalized)
    if not match:
        raise ValueError(
            f"Unable to parse height value '{raw_value}'. Use formats like '150 mm' or '6 in'."
        )

    value = float(match.group(1))
    unit = match.group(2) or "mm"
    unit = unit.strip()
    if unit in {"", None}:
        unit = "mm"

    if unit not in UNIT_FACTORS:
        raise ValueError(
            f"Unsupported unit '{unit}' in height '{raw_value}'. "
            "Use mm, cm, m, in, or ft."
        )

    return round(value * UNIT_FACTORS[unit], 3)


# Host to container path translation
# When running in Docker, host paths like /Users/Shared/KITTY/artifacts need to
# be translated to container paths like /app/artifacts
_HOST_ARTIFACT_DIRS = [
    "/Users/Shared/KITTY/artifacts",  # macOS default
    "/home/kitty/artifacts",           # Linux alternative
]
_CONTAINER_ARTIFACT_DIR = "/app/artifacts"


def _translate_host_path(host_path: str) -> Path:
    """Translate a host filesystem path to the equivalent container path."""
    for host_dir in _HOST_ARTIFACT_DIRS:
        if host_path.startswith(host_dir):
            # Replace host prefix with container prefix
            container_path = host_path.replace(host_dir, _CONTAINER_ARTIFACT_DIR, 1)
            return Path(container_path)
    # Not a host path, return as-is
    return Path(host_path)


# Global service components
analyzer: Optional[STLAnalyzer] = None
status_checker: Optional[PrinterStatusChecker] = None
selector: Optional[PrinterSelector] = None
launcher: Optional[SlicerLauncher] = None
material_inventory: Optional[MaterialInventory] = None
outcome_tracker: Optional[PrintOutcomeTracker] = None
camera_capture: Optional[CameraCapture] = None
db_session: Optional[sessionmaker] = None

# P3 #20: Multi-printer coordination components
queue_optimizer: Optional[QueueOptimizer] = None
job_scheduler: Optional[ParallelJobScheduler] = None
job_distributor: Optional[JobDistributor] = None
mq_client: Optional[object] = None  # MessageQueueClient


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for fabrication service startup/shutdown."""
    global analyzer, status_checker, selector, launcher, material_inventory, outcome_tracker, camera_capture, db_session
    global queue_optimizer, job_scheduler, job_distributor, mq_client

    LOGGER.info("Starting fabrication service")

    # Initialize database connection
    engine = create_engine(settings.database_url)
    db_session = sessionmaker(bind=engine)

    # Initialize components
    analyzer = STLAnalyzer()
    status_checker = PrinterStatusChecker(settings)
    selector = PrinterSelector(analyzer, status_checker)
    launcher = SlicerLauncher()

    # Initialize material inventory (Phase 4)
    db = db_session()
    material_inventory = MaterialInventory(
        db=db,
        low_inventory_threshold_grams=float(getattr(settings, 'LOW_INVENTORY_THRESHOLD_GRAMS', 100.0)),
        waste_factor=float(getattr(settings, 'MATERIAL_WASTE_FACTOR', 1.05)),
    )
    LOGGER.info("Material inventory initialized", threshold=material_inventory.low_inventory_threshold)

    # Initialize camera capture (Phase 4)
    camera_capture = CameraCapture(
        minio_client=None,  # TODO: Wire up MinIO client for snapshot upload
        mqtt_client=None,   # TODO: Wire up MQTT client for Bamboo Labs
        bucket_name="prints",
    )
    LOGGER.info("Camera capture initialized", enabled=settings.enable_camera_capture)

    # Initialize print outcome tracker (Phase 4)
    outcome_tracker = PrintOutcomeTracker(
        db=db,
        mqtt_client=None,     # TODO: Wire up MQTT client for feedback requests
    )
    LOGGER.info("Print outcome tracker initialized", enabled=settings.enable_print_outcome_tracking)

    # Initialize multi-printer coordination (P3 #20)
    try:
        from common.messaging.client import MessageQueueClient

        # Initialize RabbitMQ client
        rabbitmq_url = getattr(settings, 'rabbitmq_url', 'amqp://guest:guest@localhost:5672/')
        mq_client = MessageQueueClient(
            url=rabbitmq_url,
            connection_name="fabrication-coordinator",
        )
        mq_client.connect()
        LOGGER.info("RabbitMQ client connected", url=rabbitmq_url.split('@')[-1])

        # Initialize coordinator components
        queue_optimizer = QueueOptimizer(
            db=db,
            analyzer=analyzer,
        )
        LOGGER.info("Queue optimizer initialized")

        job_scheduler = ParallelJobScheduler(
            db=db,
            status_checker=status_checker,
            queue_optimizer=queue_optimizer,
        )
        LOGGER.info("Job scheduler initialized")

        job_distributor = JobDistributor(
            mq_client=mq_client,
        )
        LOGGER.info("Job distributor initialized")

    except Exception as e:
        LOGGER.error("Failed to initialize multi-printer coordination", error=str(e), exc_info=True)
        # Non-fatal: Service can run without coordination (manual workflow still works)
        queue_optimizer = None
        job_scheduler = None
        job_distributor = None
        mq_client = None

    yield

    # Cleanup
    if status_checker:
        status_checker.cleanup()

    if material_inventory and material_inventory.db:
        material_inventory.db.close()

    if outcome_tracker and outcome_tracker.db:
        outcome_tracker.db.close()

    if mq_client and hasattr(mq_client, 'disconnect'):
        mq_client.disconnect()
        LOGGER.info("RabbitMQ client disconnected")

    # Note: camera_capture has no cleanup needed (no persistent resources)

    LOGGER.info("Fabrication service stopped")


app = FastAPI(
    title="KITTY Fabrication Service",
    description="Multi-printer control with intelligent selection",
    version="1.0.0",
    lifespan=lifespan
)

# Mount static files for queue dashboard
static_dir = Path(__file__).parent.parent.parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Mount artifacts directory for serving segmented parts and other files
# This enables downloading segmented 3MF/STL files via /api/fabrication/artifacts/*
ARTIFACTS_DIR = Path("/app/artifacts")
if ARTIFACTS_DIR.exists():
    app.mount("/api/fabrication/artifacts", StaticFiles(directory=str(ARTIFACTS_DIR)), name="artifacts")
    LOGGER.info("Mounted artifacts directory", path=str(ARTIFACTS_DIR))

# Include Bambu Labs printer routes
app.include_router(bambu_router)

# Include mesh segmentation routes
app.include_router(segmentation_router)


# ============================================================================
# Request/Response Models
# ============================================================================

class OpenInSlicerRequest(BaseModel):
    """Request to open STL in slicer app (manual workflow)."""

    stl_path: str = Field(
        ...,
        description="Absolute path to STL file",
        examples=["/Users/Shared/KITTY/artifacts/cad/bracket.stl"]
    )
    print_mode: str = Field(
        default="3d_print",
        description="Print mode: 3d_print, cnc, laser",
        examples=["3d_print", "cnc", "laser"]
    )
    force_printer: Optional[str] = Field(
        default=None,
        description="Override printer selection (bamboo_h2d, elegoo_giga, snapmaker_artisan)",
        examples=["bamboo_h2d"]
    )
    target_height: Optional[str] = Field(
        default=None,
        description="Desired printed height (e.g., '6 in', '150 mm')",
        examples=["6 in", "150 mm"]
    )


class OpenInSlicerResponse(BaseModel):
    """Response from opening slicer app."""

    success: bool
    printer_id: str
    slicer_app: str
    stl_path: str
    reasoning: str
    model_dimensions: ModelDimensions
    printer_available: bool
    target_height_mm: Optional[float] = None


class AnalyzeModelRequest(BaseModel):
    """Request to analyze STL dimensions."""

    stl_path: str = Field(
        ...,
        description="Absolute path to STL file",
        examples=["/Users/Shared/KITTY/artifacts/cad/bracket.stl"]
    )
    print_mode: str = Field(
        default="3d_print",
        description="Print mode for printer selection preview",
        examples=["3d_print"]
    )
    target_height: Optional[str] = Field(
        default=None,
        description="Desired printed height (optional; e.g., '5 in', '200 mm')",
        examples=["5 in", "200 mm"]
    )


class AnalyzeModelResponse(BaseModel):
    """Model analysis with printer recommendation."""

    dimensions: ModelDimensions
    recommended_printer: str
    slicer_app: str
    reasoning: str
    printer_available: bool
    model_fits: bool
    target_height_mm: Optional[float] = None


class PrinterStatusResponse(BaseModel):
    """All printer statuses."""

    printers: dict[str, PrinterStatus]


# ============================================================================
# Phase 4: Material Inventory Request/Response Models
# ============================================================================

class MaterialResponse(BaseModel):
    """Material catalog item response."""

    id: str
    material_type: str
    color: str
    manufacturer: str
    cost_per_kg_usd: float
    density_g_cm3: float
    nozzle_temp_min_c: int
    nozzle_temp_max_c: int
    bed_temp_min_c: int
    bed_temp_max_c: int
    properties: Dict
    sustainability_score: Optional[int] = None


class InventoryItemResponse(BaseModel):
    """Inventory item (spool) response."""

    id: str
    material_id: str
    location: Optional[str] = None
    purchase_date: datetime
    initial_weight_grams: float
    current_weight_grams: float
    status: str
    notes: Optional[str] = None


class AddInventoryRequest(BaseModel):
    """Request to add new spool to inventory."""

    spool_id: str = Field(..., description="Unique spool identifier", examples=["spool_001"])
    material_id: str = Field(..., description="Material catalog ID", examples=["pla_black_esun"])
    initial_weight_grams: float = Field(..., description="Initial spool weight in grams", examples=[1000.0])
    purchase_date: datetime = Field(..., description="Date spool was purchased")
    location: Optional[str] = Field(None, description="Storage location", examples=["shelf_a"])
    notes: Optional[str] = Field(None, description="Optional notes")


class DeductUsageRequest(BaseModel):
    """Request to deduct material usage from spool."""

    spool_id: str = Field(..., description="Spool identifier", examples=["spool_001"])
    grams_used: float = Field(..., description="Amount of material used in grams", examples=[150.5])


class UsageEstimateRequest(BaseModel):
    """Request to estimate material usage from STL."""

    stl_volume_cm3: float = Field(..., description="STL model volume in cubic centimeters", examples=[100.0])
    infill_percent: int = Field(..., description="Infill percentage (0-100)", examples=[20])
    material_id: str = Field(..., description="Material catalog ID", examples=["pla_black_esun"])
    supports_enabled: bool = Field(default=False, description="Whether supports are enabled")


class UsageEstimateResponse(BaseModel):
    """Material usage estimation result."""

    estimated_grams: float
    infill_percent: int
    supports_enabled: bool
    stl_volume_cm3: float
    adjusted_volume_cm3: float
    material_density: float
    waste_factor: float


class CostEstimateRequest(BaseModel):
    """Request to estimate print cost."""

    material_id: str = Field(..., description="Material catalog ID", examples=["pla_black_esun"])
    grams_used: float = Field(..., description="Amount of material in grams", examples=[100.0])


class CostEstimateResponse(BaseModel):
    """Print cost estimation result."""

    material_cost_usd: float
    grams_used: float
    cost_per_kg: float
    material_id: str


# ============================================================================
# Phase 4: Print Outcome Request/Response Models
# ============================================================================

class RecordOutcomeRequest(BaseModel):
    """Request to record a print outcome."""

    job_id: str = Field(..., description="Unique job identifier", examples=["job_20250114_001"])
    printer_id: str = Field(..., description="Printer that executed job", examples=["bamboo_h2d"])
    material_id: str = Field(..., description="Material catalog ID", examples=["pla_black_esun"])
    success: bool = Field(..., description="Whether print succeeded")
    quality_score: float = Field(..., description="Quality rating 0-100", ge=0, le=100)
    actual_duration_hours: float = Field(..., description="Print duration in hours", examples=[2.5])
    actual_cost_usd: float = Field(..., description="Total print cost", examples=[1.25])
    material_used_grams: float = Field(..., description="Material consumed", examples=[100.5])
    print_settings: Dict = Field(..., description="Print settings (temp, speed, layer height, infill)")
    started_at: datetime = Field(..., description="Print start timestamp")
    completed_at: datetime = Field(..., description="Print completion timestamp")
    failure_reason: Optional[str] = Field(None, description="Failure classification if not successful")
    quality_metrics: Optional[Dict] = Field(None, description="Quality metrics (layer_consistency, surface_finish)")
    initial_snapshot_url: Optional[str] = Field(None, description="First layer snapshot URL")
    final_snapshot_url: Optional[str] = Field(None, description="Completed print snapshot URL")
    snapshot_urls: Optional[List[str]] = Field(None, description="All periodic snapshot URLs")
    video_url: Optional[str] = Field(None, description="Timelapse video URL")
    goal_id: Optional[str] = Field(None, description="Goal ID if autonomous")


class PrintOutcomeResponse(BaseModel):
    """Print outcome response."""

    id: str
    job_id: str
    printer_id: str
    material_id: str
    success: bool
    failure_reason: Optional[str] = None
    quality_score: float
    actual_duration_hours: float
    actual_cost_usd: float
    material_used_grams: float
    print_settings: Dict
    quality_metrics: Dict
    started_at: datetime
    completed_at: datetime
    measured_at: datetime
    initial_snapshot_url: Optional[str] = None
    final_snapshot_url: Optional[str] = None
    snapshot_urls: List[str] = []
    video_url: Optional[str] = None
    human_reviewed: bool
    review_requested_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None
    reviewed_by: Optional[str] = None
    goal_id: Optional[str] = None


class UpdateReviewRequest(BaseModel):
    """Request to update human review."""

    reviewed_by: str = Field(..., description="Reviewer user ID", examples=["user_123"])
    quality_score: Optional[float] = Field(None, description="Updated quality score 0-100", ge=0, le=100)
    failure_reason: Optional[str] = Field(None, description="Updated failure reason")
    notes: Optional[str] = Field(None, description="Review notes")


class OutcomeStatisticsResponse(BaseModel):
    """Outcome statistics response."""

    total_outcomes: int
    success_rate: float
    avg_quality_score: float
    avg_duration_hours: float
    total_cost_usd: float


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/healthz")
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/queue")
async def queue_dashboard():
    """Serve print queue dashboard UI."""
    static_dir = Path(__file__).parent.parent.parent / "static"
    queue_html = static_dir / "queue.html"
    if queue_html.exists():
        return FileResponse(queue_html)
    raise HTTPException(status_code=404, detail="Queue dashboard not found")


@app.post("/api/fabrication/open_in_slicer")
async def open_in_slicer(request: OpenInSlicerRequest) -> OpenInSlicerResponse:
    """
    Open STL file in appropriate slicer app (Manual Workflow - Phase 1).

    Workflow:
    1. Analyze STL dimensions
    2. Select optimal printer based on size and availability
    3. Launch slicer app with STL file
    4. User completes slicing and printing manually

    Printer Selection Hierarchy (Quality-First):
    - Bamboo H2D: First choice for models that fit the H2D build envelope (defaults 250mm; override with H2D_BUILD_* env vars)
    - Elegoo Giga: Fallback if Bamboo busy OR large models beyond H2D limits (fast speed, min axis from ORANGESTORM_GIGA_BUILD_* vars)
    - Snapmaker Artisan: CNC or laser jobs only
    """
    if not analyzer or not selector or not launcher:
        raise HTTPException(status_code=500, detail="Service not initialized")

    stl_path = _translate_host_path(request.stl_path)
    try:
        target_height_mm = _parse_height_to_mm(request.target_height)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Validate STL file exists
    if not stl_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"STL file not found: {request.stl_path}"
        )

    try:
        # Convert print mode string to enum
        try:
            mode = PrintMode(request.print_mode.lower())
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid print mode: {request.print_mode}. "
                       f"Must be one of: 3d_print, cnc, laser"
            )

        # Analyze model dimensions
        LOGGER.info("Analyzing model", path=request.stl_path)
        dimensions = analyzer.analyze(stl_path)

        # Select printer (or use forced override)
        if request.force_printer:
            # Manual override: just get the slicer app
            printer_map = {
                "bamboo_h2d": "BambuStudio",
                "elegoo_giga": "ElegySlicer",
                "snapmaker_artisan": "Luban"
            }
            if request.force_printer not in printer_map:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid printer: {request.force_printer}"
                )

            selection = SelectionResult(
                printer_id=request.force_printer,
                slicer_app=printer_map[request.force_printer],
                reasoning=f"Manual override: {request.force_printer}",
                model_fits=True,
                printer_available=True,
                target_height_mm=target_height_mm
            )
        else:
            # Automatic selection
            LOGGER.info("Selecting printer", mode=mode.value)
            selection = await selector.select_printer(
                stl_path,
                mode,
                target_height_mm=target_height_mm
            )

        # Launch slicer app
        LOGGER.info(
            "Launching slicer",
            app=selection.slicer_app,
            printer=selection.printer_id,
            file=stl_path.name
        )

        launcher.launch(selection.slicer_app, stl_path)

        return OpenInSlicerResponse(
            success=True,
            printer_id=selection.printer_id,
            slicer_app=selection.slicer_app,
            stl_path=request.stl_path,
            reasoning=selection.reasoning,
            model_dimensions=dimensions,
            printer_available=selection.printer_available,
            target_height_mm=selection.target_height_mm
        )

    except FileNotFoundError as e:
        LOGGER.error("Slicer app not found", error=str(e))
        raise HTTPException(status_code=404, detail=str(e))

    except ValueError as e:
        LOGGER.error("Invalid model", error=str(e))
        raise HTTPException(status_code=400, detail=str(e))

    except RuntimeError as e:
        LOGGER.error("Failed to launch slicer", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

    except Exception as e:
        LOGGER.error("Unexpected error", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal error: {e}")


@app.post("/api/fabrication/analyze_model")
async def analyze_model(request: AnalyzeModelRequest) -> AnalyzeModelResponse:
    """
    Analyze STL dimensions and preview printer selection.

    Does NOT launch slicer app. Use this to preview which printer
    would be selected before committing to open the slicer.
    """
    if not analyzer or not selector:
        raise HTTPException(status_code=500, detail="Service not initialized")

    stl_path = _translate_host_path(request.stl_path)
    try:
        target_height_mm = _parse_height_to_mm(request.target_height)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not stl_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"STL file not found: {request.stl_path}"
        )

    try:
        # Convert print mode
        try:
            mode = PrintMode(request.print_mode.lower())
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid print mode: {request.print_mode}"
            )

        # Analyze dimensions
        LOGGER.info("Analyzing model (preview)", path=request.stl_path)
        dimensions = analyzer.analyze(stl_path)

        # Get printer recommendation
        selection = await selector.select_printer(
            stl_path,
            mode,
            target_height_mm=target_height_mm
        )

        return AnalyzeModelResponse(
            dimensions=dimensions,
            recommended_printer=selection.printer_id,
            slicer_app=selection.slicer_app,
            reasoning=selection.reasoning,
            printer_available=selection.printer_available,
            model_fits=selection.model_fits,
            target_height_mm=selection.target_height_mm
        )

    except ValueError as e:
        LOGGER.error("Invalid model", error=str(e))
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        LOGGER.error("Unexpected error", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal error: {e}")


@app.get("/api/fabrication/printer_status")
async def get_printer_status() -> PrinterStatusResponse:
    """
    Get status of all printers.

    Returns current online/offline status and printing state for:
    - Bamboo Labs H2D (via MQTT)
    - Elegoo Giga (via Moonraker HTTP)
    - Snapmaker Artisan (assumed available - no status check in Phase 1)
    """
    if not status_checker:
        raise HTTPException(status_code=500, detail="Service not initialized")

    try:
        LOGGER.info("Fetching printer statuses")
        statuses = await status_checker.get_all_statuses()

        return PrinterStatusResponse(printers=statuses)

    except Exception as e:
        LOGGER.error("Failed to get printer status", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get status: {e}")


# ============================================================================
# Elegoo Giga Direct Control Endpoints (Moonraker API)
# ============================================================================


class SetTemperatureRequest(BaseModel):
    """Request to set bed or nozzle temperature."""
    heater: str = Field(..., description="Heater to control: 'heater_bed' or 'extruder'")
    target: float = Field(..., ge=0, le=350, description="Target temperature in Celsius")


class SetTemperatureResponse(BaseModel):
    """Response from temperature set request."""
    success: bool
    heater: str
    target: float
    message: str


class SendGcodeRequest(BaseModel):
    """Request to send G-code command to printer."""
    command: str = Field(..., min_length=1, description="G-code command(s) to execute")


class GcodeResponse(BaseModel):
    """Response from G-code execution."""
    success: bool
    command: str
    response: Optional[str] = None
    error: Optional[str] = None


class GcodeHistoryEntry(BaseModel):
    """Single entry from G-code history."""
    message: str
    time: float
    type: str = "command"


class GcodeHistoryResponse(BaseModel):
    """Response containing G-code history."""
    history: List[GcodeHistoryEntry]


@app.post("/api/fabrication/elegoo/temperature")
async def set_elegoo_temperature(request: SetTemperatureRequest) -> SetTemperatureResponse:
    """
    Set bed or nozzle temperature on the Elegoo Giga.

    Heater options:
    - 'heater_bed': Set bed temperature (M140)
    - 'extruder': Set nozzle/extruder temperature (M104)

    Target is in Celsius. Set to 0 to turn off heater.
    """
    # Validate heater name
    if request.heater not in ("heater_bed", "extruder"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid heater: {request.heater}. Must be 'heater_bed' or 'extruder'"
        )

    # Build G-code command
    if request.heater == "heater_bed":
        gcode = f"M140 S{request.target}"
    else:
        gcode = f"M104 S{request.target}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"http://{settings.elegoo_ip}:{settings.elegoo_moonraker_port}/printer/gcode/script",
                json={"script": gcode}
            )
            response.raise_for_status()

            LOGGER.info(
                "Set Elegoo temperature",
                heater=request.heater,
                target=request.target,
                gcode=gcode
            )

            return SetTemperatureResponse(
                success=True,
                heater=request.heater,
                target=request.target,
                message=f"Temperature set to {request.target}°C"
            )

    except httpx.TimeoutException:
        LOGGER.error("Timeout setting Elegoo temperature", heater=request.heater)
        raise HTTPException(status_code=504, detail="Printer connection timeout")
    except httpx.HTTPStatusError as e:
        LOGGER.error("HTTP error setting temperature", status=e.response.status_code)
        raise HTTPException(status_code=502, detail=f"Printer error: {e.response.status_code}")
    except Exception as e:
        LOGGER.error("Failed to set temperature", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to set temperature: {e}")


@app.post("/api/fabrication/elegoo/gcode")
async def send_elegoo_gcode(request: SendGcodeRequest) -> GcodeResponse:
    """
    Send a G-code command to the Elegoo Giga.

    Common commands:
    - G28: Home all axes
    - G28 X Y: Home X and Y only
    - M114: Report current position
    - M503: Report settings
    - M106 S255: Fan on full
    - M107: Fan off
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"http://{settings.elegoo_ip}:{settings.elegoo_moonraker_port}/printer/gcode/script",
                json={"script": request.command}
            )
            response.raise_for_status()
            result = response.json()

            LOGGER.info("Sent G-code to Elegoo", command=request.command)

            return GcodeResponse(
                success=True,
                command=request.command,
                response=result.get("result", "ok")
            )

    except httpx.TimeoutException:
        LOGGER.error("Timeout sending G-code", command=request.command)
        return GcodeResponse(
            success=False,
            command=request.command,
            error="Printer connection timeout"
        )
    except httpx.HTTPStatusError as e:
        LOGGER.error("HTTP error sending G-code", command=request.command, status=e.response.status_code)
        return GcodeResponse(
            success=False,
            command=request.command,
            error=f"Printer error: {e.response.status_code}"
        )
    except Exception as e:
        LOGGER.error("Failed to send G-code", command=request.command, error=str(e))
        return GcodeResponse(
            success=False,
            command=request.command,
            error=str(e)
        )


@app.get("/api/fabrication/elegoo/gcode_history")
async def get_elegoo_gcode_history(
    count: int = Query(50, ge=1, le=500, description="Number of entries to retrieve")
) -> GcodeHistoryResponse:
    """
    Get recent G-code command history from the Elegoo Giga.

    Returns the last N commands sent to the printer along with timestamps.
    This is useful for debugging and monitoring printer activity.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"http://{settings.elegoo_ip}:{settings.elegoo_moonraker_port}/server/gcode_store",
                params={"count": count}
            )
            response.raise_for_status()
            result = response.json()

            gcode_store = result.get("result", {}).get("gcode_store", [])

            history = [
                GcodeHistoryEntry(
                    message=entry.get("message", ""),
                    time=entry.get("time", 0),
                    type=entry.get("type", "command")
                )
                for entry in gcode_store
            ]

            return GcodeHistoryResponse(history=history)

    except httpx.TimeoutException:
        LOGGER.error("Timeout getting G-code history")
        raise HTTPException(status_code=504, detail="Printer connection timeout")
    except httpx.HTTPStatusError as e:
        LOGGER.error("HTTP error getting G-code history", status=e.response.status_code)
        raise HTTPException(status_code=502, detail=f"Printer error: {e.response.status_code}")
    except Exception as e:
        LOGGER.error("Failed to get G-code history", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get history: {e}")


# ============================================================================
# Phase 4: Material Inventory API Endpoints
# ============================================================================

@app.get("/api/fabrication/materials", response_model=List[MaterialResponse])
async def list_materials(
    material_type: Optional[str] = Query(None, description="Filter by material type (e.g., pla, petg)"),
    manufacturer: Optional[str] = Query(None, description="Filter by manufacturer"),
) -> List[MaterialResponse]:
    """
    List materials from catalog with optional filters.

    Returns all materials if no filters specified.
    Filter by material_type (pla, petg, abs, tpu, etc.) or manufacturer.
    """
    if not material_inventory:
        raise HTTPException(status_code=500, detail="Material inventory not initialized")

    try:
        materials = material_inventory.list_materials(
            material_type=material_type,
            manufacturer=manufacturer
        )

        return [
            MaterialResponse(
                id=m.id,
                material_type=m.material_type,
                color=m.color,
                manufacturer=m.manufacturer,
                cost_per_kg_usd=float(m.cost_per_kg_usd),
                density_g_cm3=float(m.density_g_cm3),
                nozzle_temp_min_c=m.nozzle_temp_min_c,
                nozzle_temp_max_c=m.nozzle_temp_max_c,
                bed_temp_min_c=m.bed_temp_min_c,
                bed_temp_max_c=m.bed_temp_max_c,
                properties=m.properties,
                sustainability_score=m.sustainability_score,
            )
            for m in materials
        ]

    except Exception as e:
        LOGGER.error("Failed to list materials", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list materials: {e}")


@app.get("/api/fabrication/materials/{material_id}", response_model=MaterialResponse)
async def get_material(material_id: str) -> MaterialResponse:
    """
    Get material by ID.

    Returns material details from catalog.
    """
    if not material_inventory:
        raise HTTPException(status_code=500, detail="Material inventory not initialized")

    try:
        material = material_inventory.get_material(material_id)

        if not material:
            raise HTTPException(status_code=404, detail=f"Material not found: {material_id}")

        return MaterialResponse(
            id=material.id,
            material_type=material.material_type,
            color=material.color,
            manufacturer=material.manufacturer,
            cost_per_kg_usd=float(material.cost_per_kg_usd),
            density_g_cm3=float(material.density_g_cm3),
            nozzle_temp_min_c=material.nozzle_temp_min_c,
            nozzle_temp_max_c=material.nozzle_temp_max_c,
            bed_temp_min_c=material.bed_temp_min_c,
            bed_temp_max_c=material.bed_temp_max_c,
            properties=material.properties,
            sustainability_score=material.sustainability_score,
        )

    except HTTPException:
        raise
    except Exception as e:
        LOGGER.error("Failed to get material", material_id=material_id, error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get material: {e}")


@app.get("/api/fabrication/inventory", response_model=List[InventoryItemResponse])
async def list_inventory(
    material_type: Optional[str] = Query(None, description="Filter by material type"),
    status: Optional[str] = Query(None, description="Filter by status (available, in_use, depleted)"),
    min_weight_grams: Optional[float] = Query(None, description="Minimum weight in grams"),
    max_weight_grams: Optional[float] = Query(None, description="Maximum weight in grams"),
    location: Optional[str] = Query(None, description="Filter by location"),
) -> List[InventoryItemResponse]:
    """
    List inventory items (spools) with optional filters.

    Returns all spools if no filters specified.
    """
    if not material_inventory:
        raise HTTPException(status_code=500, detail="Material inventory not initialized")

    try:
        # Build filters
        filters = InventoryFilters(
            material_type=material_type,
            status=InventoryStatus(status) if status else None,
            min_weight_grams=min_weight_grams,
            max_weight_grams=max_weight_grams,
            location=location,
        )

        items = material_inventory.list_inventory(filters)

        return [
            InventoryItemResponse(
                id=item.id,
                material_id=item.material_id,
                location=item.location,
                purchase_date=item.purchase_date,
                initial_weight_grams=float(item.initial_weight_grams),
                current_weight_grams=float(item.current_weight_grams),
                status=item.status.value,
                notes=item.notes,
            )
            for item in items
        ]

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        LOGGER.error("Failed to list inventory", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list inventory: {e}")


@app.get("/api/fabrication/inventory/{spool_id}", response_model=InventoryItemResponse)
async def get_inventory_item(spool_id: str) -> InventoryItemResponse:
    """
    Get inventory item (spool) by ID.

    Returns spool details including current weight and status.
    """
    if not material_inventory:
        raise HTTPException(status_code=500, detail="Material inventory not initialized")

    try:
        item = material_inventory.get_inventory(spool_id)

        if not item:
            raise HTTPException(status_code=404, detail=f"Spool not found: {spool_id}")

        return InventoryItemResponse(
            id=item.id,
            material_id=item.material_id,
            location=item.location,
            purchase_date=item.purchase_date,
            initial_weight_grams=float(item.initial_weight_grams),
            current_weight_grams=float(item.current_weight_grams),
            status=item.status.value,
            notes=item.notes,
        )

    except HTTPException:
        raise
    except Exception as e:
        LOGGER.error("Failed to get inventory item", spool_id=spool_id, error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get inventory item: {e}")


@app.post("/api/fabrication/inventory", response_model=InventoryItemResponse, status_code=201)
async def add_inventory(request: AddInventoryRequest) -> InventoryItemResponse:
    """
    Add new spool to inventory.

    Creates a new inventory item with initial weight and status=available.
    """
    if not material_inventory:
        raise HTTPException(status_code=500, detail="Material inventory not initialized")

    try:
        item = material_inventory.add_inventory(
            spool_id=request.spool_id,
            material_id=request.material_id,
            initial_weight_grams=request.initial_weight_grams,
            purchase_date=request.purchase_date,
            location=request.location,
            notes=request.notes,
        )

        return InventoryItemResponse(
            id=item.id,
            material_id=item.material_id,
            location=item.location,
            purchase_date=item.purchase_date,
            initial_weight_grams=float(item.initial_weight_grams),
            current_weight_grams=float(item.current_weight_grams),
            status=item.status.value,
            notes=item.notes,
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        LOGGER.error("Failed to add inventory", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to add inventory: {e}")


@app.post("/api/fabrication/inventory/deduct", response_model=InventoryItemResponse)
async def deduct_material_usage(request: DeductUsageRequest) -> InventoryItemResponse:
    """
    Deduct material usage from spool.

    Updates current_weight_grams after a print job.
    Auto-updates status to depleted if weight reaches 0.
    """
    if not material_inventory:
        raise HTTPException(status_code=500, detail="Material inventory not initialized")

    try:
        item = material_inventory.deduct_usage(
            spool_id=request.spool_id,
            grams_used=request.grams_used,
        )

        return InventoryItemResponse(
            id=item.id,
            material_id=item.material_id,
            location=item.location,
            purchase_date=item.purchase_date,
            initial_weight_grams=float(item.initial_weight_grams),
            current_weight_grams=float(item.current_weight_grams),
            status=item.status.value,
            notes=item.notes,
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        LOGGER.error("Failed to deduct usage", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to deduct usage: {e}")


@app.get("/api/fabrication/inventory/low", response_model=List[InventoryItemResponse])
async def check_low_inventory() -> List[InventoryItemResponse]:
    """
    Check for low inventory items.

    Returns spools with weight below threshold (default: 100g).
    Useful for triggering procurement research goals.
    """
    if not material_inventory:
        raise HTTPException(status_code=500, detail="Material inventory not initialized")

    try:
        items = material_inventory.check_low_inventory()

        return [
            InventoryItemResponse(
                id=item.id,
                material_id=item.material_id,
                location=item.location,
                purchase_date=item.purchase_date,
                initial_weight_grams=float(item.initial_weight_grams),
                current_weight_grams=float(item.current_weight_grams),
                status=item.status.value,
                notes=item.notes,
            )
            for item in items
        ]

    except Exception as e:
        LOGGER.error("Failed to check low inventory", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to check low inventory: {e}")


@app.post("/api/fabrication/usage/estimate", response_model=UsageEstimateResponse)
async def estimate_material_usage(request: UsageEstimateRequest) -> UsageEstimateResponse:
    """
    Estimate material usage from STL volume and print settings.

    Calculates grams needed based on volume, infill, supports, density, and waste factor.
    """
    if not material_inventory:
        raise HTTPException(status_code=500, detail="Material inventory not initialized")

    try:
        estimate = material_inventory.calculate_usage(
            stl_volume_cm3=request.stl_volume_cm3,
            infill_percent=request.infill_percent,
            material_id=request.material_id,
            supports_enabled=request.supports_enabled,
        )

        return UsageEstimateResponse(
            estimated_grams=estimate.estimated_grams,
            infill_percent=estimate.infill_percent,
            supports_enabled=estimate.supports_enabled,
            stl_volume_cm3=estimate.stl_volume_cm3,
            adjusted_volume_cm3=estimate.adjusted_volume_cm3,
            material_density=estimate.material_density,
            waste_factor=estimate.waste_factor,
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        LOGGER.error("Failed to estimate usage", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to estimate usage: {e}")


@app.post("/api/fabrication/cost/estimate", response_model=CostEstimateResponse)
async def estimate_print_cost(request: CostEstimateRequest) -> CostEstimateResponse:
    """
    Estimate print cost based on material usage.

    Calculates cost from grams used and material cost per kg.
    """
    if not material_inventory:
        raise HTTPException(status_code=500, detail="Material inventory not initialized")

    try:
        estimate = material_inventory.estimate_print_cost(
            material_id=request.material_id,
            grams_used=request.grams_used,
        )

        return CostEstimateResponse(
            material_cost_usd=float(estimate.material_cost_usd),
            grams_used=estimate.grams_used,
            cost_per_kg=float(estimate.cost_per_kg),
            material_id=estimate.material_id,
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        LOGGER.error("Failed to estimate cost", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to estimate cost: {e}")


# ============================================================================
# Phase 4: Print Outcome API Endpoints
# ============================================================================

@app.post("/api/fabrication/outcomes", response_model=PrintOutcomeResponse, status_code=201)
async def record_print_outcome(request: RecordOutcomeRequest) -> PrintOutcomeResponse:
    """
    Record a print outcome to database.

    Captures success/failure, quality metrics, and visual evidence for learning.
    Optionally requests human feedback via MQTT if enabled.

    Feature flags:
    - ENABLE_PRINT_OUTCOME_TRACKING: Must be true to record outcomes
    - ENABLE_HUMAN_FEEDBACK_REQUESTS: Auto-request human review via MQTT
    """
    if not outcome_tracker:
        raise HTTPException(status_code=500, detail="Outcome tracker not initialized")

    try:
        # Create outcome data (factual print data)
        outcome_data = PrintOutcomeData(
            job_id=request.job_id,
            printer_id=request.printer_id,
            material_id=request.material_id,
            started_at=request.started_at,
            completed_at=request.completed_at,
            actual_duration_hours=request.actual_duration_hours,
            actual_cost_usd=request.actual_cost_usd,
            material_used_grams=request.material_used_grams,
            print_settings=request.print_settings,
            initial_snapshot_url=request.initial_snapshot_url,
            final_snapshot_url=request.final_snapshot_url,
            snapshot_urls=request.snapshot_urls,
            video_url=request.video_url,
            goal_id=request.goal_id,
            quality_metrics=request.quality_metrics,
        )

        # Create human feedback if evaluation provided
        human_feedback = None
        if request.quality_score > 0 or request.failure_reason:
            # Parse failure reason
            failure_reason = None
            if request.failure_reason:
                try:
                    failure_reason = FailureReason(request.failure_reason)
                except ValueError:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid failure reason: {request.failure_reason}"
                    )

            # Import HumanFeedback
            from .monitoring.outcome_tracker import HumanFeedback

            human_feedback = HumanFeedback(
                success=request.success,
                failure_reason=failure_reason,
                quality_scores={"overall": int(request.quality_score / 10)} if request.quality_score > 0 else None,
                notes=None,
                reviewed_by="api_user",
            )

        # Capture outcome
        outcome = outcome_tracker.capture_outcome(outcome_data, human_feedback)

        return _outcome_to_response(outcome)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        LOGGER.error("Failed to record outcome", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to record outcome: {e}")


@app.get("/api/fabrication/outcomes/statistics", response_model=OutcomeStatisticsResponse)
async def get_outcome_statistics(
    printer_id: Optional[str] = Query(None, description="Filter by printer"),
    material_id: Optional[str] = Query(None, description="Filter by material"),
) -> OutcomeStatisticsResponse:
    """
    Get print outcome statistics.

    Returns success rate, average quality score, duration, and total cost.
    Used for printer/material performance tracking and intelligence training.
    """
    if not outcome_tracker:
        raise HTTPException(status_code=500, detail="Outcome tracker not initialized")

    try:
        stats = outcome_tracker.get_statistics(
            printer_id=printer_id,
            material_id=material_id,
        )

        return OutcomeStatisticsResponse(**stats)

    except Exception as e:
        LOGGER.error("Failed to get statistics", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get statistics: {e}")


@app.get("/api/fabrication/outcomes/{job_id}", response_model=PrintOutcomeResponse)
async def get_print_outcome(job_id: str) -> PrintOutcomeResponse:
    """
    Get print outcome by job ID.

    Returns outcome details including visual evidence and human review status.
    """
    if not outcome_tracker:
        raise HTTPException(status_code=500, detail="Outcome tracker not initialized")

    try:
        outcome = outcome_tracker.get_outcome(job_id)

        if not outcome:
            raise HTTPException(status_code=404, detail=f"Outcome not found: {job_id}")

        return _outcome_to_response(outcome)

    except HTTPException:
        raise
    except Exception as e:
        LOGGER.error("Failed to get outcome", job_id=job_id, error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get outcome: {e}")


@app.get("/api/fabrication/outcomes", response_model=List[PrintOutcomeResponse])
async def list_print_outcomes(
    printer_id: Optional[str] = Query(None, description="Filter by printer"),
    material_id: Optional[str] = Query(None, description="Filter by material"),
    success: Optional[bool] = Query(None, description="Filter by success status"),
    limit: int = Query(100, description="Max results", ge=1, le=1000),
    offset: int = Query(0, description="Pagination offset", ge=0),
) -> List[PrintOutcomeResponse]:
    """
    List print outcomes with optional filters.

    Returns outcomes ordered by completion time (most recent first).
    Use for historical analysis and success rate tracking.
    """
    if not outcome_tracker:
        raise HTTPException(status_code=500, detail="Outcome tracker not initialized")

    try:
        outcomes = outcome_tracker.list_outcomes(
            printer_id=printer_id,
            material_id=material_id,
            success=success,
            limit=limit,
            offset=offset,
        )

        return [_outcome_to_response(outcome) for outcome in outcomes]

    except Exception as e:
        LOGGER.error("Failed to list outcomes", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list outcomes: {e}")


@app.patch("/api/fabrication/outcomes/{job_id}/review", response_model=PrintOutcomeResponse)
async def update_outcome_review(job_id: str, request: UpdateReviewRequest) -> PrintOutcomeResponse:
    """
    Update print outcome with human review.

    Allows operators to refine quality scores, failure classifications, and add notes.
    Critical for training intelligence models (Phase 4: Print Intelligence).
    """
    if not outcome_tracker:
        raise HTTPException(status_code=500, detail="Outcome tracker not initialized")

    try:
        # Parse failure reason if provided
        failure_reason = None
        if request.failure_reason:
            try:
                failure_reason = FailureReason(request.failure_reason)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid failure reason: {request.failure_reason}"
                )

        # Import HumanFeedback
        from .monitoring.outcome_tracker import HumanFeedback

        # Create feedback object
        # Infer success from quality_score or presence of failure_reason
        success = (request.quality_score or 0) > 50 if request.quality_score else not failure_reason

        feedback = HumanFeedback(
            success=success,
            failure_reason=failure_reason,
            quality_scores={"overall": int((request.quality_score or 0) / 10)} if request.quality_score else None,
            notes=request.notes,
            reviewed_by=request.reviewed_by,
        )

        # Record feedback
        outcome = outcome_tracker.record_human_feedback(job_id, feedback)

        return _outcome_to_response(outcome)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        LOGGER.error("Failed to update review", job_id=job_id, error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update review: {e}")


def _outcome_to_response(outcome: PrintOutcomeModel) -> PrintOutcomeResponse:
    """Convert PrintOutcome model to response."""
    return PrintOutcomeResponse(
        id=outcome.id,
        job_id=outcome.job_id,
        printer_id=outcome.printer_id,
        material_id=outcome.material_id,
        success=outcome.success,
        failure_reason=outcome.failure_reason.value if outcome.failure_reason else None,
        quality_score=float(outcome.quality_score),
        actual_duration_hours=float(outcome.actual_duration_hours),
        actual_cost_usd=float(outcome.actual_cost_usd),
        material_used_grams=float(outcome.material_used_grams),
        print_settings=outcome.print_settings,
        quality_metrics=outcome.quality_metrics or {},
        started_at=outcome.started_at,
        completed_at=outcome.completed_at,
        measured_at=outcome.measured_at,
        initial_snapshot_url=outcome.initial_snapshot_url,
        final_snapshot_url=outcome.final_snapshot_url,
        snapshot_urls=outcome.snapshot_urls or [],
        video_url=outcome.video_url,
        human_reviewed=outcome.human_reviewed,
        review_requested_at=outcome.review_requested_at,
        reviewed_at=outcome.reviewed_at,
        reviewed_by=outcome.reviewed_by,
        goal_id=outcome.goal_id,
    )


# ============================================================================
# Camera API Endpoints
# ============================================================================


class CameraStatusResponse(BaseModel):
    """Camera status response."""

    printer_id: str = Field(..., description="Printer identifier")
    camera_type: str = Field(..., description="Camera type: bamboo_mqtt or raspberry_pi_http")
    camera_url: Optional[str] = Field(None, description="Camera endpoint URL (for Pi cameras)")
    status: str = Field(..., description="Camera status: online, offline, or unknown")
    last_snapshot_url: Optional[str] = Field(None, description="Most recent snapshot URL")
    last_snapshot_time: Optional[datetime] = Field(None, description="Timestamp of last snapshot")


class SnapshotCaptureRequest(BaseModel):
    """Request to capture a snapshot."""

    job_id: str = Field(..., description="Print job identifier")
    milestone: str = Field("manual", description="Snapshot milestone: start, first_layer, progress, complete, manual")


class SnapshotCaptureResponse(BaseModel):
    """Response from snapshot capture."""

    success: bool = Field(..., description="Whether snapshot was captured successfully")
    url: Optional[str] = Field(None, description="MinIO URL of captured snapshot")
    error: Optional[str] = Field(None, description="Error message if failed")
    milestone: str = Field(..., description="Snapshot milestone")
    timestamp: datetime = Field(..., description="Capture timestamp")


class CameraTestResponse(BaseModel):
    """Response from camera connection test."""

    success: bool = Field(..., description="Whether camera test passed")
    latency_ms: Optional[float] = Field(None, description="Camera response latency in milliseconds")
    error: Optional[str] = Field(None, description="Error message if failed")


class SnapshotGalleryItem(BaseModel):
    """Snapshot item in gallery."""

    milestone: str = Field(..., description="Snapshot milestone")
    url: str = Field(..., description="MinIO snapshot URL")
    timestamp: datetime = Field(..., description="Capture timestamp")


class SnapshotGalleryResponse(BaseModel):
    """Recent snapshot gallery response."""

    job_id: str = Field(..., description="Print job identifier")
    printer_id: str = Field(..., description="Printer identifier")
    snapshots: List[SnapshotGalleryItem] = Field(..., description="List of snapshots for this job")


# ============================================================================
# P3 #20: Multi-Printer Coordination Request/Response Models
# ============================================================================

class SubmitJobRequest(BaseModel):
    """Request to submit print job to queue."""

    job_name: str = Field(..., description="User-friendly job name", examples=["hex_box_v1"])
    stl_path: str = Field(..., description="Absolute path to STL file")
    material_id: str = Field(..., description="Material catalog ID", examples=["pla_black_esun"])
    print_settings: Dict = Field(..., description="Print settings (nozzle_temp, bed_temp, layer_height, infill, speed)")
    priority: int = Field(5, description="Priority 1-10 (1=highest)", ge=1, le=10)
    deadline: Optional[datetime] = Field(None, description="Optional deadline")
    force_printer: Optional[str] = Field(None, description="Force specific printer (bamboo_h2d, elegoo_giga, snapmaker_artisan)")
    created_by: Optional[str] = Field("user", description="User ID or 'autonomous'")


class SubmitJobResponse(BaseModel):
    """Response from job submission."""

    job_id: str
    job_name: str
    status: str
    queue_position: int
    estimated_start_time: Optional[datetime] = None
    printer_id: Optional[str] = None


class QueueJobResponse(BaseModel):
    """Queue job information."""

    job_id: str
    job_name: str
    status: str
    priority: int
    material_id: str
    printer_id: Optional[str] = None
    estimated_duration_hours: float
    estimated_cost_usd: float
    queued_at: datetime
    scheduled_start: Optional[datetime] = None
    deadline: Optional[datetime] = None
    queue_position: Optional[int] = None


class QueueStatusResponse(BaseModel):
    """Queue status response."""

    total_jobs: int
    queued: int
    scheduled: int
    printing: int
    jobs: List[QueueJobResponse]


class ScheduleResponse(BaseModel):
    """Response from manual scheduling trigger."""

    scheduled_jobs: int
    assignments: List[Dict]


class UpdatePriorityRequest(BaseModel):
    """Request to update job priority."""

    priority: int = Field(..., description="New priority 1-10", ge=1, le=10)


class QueueStatisticsResponse(BaseModel):
    """Queue statistics response."""

    total_jobs: int
    by_status: Dict[str, int]
    by_priority: Dict[str, int]
    by_material: Dict[str, int]
    upcoming_deadlines: int
    overdue: int


# ============================================================================
# P3 #17 Queue Optimization Request/Response Models
# ============================================================================

class QueueEstimateResponse(BaseModel):
    """Queue completion time estimate response."""

    printer_id: str
    total_print_hours: float
    total_material_changes: int
    material_change_time_hours: float
    maintenance_time_hours: float
    total_time_hours: float
    estimated_completion: datetime


class MaintenanceStatusResponse(BaseModel):
    """Printer maintenance status response."""

    printer_id: str
    hours_since_maintenance: float
    maintenance_due: bool
    maintenance_interval_hours: int
    next_maintenance_hours: float


@app.get("/api/fabrication/cameras/status", response_model=List[CameraStatusResponse])
async def get_camera_status():
    """Get status of all printer cameras.

    Returns camera status for all configured printers (Bamboo Labs, Snapmaker, Elegoo).
    """
    try:
        # Define camera configurations for all printers
        cameras = [
            {
                "printer_id": "bamboo_h2d",
                "camera_type": "bamboo_mqtt",
                "camera_url": None,  # Bamboo uses MQTT, no HTTP URL
            },
            {
                "printer_id": "snapmaker_artisan",
                "camera_type": "raspberry_pi_http",
                "camera_url": settings.snapmaker_camera_url,
            },
            {
                "printer_id": "elegoo_giga",
                "camera_type": "raspberry_pi_http",
                "camera_url": settings.elegoo_camera_url,
            },
        ]

        # For now, return static status (future: implement actual camera checks)
        status_list = []
        for cam in cameras:
            status_list.append(
                CameraStatusResponse(
                    printer_id=cam["printer_id"],
                    camera_type=cam["camera_type"],
                    camera_url=cam["camera_url"],
                    status="unknown",  # Future: Test camera connectivity
                    last_snapshot_url=None,  # Future: Query from database
                    last_snapshot_time=None,
                )
            )

        return status_list

    except Exception as e:
        LOGGER.error("Failed to get camera status", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get camera status: {e}")


@app.post("/api/fabrication/cameras/{printer_id}/snapshot", response_model=SnapshotCaptureResponse)
async def capture_snapshot(printer_id: str, request: SnapshotCaptureRequest):
    """Capture snapshot from printer camera.

    Args:
        printer_id: Printer identifier (bamboo_h2d, snapmaker_artisan, elegoo_giga)
        request: Snapshot capture request with job_id and milestone

    Returns:
        Snapshot capture result with MinIO URL
    """
    if not camera_capture:
        raise HTTPException(status_code=503, detail="Camera capture service not available")

    try:
        # Capture snapshot
        result = await camera_capture.capture_snapshot(
            printer_id=printer_id,
            job_id=request.job_id,
            milestone=request.milestone,
        )

        return SnapshotCaptureResponse(
            success=result.success,
            url=result.url,
            error=result.error,
            milestone=result.milestone or request.milestone,
            timestamp=result.timestamp or datetime.now(),
        )

    except Exception as e:
        LOGGER.error(
            "Failed to capture snapshot",
            printer_id=printer_id,
            job_id=request.job_id,
            error=str(e),
            exc_info=True,
        )
        return SnapshotCaptureResponse(
            success=False,
            url=None,
            error=str(e),
            milestone=request.milestone,
            timestamp=datetime.now(),
        )


@app.get("/api/fabrication/cameras/{printer_id}/test", response_model=CameraTestResponse)
async def test_camera_connection(printer_id: str):
    """Test camera connection and measure latency.

    Args:
        printer_id: Printer identifier

    Returns:
        Connection test result with latency
    """
    if not camera_capture:
        raise HTTPException(status_code=503, detail="Camera capture service not available")

    try:
        import time

        start_time = time.time()

        # Attempt to capture test snapshot
        result = await camera_capture.capture_snapshot(
            printer_id=printer_id,
            job_id="test_connection",
            milestone="test",
        )

        latency_ms = (time.time() - start_time) * 1000

        return CameraTestResponse(
            success=result.success,
            latency_ms=latency_ms if result.success else None,
            error=result.error,
        )

    except Exception as e:
        LOGGER.error("Camera test failed", printer_id=printer_id, error=str(e), exc_info=True)
        return CameraTestResponse(
            success=False,
            latency_ms=None,
            error=str(e),
        )


@app.get("/api/fabrication/cameras/snapshots/recent", response_model=List[SnapshotGalleryResponse])
async def get_recent_snapshots(limit: int = Query(10, ge=1, le=100)):
    """Get recent snapshot galleries grouped by job.

    Args:
        limit: Maximum number of job galleries to return (default: 10)

    Returns:
        List of snapshot galleries grouped by job_id
    """
    if not outcome_tracker:
        raise HTTPException(status_code=503, detail="Outcome tracker service not available")

    try:
        # Get recent print outcomes with snapshots
        outcomes = outcome_tracker.list_outcomes(limit=limit)

        galleries = []
        for outcome in outcomes:
            if not outcome.snapshot_urls and not outcome.initial_snapshot_url and not outcome.final_snapshot_url:
                continue  # Skip outcomes without snapshots

            snapshots = []

            # Add initial snapshot
            if outcome.initial_snapshot_url:
                snapshots.append(
                    SnapshotGalleryItem(
                        milestone="initial",
                        url=outcome.initial_snapshot_url,
                        timestamp=outcome.started_at,
                    )
                )

            # Add progress snapshots (stored in snapshot_urls JSONB array)
            if outcome.snapshot_urls:
                for idx, url in enumerate(outcome.snapshot_urls):
                    snapshots.append(
                        SnapshotGalleryItem(
                            milestone=f"progress_{idx + 1}",
                            url=url,
                            timestamp=outcome.started_at,  # Approximate, could be enhanced
                        )
                    )

            # Add final snapshot
            if outcome.final_snapshot_url:
                snapshots.append(
                    SnapshotGalleryItem(
                        milestone="final",
                        url=outcome.final_snapshot_url,
                        timestamp=outcome.completed_at,
                    )
                )

            if snapshots:
                galleries.append(
                    SnapshotGalleryResponse(
                        job_id=outcome.job_id,
                        printer_id=outcome.printer_id,
                        snapshots=snapshots,
                    )
                )

        return galleries

    except Exception as e:
        LOGGER.error("Failed to get recent snapshots", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get recent snapshots: {e}")


# ============================================================================
# P3 #20: Multi-Printer Coordination API Endpoints
# ============================================================================

@app.post("/api/fabrication/jobs", response_model=SubmitJobResponse, status_code=201)
async def submit_print_job(request: SubmitJobRequest) -> SubmitJobResponse:
    """
    Submit print job to queue (P3 #20).

    Workflow:
    1. Analyze STL dimensions and estimate material/cost
    2. Create job in database with status=queued
    3. Job will be scheduled automatically by background scheduler
    4. Return queue position and estimated start time

    Args:
        request: Job submission request

    Returns:
        Job submission response with queue position
    """
    if not queue_optimizer or not job_scheduler:
        raise HTTPException(
            status_code=503,
            detail="Multi-printer coordination not available. Service running in manual mode."
        )

    if not analyzer or not material_inventory:
        raise HTTPException(status_code=500, detail="Service not initialized")

    try:
        from uuid import uuid4
        from pathlib import Path
        from common.db.models import QueuedPrint, QueueStatus

        # Validate STL file exists
        stl_path = _translate_host_path(request.stl_path)
        if not stl_path.exists():
            raise HTTPException(status_code=404, detail=f"STL file not found: {request.stl_path}")

        # Analyze model dimensions
        dimensions = analyzer.analyze(stl_path)

        # Estimate material usage and cost
        infill = request.print_settings.get("infill", 20)
        supports = request.print_settings.get("supports_enabled", False)

        usage_estimate = material_inventory.calculate_usage(
            stl_volume_cm3=dimensions.volume / 1000.0,  # Convert mm³ to cm³
            infill_percent=infill,
            material_id=request.material_id,
            supports_enabled=supports,
        )

        cost_estimate = material_inventory.estimate_print_cost(
            material_id=request.material_id,
            grams_used=usage_estimate.estimated_grams,
        )

        # Estimate print duration (rough formula: volume / 15 for typical speeds)
        estimated_hours = dimensions.volume / (1000.0 * 15.0)  # Very rough estimate

        # Create job in database
        job_id = f"job_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"

        job = QueuedPrint(
            id=str(uuid4()),
            job_id=job_id,
            job_name=request.job_name,
            stl_path=request.stl_path,
            gcode_path=None,  # Will be set after slicing
            printer_id=request.force_printer,  # Optional: force specific printer
            material_id=request.material_id,
            spool_id=None,  # TODO: Auto-select available spool
            print_settings=request.print_settings,
            status=QueueStatus.queued if not request.force_printer else QueueStatus.scheduled,
            priority=request.priority,
            deadline=request.deadline,
            estimated_duration_hours=estimated_hours,
            estimated_material_grams=usage_estimate.estimated_grams,
            estimated_cost_usd=cost_estimate.material_cost_usd,
            created_by=request.created_by,
            queued_at=datetime.utcnow(),
        )

        db = db_session()
        db.add(job)
        db.commit()
        db.refresh(job)

        LOGGER.info(
            "Job submitted to queue",
            job_id=job_id,
            job_name=request.job_name,
            material=request.material_id,
            priority=request.priority,
        )

        # Get queue position
        from sqlalchemy import select, func
        stmt = (
            select(func.count())
            .select_from(QueuedPrint)
            .where(
                QueuedPrint.status == QueueStatus.queued,
                QueuedPrint.queued_at < job.queued_at,
            )
        )
        queue_position = db.execute(stmt).scalar() + 1

        db.close()

        return SubmitJobResponse(
            job_id=job_id,
            job_name=request.job_name,
            status=job.status.value,
            queue_position=queue_position,
            printer_id=job.printer_id,
        )

    except HTTPException:
        raise
    except Exception as e:
        LOGGER.error("Failed to submit job", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to submit job: {e}")


@app.get("/api/fabrication/queue", response_model=QueueStatusResponse)
async def get_queue_status(
    status: Optional[str] = Query(None, description="Filter by status"),
    printer_id: Optional[str] = Query(None, description="Filter by printer"),
    limit: int = Query(100, description="Max results", ge=1, le=1000),
) -> QueueStatusResponse:
    """
    Get print queue status (P3 #20).

    Returns all queued, scheduled, and printing jobs with their status.
    """
    if not queue_optimizer:
        raise HTTPException(status_code=503, detail="Multi-printer coordination not available")

    try:
        from sqlalchemy import select
        from common.db.models import QueuedPrint, QueueStatus

        db = db_session()

        # Build query
        stmt = select(QueuedPrint)

        # Apply filters
        if status:
            try:
                status_enum = QueueStatus(status)
                stmt = stmt.where(QueuedPrint.status == status_enum)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

        if printer_id:
            stmt = stmt.where(QueuedPrint.printer_id == printer_id)

        # Order by priority and queue time
        stmt = stmt.order_by(
            QueuedPrint.priority.asc(),
            QueuedPrint.queued_at.asc(),
        ).limit(limit)

        jobs = db.execute(stmt).scalars().all()

        # Count by status
        total_jobs = len(jobs)
        queued_count = sum(1 for j in jobs if j.status == QueueStatus.queued)
        scheduled_count = sum(1 for j in jobs if j.status == QueueStatus.scheduled)
        printing_count = sum(1 for j in jobs if j.status == QueueStatus.printing)

        # Build response
        job_responses = []
        for idx, job in enumerate(jobs):
            job_responses.append(
                QueueJobResponse(
                    job_id=job.job_id,
                    job_name=job.job_name,
                    status=job.status.value,
                    priority=job.priority,
                    material_id=job.material_id,
                    printer_id=job.printer_id,
                    estimated_duration_hours=float(job.estimated_duration_hours),
                    estimated_cost_usd=float(job.estimated_cost_usd),
                    queued_at=job.queued_at,
                    scheduled_start=job.scheduled_start,
                    deadline=job.deadline,
                    queue_position=idx + 1 if job.status == QueueStatus.queued else None,
                )
            )

        db.close()

        return QueueStatusResponse(
            total_jobs=total_jobs,
            queued=queued_count,
            scheduled=scheduled_count,
            printing=printing_count,
            jobs=job_responses,
        )

    except HTTPException:
        raise
    except Exception as e:
        LOGGER.error("Failed to get queue status", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get queue status: {e}")


@app.post("/api/fabrication/schedule", response_model=ScheduleResponse)
async def trigger_scheduling() -> ScheduleResponse:
    """
    Manually trigger job scheduling (P3 #20).

    Schedules jobs for all idle printers and distributes to RabbitMQ.
    Normally this runs automatically in background, but can be triggered manually.
    """
    if not job_scheduler or not job_distributor:
        raise HTTPException(status_code=503, detail="Multi-printer coordination not available")

    try:
        # Schedule jobs for idle printers
        assignments = await job_scheduler.schedule_next_jobs()

        # Distribute assigned jobs to RabbitMQ
        distributed = []
        for assignment in assignments:
            if assignment.status == "scheduled":
                # Get job from database
                from sqlalchemy import select
                from common.db.models import QueuedPrint

                db = db_session()
                stmt = select(QueuedPrint).where(QueuedPrint.job_id == assignment.job_id)
                job = db.execute(stmt).scalar_one_or_none()
                db.close()

                if job:
                    # Distribute to RabbitMQ
                    result = await job_distributor.distribute_job(job)
                    if result.success:
                        distributed.append({
                            "job_id": assignment.job_id,
                            "job_name": assignment.job_name,
                            "printer_id": assignment.printer_id,
                            "status": "scheduled",
                        })

        LOGGER.info("Manual scheduling complete", scheduled=len(distributed))

        return ScheduleResponse(
            scheduled_jobs=len(distributed),
            assignments=distributed,
        )

    except Exception as e:
        LOGGER.error("Failed to trigger scheduling", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to trigger scheduling: {e}")


@app.delete("/api/fabrication/jobs/{job_id}")
async def cancel_job(job_id: str):
    """
    Cancel a queued or scheduled job (P3 #20).

    Args:
        job_id: Job ID to cancel

    Returns:
        Cancellation confirmation
    """
    if not job_scheduler:
        raise HTTPException(status_code=503, detail="Multi-printer coordination not available")

    try:
        success = await job_scheduler.cancel_job(job_id, reason="User requested", cancelled_by="api_user")

        if not success:
            raise HTTPException(status_code=404, detail=f"Job not found or already completed: {job_id}")

        LOGGER.info("Job cancelled", job_id=job_id)

        return {"job_id": job_id, "status": "cancelled", "cancelled_at": datetime.utcnow()}

    except HTTPException:
        raise
    except Exception as e:
        LOGGER.error("Failed to cancel job", job_id=job_id, error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to cancel job: {e}")


@app.patch("/api/fabrication/jobs/{job_id}/priority")
async def update_job_priority(job_id: str, request: UpdatePriorityRequest):
    """
    Update job priority (P3 #20).

    Args:
        job_id: Job ID
        request: New priority (1-10)

    Returns:
        Update confirmation
    """
    if not job_scheduler:
        raise HTTPException(status_code=503, detail="Multi-printer coordination not available")

    try:
        success = await job_scheduler.update_job_priority(
            job_id=job_id,
            new_priority=request.priority,
            updated_by="api_user",
        )

        if not success:
            raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

        LOGGER.info("Job priority updated", job_id=job_id, priority=request.priority)

        return {
            "job_id": job_id,
            "priority": request.priority,
            "updated_at": datetime.utcnow(),
        }

    except HTTPException:
        raise
    except Exception as e:
        LOGGER.error("Failed to update priority", job_id=job_id, error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update priority: {e}")


@app.get("/api/fabrication/queue/statistics", response_model=QueueStatisticsResponse)
async def get_queue_statistics() -> QueueStatisticsResponse:
    """
    Get queue statistics (P3 #20).

    Returns aggregated statistics about the print queue.
    """
    if not queue_optimizer:
        raise HTTPException(status_code=503, detail="Multi-printer coordination not available")

    try:
        stats = await queue_optimizer.get_queue_statistics()

        return QueueStatisticsResponse(**stats)

    except Exception as e:
        LOGGER.error("Failed to get queue statistics", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get queue statistics: {e}")


# ============================================================================
# P3 #17 Queue Optimization Endpoints
# ============================================================================

@app.get("/api/fabrication/queue/estimate/{printer_id}", response_model=QueueEstimateResponse)
async def get_queue_estimate(
    printer_id: str,
    current_material: Optional[str] = Query(None, description="Currently loaded material ID"),
) -> QueueEstimateResponse:
    """
    Get queue completion time estimate for a printer (P3 #17).

    Accounts for:
    - Print durations
    - Material change penalties (15 min each)
    - Maintenance windows (if due)

    Args:
        printer_id: Printer to estimate for (bamboo_h2d, elegoo_giga, snapmaker_artisan)
        current_material: Currently loaded material (for change penalty calculation)

    Returns:
        Queue completion time estimate with breakdown
    """
    if not queue_optimizer:
        raise HTTPException(status_code=503, detail="Multi-printer coordination not available")

    try:
        estimate = await queue_optimizer.estimate_queue_completion(
            printer_id=printer_id,
            current_material=current_material,
        )

        return QueueEstimateResponse(
            printer_id=printer_id,
            total_print_hours=estimate.total_print_hours,
            total_material_changes=estimate.total_material_changes,
            material_change_time_hours=estimate.material_change_time_hours,
            maintenance_time_hours=estimate.maintenance_time_hours,
            total_time_hours=estimate.total_time_hours,
            estimated_completion=estimate.estimated_completion,
        )

    except Exception as e:
        LOGGER.error(
            "Failed to estimate queue completion",
            printer_id=printer_id,
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=f"Failed to estimate queue completion: {e}")


@app.get("/api/fabrication/maintenance/{printer_id}/status", response_model=MaintenanceStatusResponse)
async def get_maintenance_status(printer_id: str) -> MaintenanceStatusResponse:
    """
    Get printer maintenance status (P3 #17).

    Tracks hours printed since last maintenance and indicates when maintenance is due.

    Args:
        printer_id: Printer to check (bamboo_h2d, elegoo_giga, snapmaker_artisan)

    Returns:
        Maintenance status with hours and due flag
    """
    if not queue_optimizer:
        raise HTTPException(status_code=503, detail="Multi-printer coordination not available")

    try:
        is_due, hours_printed = queue_optimizer.check_maintenance_due(printer_id)

        # Calculate hours until next maintenance
        hours_until = queue_optimizer.maintenance_interval_hours - hours_printed

        return MaintenanceStatusResponse(
            printer_id=printer_id,
            hours_since_maintenance=hours_printed,
            maintenance_due=is_due,
            maintenance_interval_hours=queue_optimizer.maintenance_interval_hours,
            next_maintenance_hours=max(0, hours_until),
        )

    except Exception as e:
        LOGGER.error(
            "Failed to get maintenance status",
            printer_id=printer_id,
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=f"Failed to get maintenance status: {e}")


@app.post("/api/fabrication/maintenance/{printer_id}/complete")
async def record_maintenance_completed(printer_id: str) -> dict[str, str]:
    """
    Record maintenance completion for a printer (P3 #17).

    Resets the maintenance counter to zero.

    Args:
        printer_id: Printer that was serviced (bamboo_h2d, elegoo_giga, snapmaker_artisan)

    Returns:
        Success message
    """
    if not queue_optimizer:
        raise HTTPException(status_code=503, detail="Multi-printer coordination not available")

    try:
        queue_optimizer.record_maintenance_completed(printer_id)

        LOGGER.info("Maintenance recorded", printer_id=printer_id)

        return {
            "status": "success",
            "message": f"Maintenance recorded for {printer_id}, counter reset",
        }

    except Exception as e:
        LOGGER.error(
            "Failed to record maintenance",
            printer_id=printer_id,
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=f"Failed to record maintenance: {e}")


# ============================================================================
# P3 #16 Print Success Prediction Request/Response Models
# ============================================================================

class PredictSuccessRequest(BaseModel):
    """Request to predict print success probability."""

    material_id: str = Field(..., description="Material catalog ID", examples=["pla_black_esun"])
    printer_id: str = Field(..., description="Printer identifier", examples=["bamboo_h2d"])
    nozzle_temp: float = Field(..., description="Nozzle temperature °C", examples=[210])
    bed_temp: float = Field(..., description="Bed temperature °C", examples=[60])
    print_speed: float = Field(..., description="Print speed mm/s", examples=[50])
    layer_height: float = Field(..., description="Layer height mm", examples=[0.2])
    infill_percent: float = Field(..., description="Infill percentage", examples=[20])
    supports_enabled: bool = Field(..., description="Supports enabled", examples=[False])


class PredictSuccessResponse(BaseModel):
    """Print success prediction response."""

    success_probability: float  # 0.0 - 1.0
    success_percentage: float  # 0 - 100 (for display)
    risk_level: str  # "low", "medium", "high"
    confidence: float  # Model confidence 0.0 - 1.0
    recommendations: List[str]
    similar_prints_count: int
    similar_success_rate: float
    is_trained: bool


class TrainingStatusResponse(BaseModel):
    """Model training status response."""

    is_trained: bool
    model_exists: bool
    total_outcomes: int
    min_required: int
    ready_to_train: bool
    sklearn_available: bool


# ============================================================================
# P3 #16 Print Success Prediction Endpoints
# ============================================================================

@app.post("/api/fabrication/predict/success", response_model=PredictSuccessResponse)
async def predict_print_success(request: PredictSuccessRequest) -> PredictSuccessResponse:
    """
    Predict print success probability based on settings (P3 #16).

    Uses ML model trained on historical print outcomes to predict success/failure.
    Provides recommendations for high-risk settings.

    Args:
        request: Print settings for prediction

    Returns:
        Success probability, risk level, and recommendations
    """
    from fabrication.intelligence import PrintSuccessPredictor, PrintFeatures

    # Get database session
    db = next(get_db())

    try:
        # Initialize predictor
        predictor = PrintSuccessPredictor(db)

        if not predictor.is_trained:
            # Return fallback prediction
            return PredictSuccessResponse(
                success_probability=0.5,
                success_percentage=50.0,
                risk_level="medium",
                confidence=0.3,
                recommendations=[
                    "⚠️ Model not trained yet - prediction unavailable",
                    "Train model with /api/fabrication/predict/train",
                    "Requires minimum 20 historical print outcomes",
                ],
                similar_prints_count=0,
                similar_success_rate=0.0,
                is_trained=False,
            )

        # Extract features
        features = PrintFeatures(
            material_id=request.material_id,
            printer_id=request.printer_id,
            nozzle_temp=request.nozzle_temp,
            bed_temp=request.bed_temp,
            print_speed=request.print_speed,
            layer_height=request.layer_height,
            infill_percent=request.infill_percent,
            supports_enabled=request.supports_enabled,
        )

        # Predict
        result = await predictor.predict(features)

        return PredictSuccessResponse(
            success_probability=result.success_probability,
            success_percentage=result.success_probability * 100,
            risk_level=result.risk_level,
            confidence=result.confidence,
            recommendations=result.recommendations,
            similar_prints_count=result.similar_prints_count,
            similar_success_rate=result.similar_success_rate,
            is_trained=True,
        )

    except Exception as e:
        LOGGER.error("Failed to predict success", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to predict success: {e}")


@app.post("/api/fabrication/predict/train")
async def train_prediction_model() -> dict:
    """
    Train print success prediction model (P3 #16).

    Trains Random Forest classifier on historical print outcomes.
    Requires minimum 20 outcomes for training.

    Returns:
        Training result with status
    """
    from fabrication.intelligence import PrintSuccessPredictor

    # Get database session
    db = next(get_db())

    try:
        predictor = PrintSuccessPredictor(db)

        LOGGER.info("Starting model training")

        # Train model
        success = predictor.train()

        if success:
            return {
                "status": "success",
                "message": "Model trained successfully",
                "model_path": str(predictor.model_path),
            }
        else:
            # Get training status for details
            status = predictor.get_training_status()
            return {
                "status": "failed",
                "message": "Insufficient training data",
                "total_outcomes": status["total_outcomes"],
                "min_required": status["min_required"],
            }

    except Exception as e:
        LOGGER.error("Failed to train model", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to train model: {e}")


@app.get("/api/fabrication/predict/status", response_model=TrainingStatusResponse)
async def get_prediction_status() -> TrainingStatusResponse:
    """
    Get model training status (P3 #16).

    Returns information about whether model is trained and ready for predictions.

    Returns:
        Training status information
    """
    from fabrication.intelligence import PrintSuccessPredictor

    # Get database session
    db = next(get_db())

    try:
        predictor = PrintSuccessPredictor(db)
        status = predictor.get_training_status()

        return TrainingStatusResponse(**status)

    except Exception as e:
        LOGGER.error("Failed to get prediction status", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get prediction status: {e}")
