"""Provider implementations for the Universal Connections Hub."""
from __future__ import annotations

from typing import TYPE_CHECKING

from backend.connections.providers.custom_api import CustomApiProvider
from backend.connections.providers.github import GitHubProvider
from backend.connections.providers.google import GoogleProvider
from backend.connections.providers.local_files import LocalFilesProvider
from backend.connections.providers.mysql import MariaDBProvider, MySQLProvider
from backend.connections.providers.postgres import PostgreSQLProvider
from backend.connections.providers.sqlite import SQLiteProvider
from backend.connections.providers.supabase import SupabaseProvider

if TYPE_CHECKING:
    from backend.connections.registry import ProviderRegistry

__all__ = [
    "CustomApiProvider",
    "GitHubProvider",
    "GoogleProvider",
    "LocalFilesProvider",
    "MariaDBProvider",
    "MySQLProvider",
    "PostgreSQLProvider",
    "SQLiteProvider",
    "SupabaseProvider",
    "register_all_providers",
]


def register_all_providers(registry: ProviderRegistry) -> None:
    """Register all built-in code-backed providers into the registry."""
    registry.register(LocalFilesProvider())
    registry.register(PostgreSQLProvider())
    registry.register(MySQLProvider())
    registry.register(MariaDBProvider())
    registry.register(SQLiteProvider())
    registry.register(CustomApiProvider())
    registry.register(GoogleProvider())
    registry.register(GitHubProvider())
    registry.register(SupabaseProvider())
