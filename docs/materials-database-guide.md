# Materials Database Guide

Guide for managing KITTY's filament material catalog - Phase 4 Fabrication Intelligence.

## Overview

The materials database tracks filament properties, costs, and temperature ranges to enable intelligent material selection, inventory management, and print outcome learning.

---

## Database Schema

### Material Model

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `id` | String | Unique identifier | `pla_black_esun` |
| `material_type` | String | Material category | `pla`, `petg`, `abs`, `tpu`, `asa`, `nylon` |
| `color` | String | Filament color | `black`, `white`, `clear`, `red` |
| `manufacturer` | String | Brand/manufacturer | `eSUN`, `Prusa`, `HATCHBOX` |
| `cost_per_kg_usd` | Numeric | Price per kilogram (USD) | `21.99` |
| `density_g_cm3` | Numeric | Material density (g/cm³) | `1.24` (PLA), `1.27` (PETG) |
| `nozzle_temp_min_c` | Integer | Minimum nozzle temp (°C) | `190` |
| `nozzle_temp_max_c` | Integer | Maximum nozzle temp (°C) | `220` |
| `bed_temp_min_c` | Integer | Minimum bed temp (°C) | `50` |
| `bed_temp_max_c` | Integer | Maximum bed temp (°C) | `70` |
| `properties` | JSONB | Material characteristics | See below |
| `sustainability_score` | Integer | Environmental rating (0-100) | `75` |

### Material Properties (JSONB)

Flexible properties stored as JSON:

```json
{
  "strength": "medium|high|very_high",
  "flexibility": "low|medium|high|very_high|extreme",
  "food_safe": true|false,
  "uv_resistant": true|false,
  "biodegradable": true|false,
  "shrinkage": "low|medium|high",
  "ease_of_use": "beginner|intermediate|advanced",
  "hygroscopic": true|false,
  "requires_enclosure": true|false,
  "requires_direct_drive": true|false,
  "requires_drying": true|false,
  "weather_resistant": true|false,
  "chemical_resistant": true|false,
  "shore_hardness": "85A|95A",
  "toughness": "improved",
  "recycled_content": "100%"
}
```

---

## Seeding the Database

### Quick Start

```bash
# Preview materials (dry run)
python ops/scripts/seed-materials.py --dry-run

# Seed database with default file (data/seed_materials.json)
python ops/scripts/seed-materials.py

# Seed from custom file
python ops/scripts/seed-materials.py --file path/to/materials.json
```

### Requirements

- Database running and migrated: `alembic -c services/common/alembic.ini upgrade head`
- `DATABASE_URL` configured in `.env`
- Material data JSON file

### Script Behavior

- **Idempotent**: Running multiple times won't duplicate materials
- **Skip existing**: Materials with same `id` are skipped (logged)
- **Rollback on error**: Database transaction rolled back if any material fails
- **Detailed logging**: All operations logged with structlog

---

## Material Data Format

### JSON Structure

```json
{
  "materials": [
    {
      "id": "pla_black_esun",
      "material_type": "pla",
      "color": "black",
      "manufacturer": "eSUN",
      "cost_per_kg_usd": 21.99,
      "density_g_cm3": 1.24,
      "nozzle_temp_min_c": 190,
      "nozzle_temp_max_c": 220,
      "bed_temp_min_c": 50,
      "bed_temp_max_c": 70,
      "properties": {
        "strength": "medium",
        "flexibility": "low",
        "food_safe": false,
        "uv_resistant": false,
        "biodegradable": true,
        "shrinkage": "low",
        "ease_of_use": "beginner"
      },
      "sustainability_score": 75
    }
  ]
}
```

### Field Guidelines

**ID Naming Convention**: `{material_type}_{color}_{manufacturer_short}`
- Examples: `pla_black_esun`, `petg_clear_overture`, `tpu_95a_black_sainsmart`
- Use lowercase, underscores only
- Include shore hardness for TPU (e.g., `95a`, `85a`)

**Material Type**: Standardized categories
- Common: `pla`, `petg`, `abs`, `tpu`, `asa`, `nylon`, `pla_plus`
- Specialty: `carbon_fiber_pla`, `wood_pla`, `metal_pla`, `silk_pla`

**Density Values** (typical):
- PLA: `1.24` g/cm³
- PETG: `1.27` g/cm³
- ABS: `1.04` g/cm³
- TPU: `1.19-1.21` g/cm³
- ASA: `1.07` g/cm³
- Nylon: `1.14` g/cm³

**Temperature Ranges** (guidelines):
- PLA: Nozzle 180-220°C, Bed 50-70°C
- PETG: Nozzle 220-250°C, Bed 70-90°C
- ABS: Nozzle 230-260°C, Bed 90-110°C
- TPU: Nozzle 215-240°C, Bed 30-60°C

**Sustainability Score** (0-100):
- 90-100: Recycled content, biodegradable, low environmental impact
- 70-89: Biodegradable (PLA, PLA+)
- 40-69: Standard polymers (PETG)
- 20-39: High energy/emissions (ABS, ASA, Nylon, TPU)
- 0-19: Toxic or high environmental impact

---

## Adding New Materials

### Method 1: Edit JSON and Re-seed (Recommended)

1. Edit `data/seed_materials.json`
2. Add new material entry following format above
3. Run seed script: `python ops/scripts/seed-materials.py`
4. Script will skip existing materials and add only new ones

### Method 2: Direct Database Insert (API)

```python
from common.db.models import Material
from common.config import settings
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

engine = create_engine(settings.DATABASE_URL)
Session = sessionmaker(bind=engine)
session = Session()

material = Material(
    id="pla_blue_prusament",
    material_type="pla",
    color="blue",
    manufacturer="Prusa",
    cost_per_kg_usd=27.99,
    density_g_cm3=1.24,
    nozzle_temp_min_c=215,
    nozzle_temp_max_c=225,
    bed_temp_min_c=60,
    bed_temp_max_c=70,
    properties={
        "strength": "high",
        "flexibility": "low",
        "food_safe": false,
        "uv_resistant": false,
        "biodegradable": true,
        "shrinkage": "low",
        "ease_of_use": "beginner"
    },
    sustainability_score=75
)

session.add(material)
session.commit()
```

### Method 3: API Endpoint (Future)

```bash
curl -X POST http://localhost:8300/api/fabrication/materials \
  -H "Content-Type: application/json" \
  -d '{
    "id": "pla_blue_prusament",
    "material_type": "pla",
    "color": "blue",
    ...
  }'
```

---

## Common Material Properties Reference

### PLA (Polylactic Acid)
- **Ease**: Beginner-friendly
- **Strengths**: Affordable, biodegradable, low warping, wide color range
- **Weaknesses**: Low heat resistance (60°C), brittle, UV sensitive
- **Best For**: Prototypes, decorative items, indoor parts
- **Not For**: Outdoor use, high-temperature applications, flexible parts

### PETG (Polyethylene Terephthalate Glycol)
- **Ease**: Intermediate
- **Strengths**: Strong, impact-resistant, food-safe, UV-resistant, low shrinkage
- **Weaknesses**: Stringing, can be stringy, harder to post-process
- **Best For**: Functional parts, outdoor use, food containers, mechanical parts
- **Not For**: High-precision parts (due to stringing)

### ABS (Acrylonitrile Butadiene Styrene)
- **Ease**: Advanced
- **Strengths**: Strong, heat-resistant (100°C), impact-resistant, post-processable (acetone)
- **Weaknesses**: Requires enclosure, fumes (ventilation needed), warping, shrinkage
- **Best For**: Functional parts, automotive, high-temp applications
- **Not For**: Beginner users, open-air printing

### TPU (Thermoplastic Polyurethane)
- **Ease**: Advanced
- **Strengths**: Flexible, impact-resistant, abrasion-resistant, chemical-resistant
- **Weaknesses**: Requires direct drive extruder, slow print speeds, stringing
- **Best For**: Phone cases, gaskets, seals, flexible hinges, shock absorbers
- **Not For**: Rigid structural parts, Bowden extruders

### ASA (Acrylonitrile Styrene Acrylate)
- **Ease**: Advanced
- **Strengths**: UV-resistant, weather-resistant, heat-resistant, strong
- **Weaknesses**: Requires enclosure, fumes, shrinkage
- **Best For**: Outdoor parts, automotive, weather-exposed applications
- **Not For**: Indoor decorative items, beginner users

### Nylon (Polyamide)
- **Ease**: Advanced
- **Strengths**: Very strong, flexible, abrasion-resistant, chemical-resistant
- **Weaknesses**: Hygroscopic (absorbs moisture), requires drying, shrinkage, expensive
- **Best For**: Gears, bearings, functional parts, high-stress applications
- **Not For**: Beginners, humid environments without drying

---

## Maintenance

### Updating Material Costs

Costs fluctuate. Update periodically:

```bash
# Edit cost_per_kg_usd in data/seed_materials.json
nano data/seed_materials.json

# Re-seed (existing materials will be skipped)
python ops/scripts/seed-materials.py
```

To force update existing materials:
```python
# Manual update via database
session.query(Material).filter_by(id="pla_black_esun").update({"cost_per_kg_usd": 19.99})
session.commit()
```

### Deprecating Materials

```bash
# Option 1: Remove from seed file (future runs won't re-add)
# Option 2: Delete from database
python ops/scripts/delete-material.py --id pla_black_esun

# Option 3: Mark as unavailable (future feature)
# Will add "available" flag to material model
```

---

## Troubleshooting

### Issue: "Materials file not found"

**Solution**: Ensure file exists and path is correct
```bash
ls -la data/seed_materials.json
python ops/scripts/seed-materials.py --file data/seed_materials.json
```

### Issue: "Invalid materials file: missing 'materials' key"

**Solution**: Validate JSON structure. Must have top-level `materials` array:
```json
{
  "materials": [...]
}
```

### Issue: Database connection failed

**Solution**: Check database URL and ensure PostgreSQL running
```bash
# Verify DATABASE_URL in .env
cat .env | grep DATABASE_URL

# Test PostgreSQL connection
psql $DATABASE_URL -c "SELECT 1"

# Ensure migrations applied
alembic -c services/common/alembic.ini current
alembic -c services/common/alembic.ini upgrade head
```

### Issue: "Material already exists" but I want to update it

**Solution**: Direct database update or delete then re-seed
```bash
# Option 1: Update via Python/psql
psql $DATABASE_URL -c "UPDATE materials SET cost_per_kg_usd = 19.99 WHERE id = 'pla_black_esun'"

# Option 2: Delete then re-seed
psql $DATABASE_URL -c "DELETE FROM materials WHERE id = 'pla_black_esun'"
python ops/scripts/seed-materials.py
```

---

## References

- Phase 4 Specification: `specs/004-FabricationIntelligence/spec.md`
- Material Model: `services/common/src/common/db/models.py`
- Seed Script: `ops/scripts/seed-materials.py`
- Seed Data: `data/seed_materials.json`
- Database Migration: `services/common/alembic/versions/6e45f2a1_add_phase4_fabrication_intelligence.py`
