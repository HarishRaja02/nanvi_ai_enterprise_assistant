from __future__ import annotations
from .models import EmailMessage, EmailProviderContext, EmailSearchRequest, EmailSearchPage, EmailThread
from .service import EmailService


class EmailTool:
    """AI capability boundary. Read-only: no send/write operation is exposed."""
    def __init__(self, service: EmailService):
        self._service = service

    def search(self, user, context: EmailProviderContext, request: EmailSearchRequest) -> list[EmailMessage]:
        return self._service.search(user, context, request)

    def search_page(self, user, context: EmailProviderContext, request: EmailSearchRequest) -> EmailSearchPage:
        return self._service.search_page(user, context, request)

    def source_references(self, user, request_id: str, messages: tuple[EmailMessage, ...]) -> tuple:
        return self._service.source_references(user, request_id, messages)

    def get_thread(self, user, context: EmailProviderContext, conversation_id: str) -> EmailThread:
        return self._service.get_thread(user, context, conversation_id)

    def get_message(self, user, context: EmailProviderContext, message_id: str) -> EmailMessage:
        return self._service.get_message(user, context, message_id)
