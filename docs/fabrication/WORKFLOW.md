# Fabrication Workflow Guide

This document details the complete fabrication workflow from idea to printed object.

## Workflow Overview

```
+-------------+     +-------------+     +-----------+     +----------+
|   GENERATE  | --> |   SEGMENT   | --> |   SLICE   | --> |   PRINT  |
| (or Import) |     | (if needed) |     | (G-code)  |     | (send)   |
+-------------+     +-------------+     +-----------+     +----------+
     Step 1              Step 2            Step 3           Step 4
```

## Step 1: Generate or Import

### AI Generation

The console supports multiple CAD providers:

| Provider | Best For | Mode | Status |
|----------|----------|------|--------|
| **Tripo** | Organic shapes, sculptures, complex curves | organic | Active |
| **Zoo** | Mechanical parts, precise geometry | parametric | Active |
| **Meshy** | Coming soon | - | Placeholder |
| **Hitem3D** | Coming soon | - | Placeholder |

**Writing Good Prompts:**
- Include dimensions: "6 inch tall", "150mm wide"
- Describe purpose: "phone stand", "cable organizer"
- Specify features: "with 4 mounting holes", "rounded edges"

**Examples:**
```
"Design a phone stand 6 inches tall with a 45 degree viewing angle"
"Create a cable organizer box 100mm x 60mm x 30mm with 5 slots"
"Make a decorative vase with spiral patterns, 8 inches tall"
```

### Import Existing Models

Supported formats:
- `.3mf` (preferred - includes metadata)
- `.stl` (standard mesh format)

Drop files directly into the import zone or click to browse.

## Step 2: Segment (If Needed)

### Dimension Check

The system automatically measures your model against available printer build volumes:

| Printer | Build Volume (mm) |
|---------|-------------------|
| Bambu H2D | 256 x 256 x 256 |
| Elegoo Giga | 600 x 600 x 600 |
| Snapmaker Artisan | 400 x 400 x 400 |

### When Segmentation is Required

If any dimension exceeds all printer volumes, segmentation splits the model into printable parts:

**Segmentation Options:**
- **Wall Thickness**: Shell thickness (mm) - thicker = stronger
- **Joint Type**:
  - *Integrated Pins*: Printed connectors (no external hardware)
  - *Dowel*: External alignment pins
  - *Dovetail*: Interlocking joints
  - *None*: Flat surfaces for gluing
- **Max Parts**: Limit on number of segments

### Skipping Segmentation

If your model fits a printer, you can:
- Proceed directly to slicing (recommended)
- Force segmentation anyway (for shipping large items)

## Step 3: Slice

### Printer Selection

**Always select your printer manually.** The system provides recommendations but never auto-selects.

Recommendations are based on:
1. Model fits build volume
2. Printer is online and idle
3. Material compatibility

### Quality Presets

| Preset | Layer Height | Speed | Best For |
|--------|--------------|-------|----------|
| **Quick** | 0.3mm | Fast | Prototypes, test prints |
| **Standard** | 0.2mm | Balanced | General use (default) |
| **Fine** | 0.12mm | Slow | High detail, visible surfaces |

### Advanced Settings

Expand "Advanced Settings" for full control:

| Setting | Description | Default |
|---------|-------------|---------|
| **Infill %** | Internal fill density (0-100) | 20% |
| **Support Type** | None, Normal (grid), Tree (organic) | Tree |
| **Layer Height** | Override quality preset | - |
| **Nozzle Temp** | Material-specific override | Auto |
| **Bed Temp** | Material-specific override | Auto |

### Slicing Process

1. Click **Start Slicing**
2. Progress bar shows completion percentage
3. Wait for "Completed" status
4. Review estimates:
   - Print time (hours:minutes)
   - Filament usage (grams)
   - Layer count

## Step 4: Print

### Pre-Print Summary

Before sending, review:
- **Estimated Time**: Total print duration
- **Filament Usage**: Material required
- **Printer Status**: Online/Offline, Idle/Printing

### Print Options

**Print Now**:
- Uploads G-code and starts print immediately
- Requires confirmation dialog
- Printer must be online and idle

**Add to Queue**:
- Uploads G-code without starting
- Print starts when printer becomes available
- Good for batch operations

### Confirmation

The system always asks for confirmation before starting a print:
```
Are you sure you want to start printing on Bambu H2D?
Estimated time: 2h 15m

[Cancel] [Start Print]
```

## Voice Workflow

In Maker mode, the same workflow is available via voice:

```
User: "Make me a phone stand and print it"
KITTY: "I'll design that for you. How tall should it be?"
User: "6 inches"
KITTY: "Generating... Your phone stand is ready! It fits the Bambu H2D.
        Which printer? Bambu H2D is idle, Elegoo Giga is printing."
User: "Bambu"
KITTY: "Quality? Quick, Standard, or Fine?"
User: "Standard"
KITTY: "Slicing... 45% done... Complete! 45 minute print.
        Say 'confirm print' to start."
User: "Confirm print"
KITTY: "Starting print on Bambu H2D. Ready in about 45 minutes!"
```

## Elegoo Control Panel

When Elegoo Giga is selected and online, additional controls appear:

- **Thermal Panel**: Monitor/adjust bed and nozzle temperatures
- **G-code Console**: Send manual G-code commands

## Troubleshooting

See [TROUBLESHOOTING.md](./TROUBLESHOOTING.md) for common issues.
