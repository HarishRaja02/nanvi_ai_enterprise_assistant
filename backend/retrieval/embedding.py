from __future__ import annotations
from abc import ABC, abstractmethod
import hashlib
import math
import re
from typing import Sequence


class EmbeddingProvider(ABC):
    """Provider-neutral embedding contract. API keys/model credentials stay outside retrieval."""

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        raise NotImplementedError

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(text) for text in texts]


class DeterministicEmbeddingProvider(EmbeddingProvider):
    """Fast, deterministic, normalized embedding provider for CI, evals, and reproducible testing.

    Generates stable, semantic-sensitive unit vectors of fixed dimension (default 384)
    based on character n-grams and token hashes.
    """

    def __init__(self, dimensions: int = 384) -> None:
        if dimensions <= 0:
            raise ValueError("dimensions must be positive")
        self._dimensions = dimensions

    def embed(self, text: str) -> list[float]:
        if not text:
            return [0.0] * self._dimensions

        vector = [0.0] * self._dimensions
        words = re.findall(r"\w+", text.lower())
        if not words:
            words = [text.strip().lower()]

        for word in words:
            # Word-level hash contribution
            h = int(hashlib.sha256(word.encode("utf-8")).hexdigest(), 16)
            idx = h % self._dimensions
            sign = 1.0 if ((h >> 8) & 1) == 1 else -1.0
            vector[idx] += sign * (1.0 + math.log(1.0 + len(word)))

            # Character 3-gram contributions for subword semantics
            if len(word) >= 3:
                for i in range(len(word) - 2):
                    ngram = word[i : i + 3]
                    nh = int(hashlib.md5(ngram.encode("utf-8")).hexdigest(), 16)
                    nidx = nh % self._dimensions
                    nsign = 1.0 if ((nh >> 4) & 1) == 1 else -1.0
                    vector[nidx] += nsign * 0.5

        # L2 Normalize
        norm = math.sqrt(sum(x * x for x in vector))
        if norm > 0.0:
            return [x / norm for x in vector]
        return vector


class RemoteEmbeddingProvider(EmbeddingProvider):
    """Embeddings via standard HTTP/OpenAI-compatible embedding endpoint."""

    def __init__(self, api_key: str, endpoint: str = "https://api.openai.com/v1/embeddings", model: str = "text-embedding-3-small") -> None:
        if not api_key:
            raise ValueError("api_key is required for RemoteEmbeddingProvider")
        self._api_key = api_key
        self._endpoint = endpoint
        self._model = model

    def embed(self, text: str) -> list[float]:
        results = self.embed_many([text])
        return results[0] if results else []

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        import httpx

        response = httpx.post(
            self._endpoint,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json={
                "input": texts,
                "model": self._model,
            },
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json()
        embeddings = [item["embedding"] for item in data.get("data", [])]
        return embeddings
