"""
Device registry storage layer.

Handles storing and querying discovered devices in PostgreSQL.
"""
import logging
from datetime import datetime
from typing import List, Optional
from uuid import UUID, uuid4

from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from ..models import DeviceRecord, ScanRecord
from ..scanners.base import DiscoveredDevice

logger = logging.getLogger(__name__)


class DeviceStore:
    """
    Device registry storage layer.

    Manages discovered devices in PostgreSQL with deduplication and updates.
    """

    def __init__(self, database_url: str):
        """
        Initialize device store.

        Args:
            database_url: PostgreSQL connection URL (async)
        """
        self.database_url = database_url
        self.engine = create_async_engine(database_url, echo=False)
        self.async_session_maker = sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )

    async def store_device(
        self, device: DiscoveredDevice, scan_id: Optional[UUID] = None
    ) -> DeviceRecord:
        """
        Store or update a discovered device.

        Deduplicates by IP address or serial number.

        Args:
            device: Discovered device data
            scan_id: Optional scan ID that found this device

        Returns:
            DeviceRecord from database
        """
        async with self.async_session_maker() as session:
            # Check if device already exists (by IP or serial)
            existing = await self._find_existing_device(session, device)

            if existing:
                # Update existing device
                existing.last_seen = datetime.utcnow()
                existing.is_online = True

                # Update fields if changed
                if device.hostname:
                    existing.hostname = device.hostname
                if device.mac_address:
                    existing.mac_address = device.mac_address
                if device.firmware_version:
                    existing.firmware_version = device.firmware_version

                # Update services and capabilities
                if device.services:
                    existing.services = [
                        {
                            "protocol": s.protocol,
                            "port": s.port,
                            "name": s.name,
                            "version": s.version
                        }
                        for s in device.services
                    ]

                if device.capabilities:
                    existing.capabilities.update(device.capabilities)

                # Increase confidence if rediscovered via same method
                if existing.discovery_method == device.discovery_method.value:
                    current_score = float(existing.confidence_score or 0)
                    existing.confidence_score = min(1.0, current_score + 0.05)

                await session.commit()
                await session.refresh(existing)
                return existing

            else:
                # Create new device record
                record = DeviceRecord(
                    id=str(uuid4()),
                    discovered_at=device.discovered_at,
                    last_seen=device.discovered_at,
                    discovery_method=device.discovery_method.value,
                    ip_address=device.ip_address,
                    mac_address=device.mac_address,
                    hostname=device.hostname,
                    device_type=device.device_type.value,
                    manufacturer=device.manufacturer,
                    model=device.model,
                    serial_number=device.serial_number,
                    firmware_version=device.firmware_version,
                    services=[
                        {
                            "protocol": s.protocol,
                            "port": s.port,
                            "name": s.name,
                            "version": s.version
                        }
                        for s in device.services
                    ] if device.services else [],
                    capabilities=device.capabilities or {},
                    is_online=True,
                    confidence_score=device.confidence_score
                )

                session.add(record)
                await session.commit()
                await session.refresh(record)

                logger.info(
                    f"Stored new device: {record.device_type} "
                    f"at {record.ip_address} (confidence={record.confidence_score:.2f})"
                )

                return record

    async def _find_existing_device(
        self, session: AsyncSession, device: DiscoveredDevice
    ) -> Optional[DeviceRecord]:
        """
        Find existing device by IP address or serial number.

        Args:
            session: Database session
            device: Discovered device to match

        Returns:
            Existing DeviceRecord or None
        """
        # Build search conditions
        conditions = [DeviceRecord.ip_address == device.ip_address]

        if device.serial_number:
            conditions.append(DeviceRecord.serial_number == device.serial_number)

        # Query with OR conditions
        stmt = select(DeviceRecord).where(or_(*conditions))
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_device(self, device_id: UUID) -> Optional[DeviceRecord]:
        """
        Get device by ID.

        Args:
            device_id: Device UUID

        Returns:
            DeviceRecord or None
        """
        async with self.async_session_maker() as session:
            stmt = select(DeviceRecord).where(DeviceRecord.id == device_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def list_devices(
        self,
        device_type: Optional[str] = None,
        approved: Optional[bool] = None,
        is_online: Optional[bool] = None,
        manufacturer: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> tuple[List[DeviceRecord], int]:
        """
        List devices with optional filters.

        Args:
            device_type: Filter by device type
            approved: Filter by approval status
            is_online: Filter by online status
            manufacturer: Filter by manufacturer
            limit: Max results
            offset: Results offset

        Returns:
            Tuple of (devices, total_count)
        """
        async with self.async_session_maker() as session:
            # Build filters
            filters = []
            if device_type:
                filters.append(DeviceRecord.device_type == device_type)
            if approved is not None:
                filters.append(DeviceRecord.approved == approved)
            if is_online is not None:
                filters.append(DeviceRecord.is_online == is_online)
            if manufacturer:
                filters.append(
                    func.lower(DeviceRecord.manufacturer).contains(manufacturer.lower())
                )

            # Query devices
            stmt = (
                select(DeviceRecord)
                .where(and_(*filters) if filters else True)
                .order_by(desc(DeviceRecord.last_seen))
                .limit(limit)
                .offset(offset)
            )
            result = await session.execute(stmt)
            devices = result.scalars().all()

            # Count total
            count_stmt = (
                select(func.count(DeviceRecord.id))
                .where(and_(*filters) if filters else True)
            )
            count_result = await session.execute(count_stmt)
            total = count_result.scalar()

            return list(devices), total

    async def search_devices(
        self, query: str, limit: int = 50
    ) -> List[DeviceRecord]:
        """
        Search devices by hostname, model, manufacturer, or IP.

        Args:
            query: Search query
            limit: Max results

        Returns:
            List of matching devices
        """
        async with self.async_session_maker() as session:
            query_lower = query.lower()

            # Search across multiple fields
            stmt = (
                select(DeviceRecord)
                .where(
                    or_(
                        func.lower(DeviceRecord.hostname).contains(query_lower),
                        func.lower(DeviceRecord.model).contains(query_lower),
                        func.lower(DeviceRecord.manufacturer).contains(query_lower),
                        DeviceRecord.ip_address.contains(query),
                        func.lower(DeviceRecord.serial_number).contains(query_lower),
                    )
                )
                .order_by(desc(DeviceRecord.confidence_score))
                .limit(limit)
            )

            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def approve_device(
        self, device_id: UUID, approved_by: str, notes: Optional[str] = None
    ) -> Optional[DeviceRecord]:
        """
        Approve a device for integration.

        Args:
            device_id: Device UUID
            approved_by: User approving the device
            notes: Optional approval notes

        Returns:
            Updated DeviceRecord or None
        """
        async with self.async_session_maker() as session:
            stmt = select(DeviceRecord).where(DeviceRecord.id == device_id)
            result = await session.execute(stmt)
            device = result.scalar_one_or_none()

            if not device:
                return None

            device.approved = True
            device.approved_at = datetime.utcnow()
            device.approved_by = approved_by
            if notes:
                device.notes = notes

            await session.commit()
            await session.refresh(device)

            logger.info(f"Device approved: {device.ip_address} by {approved_by}")

            return device

    async def reject_device(
        self, device_id: UUID, rejected_by: str, notes: Optional[str] = None
    ) -> Optional[DeviceRecord]:
        """
        Reject/unapprove a device.

        Args:
            device_id: Device UUID
            rejected_by: User rejecting the device
            notes: Optional rejection notes

        Returns:
            Updated DeviceRecord or None
        """
        async with self.async_session_maker() as session:
            stmt = select(DeviceRecord).where(DeviceRecord.id == device_id)
            result = await session.execute(stmt)
            device = result.scalar_one_or_none()

            if not device:
                return None

            device.approved = False
            device.approved_at = None
            device.approved_by = None
            if notes:
                device.notes = notes

            await session.commit()
            await session.refresh(device)

            logger.info(f"Device rejected: {device.ip_address} by {rejected_by}")

            return device

    async def delete_device(self, device_id: UUID) -> bool:
        """
        Delete a device from registry.

        Args:
            device_id: Device UUID

        Returns:
            True if deleted, False if not found
        """
        async with self.async_session_maker() as session:
            stmt = select(DeviceRecord).where(DeviceRecord.id == device_id)
            result = await session.execute(stmt)
            device = result.scalar_one_or_none()

            if not device:
                return False

            await session.delete(device)
            await session.commit()

            logger.info(f"Device deleted: {device.ip_address}")

            return True

    async def mark_offline(self, device_id: UUID) -> None:
        """
        Mark a device as offline.

        Args:
            device_id: Device UUID
        """
        async with self.async_session_maker() as session:
            stmt = select(DeviceRecord).where(DeviceRecord.id == device_id)
            result = await session.execute(stmt)
            device = result.scalar_one_or_none()

            if device:
                device.is_online = False
                await session.commit()

    async def create_scan_record(
        self, methods: List[str], triggered_by: str = "scheduler"
    ) -> ScanRecord:
        """
        Create a new scan record.

        Args:
            methods: List of discovery methods used
            triggered_by: Who/what triggered the scan

        Returns:
            Created ScanRecord
        """
        async with self.async_session_maker() as session:
            record = ScanRecord(
                id=str(uuid4()),
                started_at=datetime.utcnow(),
                status="running",
                methods=methods,
                triggered_by=triggered_by
            )

            session.add(record)
            await session.commit()
            await session.refresh(record)

            return record

    async def update_scan_record(
        self,
        scan_id: UUID,
        status: str,
        devices_found: int = 0,
        errors: Optional[List[str]] = None
    ) -> None:
        """
        Update scan record with results.

        Args:
            scan_id: Scan UUID
            status: Scan status (completed, failed)
            devices_found: Number of devices found
            errors: List of error messages
        """
        async with self.async_session_maker() as session:
            stmt = select(ScanRecord).where(ScanRecord.id == scan_id)
            result = await session.execute(stmt)
            record = result.scalar_one_or_none()

            if record:
                record.status = status
                record.completed_at = datetime.utcnow()
                record.devices_found = devices_found
                if errors:
                    record.errors = errors

                await session.commit()

    async def get_scan_record(self, scan_id: UUID) -> Optional[ScanRecord]:
        """
        Get scan record by ID.

        Args:
            scan_id: Scan UUID

        Returns:
            ScanRecord or None
        """
        async with self.async_session_maker() as session:
            stmt = select(ScanRecord).where(ScanRecord.id == scan_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()
