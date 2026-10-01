"""Comprehensive test suite for the Universal Connections Hub."""
import tempfile
import pytest
from cryptography.fernet import Fernet

from backend.connections.base import (
    ConnectionError,
    ConnectionStatus,
    InvalidCredentials,
    OAuthDenied,
    OAuthExpired,
    SSRFBlocked,
    ScopeLevel,
)
from backend.connections.encryption import CredentialEncryptionService
from backend.connections.manager import ConnectionManager
from backend.connections.registry import ProviderRegistry, get_provider_registry
from backend.connections.schemas import (
    CreateConnectionRequest,
    UpdateConnectionRequest,
    ValidateConnectionRequest,
)
from backend.connections.ssrf import validate_url_ssrf
from backend.security.authorization.rbac import Role
from backend.security.models import UserIdentity


@pytest.fixture
def test_manager():
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
def alice():
    return UserIdentity(
        subject="alice-user-1",
        issuer="internal",
        email="alice@company.com",
        tenant_id="enterprise-tenant",
        department="Engineering",
        roles=frozenset({Role.EMPLOYEE}),
    )


@pytest.fixture
def bob():
    return UserIdentity(
        subject="bob-user-2",
        issuer="internal",
        email="bob@company.com",
        tenant_id="enterprise-tenant",
        department="Finance",
        roles=frozenset({Role.EMPLOYEE}),
    )


@pytest.fixture
def it_admin():
    return UserIdentity(
        subject="admin-user-3",
        issuer="internal",
        email="admin@company.com",
        tenant_id="enterprise-tenant",
        department="IT",
        roles=frozenset({Role.IT_ADMIN}),
    )


@pytest.fixture
def eve_foreign_tenant():
    return UserIdentity(
        subject="eve-attacker",
        issuer="internal",
        email="eve@othercorp.com",
        tenant_id="foreign-tenant-xyz",
        department="Security",
        roles=frozenset({Role.CEO}),
    )


# ── Catalog & Provider Tests ──────────────────────────────────

def test_catalog_lists_all_providers():
    reg = get_provider_registry()
    all_providers = reg.list_all()

    # Must contain at least the 6 built-in providers + catalog-only entries
    assert len(all_providers) >= 140
    ids = {p.id for p in all_providers}
    assert "local_files" in ids
    assert "postgresql" in ids
    assert "custom_api" in ids
    assert "google" in ids
    assert "github" in ids
    assert "supabase" in ids

    # Code-backed providers should have configuration_schema or auth_type
    local = next(p for p in all_providers if p.id == "local_files")
    assert local.available is True
    assert "path" in local.configuration_schema["properties"]


# ── CRUD & Scope Tests ────────────────────────────────────────

def test_local_files_crud_and_isolation(test_manager, alice, bob, eve_foreign_tenant):
    with tempfile.TemporaryDirectory() as tmp_dir:
        req = CreateConnectionRequest(
            provider="local_files",
            display_name="Alice's Local Docs",
            scope_level="user",
            config={"path": tmp_dir, "read_only": True},
        )
        conn = test_manager.create_connection(alice, req)
        assert conn.id is not None
        assert conn.display_name == "Alice's Local Docs"
        assert conn.status == ConnectionStatus.CONNECTED.value
        assert conn.scope_level == "user"
        # Secret/sensitive credentials must NOT be exposed in ConnectionPublic
        assert not hasattr(conn, "encrypted_credentials")
        assert not hasattr(conn, "credentials")

        # Alice can view and list her connection
        alice_conns = test_manager.list_connections(alice)
        assert len(alice_conns) == 1
        assert alice_conns[0].id == conn.id

        # Bob cannot see Alice's personal connection
        bob_conns = test_manager.list_connections(bob)
        assert len(bob_conns) == 0

        # Bob accessing Alice's connection directly gets 404/ConnectionError (IDOR protection)
        with pytest.raises(ConnectionError) as exc_info:
            test_manager.get_connection(conn.id, bob)
        assert "not found" in str(exc_info.value).lower()

        # Foreign tenant user also gets 404/ConnectionError
        with pytest.raises(ConnectionError) as exc_info:
            test_manager.get_connection(conn.id, eve_foreign_tenant)
        assert "not found" in str(exc_info.value).lower()

        # Alice can update connection name
        updated = test_manager.update_connection(
            conn.id, alice, UpdateConnectionRequest(display_name="Alice's Renamed Docs")
        )
        assert updated.display_name == "Alice's Renamed Docs"

        # Alice can test connection
        test_res = test_manager.test_connection(conn.id, alice)
        assert test_res.ok is True

        # Alice can delete her connection
        deleted = test_manager.delete_connection(conn.id, alice)
        assert deleted is True

        # After delete, it is soft-deleted and not found
        with pytest.raises(ConnectionError):
            test_manager.get_connection(conn.id, alice)


def test_org_connection_permissions(test_manager, alice, it_admin, bob):
    with tempfile.TemporaryDirectory() as tmp_dir:
        req = CreateConnectionRequest(
            provider="local_files",
            display_name="Enterprise Shared Data",
            scope_level="organization",
            config={"path": tmp_dir, "read_only": True},
        )

        # Standard employee (Alice) cannot create an organization connection
        with pytest.raises(ConnectionError) as exc_info:
            test_manager.create_connection(alice, req)
        assert "only administrators" in str(exc_info.value).lower()

        # IT Admin CAN create an organization connection
        org_conn = test_manager.create_connection(it_admin, req)
        assert org_conn.scope_level == "organization"

        # All employees in the tenant (Alice and Bob) can view org connections
        alice_conns = test_manager.list_connections(alice)
        assert any(c.id == org_conn.id for c in alice_conns)

        bob_conn = test_manager.get_connection(org_conn.id, bob)
        assert bob_conn.id == org_conn.id

        # But only Admin can delete/manage org connection
        with pytest.raises(ConnectionError):
            test_manager.delete_connection(org_conn.id, alice)

        assert test_manager.delete_connection(org_conn.id, it_admin) is True


# ── SSRF Protection Tests ─────────────────────────────────────

def test_ssrf_blocks_private_and_metadata_addresses():
    # Cloud metadata endpoints must be blocked
    with pytest.raises(SSRFBlocked):
        validate_url_ssrf("http://169.254.169.254/latest/meta-data/")

    with pytest.raises(SSRFBlocked):
        validate_url_ssrf("http://metadata.google.internal/computeMetadata/v1/")

    # Loopback addresses must be blocked
    with pytest.raises(SSRFBlocked):
        validate_url_ssrf("http://127.0.0.1:8000/internal")

    with pytest.raises(SSRFBlocked):
        validate_url_ssrf("http://localhost:8080")

    # Private RFC 1918 addresses must be blocked
    with pytest.raises(SSRFBlocked):
        validate_url_ssrf("https://10.0.0.1/admin")

    with pytest.raises(SSRFBlocked):
        validate_url_ssrf("https://192.168.1.1/setup")


# ── OAuth State Lifecycle & Replay Protection Tests ───────────

def test_oauth_state_lifecycle_and_replay_prevention(test_manager, alice):
    from backend.core.config import settings
    orig_id = settings.github_client_id
    orig_secret = settings.github_client_secret
    object.__setattr__(settings, "github_client_id", "test_gh_client_id")
    object.__setattr__(settings, "github_client_secret", "test_gh_secret")

    reg = test_manager._registry
    github = reg.get_provider("github")

    redirect_uri = "http://127.0.0.1:8000/api/connections/oauth/github/callback"


    # Start OAuth flow
    auth_url = test_manager.start_oauth("github", alice, redirect_uri=redirect_uri)
    assert "https://github.com/login/oauth/authorize" in auth_url
    assert "state=" in auth_url


    # Extract state parameter from generated URL
    import urllib.parse
    parsed = urllib.parse.urlparse(auth_url)
    qs = urllib.parse.parse_qs(parsed.query)
    state = qs["state"][0]

    # Verify invalid state is rejected
    with pytest.raises(OAuthDenied):
        test_manager.handle_oauth_callback("github", code="mock-code", state="invalid-fake-state", redirect_uri=redirect_uri)

    # Mock provider callback exchange to test consumption and replay prevention
    orig_handle = github.handle_callback
    try:
        github.handle_callback = lambda **kwargs: {
            "account_identifier": "test-github-user",
            "display_name": "GitHub (test-github-user)",
            "credentials": {"access_token": "gho_mock_token_12345"},
            "metadata_safe": {"login": "test-github-user"},
            "granted_scopes": ["repo"],
        }

        # First consumption succeeds
        conn, _ = test_manager.handle_oauth_callback("github", code="test-code-123", state=state, redirect_uri=redirect_uri)
        assert conn.account_identifier == "test-github-user"
        assert conn.status == "CONNECTED"

        # Second consumption of the same state MUST fail (replay attack prevention)
        with pytest.raises(OAuthDenied) as exc_info:
            test_manager.handle_oauth_callback("github", code="test-code-123", state=state, redirect_uri=redirect_uri)
        assert "already been consumed" in str(exc_info.value).lower()
    finally:
        github.handle_callback = orig_handle
        object.__setattr__(settings, "github_client_id", orig_id)
        object.__setattr__(settings, "github_client_secret", orig_secret)



# ── Agent Client Resolution Tests ─────────────────────────────

def test_agent_client_resolution(test_manager, alice):
    with tempfile.TemporaryDirectory() as tmp_dir:
        req = CreateConnectionRequest(
            provider="local_files",
            display_name="Project Repo",
            scope_level="user",
            config={"path": tmp_dir, "read_only": True},
        )
        conn = test_manager.create_connection(alice, req)

        # Agent resolves by provider name
        client = test_manager.get_client_for_agent("local_files", alice)
        assert hasattr(client, "list_files")
        assert client.read_only is True

        # Agent resolves by capability
        cap_client = test_manager.get_client_for_agent("read_documents", alice)
        assert hasattr(cap_client, "list_files")

        # Resolving non-existent provider fails
        with pytest.raises(ConnectionError):
            test_manager.get_client_for_agent("non_existent_tool", alice)
