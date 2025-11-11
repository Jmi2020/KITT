"""Intelligent printer selection based on model size and printer availability."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

from common.config import settings
from common.logging import get_logger

from ..analysis.stl_analyzer import STLAnalyzer, ModelDimensions
from ..status.printer_status import PrinterStatusChecker, PrinterStatus

LOGGER = get_logger(__name__)


class PrintMode(Enum):
    FDM_3D_PRINT = "3d_print"
    CNC_MILL = "cnc"
    LASER_ENGRAVE = "laser"


@dataclass
class PrinterCapabilities:
    """Printer specifications."""
    printer_id: str
    slicer_app: str  # "BambuStudio", "ElegySlicer", "Luban"
    build_volume: tuple[float, float, float]  # (x, y, z) in mm
    quality: str  # "excellent", "good", "medium"
    speed: str  # "fast", "medium", "slow"
    supported_modes: list[PrintMode]


@dataclass
class SelectionResult:
    """Printer selection decision."""
    printer_id: str
    slicer_app: str
    reasoning: str
    model_fits: bool
    printer_available: bool
    target_height_mm: Optional[float] = None


class PrinterSelector:
    """Select optimal printer for a given model."""

    # Printer capabilities registry
    PRINTERS = {
        "bamboo_h2d": PrinterCapabilities(
            printer_id="bamboo_h2d",
            slicer_app="BambuStudio",
            build_volume=(
                float(settings.h2d_build_width or 250),
                float(settings.h2d_build_depth or 250),
                float(settings.h2d_build_height or 250),
            ),
            quality="excellent",
            speed="medium",
            supported_modes=[PrintMode.FDM_3D_PRINT]
        ),
        "elegoo_giga": PrinterCapabilities(
            printer_id="elegoo_giga",
            slicer_app="ElegySlicer",
            build_volume=(
                float(settings.orangestorm_giga_build_width or 800),
                float(settings.orangestorm_giga_build_depth or 800),
                float(settings.orangestorm_giga_build_height or 1000),
            ),
            quality="good",
            speed="fast",
            supported_modes=[PrintMode.FDM_3D_PRINT]
        ),
        "snapmaker_artisan": PrinterCapabilities(
            printer_id="snapmaker_artisan",
            slicer_app="Luban",
            build_volume=(400, 400, 400),
            quality="good",
            speed="medium",
            supported_modes=[PrintMode.FDM_3D_PRINT, PrintMode.CNC_MILL, PrintMode.LASER_ENGRAVE]
        )
    }

    def __init__(
        self,
        analyzer: STLAnalyzer,
        status_checker: PrinterStatusChecker
    ):
        self.analyzer = analyzer
        self.status_checker = status_checker
        self._bamboo_limit = min(self.PRINTERS["bamboo_h2d"].build_volume)
        self._elegoo_limit = min(self.PRINTERS["elegoo_giga"].build_volume)

    async def select_printer(
        self,
        stl_path: Path,
        mode: PrintMode = PrintMode.FDM_3D_PRINT,
        target_height_mm: Optional[float] = None,
    ) -> SelectionResult:
        """
        Select optimal printer based on model and printer status.

        Priority hierarchy:
        1. CNC or Laser → Snapmaker (only multi-mode printer)
        2. 3D Print:
           - Model ≤250mm AND Bamboo idle → Bamboo (best quality)
           - Model ≤250mm AND Bamboo busy → Elegoo (fallback)
           - Model >250mm AND ≤800mm → Elegoo (only option)
           - Model >800mm → Error (too large)

        Args:
            stl_path: Path to STL file
            mode: Print mode (3d_print, cnc, laser)

        Returns:
            SelectionResult with printer ID, app, and reasoning
        """

        # Step 1: Check for CNC/Laser mode
        if mode in [PrintMode.CNC_MILL, PrintMode.LASER_ENGRAVE]:
            return SelectionResult(
                printer_id="snapmaker_artisan",
                slicer_app="Luban",
                reasoning=f"{mode.value} job requires Snapmaker Artisan (only multi-mode printer)",
                model_fits=True,
                printer_available=True,  # Assume available (no status checking for Snapmaker yet)
                target_height_mm=target_height_mm
            )

        # Step 2: Analyze model dimensions
        dimensions = self.analyzer.analyze(stl_path)
        effective_dimension = target_height_mm if target_height_mm else dimensions.max_dimension
        dimension_label = (
            f"User target height {effective_dimension:.1f}mm"
            if target_height_mm
            else f"Model max dimension {dimensions.max_dimension:.1f}mm"
        )

        LOGGER.info(
            "Model analysis complete",
            max_dimension=f"{dimensions.max_dimension:.1f}mm",
            volume=f"{dimensions.volume:.0f}mm³"
        )

        # Step 3: Check if model too large for all printers
        if effective_dimension > self._elegoo_limit:
            raise ValueError(
                f"Model too large for all printers. "
                f"Requested dimension: {effective_dimension:.1f}mm, "
                f"Largest printer (Elegoo Giga): {self._elegoo_limit:.1f}mm"
            )

        # Step 4: Get printer statuses
        statuses = await self.status_checker.get_all_statuses()
        bamboo_status = statuses["bamboo_h2d"]
        elegoo_status = statuses["elegoo_giga"]

        # Step 5: Apply selection logic (QUALITY-FIRST: Prefer Bamboo for superior quality)
        if effective_dimension <= self._bamboo_limit:
            # Small-medium model, prefer Bamboo for quality
            if bamboo_status.is_online and not bamboo_status.is_printing:
                return SelectionResult(
                    printer_id="bamboo_h2d",
                    slicer_app="BambuStudio",
                    reasoning=(
                        f"{dimension_label} ≤ {self._bamboo_limit:.1f}mm. "
                        f"Bamboo is idle. Using Bamboo for excellent print quality."
                    ),
                    model_fits=True,
                    printer_available=True,
                    target_height_mm=target_height_mm
                )
            else:
                # Bamboo busy or offline, fall back to Elegoo
                return SelectionResult(
                    printer_id="elegoo_giga",
                    slicer_app="ElegySlicer",
                    reasoning=(
                        f"{dimension_label} ≤ {self._bamboo_limit:.1f}mm "
                        f"but Bamboo is {bamboo_status.status}. "
                        f"Using Elegoo Giga as fallback (fast print speed)."
                    ),
                    model_fits=True,
                    printer_available=elegoo_status.is_online,
                    target_height_mm=target_height_mm
                )
        else:
            # Large model, only Elegoo can handle
            return SelectionResult(
                printer_id="elegoo_giga",
                slicer_app="ElegySlicer",
                reasoning=(
                    f"Large request ({dimension_label} > {self._bamboo_limit:.1f}mm) "
                    f"requires Elegoo Giga ({self._elegoo_limit:.1f}mm z-height)."
                ),
                model_fits=True,
                printer_available=elegoo_status.is_online,
                target_height_mm=target_height_mm
            )
