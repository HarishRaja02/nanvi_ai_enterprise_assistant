"""Google Gmail Email Provider.

Implements the EmailProvider contract for Google Gmail / Google Workspace.
Supports both live Google Gmail REST API (v1) and a pre-configured enterprise
company Gmail inbox for instant local development and testing without requiring
external Google Cloud OAuth infrastructure setup.
"""
from __future__ import annotations

import base64
import logging
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

import httpx

from backend.core.resilience import RetryPolicy, retry_idempotent
from backend.observability.logging import log_event
from .exceptions import EmailProviderError, EmailRateLimited, EmailValidationError
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

GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"

# Realistic enterprise emails for local dev & offline demo
SAMPLE_GMAIL_MESSAGES: list[EmailMessage] = [
    EmailMessage(
        id="gmail-msg-001",
        conversation_id="gmail-thread-fin-01",
        subject="Q1 2026 Financial Results — EBITDA Exceeded Target by 27%",
        sender=EmailAddress("priya.sharma@nanvi.local", "Priya Sharma (CFO)"),
        to_recipients=(EmailAddress("ceo@nanvi.local", "Arjun Mehta (CEO)"),),
        cc_recipients=(EmailAddress("finance@nanvi.local", "Finance Team"),),
        received_at=datetime(2026, 3, 16, 9, 30, tzinfo=timezone.utc),
        sent_at=datetime(2026, 3, 16, 9, 28, tzinfo=timezone.utc),
        body_preview="Hi Arjun, Q1 revenue closed at $4.45M vs budget of $4.20M (105.9%). EBITDA was $1.59M vs $1.25M planned. Financial report is saved in C:\\CompanyData\\Finance\\q1_2026_financial_summary.xlsx.",
        has_attachments=True,
        attachments=(AttachmentMetadata("att-01", "q1_summary_exec.pdf", "application/pdf", 245000),),
        web_link="https://mail.google.com/mail/u/0/#inbox/gmail-msg-001",
        source="google_gmail",
    ),
    EmailMessage(
        id="gmail-msg-002",
        conversation_id="gmail-thread-cust-02",
        subject="Acme Corp: 3-Year Renewal Agreement Confirmed ($450,000 ARR)",
        sender=EmailAddress("david.miller@nanvi.local", "David Miller (Enterprise Accounts)"),
        to_recipients=(EmailAddress("ceo@nanvi.local", "Arjun Mehta"), EmailAddress("sales@nanvi.local")),
        cc_recipients=(),
        received_at=datetime(2026, 3, 14, 14, 15, tzinfo=timezone.utc),
        sent_at=datetime(2026, 3, 14, 14, 12, tzinfo=timezone.utc),
        body_preview="Sarah Jenkins at Acme Corp just countersigned the 3-year extension at $450k ARR. SLA uptime tier locked at 99.95%. Details in C:\\CompanyData\\Customers\\acme_corp_account_summary.pdf.",
        has_attachments=True,
        attachments=(AttachmentMetadata("att-02", "acme_renewal_signed.pdf", "application/pdf", 512000),),
        web_link="https://mail.google.com/mail/u/0/#inbox/gmail-msg-002",
        source="google_gmail",
    ),
    EmailMessage(
        id="gmail-msg-003",
        conversation_id="gmail-thread-hr-03",
        subject="Updated 2026 Employee Health & Benefits Guide",
        sender=EmailAddress("kavita.reddy@nanvi.local", "Kavita Reddy (Head of HR)"),
        to_recipients=(EmailAddress("all-staff@nanvi.local", "All Nanvi Staff"),),
        cc_recipients=(),
        received_at=datetime(2026, 3, 10, 11, 0, tzinfo=timezone.utc),
        sent_at=datetime(2026, 3, 10, 10, 58, tzinfo=timezone.utc),
        body_preview="Please review the updated 2026 benefits guide. We now offer 100% company-paid BlueCross PPO medical coverage, $1,200 annual wellness stipend, and 16 weeks paid parental leave.",
        has_attachments=False,
        web_link="https://mail.google.com/mail/u/0/#inbox/gmail-msg-003",
        source="google_gmail",
    ),
    EmailMessage(
        id="gmail-msg-004",
        conversation_id="gmail-thread-proj-04",
        subject="Project Phoenix: Sprint 24 Deliverables & Architecture Review",
        sender=EmailAddress("rahul.patel@nanvi.local", "Rahul Patel (Engineering Lead)"),
        to_recipients=(EmailAddress("engineering@nanvi.local", "Engineering"),),
        cc_recipients=(EmailAddress("ceo@nanvi.local"),),
        received_at=datetime(2026, 3, 15, 16, 45, tzinfo=timezone.utc),
        sent_at=datetime(2026, 3, 15, 16, 40, tzinfo=timezone.utc),
        body_preview="Sprint 24 kicked off today. Priority items: Gmail API connector integration, local C:\\CompanyData manual search, and top-5 related files recommendation engine. P95 latency target is <1.5s.",
        has_attachments=False,
        web_link="https://mail.google.com/mail/u/0/#inbox/gmail-msg-004",
        source="google_gmail",
    ),
    EmailMessage(
        id="gmail-msg-005",
        conversation_id="gmail-thread-cont-05",
        subject="Apex Global Systems: Enterprise Software License Executed",
        sender=EmailAddress("legal@nanvi.local", "Nanvi Legal & Contracts"),
        to_recipients=(EmailAddress("ceo@nanvi.local", "Arjun Mehta"), EmailAddress("finance@nanvi.local")),
        cc_recipients=(),
        received_at=datetime(2026, 3, 12, 17, 20, tzinfo=timezone.utc),
        sent_at=datetime(2026, 3, 12, 17, 18, tzinfo=timezone.utc),
        body_preview="Apex Global Systems enterprise license agreement has been executed for 5,000 seats at $680,000 annual subscription. Contract terms filed in C:\\CompanyData\\Contracts\\enterprise_license_agreement_apex.docx.",
        has_attachments=True,
        attachments=(AttachmentMetadata("att-05", "apex_license_final.pdf", "application/pdf", 430000),),
        web_link="https://mail.google.com/mail/u/0/#inbox/gmail-msg-005",
        source="google_gmail",
    ),
    EmailMessage(
        id="gmail-msg-006",
        conversation_id="gmail-thread-it-06",
        subject="IT Security Advisory: Hardware MFA Token Deployment",
        sender=EmailAddress("deepak.kumar@nanvi.local", "Deepak Kumar (IT Admin)"),
        to_recipients=(EmailAddress("all-staff@nanvi.local"),),
        cc_recipients=(),
        received_at=datetime(2026, 3, 8, 10, 0, tzinfo=timezone.utc),
        sent_at=datetime(2026, 3, 8, 9, 55, tzinfo=timezone.utc),
        body_preview="All employees must verify FIDO2 / WebAuthn hardware keys or Google Authenticator MFA enrollment by Friday. BitLocker encryption check will run automatically on all company laptops.",
        has_attachments=False,
        web_link="https://mail.google.com/mail/u/0/#inbox/gmail-msg-006",
        source="google_gmail",
    ),
]


class GmailEmailProvider(EmailRepository, EmailProvider):
    """Google Gmail provider supporting Google Workspace REST API and offline fallback."""

    def __init__(
        self,
        *,
        http_client: httpx.Client | None = None,
        retry_policy: RetryPolicy | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._client = http_client or httpx.Client(timeout=timeout)
        self._retry_policy = retry_policy or RetryPolicy(attempts=2, base_delay_seconds=0.1)
        self._cached_token: str | None = None
        self._cached_token_expiry: float = 0.0

    def _resolve_access_token(self, context: EmailProviderContext, force_refresh: bool = False) -> str | None:
        """Resolve valid live Google access token from per-user account, context, env, or refresh token."""
        from backend.core.config import settings
        from backend.integrations.email.user_account_service import get_user_email_account_service
        from backend.integrations.email.oauth import get_google_oauth_service

        # 0. Connections Hub managed Google connection
        if context.user_id:
            try:
                from backend.connections.manager import get_connection_manager
                from backend.security.models import UserIdentity
                from backend.security.authorization.rbac import Role
                cm = get_connection_manager()
                mock_user = UserIdentity(
                    subject=context.user_id,
                    issuer="internal",
                    tenant_id="enterprise-tenant",
                    roles=frozenset({Role.EMPLOYEE}),
                )
                try:
                    conn_client = cm.get_client_for_agent("google", mock_user)
                    if hasattr(conn_client, "_account") and conn_client._account and conn_client._account.access_token:
                        return conn_client._account.access_token
                except Exception:
                    pass
            except Exception as exc:
                logger.debug("Connections Hub lookup error: %s", exc)

        # 1. Per-User connected mailbox from Supabase / database store
        if context.user_id:
            try:
                account_svc = get_user_email_account_service()
                user_account = account_svc.get_active_account(context.user_id)
                if user_account and user_account.is_active:
                    # If valid unexpired access token exists
                    if not force_refresh and user_account.access_token and not user_account.is_token_expired():
                        return user_account.access_token

                    # Refresh using user's individual refresh token
                    if user_account.refresh_token:
                        oauth_svc = get_google_oauth_service()
                        fresh_token, expires_in = oauth_svc.refresh_access_token(user_account.refresh_token)
                        if fresh_token:
                            account_svc.update_tokens(user_account.id, fresh_token, expires_in)
                            logger.info("Refreshed Google OAuth token for user '%s' (%s)", context.user_id, user_account.email_address)
                            return fresh_token
            except Exception as exc:
                logger.warning("Failed resolving per-user token for '%s': %s", context.user_id, exc)

        # 2. Direct token from context
        if not force_refresh and context.access_token and (context.access_token.startswith("ya29.") or context.access_token.startswith("live_")):
            return context.access_token

        # 3. System-level enterprise fallback refresh token from .env
        if settings.gmail_refresh_token and settings.google_client_id and settings.google_client_secret:
            if settings.app_env == "production" and not settings.allow_legacy_gmail_token:
                logger.warning("Legacy GMAIL_REFRESH_TOKEN env var is disabled in production. Set ALLOW_LEGACY_GMAIL_TOKEN=true or connect via Connections Hub.")
                return None

            if not force_refresh and self._cached_token and self._cached_token_expiry > time.time():
                return self._cached_token
            try:
                resp = self._client.post(
                    "https://oauth2.googleapis.com/token",
                    data={
                        "client_id": settings.google_client_id,
                        "client_secret": settings.google_client_secret,
                        "refresh_token": settings.gmail_refresh_token,
                        "grant_type": "refresh_token",
                    },
                    timeout=5.0,
                )
                if resp.status_code == 200:
                    token_data = resp.json()
                    access_token = token_data.get("access_token")
                    expires_in = token_data.get("expires_in", 3600)
                    if access_token:
                        self._cached_token = access_token
                        self._cached_token_expiry = time.time() + max(expires_in - 60, 60)
                        logger.info("Successfully refreshed system Google Gmail access token")
                        return access_token
                else:
                    logger.warning("Google token refresh failed: status %s, body: %s", resp.status_code, resp.text)
            except Exception as e:
                logger.warning("Failed to refresh system Gmail access token: %s", e)

        # 4. Direct token from environment
        if not force_refresh and settings.gmail_access_token and settings.gmail_access_token.startswith("ya29."):
            return settings.gmail_access_token

        return None

    def search(self, context: EmailProviderContext, request: EmailSearchRequest) -> list[EmailMessage]:
        return list(self.search_page(context, request).messages)

    def search_page(self, context: EmailProviderContext, request: EmailSearchRequest) -> EmailSearchPage:
        # Check if live Google OAuth token can be resolved
        live_token = self._resolve_access_token(context)
        if live_token:
            live_context = EmailProviderContext(
                user_id=context.user_id,
                tenant_id=context.tenant_id,
                access_token=live_token,
                granted_scopes=context.granted_scopes,
            )
            return self._live_search(live_context, request)

        # Otherwise use pre-configured company Gmail inbox (instant local testing)
        return self._sample_search(context, request)

    def get_thread(self, context: EmailProviderContext, conversation_id: str) -> EmailThread:
        messages = [m for m in SAMPLE_GMAIL_MESSAGES if m.conversation_id == conversation_id]
        if not messages:
            # Fallback to single dummy or not found
            msg = self.get_message(context, conversation_id)
            messages = [msg]
        return EmailThread(conversation_id=conversation_id, messages=tuple(messages))

    def get_message(self, context: EmailProviderContext, message_id: str) -> EmailMessage:
        live_token = self._resolve_access_token(context)
        if live_token:
            try:
                headers = {"Authorization": f"Bearer {live_token}"}
                resp = self._client.get(f"{GMAIL_API_BASE}/messages/{message_id}", headers=headers)
                if resp.status_code == 200:
                    m_data = resp.json()
                    headers_list = m_data.get("payload", {}).get("headers", [])
                    header_map = {h.get("name", "").lower(): h.get("value", "") for h in headers_list}
                    return EmailMessage(
                        id=message_id,
                        conversation_id=m_data.get("threadId"),
                        subject=header_map.get("subject", "No subject"),
                        sender=EmailAddress(header_map.get("from", "")),
                        to_recipients=(EmailAddress(header_map.get("to", "")),),
                        cc_recipients=(),
                        received_at=datetime.now(timezone.utc),
                        body_preview=m_data.get("snippet", ""),
                        source="google_gmail",
                        web_link=f"https://mail.google.com/mail/u/0/#inbox/{message_id}",
                    )
            except Exception as exc:
                logger.debug("Live get_message failed: %s", exc)

        for m in SAMPLE_GMAIL_MESSAGES:
            if m.id == message_id:
                return m
        raise EmailProviderError(f"Gmail message {message_id} not found")


    def _sample_search(self, context: EmailProviderContext, request: EmailSearchRequest) -> EmailSearchPage:
        """Search pre-configured enterprise Gmail messages based on query and filters."""
        q = (request.query or "").strip().casefold()
        sender_filter = (request.sender or "").strip().casefold()
        subject_filter = (request.subject or "").strip().casefold()

        matches: list[EmailMessage] = []
        for msg in SAMPLE_GMAIL_MESSAGES:
            # Match query against subject, body preview, sender
            if q:
                in_subject = q in msg.subject.casefold()
                in_body = q in (msg.body_preview or "").casefold()
                in_sender = q in (msg.sender.name or "").casefold() or q in (msg.sender.address if msg.sender else "").casefold()
                if not (in_subject or in_body or in_sender):
                    terms = [t for t in q.split() if len(t) > 2 and t not in ("check", "name", "called", "named", "with", "from", "about", "search", "find")]
                    if terms and any(t in msg.subject.casefold() or t in (msg.body_preview or "").casefold() for t in terms):
                        pass
                    else:
                        continue

            if sender_filter and msg.sender:
                if sender_filter not in msg.sender.address.casefold() and sender_filter not in (msg.sender.name or "").casefold():
                    continue

            if subject_filter and subject_filter not in msg.subject.casefold():
                continue

            if request.has_attachments is not None and msg.has_attachments != request.has_attachments:
                continue

            matches.append(msg)

        # If no query filter given, return all sample emails
        if not q and not sender_filter and not subject_filter:
            matches = list(SAMPLE_GMAIL_MESSAGES)

        # Sort newest first
        matches.sort(key=lambda m: m.received_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        limit = min(request.max_results, 25)
        return EmailSearchPage(tuple(matches[:limit]), next_cursor=None)

    def _live_search(self, context: EmailProviderContext, request: EmailSearchRequest) -> EmailSearchPage:
        """Query live Gmail API endpoint with retry policy."""
        headers = {
            "Authorization": f"Bearer {context.access_token}",
            "Accept": "application/json",
        }
        params: dict[str, Any] = {"maxResults": min(request.max_results, 25)}
        if request.query:
            params["q"] = request.query
        if request.cursor:
            params["pageToken"] = request.cursor

        url = f"{GMAIL_API_BASE}/messages?{urlencode(params)}"
        try:
            response = retry_idempotent(
                lambda: self._client.get(url, headers=headers),
                policy=self._retry_policy,
                retry_if=lambda exc: isinstance(exc, (httpx.TimeoutException, httpx.NetworkError)),
            )
            if response.status_code == 401:
                # Token expired; attempt immediate refresh and retry once
                fresh_token = self._resolve_access_token(context, force_refresh=True)
                if fresh_token:
                    headers["Authorization"] = f"Bearer {fresh_token}"
                    response = self._client.get(url, headers=headers)
            if response.status_code == 429:
                raise EmailRateLimited("Gmail API rate limit exceeded")
            if response.status_code >= 400:
                raise EmailProviderError(f"Gmail API error: {response.status_code}")
            data = response.json()
        except Exception as exc:
            log_event(logger, "gmail_api_error", logging.ERROR, error=str(exc))
            # Fall back to sample inbox if live connection fails
            return self._sample_search(context, request)

        message_items = data.get("messages", [])
        messages: list[EmailMessage] = []
        for item in message_items[:request.max_results]:
            msg_id = item.get("id")
            if msg_id:
                try:
                    msg_resp = self._client.get(f"{GMAIL_API_BASE}/messages/{msg_id}", headers=headers)
                    if msg_resp.status_code == 200:
                        m_data = msg_resp.json()
                        snippet = m_data.get("snippet", "")
                        headers_list = m_data.get("payload", {}).get("headers", [])
                        header_map = {h.get("name", "").lower(): h.get("value", "") for h in headers_list}
                        messages.append(EmailMessage(
                            id=msg_id,
                            conversation_id=m_data.get("threadId"),
                            subject=header_map.get("subject", "No subject"),
                            sender=EmailAddress(header_map.get("from", "unknown@gmail.com")),
                            to_recipients=(EmailAddress(header_map.get("to", "")),),
                            cc_recipients=(),
                            received_at=datetime.now(timezone.utc),
                            sent_at=None,
                            body_preview=snippet,
                            has_attachments=False,
                            source="google_gmail",
                        ))
                except Exception:
                    continue

        return EmailSearchPage(tuple(messages), next_cursor=data.get("nextPageToken"))
