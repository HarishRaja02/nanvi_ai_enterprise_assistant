from __future__ import annotations
from abc import ABC, abstractmethod
from .models import EmailMessage, EmailSearchRequest, EmailSearchPage, EmailThread, EmailProviderContext


class EmailProvider(ABC):
    """Provider-neutral delegated mailbox contract. No credential access is exposed."""

    @abstractmethod
    def search(self, context: EmailProviderContext, request: EmailSearchRequest) -> list[EmailMessage]:
        raise NotImplementedError

    def search_page(self, context: EmailProviderContext, request: EmailSearchRequest) -> EmailSearchPage:
        return EmailSearchPage(tuple(self.search(context, request)), None)

    @abstractmethod
    def get_thread(self, context: EmailProviderContext, conversation_id: str) -> EmailThread:
        raise NotImplementedError

    @abstractmethod
    def get_message(self, context: EmailProviderContext, message_id: str) -> EmailMessage:
        raise NotImplementedError
