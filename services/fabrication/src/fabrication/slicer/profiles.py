"""Profile management for slicer configurations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from common.logging import get_logger

from .schemas import PrinterProfile, MaterialProfile, QualityProfile

LOGGER = get_logger(__name__)


class ProfileManager:
    """Manages slicer profiles for printers, materials, and quality presets."""

    def __init__(self, profiles_dir: str | Path):
        """Initialize profile manager.

        Args:
            profiles_dir: Base directory containing profile subdirectories
                         (printers/, filaments/, quality/)
        """
        self.profiles_dir = Path(profiles_dir)
        self._printer_cache: dict[str, PrinterProfile] = {}
        self._material_cache: dict[str, MaterialProfile] = {}
        self._quality_cache: dict[str, QualityProfile] = {}
        self._load_profiles()

    def _load_profiles(self) -> None:
        """Load all profiles from disk into cache."""
        # Load printer profiles
        printers_dir = self.profiles_dir / "printers"
        if printers_dir.exists():
            for profile_file in printers_dir.glob("*.json"):
                try:
                    data = json.loads(profile_file.read_text())
                    profile_id = profile_file.stem
                    self._printer_cache[profile_id] = PrinterProfile(
                        id=profile_id,
                        name=data.get("name", profile_id),
                        build_volume=tuple(data.get("build_volume", [200, 200, 200])),
                        nozzle_diameter=data.get("nozzle_diameter", 0.4),
                        max_bed_temp=data.get("max_bed_temp", 110),
                        max_nozzle_temp=data.get("max_nozzle_temp", 300),
                        heated_bed=data.get("heated_bed", True),
                        supported_materials=data.get("supported_materials", []),
                        curaengine_settings=data.get("curaengine_settings", {}),
                    )
                    LOGGER.debug("Loaded printer profile", profile_id=profile_id)
                except Exception as e:
                    LOGGER.warning(
                        "Failed to load printer profile",
                        file=str(profile_file),
                        error=str(e),
                    )

        # Load material profiles
        filaments_dir = self.profiles_dir / "filaments"
        if filaments_dir.exists():
            for profile_file in filaments_dir.glob("*.json"):
                try:
                    data = json.loads(profile_file.read_text())
                    profile_id = profile_file.stem
                    self._material_cache[profile_id] = MaterialProfile(
                        id=profile_id,
                        name=data.get("name", profile_id),
                        type=data.get("type", "PLA"),
                        default_nozzle_temp=data.get("default_nozzle_temp", 210),
                        default_bed_temp=data.get("default_bed_temp", 60),
                        nozzle_temp_range=tuple(data.get("nozzle_temp_range", [180, 230])),
                        bed_temp_range=tuple(data.get("bed_temp_range", [50, 70])),
                        cooling_fan_speed=data.get("cooling_fan_speed", 100),
                        compatible_printers=data.get("compatible_printers", []),
                        curaengine_settings=data.get("curaengine_settings", {}),
                    )
                    LOGGER.debug("Loaded material profile", profile_id=profile_id)
                except Exception as e:
                    LOGGER.warning(
                        "Failed to load material profile",
                        file=str(profile_file),
                        error=str(e),
                    )

        # Load quality profiles
        quality_dir = self.profiles_dir / "quality"
        if quality_dir.exists():
            for profile_file in quality_dir.glob("*.json"):
                try:
                    data = json.loads(profile_file.read_text())
                    profile_id = profile_file.stem
                    self._quality_cache[profile_id] = QualityProfile(
                        id=profile_id,
                        name=data.get("name", profile_id),
                        layer_height=data.get("layer_height", 0.2),
                        first_layer_height=data.get("first_layer_height", 0.25),
                        perimeters=data.get("perimeters", 3),
                        top_solid_layers=data.get("top_solid_layers", 5),
                        bottom_solid_layers=data.get("bottom_solid_layers", 4),
                        fill_density=data.get("fill_density", 20),
                        fill_pattern=data.get("fill_pattern", "gyroid"),
                        print_speed=data.get("print_speed", 80),
                        curaengine_settings=data.get("curaengine_settings", {}),
                    )
                    LOGGER.debug("Loaded quality profile", profile_id=profile_id)
                except Exception as e:
                    LOGGER.warning(
                        "Failed to load quality profile",
                        file=str(profile_file),
                        error=str(e),
                    )

        LOGGER.info(
            "Loaded slicer profiles",
            printers=len(self._printer_cache),
            materials=len(self._material_cache),
            qualities=len(self._quality_cache),
        )

    def get_printer_profile(self, printer_id: str) -> Optional[PrinterProfile]:
        """Get printer profile by ID."""
        return self._printer_cache.get(printer_id)

    def get_printer_profile_path(self, printer_id: str) -> Optional[Path]:
        """Get path to printer profile JSON file."""
        path = self.profiles_dir / "printers" / f"{printer_id}.json"
        return path if path.exists() else None

    def get_material_profile(
        self, material_id: str, printer_id: Optional[str] = None
    ) -> Optional[MaterialProfile]:
        """Get material profile by ID.

        Tries printer-specific profile first if printer_id provided,
        then falls back to generic profile.
        """
        # Try printer-specific first
        if printer_id:
            specific_id = f"{printer_id}_{material_id}"
            if specific_id in self._material_cache:
                return self._material_cache[specific_id]

        return self._material_cache.get(material_id)

    def get_material_profile_path(
        self, material_id: str, printer_id: Optional[str] = None
    ) -> Optional[Path]:
        """Get path to material profile JSON file."""
        # Try printer-specific first
        if printer_id:
            specific_path = (
                self.profiles_dir / "filaments" / printer_id / f"{material_id}.json"
            )
            if specific_path.exists():
                return specific_path

        generic_path = self.profiles_dir / "filaments" / f"{material_id}.json"
        return generic_path if generic_path.exists() else None

    def get_quality_profile(self, quality_id: str) -> Optional[QualityProfile]:
        """Get quality profile by ID."""
        return self._quality_cache.get(quality_id)

    def get_quality_profile_path(self, quality_id: str) -> Optional[Path]:
        """Get path to quality profile JSON file."""
        path = self.profiles_dir / "quality" / f"{quality_id}.json"
        return path if path.exists() else None

    def list_printers(self) -> list[PrinterProfile]:
        """List all available printer profiles."""
        return list(self._printer_cache.values())

    def list_materials(self, printer_id: Optional[str] = None) -> list[MaterialProfile]:
        """List available material profiles.

        Args:
            printer_id: If provided, filter to materials compatible with this printer
        """
        materials = list(self._material_cache.values())
        if printer_id:
            materials = [
                m
                for m in materials
                if not m.compatible_printers or printer_id in m.compatible_printers
            ]
        return materials

    def list_qualities(self) -> list[QualityProfile]:
        """List all available quality profiles."""
        return list(self._quality_cache.values())

    def reload(self) -> None:
        """Reload all profiles from disk."""
        self._printer_cache.clear()
        self._material_cache.clear()
        self._quality_cache.clear()
        self._load_profiles()

    def save_custom_profile(
        self,
        profile_type: str,
        profile_id: str,
        name: str,
        data: dict,
    ) -> Path:
        """Save a custom profile to disk.

        Custom profiles are stored in custom/ subdirectories under each profile type.

        Args:
            profile_type: Type of profile ("printer", "material", "quality")
            profile_id: Unique identifier for the profile
            name: Display name
            data: Profile-specific settings

        Returns:
            Path to the saved profile file

        Raises:
            ValueError: If profile_type is invalid or required data is missing
        """
        # Determine target directory and validate
        if profile_type == "printer":
            target_dir = self.profiles_dir / "printers" / "custom"
            required_fields = ["build_volume"]
        elif profile_type == "material":
            target_dir = self.profiles_dir / "filaments" / "custom"
            required_fields = ["default_nozzle_temp", "default_bed_temp"]
        elif profile_type == "quality":
            target_dir = self.profiles_dir / "quality" / "custom"
            required_fields = ["layer_height"]
        else:
            raise ValueError(f"Invalid profile type: {profile_type}")

        # Check required fields
        for field in required_fields:
            if field not in data:
                raise ValueError(f"Missing required field for {profile_type} profile: {field}")

        # Create custom directory if needed
        target_dir.mkdir(parents=True, exist_ok=True)

        # Build profile data
        profile_data = {"id": profile_id, "name": name, "is_custom": True, **data}

        # Save to file
        profile_path = target_dir / f"{profile_id}.json"
        profile_path.write_text(json.dumps(profile_data, indent=2))

        LOGGER.info(
            "Saved custom profile",
            profile_type=profile_type,
            profile_id=profile_id,
            path=str(profile_path),
        )

        # Reload to pick up the new profile
        self.reload()

        return profile_path

    def delete_custom_profile(self, profile_type: str, profile_id: str) -> bool:
        """Delete a custom profile.

        Args:
            profile_type: Type of profile ("printer", "material", "quality")
            profile_id: Profile identifier

        Returns:
            True if deleted, False if not found
        """
        if profile_type == "printer":
            target_dir = self.profiles_dir / "printers" / "custom"
        elif profile_type == "material":
            target_dir = self.profiles_dir / "filaments" / "custom"
        elif profile_type == "quality":
            target_dir = self.profiles_dir / "quality" / "custom"
        else:
            return False

        profile_path = target_dir / f"{profile_id}.json"
        if profile_path.exists():
            profile_path.unlink()
            LOGGER.info("Deleted custom profile", profile_type=profile_type, profile_id=profile_id)
            self.reload()
            return True

        return False

    def list_custom_profiles(self, profile_type: Optional[str] = None) -> list[dict]:
        """List all custom profiles.

        Args:
            profile_type: Optional filter by type ("printer", "material", "quality")

        Returns:
            List of custom profile metadata
        """
        custom_profiles = []

        type_dirs = {
            "printer": self.profiles_dir / "printers" / "custom",
            "material": self.profiles_dir / "filaments" / "custom",
            "quality": self.profiles_dir / "quality" / "custom",
        }

        for ptype, pdir in type_dirs.items():
            if profile_type and ptype != profile_type:
                continue
            if pdir.exists():
                for profile_file in pdir.glob("*.json"):
                    try:
                        data = json.loads(profile_file.read_text())
                        custom_profiles.append({
                            "id": data.get("id", profile_file.stem),
                            "name": data.get("name", profile_file.stem),
                            "type": ptype,
                            "is_custom": True,
                        })
                    except Exception:
                        pass

        return custom_profiles
