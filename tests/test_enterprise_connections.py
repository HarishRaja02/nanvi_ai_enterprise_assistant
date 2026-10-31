"""
Comprehensive tests for Enterprise Connections Hub Redesign & Integration Management:
- Service-level management (enable/disable services independently)
- Scope authorization gating (services without granted OAuth scopes cannot be enabled)
- Backend authorization gating for AI Assistant retrieval
- Synchronization configuration & manual sync triggering
- Safe account disconnect and provider OAuth token revocation
- Integration audit logging
"""
import json
import uuid
import pytest
from cryptography.fernet import Fernet

from backend.connections.encryption import CredentialEncryptionService
from backend.connections.manager import ConnectionManager
from backend.connections.registry import get_provider_registry
from backend.connections.schemas import (
    CreateConnectionRequest,
    UpdateServiceRequest,
    UpdateSyncConfigRequest,
)
from backend.connections.services_catalog import (
    PROVIDER_SERVICES,
    resolve_services_for_connection,
    is_service_enabled_for_connection,
)
from backend.security.authorization.rbac import Role
from backend.security.models import UserIdentity


@pytest.fixture
def test_mgr():
    """Create an isolated in-memory ConnectionManager for testing."""
    key = Fernet.generate_key().decode()
    enc = CredentialEncryptionService(master_key=key, key_id="v1")
    reg = get_provider_registry()
    mgr = ConnectionManager(
        encryption_service=enc,
        registry=reg,
        database_url="",
        sqlite_path=":memory:",
        force_sqlite=True,
    )
    return mgr


@pytest.fixture
def admin_user():
    return UserIdentity(
        subject="admin-usr-100",
        issuer="internal",
        email="admin@company.com",
        tenant_id="enterprise-tenant",
        department="IT",
        roles=frozenset({Role.ADMIN, Role.SUPERIOR}),
    )


def insert_oauth_connection(
    mgr: ConnectionManager,
    user: UserIdentity,
    provider: str = "google",
    display_name: str = "Google Workspace (Enterprise)",
    account_identifier: str = "corp@example.com",
    scope_level: str = "organization",
    granted_scopes: list[str] | None = None,
) -> str:
    """Helper to insert an OAuth connection row for testing."""
    conn_id = str(uuid.uuid4())
    scopes = granted_scopes or [
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/drive.metadata.readonly",
        "https://www.googleapis.com/auth/documents.readonly",
    ]
    enc_creds = mgr._encryption.encrypt(
        json.dumps({"access_token": "mock-access-token", "refresh_token": "mock-refresh"}).encode()
    )

    sqlite_sql = """
        INSERT INTO connections (
            id, tenant_id, owner_user_id, provider, display_name, account_identifier,
            scope_level, status, credential_type, encrypted_credentials, metadata_safe,
            granted_scopes, services_config, sync_config, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'));
    """
    mgr._execute(
        "",
        sqlite_sql,
        (
            conn_id,
            user.tenant_id or "enterprise-tenant",
            user.subject,
            provider,
            display_name,
            account_identifier,
            scope_level,
            "CONNECTED",
            "oauth2",
            enc_creds,
            json.dumps({"account_identifier": account_identifier}),
            json.dumps(scopes),
            json.dumps({}),
            json.dumps({"auto_sync": True, "frequency": "1h"}),
        ),
    )
    return conn_id


def test_services_catalog_scope_resolution():
    """Verify that services are marked UNAUTHORIZED if required OAuth scopes are absent."""
    granted_scopes = ["https://www.googleapis.com/auth/gmail.readonly"]
    resolved = resolve_services_for_connection("google", granted_scopes_raw=granted_scopes)

    gmail_service = next(s for s in resolved if s.id == "gmail")
    drive_service = next(s for s in resolved if s.id == "drive")
    sheets_service = next(s for s in resolved if s.id == "sheets")

    assert gmail_service.status == "ENABLED"
    assert gmail_service.enabled is True

    # Drive and Sheets should require re-auth because drive.readonly / spreadsheets scopes are absent
    assert drive_service.status == "UNAUTHORIZED"
    assert drive_service.enabled is False
    assert sheets_service.status == "UNAUTHORIZED"
    assert sheets_service.enabled is False


def test_service_level_enable_disable_lifecycle(test_mgr, admin_user):
    """Verify enabling and disabling individual services without disconnecting account."""
    conn_id = insert_oauth_connection(test_mgr, admin_user)

    # Initially both gmail and drive should be authorized and enabled
    conn = test_mgr.get_connection(conn_id, admin_user)
    gmail = next(s for s in conn.services if s.id == "gmail")
    drive = next(s for s in conn.services if s.id == "drive")
    assert gmail.enabled is True
    assert drive.enabled is True

    # Administrator disables Google Drive for AI retrieval
    updated_conn = test_mgr.update_service(
        conn_id, "drive", admin_user, UpdateServiceRequest(enabled=False)
    )
    updated_drive = next(s for s in updated_conn.services if s.id == "drive")
    assert updated_drive.enabled is False

    # Verify backend authorization resolver blocks drive
    full_conn = test_mgr.get_connection(conn_id, admin_user)
    row_data = {
        "status": full_conn.status,
        "provider": full_conn.provider,
        "granted_scopes": full_conn.granted_scopes,
        "services_config": {"drive": {"enabled": False}},
    }
    assert is_service_enabled_for_connection(row_data, "gmail") is True
    assert is_service_enabled_for_connection(row_data, "drive") is False

    # Attempting to enable an unauthorized service (e.g. calendar without calendar scope)
    with pytest.raises(Exception) as excinfo:
        test_mgr.update_service(
            conn_id, "calendar", admin_user, UpdateServiceRequest(enabled=True)
        )
    assert "Cannot enable service" in str(excinfo.value) or "missing required scopes" in str(excinfo.value)

    # Re-enable drive
    re_enabled_conn = test_mgr.update_service(
        conn_id, "drive", admin_user, UpdateServiceRequest(enabled=True)
    )
    re_enabled_drive = next(s for s in re_enabled_conn.services if s.id == "drive")
    assert re_enabled_drive.enabled is True

    # Audit log should record SERVICE_DISABLED and SERVICE_ENABLED events
    audit_events = test_mgr.list_connection_audit(conn_id, admin_user)
    event_types = [e["event_type"] for e in audit_events]
    assert "SERVICE_DISABLED" in event_types
    assert "SERVICE_ENABLED" in event_types


def test_sync_configuration_and_trigger(test_mgr, admin_user):
    """Verify updating sync intervals and triggering on-demand sync."""
    conn_id = insert_oauth_connection(test_mgr, admin_user)

    # Update sync config
    updated_conn = test_mgr.update_sync_config(
        conn_id, admin_user, UpdateSyncConfigRequest(auto_sync=True, frequency="15m")
    )
    assert updated_conn.auto_sync is True
    assert updated_conn.sync_frequency == "15m"

    # Trigger manual sync
    sync_res = test_mgr.sync_connection(conn_id, admin_user)
    assert sync_res.ok is True
    assert len(sync_res.synced_services) > 0
    assert sync_res.synced_at is not None

    # Check that last_synced_at is recorded
    reloaded = test_mgr.get_connection(conn_id, admin_user)
    assert reloaded.last_synced_at is not None


def test_safe_revocation_and_disconnect(test_mgr, admin_user):
    """Verify safe account disconnect and OAuth revocation."""
    conn_id = insert_oauth_connection(test_mgr, admin_user)

    # Revoke connection
    revoke_conn = test_mgr.revoke_connection(conn_id, admin_user)
    assert revoke_conn.status == "DISCONNECTED"

    # Status should be DISCONNECTED and revoked in audit
    reloaded = test_mgr.get_connection(conn_id, admin_user)
    assert reloaded.status == "DISCONNECTED"

    # Audit trail verification
    audit = test_mgr.list_connection_audit(conn_id, admin_user)
    types = [e["event_type"] for e in audit]
    assert "AUTHORIZATION_REVOKED" in types
