# Tripo API: STL File Generation Guide

## Overview

This guide explains how to generate STL files from the Tripo API for 3D printing workflows. STL (Standard Triangle Language) is the standard format for 3D printing, containing only geometry data without textures or materials.

---

## Method 1: Direct STL Export via Convert Task (Recommended)

The Tripo API uses a **post-processing convert task** to transform generated models into different formats, including STL.

### Workflow Steps

1. **Generate your 3D model** using text-to-3d, image-to-3d, or multiview-to-3d
2. **Retrieve the task_id** from the generation response
3. **Submit a convert task** to transform the model to STL format
4. **Download the STL file** once conversion is complete

---

## Step-by-Step Implementation

### Step 1: Generate the 3D Model

First, create your model using any generation endpoint:

```bash
curl -X POST https://api.tripo3d.ai/v2/openapi/image-to-3d \
  -H "Authorization: Bearer <TRIPO_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "image_url": "https://your-uploaded-image-url.jpg",
    "model_version": "v2.5"
  }'
```

**Response:**
```json
{
  "code": 0,
  "data": {
    "task_id": "abc123def456"
  }
}
```

Save the `task_id` for the next step.

---

### Step 2: Wait for Model Generation to Complete

Poll the task status endpoint until generation is complete:

```bash
curl -X GET https://api.tripo3d.ai/v2/openapi/task/abc123def456 \
  -H "Authorization: Bearer <TRIPO_API_KEY>"
```

**Response when complete:**
```json
{
  "code": 0,
  "data": {
    "task_id": "abc123def456",
    "status": "success",
    "model": {
      "model_id": "model_xyz789",
      "rendered_image": "https://...",
      "pbr_model": "https://...model.glb"
    }
  }
}
```

---

### Step 3: Submit Convert Task to STL Format

Use the **convert** endpoint with the original `task_id` to request STL format:

```bash
curl -X POST https://api.tripo3d.ai/v2/openapi/convert \
  -H "Authorization: Bearer <TRIPO_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "original_task_id": "abc123def456",
    "format": "STL"
  }'
```

**Alternative parameter names (depending on API version):**
- `format`: `"STL"` or `"stl"`
- `output_format`: `"STL"`
- `target_format`: `"STL"`

**Response:**
```json
{
  "code": 0,
  "data": {
    "task_id": "convert_task_999",
    "status": "processing"
  }
}
```

---

### Step 4: Retrieve the STL File

Poll the convert task status:

```bash
curl -X GET https://api.tripo3d.ai/v2/openapi/task/convert_task_999 \
  -H "Authorization: Bearer <TRIPO_API_KEY>"
```

**Response when complete:**
```json
{
  "code": 0,
  "data": {
    "task_id": "convert_task_999",
    "status": "success",
    "model": {
      "stl_model": "https://cdn.tripo3d.ai/models/your_model.stl"
    }
  }
}
```

Download the STL file from the provided URL.

---

## Method 2: Using the Import-Model Endpoint

If you already have a GLB file or need to convert between formats:

```bash
curl -X POST https://api.tripo3d.ai/v2/openapi/import-model \
  -H "Authorization: Bearer <TRIPO_API_KEY>" \
  -F "model_file=@your_model.glb" \
  -F "output_format=STL"
```

This method is useful for:
- Converting existing GLB files to STL
- Batch processing multiple models
- Format conversion workflows

---

## Complete Python Example

```python
import requests
import time

API_KEY = "your_tripo_api_key"
BASE_URL = "https://api.tripo3d.ai/v2/openapi"
HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

def generate_model_from_image(image_url):
    """Generate 3D model from image"""
    response = requests.post(
        f"{BASE_URL}/image-to-3d",
        headers=HEADERS,
        json={
            "image_url": image_url,
            "model_version": "v2.5"
        }
    )
    return response.json()["data"]["task_id"]

def wait_for_task(task_id, timeout=300):
    """Poll until task completes"""
    start_time = time.time()
    while time.time() - start_time < timeout:
        response = requests.get(
            f"{BASE_URL}/task/{task_id}",
            headers=HEADERS
        )
        data = response.json()["data"]

        if data["status"] == "success":
            return data
        elif data["status"] == "failed":
            raise Exception(f"Task failed: {data.get('error')}")

        time.sleep(3)

    raise TimeoutError("Task did not complete in time")

def convert_to_stl(original_task_id):
    """Convert model to STL format"""
    response = requests.post(
        f"{BASE_URL}/convert",
        headers=HEADERS,
        json={
            "original_task_id": original_task_id,
            "format": "STL"
        }
    )
    return response.json()["data"]["task_id"]

def download_stl(stl_url, output_path):
    """Download the STL file"""
    response = requests.get(stl_url, stream=True)
    with open(output_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)

# Complete workflow
if __name__ == "__main__":
    # Generate model
    print("Generating 3D model...")
    task_id = generate_model_from_image("https://example.com/product.jpg")

    # Wait for generation
    print(f"Waiting for generation (task: {task_id})...")
    model_data = wait_for_task(task_id)
    print("Model generated successfully!")

    # Convert to STL
    print("Converting to STL format...")
    convert_task_id = convert_to_stl(task_id)

    # Wait for conversion
    print(f"Waiting for conversion (task: {convert_task_id})...")
    stl_data = wait_for_task(convert_task_id)

    # Download STL
    stl_url = stl_data["model"]["stl_model"]
    output_file = "output_model.stl"
    print(f"Downloading STL to {output_file}...")
    download_stl(stl_url, output_file)

    print(f"STL file saved successfully: {output_file}")
```

---

## STL Export Settings

When converting to STL, you may have additional parameters available:

### Binary vs ASCII Format
```json
{
  "original_task_id": "abc123",
  "format": "STL",
  "stl_format": "binary"
}
```

**Recommendation:** Use `"binary"` format for smaller file sizes and faster processing.

### Resolution/Triangle Count
```json
{
  "original_task_id": "abc123",
  "format": "STL",
  "face_limit": 100000
}
```

**For 3D Printing:**
- Low detail: 10,000 - 50,000 faces
- Medium detail: 50,000 - 150,000 faces
- High detail: 150,000+ faces

### Unit Settings
```json
{
  "original_task_id": "abc123",
  "format": "STL",
  "unit": "millimeters"
}
```

**Recommendation:** Use millimeters (mm) as the standard unit for 3D printing.

---

## Troubleshooting

### Issue: STL file not appearing in response

**Solution:** Ensure you are using the convert endpoint after model generation completes. Direct generation endpoints may only return GLB/OBJ formats.

### Issue: Convert endpoint returns error

**Possible causes:**
- Original task not completed
- Invalid task_id
- Format parameter incorrect (try "STL", "stl", or check API docs for exact format)

### Issue: STL file is too large or too small

**Solution:** Adjust the `face_limit` parameter or check the unit settings. Also verify your slicer software units match the export units.

---

## Important Notes for 3D Printing

1. **STL files contain only geometry** - No textures, colors, or materials are preserved
2. **Check mesh integrity** - Ensure the model is manifold (watertight) before printing
3. **Scale appropriately** - Verify units and dimensions in your slicer software
4. **Binary format preferred** - Smaller file size and faster processing
5. **Post-processing may be needed** - Use tools like Meshmixer or Blender to repair or optimize

---

## Summary Checklist

- [ ] Generate 3D model (text-to-3d, image-to-3d, or multiview-to-3d)
- [ ] Wait for generation task to complete (status: "success")
- [ ] Submit convert task with format: "STL"
- [ ] Wait for convert task to complete
- [ ] Download STL file from returned URL
- [ ] Verify STL in slicer software before printing
- [ ] Check dimensions and units match your requirements

---

## Quick Reference: API Endpoints

| Purpose | Endpoint | Method |
|---------|----------|--------|
| Generate from text | `/text-to-3d` | POST |
| Generate from image | `/image-to-3d` | POST |
| Generate from multi-view | `/multiview-to-3d` | POST |
| Check task status | `/task/{task_id}` | GET |
| Convert to STL | `/convert` | POST |
| Import and convert | `/import-model` | POST |

---

## Additional Resources

- **Tripo API Documentation:** https://platform.tripo3d.ai/docs
- **STL Format Specification:** Binary format recommended for production
- **3D Printing Best Practices:** Ensure model is manifold and properly scaled
