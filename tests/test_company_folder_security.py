"""Tests for company-folder security hardening:
- PUT /settings/company-folder and POST /settings/company-folder/browse restricted to admin roles only
- Path confinement to approved storage roots (symlink and .. resolution)
- Rejection of paths outside root
- Never enumerate /, C:\, /etc, etc.
"""
import dataclasses
import os
import tempfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.security.dependencies import get_current_user
from backend.security.models import UserIdentity
from backend.security.authorization.rbac import Role
import backend.core.config as config_mod
import backend.api.settings_routes as settings_routes_mod


def patch_settings(monkeypatch: pytest.MonkeyPatch, **kwargs):
    new_settings = dataclasses.replace(config_mod.settings, **kwargs)
    monkeypatch.setattr(config_mod, "settings", new_settings)
    if hasattr(settings_routes_mod, "settings"):
        monkeypatch.setattr(settings_routes_mod, "settings", new_settings)
    return new_settings


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def regular_employee():
    return UserIdentity(
        subject="emp-1",
        issuer="test",
        email="emp@company.com",
        tenant_id="enterprise-tenant",
        department="Engineering",
        roles=frozenset({Role.EMPLOYEE}),
    )


@pytest.fixture
def it_admin():
    return UserIdentity(
        subject="admin-1",
        issuer="test",
        email="admin@company.com",
        tenant_id="enterprise-tenant",
        department="IT",
        roles=frozenset({Role.IT_ADMIN}),
    )


def test_regular_user_blocked_from_update_and_browse(client, regular_employee):
    """Non-admin roles must receive 403 Forbidden for both update and browse."""
    app.dependency_overrides[get_current_user] = lambda: regular_employee
    try:
        resp_put = client.put("/api/settings/company-folder", json={"path": "/some/path"})
        assert resp_put.status_code == 403
        assert "Admin role required" in resp_put.json()["detail"]

        resp_browse = client.post("/api/settings/company-folder/browse", json={"path": ""})
        assert resp_browse.status_code == 403
        assert "Admin role required" in resp_browse.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_browse_empty_path_returns_configured_roots_only(client, monkeypatch, it_admin):
    """Empty path in browse must return only configured approved roots, never C:\\ or /."""
    with tempfile.TemporaryDirectory() as tmp1, tempfile.TemporaryDirectory() as tmp2:
        patch_settings(
            monkeypatch,
            company_file_roots=(("Finance", tmp1), ("Contracts", tmp2)),
        )

        app.dependency_overrides[get_current_user] = lambda: it_admin
        try:
            resp = client.post("/api/settings/company-folder/browse", json={"path": ""})
            assert resp.status_code == 200
            data = resp.json()
            assert data["path"] == ""
            entry_names = [e["name"] for e in data["entries"]]
            assert "Finance" in entry_names
            assert "Contracts" in entry_names
            # Must NOT enumerate drive roots or system root
            assert "C:\\" not in entry_names
            assert "/" not in entry_names
        finally:
            app.dependency_overrides.pop(get_current_user, None)


def test_path_traversal_and_outside_root_rejected(client, monkeypatch, it_admin):
    """Paths outside allowed root or using .. must be rejected with 403."""
    with tempfile.TemporaryDirectory() as tmp_root:
        sub_dir = Path(tmp_root) / "allowed_sub"
        sub_dir.mkdir()

        patch_settings(
            monkeypatch,
            company_file_roots=(("Data", str(sub_dir)),),
        )

        app.dependency_overrides[get_current_user] = lambda: it_admin
        try:
            # Attempt to traverse up out of the allowed sub_dir
            traversal_path = str(sub_dir / ".." / "..")
            resp_browse = client.post("/api/settings/company-folder/browse", json={"path": traversal_path})
            assert resp_browse.status_code == 403
            assert "outside approved storage roots" in resp_browse.json()["detail"]

            # Attempt to browse system root / or C:\Windows
            system_path = "C:\\Windows" if os.name == "nt" else "/etc"
            resp_browse_sys = client.post("/api/settings/company-folder/browse", json={"path": system_path})
            assert resp_browse_sys.status_code == 403
            assert "outside approved storage roots" in resp_browse_sys.json()["detail"]

            # Attempt to update to an unapproved folder
            resp_put = client.put("/api/settings/company-folder", json={"path": system_path})
            assert resp_put.status_code == 403
            assert "outside approved storage roots" in resp_put.json()["detail"]
        finally:
            app.dependency_overrides.pop(get_current_user, None)


def test_valid_admin_update_within_root_succeeds(client, monkeypatch, it_admin):
    """Admin updating company folder to a path within approved roots succeeds."""
    with tempfile.TemporaryDirectory() as tmp_root:
        valid_dir = Path(tmp_root) / "reports"
        valid_dir.mkdir()

        patch_settings(
            monkeypatch,
            company_file_roots=(("Reports", str(tmp_root)),),
        )

        app.dependency_overrides[get_current_user] = lambda: it_admin
        try:
            resp = client.put("/api/settings/company-folder", json={"path": str(valid_dir)})
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ok"
            assert data["exists"] is True
        finally:
            app.dependency_overrides.pop(get_current_user, None)
