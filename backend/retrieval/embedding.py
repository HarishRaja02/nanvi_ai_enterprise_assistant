from __future__ import annotations
from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    """Provider-neutral embedding contract. API keys/model credentials stay outside retrieval."""

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        raise NotImplementedError

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(text) for text in texts]
