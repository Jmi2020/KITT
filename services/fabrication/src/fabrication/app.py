"""FastAPI application for the fabrication service."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from common.config import settings
from common.logging import configure_logging, get_logger

from .analysis.stl_analyzer import STLAnalyzer, ModelDimensions
from .selector.printer_selector import PrinterSelector, PrintMode, SelectionResult
from .status.printer_status import PrinterStatusChecker, PrinterStatus
from .launcher.slicer_launcher import SlicerLauncher

# Configure logging
configure_logging()
LOGGER = get_logger(__name__)


# Global service components
analyzer: Optional[STLAnalyzer] = None
status_checker: Optional[PrinterStatusChecker] = None
selector: Optional[PrinterSelector] = None
launcher: Optional[SlicerLauncher] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for fabrication service startup/shutdown."""
    global analyzer, status_checker, selector, launcher

    LOGGER.info("Starting fabrication service")

    # Initialize components
    analyzer = STLAnalyzer()
    status_checker = PrinterStatusChecker(settings)
    selector = PrinterSelector(analyzer, status_checker)
    launcher = SlicerLauncher()

    yield

    # Cleanup
    if status_checker:
        status_checker.cleanup()

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


class OpenInSlicerResponse(BaseModel):
    """Response from opening slicer app."""

    success: bool
    printer_id: str
    slicer_app: str
    stl_path: str
    reasoning: str
    model_dimensions: ModelDimensions
    printer_available: bool


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


class AnalyzeModelResponse(BaseModel):
    """Model analysis with printer recommendation."""

    dimensions: ModelDimensions
    recommended_printer: str
    slicer_app: str
    reasoning: str
    printer_available: bool
    model_fits: bool


class PrinterStatusResponse(BaseModel):
    """All printer statuses."""

    printers: dict[str, PrinterStatus]


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
    - Bamboo H2D: First choice for ≤250mm models (excellent quality)
    - Elegoo Giga: Fallback if Bamboo busy OR large models >250mm (fast speed)
    - Snapmaker Artisan: CNC or laser jobs only
    """
    if not analyzer or not selector or not launcher:
        raise HTTPException(status_code=500, detail="Service not initialized")

    stl_path = Path(request.stl_path)

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
                printer_available=True
            )
        else:
            # Automatic selection
            LOGGER.info("Selecting printer", mode=mode.value)
            selection = await selector.select_printer(stl_path, mode)

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
            printer_available=selection.printer_available
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
        selection = await selector.select_printer(stl_path, mode)

        return AnalyzeModelResponse(
            dimensions=dimensions,
            recommended_printer=selection.printer_id,
            slicer_app=selection.slicer_app,
            reasoning=selection.reasoning,
            printer_available=selection.printer_available,
            model_fits=selection.model_fits
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
