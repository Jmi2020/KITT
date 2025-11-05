from pathlib import Path
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT / "services/gateway/src"))

from gateway.middleware.remote_mode import RemoteModeMiddleware  # noqa: E402


app = FastAPI()
app.add_middleware(RemoteModeMiddleware)


@app.post("/mutate")
async def mutate():
    return {"status": "ok"}


@app.get("/mutate")
async def read_mutate():
    return {"status": "ok"}


def test_remote_mode_blocks_mutation():
    client = TestClient(app)
    response = client.post("/mutate", headers={"X-Remote-Mode": "read-only"})
    assert response.status_code == 403
    assert response.text == "Remote mode is read-only"


def test_remote_mode_allows_safe_method():
    client = TestClient(app)
    response = client.get("/mutate", headers={"X-Remote-Mode": "read-only"})
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
