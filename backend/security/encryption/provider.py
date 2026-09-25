from __future__ import annotations

from abc import ABC, abstractmethod


class EncryptionProvider(ABC):
    """Provider-independent interface for encryption/decryption."""

    @abstractmethod
    def encrypt(self, plaintext: bytes) -> bytes:
        raise NotImplementedError

    @abstractmethod
    def decrypt(self, ciphertext: bytes) -> bytes:
        raise NotImplementedError
