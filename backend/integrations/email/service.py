from __future__ import annotations
from backend.security.audit import AuditLogger
from backend.security.authorization import AuthorizationService, Permission, Resource, UserAttributes
from backend.security.rate_limiting import RateLimiter, RateLimitExceeded
from .exceptions import EmailAccessDenied, EmailRateLimited
from .models import EmailMessage, EmailProviderContext, EmailSearchRequest, EmailSearchPage, EmailThread
from .repository import EmailRepository
from backend.observability.logging import log_event
import logging
import time

logger = logging.getLogger(__name__)


class EmailService:
    """Security-aware email application service; AI/tools call this, never Graph directly."""

    RESOURCE_ID = "user-mailbox"

    def __init__(self, repository: EmailRepository, authorization: AuthorizationService,
                 audit_logger: AuditLogger, rate_limiter: RateLimiter | None = None, source_service=None):
        self._repository = repository
        self._authorization = authorization
        self._audit = audit_logger
        self._rate_limiter = rate_limiter
        self._source_service = source_service

    def _authorize(self, user: UserAttributes, context: EmailProviderContext, operation: str) -> None:
        if not context.access_token:
            self._audit.record("email_access", "deny", user.user_id, user.tenant_id, self.RESOURCE_ID,
                               {"operation": operation, "reason": "Delegated mailbox token missing"})
            raise EmailAccessDenied("Email access denied")
        gmail_scopes = {"https://www.googleapis.com/auth/gmail.readonly", "gmail.readonly", "email", "Mail.Read"}
        if not context.granted_scopes or not (context.granted_scopes & gmail_scopes):
            self._audit.record("email_access", "deny", user.user_id, user.tenant_id, self.RESOURCE_ID,
                               {"operation": operation, "reason": "Required Google Gmail read scope is missing"})
            raise EmailAccessDenied("Email access denied: required Google Gmail scope is missing")
        if context.user_id != user.user_id or context.tenant_id != user.tenant_id:
            self._audit.record("email_access", "deny", user.user_id, user.tenant_id, self.RESOURCE_ID,
                               {"operation": operation, "reason": "Provider context does not match authenticated principal"})
            raise EmailAccessDenied("Email access denied: provider context mismatch")
        resource = Resource(resource_id=self.RESOURCE_ID, resource_type="email_mailbox",
                            tenant_id=context.tenant_id, owner_id=context.user_id)
        decision = self._authorization.authorize(user, Permission.EMAIL_READ, resource)
        if not decision.allowed:
            self._audit.record("email_access", "deny", user.user_id, user.tenant_id, self.RESOURCE_ID,
                               {"operation": operation, "reason": decision.reason})
            raise EmailAccessDenied("Email access denied by authorization policy")

    def _check_rate_limit(self, user: UserAttributes, operation: str) -> None:
        if self._rate_limiter is None:
            return
        try:
            self._rate_limiter.check(f"email:{user.tenant_id}:{user.user_id}")
        except RateLimitExceeded as exc:
            self._audit.record("email_access", "deny", user.user_id, user.tenant_id, self.RESOURCE_ID,
                               {"operation": operation, "reason": "application rate limit exceeded"})
            raise EmailRateLimited("Email request rate limit exceeded") from exc

    def search(self, user: UserAttributes, context: EmailProviderContext, request: EmailSearchRequest) -> list[EmailMessage]:
        return list(self.search_page(user, context, request).messages)

    def search_page(self, user: UserAttributes, context: EmailProviderContext, request: EmailSearchRequest) -> EmailSearchPage:
        self._authorize(user, context, "search")
        self._check_rate_limit(user, "search")
        started = time.perf_counter()
        try:
            page = self._repository.search_page(context, request)
        except EmailRateLimited:
            log_event(logger, "external_email_api_failed", logging.WARNING, actor_id=user.user_id, tenant_id=user.tenant_id, operation="search", failure="rate_limited", duration_ms=round((time.perf_counter() - started) * 1000, 2))
            self._audit.record("email_access", "deny", user.user_id, user.tenant_id, self.RESOURCE_ID,
                               {"operation": "search", "reason": "provider rate limit exceeded"})
            raise
        except Exception as exc:
            log_event(logger, "external_email_api_failed", logging.ERROR, actor_id=user.user_id, tenant_id=user.tenant_id, operation="search", failure=type(exc).__name__, duration_ms=round((time.perf_counter() - started) * 1000, 2))
            self._audit.record("email_access", "error", user.user_id, user.tenant_id, self.RESOURCE_ID,
                               {"operation": "search", "reason": type(exc).__name__, "duration_ms": round((time.perf_counter() - started) * 1000, 2)})
            from .exceptions import EmailProviderError
            if isinstance(exc, (EmailAccessDenied, EmailRateLimited, EmailProviderError, ValueError)):
                raise
            raise EmailProviderError("Email provider request failed") from exc
        log_event(logger, "external_email_api_completed", actor_id=user.user_id, tenant_id=user.tenant_id, operation="search", result_count=len(page.messages), duration_ms=round((time.perf_counter() - started) * 1000, 2))
        self._audit.record("email_access", "allow", user.user_id, user.tenant_id, self.RESOURCE_ID,
                           {"operation": "search", "result_count": len(page.messages),
                            "has_next_page": bool(page.next_cursor),
                            "date_filtered": bool(request.after or request.before),
                            "sender_filtered": bool(request.sender),
                            "recipient_filtered": bool(request.recipient),
                            "subject_filtered": bool(request.subject),
                            "attachment_filtered": request.has_attachments is not None,
                            "semantic_query": bool(request.query)})
        return page

    def source_references(self, user: UserAttributes, request_id: str,
                          messages: tuple[EmailMessage, ...]) -> tuple:
        """Create permission-checked, frontend-safe source references for email evidence."""
        if self._source_service is None:
            return ()
        from backend.analysis.models import DataLineage
        lineage = tuple(
            DataLineage(
                source_type="email",
                source_id=message.id,
                source_label=message.subject or "Email message",
                columns=(),
                query=None,
                tenant_id=user.tenant_id,
                owner_id=user.user_id,
                resource_type="email_mailbox",
            )
            for message in messages
        )
        return self._source_service.from_lineage(user, request_id, lineage)

    def get_thread(self, user: UserAttributes, context: EmailProviderContext, conversation_id: str) -> EmailThread:
        self._authorize(user, context, "thread")
        self._check_rate_limit(user, "thread")
        result = self._repository.get_thread(context, conversation_id)
        self._audit.record("email_access", "allow", user.user_id, user.tenant_id, self.RESOURCE_ID,
                           {"operation": "thread", "conversation_id_hash": hash(conversation_id), "message_count": len(result.messages)})
        return result

    def get_message(self, user: UserAttributes, context: EmailProviderContext, message_id: str) -> EmailMessage:
        self._authorize(user, context, "message")
        self._check_rate_limit(user, "message")
        result = self._repository.get_message(context, message_id)
        self._audit.record("email_access", "allow", user.user_id, user.tenant_id, self.RESOURCE_ID,
                           {"operation": "message", "message_id_hash": hash(message_id)})
        return result


class ProviderEmailRepository(EmailRepository):
    """Adapter that keeps the service independent of Microsoft Graph or Gmail."""
    def __init__(self, provider):
        self._provider = provider

    def search(self, context, request):
        return self._provider.search(context, request)

    def search_page(self, context, request):
        if hasattr(self._provider, "search_page"):
            return self._provider.search_page(context, request)
        # Backward-compatible provider adapter for simple test/dummy providers.
        from .models import EmailSearchPage
        return EmailSearchPage(tuple(self._provider.search(context, request)), None)

    def get_thread(self, context, conversation_id):
        return self._provider.get_thread(context, conversation_id)

    def get_message(self, context, message_id):
        return self._provider.get_message(context, message_id)
