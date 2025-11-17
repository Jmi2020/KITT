"""
Discovery service data models (Pydantic API models).

SQLAlchemy ORM models are imported from common.db.models for consistency.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

# Import ORM models from shared common package
try:
    from common.db.models import DiscoveredDevice as DeviceRecord
    from common.db.models import DiscoveryScan as ScanRecord
except ImportError:
    # Development fallback - service can run standalone
    from sqlalchemy import JSON, Boolean, Column, DateTime, Float, Integer, String, Text
    from sqlalchemy.dialects.postgresql import UUID as PGUUID
    from sqlalchemy.ext.declarative import declarative_base
    from uuid import uuid4

    Base = declarative_base()

    class DeviceRecord(Base):
        """Database model for discovered devices (fallback)."""
        __tablename__ = "discovered_devices"
        id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
        discovered_at = Column(DateTime, default=datetime.utcnow, nullable=False)
        last_seen = Column(DateTime, default=datetime.utcnow, nullable=False)
        discovery_method = Column(String, nullable=False)
        ip_address = Column(String, nullable=False)
        mac_address = Column(String)
        hostname = Column(String)
        device_type = Column(String, nullable=False)
        manufacturer = Column(String)
        model = Column(String)
        serial_number = Column(String)
        firmware_version = Column(String)
        services = Column(JSON, default=list)
        capabilities = Column(JSON, default=dict)
        approved = Column(Boolean, default=False)
        approved_at = Column(DateTime)
        approved_by = Column(String)
        notes = Column(Text)
        is_online = Column(Boolean, default=True)
        confidence_score = Column(Float, default=0.5)

    class ScanRecord(Base):
        """Database model for scan history (fallback)."""
        __tablename__ = "discovery_scans"
        id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
        started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
        completed_at = Column(DateTime)
        status = Column(String, default="running")
        methods = Column(JSON, default=list)
        devices_found = Column(Integer, default=0)
        errors = Column(JSON, default=list)
        triggered_by = Column(String)


# ==============================================================================
# Pydantic API Models
# ==============================================================================

class ServiceInfoModel(BaseModel):
    """Service information."""
    protocol: str
    port: int
    name: str
    version: Optional[str] = None


class DeviceResponse(BaseModel):
    """Device information response."""
    id: UUID
    discovered_at: datetime
    last_seen: datetime
    discovery_method: str

    ip_address: str
    mac_address: Optional[str] = None
    hostname: Optional[str] = None

    device_type: str
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    firmware_version: Optional[str] = None

    services: List[Dict[str, Any]] = Field(default_factory=list)
    capabilities: Dict[str, Any] = Field(default_factory=dict)

    approved: bool = False
    approved_at: Optional[datetime] = None
    approved_by: Optional[str] = None
    notes: Optional[str] = None

    is_online: bool = True
    confidence_score: float = 0.5

    class Config:
        from_attributes = True  # Pydantic v2 (was orm_mode in v1)


class DeviceListResponse(BaseModel):
    """List of devices response."""
    devices: List[DeviceResponse]
    total: int
    filters_applied: Dict[str, Any] = Field(default_factory=dict)


class ScanRequest(BaseModel):
    """Scan request parameters."""
    methods: Optional[List[str]] = None  # mdns, ssdp, bamboo_udp, etc.
    timeout_seconds: int = 30


class ScanStatusResponse(BaseModel):
    """Scan status response."""
    scan_id: UUID
    status: str  # running, completed, failed
    started_at: datetime
    completed_at: Optional[datetime] = None
    methods: List[str] = Field(default_factory=list)
    devices_found: int = 0
    errors: List[str] = Field(default_factory=list)


class ApproveDeviceRequest(BaseModel):
    """Device approval request."""
    notes: Optional[str] = None


class ApproveDeviceResponse(BaseModel):
    """Device approval response."""
    id: UUID
    approved: bool
    approved_at: datetime
    approved_by: str


class RejectDeviceRequest(BaseModel):
    """Device rejection request."""
    notes: Optional[str] = None


class RejectDeviceResponse(BaseModel):
    """Device rejection response."""
    id: UUID
    approved: bool
    notes: Optional[str] = None
