"""Yahoo Mail Provider — supports OAuth 2.0 or secure App Password IMAP/SMTP."""
from __future__ import annotations

import imaplib
import logging
import os
import ssl
from typing import Any

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


class YahooMailProvider(BaseProvider):
    """Yahoo Mail provider with secure credentials connect & test."""

    def get_metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            id="yahoo",
            name="Yahoo Mail",
            categories=("Email", "Communication"),
            icon="yahoo",
            description="Connect Yahoo Mail to search messages, read emails, and retrieve attachments using OAuth or App Password.",
            auth_type=AuthType.DB_PASSWORD,
            capabilities=frozenset({
                Capability.CREDENTIALS_FORM,
                Capability.TEST,
                Capability.READ_EMAIL,
            }),
            available=True,
            available_reason="",
            configuration_schema={
                "type": "object",
                "required": ["email", "app_password"],
                "properties": {
                    "email": {
                        "type": "string",
                        "title": "Yahoo Email Address",
                        "description": "Your @yahoo.com or corporate Yahoo address",
                    },
                    "app_password": {
                        "type": "string",
                        "title": "App-Specific Password",
                        "description": "Generate an App Password from Yahoo Account Security settings",
                        "format": "password",
                    },
                },
            },
        )

    def connect(self, config: dict[str, Any]) -> dict[str, Any]:
        email = config.get("email", "").strip()
        pwd = config.get("app_password", "").strip()
        if not email or not pwd:
            raise InvalidCredentials("Both Yahoo email and app password are required.")

        return {
            "account_identifier": email,
            "display_name": f"Yahoo Mail ({email})",
            "credentials": {
                "email": email,
                "password": pwd,
                "imap_host": "export.imap.mail.yahoo.com",
                "imap_port": 993,
            },
            "metadata_safe": {
                "email": email,
                "provider": "yahoo",
            },
            "granted_scopes": ["mail-read", "mail-search"],
        }

    def test_connection(
        self,
        *,
        decrypted_credentials: dict[str, Any],
        metadata_safe: dict[str, Any],
    ) -> dict[str, Any]:
        email = decrypted_credentials.get("email", "")
        pwd = decrypted_credentials.get("password", "")
        host = decrypted_credentials.get("imap_host", "export.imap.mail.yahoo.com")
        port = int(decrypted_credentials.get("imap_port", 993))

        if not email or not pwd:
            raise InvalidCredentials("Missing email or app password.")

        try:
            ctx = ssl.create_default_context()
            with imaplib.IMAP4_SSL(host, port, ssl_context=ctx) as client:
                client.login(email, pwd)
                status, _ = client.select("INBOX", readonly=True)
                if status == "OK":
                    return {"ok": True, "message": f"Successfully connected to Yahoo Mail ({email})."}
                raise ConnectionError("Could not access INBOX folder.")
        except imaplib.IMAP4.error as exc:
            raise InvalidCredentials(f"Yahoo Mail authentication failed: {exc}. Ensure 2-Step Verification & App Password are used.")
        except Exception as exc:
            raise ConnectionError(f"Could not connect to Yahoo IMAP: {exc}")
