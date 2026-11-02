import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.security.dependencies import get_current_user
from backend.security.models import UserIdentity
from backend.security.authorization.rbac import Role
from backend.logs.store import UserLogStore, get_user_log_store


@pytest.fixture
def test_log_store(tmp_path):
    store = UserLogStore(sqlite_path=tmp_path / "routes_test_logs.sqlite3")
    store.record_log(
        user_id="emp_99",
        user_name="Test User",
        user_role="Employee",
        query="What is the company leave policy?",
        answer="Employees are entitled to 20 days paid leave per annum.",
    )
    return store


def test_superior_can_access_logs(test_log_store):
    superior_user = UserIdentity(
        subject="ceo-user",
        issuer="test",
        roles=frozenset({Role.SUPERIOR}),
        tenant_id="enterprise-tenant",
    )

    app.dependency_overrides[get_current_user] = lambda: superior_user
    app.dependency_overrides[get_user_log_store] = lambda: test_log_store

    try:
        client = TestClient(app)
        dates_res = client.get("/api/logs/dates")
        assert dates_res.status_code == 200
        data = dates_res.json()
        assert "dates" in data
        assert len(data["dates"]) >= 1

        logs_res = client.get("/api/logs")
        assert logs_res.status_code == 200
        logs_data = logs_res.json()
        assert logs_data["total"] >= 1
        assert logs_data["logs"][0]["user_id"] == "emp_99"
    finally:
        app.dependency_overrides.clear()


def test_admin_can_access_logs(test_log_store):
    admin_user = UserIdentity(
        subject="admin",
        issuer="test",
        roles=frozenset({Role.ADMIN}),
        tenant_id="enterprise-tenant",
    )

    app.dependency_overrides[get_current_user] = lambda: admin_user
    app.dependency_overrides[get_user_log_store] = lambda: test_log_store

    try:
        client = TestClient(app)
        logs_res = client.get("/api/logs")
        assert logs_res.status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_employee_cannot_access_logs(test_log_store):
    employee_user = UserIdentity(
        subject="emp-1",
        issuer="test",
        roles=frozenset({Role.EMPLOYEE}),
        tenant_id="enterprise-tenant",
    )

    app.dependency_overrides[get_current_user] = lambda: employee_user
    app.dependency_overrides[get_user_log_store] = lambda: test_log_store

    try:
        client = TestClient(app)
        logs_res = client.get("/api/logs")
        assert logs_res.status_code == 403
        assert "Access restricted strictly to Superior and Admin" in logs_res.json()["detail"]

        dates_res = client.get("/api/logs/dates")
        assert dates_res.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_supervisor_cannot_access_logs(test_log_store):
    supervisor_user = UserIdentity(
        subject="sup-1",
        issuer="test",
        roles=frozenset({Role.SUPERVISOR}),
        tenant_id="enterprise-tenant",
    )

    app.dependency_overrides[get_current_user] = lambda: supervisor_user
    app.dependency_overrides[get_user_log_store] = lambda: test_log_store

    try:
        client = TestClient(app)
        logs_res = client.get("/api/logs")
        assert logs_res.status_code == 403
    finally:
        app.dependency_overrides.clear()
