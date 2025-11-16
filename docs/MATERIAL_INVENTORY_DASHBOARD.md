# Material Inventory Dashboard - User Guide

## Overview

The **Material Inventory Dashboard** is a comprehensive web interface for managing 3D printing materials and tracking spool inventory in real-time. This dashboard provides full visibility into material costs, usage, and stock levels to enable intelligent procurement and fabrication planning.

**Status**: ✅ **Production Ready** (P2 Implementation Complete)

**Access**: http://localhost:4173/?view=inventory

---

## Features

### 1. Real-Time Inventory Overview

**Statistics Cards** display key metrics at a glance:
- **Total Spools**: Count of all spools in inventory
- **Available**: Spools ready for use (status: available)
- **Low Stock**: Spools below 100g threshold (yellow warning)
- **Depleted**: Empty spools (status: depleted)
- **Total Value**: Current inventory value in USD
- **Total Weight**: Combined weight of all material (kg)

### 2. Material Catalog

Complete catalog of all supported materials with:
- **Material ID**: Unique identifier (e.g., `pla_black_esun`)
- **Type**: Material type (PLA, PETG, ABS, TPU, etc.)
- **Color**: Visual color badge
- **Manufacturer**: Brand (eSUN, Prusa, Polymaker, etc.)
- **Cost/kg**: Material cost per kilogram in USD
- **Density**: Material density in g/cm³
- **Temperature Ranges**: Nozzle and bed temp recommendations
- **Sustainability Score**: Environmental impact rating (0-100)

**Pre-loaded Materials** (12 types):
```
pla_black_esun          PLA     Black     eSUN         $20.00/kg   1.24 g/cm³
pla_white_prusa         PLA     White     Prusa        $25.00/kg   1.24 g/cm³
petg_clear_esun         PETG    Clear     eSUN         $23.00/kg   1.27 g/cm³
petg_orange_prusa       PETG    Orange    Prusa        $27.00/kg   1.27 g/cm³
abs_black_hatchbox      ABS     Black     Hatchbox     $22.00/kg   1.04 g/cm³
abs_red_polymaker       ABS     Red       Polymaker    $28.00/kg   1.04 g/cm³
tpu_black_ninjaflex     TPU     Black     NinjaFlex    $35.00/kg   1.21 g/cm³
tpu_blue_sainsmart      TPU     Blue      SainSmart    $30.00/kg   1.21 g/cm³
nylon_natural_taulman   Nylon   Natural   Taulman      $45.00/kg   1.14 g/cm³
nylon_white_polymaker   Nylon   White     Polymaker    $48.00/kg   1.14 g/cm³
pva_natural_ultimaker   PVA     Natural   Ultimaker    $50.00/kg   1.23 g/cm³
hips_white_verbatim     HIPS    White     Verbatim     $26.00/kg   1.03 g/cm³
```

### 3. Inventory Tracking

**Spool-Level Tracking** with:
- **Spool ID**: Unique identifier for each spool
- **Material Info**: Type, color, manufacturer, temperature ranges
- **Location**: Physical storage location (shelf, bin, printer)
- **Weight Tracking**:
  - Current weight vs initial weight (grams)
  - Visual progress bar (green/yellow/red based on percentage)
  - Percentage remaining
- **Status Badge**:
  - 🟢 **Available**: Ready for use
  - 🔵 **In Use**: Currently loaded in printer
  - 🟠 **Low Stock**: < 100g remaining
  - 🔴 **Depleted**: Empty spool
- **Value**: Current spool value based on remaining weight

**Low-Stock Visual Indicators**:
- Rows with < 100g highlighted with yellow background
- Weight bar turns yellow (10-30%) or red (< 10%)
- "Low Stock" badge prominently displayed

### 4. Advanced Filtering

Filter inventory by:
- **Material Type**: PLA, PETG, ABS, TPU, Nylon, PVA, HIPS
- **Manufacturer**: Search by brand name
- **Status**: Available, In Use, Depleted
- **Low Stock Only**: Toggle to show only spools below threshold

**Use Cases**:
- "Show all PLA spools" → Filter by material_type=pla
- "Find low-stock PETG" → Filter by type=petg + toggle low stock
- "All eSUN materials" → Search manufacturer="eSUN"

### 5. Add Inventory Interface

**Modal Form** for adding new spools with validation:
- **Spool ID** (required): Unique identifier (e.g., `spool_001`)
- **Material** (required): Select from catalog dropdown
- **Initial Weight** (required): Spool weight in grams (default: 1000g)
- **Location** (optional): Storage location
- **Notes** (optional): Free-form notes

**Automatic Tracking**:
- Purchase date auto-set to current timestamp
- Initial weight = current weight at creation
- Status automatically set to "available"

### 6. Cost Analytics

**Inventory Value Calculation**:
```
Spool Value = (Current Weight ÷ 1000) × Material Cost/kg
Total Value = Sum of all spool values
```

**Example**:
- Spool: 750g of PLA Black ($20/kg)
- Value: (750 ÷ 1000) × $20 = $15.00

**Use Cases**:
- Monthly inventory valuation for accounting
- Identify most expensive materials to optimize procurement
- Track capital tied up in filament inventory

---

## API Integration

The dashboard consumes the following backend endpoints:

### GET /api/fabrication/materials
List all materials from catalog.

**Query Parameters**:
- `material_type` (optional): Filter by type (e.g., pla, petg)
- `manufacturer` (optional): Filter by manufacturer

**Response**: Array of `MaterialResponse` objects

### GET /api/fabrication/materials/{material_id}
Get single material by ID.

**Response**: `MaterialResponse` object

### GET /api/fabrication/inventory
List all inventory items (spools) with optional filters.

**Query Parameters**:
- `material_type` (optional): Filter by material type
- `status` (optional): available, in_use, depleted
- `min_weight_grams` (optional): Minimum weight filter
- `max_weight_grams` (optional): Maximum weight filter
- `location` (optional): Location search

**Response**: Array of `InventoryItemResponse` objects

### GET /api/fabrication/inventory/{spool_id}
Get single inventory item by spool ID.

**Response**: `InventoryItemResponse` object

### POST /api/fabrication/inventory
Add new spool to inventory.

**Request Body**:
```json
{
  "spool_id": "spool_001",
  "material_id": "pla_black_esun",
  "initial_weight_grams": 1000,
  "purchase_date": "2025-11-16T20:30:00Z",
  "location": "Shelf A, Bin 3",
  "notes": "Purchased for urgent project"
}
```

**Response**: Created `InventoryItemResponse` object (HTTP 201)

---

## Usage Workflows

### Workflow 1: Add New Filament Spool

1. Click **"+ Add Spool"** button in header
2. Fill out form:
   - Spool ID: `spool_pla_black_001`
   - Material: Select "PLA - Black (eSUN)"
   - Initial Weight: 1000g (1kg spool)
   - Location: "Shelf A"
   - Notes: "Backup stock"
3. Click **"Add Spool"**
4. Spool appears in inventory table with status "Available"

### Workflow 2: Monitor Low-Stock Materials

1. Toggle **"Show Low Stock Only"** checkbox
2. Review highlighted rows (< 100g remaining)
3. Note materials approaching depletion
4. Plan procurement orders before stock runs out

### Workflow 3: Find Material for Print Job

1. Filter by material type: "PETG"
2. Filter by status: "Available"
3. Sort by weight (highest first)
4. Select spool with sufficient material
5. Note spool ID and location for loading

### Workflow 4: Calculate Inventory Value

1. View **"Total Value"** stat card ($XXX.XX)
2. Export data for accounting (future feature)
3. Track value changes over time

### Workflow 5: Organize Material Storage

1. Add location to each spool during intake
2. Use location filter to find spools by shelf/bin
3. Update locations when reorganizing storage

---

## Architecture

### Frontend (services/ui/src/pages/MaterialInventory.tsx)
- **React Component**: Functional component with hooks
- **State Management**: Local useState for materials, inventory, filters
- **API Client**: Fetch API with async/await
- **Styling**: CSS modules (MaterialInventory.css)
- **Responsive**: Mobile-friendly grid and table layouts

### Backend (services/fabrication/src/fabrication/)
- **API Layer**: FastAPI endpoints in `app.py`
- **Business Logic**: `intelligence/material_inventory.py`
- **Database Models**: `common/db/models.py` (Material, InventoryItem)
- **ORM**: SQLAlchemy with PostgreSQL

### Database Schema

**materials** table:
```sql
CREATE TABLE materials (
  id VARCHAR(100) PRIMARY KEY,
  material_type VARCHAR(50) NOT NULL,
  color VARCHAR(50) NOT NULL,
  manufacturer VARCHAR(120) NOT NULL,
  cost_per_kg_usd NUMERIC(10,2) NOT NULL,
  density_g_cm3 NUMERIC(4,2) NOT NULL,
  nozzle_temp_min_c INTEGER NOT NULL,
  nozzle_temp_max_c INTEGER NOT NULL,
  bed_temp_min_c INTEGER NOT NULL,
  bed_temp_max_c INTEGER NOT NULL,
  properties JSONB DEFAULT '{}',
  sustainability_score INTEGER,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP
);
```

**inventory** table:
```sql
CREATE TABLE inventory (
  id VARCHAR(100) PRIMARY KEY,
  material_id VARCHAR(100) REFERENCES materials(id),
  location VARCHAR(120),
  purchase_date TIMESTAMP NOT NULL,
  initial_weight_grams NUMERIC(10,2) NOT NULL,
  current_weight_grams NUMERIC(10,2) NOT NULL,
  status VARCHAR(20) NOT NULL,  -- available, in_use, depleted
  notes TEXT,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP
);
```

---

## Configuration

### Low-Stock Threshold

**Default**: 100 grams

**Override** via environment variable:
```bash
LOW_INVENTORY_THRESHOLD_GRAMS=150.0  # Set threshold to 150g
```

**Applied**:
- Yellow warning badges
- Low-stock filter
- Row highlighting

### Material Waste Factor

**Default**: 1.05 (5% waste)

**Override**:
```bash
MATERIAL_WASTE_FACTOR=1.10  # 10% waste for complex prints
```

**Used for**:
- Material usage estimation
- Cost calculation
- Print planning

---

## Roadmap

### Phase 4 Enhancements (Current)
- ✅ Material catalog with 12 pre-loaded materials
- ✅ Inventory tracking with spool-level detail
- ✅ Low-stock warnings and visual indicators
- ✅ Cost analytics and value calculation
- ✅ Add inventory interface
- ✅ Advanced filtering

### Phase 5 Enhancements (Planned)
- [ ] **Deduct Material** interface (manual usage logging)
- [ ] **Print Intelligence Integration**: Auto-deduct material after prints
- [ ] **Usage History Charts**: Line charts showing consumption over time
- [ ] **Cost Per Print Breakdown**: Visualize material costs by project
- [ ] **Procurement Automation**: Auto-generate purchase orders for low stock
- [ ] **Multi-User Access**: Role-based permissions for inventory management
- [ ] **Export to CSV**: Download inventory reports
- [ ] **Barcode/QR Scanning**: Scan spools for quick lookup

---

## Testing

### Manual Test Checklist

1. **Load Dashboard**:
   - Navigate to `http://localhost:4173/?view=inventory`
   - Verify statistics cards load correctly
   - Check material catalog displays all 12 materials

2. **Filter Inventory**:
   - Test material type filter (PLA, PETG, ABS)
   - Test manufacturer search
   - Test status filter (available, in_use, depleted)
   - Toggle "Low Stock Only" checkbox

3. **Add Spool**:
   - Click "+ Add Spool"
   - Fill form with valid data
   - Submit and verify spool appears in table
   - Test validation (missing required fields)

4. **Visual Indicators**:
   - Verify low-stock rows have yellow background
   - Check weight bars show correct color (green/yellow/red)
   - Confirm status badges display correctly

5. **Responsive Design**:
   - Resize browser window
   - Verify mobile layout adapts correctly
   - Check table scrolls horizontally on small screens

### API Testing

```bash
# List all materials
curl http://localhost:8080/api/fabrication/materials | jq

# List inventory with filters
curl "http://localhost:8080/api/fabrication/inventory?status=available&material_type=pla" | jq

# Add new spool
curl -X POST http://localhost:8080/api/fabrication/inventory \
  -H "Content-Type: application/json" \
  -d '{
    "spool_id": "test_spool_001",
    "material_id": "pla_black_esun",
    "initial_weight_grams": 1000,
    "purchase_date": "2025-11-16T20:00:00Z",
    "location": "Test Shelf",
    "notes": "Test spool"
  }' | jq
```

---

## Troubleshooting

### Issue: Dashboard shows "Loading inventory..." indefinitely

**Cause**: Backend service not running or API endpoint unreachable

**Solution**:
1. Check if fabrication service is running:
   ```bash
   docker compose -f infra/compose/docker-compose.yml ps fabrication
   ```
2. Verify API endpoint:
   ```bash
   curl http://localhost:8080/api/fabrication/inventory
   ```
3. Check service logs:
   ```bash
   docker compose -f infra/compose/docker-compose.yml logs fabrication
   ```

### Issue: "Failed to load materials" error

**Cause**: Database not initialized or materials table empty

**Solution**:
1. Run database migrations:
   ```bash
   alembic -c services/common/alembic.ini upgrade head
   ```
2. Seed materials catalog (if migration doesn't auto-seed):
   ```bash
   python ops/scripts/seed-materials.py
   ```

### Issue: Add Spool fails with "Material not found"

**Cause**: Selected material_id doesn't exist in catalog

**Solution**:
1. Verify material exists:
   ```bash
   curl http://localhost:8080/api/fabrication/materials/pla_black_esun
   ```
2. Use dropdown to select material (ensures valid ID)

### Issue: Statistics cards show $0.00 for total value

**Cause**: Inventory is empty or all spools are depleted

**Solution**:
1. Add inventory items with the "+ Add Spool" button
2. Verify spools have current_weight_grams > 0

---

## Related Documentation

- **Phase 4 Fabrication Intelligence**: `docs/PHASE4_PROGRESS_SUMMARY.md`
- **Material Inventory Backend**: `services/fabrication/src/fabrication/intelligence/material_inventory.py`
- **API Contracts**: `services/fabrication/src/fabrication/app.py` (lines 620-850)
- **Database Models**: `services/common/src/common/db/models.py` (lines 600-660)
- **I/O Control Dashboard**: `docs/IO_CONTROL_DASHBOARD.md`

---

## Support

For questions or issues:
1. Check logs: `docker compose logs fabrication`
2. Review API docs: `http://localhost:8080/docs`
3. File issue: https://github.com/Jmi2020/KITT/issues
