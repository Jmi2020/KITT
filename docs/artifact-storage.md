# KITTY Artifact Storage Guide

## Overview

KITTY stores all generated CAD files (STL, STEP, OBJ, GLB) and reference images in a **shared directory accessible from macOS Finder**. This makes it easy to open generated files in Fusion 360, Blender, PrusaSlicer, or any other CAD/slicing software.

---

## Quick Start

### 1. Setup Artifacts Directory (One-Time)

```bash
# Run the automated setup script
./ops/scripts/setup-artifacts-dir.sh

# This creates: /Users/Shared/KITTY/artifacts
# with subdirectories for organization
```

### 2. Configure Environment

Add to your `.env` file (or use the default):

```bash
KITTY_ARTIFACTS_DIR=/Users/Shared/KITTY/artifacts
```

### 3. Restart KITTY Services

```bash
# Stop services
docker compose -f infra/compose/docker-compose.yml down

# Start with new configuration
docker compose -f infra/compose/docker-compose.yml up -d
```

### 4. Generate a Test File

```bash
# Generate a simple test model
kitty-cli cad "Create a simple 50mm cube"

# Open the artifacts directory
open /Users/Shared/KITTY/artifacts/cad
```

---

## Directory Structure

```
/Users/Shared/KITTY/artifacts/
├── README.md              # Usage instructions
├── .gitignore             # Prevents accidental commits
├── cad/                   # CAD files (STL, STEP, OBJ, GLB, DXF)
│   ├── 20251110_a3f2b1c_cube-50mm.stl
│   ├── 20251110_b7c4d2e_phone-stand.step
│   └── ...
├── images/                # Reference images for CAD generation
│   ├── 20251110_e8f9a1b_reference.jpg
│   └── ...
├── metadata/              # JSON files with generation details
│   ├── 20251110_a3f2b1c_cube-50mm.json
│   └── ...
└── temp/                  # Temporary processing files
```

---

## Opening Files in Different Applications

### Fusion 360

**Method 1: Drag & Drop**
1. Generate a model: `kitty-cli cad "phone stand with cable routing"`
2. Open Finder → `/Users/Shared/KITTY/artifacts/cad`
3. Drag the STL file into Fusion 360

**Method 2: File → Open**
1. Fusion 360 → **File** → **Open**
2. Navigate to `/Users/Shared/KITTY/artifacts/cad`
3. Select your STL file → **Open**
4. Choose import options (mesh, scale, etc.)

**Method 3: Insert into Current Design**
1. Fusion 360 → **File** → **Insert** → **Insert Mesh**
2. Browse to `/Users/Shared/KITTY/artifacts/cad`
3. Select STL → **Open**

**Working with Imported Meshes:**
- Fusion imports STLs as mesh bodies
- Use **Mesh** → **Create Mesh Section Sketch** to trace parametric geometry
- Or use **Mesh** → **Remesh** → **Create BRep** to convert to solid
- For reference: Right-click mesh → **Create Sketch** → trace your parametric design

### Blender

```
File → Import → Stl (.stl)
Navigate to: /Users/Shared/KITTY/artifacts/cad
Select file → Import STL
```

### PrusaSlicer / Cura

**Drag & Drop:**
Just drag any STL from the artifacts folder directly into the slicer window.

**Or use File menu:**
```
File → Import → Import STL/OBJ/3MF
Navigate to: /Users/Shared/KITTY/artifacts/cad
```

### FreeCAD

```
File → Open
Navigate to: /Users/Shared/KITTY/artifacts/cad
Select file → Open
```

### MeshLab

```
File → Import Mesh
Navigate to: /Users/Shared/KITTY/artifacts/cad
```

---

## File Naming Convention

KITTY uses a consistent naming pattern for all artifacts:

```
<timestamp>_<hash>_<description>.<extension>

Examples:
20251110_a3f2b1c_hex-box-50mm.stl
20251110_b7c4d2e_phone-stand-angle-45.step
20251110_e8f9a1b_reference-image.jpg
```

**Components:**
- **Timestamp**: `YYYYMMDD` format for easy chronological sorting
- **Hash**: 7-character hash for uniqueness
- **Description**: Sanitized, lowercase, hyphen-separated
- **Extension**: File type (`.stl`, `.step`, `.obj`, etc.)

---

## Metadata Files

Each CAD file has a corresponding JSON metadata file with complete generation details:

**Example: `20251110_a3f2b1c_cube-50mm.json`**

```json
{
  "timestamp": "2025-11-10T12:34:56Z",
  "prompt": "Create a simple 50mm cube",
  "provider": "tripo",
  "model_version": "v2.5",
  "parameters": {
    "size": "50mm",
    "texture_quality": "HD",
    "face_limit": 150000,
    "unit": "millimeters"
  },
  "reference_images": [
    "/app/storage/images/20251110_e8f9a1b_reference.jpg"
  ],
  "user": "Jeremiah",
  "conversation_id": "conv_a1b2c3d4",
  "processing_time_seconds": 45.2,
  "file_size_bytes": 2458624,
  "artifact_path": "/app/artifacts/cad/20251110_a3f2b1c_cube-50mm.stl"
}
```

**Metadata includes:**
- Original prompt and user
- Provider used (Zoo, Tripo, local)
- Model version and parameters
- Processing time
- Reference images (if any)
- File paths for traceability

---

## Advanced Configuration

### Custom Artifact Directory

If you prefer a different location:

**1. Set in `.env`:**
```bash
KITTY_ARTIFACTS_DIR=/path/to/your/custom/directory
```

**2. Run setup script:**
```bash
./ops/scripts/setup-artifacts-dir.sh /path/to/your/custom/directory
```

**3. Restart services:**
```bash
docker compose -f infra/compose/docker-compose.yml down
docker compose -f infra/compose/docker-compose.yml up -d
```

### Using iCloud Drive or Dropbox

You can sync artifacts to cloud storage:

```bash
# Set to iCloud Drive folder
KITTY_ARTIFACTS_DIR=/Users/YourName/Library/Mobile\ Documents/com~apple~CloudDocs/KITTY-Artifacts

# Or Dropbox
KITTY_ARTIFACTS_DIR=/Users/YourName/Dropbox/KITTY-Artifacts
```

⚠️ **Warning:** Ensure cloud sync doesn't interfere with active file writes.

### Network Share (Advanced)

To access artifacts from other computers on your network:

**1. Share the folder:**
- System Preferences → Sharing → File Sharing
- Add `/Users/Shared/KITTY/artifacts` to shared folders

**2. Access from other Macs:**
```
Finder → Go → Connect to Server (⌘K)
smb://your-mac-studio.local
```

---

## Troubleshooting

### Files Not Appearing

**1. Check directory exists:**
```bash
ls -la /Users/Shared/KITTY/artifacts
```

**2. Verify Docker mount:**
```bash
docker compose -f infra/compose/docker-compose.yml exec cad ls -la /app/storage
```

**3. Check permissions:**
```bash
# Should be readable/writable
ls -ld /Users/Shared/KITTY/artifacts
# Should show: drwxr-xr-x (755)

# Fix if needed:
chmod -R 755 /Users/Shared/KITTY/artifacts
```

### Permission Denied

**Check ownership:**
```bash
ls -la /Users/Shared/KITTY/artifacts/cad
```

**Fix permissions:**
```bash
# Make directory world-writable (Docker needs this)
chmod -R 755 /Users/Shared/KITTY/artifacts

# Or set specific owner if needed
sudo chown -R $(whoami):staff /Users/Shared/KITTY/artifacts
```

### Docker Can't Access Directory

**1. Verify mount in container:**
```bash
docker compose -f infra/compose/docker-compose.yml exec cad bash
ls -la /app/storage
ls -la /app/artifacts
exit
```

**2. Check docker-compose.yml:**
```yaml
volumes:
  - ${KITTY_ARTIFACTS_DIR:-/Users/Shared/KITTY/artifacts}:/app/storage
  - ${KITTY_ARTIFACTS_DIR:-/Users/Shared/KITTY/artifacts}:/app/artifacts
```

**3. Restart Docker Desktop** (sometimes needed for volume mount changes)

### Files Generated But Not Visible in Finder

**1. Refresh Finder:**
- Press `⌘R` in the Finder window
- Or close and reopen the folder

**2. Check the correct subdirectory:**
```bash
# CAD files go in:
open /Users/Shared/KITTY/artifacts/cad

# Images go in:
open /Users/Shared/KITTY/artifacts/images
```

**3. View logs to see where file was saved:**
```bash
docker compose -f infra/compose/docker-compose.yml logs cad | grep "artifact"
```

---

## Best Practices

### Organizing Files

**Create project subdirectories:**
```bash
cd /Users/Shared/KITTY/artifacts/cad
mkdir project-name
mv relevant-files*.stl project-name/
```

**Use metadata for tracking:**
- Check JSON files for original prompts
- Search metadata by provider: `grep -r "tripo" metadata/`
- Find files by date: `ls -lt cad/ | head -20`

### Cleanup

KITTY does **not** auto-delete old files. Clean up manually:

```bash
# Remove files older than 30 days
cd /Users/Shared/KITTY/artifacts/cad
find . -name "*.stl" -mtime +30 -delete

# Or move to archive
mkdir archive
find . -name "*.stl" -mtime +30 -exec mv {} archive/ \;
```

### Backup

**Time Machine (Automatic):**
```bash
# Ensure Time Machine includes this directory
# System Preferences → Time Machine → Options
# Make sure /Users/Shared is NOT excluded
```

**Manual Backup:**
```bash
# Zip all artifacts
cd /Users/Shared/KITTY
tar -czf artifacts-backup-$(date +%Y%m%d).tar.gz artifacts/

# Or use rsync
rsync -av artifacts/ /path/to/backup/location/
```

---

## Integration with CAD Workflow

### Typical Workflow

1. **Generate with KITTY:**
   ```bash
   kitty-cli cad "design for ergonomic phone stand"
   ```

2. **Review in Finder:**
   ```bash
   open /Users/Shared/KITTY/artifacts/cad
   ```

3. **Import to Fusion 360:**
   - Drag STL into Fusion
   - Use as reference or convert to parametric

4. **Refine Design:**
   - Modify in Fusion 360
   - Export as STL to same directory
   - Slice and print

5. **Iterate:**
   - If changes needed, regenerate with KITTY
   - Or manually edit in Fusion and re-export

### Batch Processing

Generate multiple variations:

```bash
# Generate several versions
kitty-cli cad "phone stand 30 degree angle"
kitty-cli cad "phone stand 45 degree angle"
kitty-cli cad "phone stand 60 degree angle"

# All will appear in artifacts/cad/
# Review in Finder, pick the best one
```

---

## FAQ

**Q: Can I move files out of the artifacts directory?**
A: Yes, feel free to move or copy files anywhere. KITTY doesn't track them after generation.

**Q: Will KITTY overwrite existing files?**
A: No, each file gets a unique hash in its name preventing collisions.

**Q: Can I delete the metadata files?**
A: Yes, but you'll lose provenance information (what prompt generated the file).

**Q: How much disk space do artifacts use?**
A: STL files typically range from 500KB to 50MB. Monitor with: `du -sh /Users/Shared/KITTY/artifacts`

**Q: Can I use this on Linux or Windows?**
A: Yes, just change the path in `.env` to a platform-appropriate location.

**Q: What if I'm using MinIO instead of local filesystem?**
A: This setup **replaces** MinIO for artifact storage. MinIO is still available but artifacts will go to the shared directory by default.

---

## Related Documentation

- [CAD Generation Guide](../Research/TripoSTL.md)
- [Tripo API Reference](../Research/TripoAPI.md)
- [Testing Checklist](tripo-stl-testing.md)
- [Project Overview](project-overview.md)

---

## Support

If you encounter issues:

1. Check this guide's Troubleshooting section
2. Review logs: `docker compose -f infra/compose/docker-compose.yml logs cad`
3. Verify setup: `./ops/scripts/setup-artifacts-dir.sh`
4. Open an issue with:
   - Output of `ls -la /Users/Shared/KITTY/artifacts`
   - Relevant log excerpts
   - Steps to reproduce
