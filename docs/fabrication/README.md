# KITTY Fabrication Console - Quick Start Guide

The Fabrication Console provides a 4-step workflow for turning ideas into physical objects:

**Generate > Segment > Slice > Print**

## Quick Start

### 1. Access the Console

Open the KITTY web UI and navigate to **Fabrication Console** from the sidebar.

### 2. Generate or Import a Model

**Option A: Generate with AI**
- Select a CAD provider (Tripo for organic shapes, Zoo for mechanical parts)
- Enter a prompt describing your object (e.g., "6 inch phone stand with 45 degree angle")
- Click **Generate**

**Option B: Import Existing**
- Click **Import Model**
- Select a `.3mf` or `.stl` file from your computer

### 3. Check Segmentation

The system automatically checks if your model fits the available printers:
- **Fits**: Proceed directly to slicing
- **Too Large**: Segment into printable parts with alignment joints

### 4. Slice for Your Printer

- **Select Printer**: Choose from Bambu H2D, Elegoo Giga, or Snapmaker Artisan
- **Choose Quality**: Quick (draft), Standard, or Fine
- **Advanced Settings**: Expand for infill %, supports, temperature overrides
- Click **Start Slicing**

### 5. Print

Once slicing completes:
- Review estimated print time and filament usage
- Click **Print Now** to start immediately
- Or **Add to Queue** for later

## Voice Commands (Maker Mode)

In Maker mode, you can use voice commands for the entire workflow:

```
"Make me a phone stand and print it"
"Design a 3 inch cube with rounded corners"
"Print that on the Elegoo"
"What's the status of my print?"
```

## Key Features

- **Progressive Dashboard**: All steps visible, unlock as prerequisites complete
- **Printer Recommendations**: Based on model size and printer availability
- **Quality Presets**: One-click selection with advanced override options
- **Real-time Status**: Track slicing progress and print status
- **Voice Integration**: Full workflow support in KITTY Maker mode

## Next Steps

- [Detailed Workflow Guide](./WORKFLOW.md) - Step-by-step with diagrams
- [API Reference](./API.md) - Complete endpoint documentation
- [Slicer Profiles](./PROFILES.md) - Customize print settings
- [Troubleshooting](./TROUBLESHOOTING.md) - Common issues and solutions
