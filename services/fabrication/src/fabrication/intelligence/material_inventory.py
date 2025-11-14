"""Material inventory management for Phase 4 Fabrication Intelligence.

Provides material catalog queries, spool tracking, usage calculation, and
low-inventory alerts for autonomous procurement.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy.orm import Session

from common.db.models import InventoryItem, InventoryStatus, Material
from common.logging import get_logger

LOGGER = get_logger(__name__)


@dataclass
class InventoryFilters:
    """Filters for inventory queries."""

    material_type: Optional[str] = None  # pla, petg, abs, tpu, etc.
    status: Optional[InventoryStatus] = None  # available, in_use, depleted
    min_weight_grams: Optional[float] = None
    max_weight_grams: Optional[float] = None
    location: Optional[str] = None


@dataclass
class UsageEstimate:
    """Material usage estimation result."""

    estimated_grams: float
    infill_percent: int
    supports_enabled: bool
    stl_volume_cm3: float
    adjusted_volume_cm3: float
    material_density: float
    waste_factor: float = 1.05  # 5% waste


@dataclass
class CostEstimate:
    """Print cost estimation result."""

    material_cost_usd: Decimal
    grams_used: float
    cost_per_kg: Decimal
    material_id: str


class MaterialInventory:
    """Material inventory management system.

    Provides methods for:
    - Material catalog queries
    - Spool inventory tracking
    - Material usage calculation
    - Cost estimation
    - Low-inventory alerts
    """

    def __init__(
        self,
        db: Session,
        low_inventory_threshold_grams: float = 100.0,
        waste_factor: float = 1.05,
    ):
        """Initialize material inventory manager.

        Args:
            db: Database session
            low_inventory_threshold_grams: Threshold for low inventory alerts (default: 100g)
            waste_factor: Waste multiplier for usage calculation (default: 1.05 = 5% waste)
        """
        self.db = db
        self.low_inventory_threshold = low_inventory_threshold_grams
        self.waste_factor = waste_factor

    # ========================================================================
    # Material Catalog Operations
    # ========================================================================

    def get_material(self, material_id: str) -> Optional[Material]:
        """Retrieve material by ID.

        Args:
            material_id: Material identifier (e.g., "pla_black_esun")

        Returns:
            Material object or None if not found
        """
        material = self.db.query(Material).filter_by(id=material_id).first()

        if material:
            LOGGER.debug(
                "Retrieved material",
                material_id=material_id,
                type=material.material_type,
                manufacturer=material.manufacturer,
            )
        else:
            LOGGER.warning("Material not found", material_id=material_id)

        return material

    def list_materials(
        self, material_type: Optional[str] = None, manufacturer: Optional[str] = None
    ) -> List[Material]:
        """List materials from catalog with optional filters.

        Args:
            material_type: Filter by material type (e.g., "pla", "petg")
            manufacturer: Filter by manufacturer (e.g., "eSUN", "Prusa")

        Returns:
            List of matching materials
        """
        query = self.db.query(Material)

        if material_type:
            query = query.filter(Material.material_type == material_type.lower())

        if manufacturer:
            query = query.filter(Material.manufacturer.ilike(f"%{manufacturer}%"))

        materials = query.order_by(Material.material_type, Material.color).all()

        LOGGER.debug(
            "Listed materials",
            count=len(materials),
            material_type=material_type,
            manufacturer=manufacturer,
        )

        return materials

    # ========================================================================
    # Inventory Operations
    # ========================================================================

    def get_inventory(self, spool_id: str) -> Optional[InventoryItem]:
        """Retrieve inventory item (spool) by ID.

        Args:
            spool_id: Spool identifier

        Returns:
            InventoryItem object or None if not found
        """
        item = self.db.query(InventoryItem).filter_by(id=spool_id).first()

        if item:
            LOGGER.debug(
                "Retrieved inventory item",
                spool_id=spool_id,
                material_id=item.material_id,
                current_weight=float(item.current_weight_grams),
                status=item.status.value,
            )
        else:
            LOGGER.warning("Inventory item not found", spool_id=spool_id)

        return item

    def list_inventory(self, filters: Optional[InventoryFilters] = None) -> List[InventoryItem]:
        """List inventory items with optional filters.

        Args:
            filters: Optional filters for inventory query

        Returns:
            List of matching inventory items
        """
        query = self.db.query(InventoryItem)

        if filters:
            if filters.material_type:
                query = query.join(Material).filter(
                    Material.material_type == filters.material_type.lower()
                )

            if filters.status:
                query = query.filter(InventoryItem.status == filters.status)

            if filters.min_weight_grams is not None:
                query = query.filter(InventoryItem.current_weight_grams >= filters.min_weight_grams)

            if filters.max_weight_grams is not None:
                query = query.filter(InventoryItem.current_weight_grams <= filters.max_weight_grams)

            if filters.location:
                query = query.filter(InventoryItem.location.ilike(f"%{filters.location}%"))

        items = query.order_by(InventoryItem.current_weight_grams.asc()).all()

        LOGGER.debug("Listed inventory items", count=len(items), filters=filters)

        return items

    def add_inventory(
        self,
        spool_id: str,
        material_id: str,
        initial_weight_grams: float,
        purchase_date: datetime,
        location: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> InventoryItem:
        """Add new spool to inventory.

        Args:
            spool_id: Unique spool identifier
            material_id: Material catalog ID
            initial_weight_grams: Initial spool weight in grams
            purchase_date: Date spool was purchased
            location: Optional storage location
            notes: Optional notes

        Returns:
            Created InventoryItem

        Raises:
            ValueError: If spool_id already exists or material_id not found
        """
        # Check for duplicate spool_id
        existing = self.db.query(InventoryItem).filter_by(id=spool_id).first()
        if existing:
            raise ValueError(f"Spool ID already exists: {spool_id}")

        # Verify material exists
        material = self.get_material(material_id)
        if not material:
            raise ValueError(f"Material not found: {material_id}")

        # Create inventory item
        item = InventoryItem(
            id=spool_id,
            material_id=material_id,
            location=location,
            purchase_date=purchase_date,
            initial_weight_grams=Decimal(str(initial_weight_grams)),
            current_weight_grams=Decimal(str(initial_weight_grams)),
            status=InventoryStatus.available,
            notes=notes,
            created_at=datetime.utcnow(),
        )

        self.db.add(item)
        self.db.commit()

        LOGGER.info(
            "Added inventory item",
            spool_id=spool_id,
            material_id=material_id,
            initial_weight=initial_weight_grams,
            location=location,
        )

        return item

    def deduct_usage(self, spool_id: str, grams_used: float) -> InventoryItem:
        """Deduct material usage from spool inventory.

        Args:
            spool_id: Spool identifier
            grams_used: Amount of material used in grams

        Returns:
            Updated InventoryItem

        Raises:
            ValueError: If spool not found or insufficient material
        """
        item = self.get_inventory(spool_id)
        if not item:
            raise ValueError(f"Spool not found: {spool_id}")

        # Check sufficient material
        if float(item.current_weight_grams) < grams_used:
            raise ValueError(
                f"Insufficient material in spool {spool_id}: "
                f"{float(item.current_weight_grams)}g available, {grams_used}g required"
            )

        # Deduct usage
        old_weight = float(item.current_weight_grams)
        new_weight = old_weight - grams_used
        item.current_weight_grams = Decimal(str(new_weight))
        item.updated_at = datetime.utcnow()

        # Update status if depleted
        if new_weight <= 0:
            item.status = InventoryStatus.depleted
            LOGGER.warning("Spool depleted", spool_id=spool_id, material_id=item.material_id)
        elif new_weight < self.low_inventory_threshold:
            LOGGER.warning(
                "Low inventory alert",
                spool_id=spool_id,
                material_id=item.material_id,
                current_weight=new_weight,
                threshold=self.low_inventory_threshold,
            )

        self.db.commit()

        LOGGER.info(
            "Deducted material usage",
            spool_id=spool_id,
            grams_used=grams_used,
            old_weight=old_weight,
            new_weight=new_weight,
            status=item.status.value,
        )

        return item

    def check_low_inventory(self) -> List[InventoryItem]:
        """Find inventory items below low threshold.

        Returns:
            List of inventory items with weight below threshold
        """
        items = (
            self.db.query(InventoryItem)
            .filter(
                InventoryItem.current_weight_grams < self.low_inventory_threshold,
                InventoryItem.status != InventoryStatus.depleted,
            )
            .order_by(InventoryItem.current_weight_grams.asc())
            .all()
        )

        if items:
            LOGGER.warning(
                "Low inventory detected",
                count=len(items),
                threshold=self.low_inventory_threshold,
                items=[
                    {
                        "spool_id": item.id,
                        "material_id": item.material_id,
                        "current_weight": float(item.current_weight_grams),
                    }
                    for item in items
                ],
            )
        else:
            LOGGER.debug("No low inventory items", threshold=self.low_inventory_threshold)

        return items

    # ========================================================================
    # Usage Calculation
    # ========================================================================

    def calculate_usage(
        self,
        stl_volume_cm3: float,
        infill_percent: int,
        material_id: str,
        supports_enabled: bool = False,
    ) -> UsageEstimate:
        """Calculate material usage from STL volume and print settings.

        Formula:
        1. Adjust volume for infill percentage
        2. Add 15% if supports enabled
        3. Convert to weight using material density
        4. Add waste factor (default 5%)

        Args:
            stl_volume_cm3: STL model volume in cubic centimeters
            infill_percent: Infill percentage (0-100)
            material_id: Material catalog ID
            supports_enabled: Whether supports are enabled

        Returns:
            UsageEstimate with calculation breakdown

        Raises:
            ValueError: If material not found or invalid parameters
        """
        # Validate inputs
        if stl_volume_cm3 <= 0:
            raise ValueError(f"Invalid STL volume: {stl_volume_cm3}")
        if not 0 <= infill_percent <= 100:
            raise ValueError(f"Invalid infill percentage: {infill_percent}")

        # Get material
        material = self.get_material(material_id)
        if not material:
            raise ValueError(f"Material not found: {material_id}")

        # Calculate adjusted volume
        # Infill adjustment (e.g., 20% infill uses 20% of volume)
        adjusted_volume = stl_volume_cm3 * (infill_percent / 100.0)

        # Add supports estimate (15% of model volume)
        if supports_enabled:
            adjusted_volume *= 1.15

        # Convert to weight using material density
        estimated_grams_before_waste = adjusted_volume * float(material.density_g_cm3)

        # Add waste factor (purge, ooze, failed first layer retry)
        estimated_grams = estimated_grams_before_waste * self.waste_factor

        estimate = UsageEstimate(
            estimated_grams=round(estimated_grams, 2),
            infill_percent=infill_percent,
            supports_enabled=supports_enabled,
            stl_volume_cm3=stl_volume_cm3,
            adjusted_volume_cm3=round(adjusted_volume, 2),
            material_density=float(material.density_g_cm3),
            waste_factor=self.waste_factor,
        )

        LOGGER.debug(
            "Calculated material usage",
            material_id=material_id,
            stl_volume=stl_volume_cm3,
            infill=infill_percent,
            supports=supports_enabled,
            estimated_grams=estimate.estimated_grams,
        )

        return estimate

    # ========================================================================
    # Cost Estimation
    # ========================================================================

    def estimate_print_cost(self, material_id: str, grams_used: float) -> CostEstimate:
        """Estimate print cost based on material usage.

        Args:
            material_id: Material catalog ID
            grams_used: Amount of material in grams

        Returns:
            CostEstimate with cost breakdown

        Raises:
            ValueError: If material not found or invalid grams
        """
        if grams_used <= 0:
            raise ValueError(f"Invalid grams_used: {grams_used}")

        # Get material
        material = self.get_material(material_id)
        if not material:
            raise ValueError(f"Material not found: {material_id}")

        # Calculate cost: (grams / 1000) * cost_per_kg
        kilograms = grams_used / 1000.0
        material_cost = Decimal(str(kilograms)) * material.cost_per_kg_usd

        estimate = CostEstimate(
            material_cost_usd=material_cost.quantize(Decimal("0.01")),
            grams_used=grams_used,
            cost_per_kg=material.cost_per_kg_usd,
            material_id=material_id,
        )

        LOGGER.debug(
            "Estimated print cost",
            material_id=material_id,
            grams_used=grams_used,
            cost_per_kg=float(material.cost_per_kg_usd),
            material_cost=float(estimate.material_cost_usd),
        )

        return estimate

    def estimate_print_cost_from_stl(
        self,
        stl_volume_cm3: float,
        infill_percent: int,
        material_id: str,
        supports_enabled: bool = False,
    ) -> CostEstimate:
        """Estimate print cost directly from STL volume.

        Convenience method that combines usage calculation and cost estimation.

        Args:
            stl_volume_cm3: STL model volume in cubic centimeters
            infill_percent: Infill percentage (0-100)
            material_id: Material catalog ID
            supports_enabled: Whether supports are enabled

        Returns:
            CostEstimate with cost breakdown
        """
        # Calculate usage
        usage = self.calculate_usage(stl_volume_cm3, infill_percent, material_id, supports_enabled)

        # Estimate cost
        cost = self.estimate_print_cost(material_id, usage.estimated_grams)

        return cost
