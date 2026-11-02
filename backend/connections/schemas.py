"""Pydantic request/response schemas for the Connections API.

Uses an explicit allowlist serializer — ConnectionPublic returns ONLY safe
fields. Never includes credentials or raw secrets.
"""
from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field, computed_field


# ═══════════════════════════════════════════════════════════════
# Service and Granular Permission Models
# ═══════════════════════════════════════════════════════════════

class ServicePermission(BaseModel):
    """Specific permission granted or required for an individual service."""
    id: str
    label: str
    description: str
    granted: bool = True
    required_scopes: list[str] = Field(default_factory=list)

    @computed_field
    def name(self) -> str:
        return self.label

    @computed_field
    def enabled(self) -> bool:
        return self.granted


class ServiceState(BaseModel):
    """Current state of an individual service belonging to a connected account."""
    id: str
    name: str
    icon: str
    description: str
    enabled: bool = True
    status: str = "ENABLED"  # ENABLED | DISABLED | UNAUTHORIZED | NOT_CONFIGURED
    status_reason: str | None = None
    permissions: list[ServicePermission] = Field(default_factory=list)
    required_scopes: list[str] = Field(default_factory=list)
    granted_scopes: list[str] = Field(default_factory=list)
    last_synced_at: str | None = None
    sync_frequency: str = "1h"
    sync_status: str = "IDLE"  # IDLE | SYNCING | SUCCESS | FAILED
    item_count: int | None = None

    @computed_field
    def requires_scopes(self) -> list[str]:
        return self.required_scopes


# ═══════════════════════════════════════════════════════════════
# Public Response Models
# ═══════════════════════════════════════════════════════════════

class ConnectionPublic(BaseModel):
    """Safe public representation of a connected account. Never includes credentials."""
    id: str
    provider: str
    display_name: str
    account_identifier: str | None = None
    scope_level: str
    account_type: str = "Personal"  # Personal | Organization
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

    # Enterprise Service Management Extensions
    services: list[ServiceState] = Field(default_factory=list)
    enabled_services_count: int = 0
    total_services_count: int = 0
    auto_sync: bool = True
    sync_frequency: str = "1h"
    sync_config: dict[str, Any] = Field(default_factory=lambda: {"auto_sync": True, "frequency": "1h"})


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
    supported_services: list[str] = Field(default_factory=list)


class ProviderListResponse(BaseModel):
    providers: list[ProviderPublic]


class ConnectionListResponse(BaseModel):
    connections: list[ConnectionPublic]
    total: int


# ═══════════════════════════════════════════════════════════════
# Request Models
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


class UpdateServiceRequest(BaseModel):
    """Update an individual service's enabled status or permissions."""
    enabled: bool | None = None
    permissions: list[str] | None = None
    sync_frequency: str | None = None


class UpdateSyncConfigRequest(BaseModel):
    """Update synchronization schedule and automated sync toggles."""
    auto_sync: bool | None = None
    sync_frequency: str | None = None
    frequency: str | None = None


class SyncConnectionResponse(BaseModel):
    """Response returned upon triggering an on-demand sync."""
    ok: bool
    message: str
    synced_services: list[str] = Field(default_factory=list)
    synced_at: str


class TestConnectionResponse(BaseModel):
    ok: bool
    message: str = ""
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    code: str
    message: str
    hint: str = ""
