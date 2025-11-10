### 🎨 Stable Diffusion Image Generation

KITTY includes a local Stable Diffusion service for text-to-image generation with Apple Silicon (MPS) acceleration. Images are stored in MinIO and automatically integrate with the vision gallery.

**Quick Setup:**

```bash
# 1. Download SDXL models (one-time, ~14GB)
huggingface-cli download stabilityai/stable-diffusion-xl-base-1.0 \
  --local-dir /Users/Shared/Coding/models/sd_xl_base

# 2. Copy models configuration
cp services/images_service/models.yaml.example \
   /Users/Shared/Coding/models/models.yaml

# 3. Enable in .env
IMAGES_SERVICE_ENABLED=true

# 4. Start KITTY (images service auto-starts)
./ops/scripts/start-kitty-validated.sh
```

**Using the Service:**

```bash
# Interactive shell
kitty-cli shell
> /generate studio photo of a matte black water bottle
# Waits for generation, shows S3 key when done

# Standalone commands
kitty-cli generate-image "futuristic drone" --wait
kitty-cli list-images --limit 20
kitty-cli select-image 1  # Get presigned URL for CAD/Tripo

# Direct API access
curl -X POST http://localhost:8089/api/images/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "water bottle", "width": 1024, "height": 1024}'

# Check queue status
curl http://localhost:8089/api/images/stats
```

**Performance (M3 Ultra):**
- SDXL 1024×1024: ~45-60s (30 steps)
- SDXL + refiner: ~70-90s (30+10 steps)
- SD 1.5 512×512: ~15-20s (25 steps)

**Integration with CAD:**

Generated images can be used as reference for Tripo image-to-3D conversion:

```bash
kitty-cli shell
> /generate futuristic bracket with mounting holes
> /vision select last  # Or use /select-image
> /cad convert this to 3D --organic
```

**Architecture:**
- `services/images_service/` - FastAPI + RQ worker service
- Port 8089 (configurable via `SERVICE_PORT`)
- Queued jobs via Redis RQ
- MinIO storage at `s3://kitty-artifacts/images/`
- Gateway proxy at `/api/images/*`

**Docs:** See `docs/stable-diffusion-quickstart.md` for complete setup guide, troubleshooting, and advanced configuration (InvokeAI, Automatic1111).
