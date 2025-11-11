# Multi-Printer Control Implementation Plan

## Overview
Extend KITTY fabrication service to support three printer types with intelligent printer selection based on model characteristics:
- **Bamboo Labs H2D** - Small to medium prints (FDM)
- **Elegoo OrangeStorm Giga (Klipper)** - Large prints (FDM)
- **Snapmaker Artisan Pro** - CNC machining and laser engraving

## Architecture

### 1. Printer Driver Interface

Create abstract base class for unified printer control:

**File: `services/fabrication/src/fabrication/drivers/base.py`**

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, Any, Optional


class PrinterType(Enum):
    BAMBOO_H2D = "bamboo_h2d"
    ELEGOO_GIGA = "elegoo_giga"
    SNAPMAKER_ARTISAN = "snapmaker_artisan"


class PrintMode(Enum):
    FDM_3D_PRINT = "3d_print"
    CNC_MILL = "cnc"
    LASER_ENGRAVE = "laser"


@dataclass
class PrinterCapabilities:
    """Physical capabilities and specifications"""
    printer_type: PrinterType
    print_modes: list[PrintMode]
    max_x: float  # mm
    max_y: float  # mm
    max_z: float  # mm
    supported_materials: list[str]


@dataclass
class PrinterStatus:
    """Real-time printer state"""
    is_online: bool
    is_printing: bool
    current_job_id: Optional[str]
    bed_temp: Optional[float]
    extruder_temp: Optional[float]
    progress_percent: Optional[float]
    estimated_time_remaining: Optional[int]  # seconds


@dataclass
class PrintJobSpec:
    """Print job specification"""
    job_id: str
    file_path: Path
    print_mode: PrintMode
    nozzle_temp: Optional[int] = None
    bed_temp: Optional[int] = None
    material: Optional[str] = None


class PrinterDriver(ABC):
    """Abstract interface for all printer drivers"""

    def __init__(self, printer_id: str, config: Dict[str, Any]):
        self.printer_id = printer_id
        self.config = config

    @property
    @abstractmethod
    def capabilities(self) -> PrinterCapabilities:
        """Return printer capabilities"""
        pass

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to printer"""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection to printer"""
        pass

    @abstractmethod
    async def get_status(self) -> PrinterStatus:
        """Get current printer status"""
        pass

    @abstractmethod
    async def upload_file(self, file_path: Path) -> str:
        """Upload G-code/CAM file to printer, return remote filename"""
        pass

    @abstractmethod
    async def start_print(self, spec: PrintJobSpec) -> None:
        """Start printing a job"""
        pass

    @abstractmethod
    async def pause_print(self) -> None:
        """Pause current print"""
        pass

    @abstractmethod
    async def resume_print(self) -> None:
        """Resume paused print"""
        pass

    @abstractmethod
    async def cancel_print(self) -> None:
        """Cancel current print"""
        pass
```

### 2. Concrete Driver Implementations

#### 2.1 Bamboo Labs H2D Driver

**File: `services/fabrication/src/fabrication/drivers/bamboo.py`**

Uses MQTT for control and FTPS for file uploads.

```python
import ftplib
import json
from pathlib import Path
import paho.mqtt.client as mqtt
from typing import Dict, Any

from .base import (
    PrinterDriver, PrinterCapabilities, PrinterStatus,
    PrintJobSpec, PrinterType, PrintMode
)


class BambooLabsDriver(PrinterDriver):
    """Bamboo Labs H2D driver using MQTT + FTPS"""

    def __init__(self, printer_id: str, config: Dict[str, Any]):
        super().__init__(printer_id, config)
        self.ip = config["ip"]
        self.serial = config["serial"]
        self.access_code = config["access_code"]
        self.mqtt_host = config.get("mqtt_host", self.ip)  # Local or cloud MQTT
        self.mqtt_port = config.get("mqtt_port", 1883)
        self.mqtt_client: Optional[mqtt.Client] = None
        self._last_status: Dict[str, Any] = {}

    @property
    def capabilities(self) -> PrinterCapabilities:
        return PrinterCapabilities(
            printer_type=PrinterType.BAMBOO_H2D,
            print_modes=[PrintMode.FDM_3D_PRINT],
            max_x=250.0,
            max_y=250.0,
            max_z=250.0,
            supported_materials=["PLA", "PETG", "ABS", "TPU"]
        )

    async def connect(self) -> None:
        """Connect to Bamboo MQTT broker"""
        self.mqtt_client = mqtt.Client(
            client_id=f"kitty-{self.printer_id}",
            protocol=mqtt.MQTTv311
        )
        self.mqtt_client.username_pw_set("bblp", self.access_code)
        self.mqtt_client.on_message = self._on_mqtt_message
        self.mqtt_client.connect(self.mqtt_host, self.mqtt_port, keepalive=60)
        self.mqtt_client.subscribe(f"device/{self.serial}/report")
        self.mqtt_client.loop_start()

    async def disconnect(self) -> None:
        if self.mqtt_client:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()

    def _on_mqtt_message(self, client, userdata, message):
        """Parse printer status from MQTT"""
        self._last_status = json.loads(message.payload.decode("utf-8"))

    async def get_status(self) -> PrinterStatus:
        """Parse cached MQTT status"""
        return PrinterStatus(
            is_online=bool(self._last_status),
            is_printing=self._last_status.get("print", {}).get("state") == "printing",
            current_job_id=self._last_status.get("print", {}).get("job_id"),
            bed_temp=self._last_status.get("temps", {}).get("bed_temp"),
            extruder_temp=self._last_status.get("temps", {}).get("nozzle_temp"),
            progress_percent=self._last_status.get("print", {}).get("percent"),
            estimated_time_remaining=self._last_status.get("print", {}).get("eta")
        )

    async def upload_file(self, file_path: Path) -> str:
        """Upload G-code via FTPS"""
        session = ftplib.FTP_TLS()
        session.connect(self.ip, 990)
        session.auth()
        session.login("bblp", self.access_code)
        session.prot_p()

        with open(file_path, 'rb') as f:
            session.storbinary(f'STOR {file_path.name}', f)

        session.quit()
        return file_path.name

    async def start_print(self, spec: PrintJobSpec) -> None:
        """Send MQTT print command"""
        command = {
            "print": {
                "command": "start",
                "param": str(spec.file_path.name)
            }
        }
        self.mqtt_client.publish(
            f"device/{self.serial}/request",
            json.dumps(command)
        )

    async def pause_print(self) -> None:
        command = {"print": {"command": "pause"}}
        self.mqtt_client.publish(
            f"device/{self.serial}/request",
            json.dumps(command)
        )

    async def resume_print(self) -> None:
        command = {"print": {"command": "resume"}}
        self.mqtt_client.publish(
            f"device/{self.serial}/request",
            json.dumps(command)
        )

    async def cancel_print(self) -> None:
        command = {"print": {"command": "stop"}}
        self.mqtt_client.publish(
            f"device/{self.serial}/request",
            json.dumps(command)
        )
```

#### 2.2 Klipper Driver (Elegoo Giga)

**File: `services/fabrication/src/fabrication/drivers/klipper.py`**

Extends existing MoonrakerClient with full driver interface.

```python
import httpx
from pathlib import Path
from typing import Dict, Any

from .base import (
    PrinterDriver, PrinterCapabilities, PrinterStatus,
    PrintJobSpec, PrinterType, PrintMode
)
from ..klipper.moonraker_client import MoonrakerClient


class KlipperDriver(PrinterDriver):
    """Klipper/Moonraker driver for Elegoo OrangeStorm Giga"""

    def __init__(self, printer_id: str, config: Dict[str, Any]):
        super().__init__(printer_id, config)
        self.ip = config["ip"]
        self.port = config.get("port", 7125)
        self.base_url = f"http://{self.ip}:{self.port}"
        self.client = MoonrakerClient(self.base_url)

    @property
    def capabilities(self) -> PrinterCapabilities:
        return PrinterCapabilities(
            printer_type=PrinterType.ELEGOO_GIGA,
            print_modes=[PrintMode.FDM_3D_PRINT],
            max_x=800.0,  # Giga has 800x800x1000mm build volume
            max_y=800.0,
            max_z=1000.0,
            supported_materials=["PLA", "PETG", "ABS", "TPU", "Nylon"]
        )

    async def connect(self) -> None:
        """Moonraker is stateless HTTP, no connection needed"""
        pass

    async def disconnect(self) -> None:
        """No persistent connection to close"""
        pass

    async def get_status(self) -> PrinterStatus:
        """Query printer status via Moonraker"""
        objects = {
            "print_stats": ["state", "filename"],
            "heater_bed": ["temperature", "target"],
            "extruder": ["temperature", "target"],
            "virtual_sdcard": ["progress"]
        }
        result = await self.client.query_objects(objects)
        status_data = result.get("result", {}).get("status", {})

        print_stats = status_data.get("print_stats", {})
        heater = status_data.get("heater_bed", {})
        extruder = status_data.get("extruder", {})
        sdcard = status_data.get("virtual_sdcard", {})

        return PrinterStatus(
            is_online=True,  # If we got a response, it's online
            is_printing=print_stats.get("state") == "printing",
            current_job_id=print_stats.get("filename"),
            bed_temp=heater.get("temperature"),
            extruder_temp=extruder.get("temperature"),
            progress_percent=sdcard.get("progress", 0) * 100,
            estimated_time_remaining=None  # TODO: calculate from print stats
        )

    async def upload_file(self, file_path: Path) -> str:
        """Upload G-code via HTTP POST"""
        async with httpx.AsyncClient(timeout=300.0) as client:
            with open(file_path, 'rb') as f:
                files = {'file': (file_path.name, f, 'application/octet-stream')}
                response = await client.post(
                    f"{self.base_url}/server/files/upload",
                    files=files
                )
                response.raise_for_status()
        return file_path.name

    async def start_print(self, spec: PrintJobSpec) -> None:
        """Start print via Moonraker JSON-RPC"""
        payload = {
            "jsonrpc": "2.0",
            "method": "printer.print.start",
            "params": {"filename": spec.file_path.name},
            "id": 1
        }
        async with httpx.AsyncClient(base_url=self.base_url, timeout=30) as client:
            response = await client.post("/printer/print/start", json=payload)
            response.raise_for_status()

    async def pause_print(self) -> None:
        await self._send_gcode("PAUSE")

    async def resume_print(self) -> None:
        await self._send_gcode("RESUME")

    async def cancel_print(self) -> None:
        await self._send_gcode("CANCEL_PRINT")

    async def _send_gcode(self, script: str) -> None:
        """Send G-code command"""
        payload = {
            "jsonrpc": "2.0",
            "method": "printer.gcode.script",
            "params": {"script": script},
            "id": 1
        }
        async with httpx.AsyncClient(base_url=self.base_url, timeout=30) as client:
            await client.post("/printer/gcode/script", json=payload)
```

#### 2.3 Snapmaker Driver

**File: `services/fabrication/src/fabrication/drivers/snapmaker.py`**

Custom SACP protocol implementation.

```python
import asyncio
import json
import socket
import struct
from pathlib import Path
from typing import Dict, Any, Optional

from .base import (
    PrinterDriver, PrinterCapabilities, PrinterStatus,
    PrintJobSpec, PrinterType, PrintMode
)


class SnapmakerDriver(PrinterDriver):
    """Snapmaker Artisan Pro driver using SACP protocol"""

    def __init__(self, printer_id: str, config: Dict[str, Any]):
        super().__init__(printer_id, config)
        self.ip = config["ip"]
        self.port = config.get("port", 8888)
        self.socket: Optional[socket.socket] = None
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None

    @property
    def capabilities(self) -> PrinterCapabilities:
        return PrinterCapabilities(
            printer_type=PrinterType.SNAPMAKER_ARTISAN,
            print_modes=[PrintMode.FDM_3D_PRINT, PrintMode.CNC_MILL, PrintMode.LASER_ENGRAVE],
            max_x=400.0,
            max_y=400.0,
            max_z=400.0,
            supported_materials=["PLA", "PETG", "ABS", "Wood", "Acrylic", "Metal"]
        )

    async def connect(self) -> None:
        """Connect to SACP TCP server"""
        self._reader, self._writer = await asyncio.open_connection(self.ip, self.port)

        # Send authentication handshake
        handshake = {
            "command": "enclosure.auth",
            "token": self.config.get("token", "")
        }
        await self._send_command(handshake)
        await self._receive_response()  # Consume auth response

    async def disconnect(self) -> None:
        if self._writer:
            self._writer.close()
            await self._writer.wait_closed()

    async def _send_command(self, command: Dict[str, Any]) -> None:
        """Send SACP command (length-prefixed JSON)"""
        json_str = json.dumps(command)
        message = struct.pack('>I', len(json_str)) + json_str.encode('utf-8')
        self._writer.write(message)
        await self._writer.drain()

    async def _receive_response(self) -> Dict[str, Any]:
        """Receive SACP response"""
        length_data = await self._reader.readexactly(4)
        length = struct.unpack('>I', length_data)[0]
        response_data = await self._reader.readexactly(length)
        return json.loads(response_data.decode('utf-8'))

    async def get_status(self) -> PrinterStatus:
        """Query printer status via SACP"""
        await self._send_command({"command": "system.status"})
        response = await self._receive_response()

        return PrinterStatus(
            is_online=response.get("status") == "ok",
            is_printing=response.get("print_status") == "printing",
            current_job_id=response.get("current_file"),
            bed_temp=response.get("bed_temperature"),
            extruder_temp=response.get("nozzle_temperature"),
            progress_percent=response.get("progress"),
            estimated_time_remaining=response.get("remaining_time")
        )

    async def upload_file(self, file_path: Path) -> str:
        """Upload file via SACP (chunked transfer)"""
        # SACP file upload requires chunked binary transfer
        # Implementation details from Snapmaker SDK
        await self._send_command({
            "command": "file.upload",
            "filename": file_path.name,
            "size": file_path.stat().st_size
        })

        # Upload file in chunks (implementation simplified)
        with open(file_path, 'rb') as f:
            while chunk := f.read(4096):
                # Send chunk with SACP framing
                pass  # TODO: Full chunked upload protocol

        return file_path.name

    async def start_print(self, spec: PrintJobSpec) -> None:
        """Start print job via SACP"""
        await self._send_command({
            "command": "print.start",
            "filename": spec.file_path.name,
            "mode": spec.print_mode.value
        })

    async def pause_print(self) -> None:
        await self._send_command({"command": "print.pause"})

    async def resume_print(self) -> None:
        await self._send_command({"command": "print.resume"})

    async def cancel_print(self) -> None:
        await self._send_command({"command": "print.stop"})
```

### 3. Printer Registry

**File: `services/fabrication/src/fabrication/registry.py`**

Centralized configuration for all printers.

```python
import os
from pathlib import Path
from typing import Dict, List
import yaml

from .drivers.base import PrinterDriver, PrinterType
from .drivers.bamboo import BambooLabsDriver
from .drivers.klipper import KlipperDriver
from .drivers.snapmaker import SnapmakerDriver


class PrinterRegistry:
    """Manages available printers and their configurations"""

    def __init__(self, config_path: Path | None = None):
        if config_path is None:
            config_path = Path(os.getenv("PRINTER_CONFIG", "config/printers.yaml"))

        with open(config_path) as f:
            self.config = yaml.safe_load(f)

        self._drivers: Dict[str, PrinterDriver] = {}
        self._init_drivers()

    def _init_drivers(self) -> None:
        """Initialize printer drivers from config"""
        for printer_id, printer_config in self.config["printers"].items():
            printer_type = PrinterType(printer_config["type"])

            if printer_type == PrinterType.BAMBOO_H2D:
                driver = BambooLabsDriver(printer_id, printer_config)
            elif printer_type == PrinterType.ELEGOO_GIGA:
                driver = KlipperDriver(printer_id, printer_config)
            elif printer_type == PrinterType.SNAPMAKER_ARTISAN:
                driver = SnapmakerDriver(printer_id, printer_config)
            else:
                raise ValueError(f"Unknown printer type: {printer_type}")

            self._drivers[printer_id] = driver

    def get_driver(self, printer_id: str) -> PrinterDriver:
        """Get driver by printer ID"""
        if printer_id not in self._drivers:
            raise ValueError(f"Unknown printer: {printer_id}")
        return self._drivers[printer_id]

    def list_printers(self) -> List[str]:
        """List all registered printer IDs"""
        return list(self._drivers.keys())

    async def get_all_statuses(self) -> Dict[str, Dict]:
        """Get status of all printers"""
        statuses = {}
        for printer_id, driver in self._drivers.items():
            try:
                status = await driver.get_status()
                statuses[printer_id] = {
                    "online": status.is_online,
                    "printing": status.is_printing,
                    "capabilities": {
                        "type": driver.capabilities.printer_type.value,
                        "modes": [m.value for m in driver.capabilities.print_modes],
                        "build_volume": {
                            "x": driver.capabilities.max_x,
                            "y": driver.capabilities.max_y,
                            "z": driver.capabilities.max_z
                        }
                    }
                }
            except Exception as e:
                statuses[printer_id] = {"online": False, "error": str(e)}

        return statuses
```

**Configuration File: `config/printers.yaml`**

```yaml
printers:
  bamboo_h2d:
    type: bamboo_h2d
    ip: 192.168.1.100
    serial: "01P45165616"
    access_code: "YOUR_ACCESS_CODE"
    mqtt_host: 192.168.1.100  # Local MQTT (LAN-only mode)
    mqtt_port: 1883

  elegoo_giga:
    type: elegoo_giga
    ip: 192.168.1.200
    port: 7125
    note: "Klipper with Moonraker on default port"

  snapmaker_artisan:
    type: snapmaker_artisan
    ip: 192.168.1.150
    port: 8888
    token: ""  # Optional SACP auth token
```

### 4. Printer Selection Engine

**File: `services/fabrication/src/fabrication/selector.py`**

Intelligent printer selection based on model characteristics.

```python
from pathlib import Path
from typing import Optional
import trimesh  # For STL bounding box analysis

from .drivers.base import PrintMode, PrinterCapabilities
from .registry import PrinterRegistry


class PrinterSelector:
    """Select optimal printer for a given job"""

    def __init__(self, registry: PrinterRegistry):
        self.registry = registry

    def select_printer(
        self,
        stl_path: Path,
        print_mode: PrintMode = PrintMode.FDM_3D_PRINT,
        preferred_printer: Optional[str] = None
    ) -> str:
        """
        Select printer based on model size and print mode.

        Selection logic:
        - CNC or laser → Snapmaker Artisan (only printer with these capabilities)
        - 3D print, small-medium (≤200mm) → Bamboo H2D
        - 3D print, large (>200mm) → Elegoo Giga
        """

        # If user specifies printer, use it
        if preferred_printer:
            return preferred_printer

        # CNC and laser only supported by Snapmaker
        if print_mode in [PrintMode.CNC_MILL, PrintMode.LASER_ENGRAVE]:
            return "snapmaker_artisan"

        # Analyze STL bounding box for 3D prints
        mesh = trimesh.load(stl_path)
        bounds = mesh.bounds  # [[min_x, min_y, min_z], [max_x, max_y, max_z]]
        dimensions = bounds[1] - bounds[0]  # [width, depth, height]
        max_dim = max(dimensions)

        # Selection thresholds
        SMALL_MEDIUM_THRESHOLD = 200.0  # mm

        if max_dim <= SMALL_MEDIUM_THRESHOLD:
            # Small-medium prints → Bamboo H2D (faster, quieter)
            return "bamboo_h2d"
        else:
            # Large prints → Elegoo Giga (800x800x1000mm build volume)
            return "elegoo_giga"

    def validate_fit(self, stl_path: Path, printer_id: str) -> bool:
        """Check if model fits on specified printer"""
        driver = self.registry.get_driver(printer_id)
        caps = driver.capabilities

        mesh = trimesh.load(stl_path)
        bounds = mesh.bounds
        dimensions = bounds[1] - bounds[0]

        return (
            dimensions[0] <= caps.max_x and
            dimensions[1] <= caps.max_y and
            dimensions[2] <= caps.max_z
        )
```

### 5. Enhanced Job Manager

**File: `services/fabrication/src/fabrication/jobs/manager.py`** (Updated)

```python
from pathlib import Path
from typing import Optional

from common.logging import get_logger

from ..drivers.base import PrintJobSpec, PrintMode
from ..registry import PrinterRegistry
from ..selector import PrinterSelector

LOGGER = get_logger(__name__)


class PrintJobManager:
    """Manages print jobs across multiple printers"""

    def __init__(self, registry: PrinterRegistry):
        self.registry = registry
        self.selector = PrinterSelector(registry)

    async def queue_print(
        self,
        job_id: str,
        file_path: Path,
        print_mode: PrintMode = PrintMode.FDM_3D_PRINT,
        printer_id: Optional[str] = None,
        nozzle_temp: Optional[int] = None,
        bed_temp: Optional[int] = None
    ) -> dict:
        """
        Queue print job with automatic or manual printer selection.

        Returns:
            dict with printer_id, job_id, status
        """

        # Auto-select printer if not specified
        if printer_id is None:
            printer_id = self.selector.select_printer(file_path, print_mode)
            LOGGER.info(
                "Auto-selected printer",
                printer=printer_id,
                job=job_id,
                mode=print_mode.value
            )
        else:
            # Validate manual selection
            if not self.selector.validate_fit(file_path, printer_id):
                raise ValueError(f"Model too large for {printer_id}")

        # Get driver and submit job
        driver = self.registry.get_driver(printer_id)
        await driver.connect()

        try:
            # Upload file
            LOGGER.info("Uploading file", job=job_id, printer=printer_id)
            remote_filename = await driver.upload_file(file_path)

            # Create job spec
            spec = PrintJobSpec(
                job_id=job_id,
                file_path=Path(remote_filename),
                print_mode=print_mode,
                nozzle_temp=nozzle_temp,
                bed_temp=bed_temp
            )

            # Start print
            LOGGER.info("Starting print", job=job_id, printer=printer_id)
            await driver.start_print(spec)

            return {
                "printer_id": printer_id,
                "job_id": job_id,
                "status": "printing",
                "selection_method": "auto" if printer_id else "manual"
            }

        finally:
            await driver.disconnect()

    async def pause_job(self, printer_id: str) -> None:
        """Pause print on specific printer"""
        driver = self.registry.get_driver(printer_id)
        await driver.connect()
        try:
            await driver.pause_print()
        finally:
            await driver.disconnect()

    async def resume_job(self, printer_id: str) -> None:
        """Resume print on specific printer"""
        driver = self.registry.get_driver(printer_id)
        await driver.connect()
        try:
            await driver.resume_print()
        finally:
            await driver.disconnect()

    async def cancel_job(self, printer_id: str) -> None:
        """Cancel print on specific printer"""
        driver = self.registry.get_driver(printer_id)
        await driver.connect()
        try:
            await driver.cancel_print()
        finally:
            await driver.disconnect()
```

### 6. Gateway Fabrication Routes

**File: `services/gateway/src/gateway/routes/fabrication.py`** (New)

```python
"""KITTY Gateway - Fabrication Service Proxy"""
from __future__ import annotations

import os
from typing import Any, Optional

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
import httpx


router = APIRouter(prefix="/api/fabrication", tags=["fabrication"])

FABRICATION_BASE = os.getenv("FABRICATION_BASE", "http://127.0.0.1:8300")


class QueuePrintRequest(BaseModel):
    artifact_path: str
    print_mode: str = "3d_print"
    printer_id: Optional[str] = None
    nozzle_temp: Optional[int] = None
    bed_temp: Optional[int] = None


@router.post("/queue")
async def queue_print(request: QueuePrintRequest) -> dict[str, Any]:
    """
    Queue print job with automatic printer selection.

    Print mode options:
    - "3d_print" (default)
    - "cnc"
    - "laser"

    If printer_id is not specified, KITTY will automatically select:
    - Small-medium models (≤200mm) → bamboo_h2d
    - Large models (>200mm) → elegoo_giga
    - CNC/laser → snapmaker_artisan
    """
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(
                f"{FABRICATION_BASE}/api/fabrication/queue",
                json=request.dict()
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail=f"Fabrication service error: {e}")


@router.get("/printers")
async def list_printers() -> dict[str, Any]:
    """
    List all available printers with status and capabilities.
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{FABRICATION_BASE}/api/fabrication/printers")
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail=f"Fabrication service error: {e}")


@router.get("/printers/{printer_id}/status")
async def printer_status(printer_id: str) -> dict[str, Any]:
    """Get status of specific printer"""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{FABRICATION_BASE}/api/fabrication/printers/{printer_id}/status"
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail=f"Fabrication service error: {e}")


@router.post("/printers/{printer_id}/pause")
async def pause_print(printer_id: str) -> dict[str, str]:
    """Pause print on specific printer"""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{FABRICATION_BASE}/api/fabrication/printers/{printer_id}/pause"
            )
            response.raise_for_status()
            return {"status": "paused"}
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail=f"Fabrication service error: {e}")


@router.post("/printers/{printer_id}/resume")
async def resume_print(printer_id: str) -> dict[str, str]:
    """Resume print on specific printer"""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{FABRICATION_BASE}/api/fabrication/printers/{printer_id}/resume"
            )
            response.raise_for_status()
            return {"status": "resumed"}
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail=f"Fabrication service error: {e}")


@router.post("/printers/{printer_id}/cancel")
async def cancel_print(printer_id: str) -> dict[str, str]:
    """Cancel print on specific printer"""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{FABRICATION_BASE}/api/fabrication/printers/{printer_id}/cancel"
            )
            response.raise_for_status()
            return {"status": "cancelled"}
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail=f"Fabrication service error: {e}")
```

**Register in Gateway: `services/gateway/src/gateway/app.py`**

```python
from .routes.fabrication import router as fabrication_router
app.include_router(fabrication_router)
```

### 7. Tool Registry Updates

**File: `config/tool_registry.yaml`** (Update)

```yaml
tools:
  # ... existing tools ...

  # ==============================================================================
  # Fabrication Tools (Updated for Multi-Printer Support)
  # ==============================================================================

  fabrication.queue_print:
    server: broker
    description: "Queue 3D print/CNC/laser job with automatic printer selection"
    hazard_class: medium
    requires_confirmation: true
    confirmation_phrase: "Confirm: proceed"
    budget_tier: free
    enabled: true
    note: |
      Automatically selects printer based on model size and mode:
      - Small-medium 3D prints (≤200mm) → Bamboo H2D
      - Large 3D prints (>200mm) → Elegoo Giga
      - CNC/laser → Snapmaker Artisan

      Parameters:
      - artifact_path (required): Path to STL/GCODE file
      - print_mode (optional): "3d_print" (default), "cnc", or "laser"
      - printer_id (optional): Manual printer selection
      - nozzle_temp (optional): Nozzle temperature override
      - bed_temp (optional): Bed temperature override

  fabrication.list_printers:
    server: broker
    description: "List all available printers with status and capabilities"
    hazard_class: none
    requires_confirmation: false
    budget_tier: free
    enabled: true

  fabrication.cancel_print:
    server: broker
    description: "Cancel currently running print job on specified printer"
    hazard_class: low
    requires_confirmation: false
    budget_tier: free
    enabled: true
    note: "Requires printer_id parameter"

  fabrication.pause_print:
    server: broker
    description: "Pause currently running print job on specified printer"
    hazard_class: low
    requires_confirmation: false
    budget_tier: free
    enabled: true
    note: "Requires printer_id parameter"

  fabrication.resume_print:
    server: broker
    description: "Resume paused print job on specified printer"
    hazard_class: low
    requires_confirmation: false
    budget_tier: free
    enabled: true
    note: "Requires printer_id parameter"

categories:
  # ... existing categories ...
  fabrication:
    - fabrication.queue_print
    - fabrication.list_printers
    - fabrication.cancel_print
    - fabrication.pause_print
    - fabrication.resume_print
```

## Implementation Checklist

### Phase 1: Driver Foundation
- [ ] Create `services/fabrication/src/fabrication/drivers/base.py` with abstract interface
- [ ] Implement `services/fabrication/src/fabrication/drivers/bamboo.py`
- [ ] Enhance `services/fabrication/src/fabrication/drivers/klipper.py`
- [ ] Implement `services/fabrication/src/fabrication/drivers/snapmaker.py`
- [ ] Add Python dependencies:
  ```bash
  pip install paho-mqtt trimesh
  ```

### Phase 2: Registry & Selection
- [ ] Create `services/fabrication/src/fabrication/registry.py`
- [ ] Create `config/printers.yaml` configuration file
- [ ] Implement `services/fabrication/src/fabrication/selector.py`
- [ ] Add `.env` variables:
  ```bash
  PRINTER_CONFIG=config/printers.yaml
  FABRICATION_BASE=http://fabrication:8300
  ```

### Phase 3: Job Manager Update
- [ ] Refactor `services/fabrication/src/fabrication/jobs/manager.py` to use new registry
- [ ] Update MQTT handlers to support printer_id parameter
- [ ] Add fabrication service API endpoints (FastAPI)

### Phase 4: Gateway Integration
- [ ] Create `services/gateway/src/gateway/routes/fabrication.py`
- [ ] Register fabrication router in `services/gateway/src/gateway/app.py`
- [ ] Update `config/tool_registry.yaml` with new fabrication tools

### Phase 5: Testing & Validation
- [ ] Test Bamboo H2D connection and file upload
- [ ] Test Elegoo Giga via Moonraker
- [ ] Test Snapmaker SACP protocol
- [ ] Test automatic printer selection logic
- [ ] Validate size-based routing with sample STL files
- [ ] Integration test: Full CAD → Print workflow

### Phase 6: Documentation
- [ ] Update `KITTY_OperationsManual.md` with multi-printer operations
- [ ] Add printer configuration guide to `config/README.md`
- [ ] Document troubleshooting for each printer type

## Environment Variables

Add to `.env`:

```bash
# Fabrication Service
FABRICATION_BASE=http://fabrication:8300
PRINTER_CONFIG=config/printers.yaml

# Printer Credentials (populated per your setup)
BAMBOO_IP=192.168.1.100
BAMBOO_SERIAL=01P45165616
BAMBOO_ACCESS_CODE=YOUR_16_CHAR_CODE

ELEGOO_IP=192.168.1.200
ELEGOO_MOONRAKER_PORT=7125

SNAPMAKER_IP=192.168.1.150
SNAPMAKER_PORT=8888
```

## Usage Examples

### Example 1: Automatic Printer Selection

```python
# Via ReAct agent tool
{
  "tool": "fabrication.queue_print",
  "args": {
    "artifact_path": "/Users/Shared/KITTY/artifacts/cad/bracket.stl",
    "print_mode": "3d_print"
  }
}
# → Auto-selects bamboo_h2d (small model)
```

### Example 2: Manual Printer Selection

```python
{
  "tool": "fabrication.queue_print",
  "args": {
    "artifact_path": "/Users/Shared/KITTY/artifacts/cad/large_enclosure.stl",
    "print_mode": "3d_print",
    "printer_id": "elegoo_giga"
  }
}
# → Forces Elegoo Giga for large print
```

### Example 3: CNC Job

```python
{
  "tool": "fabrication.queue_print",
  "args": {
    "artifact_path": "/Users/Shared/KITTY/artifacts/cam/aluminum_plate.nc",
    "print_mode": "cnc"
  }
}
# → Auto-selects snapmaker_artisan (only CNC-capable printer)
```

### Example 4: Check Printer Status

```python
{
  "tool": "fabrication.list_printers",
  "args": {}
}
# Returns:
# {
#   "bamboo_h2d": {"online": true, "printing": false, ...},
#   "elegoo_giga": {"online": true, "printing": true, "progress": 45},
#   "snapmaker_artisan": {"online": false, ...}
# }
```

## Integration with CAD → Print Workflow

```yaml
User: "Generate a 150mm water bottle holder and print it"

Agent Turn 1:
  type: action
  tool: cad.generate_model
  args:
    prompt: "water bottle holder, 150mm diameter"
    provider: zoo

Observation: {"stl_path": "/Users/Shared/KITTY/artifacts/cad/bottle_holder.stl"}

Safety Check: fabrication.queue_print requires confirmation

Agent Turn 2:
  type: ask_user
  message: "CAD complete. Model is 150mm (small-medium). Ready to print on Bamboo H2D. Say 'Confirm: proceed' to start."

User: "Confirm: proceed"

Agent Turn 3:
  type: action
  tool: fabrication.queue_print
  args:
    artifact_path: "/Users/Shared/KITTY/artifacts/cad/bottle_holder.stl"
    print_mode: "3d_print"
    # No printer_id → auto-selects bamboo_h2d

Observation: {"printer_id": "bamboo_h2d", "job_id": "job_12345", "status": "printing"}

Agent Final:
  type: final
  message: "Printing on Bamboo H2D, ETA 1h 45m"
```

## Size Selection Decision Tree

```
┌─────────────────────────────────────┐
│ Analyze STL bounding box            │
│ Extract max dimension (X, Y, or Z)  │
└──────────────┬──────────────────────┘
               │
               ▼
       ┌───────────────┐
       │ Print Mode?   │
       └───┬───────────┘
           │
    ┌──────┴──────────┬─────────────┐
    │                 │             │
    ▼                 ▼             ▼
┌────────┐      ┌─────────┐   ┌──────────┐
│ CNC    │      │ Laser   │   │ 3D Print │
│        │      │         │   │          │
└────┬───┘      └────┬────┘   └────┬─────┘
     │               │             │
     └───────────────┴─────────────┘
                     │
                     ▼
         ┌────────────────────────┐
         │ Snapmaker Artisan      │  (Only printer with CNC/Laser)
         └────────────────────────┘

                     │
                     ▼ (for 3D Print)
         ┌────────────────────────┐
         │ Max Dimension ≤ 200mm? │
         └───┬────────────────┬───┘
             │                │
          Yes│                │No
             │                │
             ▼                ▼
    ┌─────────────────┐  ┌─────────────────┐
    │ Bamboo H2D      │  │ Elegoo Giga     │
    │ (250x250x250mm) │  │ (800x800x1000mm)│
    └─────────────────┘  └─────────────────┘
```

## Security & Safety Notes

1. **Confirmation Required**: `fabrication.queue_print` is `hazard_class: medium` and requires confirmation phrase
2. **Network Security**: All printers on local WiFi (192.168.1.x). No internet exposure.
3. **Authentication**:
   - Bamboo: Access code (16 chars)
   - Klipper: No auth (local network only)
   - Snapmaker: Optional token
4. **Audit Logging**: All print jobs logged to PostgreSQL `telemetry_events` table
5. **Safety Events**: Camera bookmarks created when fabrication starts (future feature)

## Future Enhancements

1. **Multi-Material Detection**: Analyze STL for multi-material requirements
2. **Printer Health Monitoring**: Track failure rates, maintenance schedules
3. **Queue Management**: Support job queuing when printer busy
4. **Slicing Integration**: Auto-slice STL to G-code with Orca Slicer CLI
5. **Cost Estimation**: Calculate material cost and time for each printer
6. **Print Farm Scaling**: Support multiple instances of same printer type
7. **Computer Vision Integration**: Link to existing CV monitor for failure detection

## Dependencies

Add to `services/fabrication/requirements.txt`:

```txt
paho-mqtt==1.6.1       # Bamboo Labs MQTT
trimesh==4.0.10        # STL bounding box analysis
httpx==0.25.2          # Already in use
pyyaml==6.0.1          # Already in use
```

## Estimated Implementation Time

- **Phase 1 (Drivers)**: 8 hours
- **Phase 2 (Registry/Selection)**: 4 hours
- **Phase 3 (Job Manager)**: 3 hours
- **Phase 4 (Gateway)**: 2 hours
- **Phase 5 (Testing)**: 6 hours
- **Phase 6 (Documentation)**: 2 hours

**Total**: ~25 hours of development time

## Success Criteria

1. ✅ All three printers accessible from KITTY
2. ✅ Automatic printer selection based on model size
3. ✅ Manual printer override capability
4. ✅ Real-time printer status monitoring
5. ✅ Full CAD → Print workflow without human intervention (after confirmation)
6. ✅ Safety confirmation for all print jobs
7. ✅ Comprehensive error handling and logging
