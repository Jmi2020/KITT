"""
KITTY Images Service - Diffusers Worker
Headless image generation using Diffusers library with Apple Silicon MPS support
"""
from __future__ import annotations
import io
import os
import json
import time
import uuid
from dataclasses import dataclass
from typing import Optional, Dict, Any

import torch
from PIL import Image
import boto3

from diffusers import (
    StableDiffusionXLPipeline,
    StableDiffusionXLImg2ImgPipeline,
    StableDiffusionPipeline,
    EulerAncestralDiscreteScheduler,
)


@dataclass
class GenParams:
    """Generation parameters for text-to-image"""
    prompt: str
    width: int = 1024
    height: int = 1024
    steps: int = 30
    cfg: float = 7.0
    seed: Optional[int] = None
    model: str = "sdxl_base"  # see models.yaml
    refiner: Optional[str] = None


class S3Store:
    """MinIO/S3 storage handler for generated images and metadata"""

    def __init__(self):
        self.client = boto3.client(
            "s3",
            endpoint_url=os.getenv("S3_ENDPOINT_URL"),
            aws_access_key_id=os.getenv("S3_ACCESS_KEY"),
            aws_secret_access_key=os.getenv("S3_SECRET_KEY"),
            region_name=os.getenv("S3_REGION"),
        )
        self.bucket = os.getenv("S3_BUCKET")
        self.prefix = os.getenv("S3_PREFIX", "images/")

    def save_png_and_meta(self, im: Image.Image, meta: Dict[str, Any]) -> Dict[str, str]:
        """Save PNG image and JSON metadata to S3, return keys"""
        ts = time.strftime("%Y%m%d_%H%M%S")
        uid = uuid.uuid4().hex[:8]
        base = f"{self.prefix}{ts}_{uid}"
        png_key = f"{base}.png"
        meta_key = f"{base}.json"

        # Upload PNG
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        buf.seek(0)
        self.client.put_object(
            Bucket=self.bucket,
            Key=png_key,
            Body=buf.getvalue(),
            ContentType="image/png"
        )

        # Upload metadata
        self.client.put_object(
            Bucket=self.bucket,
            Key=meta_key,
            Body=json.dumps(meta, indent=2).encode("utf-8"),
            ContentType="application/json"
        )

        return {"png_key": png_key, "meta_key": meta_key}


class DiffusersWorker:
    """Headless Diffusers worker with MPS acceleration for Apple Silicon"""

    def __init__(self, models_yaml: str):
        import yaml
        with open(models_yaml, "r") as f:
            self.models = yaml.safe_load(f)

        # Use MPS (Metal Performance Shaders) on Apple Silicon
        self.device = torch.device("mps") if torch.backends.mps.is_available() else torch.device("cpu")
        print(f"[DiffusersWorker] Using device: {self.device}")

        self.s3 = S3Store()

        # Simple model caches (load on demand)
        self._sdxl = {}
        self._sd15 = {}

    def _load_sdxl(self, name: str):
        """Load SDXL pipeline (lazy loading with cache)"""
        if name in self._sdxl:
            return self._sdxl[name]

        base_path = self.models[name]
        print(f"[DiffusersWorker] Loading SDXL model: {name} from {base_path}")

        pipe = StableDiffusionXLPipeline.from_pretrained(
            base_path,
            torch_dtype=torch.float32,  # Use float32 on MPS for stability
            variant=None,
            use_safetensors=True
        )
        pipe.to(self.device)

        # Memory optimization for MPS
        pipe.enable_attention_slicing("max")

        self._sdxl[name] = pipe
        print(f"[DiffusersWorker] Model {name} loaded successfully")
        return pipe

    def _load_sd15(self, name: str):
        """Load SD 1.5 pipeline (lazy loading with cache)"""
        if name in self._sd15:
            return self._sd15[name]

        base_path = self.models[name]
        print(f"[DiffusersWorker] Loading SD1.5 model: {name} from {base_path}")

        pipe = StableDiffusionPipeline.from_pretrained(
            base_path,
            torch_dtype=torch.float32,  # Use float32 on MPS for stability
            safety_checker=None,
            feature_extractor=None
        )
        pipe.scheduler = EulerAncestralDiscreteScheduler.from_config(pipe.scheduler.config)
        pipe.to(self.device)
        pipe.enable_attention_slicing("max")

        self._sd15[name] = pipe
        print(f"[DiffusersWorker] Model {name} loaded successfully")
        return pipe

    def generate(self, p: GenParams) -> Dict[str, str]:
        """Generate image from parameters and upload to S3"""
        print(f"[DiffusersWorker] Generating image: {p.prompt[:60]}...")

        # Setup generator for reproducibility
        g = None
        if p.seed is not None:
            g = torch.Generator(device=self.device).manual_seed(int(p.seed))

        # Generate based on model type
        if p.model.startswith("sdxl"):
            pipe = self._load_sdxl(p.model)
            image = pipe(
                prompt=p.prompt,
                num_inference_steps=p.steps,
                guidance_scale=p.cfg,
                width=p.width,
                height=p.height,
                generator=g
            ).images[0]

            # Optional refiner pass for extra quality
            if p.refiner:
                print(f"[DiffusersWorker] Applying refiner: {p.refiner}")
                ref_pipe = self._load_sdxl(p.refiner)
                # Convert base to img2img for refiner
                ref_pipe_img2img = StableDiffusionXLImg2ImgPipeline(
                    vae=ref_pipe.vae,
                    text_encoder=ref_pipe.text_encoder,
                    text_encoder_2=ref_pipe.text_encoder_2,
                    tokenizer=ref_pipe.tokenizer,
                    tokenizer_2=ref_pipe.tokenizer_2,
                    unet=ref_pipe.unet,
                    scheduler=ref_pipe.scheduler,
                )
                ref_pipe_img2img.to(self.device)
                image = ref_pipe_img2img(
                    prompt=p.prompt,
                    num_inference_steps=10,
                    guidance_scale=min(5.0, p.cfg),
                    image=image
                ).images[0]

        else:
            # SD 1.5 or other non-XL models
            pipe = self._load_sd15(p.model)
            image = pipe(
                prompt=p.prompt,
                num_inference_steps=p.steps,
                guidance_scale=p.cfg,
                width=p.width,
                height=p.height,
                generator=g
            ).images[0]

        # Prepare metadata
        meta = {
            "engine": "diffusers",
            "request": {
                "prompt": p.prompt,
                "width": p.width,
                "height": p.height,
                "steps": p.steps,
                "cfg": p.cfg,
                "seed": p.seed,
                "model": p.model,
                "refiner": p.refiner,
            },
            "device": str(self.device),
            "library": "diffusers",
            "timestamp": time.time(),
        }

        # Upload to S3/MinIO
        print(f"[DiffusersWorker] Uploading to S3...")
        result = self.s3.save_png_and_meta(image, meta)
        print(f"[DiffusersWorker] Image saved: {result['png_key']}")

        return result


# ============================================================================
# RQ Worker Entry Point
# ============================================================================

_worker_singleton = None


def run_diffusers_job(params: Dict[str, Any]) -> Dict[str, str]:
    """
    Entry point for RQ worker jobs
    Initializes worker on first call (singleton pattern)
    """
    global _worker_singleton

    if _worker_singleton is None:
        models_yaml = os.getenv("MODELS_YAML", "/Users/Shared/KITTY/models/models.yaml")
        print(f"[run_diffusers_job] Initializing worker with models: {models_yaml}")
        _worker_singleton = DiffusersWorker(models_yaml)

    # Convert dict params to GenParams dataclass
    gp = GenParams(**params)
    return _worker_singleton.generate(gp)
