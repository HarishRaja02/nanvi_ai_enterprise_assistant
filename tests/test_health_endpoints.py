"""Tests for real health endpoints (Item 10).

Verifies:
1. /api/health/live is trivial with no external dependencies (returns 200).
2. /api/health/ready returns 200 when all dependencies are ready.
3. /api/health/ready returns 503 with per-dependency breakdown when a dependency fails.
"""
from __future__ import annotations

import dataclasses
import pytest
from fastapi.testclient import TestClient

import backend.core.config as config_mod
from backend.main import app


def patch_settings(monkeypatch: pytest.MonkeyPatch, **kwargs):
    new_settings = dataclasses.replace(config_mod.settings, **kwargs)
    monkeypatch.setattr(config_mod, "settings", new_settings)
    import backend.api.routes as routes_mod
    monkeypatch.setattr(routes_mod, "settings", new_settings)
    return new_settings


@pytest.fixture
def client():
    return TestClient(app)


def test_health_live_endpoint(client: TestClient):
    resp = client.get("/api/health/live")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_health_ready_development_mode(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    patch_settings(
        monkeypatch,
        app_mode="development",
        database_url="",
        supabase_database_url="",
        redis_url="",
        groq_api_key="test-key",
    )
    resp = client.get("/api/health/ready")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ready"
    assert "dependencies" in data
    assert data["dependencies"]["database"]["status"] == "up"
    assert data["dependencies"]["database"]["backend"] == "sqlite"
    assert data["dependencies"]["storage"]["status"] == "up"


def test_health_ready_production_failure_without_db(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    patch_settings(
        monkeypatch,
        app_mode="production",
        database_url="",
        supabase_database_url="",
        redis_url="",
        groq_api_key="test-key",
    )
    resp = client.get("/api/health/ready")
    assert resp.status_code == 503
    data = resp.json()
    assert data["status"] == "unavailable"
    assert data["dependencies"]["database"]["status"] == "down"
    assert "No PostgreSQL database URL configured" in data["dependencies"]["database"]["error"]


def test_health_ready_production_failure_without_llm(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    patch_settings(
        monkeypatch,
        app_mode="production",
        database_url="",
        supabase_database_url="",
        redis_url="",
        groq_api_key="",
    )
    resp = client.get("/api/health/ready")
    assert resp.status_code == 503
    data = resp.json()
    assert data["status"] == "unavailable"
    assert data["dependencies"]["llm"]["status"] == "down"
