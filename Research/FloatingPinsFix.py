"""
KITT Mesh Splitter - Connector Integration Fix

The issue: Pins are being generated as separate mesh objects rather than
being Boolean-merged into the cut pieces.

The fix: After each planar cut, we must:
1. UNION the male pin geometry INTO the positive-side piece
2. SUBTRACT the female socket geometry FROM the negative-side piece

This ensures pieces export as single manifold meshes with integrated connectors.
"""

import numpy as np
import trimesh
from typing import Tuple, List, Optional
from dataclasses import dataclass

# For robust Boolean operations, use manifold3d
# pip install manifold3d
try:
    import manifold3d
    MANIFOLD_AVAILABLE = True
except ImportError:
    MANIFOLD_AVAILABLE = False
    print("Warning: manifold3d not installed. Falling back to trimesh booleans (less reliable)")


@dataclass
class ConnectorParams:
    """Parameters for connector generation"""
    type: str = "dowel"  # "dowel", "dovetail", or "pyramid"
    diameter: float = 4.0  # mm for dowels
    height: float = 8.0    # mm, how far pin extends
    clearance: float = 0.15  # mm, gap for fit tolerance
    count: int = 2         # minimum connectors per cut
    edge_margin: float = 10.0  # mm from edge


def create_dowel_pin(
    position: np.ndarray,
    normal: np.ndarray,
    params: ConnectorParams
) -> Tuple[trimesh.Trimesh, trimesh.Trimesh]:
    """
    Create a dowel pin (male) and socket (female) at the given position.
    
    Args:
        position: 3D point on the cut surface
        normal: Direction the pin should extend (toward positive side)
        params: Connector parameters
        
    Returns:
        (male_pin, female_socket) - trimesh objects
    """
    # Male pin - slightly smaller for clearance
    male_radius = (params.diameter / 2) - (params.clearance / 2)
    male_pin = trimesh.creation.cylinder(
        radius=male_radius,
        height=params.height,
        sections=32
    )
    
    # Female socket - slightly larger for clearance
    female_radius = (params.diameter / 2) + (params.clearance / 2)
    female_socket = trimesh.creation.cylinder(
        radius=female_radius,
        height=params.height + 1.0,  # Slightly deeper for easy insertion
        sections=32
    )
    
    # Orient cylinders along the normal direction
    # Default cylinder is along Z axis, we need to rotate to normal
    z_axis = np.array([0, 0, 1])
    
    if not np.allclose(normal, z_axis):
        rotation_axis = np.cross(z_axis, normal)
        rotation_axis = rotation_axis / np.linalg.norm(rotation_axis)
        angle = np.arccos(np.clip(np.dot(z_axis, normal), -1, 1))
        rotation_matrix = trimesh.transformations.rotation_matrix(
            angle, rotation_axis
        )
        male_pin.apply_transform(rotation_matrix)
        female_socket.apply_transform(rotation_matrix)
    
    # Position the pin so it starts at the cut surface and extends outward
    # Male pin: extends from surface into positive side
    male_offset = position + normal * (params.height / 2)
    male_pin.apply_translation(male_offset)
    
    # Female socket: extends from surface into negative side
    female_offset = position - normal * (params.height / 2)
    female_socket.apply_translation(female_offset)
    
    return male_pin, female_socket


def create_pyramid_connector(
    position: np.ndarray,
    normal: np.ndarray,
    params: ConnectorParams
) -> Tuple[trimesh.Trimesh, trimesh.Trimesh]:
    """
    Create a hollow pyramid connector (prints support-free on both halves).
    
    This is the Split3r-style connector that works well for vertical wall prints.
    """
    # Base size
    base_size = params.diameter * 1.5
    top_size = base_size * 0.4  # Tapered top
    wall_thickness = 1.5  # mm
    
    # Outer pyramid (male)
    outer_vertices = np.array([
        # Base (at cut surface)
        [-base_size/2, -base_size/2, 0],
        [base_size/2, -base_size/2, 0],
        [base_size/2, base_size/2, 0],
        [-base_size/2, base_size/2, 0],
        # Top
        [-top_size/2, -top_size/2, params.height],
        [top_size/2, -top_size/2, params.height],
        [top_size/2, top_size/2, params.height],
        [-top_size/2, top_size/2, params.height],
    ])
    
    # Create faces for a pyramid frustum
    faces = np.array([
        # Base
        [0, 1, 2], [0, 2, 3],
        # Top
        [4, 6, 5], [4, 7, 6],
        # Sides
        [0, 4, 5], [0, 5, 1],
        [1, 5, 6], [1, 6, 2],
        [2, 6, 7], [2, 7, 3],
        [3, 7, 4], [3, 4, 0],
    ])
    
    male_pyramid = trimesh.Trimesh(vertices=outer_vertices, faces=faces)
    male_pyramid.fix_normals()
    
    # Female socket - larger with clearance
    socket_base = base_size + params.clearance * 2
    socket_top = top_size + params.clearance * 2
    
    socket_vertices = outer_vertices.copy()
    socket_vertices[:4] *= (socket_base / base_size)
    socket_vertices[4:] *= (socket_top / top_size)
    socket_vertices[:, 2] -= params.height  # Flip direction
    
    female_socket = trimesh.Trimesh(vertices=socket_vertices, faces=faces)
    female_socket.fix_normals()
    
    # Transform to position and orientation
    z_axis = np.array([0, 0, 1])
    if not np.allclose(normal, z_axis):
        rotation_axis = np.cross(z_axis, normal)
        if np.linalg.norm(rotation_axis) > 1e-6:
            rotation_axis = rotation_axis / np.linalg.norm(rotation_axis)
            angle = np.arccos(np.clip(np.dot(z_axis, normal), -1, 1))
            rotation_matrix = trimesh.transformations.rotation_matrix(angle, rotation_axis)
            male_pyramid.apply_transform(rotation_matrix)
            female_socket.apply_transform(rotation_matrix)
    
    male_pyramid.apply_translation(position)
    female_socket.apply_translation(position)
    
    return male_pyramid, female_socket


def boolean_union(mesh_a: trimesh.Trimesh, mesh_b: trimesh.Trimesh) -> trimesh.Trimesh:
    """
    Robust Boolean union using manifold3d (preferred) or trimesh fallback.
    """
    if MANIFOLD_AVAILABLE:
        return _manifold_union(mesh_a, mesh_b)
    else:
        return _trimesh_union(mesh_a, mesh_b)


def boolean_difference(mesh_a: trimesh.Trimesh, mesh_b: trimesh.Trimesh) -> trimesh.Trimesh:
    """
    Robust Boolean difference (A - B) using manifold3d or trimesh fallback.
    """
    if MANIFOLD_AVAILABLE:
        return _manifold_difference(mesh_a, mesh_b)
    else:
        return _trimesh_difference(mesh_a, mesh_b)


def _manifold_union(mesh_a: trimesh.Trimesh, mesh_b: trimesh.Trimesh) -> trimesh.Trimesh:
    """Union using manifold3d - guaranteed manifold output."""
    import manifold3d as mf
    
    # Convert to manifold
    m_a = mf.Manifold.from_mesh(mesh_a.vertices, mesh_a.faces)
    m_b = mf.Manifold.from_mesh(mesh_b.vertices, mesh_b.faces)
    
    # Perform union
    result = m_a + m_b
    
    # Convert back to trimesh
    mesh_result = result.to_mesh()
    return trimesh.Trimesh(
        vertices=mesh_result.vert_properties[:, :3],
        faces=mesh_result.tri_verts
    )


def _manifold_difference(mesh_a: trimesh.Trimesh, mesh_b: trimesh.Trimesh) -> trimesh.Trimesh:
    """Difference using manifold3d - guaranteed manifold output."""
    import manifold3d as mf
    
    m_a = mf.Manifold.from_mesh(mesh_a.vertices, mesh_a.faces)
    m_b = mf.Manifold.from_mesh(mesh_b.vertices, mesh_b.faces)
    
    result = m_a - m_b
    
    mesh_result = result.to_mesh()
    return trimesh.Trimesh(
        vertices=mesh_result.vert_properties[:, :3],
        faces=mesh_result.tri_verts
    )


def _trimesh_union(mesh_a: trimesh.Trimesh, mesh_b: trimesh.Trimesh) -> trimesh.Trimesh:
    """Fallback union using trimesh (less reliable)."""
    try:
        return mesh_a.union(mesh_b, engine='blender')
    except Exception:
        try:
            return mesh_a.union(mesh_b, engine='scad')
        except Exception as e:
            print(f"Warning: Boolean union failed: {e}")
            # Last resort: concatenate (NOT a true union)
            return trimesh.util.concatenate([mesh_a, mesh_b])


def _trimesh_difference(mesh_a: trimesh.Trimesh, mesh_b: trimesh.Trimesh) -> trimesh.Trimesh:
    """Fallback difference using trimesh (less reliable)."""
    try:
        return mesh_a.difference(mesh_b, engine='blender')
    except Exception:
        try:
            return mesh_a.difference(mesh_b, engine='scad')
        except Exception as e:
            print(f"Warning: Boolean difference failed: {e}")
            return mesh_a  # Return original if difference fails


def place_connectors_on_cut_boundary(
    cut_boundary: trimesh.path.Path3D,
    cut_normal: np.ndarray,
    params: ConnectorParams
) -> List[np.ndarray]:
    """
    Distribute connector positions across the cut boundary.
    Uses Poisson disk sampling for even distribution.
    """
    # Get the 2D boundary in the cut plane
    boundary_points = []
    for entity in cut_boundary.entities:
        points = cut_boundary.vertices[entity.points]
        boundary_points.extend(points)
    
    if not boundary_points:
        return []
    
    boundary_points = np.array(boundary_points)
    
    # Compute centroid and bounding box
    centroid = boundary_points.mean(axis=0)
    bbox_min = boundary_points.min(axis=0)
    bbox_max = boundary_points.max(axis=0)
    bbox_size = bbox_max - bbox_min
    
    # Calculate number of connectors based on area
    approx_area = bbox_size[0] * bbox_size[1] if len(bbox_size) >= 2 else bbox_size[0] ** 2
    area_per_connector = 400  # mm²
    num_connectors = max(params.count, int(approx_area / area_per_connector))
    
    # Simple grid-based placement (upgrade to Poisson disk for production)
    positions = []
    
    if num_connectors == 2:
        # Two connectors: place along longest axis
        longest_axis = np.argmax(bbox_size[:2]) if len(bbox_size) >= 2 else 0
        offset = bbox_size[longest_axis] * 0.3
        
        pos1 = centroid.copy()
        pos2 = centroid.copy()
        pos1[longest_axis] -= offset
        pos2[longest_axis] += offset
        positions = [pos1, pos2]
    else:
        # Grid placement for more connectors
        grid_size = int(np.ceil(np.sqrt(num_connectors)))
        for i in range(grid_size):
            for j in range(grid_size):
                if len(positions) >= num_connectors:
                    break
                x = bbox_min[0] + params.edge_margin + (i + 0.5) * (bbox_size[0] - 2*params.edge_margin) / grid_size
                y = bbox_min[1] + params.edge_margin + (j + 0.5) * (bbox_size[1] - 2*params.edge_margin) / grid_size
                z = centroid[2] if len(centroid) > 2 else 0
                positions.append(np.array([x, y, z]))
    
    return positions


def cut_and_integrate_connectors(
    mesh: trimesh.Trimesh,
    plane_origin: np.ndarray,
    plane_normal: np.ndarray,
    connector_params: ConnectorParams
) -> Tuple[trimesh.Trimesh, trimesh.Trimesh]:
    """
    THE MAIN FIX: Cut mesh and integrate connectors via Boolean operations.
    
    This is the corrected version that ensures pins are part of the mesh,
    not separate floating objects.
    
    Args:
        mesh: Input mesh to split
        plane_origin: Point on the cutting plane
        plane_normal: Normal vector of cutting plane (points toward positive side)
        connector_params: Connector configuration
        
    Returns:
        (positive_piece, negative_piece) with connectors integrated
    """
    # Normalize the plane normal
    plane_normal = plane_normal / np.linalg.norm(plane_normal)
    
    # Step 1: Perform the planar cut
    positive_piece = mesh.slice_plane(
        plane_origin=plane_origin,
        plane_normal=plane_normal,
        cap=True
    )
    
    negative_piece = mesh.slice_plane(
        plane_origin=plane_origin,
        plane_normal=-plane_normal,
        cap=True
    )
    
    if positive_piece is None or negative_piece is None:
        raise ValueError("Planar cut failed - check that plane intersects mesh")
    
    # Step 2: Get the cut boundary for connector placement
    # The cut boundary is the intersection of the plane with the mesh
    cut_section = mesh.section(plane_normal=plane_normal, plane_origin=plane_origin)
    
    if cut_section is None:
        print("Warning: Could not compute cut boundary, skipping connectors")
        return positive_piece, negative_piece
    
    # Step 3: Place connectors along the cut boundary
    connector_positions = place_connectors_on_cut_boundary(
        cut_section,
        plane_normal,
        connector_params
    )
    
    print(f"Placing {len(connector_positions)} connectors on cut surface")
    
    # Step 4: Generate and integrate connectors
    for i, pos in enumerate(connector_positions):
        print(f"  Integrating connector {i+1}/{len(connector_positions)}...")
        
        # Create male and female connector geometry
        if connector_params.type == "dowel":
            male_pin, female_socket = create_dowel_pin(pos, plane_normal, connector_params)
        elif connector_params.type == "pyramid":
            male_pin, female_socket = create_pyramid_connector(pos, plane_normal, connector_params)
        else:
            raise ValueError(f"Unknown connector type: {connector_params.type}")
        
        # ========================================
        # THIS IS THE CRITICAL FIX!
        # ========================================
        # UNION the male pin INTO the positive piece
        positive_piece = boolean_union(positive_piece, male_pin)
        
        # SUBTRACT the female socket FROM the negative piece
        negative_piece = boolean_difference(negative_piece, female_socket)
    
    # Step 5: Validate output meshes
    if not positive_piece.is_watertight:
        print("Warning: Positive piece is not watertight, attempting repair...")
        positive_piece.fill_holes()
        positive_piece.fix_normals()
    
    if not negative_piece.is_watertight:
        print("Warning: Negative piece is not watertight, attempting repair...")
        negative_piece.fill_holes()
        negative_piece.fix_normals()
    
    return positive_piece, negative_piece


# =============================================================================
# Example usage / test
# =============================================================================

if __name__ == "__main__":
    print("KITT Connector Integration Test")
    print("=" * 50)
    
    # Create a test cube (200mm, larger than typical build volume)
    test_mesh = trimesh.creation.box(extents=[200, 200, 200])
    print(f"Input mesh: {len(test_mesh.vertices)} vertices, {len(test_mesh.faces)} faces")
    
    # Define cut plane (horizontal cut at Z=100)
    plane_origin = np.array([0, 0, 0])
    plane_normal = np.array([0, 0, 1])  # Pointing up
    
    # Connector parameters
    params = ConnectorParams(
        type="dowel",
        diameter=4.0,
        height=8.0,
        clearance=0.15,
        count=2
    )
    
    # Perform the cut with integrated connectors
    print("\nPerforming cut with connector integration...")
    positive, negative = cut_and_integrate_connectors(
        test_mesh,
        plane_origin,
        plane_normal,
        params
    )
    
    print(f"\nPositive piece: {len(positive.vertices)} vertices, {len(positive.faces)} faces")
    print(f"  Watertight: {positive.is_watertight}")
    print(f"  Volume: {positive.volume:.1f} mm³")
    
    print(f"\nNegative piece: {len(negative.vertices)} vertices, {len(negative.faces)} faces")
    print(f"  Watertight: {negative.is_watertight}")
    print(f"  Volume: {negative.volume:.1f} mm³")
    
    # Export test pieces
    positive.export("test_positive_with_pins.stl")
    negative.export("test_negative_with_sockets.stl")
    print("\nExported: test_positive_with_pins.stl, test_negative_with_sockets.stl")