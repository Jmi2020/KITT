"""STL file analysis using trimesh."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import trimesh
import numpy as np

from common.logging import get_logger

LOGGER = get_logger(__name__)


@dataclass
class ModelDimensions:
    """STL model dimensions and metadata."""
    width: float  # X dimension (mm)
    depth: float  # Y dimension (mm)
    height: float  # Z dimension (mm)
    max_dimension: float  # Largest of width/depth/height
    volume: float  # mm³
    surface_area: float  # mm²
    bounds: tuple  # [[min_x, min_y, min_z], [max_x, max_y, max_z]]


class STLAnalyzer:
    """Analyze STL files for printer selection."""

    def analyze(self, stl_path: Path) -> ModelDimensions:
        """
        Load STL and extract dimensions.

        Args:
            stl_path: Path to STL file

        Returns:
            ModelDimensions with all calculated properties

        Raises:
            FileNotFoundError: STL file doesn't exist
            ValueError: STL file is corrupted or invalid
        """
        if not stl_path.exists():
            raise FileNotFoundError(f"STL file not found: {stl_path}")

        try:
            mesh = trimesh.load(stl_path)
        except Exception as e:
            raise ValueError(f"Failed to load STL: {e}")

        # Validate mesh (best-effort; not all Trimesh versions expose validation helpers)
        is_watertight = getattr(mesh, "is_watertight", None)
        if is_watertight is False:
            LOGGER.warning("STL mesh is not watertight", path=str(stl_path))

        # Calculate bounding box
        bounds = mesh.bounds  # [[min_x, min_y, min_z], [max_x, max_y, max_z]]
        dimensions = bounds[1] - bounds[0]  # [width, depth, height]

        width, depth, height = dimensions
        max_dim = max(dimensions)

        LOGGER.info(
            "Analyzed STL",
            path=stl_path.name,
            dimensions={
                "width": f"{width:.1f}mm",
                "depth": f"{depth:.1f}mm",
                "height": f"{height:.1f}mm",
                "max": f"{max_dim:.1f}mm"
            }
        )

        return ModelDimensions(
            width=float(width),
            depth=float(depth),
            height=float(height),
            max_dimension=float(max_dim),
            volume=float(mesh.volume),
            surface_area=float(mesh.area),
            bounds=(bounds.tolist(),)
        )

    def scale_model(
        self,
        stl_path: Path,
        target_height: float,
        output_path: Path
    ) -> ModelDimensions:
        """
        Scale STL to target height (Phase 2).

        Args:
            stl_path: Input STL file
            target_height: Desired height in mm
            output_path: Where to save scaled STL

        Returns:
            ModelDimensions of scaled model
        """
        mesh = trimesh.load(stl_path)

        # Calculate current height
        current_height = mesh.bounds[1][2] - mesh.bounds[0][2]
        scale_factor = target_height / current_height

        LOGGER.info(
            "Scaling model",
            from_height=f"{current_height:.1f}mm",
            to_height=f"{target_height:.1f}mm",
            scale_factor=f"{scale_factor:.2f}x"
        )

        # Apply uniform scaling
        mesh.apply_scale(scale_factor)

        # Export scaled mesh
        mesh.export(output_path)

        # Analyze scaled dimensions
        return self.analyze(output_path)
