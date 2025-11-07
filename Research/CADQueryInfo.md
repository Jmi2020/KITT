# CAD Fallback on Apple Silicon

## Overview
- Zoo stays primary; CadQuery/OCP is the offline fallback on Mac Studio.
- Prefer prebuilt binaries (conda/pip) to avoid flaky source builds.

## Problem Summary
- `cadquery-ocp` lacks universal wheels; fails on osx-arm64.
- Compiling OpenCascade locally is slow and brittle.
- Need reproducible install paths that don’t break Zoo → MinIO workflows.

## Recommended Approaches

### Option A – MicroMamba / Conda-Forge (Most reliable)
```bash
/bin/bash -c "$(curl -L micro.mamba.pm/install.sh)"
micromamba create -n cq -c conda-forge python=3.11 cadquery ocp -y
micromamba activate cq
python - <<'PY'
import cadquery as cq
result = cq.Workplane('XY').box(40, 40, 10)
print('cadquery OK:', result.val().Volume() > 0)
PY
```
Conda-Forge publishes osx-arm64 wheels for both CadQuery and OCP.

### Option B – pip (binary wheels only)
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip wheel setuptools
pip uninstall -y cadquery-ocp ocp OCP cadquery || true
pip install --only-binary=:all: "ocp>=7.7,<7.8" "cadquery>=2.4,<2.5"
python -c "import cadquery as cq; print('cadquery OK:', cq.Workplane('XY').box(1,1,1))"
```
If pip tries to build from source, tighten version pins or revert to Option A.

### Option C – Containerized CadQuery service
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
Minimal API:
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
    out = f"/data/cube_{size_mm}.step"
    model.val().exportStep(out)
    return {'step': out}
```

## Integration Notes
1. Keep Zoo default; use CadQuery only when offline or for post-processing.
2. Remove `cadquery-ocp`; depend on `cadquery` + `ocp` (conda or pip).
3. Pin versions:
   - `cadquery==2.4.*`
   - `ocp==7.7.*`
   - `python==3.11`
4. Add `/healthz` and STEP smoke tests for the fallback service.

## Temporary Fallback
- Set `CAD_LOCAL_ENABLED=false` to route all workflows to Zoo while local stack stabilizes.

## Future Enhancements
- Cost accounting for cloud CAD.
- Complete UniFi Access integration (pending creds).
- CLI polishing (log streaming, status dashboards).
- Voice capture upgrades (MediaRecorder support).
- IaC automation for remote deployments.

## Offline CAD with Native ARM64 Support
| Software   | License     | ARM64 Support | Notes                                   |
|------------|-------------|---------------|-----------------------------------------|
| FreeCAD    | Open Source | ✅ Native     | Parametric, STEP/IGES support           |
| OpenSCAD   | Open Source | ✅ Universal  | Scripted CAD, CGAL kernel               |
| Blender    | Open Source | ✅ Native     | CAD-adjacent mesh workflows             |
| Fusion 360 | Commercial  | ✅ Native     | Cloud/tethered, hobbyist tier           |
| Shapr3D    | Commercial  | ✅ Native     | Touch-first workflow, STEP/IGES         |
| SolveSpace | Open Source | ⚠️ Nightly    | Universal nightly builds (test first)   |
| Build123d  | Open Source | ⚠️ Workaround | Requires conda/Nix on ARM64             |
| BRL-CAD    | Open Source | ⚠️ Source     | Manual build on ARM64                   |

## References
1. https://github.com/FreeCAD/FreeCAD-Bundle/releases/tag/weekly-builds
2. https://wiki.freecad.org/Download#macOS
3. https://openscad.org/downloads.html
4. https://openscad.org/news/2023/02/19/legacy-releases.html#
5. https://www.blender.org/download/releases/2-93/
6. https://www.blender.org/download/releases/4-0/
7. https://www.autodesk.com/products/fusion-360/blog/apple-silicon/
8. https://forums.autodesk.com/t5/fusion-support-forum/apple-silicon-m3/td/p/12353926
9. https://forums.autodesk.com/t5/fusion-support-forum/is-autodesk-ever-going-to-fix-fusion-360-for-apple/td/p/12513643
10. https://support.shapr3d.com/hc/en-us/articles/4405755373842-Install-Shapr3D-on-macOS
11. https://solvespace.com/download.pl
12. https://solvespace.com/forum.pl?action=viewthread&parent=5892&tt=1731684130
13. https://discourse.nixos.org/t/hoping-to-make-a-aarch64-darwin-flake-for-cadquery-ocp-libclang-dylib-woes/28261
14. https://cadquery.discourse.group/t/build123d-on-apple-silicon/1571/7
15. https://github.com/BRL-CAD/brlcad/issues/743
16. https://forums.autodesk.com/t5/fusion-support-forum/about-offline-mode/td/p/11327824
