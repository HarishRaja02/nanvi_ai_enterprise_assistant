"""Thread-safe, short-lived server-side validation cache for UECP access decisions."""
from __future__ import annotations

import threading
import time
from typing import Any

from backend.uecp.models import UECPAccessState


class UECPValidationCache:
    """Stores validated UECP access decisions with short TTL (e.g. 60s).

    Never stores credentials, secrets, or permanent authorization.
    Supports rapid explicit invalidation.
    """

    def __init__(self, default_ttl_seconds: int = 60) -> None:
        self._default_ttl = max(1, min(default_ttl_seconds, 300))
        self._lock = threading.Lock()
        # Key: (organization_id or "", permission or "") -> (UECPAccessState, expiry_monotonic)
        self._cache: dict[tuple[str, str], tuple[UECPAccessState, float]] = {}

    def _make_key(self, organization_id: str | None, permission: str | None) -> tuple[str, str]:
        return (organization_id or "", permission or "")

    def get(self, organization_id: str | None, permission: str | None = None) -> UECPAccessState | None:
        """Retrieve a cached decision if not expired."""
        key = self._make_key(organization_id, permission)
        now = time.monotonic()
        with self._lock:
            entry = self._cache.get(key)
            if not entry:
                return None
            state, expires_at = entry
            if now >= expires_at:
                # Expired
                self._cache.pop(key, None)
                return None
            return state

    def set(
        self,
        organization_id: str | None,
        permission: str | None,
        state: UECPAccessState,
        ttl_seconds: int | None = None,
    ) -> None:
        """Store an access decision.

        Negative decisions (frozen, revoked, expired) are cached for at most
        the specified short TTL or less, never overriding future positive checks indefinitely.
        """
        key = self._make_key(organization_id, permission)
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
        # Negative decisions can be cached with shorter TTL (e.g., 10s or default)
        effective_ttl = min(ttl, 15) if not state.allowed else ttl
        expires_at = time.monotonic() + effective_ttl

        with self._lock:
            self._cache[key] = (state, expires_at)

    def invalidate(self, organization_id: str | None, permission: str | None = None) -> None:
        """Rapid invalidation for a specific organization/permission entry."""
        key = self._make_key(organization_id, permission)
        with self._lock:
            self._cache.pop(key, None)

    def invalidate_organization(self, organization_id: str | None) -> None:
        """Rapidly evict all cached entries for an organization (e.g. upon revoke/freeze notification)."""
        target_org = organization_id or ""
        with self._lock:
            keys_to_remove = [k for k in self._cache.keys() if k[0] == target_org]
            for k in keys_to_remove:
                self._cache.pop(k, None)

    def clear(self) -> None:
        """Evict all cached entries."""
        with self._lock:
            self._cache.clear()

    def size(self) -> int:
        with self._lock:
            return len(self._cache)
