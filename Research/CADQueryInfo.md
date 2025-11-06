# CADQuery / OCP on Apple Silicon

This note captures supported setups for KITTY's local CAD fallback on a Mac Studio (Apple Silicon). The goal is to keep Zoo (online) as the default parametric path while retaining CadQuery as an offline fallback.

## Problem Summary

- `cadquery-ocp` often ships x86-only binaries; installing it on macOS arm64 fails with missing wheels.
- Building OpenCascade (OCP) locally is slow and brittle.
- We need a reproducible path that aligns with the "offline fallback" policy, without disrupting the Zoo → MinIO workflow.

## Recommended Approaches

### Option A: MicroMamba / Conda-Forge (Most Reliable)

```bash
/bin/bash -c "$(curl -L micro.mamba.pm/install.sh)"
micromamba create -n cq -c conda-forge python=3.11 cadquery ocp -y
micromamba activate cq
python - <<'PY'
import cadquery as cq
r = cq.Workplane('XY').box(40, 40, 10)
print('cadquery OK:', r.val().Volume() > 0)
PY
```

Why it works: Conda-Forge provides prebuilt osx-arm64 wheels for CadQuery + OCP, so we avoid manual compilation.

### Option B: Pure pip (force binary wheels only)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip wheel setuptools
pip uninstall -y cadquery-ocp ocp OCP cadquery
pip install --only-binary=:all: "ocp>=7.7,<7.8" "cadquery>=2.4,<2.5"
python -c "import cadquery as cq; print('cadquery OK:', cq.Workplane('XY').box(1,1,1))"
```

If pip attempts to build from source, tighten versions or switch back to Option A.

### Option C: Containerised CadQuery Service

Run CadQuery inside a dedicated container (optional if you prefer to keep the host clean).

```yaml
services:
  cad-cq:
    image: mambaorg/micromamba:1.5.8
    platform: linux/arm64
    command:
      - /bin/bash
      - -lc
      - |
          micromamba install -y -n base -c conda-forge python=3.11 cadquery ocp uvicorn fastapi
          uvicorn app:app --host 0.0.0.0 --port 8000
    volumes:
      - ./services/cad-cq:/opt/app
      - ./data/cad:/data
    working_dir: /opt/app
    ports:
      - "8000:8000"
```

Minimal `app.py` for the service:

```python
from fastapi import FastAPI
import cadquery as cq

app = FastAPI()

@app.get('/healthz')
def healthz():
    return {'ok': True}

@app.post('/cube/{size_mm}')
def cube(size_mm: float):
    model = cq.Workplane('XY').box(size_mm, size_mm, size_mm)
    output = f"/data/cube_{size_mm}.step"
    model.val().exportStep(output)
    return {'step': output}
```

## KITTY Integration Notes

1. Zoo remains the default for parametric CAD. Use CadQuery only when offline or for post-processing.
2. Remove `cadquery-ocp` from the dependency graph; depend on `cadquery` + `ocp` directly (via Conda-Forge or pip).
3. Example version pins:
   - `cadquery==2.4.*`
   - `ocp==7.7.*`
   - `python==3.11`
4. Add health checks for the fallback (`/healthz`, simple STEP generation smoke test).

## Temporary Fallback

- Set `CAD_LOCAL_ENABLED=false` (or equivalent) and route all jobs to Zoo if local CadQuery is not ready.
- Re-enable once one of the solutions above is stable.

## Future Enhancements

- Real-time cost accounting for cloud routes.
- Completing UniFi Access integration when credentials are available.
- CLI improvements (log streaming, status dashboard).
- Browser MediaRecorder support for voice capture.
- Infrastructure-as-code automation (Terraform/Ansible) for remote deployments.
