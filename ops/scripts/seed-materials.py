#!/usr/bin/env python3
"""Seed material catalog database with common filament materials.

Usage:
    python ops/scripts/seed-materials.py              # Default: data/seed_materials.json
    python ops/scripts/seed-materials.py --file path/to/materials.json
    python ops/scripts/seed-materials.py --dry-run    # Preview without inserting
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# Add services/common to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "services" / "common" / "src"))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from common.config import settings
from common.db.models import Base, Material
from common.logging import configure_logging, get_logger

configure_logging()
LOGGER = get_logger(__name__)


def load_materials_data(file_path: Path) -> dict:
    """Load materials from JSON file."""
    if not file_path.exists():
        raise FileNotFoundError(f"Materials file not found: {file_path}")

    with open(file_path, "r") as f:
        data = json.load(f)

    if "materials" not in data:
        raise ValueError("Invalid materials file: missing 'materials' key")

    return data


def seed_materials(session, materials_data: list, dry_run: bool = False):
    """Seed materials into database."""

    materials_added = 0
    materials_skipped = 0
    materials_updated = 0

    for material_data in materials_data:
        material_id = material_data["id"]

        # Check if material already exists
        existing = session.query(Material).filter_by(id=material_id).first()

        if existing:
            LOGGER.info(
                "Material already exists",
                material_id=material_id,
                manufacturer=material_data["manufacturer"],
            )
            materials_skipped += 1
            continue

        # Create new material
        material = Material(
            id=material_id,
            material_type=material_data["material_type"],
            color=material_data["color"],
            manufacturer=material_data["manufacturer"],
            cost_per_kg_usd=material_data["cost_per_kg_usd"],
            density_g_cm3=material_data["density_g_cm3"],
            nozzle_temp_min_c=material_data["nozzle_temp_min_c"],
            nozzle_temp_max_c=material_data["nozzle_temp_max_c"],
            bed_temp_min_c=material_data["bed_temp_min_c"],
            bed_temp_max_c=material_data["bed_temp_max_c"],
            properties=material_data.get("properties", {}),
            sustainability_score=material_data.get("sustainability_score"),
            created_at=datetime.utcnow(),
        )

        if dry_run:
            LOGGER.info(
                "[DRY RUN] Would add material",
                material_id=material_id,
                type=material_data["material_type"],
                color=material_data["color"],
                manufacturer=material_data["manufacturer"],
                cost_per_kg=material_data["cost_per_kg_usd"],
            )
        else:
            session.add(material)
            LOGGER.info(
                "Added material",
                material_id=material_id,
                type=material_data["material_type"],
                color=material_data["color"],
                manufacturer=material_data["manufacturer"],
                cost_per_kg=material_data["cost_per_kg_usd"],
            )

        materials_added += 1

    if not dry_run:
        session.commit()
        LOGGER.info("Materials seeded successfully", count=materials_added)
    else:
        LOGGER.info("[DRY RUN] Would seed materials", count=materials_added)

    return {
        "added": materials_added,
        "skipped": materials_skipped,
        "updated": materials_updated,
    }


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Seed material catalog database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--file",
        type=Path,
        default=Path("data/seed_materials.json"),
        help="Path to materials JSON file (default: data/seed_materials.json)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview materials without inserting into database",
    )
    args = parser.parse_args()

    # Load materials data
    LOGGER.info("Loading materials data", file=str(args.file))
    try:
        data = load_materials_data(args.file)
    except Exception as e:
        LOGGER.error("Failed to load materials data", error=str(e))
        return 1

    materials_count = len(data["materials"])
    LOGGER.info("Loaded materials", count=materials_count)

    # Create database connection
    if args.dry_run:
        LOGGER.info("[DRY RUN] Skipping database connection")
        results = seed_materials(None, data["materials"], dry_run=True)
    else:
        LOGGER.info("Connecting to database", url=settings.DATABASE_URL)
        engine = create_engine(settings.DATABASE_URL)
        Session = sessionmaker(bind=engine)
        session = Session()

        try:
            # Seed materials
            results = seed_materials(session, data["materials"], dry_run=False)

            LOGGER.info(
                "Seeding complete",
                added=results["added"],
                skipped=results["skipped"],
                updated=results["updated"],
            )

        except Exception as e:
            session.rollback()
            LOGGER.error("Failed to seed materials", error=str(e), exc_info=True)
            return 1
        finally:
            session.close()

    # Print summary
    print("\n" + "=" * 60)
    print(f"{'DRY RUN - ' if args.dry_run else ''}Material Seeding Summary")
    print("=" * 60)
    print(f"Materials to add:  {results['added']}")
    print(f"Materials skipped: {results['skipped']}")
    print(f"Materials updated: {results['updated']}")
    print(f"Total in file:     {materials_count}")
    print("=" * 60)

    if args.dry_run:
        print("\nThis was a dry run. No changes were made to the database.")
        print("Run without --dry-run to actually seed the database.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
