from __future__ import annotations

from datetime import datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain.routes import projects as routes


class DummyProject:
    def __init__(self):
        self.id = "proj-1"
        self.conversation_id = "conv-1"
        self.title = "Bracket"
        self.summary = "Wall mount bracket"
        self.artifacts = [
            {
                "provider": "tripo",
                "artifactType": "stl",
                "location": "/api/cad/artifacts/stl/abc.stl",
                "metadata": {"glb_location": "/api/cad/artifacts/glb/abc.glb"},
            }
        ]
        self.project_metadata = {"printer": "bambu"}
        self.updated_at = datetime(2025, 1, 1, 12, 0, 0)


def build_app() -> TestClient:
    app = FastAPI()
    app.include_router(routes.router)
    return TestClient(app)


def test_list_projects(monkeypatch):
    dummy = DummyProject()
    monkeypatch.setattr(routes, "list_projects", lambda *args, **kwargs: [dummy])
    client = build_app()

    resp = client.get("/api/projects")
    assert resp.status_code == 200
    data = resp.json()[0]
    assert data["projectId"] == dummy.id
    assert data["artifacts"][0]["artifactType"] == "stl"
    assert data["metadata"]["printer"] == "bambu"


def test_get_project_404(monkeypatch):
    monkeypatch.setattr(routes, "get_project", lambda project_id: None)
    client = build_app()
    resp = client.get("/api/projects/missing")
    assert resp.status_code == 404


def test_delete_project(monkeypatch):
    monkeypatch.setattr(routes, "soft_delete_project", lambda project_id: True)
    client = build_app()
    resp = client.delete("/api/projects/proj-1")
    assert resp.status_code == 204


def test_append_artifacts(monkeypatch):
    dummy = DummyProject()
    monkeypatch.setattr(routes, "append_artifacts", lambda project_id, artifacts: dummy)
    client = build_app()
    resp = client.post(
        "/api/projects/proj-1/artifacts",
        json={
            "artifacts": [
                {
                    "provider": "tripo",
                    "artifactType": "glb",
                    "location": "/api/cad/artifacts/glb/abc.glb",
                    "metadata": {},
                }
            ]
        },
    )
    assert resp.status_code == 200
    assert resp.json()["projectId"] == dummy.id
