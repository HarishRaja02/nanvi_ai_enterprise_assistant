"""Data models for UECP integration."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class UECPAccessState:
    """Server-side authoritative access decision from UECP."""

    allowed: bool
    reason: str | None = None
    entitlements: tuple[str, ...] = field(default_factory=tuple)
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    organization_id: str | None = None
    application_id: str | None = None
    status: str = "active"

    def can(self, permission: str | None) -> bool:
        """Check if this state permits the given action."""
        if not self.allowed:
            return False
        if not permission:
            return True
        # If no granular entitlements are defined by UECP, general grant applies
        if not self.entitlements:
            return True
        return permission in self.entitlements or "*" in self.entitlements

    def to_safe_frontend(self) -> SafeUECPState:
        """Project access state into non-sensitive payload suitable for React frontend."""
        features = {e: True for e in self.entitlements}
        return SafeUECPState(
            connected=True,
            allowed=self.allowed,
            features=features,
        )


@dataclass(frozen=True)
class SafeUECPState:
    """Safe state object for frontend consumption. Never exposes secrets or internal error details."""

    connected: bool
    allowed: bool
    features: dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "connected": self.connected,
            "allowed": self.allowed,
            "features": self.features,
        }
