# Mesh Cutting with Automatic Connector Generation: Implementation Deep Dive

PrusaSlicer and Bambu Studio provide the most sophisticated open-source implementations of mesh cutting with automatic male/female connector generation, using CGAL Boolean operations to union pins to one mesh half while subtracting clearance-adjusted sockets from the other. Cura lacks this capability entirely. The core algorithm generates connector geometry once, then applies it with different Boolean operations and tolerance offsets to ensure perfect geometric correspondence between mating parts.

## How PrusaSlicer's cut tool generates matching connector pairs

PrusaSlicer's cut tool architecture spans two key components: the **GLGizmoCut3D** class in `src/slic3r/GUI/Gizmos/GLGizmoCut.cpp` handles interactive placement and visualization, while the actual cutting logic lives in `src/libslic3r/Model.cpp` and `src/libslic3r/CutUtils.cpp`. Boolean operations are performed through `src/libslic3r/MeshBoolean.cpp`, which wraps CGAL and libigl libraries.

The fundamental data structure is the `CutConnector` struct defined in `Model.hpp`:

```cpp
enum class CutConnectorType : int { Plug, Dowel, Snap };
enum class CutConnectorStyle : int { Prism, Frustum };
enum class CutConnectorShape : int { Circle, Triangle, Square, Hexagon };

struct CutConnector {
    Vec3d pos;                // Position on cut plane
    Transform3d rotation;     // Connector orientation
    float radius;             // Connector size
    float height;             // Connector depth
    float radius_tolerance;   // Clearance for female socket (radius)
    float height_tolerance;   // Clearance for female socket (depth)
    CutConnectorType type;    // Plug, Dowel, or Snap
    CutConnectorStyle style;  // Prism or Frustum (tapered)
    CutConnectorShape shape;  // Cross-section geometry
};
```

Connectors are stored in `ModelObject::cut_connectors`, a vector that **both halves reference** during the cut operation. This shared reference is critical—it ensures the male geometry and female geometry are mathematically identical except for the tolerance offset.

## The three connector types and their Boolean operations

**Plug connectors** implement the classic male/female pattern. The algorithm generates connector geometry (cylinder, prism, or frustum based on shape/style), then applies it asymmetrically: the lower piece receives a Boolean **union** with the raw connector mesh, while the upper piece receives a Boolean **difference** with a scaled-up version of the same geometry.

**Dowel connectors** behave differently—both halves receive Boolean **difference** operations, creating matching holes. The system then generates a separate `ModelObject` containing the dowel pin as a printable part. This approach suits scenarios where the connecting pin should be printed with different orientation or material.

**Snap connectors** add snap-fit barbs with flexible cantilevers on the male side and receiving cavities with retention slots on the female side. The geometry includes "bulge" and "space" parameters controlling the snap-fit mechanism, though users report these sometimes fail with complex meshes.

## How clearance ensures proper fit between mating parts

The tolerance mechanism operates by **scaling the subtracted geometry** rather than shrinking the unioned geometry. For a plug connector with `radius = 2.0mm` and `radius_tolerance = 0.075` (representing 7.5% or ~0.15mm):

```cpp
// Male connector: exact dimensions
TriangleMesh male = generate_connector(radius, height, shape);
lower_piece = boolean_union(lower_piece, male);

// Female socket: scaled by tolerance
float socket_radius = radius * (1.0 + radius_tolerance);
float socket_depth = height * (1.0 + height_tolerance);
TriangleMesh female = generate_connector(socket_radius, socket_depth, shape);
upper_piece = boolean_difference(upper_piece, female);
```

Typical clearance values for FDM printing range from **0.1mm (tight fit)** to **0.2mm (easy assembly)**. The tolerance is applied as a percentage in the UI, allowing proportional scaling for different connector sizes.

## Cut plane normal determines which side receives male geometry

The cut plane orientation defines a **normal vector** pointing toward one half of the model. By convention, the piece on the **positive normal side** (typically the upper piece when cutting horizontally) receives female sockets via subtraction, while the **negative normal side** receives male plugs via union.

The "Flip cut plane" button inverts this assignment without moving the plane itself—it simply swaps which piece gets which Boolean operation. This is stored as a boolean flag that conditionally reverses the male/female assignment during cut execution.

## Bambu Studio shares identical connector architecture

Bambu Studio, forked from PrusaSlicer, inherits the same cut tool implementation with equivalent file structure. The key files are `src/libslic3r/CutUtils.cpp`, `src/libslic3r/Model.cpp`, and the GUI layer in `src/slic3r/GUI/Gizmos/`. The connector types, shapes, and Boolean operation flow remain identical.

Bambu Studio adds integration with its multi-plate system, allowing cut parts to be assigned to different build plates automatically. The UI styling differs but the underlying algorithm—generate connector once, union to one piece, subtract with clearance from the other—is preserved from PrusaSlicer.

Both slicers support **dovetail mode**, which creates trapezoidal interlocking joints rather than discrete pin connectors. Dovetails use the same Boolean operation pattern but with wedge-shaped geometry that provides self-alignment and mechanical locking.

## Cura lacks native connector generation entirely

Cura does **not** include mesh cutting with connector generation. Its architecture focuses on slicing rather than mesh manipulation, offering only indirect workarounds:

The **Mesh Tools plugin** (fieldOfView/Cura-MeshTools on GitHub) can separate multi-body files into distinct objects but cannot cut single solid meshes or generate connectors. The **Banana Split plugin** offers crude build-plate-based splitting without connectors—users must manually position models and track cut coordinates.

For connector-based splitting, the recommended workflow is to use PrusaSlicer or Bambu Studio for cutting, export the resulting STL files, then import to Cura for final slicing. **LuBan3D** (a separate commercial tool unrelated to Snapmaker's Luban slicer) offers advanced multi-plane splitting with automatic connector generation at approximately $30/year.

## Python implementation using trimesh and manifold3d

Replicating the slicer behavior in Python requires four operations: mesh slicing, connector geometry generation, clearance application, and Boolean operations. The **manifold3d** engine provides the most reliable Boolean operations for 3D printing geometry.

```python
import trimesh
import numpy as np
from trimesh.intersections import slice_mesh_plane

def cut_mesh_with_connectors(
    mesh,
    plane_origin,
    plane_normal,
    connector_positions,
    connector_radius=2.0,
    connector_height=6.0,
    clearance=0.15
):
    """
    Cut mesh at plane and add male/female connectors.
    
    The key insight: generate connector geometry ONCE, then:
    - Union exact geometry to one piece (male)
    - Subtract enlarged geometry from other piece (female)
    """
    plane_normal = np.array(plane_normal)
    plane_normal = plane_normal / np.linalg.norm(plane_normal)
    
    # Step 1: Slice mesh into two halves
    top_half = slice_mesh_plane(
        mesh, plane_normal=plane_normal,
        plane_origin=plane_origin, cap=True
    )
    bottom_half = slice_mesh_plane(
        mesh, plane_normal=-plane_normal,
        plane_origin=plane_origin, cap=True
    )
    
    # Step 2: Generate connector pairs
    male_connectors = []
    female_connectors = []
    
    for pos in connector_positions:
        # Position so connector spans the cut plane
        center = np.array(pos) - (plane_normal * connector_height / 2)
        
        # MALE: exact dimensions
        male = trimesh.creation.cylinder(
            radius=connector_radius,
            height=connector_height,
            sections=32
        )
        male.apply_translation(center)
        male_connectors.append(male)
        
        # FEMALE: enlarged by clearance
        female = trimesh.creation.cylinder(
            radius=connector_radius + clearance,
            height=connector_height + clearance * 2,
            sections=32
        )
        female.apply_translation(center - plane_normal * clearance)
        female_connectors.append(female)
    
    # Step 3: Combine and apply Boolean operations
    all_males = trimesh.boolean.union(male_connectors, engine='manifold')
    all_females = trimesh.boolean.union(female_connectors, engine='manifold')
    
    # Union male pins to bottom half
    bottom_with_pins = trimesh.boolean.union(
        [bottom_half, all_males], engine='manifold'
    )
    
    # Subtract female sockets from top half
    top_with_sockets = trimesh.boolean.difference(
        [top_half, all_females], engine='manifold'
    )
    
    return bottom_with_pins, top_with_sockets
```

The critical implementation detail is that **both pieces reference identical connector positions**—the only difference is whether the geometry is added or subtracted, and whether clearance is applied. This guarantees geometric correspondence.

## Clearance guidelines for different fit types

Clearance selection depends on the desired assembly behavior:

| Fit Type | Clearance | Use Case |
|----------|-----------|----------|
| Press fit | 0.05–0.10mm | Permanent connections |
| Snug fit | 0.10–0.15mm | Parts that stay together |
| Sliding fit | 0.15–0.20mm | Easy assembly, minimal play |
| Loose fit | 0.25–0.35mm | Parts requiring rotation |

These values assume well-calibrated FDM printers with **0.4mm nozzles** and typical dimensional accuracy of ±0.1mm. Resin printers can use tighter tolerances; poorly calibrated printers need looser fits.

## Why Boolean operations sometimes fail

Both PrusaSlicer and Bambu Studio report "Unable to perform boolean operations on model meshes" when:

- Connectors intersect mesh edges or vertices at problematic angles
- Input meshes are non-manifold or contain self-intersections  
- Connector geometry creates degenerate faces or zero-thickness walls
- The resulting mesh would be non-manifold

The solution involves positioning connectors away from mesh edges (**minimum 2× connector radius**), ensuring input meshes are watertight using `trimesh.repair.fill_holes()` and `trimesh.repair.fix_normals()`, and using adequate mesh resolution (32+ segments for cylinders).

## Conclusion

The slicer cut tool algorithm is elegantly simple once understood: store connector definitions in a shared data structure, generate primitive geometry for each connector, then apply asymmetric Boolean operations—union for male, difference with clearance for female. PrusaSlicer's implementation using CGAL provides robust mesh Boolean operations, while Python's trimesh with manifold3d backend offers equivalent capability for custom tooling. The key architectural insight is that connector geometry must be generated from shared positions with consistent parameters; only the Boolean operation type and tolerance offset differ between mating parts.