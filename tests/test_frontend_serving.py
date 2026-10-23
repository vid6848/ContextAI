"""Tests for serving the built single-page app alongside the API."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.backend.main import mount_frontend


def _client(dist) -> TestClient:
    application = FastAPI()

    @application.get("/api/v1/ping")
    def ping():
        return {"pong": True}

    mount_frontend(application, dist)
    return TestClient(application)


def _build(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>ContextAI</title><div id=root></div>")
    (dist / "assets" / "index-abc123.js").write_text("console.log('app')")
    (dist / "favicon.svg").write_text("<svg/>")
    (tmp_path / "secret.txt").write_text("do not serve")
    return dist


def test_spa_routes_fall_back_to_index(tmp_path):
    client = _client(_build(tmp_path))
    for path in ("/", "/c/abc123", "/some/deep/link"):
        resp = client.get(path)
        assert resp.status_code == 200
        assert "<title>ContextAI</title>" in resp.text


def test_static_files_and_hashed_assets_are_served(tmp_path):
    client = _client(_build(tmp_path))
    assert client.get("/assets/index-abc123.js").text == "console.log('app')"
    assert client.get("/favicon.svg").text == "<svg/>"


def test_api_paths_are_not_swallowed_by_the_spa(tmp_path):
    client = _client(_build(tmp_path))
    assert client.get("/api/v1/ping").json() == {"pong": True}
    assert client.get("/api/v1/missing").status_code == 404
    assert client.get("/assets/missing.js").status_code == 404


def test_path_traversal_is_blocked(tmp_path):
    client = _client(_build(tmp_path))
    resp = client.get("/..%2Fsecret.txt")
    assert "do not serve" not in resp.text


def test_missing_build_returns_helpful_message(tmp_path):
    client = _client(tmp_path / "nope")
    resp = client.get("/")
    assert resp.status_code == 503
    assert "npm run build" in resp.json()["detail"]
