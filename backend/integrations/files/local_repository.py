from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath
from typing import Iterable, Mapping

from backend.integrations.files.exceptions import FileNotFound, FileTooLarge, FileTypeNotAllowed, InvalidFilePath
from backend.integrations.files.models import FileMetadata, FileRecord
from backend.integrations.files.repository import FileRepository

DEFAULT_ALLOWED_EXTENSIONS = frozenset({
    ".pdf", ".docx", ".xlsx", ".csv", ".txt", ".md", ".pptx",
})


def _normalize_relative_path(value: str, *, allow_empty: bool = False) -> Path:
    if not isinstance(value, str):
        raise InvalidFilePath("Path must be a string")
    if "\x00" in value:
        raise InvalidFilePath("Path contains a null byte")
    value = value.strip()
    if not value and allow_empty:
        return Path(".")
    if not value:
        raise InvalidFilePath("Path cannot be empty")
    windows_path = PureWindowsPath(value)
    if windows_path.is_absolute() or windows_path.drive:
        raise InvalidFilePath("Absolute or drive-qualified paths are not allowed")
    if value.startswith(("/", "\\")):
        raise InvalidFilePath("Absolute paths are not allowed")
    parts = value.replace("\\", "/").split("/")
    if any(part == ".." for part in parts):
        raise InvalidFilePath("Path traversal is not allowed")
    parts = [part for part in parts if part]
    for part in parts:
        if any(ord(ch) < 32 for ch in part):
            raise InvalidFilePath("Path contains control characters")
        if part.endswith((".", " ")):
            raise InvalidFilePath("Path component is ambiguous on Windows")
        if part.casefold().split(".")[0] in {"con", "prn", "aux", "nul", "com1", "com2", "com3", "com4", "com5", "com6", "com7", "com8", "com9", "lpt1", "lpt2", "lpt3", "lpt4", "lpt5", "lpt6", "lpt7", "lpt8", "lpt9"}:
            raise InvalidFilePath("Reserved Windows filename")
    return Path(*parts)


class LocalFileRepository(FileRepository):
    """Secure repository for one explicitly configured root.

    The public repository API accepts relative paths only. Resolved targets must
    remain below the configured root, including when symlinks are present.
    """
    def __init__(self, root_dir: str | Path, *, max_file_size_bytes: int = 10 * 1024 * 1024,
                 allowed_extensions: frozenset[str] = DEFAULT_ALLOWED_EXTENSIONS) -> None:
        self._root = Path(root_dir).expanduser().resolve(strict=True)
        if not self._root.is_dir():
            raise ValueError("Company file root must be a directory")
        self._configure_limits(max_file_size_bytes, allowed_extensions)

    def _configure_limits(self, max_file_size_bytes: int, allowed_extensions: frozenset[str]) -> None:
        if max_file_size_bytes <= 0:
            raise ValueError("max_file_size_bytes must be positive")
        self._max_file_size = max_file_size_bytes
        self._allowed_extensions = frozenset(ext.lower() for ext in allowed_extensions)

    @property
    def root_dir(self) -> Path:
        return self._root

    def list_files(self, relative_directory: str = "") -> Iterable[FileRecord]:
        directory = self._resolve_directory(relative_directory)
        for entry in directory.iterdir():
            if entry.is_file() or entry.is_symlink():
                try:
                    yield self._record(entry)
                except (FileNotFound, InvalidFilePath, FileTypeNotAllowed, FileTooLarge):
                    continue

    def search_by_filename(self, relative_directory: str = "", query: str = "") -> Iterable[FileRecord]:
        query = query.strip().casefold()
        if not query:
            raise InvalidFilePath("Filename search query cannot be empty")
        directory = self._resolve_directory(relative_directory)
        for current_root, dir_names, file_names in os.walk(directory, followlinks=False):
            dir_names[:] = [n for n in dir_names if not (Path(current_root) / n).is_symlink()]
            for name in file_names:
                if query in name.casefold():
                    try:
                        yield self._record(Path(current_root) / name)
                    except (FileNotFound, InvalidFilePath, FileTypeNotAllowed, FileTooLarge):
                        continue

    def get_metadata(self, relative_path: str) -> FileRecord:
        return self._record(self._resolve_file(relative_path))

    def read_file(self, relative_path: str) -> bytes:
        target = self._resolve_file(relative_path)
        record = self._record(target)
        safe_target = self._resolve_file(relative_path)
        if safe_target != record.absolute_path:
            raise InvalidFilePath("File target changed during validation")
        with safe_target.open("rb") as handle:
            data = handle.read(self._max_file_size + 1)
        if len(data) > self._max_file_size:
            raise FileTooLarge(f"File exceeds {self._max_file_size} byte limit")
        return data

    def _resolve_directory(self, relative_directory: str) -> Path:
        target = self._resolve_existing(self._root / _normalize_relative_path(relative_directory, allow_empty=True))
        if not target.is_dir():
            raise FileNotFound(f"Directory not found: {relative_directory}")
        return target

    def _resolve_file(self, relative_path: str) -> Path:
        target = self._resolve_existing(self._root / _normalize_relative_path(relative_path))
        if not target.is_file():
            raise FileNotFound(f"File not found: {relative_path}")
        return target

    def _resolve_existing(self, candidate: Path) -> Path:
        try:
            resolved = candidate.resolve(strict=True)
        except FileNotFoundError as exc:
            raise FileNotFound(f"Path does not exist") from exc
        self._ensure_inside_root(resolved)
        return resolved

    def _ensure_inside_root(self, target: Path) -> None:
        try:
            target.relative_to(self._root)
        except ValueError as exc:
            raise InvalidFilePath("Path escapes configured company-data root") from exc

    def _record(self, path: Path) -> FileRecord:
        target = self._resolve_existing(path)
        suffix = target.suffix.lower()
        if suffix not in self._allowed_extensions:
            raise FileTypeNotAllowed(f"Extension is not allowed: {suffix or '<none>'}")
        stat = target.stat()
        if stat.st_size > self._max_file_size:
            raise FileTooLarge(f"File exceeds {self._max_file_size} byte limit")
        relative = target.relative_to(self._root).as_posix()
        return FileRecord(FileMetadata(relative, target.name, suffix, stat.st_size,
                                       datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                                       is_symlink=path.is_symlink()), target)


class ConfiguredLocalFileRepository(FileRepository):
    """Multi-root repository with an explicit virtual root allowlist.

    Example virtual paths: ``Customers/acme.pdf`` and ``Finance/revenue.xlsx``.
    No path outside the five configured root directories can be addressed.
    """
    def __init__(self, allowed_roots: Mapping[str, str | Path], *, max_file_size_bytes: int = 10 * 1024 * 1024,
                 allowed_extensions: frozenset[str] = DEFAULT_ALLOWED_EXTENSIONS) -> None:
        if not allowed_roots:
            raise ValueError("At least one explicit company root is required")
        self._roots = {}
        for name, root in allowed_roots.items():
            key = _normalize_root_name(name)
            resolved = Path(root).expanduser().resolve(strict=True)
            if not resolved.is_dir():
                raise ValueError(f"Configured company root is not a directory: {name}")
            self._roots[key] = resolved
        if max_file_size_bytes <= 0:
            raise ValueError("max_file_size_bytes must be positive")
        self._max_file_size = max_file_size_bytes
        self._allowed_extensions = frozenset(x.lower() for x in allowed_extensions)

    @property
    def allowed_roots(self) -> Mapping[str, Path]:
        return dict(self._roots)

    def _split(self, virtual_path: str, allow_empty: bool = False) -> tuple[str, Path]:
        rel = _normalize_relative_path(virtual_path, allow_empty=allow_empty)
        if rel == Path("."):
            raise InvalidFilePath("A configured root name is required")
        parts = rel.parts
        root_name = parts[0].casefold()
        root = self._roots.get(root_name)
        if root is None:
            raise InvalidFilePath("Path is outside configured company roots")
        child = Path(*parts[1:]) if len(parts) > 1 else Path(".")
        return root_name, child

    def _resolve(self, virtual_path: str, *, directory: bool = False) -> FileRecord | Path:
        root_name, child = self._split(virtual_path)
        root = self._roots[root_name]
        try:
            resolved = (root / child).resolve(strict=True)
        except FileNotFoundError as exc:
            raise FileNotFound("Path does not exist") from exc
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise InvalidFilePath("Path escapes configured company root") from exc
        if directory:
            if not resolved.is_dir():
                raise FileNotFound("Directory not found")
            return resolved
        if not resolved.is_file():
            raise FileNotFound("File not found")
        suffix = resolved.suffix.lower()
        if suffix not in self._allowed_extensions:
            raise FileTypeNotAllowed(f"Extension is not allowed: {suffix or '<none>'}")
        stat = resolved.stat()
        if stat.st_size > self._max_file_size:
            raise FileTooLarge(f"File exceeds {self._max_file_size} byte limit")
        relative = f"{root_name}/{resolved.relative_to(root).as_posix()}"
        return FileRecord(FileMetadata(relative, resolved.name, suffix, stat.st_size,
                                       datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                                       is_symlink=(root / child).is_symlink()), resolved)

    def list_files(self, relative_directory: str = "") -> Iterable[FileRecord]:
        root_name, child = self._split(relative_directory, allow_empty=False)
        root = self._roots[root_name]
        directory = (root / child).resolve(strict=True)
        try:
            directory.relative_to(root)
        except ValueError as exc:
            raise InvalidFilePath("Path escapes configured company root") from exc
        if not directory.is_dir():
            raise FileNotFound("Directory not found")
        for entry in directory.iterdir():
            if entry.is_file() or entry.is_symlink():
                try:
                    yield self._resolve(f"{root_name}/{entry.relative_to(self._roots[root_name]).as_posix()}")
                except (FileNotFound, InvalidFilePath, FileTypeNotAllowed, FileTooLarge):
                    continue

    def search_by_filename(self, relative_directory: str = "", query: str = "") -> Iterable[FileRecord]:
        query = query.strip().casefold()
        if not query:
            raise InvalidFilePath("Filename search query cannot be empty")
        root_name, child = self._split(relative_directory, allow_empty=False)
        root = self._roots[root_name]
        directory = (root / child).resolve(strict=True)
        try:
            directory.relative_to(root)
        except ValueError as exc:
            raise InvalidFilePath("Path escapes configured company root") from exc
        if not directory.is_dir():
            raise FileNotFound("Directory not found")
        root = self._roots[root_name]
        for current_root, dir_names, file_names in os.walk(directory, followlinks=False):
            dir_names[:] = [n for n in dir_names if not (Path(current_root) / n).is_symlink()]
            for name in file_names:
                if query in name.casefold():
                    try:
                        yield self._resolve(f"{root_name}/{(Path(current_root) / name).relative_to(root).as_posix()}")
                    except (FileNotFound, InvalidFilePath, FileTypeNotAllowed, FileTooLarge):
                        continue

    def get_metadata(self, relative_path: str) -> FileRecord:
        return self._resolve(relative_path)

    def read_file(self, relative_path: str) -> bytes:
        record = self._resolve(relative_path)
        assert isinstance(record, FileRecord)
        # Re-resolve immediately before opening to reduce symlink replacement risk.
        safe = self._resolve(record.metadata.relative_path)
        if safe.absolute_path != record.absolute_path:
            raise InvalidFilePath("File target changed during validation")
        with safe.absolute_path.open("rb") as handle:
            data = handle.read(self._max_file_size + 1)
        if len(data) > self._max_file_size:
            raise FileTooLarge(f"File exceeds {self._max_file_size} byte limit")
        return data


def _normalize_root_name(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Company root names must be non-empty")
    name = value.strip().casefold()
    if "/" in name or "\\" in name or name in {".", ".."}:
        raise ValueError("Invalid company root name")
    return name
