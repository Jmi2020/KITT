"""
KITTY Images Service - Main FastAPI Application
Queued image generation with MinIO storage and /vision integration
"""
import os
import json
from typing import Optional, Dict, Any
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from redis import Redis
from rq import Queue
from rq.job import Job
import boto3


# ============================================================================
# Configuration
# ============================================================================

REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
S3_ENDPOINT = os.getenv("S3_ENDPOINT_URL", "http://localhost:9000")
S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY", "minioadmin")
S3_SECRET_KEY = os.getenv("S3_SECRET_KEY", "minioadmin")
S3_REGION = os.getenv("S3_REGION", "us-east-1")
S3_BUCKET = os.getenv("S3_BUCKET", "kitty-artifacts")
S3_PREFIX = os.getenv("S3_PREFIX", "images/")

# Initialize Redis connection and RQ queue
redis_conn = Redis.from_url(REDIS_URL)
images_queue = Queue("images", connection=redis_conn)

# Initialize S3 client
s3_client = boto3.client(
    "s3",
    endpoint_url=S3_ENDPOINT,
    aws_access_key_id=S3_ACCESS_KEY,
    aws_secret_access_key=S3_SECRET_KEY,
    region_name=S3_REGION,
)


# ============================================================================
# API Models
# ============================================================================

class GenerateRequest(BaseModel):
    """Image generation request"""
    prompt: str = Field(..., description="Text prompt for image generation")
    width: int = Field(1024, ge=512, le=2048, description="Image width")
    height: int = Field(1024, ge=512, le=2048, description="Image height")
    steps: int = Field(30, ge=10, le=150, description="Number of inference steps")
    cfg: float = Field(7.0, ge=1.0, le=20.0, description="Guidance scale")
    seed: Optional[int] = Field(None, description="Random seed for reproducibility")
    model: str = Field("sdxl_base", description="Model name from models.yaml")
    refiner: Optional[str] = Field(None, description="Optional refiner model (SDXL only)")


class GenerateResponse(BaseModel):
    """Image generation response"""
    job_id: str
    status: str


class JobStatusResponse(BaseModel):
    """Job status response"""
    status: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class ImageItem(BaseModel):
    """Single image item in listing"""
    key: str
    size: int
    last_modified: str


class ImagesListResponse(BaseModel):
    """List of images"""
    items: list[ImageItem]


class SelectRequest(BaseModel):
    """Image selection request"""
    key: str = Field(..., description="S3 key of the image to select")


class SelectResponse(BaseModel):
    """Image selection response with imageRef"""
    imageRef: Dict[str, str]


# ============================================================================
# FastAPI Application
# ============================================================================

app = FastAPI(
    title="KITTY Images Service",
    description="Stable Diffusion image generation with queued jobs and MinIO storage",
    version="1.0.0"
)

# CORS middleware for UI access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# API Routes
# ============================================================================

@app.get("/")
def root():
    """Health check and service info"""
    return {
        "service": "KITTY Images Service",
        "status": "online",
        "engine": os.getenv("IMAGE_ENGINE", "diffusers"),
        "queue_name": "images",
    }


@app.post("/api/images/generate", response_model=GenerateResponse)
def generate(req: GenerateRequest):
    """
    Enqueue an image generation job

    Returns a job_id that can be used to poll job status
    """
    # Select engine based on IMAGE_ENGINE env var
    engine = os.getenv("IMAGE_ENGINE", "diffusers").lower()

    if engine == "a1111":
        from engines.a1111_client import run_a1111_job as job_fn
    elif engine == "invokeai":
        from engines.invokeai_client import run_invokeai_job as job_fn
    else:
        # Default to diffusers
        from worker_diffusers import run_diffusers_job as job_fn

    # Enqueue job with RQ
    job = images_queue.enqueue(
        job_fn,
        req.model_dump(),
        job_timeout="15m",  # 15 minute timeout for generation
        result_ttl=86400,  # Keep results for 24 hours
        failure_ttl=3600,  # Keep failed jobs for 1 hour
    )

    return GenerateResponse(job_id=job.id, status="queued")


@app.get("/api/images/jobs/{job_id}", response_model=JobStatusResponse)
def job_status(job_id: str):
    """
    Get status of a generation job

    Status can be: queued, started, finished, failed
    """
    try:
        job = Job.fetch(job_id, connection=redis_conn)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    if job.is_failed:
        error_info = str(job.exc_info) if job.exc_info else "Unknown error"
        # Truncate long error messages
        error_info = error_info[-800:] if len(error_info) > 800 else error_info
        return JobStatusResponse(status="failed", error=error_info)

    if job.is_finished:
        return JobStatusResponse(status="finished", result=job.result)

    return JobStatusResponse(status=job.get_status())


@app.get("/api/images/latest", response_model=ImagesListResponse)
def latest(limit: int = 36):
    """
    List latest generated images from MinIO

    Returns most recently modified images first
    """
    try:
        response = s3_client.list_objects_v2(Bucket=S3_BUCKET, Prefix=S3_PREFIX)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list images: {e}")

    items = response.get("Contents", [])

    # Sort by modification time (newest first)
    items.sort(key=lambda x: x["LastModified"], reverse=True)

    # Filter PNG files only and format response
    image_items = [
        ImageItem(
            key=item["Key"],
            size=item["Size"],
            last_modified=item["LastModified"].isoformat()
        )
        for item in items[:limit]
        if item["Key"].lower().endswith(".png")
    ]

    return ImagesListResponse(items=image_items)


@app.post("/api/images/select", response_model=SelectResponse)
def select_image(body: SelectRequest):
    """
    Select an image and return an imageRef

    This aligns with KITTY's /vision imageRefs contract
    Returns a presigned download URL and storage URI
    """
    key = body.key

    # Verify the object exists
    try:
        s3_client.head_object(Bucket=S3_BUCKET, Key=key)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Image not found: {key}")

    # Generate presigned URL (valid for 24 hours)
    try:
        download_url = s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": S3_BUCKET, "Key": key},
            ExpiresIn=86400
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate URL: {e}")

    # Return imageRef format compatible with KITTY vision flows
    return SelectResponse(
        imageRef={
            "downloadUrl": download_url,
            "storageUri": f"s3://{S3_BUCKET}/{key}",
            "key": key,
        }
    )


@app.get("/api/images/stats")
def stats():
    """Get queue statistics"""
    return {
        "queued": len(images_queue),
        "started": len(images_queue.started_job_registry),
        "finished": len(images_queue.finished_job_registry),
        "failed": len(images_queue.failed_job_registry),
    }


# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    host = os.getenv("SERVICE_HOST", "127.0.0.1")
    port = int(os.getenv("SERVICE_PORT", "8089"))

    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        log_level="info",
        reload=False  # Set to True for development
    )
