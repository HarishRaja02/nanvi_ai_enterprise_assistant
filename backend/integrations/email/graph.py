from __future__ import annotations
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import quote, urlparse
import base64
import httpx

from .models import (
    AttachmentMetadata, EmailAddress, EmailMessage, EmailProviderContext,
    EmailSearchRequest, EmailSearchPage, EmailThread,
)
from .provider import EmailProvider
from .exceptions import EmailProviderError, EmailRateLimited, EmailValidationError
from backend.core.resilience import RetryPolicy, retry_idempotent
from backend.observability.logging import log_event
import logging
import time

logger = logging.getLogger(__name__)


GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_GRAPH_HOST = "graph.microsoft.com"
_GRAPH_MESSAGES_PATH = "/v1.0/me/messages"


def _address(value: dict[str, Any] | None) -> EmailAddress | None:
    if not value:
        return None
    ea = value.get("emailAddress") or {}
    address = ea.get("address")
    return EmailAddress(address=address, name=ea.get("name")) if address else None


def _addresses(values: list[dict[str, Any]] | None) -> tuple[EmailAddress, ...]:
    result = []
    for value in values or []:
        item = _address(value)
        if item:
            result.append(item)
    return tuple(result)


def _dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EmailProviderError("Microsoft Graph returned an invalid email timestamp") from exc


def _message(data: dict[str, Any]) -> EmailMessage:
    attachments = tuple(
        AttachmentMetadata(
            id=str(a.get("id", "")), name=str(a.get("name", "")),
            content_type=a.get("contentType"), size_bytes=a.get("size"),
            is_inline=bool(a.get("isInline", False)),
        )
        for a in data.get("attachments", [])
        if isinstance(a, dict)
    )
    return EmailMessage(
        id=str(data.get("id", "")), conversation_id=data.get("conversationId"),
        subject=data.get("subject") or "", sender=_address(data.get("from")),
        to_recipients=_addresses(data.get("toRecipients")),
        cc_recipients=_addresses(data.get("ccRecipients")),
        received_at=_dt(data.get("receivedDateTime")), sent_at=_dt(data.get("sentDateTime")),
        body_preview=data.get("bodyPreview"),
        has_attachments=bool(data.get("hasAttachments", False)), attachments=attachments,
        web_link=data.get("webLink"), source="microsoft_graph",
    )


def _cursor_encode(next_link: str) -> str:
    raw = next_link.encode("utf-8")
    if len(raw) > 8192:
        raise EmailProviderError("Microsoft Graph returned an unexpectedly large continuation link")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _cursor_decode(cursor: str) -> str:
    if not cursor or len(cursor) > 12000:
        raise EmailValidationError("Invalid email pagination cursor")
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        url = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        raise EmailValidationError("Invalid email pagination cursor") from exc
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != _GRAPH_HOST or parsed.port not in (None, 443):
        raise EmailValidationError("Invalid email pagination cursor")
    if parsed.path != _GRAPH_MESSAGES_PATH:
        raise EmailValidationError("Invalid email pagination cursor")
    if parsed.fragment or parsed.username or parsed.password:
        raise EmailValidationError("Invalid email pagination cursor")
    return url


class MicrosoftGraphEmailProvider(EmailProvider):
    """Microsoft Graph delegated-mail provider.

    The caller supplies a short-lived delegated access token in an opaque context.
    This class does not expose client secrets, refresh tokens, passwords, or Graph
    credentials to callers or future AI tools.
    """

    def __init__(self, http_client: httpx.Client | None = None, timeout: float = 15.0, retry_policy: RetryPolicy | None = None):
        self._client = http_client or httpx.Client(timeout=timeout)
        self._retry_policy = retry_policy or RetryPolicy(attempts=2)

    def _get(self, context: EmailProviderContext, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if not context.access_token:
            raise EmailProviderError("A delegated Graph access token is required")
        def operation():
            try:
                response = self._client.get(
                    f"{GRAPH_BASE}{path}", params=params,
                    headers={"Authorization": f"Bearer {context.access_token}", "Accept": "application/json"},
                )
                return self._handle_response(response)
            except httpx.TimeoutException as exc:
                raise EmailProviderError("Microsoft Graph request timed out") from exc
            except httpx.HTTPError as exc:
                raise EmailProviderError("Microsoft Graph request failed") from exc

        started = time.perf_counter()
        try:
            data = retry_idempotent(operation, policy=self._retry_policy, retry_if=lambda exc: self._retryable(exc))
        except EmailRateLimited:
            log_event(logger, "external_api_failed", logging.WARNING, provider="microsoft_graph", operation="mail_read", failure="rate_limited", duration_ms=round((time.perf_counter() - started) * 1000, 2))
            raise
        except EmailProviderError as exc:
            log_event(logger, "external_api_failed", logging.ERROR, provider="microsoft_graph", operation="mail_read", failure=type(exc).__name__, duration_ms=round((time.perf_counter() - started) * 1000, 2))
            raise
        log_event(logger, "external_api_completed", provider="microsoft_graph", operation="mail_read", duration_ms=round((time.perf_counter() - started) * 1000, 2))
        return data

    @staticmethod
    def _retryable(exc: Exception) -> bool:
        if isinstance(exc, EmailProviderError) and not isinstance(exc, EmailRateLimited):
            cause = exc.__cause__
            return isinstance(cause, (httpx.TimeoutException, httpx.TransportError))
        return False

    def _get_url(self, context: EmailProviderContext, url: str) -> dict[str, Any]:
        if not context.access_token:
            raise EmailProviderError("A delegated Graph access token is required")
        validated = _cursor_decode(_cursor_encode(url))
        def operation():
            try:
                response = self._client.get(
                    validated,
                    headers={"Authorization": f"Bearer {context.access_token}", "Accept": "application/json"},
                )
                return self._handle_response(response)
            except httpx.TimeoutException as exc:
                raise EmailProviderError("Microsoft Graph request timed out") from exc
            except httpx.HTTPError as exc:
                raise EmailProviderError("Microsoft Graph request failed") from exc
        started = time.perf_counter()
        try:
            data = retry_idempotent(operation, policy=self._retry_policy, retry_if=lambda exc: self._retryable(exc))
        except EmailRateLimited:
            log_event(logger, "external_api_failed", logging.WARNING, provider="microsoft_graph", operation="mail_read_pagination", failure="rate_limited", duration_ms=round((time.perf_counter() - started) * 1000, 2))
            raise
        except EmailProviderError as exc:
            log_event(logger, "external_api_failed", logging.ERROR, provider="microsoft_graph", operation="mail_read_pagination", failure=type(exc).__name__, duration_ms=round((time.perf_counter() - started) * 1000, 2))
            raise
        log_event(logger, "external_api_completed", provider="microsoft_graph", operation="mail_read_pagination", duration_ms=round((time.perf_counter() - started) * 1000, 2))
        return data

    @staticmethod
    def _handle_response(response: httpx.Response) -> dict[str, Any]:
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            retry_seconds: int | None = None
            if retry_after:
                try:
                    retry_seconds = max(0, int(retry_after))
                except ValueError:
                    try:
                        dt = parsedate_to_datetime(retry_after)
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        retry_seconds = max(0, int((dt - datetime.now(timezone.utc)).total_seconds()))
                    except (TypeError, ValueError, OverflowError):
                        retry_seconds = None
            raise EmailRateLimited(retry_after_seconds=retry_seconds)
        if response.status_code in (401, 403):
            raise EmailProviderError("Microsoft Graph rejected the mailbox authorization")
        if response.status_code >= 400:
            raise EmailProviderError(f"Microsoft Graph request failed with HTTP {response.status_code}")
        try:
            data = response.json()
        except ValueError as exc:
            raise EmailProviderError("Microsoft Graph returned an invalid response") from exc
        if not isinstance(data, dict):
            raise EmailProviderError("Microsoft Graph returned an unexpected response")
        return data

    @staticmethod
    def _validate_request(request: EmailSearchRequest) -> None:
        if request.max_results < 1 or request.max_results > 100:
            raise EmailValidationError("max_results must be between 1 and 100")
        for name in ("query", "sender", "recipient", "subject"):
            value = getattr(request, name)
            if value is not None and (not value.strip() or len(value) > 320):
                raise EmailValidationError(f"{name} is invalid")
        if request.after and request.before and request.after >= request.before:
            raise EmailValidationError("after must be earlier than before")

    def search_page(self, context: EmailProviderContext, request: EmailSearchRequest) -> EmailSearchPage:
        self._validate_request(request)
        if request.cursor:
            data = self._get_url(context, _cursor_decode(request.cursor))
        else:
            params: dict[str, Any] = {
                "$top": request.max_results,
                "$select": "id,conversationId,subject,from,toRecipients,ccRecipients,receivedDateTime,sentDateTime,bodyPreview,hasAttachments,webLink",
                "$orderby": "receivedDateTime desc",
            }
            filters = []
            if request.sender:
                escaped = request.sender.replace("'", "''")
                filters.append(f"from/emailAddress/address eq '{escaped}'")
            if request.recipient:
                escaped = request.recipient.replace("'", "''")
                filters.append(f"(toRecipients/any(r:r/emailAddress/address eq '{escaped}') or ccRecipients/any(r:r/emailAddress/address eq '{escaped}'))")
            if request.subject:
                escaped = request.subject.replace("'", "''")
                filters.append(f"subject eq '{escaped}'")
            if request.after:
                filters.append(f"receivedDateTime ge {request.after.isoformat()}")
            if request.before:
                filters.append(f"receivedDateTime lt {request.before.isoformat()}")
            if request.has_attachments is not None:
                filters.append(f"hasAttachments eq {'true' if request.has_attachments else 'false'}")
            if filters:
                params["$filter"] = " and ".join(filters)
            if request.query:
                phrase = request.query.replace('"', '\\"')
                params["$search"] = f'"{phrase}"'
                params["$orderby"] = None
            data = self._get(context, "/me/messages", params)
        messages = tuple(_message(item) for item in data.get("value", []) if isinstance(item, dict))
        next_link = data.get("@odata.nextLink")
        next_cursor = _cursor_encode(next_link) if isinstance(next_link, str) and next_link else None
        return EmailSearchPage(messages=messages, next_cursor=next_cursor)

    def search(self, context: EmailProviderContext, request: EmailSearchRequest) -> list[EmailMessage]:
        return list(self.search_page(context, request).messages)

    def get_thread(self, context: EmailProviderContext, conversation_id: str) -> EmailThread:
        if not conversation_id or len(conversation_id) > 512:
            raise EmailValidationError("Invalid conversation id")
        escaped = conversation_id.replace("'", "''")
        params = {
            "$filter": f"conversationId eq '{escaped}'",
            "$orderby": "receivedDateTime asc",
            "$top": 100,
            "$select": "id,conversationId,subject,from,toRecipients,ccRecipients,receivedDateTime,sentDateTime,bodyPreview,hasAttachments,webLink",
        }
        data = self._get(context, "/me/messages", params)
        messages = tuple(_message(item) for item in data.get("value", []) if isinstance(item, dict))
        return EmailThread(conversation_id=conversation_id, messages=messages)

    def get_message(self, context: EmailProviderContext, message_id: str) -> EmailMessage:
        if not message_id or len(message_id) > 1024:
            raise EmailValidationError("Invalid message id")
        params = {"$select": "id,conversationId,subject,from,toRecipients,ccRecipients,receivedDateTime,sentDateTime,bodyPreview,hasAttachments,webLink"}
        safe_message_id = quote(message_id, safe="")
        return _message(self._get(context, f"/me/messages/{safe_message_id}", params))
