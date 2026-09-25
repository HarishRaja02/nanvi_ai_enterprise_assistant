import base64
import json
import time

import jwt
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.security.exceptions import AuthenticationError
from backend.security.token_validator import TokenValidator


class FakeValidator(TokenValidator):
    def __init__(self, token_map):
        self.token_map = token_map

    def validate(self, token):
        if token in self.token_map:
            return self.token_map[token]
        raise AuthenticationError("Invalid access token")


def test_valid_token():
    validator = FakeValidator({"valid": object()})
    assert validator.validate("valid") is not None


def test_expired_token():
    with pytest.raises(jwt.ExpiredSignatureError):
        jwt.decode(
            jwt.encode({"sub": "u1", "exp": int(time.time()) - 1}, "test-secret-for-nanvi-hs256-regression", algorithm="HS256"),
            "test-secret-for-nanvi-hs256-regression",
            algorithms=["HS256"],
        )


def test_invalid_token():
    validator = FakeValidator({})
    with pytest.raises(AuthenticationError):
        validator.validate("invalid")


def test_missing_token():
    client = TestClient(app)
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_malformed_token():
    validator = TokenValidator(jwks_url="https://example.invalid/jwks")
    with pytest.raises(AuthenticationError, match="Malformed"):
        validator.validate("not-a-jwt")
