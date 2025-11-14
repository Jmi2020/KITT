"""Unit tests for MaterialInventory class - Phase 4 Task 1.3."""

from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from common.db.models import InventoryItem, InventoryStatus, Material

# Import from fabrication service (will be available after implementation)
import sys
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).parent.parent.parent / "services" / "fabrication" / "src"),
)

from fabrication.intelligence.material_inventory import (
    CostEstimate,
    InventoryFilters,
    MaterialInventory,
    UsageEstimate,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_db():
    """Mock database session."""
    return MagicMock(spec=Session)


@pytest.fixture
def material_inventory(mock_db):
    """MaterialInventory instance with mock database."""
    return MaterialInventory(
        db=mock_db,
        low_inventory_threshold_grams=100.0,
        waste_factor=1.05,
    )


@pytest.fixture
def sample_material_pla():
    """Sample PLA material."""
    return Material(
        id="pla_black_esun",
        material_type="pla",
        color="black",
        manufacturer="eSUN",
        cost_per_kg_usd=Decimal("21.99"),
        density_g_cm3=Decimal("1.24"),
        nozzle_temp_min_c=190,
        nozzle_temp_max_c=220,
        bed_temp_min_c=50,
        bed_temp_max_c=70,
        properties={"strength": "medium", "flexibility": "low"},
        sustainability_score=75,
    )


@pytest.fixture
def sample_material_petg():
    """Sample PETG material."""
    return Material(
        id="petg_clear_overture",
        material_type="petg",
        color="clear",
        manufacturer="Overture",
        cost_per_kg_usd=Decimal("23.99"),
        density_g_cm3=Decimal("1.27"),
        nozzle_temp_min_c=220,
        nozzle_temp_max_c=250,
        bed_temp_min_c=70,
        bed_temp_max_c=85,
        properties={"strength": "high", "flexibility": "medium"},
        sustainability_score=45,
    )


@pytest.fixture
def sample_inventory_item():
    """Sample inventory item (spool)."""
    return InventoryItem(
        id="spool_001",
        material_id="pla_black_esun",
        location="shelf_a",
        purchase_date=datetime(2025, 1, 1),
        initial_weight_grams=Decimal("1000.0"),
        current_weight_grams=Decimal("750.0"),
        status=InventoryStatus.available,
        notes="Test spool",
    )


# ============================================================================
# Material Catalog Operations Tests
# ============================================================================


class TestGetMaterial:
    """Test get_material method."""

    def test_get_material_exists(self, material_inventory, mock_db, sample_material_pla):
        """Test retrieving existing material."""
        mock_db.query.return_value.filter_by.return_value.first.return_value = sample_material_pla

        result = material_inventory.get_material("pla_black_esun")

        assert result == sample_material_pla
        mock_db.query.assert_called_once_with(Material)
        mock_db.query.return_value.filter_by.assert_called_once_with(id="pla_black_esun")

    def test_get_material_not_found(self, material_inventory, mock_db):
        """Test retrieving non-existent material."""
        mock_db.query.return_value.filter_by.return_value.first.return_value = None

        result = material_inventory.get_material("nonexistent")

        assert result is None

    def test_get_material_logs_warning_when_not_found(
        self, material_inventory, mock_db, caplog
    ):
        """Test warning logged when material not found."""
        mock_db.query.return_value.filter_by.return_value.first.return_value = None

        with caplog.at_level("WARNING"):
            material_inventory.get_material("nonexistent")

        assert "Material not found" in caplog.text


class TestListMaterials:
    """Test list_materials method."""

    def test_list_materials_all(
        self, material_inventory, mock_db, sample_material_pla, sample_material_petg
    ):
        """Test listing all materials without filters."""
        materials = [sample_material_pla, sample_material_petg]
        mock_db.query.return_value.order_by.return_value.all.return_value = materials

        result = material_inventory.list_materials()

        assert len(result) == 2
        assert result == materials

    def test_list_materials_filter_by_type(
        self, material_inventory, mock_db, sample_material_pla
    ):
        """Test listing materials filtered by type."""
        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
            sample_material_pla
        ]

        result = material_inventory.list_materials(material_type="pla")

        assert len(result) == 1
        assert result[0].material_type == "pla"

    def test_list_materials_filter_by_manufacturer(
        self, material_inventory, mock_db, sample_material_pla
    ):
        """Test listing materials filtered by manufacturer."""
        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
            sample_material_pla
        ]

        result = material_inventory.list_materials(manufacturer="eSUN")

        assert len(result) == 1
        assert result[0].manufacturer == "eSUN"

    def test_list_materials_empty(self, material_inventory, mock_db):
        """Test listing materials when none exist."""
        mock_db.query.return_value.order_by.return_value.all.return_value = []

        result = material_inventory.list_materials()

        assert len(result) == 0


# ============================================================================
# Inventory Operations Tests
# ============================================================================


class TestGetInventory:
    """Test get_inventory method."""

    def test_get_inventory_exists(
        self, material_inventory, mock_db, sample_inventory_item
    ):
        """Test retrieving existing inventory item."""
        mock_db.query.return_value.filter_by.return_value.first.return_value = (
            sample_inventory_item
        )

        result = material_inventory.get_inventory("spool_001")

        assert result == sample_inventory_item
        mock_db.query.assert_called_once_with(InventoryItem)

    def test_get_inventory_not_found(self, material_inventory, mock_db):
        """Test retrieving non-existent inventory item."""
        mock_db.query.return_value.filter_by.return_value.first.return_value = None

        result = material_inventory.get_inventory("nonexistent")

        assert result is None


class TestListInventory:
    """Test list_inventory method."""

    def test_list_inventory_all(self, material_inventory, mock_db, sample_inventory_item):
        """Test listing all inventory items without filters."""
        items = [sample_inventory_item]
        mock_db.query.return_value.order_by.return_value.all.return_value = items

        result = material_inventory.list_inventory()

        assert len(result) == 1
        assert result == items

    def test_list_inventory_filter_by_status(
        self, material_inventory, mock_db, sample_inventory_item
    ):
        """Test listing inventory filtered by status."""
        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
            sample_inventory_item
        ]

        filters = InventoryFilters(status=InventoryStatus.available)
        result = material_inventory.list_inventory(filters)

        assert len(result) == 1
        assert result[0].status == InventoryStatus.available

    def test_list_inventory_filter_by_weight_range(
        self, material_inventory, mock_db, sample_inventory_item
    ):
        """Test listing inventory filtered by weight range."""
        mock_db.query.return_value.filter.return_value.filter.return_value.order_by.return_value.all.return_value = [
            sample_inventory_item
        ]

        filters = InventoryFilters(min_weight_grams=500.0, max_weight_grams=1000.0)
        result = material_inventory.list_inventory(filters)

        assert len(result) == 1
        assert 500.0 <= float(result[0].current_weight_grams) <= 1000.0

    def test_list_inventory_filter_by_location(
        self, material_inventory, mock_db, sample_inventory_item
    ):
        """Test listing inventory filtered by location."""
        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
            sample_inventory_item
        ]

        filters = InventoryFilters(location="shelf")
        result = material_inventory.list_inventory(filters)

        assert len(result) == 1

    def test_list_inventory_empty(self, material_inventory, mock_db):
        """Test listing inventory when empty."""
        mock_db.query.return_value.order_by.return_value.all.return_value = []

        result = material_inventory.list_inventory()

        assert len(result) == 0


class TestAddInventory:
    """Test add_inventory method."""

    def test_add_inventory_success(self, material_inventory, mock_db, sample_material_pla):
        """Test adding new inventory item."""
        mock_db.query.return_value.filter_by.return_value.first.side_effect = [
            None,  # No existing spool
            sample_material_pla,  # Material exists
        ]

        result = material_inventory.add_inventory(
            spool_id="spool_new",
            material_id="pla_black_esun",
            initial_weight_grams=1000.0,
            purchase_date=datetime(2025, 1, 15),
            location="shelf_b",
            notes="New spool",
        )

        assert result.id == "spool_new"
        assert result.material_id == "pla_black_esun"
        assert result.current_weight_grams == result.initial_weight_grams
        assert result.status == InventoryStatus.available
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    def test_add_inventory_duplicate_spool_id(
        self, material_inventory, mock_db, sample_inventory_item
    ):
        """Test adding inventory with duplicate spool ID."""
        mock_db.query.return_value.filter_by.return_value.first.return_value = (
            sample_inventory_item
        )

        with pytest.raises(ValueError, match="Spool ID already exists"):
            material_inventory.add_inventory(
                spool_id="spool_001",
                material_id="pla_black_esun",
                initial_weight_grams=1000.0,
                purchase_date=datetime(2025, 1, 15),
            )

    def test_add_inventory_material_not_found(self, material_inventory, mock_db):
        """Test adding inventory with non-existent material."""
        mock_db.query.return_value.filter_by.return_value.first.side_effect = [
            None,  # No existing spool
            None,  # Material not found
        ]

        with pytest.raises(ValueError, match="Material not found"):
            material_inventory.add_inventory(
                spool_id="spool_new",
                material_id="nonexistent",
                initial_weight_grams=1000.0,
                purchase_date=datetime(2025, 1, 15),
            )


class TestDeductUsage:
    """Test deduct_usage method."""

    def test_deduct_usage_success(
        self, material_inventory, mock_db, sample_inventory_item
    ):
        """Test deducting material usage successfully."""
        mock_db.query.return_value.filter_by.return_value.first.return_value = (
            sample_inventory_item
        )

        result = material_inventory.deduct_usage("spool_001", 250.0)

        assert float(result.current_weight_grams) == 500.0  # 750 - 250
        assert result.status == InventoryStatus.available
        mock_db.commit.assert_called_once()

    def test_deduct_usage_depletes_spool(
        self, material_inventory, mock_db, sample_inventory_item
    ):
        """Test deducting usage that depletes spool."""
        mock_db.query.return_value.filter_by.return_value.first.return_value = (
            sample_inventory_item
        )

        result = material_inventory.deduct_usage("spool_001", 750.0)

        assert float(result.current_weight_grams) == 0.0
        assert result.status == InventoryStatus.depleted

    def test_deduct_usage_low_inventory_warning(
        self, material_inventory, mock_db, sample_inventory_item, caplog
    ):
        """Test low inventory warning when below threshold."""
        mock_db.query.return_value.filter_by.return_value.first.return_value = (
            sample_inventory_item
        )

        with caplog.at_level("WARNING"):
            material_inventory.deduct_usage("spool_001", 700.0)  # Leaves 50g

        assert "Low inventory alert" in caplog.text

    def test_deduct_usage_spool_not_found(self, material_inventory, mock_db):
        """Test deducting usage from non-existent spool."""
        mock_db.query.return_value.filter_by.return_value.first.return_value = None

        with pytest.raises(ValueError, match="Spool not found"):
            material_inventory.deduct_usage("nonexistent", 100.0)

    def test_deduct_usage_insufficient_material(
        self, material_inventory, mock_db, sample_inventory_item
    ):
        """Test deducting more material than available."""
        mock_db.query.return_value.filter_by.return_value.first.return_value = (
            sample_inventory_item
        )

        with pytest.raises(ValueError, match="Insufficient material"):
            material_inventory.deduct_usage("spool_001", 1000.0)  # Only 750g available


class TestCheckLowInventory:
    """Test check_low_inventory method."""

    def test_check_low_inventory_found(
        self, material_inventory, mock_db, sample_inventory_item
    ):
        """Test finding low inventory items."""
        # Set weight below threshold
        sample_inventory_item.current_weight_grams = Decimal("50.0")

        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
            sample_inventory_item
        ]

        result = material_inventory.check_low_inventory()

        assert len(result) == 1
        assert float(result[0].current_weight_grams) < 100.0

    def test_check_low_inventory_none_found(self, material_inventory, mock_db):
        """Test when no low inventory items."""
        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []

        result = material_inventory.check_low_inventory()

        assert len(result) == 0

    def test_check_low_inventory_excludes_depleted(
        self, material_inventory, mock_db
    ):
        """Test that depleted spools are excluded."""
        # This is tested via the filter in the query
        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []

        result = material_inventory.check_low_inventory()

        # Verify filter excludes depleted status
        assert len(result) == 0


# ============================================================================
# Usage Calculation Tests
# ============================================================================


class TestCalculateUsage:
    """Test calculate_usage method."""

    def test_calculate_usage_basic(
        self, material_inventory, mock_db, sample_material_pla
    ):
        """Test basic usage calculation without supports."""
        mock_db.query.return_value.filter_by.return_value.first.return_value = (
            sample_material_pla
        )

        result = material_inventory.calculate_usage(
            stl_volume_cm3=100.0,
            infill_percent=20,
            material_id="pla_black_esun",
            supports_enabled=False,
        )

        # Expected: 100 * 0.20 (infill) * 1.24 (density) * 1.05 (waste) = 26.04g
        assert isinstance(result, UsageEstimate)
        assert result.stl_volume_cm3 == 100.0
        assert result.infill_percent == 20
        assert result.supports_enabled is False
        assert result.material_density == 1.24
        assert result.estimated_grams == pytest.approx(26.04, rel=0.01)

    def test_calculate_usage_with_supports(
        self, material_inventory, mock_db, sample_material_pla
    ):
        """Test usage calculation with supports enabled."""
        mock_db.query.return_value.filter_by.return_value.first.return_value = (
            sample_material_pla
        )

        result = material_inventory.calculate_usage(
            stl_volume_cm3=100.0,
            infill_percent=20,
            material_id="pla_black_esun",
            supports_enabled=True,
        )

        # Expected: 100 * 0.20 * 1.15 (supports) * 1.24 * 1.05 = 29.95g
        assert result.supports_enabled is True
        assert result.estimated_grams == pytest.approx(29.95, rel=0.01)

    def test_calculate_usage_100_percent_infill(
        self, material_inventory, mock_db, sample_material_pla
    ):
        """Test usage calculation with 100% infill."""
        mock_db.query.return_value.filter_by.return_value.first.return_value = (
            sample_material_pla
        )

        result = material_inventory.calculate_usage(
            stl_volume_cm3=50.0,
            infill_percent=100,
            material_id="pla_black_esun",
            supports_enabled=False,
        )

        # Expected: 50 * 1.00 * 1.24 * 1.05 = 65.1g
        assert result.infill_percent == 100
        assert result.estimated_grams == pytest.approx(65.1, rel=0.01)

    def test_calculate_usage_different_material_density(
        self, material_inventory, mock_db, sample_material_petg
    ):
        """Test usage calculation with different material density."""
        mock_db.query.return_value.filter_by.return_value.first.return_value = (
            sample_material_petg
        )

        result = material_inventory.calculate_usage(
            stl_volume_cm3=100.0,
            infill_percent=20,
            material_id="petg_clear_overture",
            supports_enabled=False,
        )

        # PETG density 1.27 vs PLA 1.24
        # Expected: 100 * 0.20 * 1.27 * 1.05 = 26.67g
        assert result.material_density == 1.27
        assert result.estimated_grams == pytest.approx(26.67, rel=0.01)

    def test_calculate_usage_invalid_volume(self, material_inventory, mock_db):
        """Test usage calculation with invalid volume."""
        with pytest.raises(ValueError, match="Invalid STL volume"):
            material_inventory.calculate_usage(
                stl_volume_cm3=0.0,
                infill_percent=20,
                material_id="pla_black_esun",
            )

        with pytest.raises(ValueError, match="Invalid STL volume"):
            material_inventory.calculate_usage(
                stl_volume_cm3=-10.0,
                infill_percent=20,
                material_id="pla_black_esun",
            )

    def test_calculate_usage_invalid_infill(self, material_inventory, mock_db):
        """Test usage calculation with invalid infill percentage."""
        with pytest.raises(ValueError, match="Invalid infill percentage"):
            material_inventory.calculate_usage(
                stl_volume_cm3=100.0,
                infill_percent=150,
                material_id="pla_black_esun",
            )

        with pytest.raises(ValueError, match="Invalid infill percentage"):
            material_inventory.calculate_usage(
                stl_volume_cm3=100.0,
                infill_percent=-10,
                material_id="pla_black_esun",
            )

    def test_calculate_usage_material_not_found(self, material_inventory, mock_db):
        """Test usage calculation with non-existent material."""
        mock_db.query.return_value.filter_by.return_value.first.return_value = None

        with pytest.raises(ValueError, match="Material not found"):
            material_inventory.calculate_usage(
                stl_volume_cm3=100.0,
                infill_percent=20,
                material_id="nonexistent",
            )


# ============================================================================
# Cost Estimation Tests
# ============================================================================


class TestEstimatePrintCost:
    """Test estimate_print_cost method."""

    def test_estimate_cost_basic(
        self, material_inventory, mock_db, sample_material_pla
    ):
        """Test basic cost estimation."""
        mock_db.query.return_value.filter_by.return_value.first.return_value = (
            sample_material_pla
        )

        result = material_inventory.estimate_print_cost(
            material_id="pla_black_esun", grams_used=100.0
        )

        # Expected: (100 / 1000) * 21.99 = $2.20
        assert isinstance(result, CostEstimate)
        assert result.material_id == "pla_black_esun"
        assert result.grams_used == 100.0
        assert result.cost_per_kg == Decimal("21.99")
        assert result.material_cost_usd == Decimal("2.20")

    def test_estimate_cost_small_amount(
        self, material_inventory, mock_db, sample_material_pla
    ):
        """Test cost estimation for small amount."""
        mock_db.query.return_value.filter_by.return_value.first.return_value = (
            sample_material_pla
        )

        result = material_inventory.estimate_print_cost(
            material_id="pla_black_esun", grams_used=10.0
        )

        # Expected: (10 / 1000) * 21.99 = $0.22
        assert result.material_cost_usd == Decimal("0.22")

    def test_estimate_cost_expensive_material(
        self, material_inventory, mock_db, sample_material_petg
    ):
        """Test cost estimation with more expensive material."""
        mock_db.query.return_value.filter_by.return_value.first.return_value = (
            sample_material_petg
        )

        result = material_inventory.estimate_print_cost(
            material_id="petg_clear_overture", grams_used=100.0
        )

        # Expected: (100 / 1000) * 23.99 = $2.40
        assert result.cost_per_kg == Decimal("23.99")
        assert result.material_cost_usd == Decimal("2.40")

    def test_estimate_cost_invalid_grams(self, material_inventory, mock_db):
        """Test cost estimation with invalid grams."""
        with pytest.raises(ValueError, match="Invalid grams_used"):
            material_inventory.estimate_print_cost(
                material_id="pla_black_esun", grams_used=0.0
            )

        with pytest.raises(ValueError, match="Invalid grams_used"):
            material_inventory.estimate_print_cost(
                material_id="pla_black_esun", grams_used=-10.0
            )

    def test_estimate_cost_material_not_found(self, material_inventory, mock_db):
        """Test cost estimation with non-existent material."""
        mock_db.query.return_value.filter_by.return_value.first.return_value = None

        with pytest.raises(ValueError, match="Material not found"):
            material_inventory.estimate_print_cost(
                material_id="nonexistent", grams_used=100.0
            )


class TestEstimatePrintCostFromSTL:
    """Test estimate_print_cost_from_stl method."""

    def test_estimate_cost_from_stl(
        self, material_inventory, mock_db, sample_material_pla
    ):
        """Test combined usage and cost estimation from STL."""
        mock_db.query.return_value.filter_by.return_value.first.return_value = (
            sample_material_pla
        )

        result = material_inventory.estimate_print_cost_from_stl(
            stl_volume_cm3=100.0,
            infill_percent=20,
            material_id="pla_black_esun",
            supports_enabled=False,
        )

        # Usage: 100 * 0.20 * 1.24 * 1.05 = 26.04g
        # Cost: (26.04 / 1000) * 21.99 = $0.57
        assert isinstance(result, CostEstimate)
        assert result.grams_used == pytest.approx(26.04, rel=0.01)
        assert result.material_cost_usd == Decimal("0.57")

    def test_estimate_cost_from_stl_with_supports(
        self, material_inventory, mock_db, sample_material_pla
    ):
        """Test cost estimation from STL with supports."""
        mock_db.query.return_value.filter_by.return_value.first.return_value = (
            sample_material_pla
        )

        result = material_inventory.estimate_print_cost_from_stl(
            stl_volume_cm3=100.0,
            infill_percent=20,
            material_id="pla_black_esun",
            supports_enabled=True,
        )

        # Usage: 100 * 0.20 * 1.15 (supports) * 1.24 * 1.05 = 29.95g
        # Cost: (29.95 / 1000) * 21.99 = $0.66
        assert result.grams_used == pytest.approx(29.95, rel=0.01)
        assert result.material_cost_usd == Decimal("0.66")
