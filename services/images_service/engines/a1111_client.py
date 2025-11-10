"""
Automatic1111 (AUTOMATIC1111 Stable Diffusion WebUI) Engine Adapter
Routes generation jobs to A1111 REST API
"""
import os
import base64
import requests
from typing import Dict, Any
from .util_s3 import S3Store


def run_a1111_job(p: Dict[str, Any]) -> Dict[str, str]:
    """
    Generate image using Automatic1111 WebUI API and upload to MinIO

    A1111 must be running with --api flag enabled
    Default: http://127.0.0.1:7860
    """
    base_url = os.getenv("A1111_BASE_URL", "http://127.0.0.1:7860")

    # Build A1111 API payload
    payload = {
        "prompt": p["prompt"],
        "steps": p.get("steps", 30),
        "cfg_scale": p.get("cfg", 7.0),
        "width": p.get("width", 1024),
        "height": p.get("height", 1024),
        "sampler_name": "Euler a",  # Good default
        "batch_size": 1,
        "n_iter": 1,
    }

    # Add seed if specified
    if "seed" in p and p["seed"] is not None:
        payload["seed"] = int(p["seed"])
    else:
        payload["seed"] = -1  # Random seed

    # Add negative prompt if specified
    if "negative_prompt" in p:
        payload["negative_prompt"] = p["negative_prompt"]

    print(f"[A1111] Generating with prompt: {p['prompt'][:60]}...")

    # Call A1111 txt2img API
    try:
        response = requests.post(
            f"{base_url}/sdapi/v1/txt2img",
            json=payload,
            timeout=600  # 10 minutes
        )
        response.raise_for_status()
    except requests.RequestException as e:
        raise RuntimeError(f"A1111 API request failed: {e}")

    data = response.json()

    # Extract base64 image (A1111 returns images as base64)
    if not data.get("images"):
        raise RuntimeError("A1111 did not return any images")

    # Decode base64 image
    b64_image = data["images"][0]
    # Handle data URI format (data:image/png;base64,...)
    if "," in b64_image:
        b64_image = b64_image.split(",", 1)[-1]

    png_bytes = base64.b64decode(b64_image)

    # Upload to MinIO
    s3 = S3Store()
    meta = {
        "engine": "a1111",
        "request": p,
        "a1111_parameters": data.get("parameters", {}),
        "a1111_info": data.get("info", ""),
    }
    result = s3.save_png_and_bytes(png_bytes, meta)

    print(f"[A1111] Image saved: {result['png_key']}")
    return result
