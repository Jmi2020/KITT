"""Pydantic schemas for G-code slicing."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class SupportType(str, Enum):
    """Support structure type for overhangs."""

    NONE = "none"
    NORMAL = "normal"
    TREE = "tree"


class QualityPreset(str, Enum):
    """Print quality presets."""

    DRAFT = "draft"  # 0.3mm layers, fast
    NORMAL = "normal"  # 0.2mm layers, balanced
    FINE = "fine"  # 0.12mm layers, high quality


class SlicingStatus(str, Enum):
    """Status of a slicing job."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class SlicingConfig(BaseModel):
    """Configuration for a slicing job."""

    printer_id: str = Field(
        ...,
        description="Target printer ID (elegoo_giga, bambu_h2d, snapmaker_artisan)",
        examples=["elegoo_giga"],
    )
    material_id: str = Field(
        default="pla_generic",
        description="Material profile ID",
        examples=["pla_generic", "petg_generic"],
    )
    quality: QualityPreset = Field(
        default=QualityPreset.NORMAL,
        description="Print quality preset",
    )
    support_type: SupportType = Field(
        default=SupportType.TREE,
        description="Support structure type",
    )
    infill_percent: int = Field(
        default=20,
        description="Infill percentage (0-100)",
        ge=0,
        le=100,
    )
    # Optional overrides
    layer_height_mm: Optional[float] = Field(
        default=None,
        description="Override layer height (mm)",
        ge=0.05,
        le=0.6,
    )
    nozzle_temp_c: Optional[int] = Field(
        default=None,
        description="Override nozzle temperature (C)",
        ge=150,
        le=350,
    )
    bed_temp_c: Optional[int] = Field(
        default=None,
        description="Override bed temperature (C)",
        ge=0,
        le=120,
    )


class SliceRequest(BaseModel):
    """Request to start a slicing job."""

    input_path: str = Field(
        ...,
        description="Path to input 3MF or STL file",
        examples=["/app/artifacts/3mf/model_segmented/combined.3mf"],
    )
    config: SlicingConfig = Field(
        ...,
        description="Slicing configuration",
    )
    upload_to_printer: bool = Field(
        default=False,
        description="Automatically upload G-code to printer after slicing",
    )


class SlicingJobStatus(BaseModel):
    """Status of a slicing job."""

    job_id: str
    status: SlicingStatus
    progress: float = Field(
        default=0.0,
        description="Progress percentage (0.0 to 1.0)",
        ge=0.0,
        le=1.0,
    )
    input_path: str
    config: SlicingConfig
    gcode_path: Optional[str] = Field(
        default=None,
        description="Path to generated G-code (when completed)",
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message (when failed)",
    )
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    # Estimates (populated after slicing)
    estimated_print_time_seconds: Optional[int] = None
    estimated_filament_grams: Optional[float] = None
    layer_count: Optional[int] = None


class SliceResponse(BaseModel):
    """Response from starting a slicing job."""

    job_id: str
    status: SlicingStatus
    status_url: str = Field(
        ...,
        description="URL to poll for job status",
    )


class PrinterProfile(BaseModel):
    """Printer profile information."""

    id: str
    name: str
    build_volume: tuple[float, float, float] = Field(
        ...,
        description="Build volume (X, Y, Z) in mm",
    )
    nozzle_diameter: float = 0.4
    max_bed_temp: int = 110
    max_nozzle_temp: int = 300
    heated_bed: bool = True
    supported_materials: list[str] = Field(default_factory=list)
    curaengine_settings: dict = Field(
        default_factory=dict,
        description="CuraEngine-specific settings (machine_width, machine_depth, etc.)",
    )


class MaterialProfile(BaseModel):
    """Material/filament profile information."""

    id: str
    name: str
    type: str  # PLA, PETG, ABS, TPU, etc.
    default_nozzle_temp: int
    default_bed_temp: int
    nozzle_temp_range: tuple[int, int]
    bed_temp_range: tuple[int, int]
    cooling_fan_speed: int = 100
    compatible_printers: list[str] = Field(default_factory=list)
    curaengine_settings: dict = Field(
        default_factory=dict,
        description="CuraEngine-specific settings (material_print_temperature, etc.)",
    )


class QualityProfile(BaseModel):
    """Print quality profile information."""

    id: str
    name: str
    layer_height: float
    first_layer_height: float
    perimeters: int = 3
    top_solid_layers: int = 5
    bottom_solid_layers: int = 4
    fill_density: int = 20
    fill_pattern: str = "gyroid"
    print_speed: int = 80
    curaengine_settings: dict = Field(
        default_factory=dict,
        description="CuraEngine-specific settings (layer_height in microns, speed_print, etc.)",
    )


class ProfilesResponse(BaseModel):
    """Response listing available profiles."""

    printers: list[PrinterProfile] = Field(default_factory=list)
    materials: list[MaterialProfile] = Field(default_factory=list)
    qualities: list[QualityProfile] = Field(default_factory=list)
