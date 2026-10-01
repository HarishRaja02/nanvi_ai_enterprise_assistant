from __future__ import annotations
from abc import ABC, abstractmethod
from .models import EmailMessage, EmailProviderContext, EmailSearchRequest, EmailSearchPage, EmailThread


class EmailRepository(ABC):
    """Repository boundary for mailbox operations. Implementations may call Graph/Gmail/etc."""

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
