"""Tests for CredentialEncryptionService, key rotation, and production safeguards."""
import os
import pytest
from cryptography.fernet import Fernet, InvalidToken

from backend.connections.encryption import CredentialEncryptionService


def test_encryption_roundtrip():
    key = Fernet.generate_key().decode()
    service = CredentialEncryptionService(master_key=key, key_id="v1")

    creds = {"password": "SuperSecretPassword123!", "api_key": "live_abcdef123456"}
    ciphertext, key_id = service.encrypt_credentials(creds)

    assert key_id == "v1"
    assert ciphertext != creds
    assert b"SuperSecretPassword123!" not in ciphertext

    decrypted = service.decrypt_credentials(ciphertext)
    assert decrypted == creds


def test_tamper_detection():
    key = Fernet.generate_key().decode()
    service = CredentialEncryptionService(master_key=key, key_id="v1")

    creds = {"token": "secret-token"}
    ciphertext, _ = service.encrypt_credentials(creds)

    # Tamper with ciphertext bytes
    tampered = ciphertext[:-4] + b"XXXX"
    with pytest.raises(InvalidToken):
        service.decrypt_credentials(tampered)


def test_key_rotation_support():
    old_key = Fernet.generate_key().decode()
    new_key = Fernet.generate_key().decode()

    # Old service encrypts with v1
    old_service = CredentialEncryptionService(master_key=old_key, key_id="v1")
    ciphertext_v1, kid_v1 = old_service.encrypt_credentials({"secret": "rotate_me"})
    assert kid_v1 == "v1"

    # New service has v2 as current, and v1 in previous_keys
    new_service = CredentialEncryptionService(
        master_key=new_key,
        key_id="v2",
        previous_keys={"v1": old_key},
    )

    # It can decrypt v1 ciphertext seamlessly
    decrypted = new_service.decrypt_credentials(ciphertext_v1)
    assert decrypted == {"secret": "rotate_me"}
    assert new_service.needs_rotation(ciphertext_v1) is True

    # Rotate ciphertext to v2
    new_ciphertext, new_kid = new_service.rotate(ciphertext_v1)
    assert new_kid == "v2"
    assert new_service.needs_rotation(new_ciphertext) is False

    # And decrypts with v2
    assert new_service.decrypt_credentials(new_ciphertext) == {"secret": "rotate_me"}


def test_production_fails_if_key_missing(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ENCRYPTION_KEY", "")

    with pytest.raises(RuntimeError) as exc_info:
        CredentialEncryptionService(master_key=None)
    assert "ENCRYPTION_KEY is required in production" in str(exc_info.value)
