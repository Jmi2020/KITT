"""FastAPI application for the fabrication service."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
from decimal import Decimal
import re
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from common.config import settings
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


# Global service components
analyzer: Optional[STLAnalyzer] = None
status_checker: Optional[PrinterStatusChecker] = None
selector: Optional[PrinterSelector] = None
launcher: Optional[SlicerLauncher] = None
material_inventory: Optional[MaterialInventory] = None
outcome_tracker: Optional[PrintOutcomeTracker] = None
camera_capture: Optional[CameraCapture] = None
db_session: Optional[sessionmaker] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for fabrication service startup/shutdown."""
    global analyzer, status_checker, selector, launcher, material_inventory, outcome_tracker, camera_capture, db_session

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

    yield

    # Cleanup
    if status_checker:
        status_checker.cleanup()

    if material_inventory and material_inventory.db:
        material_inventory.db.close()

    if outcome_tracker and outcome_tracker.db:
        outcome_tracker.db.close()

    # Note: camera_capture has no cleanup needed (no persistent resources)

    LOGGER.info("Fabrication service stopped")


app = FastAPI(
    title="KITTY Fabrication Service",
    description="Multi-printer control with intelligent selection",
    version="1.0.0",
    lifespan=lifespan
)


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

    stl_path = Path(request.stl_path)
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

    stl_path = Path(request.stl_path)
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
