from __future__ import annotations

from backend.security.encryption.provider import EncryptionProvider


class EncryptionService:
    """Security-layer facade for future enterprise encryption providers."""

    def __init__(self, provider: EncryptionProvider) -> None:
        self._provider = provider

    def encrypt(self, plaintext: bytes) -> bytes:
        return self._provider.encrypt(plaintext)

    def decrypt(self, ciphertext: bytes) -> bytes:
        return self._provider.decrypt(ciphertext)
