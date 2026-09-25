import pytest
from unittest.mock import MagicMock, patch
import httpx

from backend.connections.providers.supabase import SupabaseProvider
from backend.connections.base import InvalidCredentials, Unreachable

@pytest.fixture(autouse=True)
def mock_ssrf():
    with patch("backend.connections.providers.supabase.validate_url_ssrf") as mock:
        mock.return_value = "https://mock.supabase.co"
        yield mock

def test_supabase_provider_publishable_key():
    client = MagicMock(spec=httpx.Client)
    # /auth/v1/settings returns 200
    mock_auth_resp = MagicMock(status_code=200)
    client.get.return_value = mock_auth_resp

    provider = SupabaseProvider(http_client=client)
    res = provider.test_connection(
        decrypted_credentials={
            "supabase_url": "https://mock.supabase.co",
            "supabase_key": "sb_publishable_test123",
        },
        metadata_safe={},
    )
    assert res["ok"] is True
    assert res["api_verified"] is True
    assert res["key_type"] == "verified_auth"

def test_supabase_provider_service_role_key():
    client = MagicMock(spec=httpx.Client)
    # /auth/v1/settings returns 404/non-200, but /rest/v1/ returns 200
    mock_auth = MagicMock(status_code=404)
    mock_rest = MagicMock(status_code=200)
    client.get.side_effect = [mock_auth, mock_rest]

    provider = SupabaseProvider(http_client=client)
    res = provider.test_connection(
        decrypted_credentials={
            "supabase_url": "https://mock.supabase.co",
            "supabase_key": "sb_secret_test123",
        },
        metadata_safe={},
    )
    assert res["ok"] is True
    assert res["key_type"] == "service_role"

def test_supabase_provider_invalid_key():
    client = MagicMock(spec=httpx.Client)
    # /auth/v1/settings returns 401 with error message
    mock_auth = MagicMock(status_code=401)
    mock_auth.json.return_value = {"message": "Invalid API key"}
    mock_rest = MagicMock(
        status_code=401,
        headers={"sb-error-code": "UNAUTHORIZED_INVALID_API_KEY"},
        text='{"message":"Invalid API key"}',
    )
    client.get.side_effect = [mock_auth, mock_rest]

    provider = SupabaseProvider(http_client=client)
    with pytest.raises(InvalidCredentials) as exc:
        provider.test_connection(
            decrypted_credentials={
                "supabase_url": "https://mock.supabase.co",
                "supabase_key": "sb_publishable_bad",
            },
            metadata_safe={},
        )
    assert "Invalid API key" in str(exc.value)
