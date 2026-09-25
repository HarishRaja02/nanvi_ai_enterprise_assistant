import pytest
from unittest.mock import MagicMock
import httpx

from backend.connections.providers.github import GitHubProvider
from backend.connections.base import InvalidCredentials

def test_github_pat_connect_and_test():
    client = MagicMock(spec=httpx.Client)
    # Mock user response
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {
        "login": "octocat",
        "name": "The Octocat",
        "avatar_url": "https://github.com/images/error/octocat_happy.gif",
        "html_url": "https://github.com/octocat",
    }
    client.get.return_value = mock_resp

    provider = GitHubProvider(http_client=client)
    res = provider.connect({"github_token": "ghp_mocktoken123"})
    assert res["account_identifier"] == "octocat"
    assert res["display_name"] == "GitHub (octocat)"
    assert res["credentials"]["access_token"] == "ghp_mocktoken123"

    # Test connection
    test_res = provider.test_connection(
        decrypted_credentials=res["credentials"],
        metadata_safe=res["metadata_safe"],
    )
    assert test_res["ok"] is True
    assert test_res["login"] == "octocat"

def test_github_pat_invalid_token():
    client = MagicMock(spec=httpx.Client)
    mock_resp = MagicMock(status_code=401)
    client.get.return_value = mock_resp

    provider = GitHubProvider(http_client=client)
    with pytest.raises(InvalidCredentials):
        provider.connect({"github_token": "ghp_invalidtoken"})
