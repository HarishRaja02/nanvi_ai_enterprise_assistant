"""EmailAgent implementation for Google Gmail and Workspace message management."""
from __future__ import annotations

import logging
import re
from typing import Any

from backend.agents.interfaces import Agent
from backend.agents.models import AgentRequest, AgentResponse, Capability
from backend.agents.security_gateway import SecureToolGateway
from backend.core.config import settings
from backend.sources.models import SourceReference, SourceType
from backend.sources.service import SourceReferenceService

logger = logging.getLogger(__name__)


class EmailAgent(Agent):
    capability = Capability.EMAIL

    def __init__(
        self,
        email_service=None,
        source_references: SourceReferenceService | None = None,
        gateway: SecureToolGateway | None = None,
    ):
        self._email = email_service
        self._sources = source_references
        self._gateway = gateway

    def run(self, request: AgentRequest) -> AgentResponse:
        if self._email is None:
            return AgentResponse(
                self.capability,
                "Google Gmail service is not configured for this environment.",
                (),
            )

        from backend.integrations.email.models import EmailProviderContext, EmailSearchRequest

        # Check if user specifically requested email
        is_explicit_email = bool(re.search(r"\b(email|emails|mail|inbox|gmail)\b", request.query, flags=re.IGNORECASE))

        # Strip common conversational noise words to get the actual target topic / sender
        noise_pattern = r"\b(check|show|get|read|search|find|view|list|any|my|me|the|our|for|about|recent|resent|latest|last|new|incoming|unread|emails?|mails?|inbox|gmail|files?|documents?)\b"
        clean_q = re.sub(noise_pattern, " ", request.query, flags=re.IGNORECASE)
        clean_q = re.sub(r"[\"\'\?\!\.,;:]", " ", clean_q)
        clean_q = " ".join(clean_q.split()).strip()
        filename_match = re.search(
            r"(?i)(?<![\w])([A-Za-z0-9_-]+\.(?:pdf|docx|xlsx|csv|txt|md|pptx))(?![\w])",
            request.query,
        )
        email_search_query = f"filename:{filename_match.group(1)}" if filename_match else clean_q

        from backend.integrations.email.user_account_service import get_user_email_account_service
        account_svc = get_user_email_account_service()
        user_mailbox = account_svc.get_active_account(request.user.user_id)
        if not user_mailbox:
            try:
                from backend.connections.manager import get_connection_manager
                from backend.security.models import UserIdentity
                from backend.security.authorization.rbac import Role
                cm = get_connection_manager()
                mock_u = UserIdentity(
                    subject=request.user.user_id,
                    issuer="internal",
                    tenant_id=request.user.tenant_id or "enterprise-tenant",
                    roles=frozenset({Role.EMPLOYEE}),
                )
                conn_client = cm.get_client_for_agent("google", mock_u)
                if hasattr(conn_client, "_account") and conn_client._account:
                    user_mailbox = conn_client._account
            except Exception:
                pass

        import backend.core.config as cfg
        if not user_mailbox and (cfg.settings.is_production or not cfg.settings.allows_synthetic_data):
            return AgentResponse(
                self.capability,
                "No Gmail account is connected. Click Connect Mailbox to connect your Google Workspace / Gmail account.",
                (),
                data_source="live",
            )

        context = EmailProviderContext(
            user_id=request.user.user_id,
            tenant_id=request.user.tenant_id,
            access_token="live_auth",
            granted_scopes=frozenset({"gmail.readonly", "email"}),
        )

        messages = []
        search_failed = False
        if email_search_query:
            try:
                messages = self._email.search(request.user, context, EmailSearchRequest(query=email_search_query, max_results=5))
            except Exception as exc:
                logger.warning("Gmail search for '%s' failed: %s", email_search_query, exc)
                search_failed = True

        # Fallback to recent inbox messages if specific search yielded nothing or if query was just asking to check mail
        if not messages and (is_explicit_email or not clean_q):
            try:
                messages = self._email.search(request.user, context, EmailSearchRequest(query="", max_results=5))
            except Exception as exc:
                logger.warning("Gmail recent inbox fetch failed: %s", exc)

        if not messages:
            if search_failed:
                return AgentResponse(
                    self.capability,
                    "Gmail search failed because mailbox access was denied or unavailable. Reconnect the mailbox in **Settings** and grant Gmail read access.",
                    (),
                    data_source="live",
                )
            if is_explicit_email:
                if user_mailbox:
                    return AgentResponse(
                        self.capability,
                        f"No relevant messages or email attachments found in your connected mailbox (**{user_mailbox.email_address}**).",
                        (),
                        data_source="live",
                    )
                return AgentResponse(
                    self.capability,
                    "No Gmail account is connected. Click Connect Mailbox to connect your Google Workspace / Gmail account.",
                    (),
                    data_source="live",
                )
            if any(w in request.query.casefold() for w in ("resume", "candidate", "applicant", "hiring", "interview")):
                return AgentResponse(
                    self.capability,
                    "No relevant Google Gmail messages or email attachments found in your authorized mailbox.",
                    (),
                    data_source="live",
                )
            return AgentResponse(self.capability, "", (), data_source="live")

        is_synthetic = not bool(user_mailbox)
        if is_synthetic:
            account_tag = " (Synthetic Demo Inbox)"
            lines = [
                f"Here are sample Google Gmail messages{account_tag} for **\"{request.query}\"** (Note: Showing synthetic sample data because no live mailbox is connected):",
                "",
            ]
        else:
            account_tag = f" (**{user_mailbox.email_address}**)"
            lines = [
                f"Here are the relevant Google Gmail messages{account_tag} for **\"{request.query}\"**:",
                "",
            ]

        sources: list[SourceReference] = []

        for idx, msg in enumerate(messages, start=1):
            sender_str = f"{msg.sender.name} <{msg.sender.address}>" if msg.sender else "Unknown Sender"
            date_str = msg.received_at.strftime("%b %d, %Y") if msg.received_at else "Recent"
            lines.append(f"{idx}. 📧 **{msg.subject}**")
            lines.append(f"   • *From:* {sender_str} | *Date:* {date_str}")
            if msg.body_preview:
                lines.append(f"   • *Preview:* {msg.body_preview}")
            if msg.attachments:
                attachment_names = ", ".join(f"`{attachment.name}`" for attachment in msg.attachments)
                lines.append(f"   • *Attachments:* {attachment_names}")
            lines.append("")

            sources.append(
                SourceReference(
                    reference_id=f"gmail-{msg.id}",
                    source_type=SourceType.EMAIL,
                    display_name=f"[Gmail] {msg.subject}",
                    title=f"{msg.subject}",
                    location=f"Gmail: {sender_str}",
                    href=msg.web_link,
                )
            )
            for attachment in msg.attachments:
                sources.append(
                    SourceReference(
                        reference_id=f"gmail-{msg.id}-attachment-{attachment.id}",
                        source_type=SourceType.EMAIL,
                        display_name=f"[Gmail attachment] {attachment.name}",
                        title=attachment.name,
                        location=f"Gmail: {msg.subject} — {sender_str}",
                        mime_type=attachment.content_type,
                        href=msg.web_link,
                    )
                )

        return AgentResponse(
            self.capability,
            "\n".join(lines),
            tuple(sources),
            data_source="synthetic" if is_synthetic else "live",
        )
