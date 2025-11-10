# Stable Diffusion Integration - Quick Start Guide

This guide will help you get started with KITTY's Stable Diffusion integration for local image generation on Apple Silicon.

## Overview

KITTY's Stable Diffusion integration provides:

- **Queued image generation** with non-blocking job submission
- **Multiple engine support**: Diffusers (default), InvokeAI, Automatic1111
- **MPS acceleration** for Apple Silicon (Metal Performance Shaders)
- **MinIO storage** with automatic artifact management
- **CLI and API** access for automation
- **Vision gallery** integration for easy image selection

## Prerequisites

1. **macOS 14+** with Apple Silicon (M1/M2/M3)
2. **Python 3.11+**
3. **Redis** - for job queue
4. **MinIO** - for S3-compatible storage (included in KITTY stack)
5. **GGUF models downloaded** (see below)

## Step 1: Download Models

Create the models directory and download Stable Diffusion models:

**Note:** This uses the same models directory as your llama.cpp models (`/Users/Shared/Coding/models`).

```bash
# Models directory should already exist from llama.cpp setup
# If not: mkdir -p /Users/Shared/Coding/models

# Install Hugging Face CLI if needed
pip install "huggingface_hub[cli]"

# Download SDXL base model (best quality, ~14GB)
huggingface-cli download stabilityai/stable-diffusion-xl-base-1.0 \
  --local-dir /Users/Shared/Coding/models/sd_xl_base

# Download SDXL refiner (optional, for extra quality, ~12GB)
huggingface-cli download stabilityai/stable-diffusion-xl-refiner-1.0 \
  --local-dir /Users/Shared/Coding/models/sd_xl_refiner

# Download SD 1.5 (faster, smaller, ~8GB)
huggingface-cli download runwayml/stable-diffusion-v1-5 \
  --local-dir /Users/Shared/Coding/models/sd15_base
```

**Estimated download time:** 30-60 minutes depending on internet speed.

## Step 2: Configure Models

Create the models configuration file:

```bash
# Copy the example models.yaml
cp services/images_service/models.yaml.example \
   /Users/Shared/Coding/models/models.yaml
```

The default configuration should work if you followed the paths above. Edit if needed:

```yaml
# /Users/Shared/Coding/models/models.yaml
sdxl_base: /Users/Shared/Coding/models/sd_xl_base
sdxl_refiner: /Users/Shared/Coding/models/sd_xl_refiner
sd15_base: /Users/Shared/Coding/models/sd15_base
```

## Step 3: Install Service Dependencies

```bash
cd services/images_service

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

## Step 4: Configure Environment

The service configuration is already in the main `.env` file. Verify these settings:

```bash
# Check .env for these variables (already configured)
grep -A 5 "Images Service" .env
```

You should see:
```
IMAGES_BASE=http://127.0.0.1:8089
S3_ENDPOINT_URL=http://localhost:9000
S3_BUCKET=kitty-artifacts
REDIS_URL=redis://127.0.0.1:6379/0
```

## Step 5: Start Redis

If not already running:

```bash
# macOS with Homebrew
brew services start redis

# Or run in foreground
redis-server
```

## Step 6: Start the Images Service

Start both the FastAPI service and RQ worker:

```bash
./ops/scripts/start-images-service.sh
```

This will:
1. Start the RQ worker for processing generation jobs
2. Start the FastAPI service on port 8089
3. Log output to `services/images_service/.logs/`

**Check status:**
```bash
# View service logs
tail -f services/images_service/.logs/service.log

# View worker logs
tail -f services/images_service/.logs/rq_worker.log
```

## Step 7: Test Image Generation

### Using CLI

```bash
# Generate an image (queued, non-blocking)
kitty-cli generate-image "studio photo of a matte black water bottle"

# Generate with specific parameters
kitty-cli generate-image "photoreal robot arm" \
  --width 1024 \
  --height 768 \
  --steps 40 \
  --wait

# List generated images
kitty-cli list-images

# Select an image (gets download URL)
kitty-cli select-image 1
```

### Using API

```bash
# Generate image
curl -X POST http://localhost:8089/api/images/generate \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "studio photo of a matte black water bottle",
    "width": 1024,
    "height": 1024,
    "steps": 30,
    "model": "sdxl_base"
  }'

# Check job status
curl http://localhost:8089/api/images/jobs/<job_id>

# List latest images
curl http://localhost:8089/api/images/latest?limit=10
```

### Via Gateway (if running full KITTY stack)

The Gateway proxies requests to the images service:

```bash
# Through Gateway
curl -X POST http://localhost:8080/api/images/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "futuristic drone", "model": "sdxl_base"}'
```

## Performance Expectations (M3 Ultra)

| Model | Resolution | Steps | Time | Quality |
|-------|-----------|-------|------|---------|
| SDXL Base | 1024x1024 | 30 | ~45-60s | Excellent |
| SDXL + Refiner | 1024x1024 | 30+10 | ~70-90s | Outstanding |
| SD 1.5 | 512x512 | 25 | ~15-20s | Good |

## Accessing Generated Images

### Option 1: MinIO Console

1. Open http://localhost:9001
2. Login with credentials from `.env` (default: minioadmin/minioadmin)
3. Navigate to `kitty-artifacts` bucket → `images/` prefix
4. Download PNGs directly

### Option 2: Vision Gallery (UI)

1. Open http://localhost:4173
2. Go to Vision gallery view
3. All generated images appear automatically
4. Click to view/download

### Option 3: CLI Selection

```bash
# List images
kitty-cli list-images

# Select by index to get presigned URL
kitty-cli select-image 3
```

## Integration with CAD Pipeline

Use generated images as reference for Tripo image-to-3D conversion:

```bash
# 1. Generate an image
kitty-cli generate-image "futuristic bracket with mounting holes" --wait

# 2. Select the image
kitty-cli select-image 1
# Copy the download URL

# 3. Use with Tripo (through CAD service)
kitty-cli cad "convert this image to 3D" --organic
# Paste the URL when prompted, or use storage helper
```

## Troubleshooting

### Service won't start

**Check Redis:**
```bash
redis-cli ping
# Should return: PONG
```

**Check MinIO:**
```bash
curl http://localhost:9000/minio/health/live
# Should return: 200 OK
```

**Check models.yaml:**
```bash
cat /Users/Shared/Coding/models/models.yaml
# Verify paths exist
ls /Users/Shared/Coding/models/sd_xl_base
```

### Generation is slow

1. **Check GPU acceleration:**
   ```python
   python3 -c "import torch; print(f'MPS available: {torch.backends.mps.is_available()}')"
   ```

2. **Reduce steps** for faster generation:
   ```bash
   kitty-cli generate-image "test prompt" --steps 20
   ```

3. **Use SD 1.5** instead of SDXL for speed:
   ```bash
   kitty-cli generate-image "test prompt" --model sd15_base --width 512 --height 512
   ```

### Out of memory errors

1. **Set memory tuning:**
   ```bash
   export PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.0
   ```

2. **Reduce resolution:**
   ```bash
   kitty-cli generate-image "prompt" --width 768 --height 768
   ```

3. **Close other GPU-intensive apps** (llama.cpp, browsers with hardware acceleration)

### Images not appearing in MinIO

**Check S3 credentials in .env:**
```bash
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin
S3_BUCKET=kitty-artifacts
```

**Verify bucket exists:**
```bash
# Install mc (MinIO client)
brew install minio/stable/mc

# Configure alias
mc alias set local http://localhost:9000 minioadmin minioadmin

# Check bucket
mc ls local/kitty-artifacts/images/
```

## Stopping the Service

```bash
./ops/scripts/stop-images-service.sh
```

## Advanced: Using InvokeAI

For a full UI-based authoring experience:

1. **Install InvokeAI:**
   ```bash
   python3 -m venv ~/venvs/invokeai
   source ~/venvs/invokeai/bin/activate
   pip install invokeai
   invokeai-configure
   ```

2. **Start InvokeAI:**
   ```bash
   invokeai-web --host 127.0.0.1 --port 9091
   ```

3. **Configure KITTY to use it:**
   ```bash
   # In services/images_service/.env
   IMAGE_ENGINE=invokeai
   INVOKE_HOST=127.0.0.1
   INVOKE_PORT=9091
   ```

4. **Restart images service:**
   ```bash
   ./ops/scripts/stop-images-service.sh
   ./ops/scripts/start-images-service.sh
   ```

## Next Steps

- **Explore the full API:** http://localhost:8089/docs
- **Review the recommended stack guide:** `Research/KITTY_SD_Recommended_Stack_Integration.md`
- **Integrate with workflows:** Use generated images as reference for CAD generation
- **Fine-tune models:** Add custom models to `models.yaml`

## Support

- **Documentation:** `Research/KITTY_SD_Recommended_Stack_Integration.md`
- **Alternative guide:** `Research/KITTY_SD_Integration_Guide.md`
- **Logs:** `services/images_service/.logs/`
- **API docs:** http://localhost:8089/docs
