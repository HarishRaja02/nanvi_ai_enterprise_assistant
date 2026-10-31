"""Provider implementations for the Universal Connections Hub."""
from __future__ import annotations

from typing import TYPE_CHECKING

from backend.connections.providers.cloud_storage import BoxProvider, DropboxProvider, EgnyteProvider
from backend.connections.providers.custom_api import CustomApiProvider
from backend.connections.providers.email_generic import ImapProvider, SmtpProvider
from backend.connections.providers.github import GitHubProvider
from backend.connections.providers.google import GoogleProvider
from backend.connections.providers.local_files import LocalFilesProvider
from backend.connections.providers.microsoft import (
    Microsoft365Provider,
    OneDriveProvider,
    OutlookProvider,
    SharePointProvider,
)
from backend.connections.providers.mysql import MariaDBProvider, MySQLProvider
from backend.connections.providers.postgres import PostgreSQLProvider
from backend.connections.providers.sqlite import SQLiteProvider
from backend.connections.providers.supabase import SupabaseProvider
from backend.connections.providers.yahoo import YahooMailProvider

if TYPE_CHECKING:
    from backend.connections.registry import ProviderRegistry

__all__ = [
    "BoxProvider",
    "CustomApiProvider",
    "DropboxProvider",
    "EgnyteProvider",
    "GitHubProvider",
    "GoogleProvider",
    "ImapProvider",
    "LocalFilesProvider",
    "MariaDBProvider",
    "Microsoft365Provider",
    "MySQLProvider",
    "OneDriveProvider",
    "OutlookProvider",
    "PostgreSQLProvider",
    "SharePointProvider",
    "SQLiteProvider",
    "SmtpProvider",
    "SupabaseProvider",
    "YahooMailProvider",
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
    registry.register(Microsoft365Provider())
    registry.register(OutlookProvider())
    registry.register(OneDriveProvider())
    registry.register(SharePointProvider())
    registry.register(YahooMailProvider())
    registry.register(ImapProvider())
    registry.register(SmtpProvider())
    registry.register(BoxProvider())
    registry.register(DropboxProvider())
    registry.register(EgnyteProvider())
    registry.register(GitHubProvider())
    registry.register(SupabaseProvider())
