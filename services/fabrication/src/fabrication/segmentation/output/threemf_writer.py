"""3MF file writer for segmented mesh output."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import json
import tempfile

from common.logging import get_logger

from ..geometry.mesh_wrapper import MeshWrapper
from ..schemas import SegmentedPart, SegmentationResult

LOGGER = get_logger(__name__)


@dataclass
class ThreeMFConfig:
    """Configuration for 3MF output."""

    include_thumbnails: bool = True
    thumbnail_size: Tuple[int, int] = (256, 256)
    include_metadata: bool = True
    manufacturer: str = "KITT Fabrication"
    application: str = "KITT Mesh Segmentation"


class ThreeMFWriter:
    """
    Writer for 3MF (3D Manufacturing Format) files.

    Creates multi-part 3MF files with:
    - Individual mesh objects for each part
    - Assembly metadata and relationships
    - Build plate configuration
    - Color coding for part identification
    """

    def __init__(self, config: ThreeMFConfig = None):
        """Initialize writer with configuration."""
        self.config = config or ThreeMFConfig()
        self._lib3mf_available = self._check_lib3mf()

    def _check_lib3mf(self) -> bool:
        """Check if lib3mf is available."""
        try:
            import lib3mf  # noqa: F401
            return True
        except ImportError:
            LOGGER.warning("lib3mf not available, using trimesh fallback for 3MF export")
            return False

    def write(
        self,
        parts: List[MeshWrapper],
        output_path: Path,
        result: Optional[SegmentationResult] = None,
    ) -> Path:
        """
        Write parts to a 3MF file.

        Args:
            parts: List of mesh parts to include
            output_path: Output file path
            result: Optional segmentation result for metadata

        Returns:
            Path to written file
        """
        output_path = Path(output_path)

        if self._lib3mf_available:
            return self._write_lib3mf(parts, output_path, result)
        else:
            return self._write_trimesh_fallback(parts, output_path, result)

    def _write_lib3mf(
        self,
        parts: List[MeshWrapper],
        output_path: Path,
        result: Optional[SegmentationResult],
    ) -> Path:
        """Write 3MF using lib3mf library."""
        try:
            import lib3mf

            # Create wrapper and model
            wrapper = lib3mf.Wrapper()
            model = wrapper.CreateModel()

            # Set metadata
            if self.config.include_metadata:
                self._add_metadata(model, result)

            # Add mesh objects
            colors = self._generate_part_colors(len(parts))
            build_items = []

            for i, part in enumerate(parts):
                mesh_object = self._add_mesh_to_model(
                    model, part, f"part_{i:02d}", colors[i]
                )
                build_items.append(mesh_object)

            # Configure build items (placement on build plate)
            self._configure_build_plate(model, build_items, parts)

            # Write to file
            writer = model.QueryWriter("3mf")
            writer.WriteToFile(str(output_path))

            LOGGER.info(f"Wrote 3MF file with {len(parts)} parts to {output_path}")
            return output_path

        except Exception as e:
            LOGGER.error(f"lib3mf export failed: {e}, falling back to trimesh")
            return self._write_trimesh_fallback(parts, output_path, result)

    def _add_metadata(self, model, result: Optional[SegmentationResult]) -> None:
        """Add metadata to 3MF model."""
        import lib3mf

        metadata = model.GetMetaDataGroup()

        # Standard metadata
        metadata.AddMetaData("", "Application", self.config.application, "string", True)
        metadata.AddMetaData("", "Manufacturer", self.config.manufacturer, "string", True)

        if result:
            # Add segmentation-specific metadata
            metadata.AddMetaData(
                "", "PartCount", str(result.num_parts), "string", True
            )
            metadata.AddMetaData(
                "", "AssemblyNotes", result.assembly_notes[:500], "string", True
            )

            # Add hardware requirements as JSON
            if result.hardware_required:
                hardware_json = json.dumps(result.hardware_required)
                metadata.AddMetaData(
                    "", "HardwareRequired", hardware_json, "string", True
                )

    def _add_mesh_to_model(
        self,
        model,
        mesh: MeshWrapper,
        name: str,
        color: Tuple[int, int, int],
    ):
        """Add a mesh as an object in the 3MF model."""
        import lib3mf

        tm = mesh.as_trimesh
        vertices = tm.vertices
        faces = tm.faces

        # Create mesh object
        mesh_object = model.AddMeshObject()
        mesh_object.SetName(name)

        # Add vertices
        for v in vertices:
            mesh_object.AddVertex(lib3mf.Position(float(v[0]), float(v[1]), float(v[2])))

        # Add triangles
        for f in faces:
            mesh_object.AddTriangle(lib3mf.Triangle(int(f[0]), int(f[1]), int(f[2])))

        # Set color
        r, g, b = color
        base_material = model.AddBaseMaterialGroup()
        base_material.AddMaterial(name, lib3mf.Color(r, g, b, 255))

        return mesh_object

    def _configure_build_plate(
        self,
        model,
        mesh_objects: list,
        parts: List[MeshWrapper],
    ) -> None:
        """Configure build plate layout for parts."""
        import lib3mf

        # Calculate layout - arrange parts in a grid
        spacing = 10.0  # mm between parts
        current_x = 0.0
        current_y = 0.0
        row_height = 0.0

        max_row_width = 250.0  # Typical build plate width

        for i, (mesh_obj, part) in enumerate(zip(mesh_objects, parts)):
            dims = part.dimensions

            # Check if part fits in current row
            if current_x + dims[0] > max_row_width and current_x > 0:
                # Move to next row
                current_x = 0.0
                current_y += row_height + spacing
                row_height = 0.0

            # Create transformation matrix for positioning
            transform = lib3mf.Transform()
            transform.Fields[0][0] = 1.0  # Scale X
            transform.Fields[1][1] = 1.0  # Scale Y
            transform.Fields[2][2] = 1.0  # Scale Z
            transform.Fields[0][3] = current_x  # Translate X
            transform.Fields[1][3] = current_y  # Translate Y
            transform.Fields[2][3] = 0.0  # Translate Z (on build plate)

            # Add build item with transform
            model.AddBuildItem(mesh_obj, transform)

            # Update position for next part
            current_x += dims[0] + spacing
            row_height = max(row_height, dims[1])

    def _generate_part_colors(self, count: int) -> List[Tuple[int, int, int]]:
        """Generate distinct colors for parts."""
        # Use a colorblind-friendly palette
        palette = [
            (66, 133, 244),   # Blue
            (219, 68, 55),    # Red
            (244, 180, 0),    # Yellow
            (15, 157, 88),    # Green
            (171, 71, 188),   # Purple
            (255, 112, 67),   # Orange
            (0, 172, 193),    # Cyan
            (124, 179, 66),   # Lime
            (255, 167, 38),   # Amber
            (141, 110, 99),   # Brown
        ]

        colors = []
        for i in range(count):
            colors.append(palette[i % len(palette)])

        return colors

    def _write_trimesh_fallback(
        self,
        parts: List[MeshWrapper],
        output_path: Path,
        result: Optional[SegmentationResult],
    ) -> Path:
        """
        Fallback 3MF export using trimesh.

        Creates a scene with all parts and exports to 3MF.
        """
        try:
            import trimesh

            # Create scene with all parts
            scene = trimesh.Scene()
            colors = self._generate_part_colors(len(parts))

            current_x = 0.0
            spacing = 10.0

            for i, part in enumerate(parts):
                mesh = part.as_trimesh.copy()

                # Set color
                r, g, b = colors[i]
                mesh.visual.face_colors = [r, g, b, 255]

                # Position mesh
                mesh.apply_translation([current_x, 0, 0])

                # Add to scene
                scene.add_geometry(mesh, node_name=f"part_{i:02d}")

                # Update position for next part
                current_x += part.dimensions[0] + spacing

            # Export scene to 3MF
            scene.export(str(output_path), file_type="3mf")

            LOGGER.info(f"Wrote 3MF file (trimesh) with {len(parts)} parts to {output_path}")
            return output_path

        except Exception as e:
            LOGGER.error(f"Trimesh 3MF export failed: {e}")
            # Last resort: export individual STL files
            return self._write_individual_stls(parts, output_path)

    def _write_individual_stls(
        self,
        parts: List[MeshWrapper],
        output_path: Path,
    ) -> Path:
        """
        Emergency fallback: write individual STL files.

        Creates a directory with separate STL files for each part.
        """
        output_dir = output_path.parent / output_path.stem
        output_dir.mkdir(parents=True, exist_ok=True)

        for i, part in enumerate(parts):
            stl_path = output_dir / f"part_{i:02d}.stl"
            part.export(stl_path)
            LOGGER.info(f"Wrote part {i} to {stl_path}")

        # Write manifest
        manifest = {
            "num_parts": len(parts),
            "files": [f"part_{i:02d}.stl" for i in range(len(parts))],
            "note": "3MF export failed, individual STL files created",
        }

        manifest_path = output_dir / "manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)

        LOGGER.warning(f"3MF export failed, wrote {len(parts)} STL files to {output_dir}")
        return output_dir

    def write_individual_parts(
        self,
        parts: List[MeshWrapper],
        output_dir: Path,
        format: str = "3mf",
    ) -> List[Path]:
        """
        Write each part as a separate file.

        Args:
            parts: List of mesh parts
            output_dir: Directory for output files
            format: File format (3mf, stl)

        Returns:
            List of paths to written files
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        paths = []
        for i, part in enumerate(parts):
            filename = f"part_{i:02d}.{format}"
            filepath = output_dir / filename

            if format == "3mf":
                self.write([part], filepath)
            else:
                part.export(filepath)

            paths.append(filepath)
            LOGGER.info(f"Wrote {filepath}")

        return paths

    def add_assembly_instructions(
        self,
        model_path: Path,
        result: SegmentationResult,
    ) -> None:
        """
        Add assembly instructions as metadata to existing 3MF file.

        Creates or updates the assembly notes in the 3MF metadata.
        """
        if not self._lib3mf_available:
            LOGGER.warning("lib3mf not available, cannot add assembly instructions")
            return

        try:
            import lib3mf

            wrapper = lib3mf.Wrapper()
            model = wrapper.CreateModel()

            # Read existing file
            reader = model.QueryReader("3mf")
            reader.ReadFromFile(str(model_path))

            # Update metadata
            metadata = model.GetMetaDataGroup()
            metadata.AddMetaData(
                "", "AssemblyInstructions", result.assembly_notes, "string", True
            )

            # Write back
            writer = model.QueryWriter("3mf")
            writer.WriteToFile(str(model_path))

        except Exception as e:
            LOGGER.error(f"Failed to add assembly instructions: {e}")
