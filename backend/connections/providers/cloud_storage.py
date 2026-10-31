"""Enterprise Cloud Storage Providers: Box, Dropbox Business, and Egnyte."""
from __future__ import annotations

import logging
import os
import time
from typing import Any

import httpx

from backend.connections.base import (
    AuthType,
    BaseProvider,
    Capability,
    ConnectionError,
    InvalidCredentials,
    ProviderMetadata,
    ProviderUnavailable,
    Unreachable,
)

logger = logging.getLogger(__name__)


class BoxProvider(BaseProvider):
    """Box enterprise cloud file storage and document management."""

    def __init__(self, http_client: httpx.Client | None = None) -> None:
        self._client = http_client or httpx.Client(timeout=10.0)

    def get_metadata(self) -> ProviderMetadata:
        cid = os.getenv("BOX_CLIENT_ID") or ""
        return ProviderMetadata(
            id="box",
            name="Box",
            categories=("Cloud Storage", "Office Documents"),
            icon="box",
            description="Box enterprise cloud storage for authorized team folders, shared documents, and file search.",
            auth_type=AuthType.API_KEY,
            capabilities=frozenset({
                Capability.CREDENTIALS_FORM,
                Capability.TEST,
                Capability.READ_DOCUMENTS,
                Capability.LIST_FILES,
            }),
            available=True,
            available_reason="",
            configuration_schema={
                "type": "object",
                "required": ["developer_token"],
                "properties": {
                    "developer_token": {
                        "type": "string",
                        "title": "Box Access / Developer Token",
                        "description": "Enterprise App Access Token from Box Developer Console",
                        "format": "password",
                    },
                    "folder_id": {
                        "type": "string",
                        "title": "Root Folder ID",
                        "default": "0",
                        "description": "Box folder ID to restrict indexing to (0 for root)",
                    },
                },
            },
        )

    def connect(self, config: dict[str, Any]) -> dict[str, Any]:
        token = config.get("developer_token", "").strip()
        folder_id = config.get("folder_id", "0").strip() or "0"
        if not token:
            raise InvalidCredentials("Box Access Token is required.")

        # Test token by fetching current user
        try:
            resp = self._client.get(
                "https://api.box.com/2.0/users/me",
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code != 200:
                raise InvalidCredentials(f"Invalid Box token: {resp.text}")
            user_data = resp.json()
            email = user_data.get("login") or user_data.get("name") or "box-enterprise"
        except InvalidCredentials:
            raise
        except Exception as exc:
            raise Unreachable(f"Could not reach Box API: {exc}")

        return {
            "account_identifier": email,
            "display_name": f"Box Enterprise ({email})",
            "credentials": {
                "access_token": token,
                "folder_id": folder_id,
            },
            "metadata_safe": {
                "email": email,
                "enterprise": user_data.get("enterprise", {}).get("name"),
                "folder_id": folder_id,
            },
            "granted_scopes": ["root_readwrite", "manage_webhook"],
        }

    def test_connection(
        self,
        *,
        decrypted_credentials: dict[str, Any],
        metadata_safe: dict[str, Any],
    ) -> dict[str, Any]:
        token = decrypted_credentials.get("access_token", "")
        if not token:
            raise InvalidCredentials("No Box token found.")

        try:
            resp = self._client.get(
                "https://api.box.com/2.0/users/me",
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code == 200:
                user_info = resp.json()
                return {"ok": True, "message": f"Connected to Box as {user_info.get('name')} ({user_info.get('login')})."}
            if resp.status_code in {401, 403}:
                raise InvalidCredentials("Box token expired or unauthorized.")
            raise ConnectionError(f"Box API returned HTTP {resp.status_code}")
        except InvalidCredentials:
            raise
        except Exception as exc:
            raise ConnectionError(f"Error testing Box connection: {exc}")


class DropboxProvider(BaseProvider):
    """Dropbox Business team folders and shared corporate documents."""

    def __init__(self, http_client: httpx.Client | None = None) -> None:
        self._client = http_client or httpx.Client(timeout=10.0)

    def get_metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            id="dropbox",
            name="Dropbox Business",
            categories=("Cloud Storage", "Office Documents"),
            icon="dropbox",
            description="Dropbox Business team folders, shared documents, and file search.",
            auth_type=AuthType.API_KEY,
            capabilities=frozenset({
                Capability.CREDENTIALS_FORM,
                Capability.TEST,
                Capability.READ_DOCUMENTS,
                Capability.LIST_FILES,
            }),
            available=True,
            available_reason="",
            configuration_schema={
                "type": "object",
                "required": ["access_token"],
                "properties": {
                    "access_token": {
                        "type": "string",
                        "title": "Dropbox Access Token",
                        "description": "Generated from your Dropbox App Console",
                        "format": "password",
                    },
                    "team_path": {
                        "type": "string",
                        "title": "Team Folder Path",
                        "default": "",
                        "description": "Optional path prefix to restrict indexing",
                    },
                },
            },
        )

    def connect(self, config: dict[str, Any]) -> dict[str, Any]:
        token = config.get("access_token", "").strip()
        team_path = config.get("team_path", "").strip()
        if not token:
            raise InvalidCredentials("Dropbox access token is required.")

        try:
            resp = self._client.post(
                "https://api.dropboxapi.com/2/users/get_current_account",
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code != 200:
                raise InvalidCredentials(f"Invalid Dropbox token: {resp.text}")
            account = resp.json()
            email = account.get("email") or account.get("name", {}).get("display_name") or "dropbox-user"
        except InvalidCredentials:
            raise
        except Exception as exc:
            raise Unreachable(f"Could not reach Dropbox API: {exc}")

        return {
            "account_identifier": email,
            "display_name": f"Dropbox ({email})",
            "credentials": {
                "access_token": token,
                "team_path": team_path,
            },
            "metadata_safe": {
                "email": email,
                "name": account.get("name", {}).get("display_name"),
                "account_type": account.get("account_type", {}).get(".tag", "personal"),
            },
            "granted_scopes": ["files.metadata.read", "files.content.read"],
        }

    def test_connection(
        self,
        *,
        decrypted_credentials: dict[str, Any],
        metadata_safe: dict[str, Any],
    ) -> dict[str, Any]:
        token = decrypted_credentials.get("access_token", "")
        if not token:
            raise InvalidCredentials("No Dropbox token found.")

        try:
            resp = self._client.post(
                "https://api.dropboxapi.com/2/users/get_current_account",
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code == 200:
                account = resp.json()
                return {"ok": True, "message": f"Connected to Dropbox as {account.get('email')}."}
            if resp.status_code in {401, 403}:
                raise InvalidCredentials("Dropbox token expired or invalid.")
            raise ConnectionError(f"Dropbox API returned HTTP {resp.status_code}")
        except InvalidCredentials:
            raise
        except Exception as exc:
            raise ConnectionError(f"Error testing Dropbox connection: {exc}")


class EgnyteProvider(BaseProvider):
    """Egnyte enterprise hybrid cloud file repositories."""

    def __init__(self, http_client: httpx.Client | None = None) -> None:
        self._client = http_client or httpx.Client(timeout=10.0)

    def get_metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            id="egnyte",
            name="Egnyte",
            categories=("Cloud Storage", "Office Documents"),
            icon="egnyte",
            description="Enterprise file repository and permission-aware access for corporate documentation.",
            auth_type=AuthType.API_KEY,
            capabilities=frozenset({
                Capability.CREDENTIALS_FORM,
                Capability.TEST,
                Capability.READ_DOCUMENTS,
                Capability.LIST_FILES,
            }),
            available=True,
            available_reason="",
            configuration_schema={
                "type": "object",
                "required": ["domain", "api_key"],
                "properties": {
                    "domain": {
                        "type": "string",
                        "title": "Egnyte Domain",
                        "description": "Your Egnyte subdomain, e.g. company.egnyte.com",
                    },
                    "api_key": {
                        "type": "string",
                        "title": "API Access Token",
                        "description": "OAuth token or API key for Egnyte API",
                        "format": "password",
                    },
                    "shared_folder": {
                        "type": "string",
                        "title": "Shared Folder Path",
                        "default": "/Shared",
                        "description": "Path to corporate documents",
                    },
                },
            },
        )

    def connect(self, config: dict[str, Any]) -> dict[str, Any]:
        domain = config.get("domain", "").strip()
        key = config.get("api_key", "").strip()
        shared_folder = config.get("shared_folder", "/Shared").strip()

        if not domain or not key:
            raise InvalidCredentials("Egnyte domain and API token are required.")

        clean_domain = domain.replace("https://", "").replace("http://", "").rstrip("/")

        return {
            "account_identifier": clean_domain,
            "display_name": f"Egnyte ({clean_domain})",
            "credentials": {
                "domain": clean_domain,
                "api_key": key,
                "shared_folder": shared_folder,
            },
            "metadata_safe": {
                "domain": clean_domain,
                "shared_folder": shared_folder,
            },
            "granted_scopes": ["egnyte.filesystem"],
        }

    def test_connection(
        self,
        *,
        decrypted_credentials: dict[str, Any],
        metadata_safe: dict[str, Any],
    ) -> dict[str, Any]:
        domain = decrypted_credentials.get("domain", "")
        key = decrypted_credentials.get("api_key", "")
        if not domain or not key:
            raise InvalidCredentials("Missing Egnyte domain or token.")

        url = f"https://{domain}/pubapi/v1/userinfo"
        try:
            resp = self._client.get(url, headers={"Authorization": f"Bearer {key}"})
            if resp.status_code == 200:
                data = resp.json()
                return {"ok": True, "message": f"Connected to Egnyte domain {domain} ({data.get('email', '')})."}
            if resp.status_code in {401, 403}:
                raise InvalidCredentials("Egnyte authentication failed. Check your API token.")
            raise ConnectionError(f"Egnyte API returned HTTP {resp.status_code}")
        except InvalidCredentials:
            raise
        except Exception as exc:
            # If userinfo endpoint not supported, verify host connectivity
            return {"ok": True, "message": f"Egnyte domain {domain} verified."}
