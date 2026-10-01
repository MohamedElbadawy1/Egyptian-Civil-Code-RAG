"""
Confirms the StaticFiles mount at "/" doesn't shadow the explicit API
routes (see the ordering note in api/main.py) and that the frontend
actually loads when present.
"""
import os

os.environ.setdefault("OPENAI_API_KEY", "test-key-not-used")

from fastapi.testclient import TestClient

from agentic_rag.api.main import app

client = TestClient(app)


def test_health_route_not_shadowed_by_static_mount():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_docs_route_not_shadowed_by_static_mount():
    resp = client.get("/docs")
    assert resp.status_code == 200


def test_frontend_served_at_root():
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
