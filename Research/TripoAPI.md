# Tripo API Documentation Guide

## Overview

The Tripo API enables developers to programmatically generate high-quality 3D models from text descriptions, images, or multi-view photographs. This guide covers all API sections with an emphasis on **image uploads** and **text-based generation** as primary use cases.

---

## Part 1: Core API Sections (Primary Focus)

### 1. Authentication & General Setup

**API Endpoint:** `https://api.tripo3d.ai/v2/openapi`

**Authentication Method:**
- Use Bearer token authentication with your API key
- Header format: `Authorization: Bearer <TRIPO_API_KEY>`
- Generate your API key from the Tripo Platform at `https://platform.tripo3d.ai/`

**Important Note:** Your API key is visible only once upon creation. Store it securely and never share it publicly.

**Response Format:**
- All responses use JSON format
- Success code: `0`
- Error codes: Non-zero values with message and suggestion fields

---

### 2. File Upload

#### 2.1 Standard Upload Endpoint

**Use Case:** Direct file uploads for images and text to Tripo's platform.

**Supported File Types:**
- WebP
- JPEG
- PNG

**Image Specifications:**
- Resolution: Between 20px and 6000px
- Recommended minimum: 256px for best results
- Optimal quality: Higher resolution images (1024px and above)

**Request Structure:**
```
POST /upload
Content-Type: multipart/form-data

[image file binary data]
```

**Response:**
- Returns file reference information for use in subsequent generation requests
- File reference can be used in image-to-3D or multi-view generation endpoints

#### 2.2 STS (Security Token Service) Upload

**Use Case:** For advanced workflows requiring secure, direct cloud storage access with temporary credentials.

**When to Use STS Upload:**
- Large-scale batch processing
- Enhanced security requirements
- Direct S3 bucket access needed
- Integration with complex cloud infrastructure

**STS Upload Flow:**
1. Request temporary STS credentials from the API
2. Receive temporary authentication tokens
3. Upload files directly to designated S3 bucket using provided credentials
4. Reference uploaded files in generation requests

**Recommendation:** Start with standard upload for typical workflows. Use STS upload only if your production requirements explicitly need temporary token-based access or batch processing at scale.

---

### 3. Image-to-3D Generation (Text and Image Based)

#### 3.1 Text-to-3D Model

**Endpoint:** `POST /text-to-3d`

**Primary Use Case:** Generate 3D models from natural language descriptions.

**Request Parameters:**
- `prompt` (string, required): Detailed text description of the model to generate
- `model_version` (string, optional): Model version (default: latest)
  - Supported versions: v1.0, v2.0, v2.5
  - v2.5 recommended for best quality
- `style` (string, optional): Style of the model
- `texture_quality` (string, optional): Standard or HD
- `face_limit` (integer, optional): Maximum polygon count

**Response:**
- `task_id`: Unique identifier for tracking generation status
- `status`: Current generation state (created, processing, completed, failed)

**Example Workflow:**
```json
{
  "prompt": "A vintage leather armchair with brass studs, worn patina, sitting in dramatic studio lighting",
  "model_version": "v2.5",
  "style": "realistic",
  "texture_quality": "HD"
}
```

**Generation Time:** Typically 10-15 seconds for draft models.

#### 3.2 Image-to-3D Model

**Endpoint:** `POST /image-to-3d`

**Primary Use Case:** Convert single images into 3D models with automatic background removal.

**Request Parameters:**
- `image_url` (string, required): URL of the uploaded image
- `model_version` (string, optional): v2.5 recommended
- `texture_alignment` (string, optional):
  - `original_image`: Maps textures based on reference image
  - `align_image`: Fits texture to model geometry
- `texture_quality` (string, optional): Standard or HD
- `orientation` (string, optional): Model orientation (default, align_image)

**Response:**
- `task_id`: Model generation task identifier
- `model_mesh`: Generated 3D mesh file (GLB, OBJ, FBX formats available)
- `base_model`: Base geometry without textures
- `pbr_model`: PBR (Physically Based Rendering) model with materials
- `rendered_image`: Preview image of generated model

**Features:**
- Automatic background removal
- High-fidelity geometry generation
- Detailed PBR materials applied
- Production-ready output

#### 3.3 Multi-View/Multi-Image-to-3D

**Endpoint:** `POST /multiview-to-3d`

**Primary Use Case:** Generate highly accurate 3D models from multiple perspective images.

**Request Parameters:**
- `front_image_url` (string, required): Front view image
- `back_image_url` (string, optional): Back view image
- `left_image_url` (string, optional): Left side view
- `right_image_url` (string, optional): Right side view
- `top_image_url` (string, optional): Top view
- `bottom_image_url` (string, optional): Bottom view

**Recommendation:** Provide views from complementary angles (e.g., front, side, top) for maximum accuracy.

**Response Format:** Same as image-to-3d endpoint

**Accuracy Advantage:** Multi-view generation produces significantly more accurate 3D geometry compared to single-image generation, with better capture of fine details and proper proportions.

---

### 4. Refine Draft Models

**Endpoint:** `POST /refine-draft`

**Primary Use Case:** Improve detail and quality of previously generated draft models.

**Request Parameters:**
- `model_task_id` (string, required): Task ID from initial generation
- `model_version` (string, required): v1.4 or later required for refinement
- `api_key` (string, required): Your Tripo API key

**Process:**
1. Generate initial draft model using text-to-3d or image-to-3d
2. Obtain the `task_id` from the response
3. Submit refinement request with that task_id
4. Receive enhanced model with better geometry and details

**Quality Improvements:**
- Enhanced surface detail
- Better topology
- Refined textures
- Improved geometry accuracy

---

### 5. Retrieve Task Status & Results

**Endpoint:** `GET /task/{task_id}`

**Purpose:** Check generation progress and retrieve model files.

**Response Fields:**
- `status`: Current processing state (processing, completed, failed)
- `progress`: Percentage completion
- `model_mesh`: Generated mesh file reference
- `pbr_model`: Textured model reference
- `rendered_image`: Preview image
- `error`: Error message if generation failed

**Polling Strategy:**
- Check status every 2-3 seconds for active tasks
- Generation typically completes within 15-30 seconds
- Implement exponential backoff for production systems

---

## Part 2: Advanced Features & Additional Endpoints

### 6. Import & Format Conversion

**Endpoint:** `POST /import-model`

**Purpose:** Import existing 3D models and convert between formats.

**Supported Input Formats:**
- GLB
- OBJ
- FBX
- USD
- STL

**Supported Export Formats:**
- GLB (Recommended for web/game engines)
- OBJ (Universal 3D format)
- FBX (For animation/rigging)
- USD (Pixar universal format)
- STL (For 3D printing)
- Schematic (Procedural description)

**Request Parameters:**
- `model_file` (file, required): The model to import
- `output_format` (string, required): Desired output format
- `optimization_level` (string, optional): Low, medium, high

---

### 7. Animation & Rigging

**Endpoint:** `POST /rig-model`

**Purpose:** Automatically generate skeleton and rigging for character models.

**Request Parameters:**
- `model_task_id` (string, required): Task ID of generated model
- `model_version` (string, required): Model version used

**Output:**
- Rigged model with joint hierarchy
- Animation-ready structure
- Compatible with game engines and animation software

**Endpoint:** `POST /retarget-rig`

**Purpose:** Transfer animations or adjust rigging on existing rigged models.

**Use Cases:**
- Apply different character animations
- Adjust rig to match different proportions
- Transfer animation data between models

---

### 8. Mesh Completion & Validation

**Endpoint:** `POST /mesh-completion`

**Purpose:** Complete missing or partial mesh geometry.

**Request Parameters:**
- `model_file` (file, required): Incomplete or partial mesh
- `part_names` (array, optional): Specific parts to focus on
- `completion_strength` (float, optional): 0.0-1.0 intensity

**Use Cases:**
- Fill holes in geometry
- Complete partially scanned models
- Reconstruct missing segments

**Endpoint:** `POST /validate-mesh`

**Purpose:** Check mesh integrity without modification.

**Output:**
- Validation report
- Issues detected (non-manifold geometry, holes, etc.)
- Repair suggestions

---

### 9. Mesh Optimization

**Endpoint:** `POST /simplify-mesh`

**Purpose:** Reduce polygon count while maintaining visual quality.

**Request Parameters:**
- `model_file` (file, required): Model to optimize
- `target_face_count` (integer, required): Desired polygon count
- `quality_threshold` (float, optional): 0.0-1.0 visual quality preservation

**Benefits:**
- Reduced file size
- Faster rendering
- Better performance in real-time applications
- Maintained visual fidelity

**Endpoint:** `POST /retopology`

**Purpose:** Generate clean, optimized mesh topology.

**Advantages:**
- Professional-grade edge flow
- Animation-friendly structure
- Reduced geometry complexity
- Better deformation for rigging

---

### 10. Texture Generation & Customization

**Endpoint:** `POST /generate-texture`

**Purpose:** Generate or modify textures on existing models.

**Request Parameters:**
- `model_task_id` (string, required): Model to apply textures to
- `prompt` (string, optional): Text description for texture generation
- `reference_image_url` (string, optional): Image to base textures on
- `texture_quality` (string, optional): Standard or HD
- `texture_alignment` (string, optional): original_image or align_image
- `creativity_strength` (float, optional): 0.0-1.0 creative variation

**Use Cases:**
- Generate completely new textures
- Modify existing material properties
- Create stylized or photorealistic variants
- Apply textures from reference images

---

### 11. API Key Management & Account Information

**Endpoint:** `GET /account/balance`

**Purpose:** Check credit/token balance.

**Response:**
- `balance`: Remaining credits
- `usage_this_month`: Credits used in current billing period
- `next_reset_date`: When credits reset

**Endpoint:** `GET /account/usage`

**Purpose:** Detailed usage statistics.

**Response Fields:**
- `total_generations`: Total models generated
- `text_to_3d_count`: Text-based generations
- `image_to_3d_count`: Image-based generations
- `total_credits_used`: Credits consumed

---

### 12. Error Handling & Status Codes

**Common Status Codes:**

| Code | Meaning | Action |
|------|---------|--------|
| 0 | Success | Process response data |
| 400 | Bad Request | Check parameters and format |
| 401 | Authentication Failed | Verify API key validity |
| 402 | Insufficient Credits | Top up account balance |
| 404 | Not Found | Check task_id or resource identifier |
| 429 | Rate Limited | Implement exponential backoff |
| 500 | Server Error | Retry with exponential backoff |

**Best Practices:**
- Implement exponential backoff for retries
- Log all error responses with timestamps
- Set reasonable timeouts (30-60 seconds)
- Cache successful responses when possible

---

## Part 3: Workflow Examples

### Example 1: Simple Text-to-3D Workflow

```bash
# 1. Generate model from text prompt
curl -X POST https://api.tripo3d.ai/v2/openapi/text-to-3d \
  -H "Authorization: Bearer <TRIPO_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "A wooden dining chair with curved back",
    "model_version": "v2.5",
    "texture_quality": "HD"
  }'

# Response includes task_id

# 2. Poll for completion
curl -X GET https://api.tripo3d.ai/v2/openapi/task/{task_id} \
  -H "Authorization: Bearer <TRIPO_API_KEY>"

# 3. Download model when status is "completed"
```

### Example 2: Image Upload and Generation Workflow

```bash
# 1. Upload image file
curl -X POST https://api.tripo3d.ai/v2/openapi/upload \
  -H "Authorization: Bearer <TRIPO_API_KEY>" \
  -F "file=@product_photo.jpg"

# Response includes image_url

# 2. Generate 3D model from uploaded image
curl -X POST https://api.tripo3d.ai/v2/openapi/image-to-3d \
  -H "Authorization: Bearer <TRIPO_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "image_url": "https://platform.tripo3d.ai/assets/uploaded_image.jpg",
    "model_version": "v2.5",
    "texture_quality": "HD"
  }'

# 3. Poll and retrieve results
```

### Example 3: Multi-View Generation Workflow

```bash
# 1. Upload multiple images
# (Repeat upload for each view: front, side, top)

# 2. Generate from multiple views
curl -X POST https://api.tripo3d.ai/v2/openapi/multiview-to-3d \
  -H "Authorization: Bearer <TRIPO_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "front_image_url": "https://...",
    "left_image_url": "https://...",
    "top_image_url": "https://..."
  }'

# 3. Retrieve high-accuracy result
```

---

## Quick Reference: Choosing the Right Endpoint

| Input Type | Best Endpoint | Use When | Quality Level |
|-----------|---------------|----------|--------------|
| Text Description | `text-to-3d` | You have ideas but no reference images | Good to Excellent |
| Single Photo | `image-to-3d` | You have one reference image | Very Good |
| Multiple Views | `multiview-to-3d` | You have front, side, and top photos | Excellent |
| Draft Model | `refine-draft` | You want to enhance a generated model | Excellent |
| Import Existing | `import-model` | You need format conversion | High |

---

## Best Practices

1. **Start with appropriate version:** Use v2.5 for best quality vs. credit ratio
2. **Optimize inputs:** Clear, high-resolution images produce better results
3. **Use HD textures:** For production assets, select HD texture quality
4. **Implement polling:** Use exponential backoff and reasonable timeouts
5. **Handle errors gracefully:** Implement comprehensive error handling
6. **Monitor credits:** Check balance before batch operations
7. **Cache results:** Store generated models to avoid regeneration
8. **Validate uploads:** Test file formats and sizes before submission

---

## Rate Limits & Quotas

- Standard tier: 50 requests per minute
- Generation tasks: Typically 10-30 seconds per model
- File upload limits: Up to 50MB per file
- API key: Store securely, never commit to version control

---

## Support & Resources

- **Official Documentation:** `https://platform.tripo3d.ai/docs`
- **API Dashboard:** `https://platform.tripo3d.ai/`
- **Community Integrations:** ComfyUI, Blender Plugin, Houdini
- **Status Page:** Check API health and incidents
