# Multi-Printer Control Implementation Plan

## Overview

Implement two-phase printer integration:
- **Phase 1 (Manual Workflow)**: STL analysis + printer selection + slicer app launching
- **Phase 2 (Automatic Workflow)**: Add model scaling, orientation validation, and support detection

This is a pragmatic approach that gives users control while leveraging KITTY's intelligence for prep work.

## Architecture Diagram

```
User: "print this bracket"
    ↓
ReAct Agent: fabrication.open_in_slicer
    ↓
Gateway (:8080/api/fabrication/open_in_slicer)
    ↓
Fabrication Service (:8300)
    ├─ STL Analyzer (trimesh)
    ├─ Printer Status Checker (MQTT + HTTP)
    ├─ Printer Selector (decision logic)
    └─ Slicer Launcher (macOS open command)
    ↓
BambuStudio.app opens with bracket.stl
    ↓
User: slices, configures, and prints manually
```

## Phase 1: Manual Workflow (Default)

### Step 1: STL Analysis Module

**File: `services/fabrication/src/fabrication/analysis/stl_analyzer.py`**

```python
"""STL file analysis using trimesh."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import trimesh
import numpy as np

from common.logging import get_logger

LOGGER = get_logger(__name__)


@dataclass
class ModelDimensions:
    """STL model dimensions and metadata."""
    width: float  # X dimension (mm)
    depth: float  # Y dimension (mm)
    height: float  # Z dimension (mm)
    max_dimension: float  # Largest of width/depth/height
    volume: float  # mm³
    surface_area: float  # mm²
    bounds: tuple  # [[min_x, min_y, min_z], [max_x, max_y, max_z]]


class STLAnalyzer:
    """Analyze STL files for printer selection."""

    def analyze(self, stl_path: Path) -> ModelDimensions:
        """
        Load STL and extract dimensions.

        Args:
            stl_path: Path to STL file

        Returns:
            ModelDimensions with all calculated properties

        Raises:
            FileNotFoundError: STL file doesn't exist
            ValueError: STL file is corrupted or invalid
        """
        if not stl_path.exists():
            raise FileNotFoundError(f"STL file not found: {stl_path}")

        try:
            mesh = trimesh.load(stl_path)
        except Exception as e:
            raise ValueError(f"Failed to load STL: {e}")

        # Validate mesh
        if not mesh.is_valid:
            LOGGER.warning("STL has invalid geometry", path=str(stl_path))

        # Calculate bounding box
        bounds = mesh.bounds  # [[min_x, min_y, min_z], [max_x, max_y, max_z]]
        dimensions = bounds[1] - bounds[0]  # [width, depth, height]

        width, depth, height = dimensions
        max_dim = max(dimensions)

        LOGGER.info(
            "Analyzed STL",
            path=stl_path.name,
            dimensions={
                "width": f"{width:.1f}mm",
                "depth": f"{depth:.1f}mm",
                "height": f"{height:.1f}mm",
                "max": f"{max_dim:.1f}mm"
            }
        )

        return ModelDimensions(
            width=float(width),
            depth=float(depth),
            height=float(height),
            max_dimension=float(max_dim),
            volume=float(mesh.volume),
            surface_area=float(mesh.area),
            bounds=(bounds.tolist(),)
        )

    def scale_model(
        self,
        stl_path: Path,
        target_height: float,
        output_path: Path
    ) -> ModelDimensions:
        """
        Scale STL to target height (Phase 2).

        Args:
            stl_path: Input STL file
            target_height: Desired height in mm
            output_path: Where to save scaled STL

        Returns:
            ModelDimensions of scaled model
        """
        mesh = trimesh.load(stl_path)

        # Calculate current height
        current_height = mesh.bounds[1][2] - mesh.bounds[0][2]
        scale_factor = target_height / current_height

        LOGGER.info(
            "Scaling model",
            from_height=f"{current_height:.1f}mm",
            to_height=f"{target_height:.1f}mm",
            scale_factor=f"{scale_factor:.2f}x"
        )

        # Apply uniform scaling
        mesh.apply_scale(scale_factor)

        # Export scaled mesh
        mesh.export(output_path)

        # Analyze scaled dimensions
        return self.analyze(output_path)
```

### Step 2: Printer Status Checker

**File: `services/fabrication/src/fabrication/status/printer_status.py`**

```python
"""Check printer availability via MQTT and HTTP."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Optional
import json

import httpx
import paho.mqtt.client as mqtt

from common.config import Settings
from common.logging import get_logger

LOGGER = get_logger(__name__)


@dataclass
class PrinterStatus:
    """Printer availability and state."""
    printer_id: str
    is_online: bool
    is_printing: bool
    status: str  # "idle", "printing", "paused", "offline"
    current_job: Optional[str] = None
    progress_percent: Optional[float] = None
    bed_temp: Optional[float] = None
    extruder_temp: Optional[float] = None
    last_updated: Optional[datetime] = None


class PrinterStatusChecker:
    """Query printer status with caching."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._cache: Dict[str, PrinterStatus] = {}
        self._cache_ttl = timedelta(seconds=30)

        # Bamboo MQTT client
        self._bamboo_mqtt: Optional[mqtt.Client] = None
        self._bamboo_status: Dict = {}

    async def get_bamboo_status(self) -> PrinterStatus:
        """
        Check Bamboo H2D status via MQTT.

        Returns cached status if fresh (<30s old).
        """
        printer_id = "bamboo_h2d"

        # Check cache first
        if printer_id in self._cache:
            cached = self._cache[printer_id]
            age = datetime.now() - (cached.last_updated or datetime.min)
            if age < self._cache_ttl:
                LOGGER.debug("Using cached Bamboo status", age_seconds=age.total_seconds())
                return cached

        # Initialize MQTT client if needed
        if not self._bamboo_mqtt:
            self._init_bamboo_mqtt()

        # Wait up to 2 seconds for MQTT message
        await asyncio.sleep(2)

        # Parse status from last MQTT message
        print_state = self._bamboo_status.get("print", {}).get("gcode_state", "IDLE")
        is_printing = print_state in ["RUNNING", "PAUSE"]

        status = PrinterStatus(
            printer_id=printer_id,
            is_online=bool(self._bamboo_status),
            is_printing=is_printing,
            status="printing" if print_state == "RUNNING" else "idle" if print_state == "IDLE" else "offline",
            current_job=self._bamboo_status.get("print", {}).get("subtask_name"),
            progress_percent=self._bamboo_status.get("print", {}).get("mc_percent"),
            bed_temp=self._bamboo_status.get("temps", {}).get("bed_temp"),
            extruder_temp=self._bamboo_status.get("temps", {}).get("nozzle_temp"),
            last_updated=datetime.now()
        )

        self._cache[printer_id] = status
        return status

    def _init_bamboo_mqtt(self) -> None:
        """Initialize MQTT client for Bamboo H2D."""
        self._bamboo_mqtt = mqtt.Client(
            client_id=f"kitty-status-{self.settings.BAMBOO_SERIAL}",
            protocol=mqtt.MQTTv311
        )
        self._bamboo_mqtt.username_pw_set("bblp", self.settings.BAMBOO_ACCESS_CODE)
        self._bamboo_mqtt.on_message = self._on_bamboo_message

        try:
            self._bamboo_mqtt.connect(self.settings.BAMBOO_IP, 1883, keepalive=60)
            self._bamboo_mqtt.subscribe(f"device/{self.settings.BAMBOO_SERIAL}/report")
            self._bamboo_mqtt.loop_start()
            LOGGER.info("Connected to Bamboo MQTT", ip=self.settings.BAMBOO_IP)
        except Exception as e:
            LOGGER.error("Failed to connect to Bamboo MQTT", error=str(e))

    def _on_bamboo_message(self, client, userdata, message):
        """Parse Bamboo MQTT status update."""
        try:
            self._bamboo_status = json.loads(message.payload.decode("utf-8"))
        except Exception as e:
            LOGGER.error("Failed to parse Bamboo MQTT message", error=str(e))

    async def get_elegoo_status(self) -> PrinterStatus:
        """
        Check Elegoo Giga status via Moonraker HTTP.

        Returns cached status if fresh (<30s old).
        """
        printer_id = "elegoo_giga"

        # Check cache
        if printer_id in self._cache:
            cached = self._cache[printer_id]
            age = datetime.now() - (cached.last_updated or datetime.min)
            if age < self._cache_ttl:
                LOGGER.debug("Using cached Elegoo status", age_seconds=age.total_seconds())
                return cached

        # Query Moonraker
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(
                    f"http://{self.settings.ELEGOO_IP}:7125/printer/info"
                )
                response.raise_for_status()
                data = response.json()

                state = data.get("result", {}).get("state", "offline")
                is_printing = state == "printing"

                status = PrinterStatus(
                    printer_id=printer_id,
                    is_online=True,
                    is_printing=is_printing,
                    status="printing" if is_printing else "idle",
                    last_updated=datetime.now()
                )

        except Exception as e:
            LOGGER.warning("Failed to get Elegoo status", error=str(e))
            status = PrinterStatus(
                printer_id=printer_id,
                is_online=False,
                is_printing=False,
                status="offline",
                last_updated=datetime.now()
            )

        self._cache[printer_id] = status
        return status

    async def get_all_statuses(self) -> Dict[str, PrinterStatus]:
        """Get status of all printers concurrently."""
        bamboo, elegoo = await asyncio.gather(
            self.get_bamboo_status(),
            self.get_elegoo_status(),
            return_exceptions=True
        )

        return {
            "bamboo_h2d": bamboo if not isinstance(bamboo, Exception) else PrinterStatus("bamboo_h2d", False, False, "offline"),
            "elegoo_giga": elegoo if not isinstance(elegoo, Exception) else PrinterStatus("elegoo_giga", False, False, "offline")
        }
```

### Step 3: Printer Selector

**File: `services/fabrication/src/fabrication/selector/printer_selector.py`**

```python
"""Intelligent printer selection based on model size and printer availability."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

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


class PrinterSelector:
    """Select optimal printer for a given model."""

    # Printer capabilities registry
    PRINTERS = {
        "bamboo_h2d": PrinterCapabilities(
            printer_id="bamboo_h2d",
            slicer_app="BambuStudio",
            build_volume=(250, 250, 250),
            quality="excellent",
            speed="medium",
            supported_modes=[PrintMode.FDM_3D_PRINT]
        ),
        "elegoo_giga": PrinterCapabilities(
            printer_id="elegoo_giga",
            slicer_app="ElegySlicer",
            build_volume=(800, 800, 1000),
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

    async def select_printer(
        self,
        stl_path: Path,
        mode: PrintMode = PrintMode.FDM_3D_PRINT
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
                printer_available=True  # Assume available (no status checking for Snapmaker yet)
            )

        # Step 2: Analyze model dimensions
        dimensions = self.analyzer.analyze(stl_path)

        LOGGER.info(
            "Model analysis complete",
            max_dimension=f"{dimensions.max_dimension:.1f}mm",
            volume=f"{dimensions.volume:.0f}mm³"
        )

        # Step 3: Check if model too large for all printers
        if dimensions.max_dimension > 800:
            raise ValueError(
                f"Model too large for all printers. "
                f"Max dimension: {dimensions.max_dimension:.1f}mm, "
                f"Largest printer (Elegoo Giga): 800mm"
            )

        # Step 4: Get printer statuses
        statuses = await self.status_checker.get_all_statuses()
        bamboo_status = statuses["bamboo_h2d"]
        elegoo_status = statuses["elegoo_giga"]

        # Step 5: Apply selection logic
        if dimensions.max_dimension <= 250:
            # Small-medium model, prefer Bamboo for quality
            if bamboo_status.is_online and not bamboo_status.is_printing:
                return SelectionResult(
                    printer_id="bamboo_h2d",
                    slicer_app="BambuStudio",
                    reasoning=(
                        f"Model fits Bamboo H2D ({dimensions.max_dimension:.1f}mm ≤ 250mm). "
                        f"Bamboo is idle. Using Bamboo for excellent print quality."
                    ),
                    model_fits=True,
                    printer_available=True
                )
            else:
                # Bamboo busy or offline, fall back to Elegoo
                return SelectionResult(
                    printer_id="elegoo_giga",
                    slicer_app="ElegySlicer",
                    reasoning=(
                        f"Model fits Bamboo ({dimensions.max_dimension:.1f}mm ≤ 250mm) "
                        f"but Bamboo is {bamboo_status.status}. "
                        f"Using Elegoo Giga as fallback (fast print speed)."
                    ),
                    model_fits=True,
                    printer_available=elegoo_status.is_online
                )
        else:
            # Large model, only Elegoo can handle
            return SelectionResult(
                printer_id="elegoo_giga",
                slicer_app="ElegySlicer",
                reasoning=(
                    f"Large model ({dimensions.max_dimension:.1f}mm > 250mm) "
                    f"requires Elegoo Giga (800x800x1000mm build volume)."
                ),
                model_fits=True,
                printer_available=elegoo_status.is_online
            )
```

### Step 4: Slicer App Launcher

**File: `services/fabrication/src/fabrication/launcher/slicer_launcher.py`**

```python
"""Launch macOS slicer applications."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

from common.logging import get_logger

LOGGER = get_logger(__name__)


class SlicerLauncher:
    """Launch slicer applications on macOS."""

    # Application names and bundle identifiers
    APPS = {
        "BambuStudio": "com.bambulab.bambu-studio",
        "ElegySlicer": "com.elegoo.elegyslicer",  # May vary
        "Luban": "com.snapmaker.luban"
    }

    def launch(self, app_name: str, stl_path: Path) -> bool:
        """
        Launch slicer app with STL file on macOS.

        Args:
            app_name: Application name (BambuStudio, ElegySlicer, Luban)
            stl_path: Path to STL file to open

        Returns:
            True if launched successfully

        Raises:
            FileNotFoundError: Slicer app not installed
            RuntimeError: Failed to launch app
        """

        if not stl_path.exists():
            raise FileNotFoundError(f"STL file not found: {stl_path}")

        # Check if app is installed
        if not self._app_exists(app_name):
            raise FileNotFoundError(
                f"{app_name} not installed. "
                f"Download from: {self._get_download_link(app_name)}"
            )

        # Launch app with file
        try:
            subprocess.run(
                ["open", "-a", app_name, str(stl_path)],
                check=True,
                capture_output=True,
                timeout=10
            )
            LOGGER.info("Launched slicer app", app=app_name, file=stl_path.name)
            return True

        except subprocess.CalledProcessError as e:
            LOGGER.error(
                "Failed to launch slicer",
                app=app_name,
                error=e.stderr.decode()
            )
            raise RuntimeError(f"Failed to launch {app_name}: {e.stderr.decode()}")

        except subprocess.TimeoutExpired:
            LOGGER.error("Slicer launch timed out", app=app_name)
            raise RuntimeError(f"Timeout launching {app_name}")

    def _app_exists(self, app_name: str) -> bool:
        """Check if macOS app is installed."""
        try:
            result = subprocess.run(
                ["mdfind", f"kMDItemCFBundleIdentifier == '{self.APPS.get(app_name, app_name)}'"],
                capture_output=True,
                text=True,
                timeout=5
            )
            return bool(result.stdout.strip())
        except Exception:
            # Fallback: try launching and see if it fails
            return True

    def _get_download_link(self, app_name: str) -> str:
        """Get download URL for slicer app."""
        links = {
            "BambuStudio": "https://bambulab.com/en/download",
            "ElegySlicer": "https://www.elegoo.com/pages/3d-printing-user-support",
            "Luban": "https://snapmaker.com/product/snapmaker-luban"
        }
        return links.get(app_name, "Check manufacturer website")
```

### Step 5: Fabrication Service API

**File: `services/fabrication/src/fabrication/app.py`** (Updated)

```python
"""Fabrication service with slicer integration."""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from pathlib import Path
from typing import Optional

from common.config import Settings
from common.logging import get_logger

from .analysis.stl_analyzer import STLAnalyzer
from .status.printer_status import PrinterStatusChecker
from .selector.printer_selector import PrinterSelector, PrintMode
from .launcher.slicer_launcher import SlicerLauncher

LOGGER = get_logger(__name__)

app = FastAPI(title="KITTY Fabrication Service")

# Initialize components
settings = Settings()
analyzer = STLAnalyzer()
status_checker = PrinterStatusChecker(settings)
selector = PrinterSelector(analyzer, status_checker)
launcher = SlicerLauncher()


class OpenInSlicerRequest(BaseModel):
    stl_path: str
    mode: str = "3d_print"


class OpenInSlicerResponse(BaseModel):
    printer_id: str
    slicer_app: str
    message: str
    model_dimensions: dict
    printer_available: bool


@app.post("/api/fabrication/open_in_slicer")
async def open_in_slicer(request: OpenInSlicerRequest) -> OpenInSlicerResponse:
    """
    Manual workflow: Analyze model, select printer, open in slicer.

    This is the default workflow. User completes slicing and printing manually.
    """
    stl_path = Path(request.stl_path)

    if not stl_path.exists():
        raise HTTPException(status_code=404, detail=f"STL file not found: {stl_path}")

    try:
        # Parse mode
        mode = PrintMode(request.mode)

        # Select printer
        selection = await selector.select_printer(stl_path, mode)

        # Get model dimensions for response
        dimensions = analyzer.analyze(stl_path)

        # Launch slicer app
        launcher.launch(selection.slicer_app, stl_path)

        return OpenInSlicerResponse(
            printer_id=selection.printer_id,
            slicer_app=selection.slicer_app,
            message=f"Opening in {selection.slicer_app}. {selection.reasoning}",
            model_dimensions={
                "width": dimensions.width,
                "depth": dimensions.depth,
                "height": dimensions.height,
                "max_dimension": dimensions.max_dimension,
                "volume": dimensions.volume
            },
            printer_available=selection.printer_available
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        LOGGER.error("Failed to open in slicer", error=str(e))
        raise HTTPException(status_code=500, detail=f"Internal error: {e}")


@app.get("/api/fabrication/analyze_model")
async def analyze_model(stl_path: str):
    """Analyze STL dimensions and recommend printer without opening slicer."""
    path = Path(stl_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="STL not found")

    dimensions = analyzer.analyze(path)
    selection = await selector.select_printer(path)

    return {
        "dimensions": {
            "width": dimensions.width,
            "depth": dimensions.depth,
            "height": dimensions.height,
            "max_dimension": dimensions.max_dimension
        },
        "volume": dimensions.volume,
        "recommended_printer": selection.printer_id,
        "slicer_app": selection.slicer_app,
        "reasoning": selection.reasoning
    }


@app.get("/api/fabrication/printer_status")
async def printer_status():
    """Get status of all printers."""
    statuses = await status_checker.get_all_statuses()
    return {
        pid: {
            "is_online": status.is_online,
            "is_printing": status.is_printing,
            "status": status.status,
            "current_job": status.current_job,
            "progress_percent": status.progress_percent
        }
        for pid, status in statuses.items()
    }
```

### Step 6: Gateway Integration

**File: `services/gateway/src/gateway/routes/fabrication.py`** (New)

```python
"""Gateway fabrication routes - proxy to fabrication service."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import httpx
import os

router = APIRouter(prefix="/api/fabrication", tags=["fabrication"])

FABRICATION_BASE = os.getenv("FABRICATION_BASE", "http://fabrication:8300")


class OpenInSlicerRequest(BaseModel):
    stl_path: str
    mode: str = "3d_print"


@router.post("/open_in_slicer")
async def open_in_slicer(request: OpenInSlicerRequest):
    """Proxy to fabrication service - open STL in slicer app."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{FABRICATION_BASE}/api/fabrication/open_in_slicer",
                json=request.dict()
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail=f"Fabrication service error: {e}")


@router.get("/analyze_model")
async def analyze_model(stl_path: str):
    """Analyze STL without opening slicer."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{FABRICATION_BASE}/api/fabrication/analyze_model",
                params={"stl_path": stl_path}
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/printer_status")
async def printer_status():
    """Get status of all printers."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"{FABRICATION_BASE}/api/fabrication/printer_status"
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail=str(e))
```

**Register in `services/gateway/src/gateway/app.py`:**

```python
from .routes.fabrication import router as fabrication_router
app.include_router(fabrication_router)
```

---

## Phase 2: Automatic Workflow (Future)

### Step 7: Vision Server Integration (Phase 2)

**File: `services/fabrication/src/fabrication/vision/orientation_checker.py`**

```python
"""Vision server integration for orientation and support detection."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import httpx

from common.config import Settings
from common.logging import get_logger

LOGGER = get_logger(__name__)


@dataclass
class OrientationAnalysis:
    """Orientation analysis from vision server."""
    score: float  # 0-100, higher is better
    widest_dimension_on_buildplate: bool
    suggested_rotation: Optional[tuple[float, float, float]]  # (x, y, z) degrees
    reasoning: str


@dataclass
class SupportAnalysis:
    """Support detection from vision server."""
    supports_required: bool
    severity: str  # "none", "low", "medium", "high"
    overhang_percentage: float  # % of model with overhangs
    overhang_areas: list  # Locations of overhangs
    reasoning: str


class VisionChecker:
    """Interface to vision service for STL analysis."""

    def __init__(self, settings: Settings):
        self.vision_base = settings.VISION_BASE

    async def analyze_orientation(self, stl_path: Path) -> OrientationAnalysis:
        """
        Call vision service to analyze STL orientation.

        Vision service should:
        - Calculate center of mass
        - Identify widest cross-section
        - Determine if widest area is on Z-axis (build plate)
        - Suggest rotation if orientation is poor

        Args:
            stl_path: Path to STL file

        Returns:
            OrientationAnalysis with score and suggestions
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Send STL file to vision service
            with open(stl_path, 'rb') as f:
                files = {'stl': (stl_path.name, f, 'application/octet-stream')}
                response = await client.post(
                    f"{self.vision_base}/api/vision/analyze_orientation",
                    files=files
                )
                response.raise_for_status()
                data = response.json()

        return OrientationAnalysis(
            score=data['score'],
            widest_dimension_on_buildplate=data['widest_on_buildplate'],
            suggested_rotation=tuple(data['suggested_rotation']) if data.get('suggested_rotation') else None,
            reasoning=data['reasoning']
        )

    async def analyze_supports(self, stl_path: Path) -> SupportAnalysis:
        """
        Call vision service to detect support requirements.

        Vision service should:
        - Iterate through triangles and calculate normals
        - Detect faces with angle > 45° from vertical (overhangs)
        - Calculate percentage of model requiring supports
        - Identify attachment points for supports

        Args:
            stl_path: Path to STL file

        Returns:
            SupportAnalysis with requirements and severity
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            with open(stl_path, 'rb') as f:
                files = {'stl': (stl_path.name, f, 'application/octet-stream')}
                response = await client.post(
                    f"{self.vision_base}/api/vision/analyze_supports",
                    files=files
                )
                response.raise_for_status()
                data = response.json()

        return SupportAnalysis(
            supports_required=data['supports_required'],
            severity=data['severity'],
            overhang_percentage=data['overhang_percentage'],
            overhang_areas=data.get('overhang_areas', []),
            reasoning=data['reasoning']
        )
```

**Add to fabrication service (Phase 2):**

```python
@app.post("/api/fabrication/prepare_print")
async def prepare_print(
    stl_path: str,
    target_height: Optional[float] = None,
    auto_orient: bool = False,
    mode: str = "3d_print"
):
    """
    Automatic workflow: scale, orient, check supports, then open in slicer.

    This is Phase 2 functionality requiring vision server integration.
    """
    path = Path(stl_path)

    # Step 1: Scale if target_height provided
    if target_height:
        scaled_path = path.parent / f"{path.stem}_scaled_{target_height}mm.stl"
        dimensions = analyzer.scale_model(path, target_height, scaled_path)
        path = scaled_path

    # Step 2: Check orientation
    vision_checker = VisionChecker(settings)
    orientation = await vision_checker.analyze_orientation(path)

    if orientation.score < 70 and auto_orient and orientation.suggested_rotation:
        # Apply rotation (implementation needed in STLAnalyzer)
        pass

    # Step 3: Check support requirements
    supports = await vision_checker.analyze_supports(path)

    # Step 4: Select printer and launch
    selection = await selector.select_printer(path, PrintMode(mode))
    launcher.launch(selection.slicer_app, path)

    return {
        "printer": selection.printer_id,
        "slicer_app": selection.slicer_app,
        "message": selection.reasoning,
        "scaled": target_height is not None,
        "orientation": {
            "score": orientation.score,
            "suggestion": orientation.reasoning
        },
        "supports": {
            "required": supports.supports_required,
            "severity": supports.severity,
            "suggestion": supports.reasoning
        }
    }
```

---

## Configuration

### Environment Variables (`.env`)

```bash
# Fabrication Service
FABRICATION_BASE=http://fabrication:8300
VISION_BASE=http://vision:8200

# Bamboo Labs H2D
BAMBOO_IP=192.168.1.100
BAMBOO_SERIAL=01P45165616
BAMBOO_ACCESS_CODE=your_16_char_code

# Elegoo Giga
ELEGOO_IP=192.168.1.200
ELEGOO_MOONRAKER_PORT=7125

# Snapmaker Artisan
SNAPMAKER_IP=192.168.1.150
```

### Printer Configuration (`config/printers.yaml`)

```yaml
version: 1

printers:
  bamboo_h2d:
    type: bamboo_h2d
    slicer_app: BambuStudio
    build_volume: [250, 250, 250]
    quality: excellent
    speed: medium
    ip: ${BAMBOO_IP}
    serial: ${BAMBOO_SERIAL}
    access_code: ${BAMBOO_ACCESS_CODE}

  elegoo_giga:
    type: elegoo_giga
    slicer_app: ElegySlicer
    build_volume: [800, 800, 1000]
    quality: good
    speed: fast
    ip: ${ELEGOO_IP}
    port: 7125

  snapmaker_artisan:
    type: snapmaker_artisan
    slicer_app: Luban
    build_volume: [400, 400, 400]
    quality: good
    speed: medium
    modes: [3d_print, cnc, laser]
    ip: ${SNAPMAKER_IP}
```

---

## Implementation Checklist

### Phase 1: Manual Workflow (Default)

**Week 1:**
- [x] Create spec.md with user stories and requirements
- [x] Update tool_registry.yaml with new tools
- [ ] Implement STLAnalyzer class
- [ ] Implement PrinterStatusChecker class
- [ ] Implement PrinterSelector class

**Week 2:**
- [ ] Implement SlicerLauncher class
- [ ] Create fabrication service API endpoints
- [ ] Create gateway routes
- [ ] Update docker-compose.yml if needed

**Week 3:**
- [ ] Unit tests for STL analysis
- [ ] Unit tests for printer selection logic
- [ ] Integration tests with mock status checker
- [ ] Manual testing with real STL files

**Week 4:**
- [ ] Test with all three printers (Bamboo, Elegoo, Snapmaker)
- [ ] Validate slicer app launching on macOS
- [ ] Update documentation
- [ ] Deploy to production

### Phase 2: Automatic Workflow (Future)

**Week 5-6:**
- [ ] Implement model scaling in STLAnalyzer
- [ ] Implement vision server orientation endpoint
- [ ] Implement vision server support detection endpoint
- [ ] Integrate VisionChecker with fabrication service

**Week 7:**
- [ ] Add `fabrication.prepare_print` endpoint
- [ ] Enable Phase 2 tool in tool_registry.yaml
- [ ] Testing with scaled models
- [ ] Testing with orientation correction

**Week 8:**
- [ ] User acceptance testing
- [ ] Documentation updates
- [ ] Final deployment

---

## Testing Strategy

### Unit Tests

**test_stl_analyzer.py:**
```python
def test_analyze_small_model():
    analyzer = STLAnalyzer()
    dimensions = analyzer.analyze(Path("fixtures/bracket_150mm.stl"))
    assert dimensions.max_dimension <= 200
    assert dimensions.width > 0

def test_analyze_large_model():
    analyzer = STLAnalyzer()
    dimensions = analyzer.analyze(Path("fixtures/enclosure_600mm.stl"))
    assert dimensions.max_dimension > 250
    assert dimensions.max_dimension <= 800
```

**test_printer_selector.py:**
```python
@pytest.mark.asyncio
async def test_select_small_model_bamboo_idle():
    selector = PrinterSelector(mock_analyzer, mock_status_checker)
    # Mock: Bamboo idle, model 150mm
    result = await selector.select_printer(Path("small.stl"))
    assert result.printer_id == "bamboo_h2d"
    assert "excellent" in result.reasoning.lower()

@pytest.mark.asyncio
async def test_select_small_model_bamboo_busy():
    # Mock: Bamboo printing, model 180mm
    result = await selector.select_printer(Path("medium.stl"))
    assert result.printer_id == "elegoo_giga"
    assert "fallback" in result.reasoning.lower()
```

### Integration Tests

```bash
# Test full workflow with real STL
curl -X POST http://localhost:8080/api/fabrication/open_in_slicer \
  -H 'Content-Type: application/json' \
  -d '{"stl_path": "/Users/Shared/KITTY/artifacts/cad/bracket.stl"}'

# Expected response:
{
  "printer_id": "bamboo_h2d",
  "slicer_app": "BambuStudio",
  "message": "Opening in BambuStudio. Model fits Bamboo H2D...",
  "model_dimensions": {"max_dimension": 150.5, ...},
  "printer_available": true
}

# Verify BambuStudio launched with bracket.stl
```

---

## Estimated Timeline

| Phase | Task | Hours |
|-------|------|-------|
| **Phase 1** | STL Analyzer | 4h |
| | Printer Status Checker | 6h |
| | Printer Selector | 4h |
| | Slicer Launcher | 3h |
| | Fabrication Service API | 3h |
| | Gateway Integration | 2h |
| | Testing | 8h |
| **Phase 1 Total** | | **30h (~1 week)** |
| **Phase 2** | Model Scaling | 3h |
| | Vision Server Endpoints | 12h |
| | Vision Integration | 4h |
| | Testing | 6h |
| **Phase 2 Total** | | **25h (~1 week)** |

**Total Estimated Time: 55 hours (~2 weeks full-time)**

---

## Success Criteria

### Phase 1 (Manual Workflow)
- ✅ All STL files analyzed correctly (dimensions extracted)
- ✅ Printer selection logic 100% accurate for test cases
- ✅ BambuStudio, ElegySlicer, Luban all launch successfully on macOS
- ✅ Bamboo H2D status detected via MQTT within 2 seconds
- ✅ Elegoo Giga status detected via Moonraker within 2 seconds
- ✅ Total workflow <10 seconds from API call to slicer open
- ✅ Clear, actionable error messages for all failure cases

### Phase 2 (Automatic Workflow)
- ✅ Model scaling accurate within 0.5mm of target
- ✅ Orientation analysis >85% accuracy on test models
- ✅ Support detection >80% accuracy on overhang models
- ✅ Vision server response time <15 seconds per analysis
- ✅ User satisfaction: "KITTY's recommendations were helpful"

---

## Deployment

```bash
# Phase 1 deployment
cd services/fabrication
pip install -r requirements.txt
pytest tests/unit tests/integration
docker-compose build fabrication
docker-compose up -d fabrication

# Verify
curl http://localhost:8080/api/fabrication/printer_status

# Phase 2 deployment (after vision server ready)
# Enable Phase 2 tool in tool_registry.yaml
# Restart services
docker-compose restart fabrication gateway
```

---

## Next Steps

1. **Immediate (This Week)**:
   - Implement STLAnalyzer (4h)
   - Implement PrinterStatusChecker (6h)
   - Implement PrinterSelector (4h)

2. **Short Term (Next Week)**:
   - Complete Phase 1 implementation
   - Testing with real printers
   - Documentation updates

3. **Medium Term (2-4 Weeks)**:
   - Vision server implementation
   - Phase 2 automatic workflow
   - User acceptance testing

4. **Long Term (Future)**:
   - Auto-slicing integration (Orca Slicer CLI)
   - Direct printer control via APIs (return to original plan)
   - Multi-printer job queue management
