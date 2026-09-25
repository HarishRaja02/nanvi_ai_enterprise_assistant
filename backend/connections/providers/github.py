"""GitHub Provider (Personal Access Token / OAuth 2.0)."""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlencode

import httpx

from backend.connections.base import (
    AuthType,
    BaseProvider,
    Capability,
    ConnectionError,
    ConnectionTimeout,
    InvalidCredentials,
    OAuthDenied,
    ProviderMetadata,
    ProviderUnavailable,
    Unreachable,
)
from backend.core.config import settings

logger = logging.getLogger(__name__)

GITHUB_AUTH_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_API_USER_URL = "https://api.github.com/user"

DEFAULT_GITHUB_SCOPES = ("read:user", "repo")


class GitHubProvider(BaseProvider):
    """GitHub provider supporting both Personal Access Token (PAT) and OAuth 2.0."""

    def __init__(self, http_client: httpx.Client | None = None) -> None:
        self._client = http_client or httpx.Client(timeout=10.0)

    def get_metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            id="github",
            name="GitHub",
            categories=("Developer Tools",),
            icon="github",
            description="Connect GitHub repositories for code analysis, pull requests, and documentation search.",
            auth_type=AuthType.API_KEY,
            capabilities=frozenset({
                Capability.CREDENTIALS_FORM,
                Capability.TEST,
                Capability.REVOKE,
                Capability.READ_REPOS,
                Capability.READ_DOCUMENTS,
                Capability.OAUTH,
            }),
            available=True,
            available_reason="",
            required_scopes=DEFAULT_GITHUB_SCOPES,
            configuration_schema={
                "type": "object",
                "required": ["github_token"],
                "properties": {
                    "github_token": {
                        "type": "string",
                        "title": "Personal Access Token (PAT)",
                        "description": "GitHub token (classic with 'repo' scope or fine-grained token)",
                        "format": "password",
                    },
                },
            },
        )

    def connect(self, config: dict[str, Any]) -> dict[str, Any]:
        token = config.get("github_token", "").strip() or config.get("access_token", "").strip()
        if not token:
            raise InvalidCredentials("GitHub Personal Access Token is required.")

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "Nanvi-Assistant/1.0",
        }
        try:
            resp = self._client.get(GITHUB_API_USER_URL, headers=headers)
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise Unreachable(f"Could not connect to GitHub API: {exc}") from exc
        except httpx.TimeoutException as exc:
            raise ConnectionTimeout("Connection to GitHub API timed out.") from exc
        except Exception as exc:
            raise Unreachable(f"GitHub connection error: {exc}") from exc

        if resp.status_code in {401, 403}:
            raise InvalidCredentials("Invalid or expired GitHub Personal Access Token.")
        if resp.status_code != 200:
            raise ConnectionError(f"GitHub API returned HTTP {resp.status_code}")

        user_info = resp.json()
        login = user_info.get("login") or "github-user"
        name = user_info.get("name") or login
        avatar_url = user_info.get("avatar_url")
        html_url = user_info.get("html_url")

        return {
            "account_identifier": login,
            "display_name": f"GitHub ({login})",
            "credentials": {
                "access_token": token,
                "github_token": token,
                "token_type": "bearer",
            },
            "metadata_safe": {
                "login": login,
                "name": name,
                "avatar_url": avatar_url,
                "html_url": html_url,
            },
            "granted_scopes": ["read:user", "repo"],
        }

    def get_authorization_url(
        self,
        *,
        user_id: str,
        tenant_id: str,
        redirect_uri: str,
        state: str,
        pkce_verifier: str | None = None,
    ) -> str:
        if not settings.github_client_id:
            raise ProviderUnavailable("GITHUB_CLIENT_ID is not configured on the server.")

        params = {
            "client_id": settings.github_client_id,
            "redirect_uri": redirect_uri,
            "scope": " ".join(DEFAULT_GITHUB_SCOPES),
            "state": state,
        }
        return f"{GITHUB_AUTH_URL}?{urlencode(params)}"

    def handle_callback(
        self,
        *,
        code: str,
        state: str,
        redirect_uri: str,
        pkce_verifier: str | None = None,
    ) -> dict[str, Any]:
        if not settings.github_client_id or not settings.github_client_secret:
            raise ProviderUnavailable("GitHub OAuth client credentials missing.")

        payload = {
            "client_id": settings.github_client_id,
            "client_secret": settings.github_client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
        }
        headers = {"Accept": "application/json", "User-Agent": "Nanvi-Assistant/1.0"}
        try:
            resp = self._client.post(GITHUB_TOKEN_URL, data=payload, headers=headers)
        except Exception as exc:
            raise Unreachable(f"Could not reach GitHub OAuth server: {exc}") from exc

        if resp.status_code != 200:
            raise OAuthDenied(f"GitHub token exchange failed: {resp.text}")

        token_data = resp.json()
        if "error" in token_data:
            raise OAuthDenied(f"GitHub authorization error: {token_data.get('error_description', token_data['error'])}")

        access_token = token_data.get("access_token", "")
        token_type = token_data.get("token_type", "bearer")
        scope_str = token_data.get("scope", "")
        granted_scopes = [s.strip() for s in scope_str.split(",") if s.strip()]

        # Fetch GitHub user profile
        user_info = {}
        try:
            info_resp = self._client.get(
                GITHUB_API_USER_URL,
                headers={"Authorization": f"Bearer {access_token}", "User-Agent": "Nanvi-Assistant/1.0"},
            )
            if info_resp.status_code == 200:
                user_info = info_resp.json()
        except Exception as exc:
            logger.warning("Could not fetch GitHub user info: %s", exc)

        login = user_info.get("login") or "github-user"
        name = user_info.get("name") or login
        avatar_url = user_info.get("avatar_url")
        html_url = user_info.get("html_url")

        return {
            "account_identifier": login,
            "display_name": f"GitHub ({login})",
            "credentials": {
                "access_token": access_token,
                "github_token": access_token,
                "token_type": token_type,
            },
            "metadata_safe": {
                "login": login,
                "name": name,
                "avatar_url": avatar_url,
                "html_url": html_url,
            },
            "granted_scopes": granted_scopes,
        }

    def test_connection(
        self,
        *,
        decrypted_credentials: dict[str, Any],
        metadata_safe: dict[str, Any],
    ) -> dict[str, Any]:
        token = (
            decrypted_credentials.get("access_token", "").strip()
            or decrypted_credentials.get("github_token", "").strip()
        )
        if not token:
            raise InvalidCredentials("Missing GitHub access token.")

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "Nanvi-Assistant/1.0",
        }
        try:
            resp = self._client.get(GITHUB_API_USER_URL, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                return {"ok": True, "login": data.get("login", ""), "verified": True}
            if resp.status_code in {401, 403}:
                raise InvalidCredentials("GitHub token is invalid or has expired.")
            raise ConnectionError(f"GitHub API returned HTTP {resp.status_code}")
        except InvalidCredentials:
            raise
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise Unreachable(f"Could not connect to GitHub API: {exc}") from exc
        except httpx.TimeoutException as exc:
            raise ConnectionTimeout("Connection to GitHub API timed out.") from exc
        except Exception as exc:
            raise ConnectionError(f"Error testing GitHub connection: {exc}") from exc

    def get_client(
        self,
        *,
        decrypted_credentials: dict[str, Any],
        metadata_safe: dict[str, Any],
    ) -> Any:
        token = (
            decrypted_credentials.get("access_token", "").strip()
            or decrypted_credentials.get("github_token", "").strip()
        )
        client = self._client

        class GitHubClient:
            def __init__(self, token: str) -> None:
                self.token = token
                self._headers = {
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "Nanvi-Assistant/1.0",
                }

            def list_repositories(self, limit: int = 50) -> list[dict[str, Any]]:
                resp = client.get(f"https://api.github.com/user/repos?sort=updated&per_page={limit}", headers=self._headers)
                if resp.status_code == 200:
                    results = []
                    for r in resp.json():
                        results.append({
                            "name": r.get("name"),
                            "full_name": r.get("full_name"),
                            "owner": r.get("owner", {}).get("login"),
                            "private": r.get("private", False),
                            "description": r.get("description") or "No description",
                            "default_branch": r.get("default_branch", "main"),
                            "updated_at": r.get("updated_at"),
                            "html_url": r.get("html_url"),
                            "stargazers_count": r.get("stargazers_count", 0),
                            "forks_count": r.get("forks_count", 0),
                        })
                    return results
                return []

            def get_repository(self, repo_name_or_full: str) -> dict[str, Any] | None:
                clean = repo_name_or_full.strip().strip("/")
                if "/" in clean:
                    resp = client.get(f"https://api.github.com/repos/{clean}", headers=self._headers)
                    if resp.status_code == 200:
                        r = resp.json()
                        return {
                            "name": r.get("name"),
                            "full_name": r.get("full_name"),
                            "owner": r.get("owner", {}).get("login"),
                            "private": r.get("private", False),
                            "description": r.get("description") or "No description",
                            "default_branch": r.get("default_branch", "main"),
                            "updated_at": r.get("updated_at"),
                            "html_url": r.get("html_url"),
                        }
                # Search in user's repos
                all_repos = self.list_repositories(limit=100)
                clean_lower = clean.lower()
                for r in all_repos:
                    if r["name"].lower() == clean_lower or r["full_name"].lower() == clean_lower:
                        return r
                return None

            def list_branches(self, owner: str, repo: str) -> list[dict[str, Any]]:
                resp = client.get(f"https://api.github.com/repos/{owner}/{repo}/branches?per_page=100", headers=self._headers)
                if resp.status_code == 200:
                    branches = []
                    for b in resp.json():
                        branches.append({
                            "name": b.get("name"),
                            "protected": b.get("protected", False),
                            "commit_sha": b.get("commit", {}).get("sha", "")[:7],
                        })
                    return branches
                return []

            def list_commits(self, owner: str, repo: str, branch: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
                url = f"https://api.github.com/repos/{owner}/{repo}/commits?per_page={limit}"
                if branch:
                    url += f"&sha={urllib.parse.quote(branch)}"
                resp = client.get(url, headers=self._headers)
                if resp.status_code == 200:
                    commits = []
                    for c in resp.json():
                        commit_info = c.get("commit", {})
                        author_info = commit_info.get("author", {})
                        msg = commit_info.get("message", "").split("\n")[0]
                        commits.append({
                            "sha": c.get("sha", "")[:7],
                            "full_sha": c.get("sha", ""),
                            "message": msg,
                            "author": author_info.get("name", "Unknown"),
                            "date": author_info.get("date", ""),
                            "html_url": c.get("html_url", ""),
                        })
                    return commits
                return []

            def get_file_content(self, owner: str, repo: str, path: str, ref: str = "main") -> str | None:
                import base64
                resp = client.get(f"https://api.github.com/repos/{owner}/{repo}/contents/{path}?ref={ref}", headers=self._headers)
                if resp.status_code == 200:
                    data = resp.json()
                    content = data.get("content", "")
                    return base64.b64decode(content).decode("utf-8", errors="replace")
                return None

        return GitHubClient(token)
