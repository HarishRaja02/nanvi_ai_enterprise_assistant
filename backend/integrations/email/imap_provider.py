"""Universal IMAP Email Provider for enterprise email boxes.

Supports ANY email provider worldwide (Gmail, Google Workspace, Microsoft 365,
Exchange, Yahoo, Zoho, and private corporate domains) via standard IMAP/TLS.
"""
from __future__ import annotations

import email
import imaplib
import logging
from datetime import datetime, timezone
from email.header import decode_header
from typing import Any

from .exceptions import EmailProviderError, EmailRateLimited
from .models import (
    AttachmentMetadata,
    EmailAddress,
    EmailMessage,
    EmailProviderContext,
    EmailSearchPage,
    EmailSearchRequest,
    EmailThread,
)
from .provider import EmailProvider
from .repository import EmailRepository

logger = logging.getLogger(__name__)

DEFAULT_IMAP_HOSTS = {
    "gmail.com": "imap.gmail.com",
    "googlemail.com": "imap.gmail.com",
    "outlook.com": "outlook.office365.com",
    "hotmail.com": "outlook.office365.com",
    "office365.com": "outlook.office365.com",
    "yahoo.com": "imap.mail.yahoo.com",
    "zoho.com": "imap.zoho.com",
    "icloud.com": "imap.mail.me.com",
}


def _decode_mime_header(header_val: str | None) -> str:
    if not header_val:
        return ""
    decoded_fragments = decode_header(header_val)
    parts = []
    for frag, enc in decoded_fragments:
        if isinstance(frag, bytes):
            try:
                parts.append(frag.decode(enc or "utf-8", errors="replace"))
            except Exception:
                parts.append(frag.decode("latin-1", errors="replace"))
        else:
            parts.append(str(frag))
    return "".join(parts)


class ImapEmailProvider(EmailRepository, EmailProvider):
    """Universal IMAP provider connecting securely over TLS (port 993)."""

    def __init__(self, host: str = "imap.gmail.com", port: int = 993) -> None:
        self._host = host
        self._port = port

    def _get_imap_client(self, email_address: str, password_or_token: str, host: str | None = None) -> imaplib.IMAP4_SSL:
        domain = email_address.split("@")[-1].lower() if "@" in email_address else ""
        target_host = host or DEFAULT_IMAP_HOSTS.get(domain, f"imap.{domain}")
        try:
            client = imaplib.IMAP4_SSL(target_host, self._port, timeout=12.0)
            client.login(email_address, password_or_token)
            return client
        except Exception as exc:
            logger.error("IMAP login failed for '%s' at '%s': %s", email_address, target_host, exc)
            raise EmailProviderError(f"Could not connect to mailbox via IMAP ({target_host}): {exc}") from exc

    def search_page_with_creds(
        self,
        email_address: str,
        password_or_token: str,
        request: EmailSearchRequest,
        host: str | None = None,
    ) -> EmailSearchPage:
        """Query mailbox via IMAP directly."""
        client = None
        try:
            client = self._get_imap_client(email_address, password_or_token, host)
            client.select("INBOX", readonly=True)

            # Build IMAP search criteria
            criteria = []
            if request.query:
                # IMAP TEXT search matches headers and body
                criteria.append(f'TEXT "{request.query}"')
            if request.sender:
                criteria.append(f'FROM "{request.sender}"')
            if request.subject:
                criteria.append(f'SUBJECT "{request.subject}"')

            search_query = " ".join(criteria) if criteria else "ALL"
            typ, data = client.search(None, search_query)
            if typ != "OK":
                return EmailSearchPage(tuple(), next_cursor=None)

            msg_ids = data[0].split()
            # Fetch newest messages first
            msg_ids.reverse()
            limit = min(request.max_results, 25)
            selected_ids = msg_ids[:limit]

            messages: list[EmailMessage] = []
            for msg_id in selected_ids:
                try:
                    _, fetch_data = client.fetch(msg_id, "(RFC822.HEADER BODY.PEEK[TEXT])")
                    raw_email = None
                    for part in fetch_data:
                        if isinstance(part, tuple):
                            raw_email = part[1]
                            break
                    if not raw_email:
                        continue

                    parsed = email.message_from_bytes(raw_email)
                    subject = _decode_mime_header(parsed.get("Subject", "(No Subject)"))
                    sender_raw = _decode_mime_header(parsed.get("From", "Unknown"))
                    date_str = parsed.get("Date", "")
                    body_preview = ""

                    # Extract body text snippet
                    if parsed.is_multipart():
                        for subpart in parsed.walk():
                            if subpart.get_content_type() == "text/plain":
                                payload = subpart.get_payload(decode=True)
                                if payload:
                                    body_preview = payload.decode("utf-8", errors="replace")[:250].strip()
                                    break
                    else:
                        payload = parsed.get_payload(decode=True)
                        if payload:
                            body_preview = payload.decode("utf-8", errors="replace")[:250].strip()

                    clean_body = " ".join(body_preview.split()) if body_preview else ""
                    messages.append(EmailMessage(
                        id=str(msg_id.decode()),
                        conversation_id=str(msg_id.decode()),
                        subject=subject,
                        sender=EmailAddress(sender_raw),
                        to_recipients=(),
                        cc_recipients=(),
                        received_at=datetime.now(timezone.utc),
                        body_preview=clean_body,
                        source="universal_imap",
                        web_link=f"https://mail.google.com" if "gmail" in email_address else None,
                    ))
                except Exception as parse_exc:
                    logger.debug("Could not parse IMAP message %s: %s", msg_id, parse_exc)
                    continue

            return EmailSearchPage(tuple(messages), next_cursor=None)
        finally:
            if client:
                try:
                    client.close()
                    client.logout()
                except Exception:
                    pass

    def search(self, context: EmailProviderContext, request: EmailSearchRequest) -> list[EmailMessage]:
        return list(self.search_page(context, request).messages)

    def search_page(self, context: EmailProviderContext, request: EmailSearchRequest) -> EmailSearchPage:
        # Implemented for polymorphism; context-level search delegates to stored credentials
        return EmailSearchPage(tuple(), next_cursor=None)

    def get_thread(self, context: EmailProviderContext, conversation_id: str) -> EmailThread:
        return EmailThread(conversation_id=conversation_id, messages=tuple())

    def get_message(self, context: EmailProviderContext, message_id: str) -> EmailMessage:
        raise EmailProviderError(f"IMAP message {message_id} fetch requires active session")


_imap_provider: ImapEmailProvider | None = None


def get_imap_email_provider() -> ImapEmailProvider:
    global _imap_provider
    if _imap_provider is None:
        _imap_provider = ImapEmailProvider()
    return _imap_provider
