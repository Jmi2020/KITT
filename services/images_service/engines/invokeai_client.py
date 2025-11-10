"""
InvokeAI Engine Adapter
Routes generation jobs to InvokeAI server/CLI
"""
import os
import subprocess
import shlex
from typing import Dict, Any
from .util_s3 import S3Store


def run_invokeai_job(p: Dict[str, Any]) -> Dict[str, str]:
    """
    Generate image using InvokeAI CLI and upload to MinIO

    Note: This is a simple CLI-based adapter. For production, consider:
    - Using InvokeAI's REST API if exposed
    - Using InvokeAI's Python SDK directly
    - Creating a custom workflow script
    """
    prompt = p["prompt"].replace('"', '\\"')
    outdir = os.getenv("INVOKE_OUTDIR", "/tmp/invoke_out")
    os.makedirs(outdir, exist_ok=True)

    # Build InvokeAI CLI command
    # Adjust this command based on your InvokeAI version and setup
    cmd = (
        f'invokeai '
        f'--prompt "{prompt}" '
        f'--steps {p.get("steps", 30)} '
        f'--cfg_scale {p.get("cfg", 7.0)} '
        f'--width {p.get("width", 1024)} '
        f'--height {p.get("height", 1024)} '
        f'--outdir {outdir}'
    )

    if "seed" in p and p["seed"] is not None:
        cmd += f' --seed {p["seed"]}'

    # Execute InvokeAI CLI
    print(f"[InvokeAI] Running: {cmd[:100]}...")
    try:
        subprocess.run(shlex.split(cmd), check=True, timeout=600)
    except subprocess.TimeoutExpired:
        raise RuntimeError("InvokeAI generation timed out after 10 minutes")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"InvokeAI failed: {e}")

    # Find newest PNG in output directory
    pngs = sorted([f for f in os.listdir(outdir) if f.endswith(".png")])
    if not pngs:
        raise RuntimeError("InvokeAI did not produce an image in outdir")

    latest = os.path.join(outdir, pngs[-1])

    # Read generated image
    with open(latest, "rb") as f:
        png_bytes = f.read()

    # Upload to MinIO
    s3 = S3Store()
    meta = {
        "engine": "invokeai",
        "request": p,
        "cli_output": latest,
    }
    result = s3.save_png_and_bytes(png_bytes, meta)

    # Cleanup temporary file
    try:
        os.remove(latest)
    except Exception:
        pass

    print(f"[InvokeAI] Image saved: {result['png_key']}")
    return result
