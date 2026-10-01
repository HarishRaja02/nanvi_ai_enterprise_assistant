"""Custom REST API Provider with SSRF protection and multi-auth support."""
from __future__ import annotations

import urllib.parse
from typing import Any

from backend.connections.base import (
    AuthType,
    BaseProvider,
    Capability,
    ConnectionError,
    ConnectionTimeout,
    InvalidCredentials,
    ProviderMetadata,
    SSRFBlocked,
    TlsError,
    Unreachable,
)
from backend.connections.ssrf import validate_url_ssrf


class CustomApiProvider(BaseProvider):
    """Provider for custom external REST APIs with built-in SSRF protection."""

    def get_metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            id="custom_api",
            name="Custom REST API",
            categories=("Developer Tools", "Cloud"),
            icon="webhook",
            description="Connect any external REST API with Bearer token, API Key, or Basic auth.",
            auth_type=AuthType.API_KEY,
            capabilities=frozenset({
                Capability.CREDENTIALS_FORM,
                Capability.TEST,
                Capability.CALL_API,
            }),
            available=True,
            configuration_schema={
                "type": "object",
                "required": ["base_url"],
                "properties": {
                    "base_url": {
                        "type": "string",
                        "title": "Base URL",
                        "description": "https://api.example.com/v1",
                    },
                    "auth_type": {
                        "type": "string",
                        "title": "Authentication Type",
                        "enum": ["none", "bearer", "api_key", "basic"],
                        "default": "bearer",
                    },
                    "token": {
                        "type": "string",
                        "title": "Bearer Token",
                        "format": "password",
                    },
                    "api_key_header": {
                        "type": "string",
                        "title": "API Key Header Name",
                        "default": "X-API-Key",
                    },
                    "api_key_value": {
                        "type": "string",
                        "title": "API Key",
                        "format": "password",
                    },
                    "username": {
                        "type": "string",
                        "title": "Basic Auth Username",
                    },
                    "password": {
                        "type": "string",
                        "title": "Basic Auth Password",
                        "format": "password",
                    },
                    "test_endpoint": {
                        "type": "string",
                        "title": "Test Path",
                        "default": "/",
                    },
                },
            },
        )

    def connect(self, config: dict[str, Any]) -> dict[str, Any]:
        base_url = config.get("base_url", "").strip().rstrip("/")
        if not base_url:
            raise InvalidCredentials("Base URL is required.")

        # SSRF validation
        try:
            validate_url_ssrf(base_url)
        except Exception as exc:
            raise SSRFBlocked(str(exc)) from exc

        auth_type = config.get("auth_type", "none").lower()
        credentials: dict[str, Any] = {"base_url": base_url, "auth_type": auth_type}
        safe_meta: dict[str, Any] = {
            "base_url": base_url,
            "auth_type": auth_type,
            "test_endpoint": config.get("test_endpoint", "/"),
        }

        if auth_type == "bearer":
            token = config.get("token", "").strip()
            if not token:
                raise InvalidCredentials("Bearer token is required.")
            credentials["token"] = token
            safe_meta["token_preview"] = f"***{token[-4:]}" if len(token) > 4 else "***"
        elif auth_type == "api_key":
            header = config.get("api_key_header", "X-API-Key").strip()
            val = config.get("api_key_value", "").strip()
            if not val:
                raise InvalidCredentials("API key is required.")
            credentials["api_key_header"] = header
            credentials["api_key_value"] = val
            safe_meta["api_key_header"] = header
        elif auth_type == "basic":
            user = config.get("username", "").strip()
            pwd = config.get("password", "")
            credentials["username"] = user
            credentials["password"] = pwd
            safe_meta["username"] = user

        parsed = urllib.parse.urlparse(base_url)
        account_id = f"{parsed.netloc}{parsed.path}"
        display_name = f"API ({parsed.netloc})"

        return {
            "account_identifier": account_id,
            "display_name": display_name,
            "credentials": credentials,
            "metadata_safe": safe_meta,
            "granted_scopes": ["call_api"],
        }

    def _build_request_headers(self, creds: dict[str, Any]) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/json", "User-Agent": "Nanvi-Assistant/1.0"}
        auth_type = creds.get("auth_type", "none")

        if auth_type == "bearer" and creds.get("token"):
            headers["Authorization"] = f"Bearer {creds['token']}"
        elif auth_type == "api_key" and creds.get("api_key_value"):
            hdr = creds.get("api_key_header", "X-API-Key")
            headers[hdr] = creds["api_key_value"]
        elif auth_type == "basic" and creds.get("username"):
            import base64
            user = creds.get("username", "")
            pwd = creds.get("password", "")
            enc = base64.b64encode(f"{user}:{pwd}".encode()).decode()
            headers["Authorization"] = f"Basic {enc}"

        return headers

    def test_connection(
        self,
        *,
        decrypted_credentials: dict[str, Any],
        metadata_safe: dict[str, Any],
    ) -> dict[str, Any]:
        import urllib.request
        import urllib.error
        import ssl

        base_url = decrypted_credentials.get("base_url") or metadata_safe.get("base_url")
        if not base_url:
            raise InvalidCredentials("Missing API base URL.")

        test_path = metadata_safe.get("test_endpoint", "/")
        if not test_path.startswith("/"):
            test_path = f"/{test_path}"
        full_url = f"{base_url.rstrip('/')}{test_path}"

        # SSRF validation on target
        try:
            validate_url_ssrf(full_url)
        except Exception as exc:
            raise SSRFBlocked(str(exc)) from exc

        headers = self._build_request_headers(decrypted_credentials)
        req = urllib.request.Request(full_url, headers=headers, method="GET")

        ctx = ssl.create_default_context()
        try:
            with urllib.request.urlopen(req, timeout=5, context=ctx) as resp:
                status_code = resp.status
                return {
                    "ok": True,
                    "status_code": status_code,
                    "url": full_url,
                }
        except urllib.error.HTTPError as exc:
            if exc.code in {401, 403}:
                raise InvalidCredentials(f"API Authentication failed (HTTP {exc.code})") from exc
            if exc.code == 404:
                # 404 means host is reached, but endpoint path didn't match
                return {"ok": True, "status_code": 404, "note": "Host reached, test endpoint returned 404"}
            raise ConnectionError(f"API returned HTTP {exc.code}: {exc.reason}") from exc
        except urllib.error.URLError as exc:
            reason = str(exc.reason).lower()
            if "ssl" in reason or "certificate" in reason:
                raise TlsError(f"TLS/SSL error: {exc.reason}") from exc
            if "timed out" in reason:
                raise ConnectionTimeout("API request timed out.") from exc
            raise Unreachable(f"API host unreachable: {exc.reason}") from exc
        except Exception as exc:
            raise ConnectionError(f"Unexpected error testing API: {exc}") from exc

    def get_client(
        self,
        *,
        decrypted_credentials: dict[str, Any],
        metadata_safe: dict[str, Any],
    ) -> Any:
        provider = self

        class CustomApiClient:
            def __init__(self, creds: dict[str, Any]) -> None:
                self.creds = creds
                self.base_url = creds.get("base_url", "").rstrip("/")

            def request(self, path: str, method: str = "GET", json_body: dict | None = None) -> Any:
                import json
                import urllib.request
                import ssl

                if not path.startswith("/"):
                    path = f"/{path}"
                url = f"{self.base_url}{path}"
                validate_url_ssrf(url)

                headers = provider._build_request_headers(self.creds)
                data = None
                if json_body is not None:
                    headers["Content-Type"] = "application/json"
                    data = json.dumps(json_body).encode("utf-8")

                req = urllib.request.Request(url, data=data, headers=headers, method=method)
                ctx = ssl.create_default_context()
                with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
                    raw = resp.read(1024 * 1024)  # 1MB max
                    try:
                        return json.loads(raw.decode("utf-8"))
                    except Exception:
                        return raw.decode("utf-8", errors="replace")

        return CustomApiClient(decrypted_credentials)
