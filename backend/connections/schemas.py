"""Pydantic request/response schemas for the Connections API.

Uses an explicit allowlist serializer — ConnectionPublic returns ONLY safe
fields.  No "return the model minus a few fields" pattern.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════
# Public response models (allowlist — never include secrets)
# ═══════════════════════════════════════════════════════════════

class ConnectionPublic(BaseModel):
    """Safe public representation of a connection.  Never includes credentials."""
    id: str
    provider: str
    display_name: str
    account_identifier: str | None = None
    scope_level: str
    status: str
    status_reason: str | None = None
    granted_scopes: list[str] = Field(default_factory=list)
    metadata_safe: dict[str, Any] = Field(default_factory=dict)
    credential_type: str | None = None
    last_tested_at: str | None = None
    last_used_at: str | None = None
    last_synced_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    created_by: str | None = None
    owner_user_id: str | None = None


class ProviderPublic(BaseModel):
    """Provider catalog entry for the UI."""
    id: str
    name: str
    categories: list[str]
    icon: str
    description: str
    auth_type: str
    capabilities: list[str]
    available: bool = True
    available_reason: str = ""
    configuration_schema: dict[str, Any] = Field(default_factory=dict)


class ProviderListResponse(BaseModel):
    providers: list[ProviderPublic]


class ConnectionListResponse(BaseModel):
    connections: list[ConnectionPublic]
    total: int


# ═══════════════════════════════════════════════════════════════
# Request models
# ═══════════════════════════════════════════════════════════════

class CreateConnectionRequest(BaseModel):
    """Create a new connection via credential form."""
    provider: str = Field(min_length=1, max_length=100)
    display_name: str = Field(min_length=1, max_length=255)
    scope_level: str = Field(default="user", pattern=r"^(user|organization)$")
    config: dict[str, Any] = Field(default_factory=dict)


class ValidateConnectionRequest(BaseModel):
    """Test a connection before saving."""
    provider: str = Field(min_length=1, max_length=100)
    config: dict[str, Any] = Field(default_factory=dict)


class UpdateConnectionRequest(BaseModel):
    """Update connection metadata (non-secret settings)."""
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    config: dict[str, Any] | None = None


class TestConnectionResponse(BaseModel):
    ok: bool
    message: str = ""
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    code: str
    message: str
    hint: str = ""
