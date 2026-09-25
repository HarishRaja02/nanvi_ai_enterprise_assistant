"""Credential encryption service using Fernet (AES-128-CBC + HMAC-SHA256).

Provides authenticated encryption with key-ID tracking for seamless rotation.
The master key comes from the environment; the app refuses to start in production
if it is missing or malformed.  In development, a missing key produces a loud
warning with setup instructions rather than silently falling back.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import secrets

from cryptography.fernet import Fernet, InvalidToken

from backend.security.encryption.provider import EncryptionProvider

logger = logging.getLogger(__name__)

# Sensitive key names that trigger redaction in logs/serializers
_SECRET_KEY_PATTERNS = frozenset({
    "password", "secret", "token", "authorization", "api_key",
    "private_key", "refresh_token", "access_token", "credential",
    "client_secret", "encryption_key", "service_key", "anon_key",
})


class CredentialEncryptionService(EncryptionProvider):
    """Encrypts / decrypts credential blobs with key-ID tracking.

    Each ciphertext is prefixed with the key_id so records encrypted under
    an old key can still be decrypted after rotation (the old key is kept
    in a ``previous_keys`` map).

    Wire format:  ``key_id:base64(fernet_ciphertext)`` encoded as UTF-8 bytes.
    """

    def __init__(
        self,
        master_key: str | None = None,
        key_id: str | None = None,
        previous_keys: dict[str, str] | None = None,
    ) -> None:
        resolved_key = master_key or os.getenv("ENCRYPTION_KEY", "")
        resolved_id = key_id or os.getenv("ENCRYPTION_KEY_ID", "v1")

        env = os.getenv("APP_ENV", "development")

        if not resolved_key:
            if env == "production":
                raise RuntimeError(
                    "ENCRYPTION_KEY is required in production.  "
                    "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
                )
            logger.warning(
                "ENCRYPTION_KEY is not set.  Generating an ephemeral key for development.  "
                "Encrypted data will be lost on restart.  "
                "To persist: ENCRYPTION_KEY=$(python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\")"
            )
            resolved_key = Fernet.generate_key().decode()

        try:
            self._current_fernet = Fernet(resolved_key.encode() if isinstance(resolved_key, str) else resolved_key)
        except Exception as exc:
            raise RuntimeError(
                f"ENCRYPTION_KEY is malformed (must be a valid Fernet key).  "
                f"Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            ) from exc

        self._key_id = resolved_id

        # Build lookup for old keys
        self._key_map: dict[str, Fernet] = {resolved_id: self._current_fernet}
        if previous_keys:
            for kid, key_value in previous_keys.items():
                try:
                    self._key_map[kid] = Fernet(key_value.encode() if isinstance(key_value, str) else key_value)
                except Exception:
                    logger.warning("Ignoring invalid previous encryption key '%s'", kid)

    @property
    def key_id(self) -> str:
        return self._key_id

    # ── EncryptionProvider interface ──────────────────────────────

    def encrypt(self, plaintext: bytes) -> bytes:
        """Encrypt and return ``key_id:ciphertext`` as bytes."""
        ciphertext = self._current_fernet.encrypt(plaintext)
        return f"{self._key_id}:{base64.urlsafe_b64encode(ciphertext).decode()}".encode()

    def decrypt(self, ciphertext: bytes) -> bytes:
        """Decrypt a ``key_id:ciphertext`` blob."""
        try:
            text = ciphertext.decode() if isinstance(ciphertext, (bytes, memoryview)) else ciphertext
            if ":" not in text:
                # Legacy: try current key directly
                return self._current_fernet.decrypt(ciphertext)
            kid, b64_ct = text.split(":", 1)
            fernet = self._key_map.get(kid)
            if fernet is None:
                raise InvalidToken(f"Unknown encryption key ID: {kid}")
            return fernet.decrypt(base64.urlsafe_b64decode(b64_ct))
        except InvalidToken:
            raise
        except Exception as exc:
            raise InvalidToken(f"Decryption failed: {type(exc).__name__}") from exc

    # ── High-level helpers ───────────────────────────────────────

    def encrypt_credentials(self, credentials: dict) -> tuple[bytes, str]:
        """Encrypt a credentials dict.  Returns ``(ciphertext, key_id)``."""
        plaintext = json.dumps(credentials, separators=(",", ":")).encode("utf-8")
        return self.encrypt(plaintext), self._key_id

    def decrypt_credentials(self, ciphertext: bytes) -> dict:
        """Decrypt a ciphertext blob back to a credentials dict."""
        plaintext = self.decrypt(ciphertext)
        return json.loads(plaintext)

    def rotate(self, ciphertext: bytes) -> tuple[bytes, str]:
        """Re-encrypt under the current key.  Returns ``(new_ciphertext, key_id)``."""
        plaintext = self.decrypt(ciphertext)
        return self.encrypt(plaintext), self._key_id

    def needs_rotation(self, ciphertext: bytes) -> bool:
        """Check if the ciphertext was encrypted under a previous key."""
        try:
            text = ciphertext.decode() if isinstance(ciphertext, (bytes, memoryview)) else ciphertext
            if ":" not in text:
                return True
            kid = text.split(":", 1)[0]
            return kid != self._key_id
        except Exception:
            return True


# ═══════════════════════════════════════════════════════════════
# Module-level singleton
# ═══════════════════════════════════════════════════════════════

_encryption_service: CredentialEncryptionService | None = None


def get_encryption_service() -> CredentialEncryptionService:
    global _encryption_service
    if _encryption_service is None:
        _encryption_service = CredentialEncryptionService()
    return _encryption_service
