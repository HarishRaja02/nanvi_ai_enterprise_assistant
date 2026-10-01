"""Local Files provider for company folders and filesystem storage."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from backend.connections.base import (
    AuthType,
    BaseProvider,
    Capability,
    ConnectionError,
    InvalidCredentials,
    ProviderMetadata,
    Unreachable,
)


class LocalFilesProvider(BaseProvider):
    """Provider for local directory and file storage."""

    def get_metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            id="local_files",
            name="Local Files & Folders",
            categories=("Storage / Documents",),
            icon="folder",
            description="Connect a local folder containing company documents, spreadsheets, or data.",
            auth_type=AuthType.FILESYSTEM,
            capabilities=frozenset({
                Capability.CREDENTIALS_FORM,
                Capability.TEST,
                Capability.READ_DOCUMENTS,
                Capability.LIST_FILES,
                Capability.WRITE_FILES,
            }),
            available=True,
            configuration_schema={
                "type": "object",
                "required": ["path"],
                "properties": {
                    "path": {
                        "type": "string",
                        "title": "Folder Path",
                        "description": "Absolute path to the folder on the server (e.g. C:/data or /var/data)",
                    },
                    "read_only": {
                        "type": "boolean",
                        "title": "Read Only",
                        "description": "Prevent any modifications to files in this folder",
                        "default": True,
                    },
                },
            },
        )

    def connect(self, config: dict[str, Any]) -> dict[str, Any]:
        path_str = config.get("path", "").strip()
        if not path_str:
            raise InvalidCredentials("Folder path is required.")

        folder = Path(path_str).resolve()
        if not folder.exists():
            raise Unreachable(f"Path does not exist: {path_str}")
        if not folder.is_dir():
            raise InvalidCredentials(f"Path is not a directory: {path_str}")

        read_only = bool(config.get("read_only", True))

        return {
            "account_identifier": str(folder),
            "display_name": folder.name or str(folder),
            "credentials": {"path": str(folder), "read_only": read_only},
            "metadata_safe": {"path": str(folder), "read_only": read_only},
            "granted_scopes": ["read"] if read_only else ["read", "write"],
        }

    def test_connection(
        self,
        *,
        decrypted_credentials: dict[str, Any],
        metadata_safe: dict[str, Any],
    ) -> dict[str, Any]:
        path_str = decrypted_credentials.get("path") or metadata_safe.get("path")
        if not path_str:
            raise InvalidCredentials("Missing folder path.")

        folder = Path(path_str).resolve()
        if not folder.exists():
            raise Unreachable(f"Folder no longer exists: {path_str}")
        if not folder.is_dir():
            raise ConnectionError(f"Target is not a directory: {path_str}")

        try:
            entries = list(os.scandir(folder))
            file_count = sum(1 for e in entries if e.is_file())
            dir_count = sum(1 for e in entries if e.is_dir())
            return {
                "ok": True,
                "file_count": file_count,
                "subfolder_count": dir_count,
                "path": str(folder),
            }
        except PermissionError as exc:
            raise ConnectionError(f"Permission denied reading directory: {exc}") from exc

    def get_client(
        self,
        *,
        decrypted_credentials: dict[str, Any],
        metadata_safe: dict[str, Any],
    ) -> Any:
        class LocalFilesClient:
            def __init__(self, root: str, read_only: bool) -> None:
                self.root = Path(root).resolve()
                self.read_only = read_only

            def list_files(self) -> list[str]:
                if not self.root.exists():
                    return []
                return [str(p.relative_to(self.root)) for p in self.root.rglob("*") if p.is_file()]

            def read_file(self, relative_path: str) -> bytes:
                target = (self.root / relative_path).resolve()
                if not target.is_relative_to(self.root):
                    raise ConnectionError("Path traversal attempt detected.")
                if not target.exists():
                    raise ConnectionError(f"File not found: {relative_path}")
                return target.read_bytes()

        return LocalFilesClient(
            root=decrypted_credentials.get("path", ""),
            read_only=decrypted_credentials.get("read_only", True),
        )
