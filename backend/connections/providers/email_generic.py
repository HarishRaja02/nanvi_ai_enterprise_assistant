"""Generic IMAP and Generic SMTP Email Providers."""
from __future__ import annotations

import imaplib
import logging
import smtplib
import ssl
from typing import Any

from backend.connections.base import (
    AuthType,
    BaseProvider,
    Capability,
    ConnectionError,
    InvalidCredentials,
    ProviderMetadata,
    TlsError,
    Unreachable,
)
from backend.connections.ssrf import validate_hostname

logger = logging.getLogger(__name__)


class ImapProvider(BaseProvider):
    """Generic IMAP Email Provider for reading and searching corporate mailboxes."""

    def get_metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            id="imap",
            name="Generic IMAP",
            categories=("Email", "Communication"),
            icon="mail",
            description="Connect any standard enterprise IMAP server over secure TLS/SSL for reading and searching emails.",
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
                "required": ["host", "port", "username", "password"],
                "properties": {
                    "host": {"type": "string", "title": "IMAP Server Host", "description": "e.g. imap.example.com"},
                    "port": {"type": "integer", "title": "Port", "default": 993},
                    "username": {"type": "string", "title": "Username / Email"},
                    "password": {"type": "string", "title": "Password", "format": "password"},
                    "use_ssl": {"type": "boolean", "title": "Use SSL/TLS", "default": True},
                },
            },
        )

    def connect(self, config: dict[str, Any]) -> dict[str, Any]:
        host = config.get("host", "").strip()
        port = int(config.get("port", 993))
        user = config.get("username", "").strip()
        pwd = config.get("password", "").strip()
        use_ssl = bool(config.get("use_ssl", True))

        if not host or not user or not pwd:
            raise InvalidCredentials("Host, username, and password are required.")

        validate_hostname(host, port=port)

        return {
            "account_identifier": f"{user}@{host}",
            "display_name": f"IMAP ({user}@{host})",
            "credentials": {
                "host": host,
                "port": port,
                "username": user,
                "password": pwd,
                "use_ssl": use_ssl,
            },
            "metadata_safe": {
                "host": host,
                "port": port,
                "username": user,
                "use_ssl": use_ssl,
            },
            "granted_scopes": ["imap-read", "imap-search"],
        }

    def test_connection(
        self,
        *,
        decrypted_credentials: dict[str, Any],
        metadata_safe: dict[str, Any],
    ) -> dict[str, Any]:
        host = decrypted_credentials.get("host", "")
        port = int(decrypted_credentials.get("port", 993))
        user = decrypted_credentials.get("username", "")
        pwd = decrypted_credentials.get("password", "")
        use_ssl = bool(decrypted_credentials.get("use_ssl", True))

        validate_hostname(host, port=port)

        try:
            if use_ssl:
                ctx = ssl.create_default_context()
                client = imaplib.IMAP4_SSL(host, port, ssl_context=ctx)
            else:
                client = imaplib.IMAP4(host, port)

            with client:
                client.login(user, pwd)
                status, _ = client.select("INBOX", readonly=True)
                if status == "OK":
                    return {"ok": True, "message": f"Successfully connected to IMAP server {host}."}
                raise ConnectionError("Login succeeded, but failed to open INBOX.")
        except imaplib.IMAP4.error as exc:
            raise InvalidCredentials(f"IMAP authentication failed: {exc}")
        except ssl.SSLError as exc:
            raise TlsError(f"IMAP TLS/SSL negotiation failed: {exc}")
        except Exception as exc:
            raise Unreachable(f"Could not reach IMAP server: {exc}")


class SmtpProvider(BaseProvider):
    """Generic SMTP Outbound Email Provider."""

    def get_metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            id="smtp",
            name="Generic SMTP",
            categories=("Email", "Communication"),
            icon="send",
            description="Connect an enterprise SMTP mail gateway for sending system notifications, alerts, and reports.",
            auth_type=AuthType.DB_PASSWORD,
            capabilities=frozenset({
                Capability.CREDENTIALS_FORM,
                Capability.TEST,
                Capability.SEND_EMAIL,
            }),
            available=True,
            available_reason="",
            configuration_schema={
                "type": "object",
                "required": ["host", "port", "username", "password"],
                "properties": {
                    "host": {"type": "string", "title": "SMTP Server Host", "description": "e.g. smtp.example.com"},
                    "port": {"type": "integer", "title": "Port", "default": 587},
                    "username": {"type": "string", "title": "SMTP Username"},
                    "password": {"type": "string", "title": "SMTP Password", "format": "password"},
                    "use_tls": {"type": "boolean", "title": "Use STARTTLS", "default": True},
                    "sender_address": {"type": "string", "title": "Default Sender Email", "description": "e.g. assistant@company.com"},
                },
            },
        )

    def connect(self, config: dict[str, Any]) -> dict[str, Any]:
        host = config.get("host", "").strip()
        port = int(config.get("port", 587))
        user = config.get("username", "").strip()
        pwd = config.get("password", "").strip()
        use_tls = bool(config.get("use_tls", True))
        sender = config.get("sender_address", "").strip() or user

        if not host or not user or not pwd:
            raise InvalidCredentials("Host, username, and password are required.")

        validate_hostname(host, port=port)

        return {
            "account_identifier": f"{user}@{host}",
            "display_name": f"SMTP Gateway ({host})",
            "credentials": {
                "host": host,
                "port": port,
                "username": user,
                "password": pwd,
                "use_tls": use_tls,
                "sender_address": sender,
            },
            "metadata_safe": {
                "host": host,
                "port": port,
                "username": user,
                "use_tls": use_tls,
                "sender_address": sender,
            },
            "granted_scopes": ["smtp-send"],
        }

    def test_connection(
        self,
        *,
        decrypted_credentials: dict[str, Any],
        metadata_safe: dict[str, Any],
    ) -> dict[str, Any]:
        host = decrypted_credentials.get("host", "")
        port = int(decrypted_credentials.get("port", 587))
        user = decrypted_credentials.get("username", "")
        pwd = decrypted_credentials.get("password", "")
        use_tls = bool(decrypted_credentials.get("use_tls", True))

        validate_hostname(host, port=port)

        try:
            if port == 465:
                server = smtplib.SMTP_SSL(host, port, timeout=8.0)
            else:
                server = smtplib.SMTP(host, port, timeout=8.0)

            with server:
                server.ehlo()
                if use_tls and server.has_extn("STARTTLS"):
                    ctx = ssl.create_default_context()
                    server.starttls(context=ctx)
                    server.ehlo()
                server.login(user, pwd)
                return {"ok": True, "message": f"Successfully authenticated with SMTP server {host}."}
        except smtplib.SMTPAuthenticationError as exc:
            raise InvalidCredentials(f"SMTP authentication failed: {exc}")
        except ssl.SSLError as exc:
            raise TlsError(f"SMTP TLS negotiation failed: {exc}")
        except Exception as exc:
            raise Unreachable(f"Could not connect to SMTP server: {exc}")
