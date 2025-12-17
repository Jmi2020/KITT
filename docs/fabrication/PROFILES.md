# Slicer Profile Customization

This guide explains how to customize slicer profiles for different printers, materials, and quality settings.

## Profile Types

### Printer Profiles

Define the physical characteristics of each printer.

**Location**: `config/slicer_profiles/printers/`

**Example: `bambu_h2d.json`**
```json
{
  "id": "bambu_h2d",
  "name": "Bambu H2D",
  "build_volume": [256, 256, 256],
  "nozzle_diameter": 0.4,
  "max_bed_temp": 110,
  "max_nozzle_temp": 300,
  "heated_bed": true,
  "supported_materials": ["pla", "petg", "abs", "tpu"],
  "curaengine_settings": {
    "machine_width": 256,
    "machine_depth": 256,
    "machine_height": 256,
    "machine_heated_bed": true,
    "machine_center_is_zero": false,
    "machine_gcode_flavor": "Marlin",
    "machine_start_gcode": "G28 ; Home all axes\nG1 Z5 F3000 ; Raise Z",
    "machine_end_gcode": "M104 S0 ; Turn off extruder\nM140 S0 ; Turn off bed\nG28 X Y ; Home X Y"
  }
}
```

**Key Settings:**

| Setting | Description |
|---------|-------------|
| `build_volume` | [X, Y, Z] dimensions in mm |
| `nozzle_diameter` | Nozzle size in mm (typically 0.4) |
| `max_bed_temp` | Maximum bed temperature (C) |
| `max_nozzle_temp` | Maximum nozzle temperature (C) |
| `heated_bed` | Whether printer has heated bed |
| `supported_materials` | List of compatible material types |

### Material Profiles

Define temperature and flow settings for each filament type.

**Location**: `config/slicer_profiles/materials/`

**Example: `pla_generic.json`**
```json
{
  "id": "pla_generic",
  "name": "Generic PLA",
  "type": "PLA",
  "default_nozzle_temp": 210,
  "default_bed_temp": 60,
  "nozzle_temp_range": [190, 230],
  "bed_temp_range": [50, 70],
  "cooling_fan_speed": 100,
  "compatible_printers": ["bambu_h2d", "elegoo_giga", "snapmaker_artisan"],
  "curaengine_settings": {
    "material_print_temperature": 210,
    "material_bed_temperature": 60,
    "material_flow": 100,
    "retraction_amount": 0.8,
    "retraction_speed": 45
  }
}
```

**Common Materials:**

| Material | Nozzle Temp | Bed Temp | Notes |
|----------|-------------|----------|-------|
| PLA | 200-220 | 50-60 | Easy to print, good detail |
| PETG | 230-250 | 70-80 | Strong, slightly flexible |
| ABS | 240-260 | 100-110 | Requires enclosure |
| TPU | 220-240 | 40-60 | Flexible, slow printing |

### Quality Profiles

Define layer height and speed settings for different quality levels.

**Location**: `config/slicer_profiles/qualities/`

**Example: `normal.json`**
```json
{
  "id": "normal",
  "name": "Normal Quality",
  "layer_height": 0.2,
  "first_layer_height": 0.28,
  "perimeters": 3,
  "top_solid_layers": 5,
  "bottom_solid_layers": 4,
  "fill_density": 20,
  "fill_pattern": "gyroid",
  "print_speed": 80,
  "curaengine_settings": {
    "layer_height": 200,
    "layer_height_0": 280,
    "wall_line_count": 3,
    "top_layers": 5,
    "bottom_layers": 4,
    "infill_sparse_density": 20,
    "infill_pattern": "gyroid",
    "speed_print": 80
  }
}
```

**Quality Comparison:**

| Quality | Layer Height | Print Speed | Use Case |
|---------|--------------|-------------|----------|
| Draft | 0.3mm | 100mm/s | Quick prototypes |
| Normal | 0.2mm | 80mm/s | Balanced quality/speed |
| Fine | 0.12mm | 50mm/s | High detail, visible surfaces |

## Creating Custom Profiles

### 1. Create a New Printer Profile

Copy an existing profile and modify:

```bash
cp config/slicer_profiles/printers/bambu_h2d.json \
   config/slicer_profiles/printers/my_printer.json
```

Edit the new file with your printer's specifications.

### 2. Create a Custom Material

For specialty filaments:

```json
{
  "id": "silk_pla",
  "name": "Silk PLA",
  "type": "PLA",
  "default_nozzle_temp": 215,
  "default_bed_temp": 60,
  "nozzle_temp_range": [200, 230],
  "bed_temp_range": [50, 70],
  "cooling_fan_speed": 80,
  "compatible_printers": ["bambu_h2d", "elegoo_giga"],
  "curaengine_settings": {
    "material_print_temperature": 215,
    "material_bed_temperature": 60,
    "material_flow": 95,
    "retraction_amount": 0.6,
    "retraction_speed": 40
  }
}
```

### 3. Create a Custom Quality

For specific use cases:

```json
{
  "id": "vase_mode",
  "name": "Vase Mode",
  "layer_height": 0.2,
  "first_layer_height": 0.3,
  "perimeters": 1,
  "top_solid_layers": 0,
  "bottom_solid_layers": 3,
  "fill_density": 0,
  "print_speed": 40,
  "curaengine_settings": {
    "layer_height": 200,
    "wall_line_count": 1,
    "magic_spiralize": true,
    "speed_print": 40
  }
}
```

### 4. Reload Profiles

After creating or modifying profiles:

```http
POST /api/slicer/profiles/reload
```

Or restart the fabrication service.

## CuraEngine Settings Reference

Common CuraEngine settings you can customize:

### Layer Settings
- `layer_height`: Layer thickness in microns
- `layer_height_0`: First layer height
- `initial_layer_line_width_factor`: First layer width %

### Wall Settings
- `wall_line_count`: Number of perimeter walls
- `wall_thickness`: Total wall thickness (mm)
- `wall_0_wipe_dist`: Outer wall wipe distance

### Top/Bottom
- `top_layers`: Number of top solid layers
- `bottom_layers`: Number of bottom solid layers
- `top_bottom_pattern`: Pattern for top/bottom (lines, zigzag, concentric)

### Infill
- `infill_sparse_density`: Infill percentage (0-100)
- `infill_pattern`: Pattern (grid, lines, triangles, cubic, gyroid)
- `infill_line_distance`: Distance between infill lines

### Speed
- `speed_print`: Default print speed (mm/s)
- `speed_wall_0`: Outer wall speed
- `speed_wall_x`: Inner wall speed
- `speed_infill`: Infill speed
- `speed_travel`: Non-print move speed

### Support
- `support_enable`: Enable supports
- `support_type`: Support type (normal, tree)
- `support_angle`: Overhang angle threshold
- `support_density`: Support infill density

### Temperature
- `material_print_temperature`: Nozzle temperature
- `material_bed_temperature`: Bed temperature
- `material_print_temperature_layer_0`: First layer nozzle temp

### Retraction
- `retraction_enable`: Enable retraction
- `retraction_amount`: Retraction distance (mm)
- `retraction_speed`: Retraction speed (mm/s)

## Profile Inheritance

Profiles can inherit from base profiles:

```json
{
  "id": "petg_bambu",
  "inherits": "petg_generic",
  "name": "PETG for Bambu",
  "compatible_printers": ["bambu_h2d"],
  "curaengine_settings": {
    "material_print_temperature": 245,
    "retraction_amount": 0.6
  }
}
```

Only override the settings that differ from the base profile.

## Troubleshooting Profiles

### Profile Not Loading

Check:
1. JSON syntax is valid
2. Required fields are present (`id`, `name`)
3. File is in correct directory
4. Reload profiles after changes

### Print Quality Issues

| Problem | Setting to Adjust |
|---------|-------------------|
| Stringing | Increase retraction_amount, retraction_speed |
| Weak parts | Increase wall_line_count, infill_sparse_density |
| Poor adhesion | Increase layer_height_0, bed temperature |
| Warping | Enable brim, increase bed temperature |
| Overhangs drooping | Enable supports, reduce speed_wall |

### Temperature Issues

- If print fails immediately: Check temp ranges are within printer limits
- If first layer doesn't stick: Increase first layer temp, check bed level
- If material oozes: Reduce nozzle temp, increase retraction
