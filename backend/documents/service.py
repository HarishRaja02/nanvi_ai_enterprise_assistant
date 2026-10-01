from __future__ import annotations
from datetime import datetime
from io import BytesIO
from pathlib import Path
from zipfile import BadZipFile, ZipFile
from .models import Document
from .parser import DocumentParser

class UnsupportedDocumentTypeError(ValueError): pass
class DocumentProcessingError(ValueError): pass

class DocumentProcessingService:
    """Processes bytes obtained from FileService; it never resolves filesystem paths."""
    ZIP_FORMATS = frozenset({".docx", ".xlsx", ".pptx"})
    MAX_ZIP_ENTRIES = 2000
    MAX_ZIP_UNCOMPRESSED = 50 * 1024 * 1024
    MAX_COMPRESSION_RATIO = 100

    def __init__(self, parsers: list[DocumentParser]):
        self._parsers = tuple(parsers)

    def parse_bytes(self, *, filename: str, relative_path: str, data: bytes,
                    modified_at: datetime | None = None) -> Document:
        suffix = Path(filename).suffix.casefold()
        parser = next((p for p in self._parsers if p.supports(filename)), None)
        if parser is None:
            raise UnsupportedDocumentTypeError(f"Unsupported document type: {suffix or '<none>'}")
        if suffix in self.ZIP_FORMATS:
            self._validate_ooxml_archive(data)
        try:
            return parser.parse_bytes(filename=filename, relative_path=relative_path, data=data, modified_at=modified_at)
        except (UnsupportedDocumentTypeError, DocumentProcessingError):
            raise
        except Exception as exc:
            raise DocumentProcessingError(f"Unable to process {suffix or 'document'}") from exc

    def parse_file(self, file_service, user, relative_path: str) -> Document:
        """Controlled entry point: only FileService may read the filesystem."""
        metadata, data = file_service.read_for_processing(user, relative_path)
        return self.parse_bytes(filename=metadata.name, relative_path=metadata.relative_path,
                                data=data, modified_at=metadata.modified_at)

    @classmethod
    def _validate_ooxml_archive(cls, data: bytes) -> None:
        try:
            with ZipFile(BytesIO(data)) as archive:
                infos = archive.infolist()
                if len(infos) > cls.MAX_ZIP_ENTRIES:
                    raise DocumentProcessingError("Document contains too many archive entries")
                total = 0
                for info in infos:
                    archive_name = info.filename.replace("\\", "/")
                    windows_name = Path(archive_name)
                    if archive_name.startswith("/") or ".." in windows_name.parts:
                        raise DocumentProcessingError("Document contains an unsafe archive path")
                    from pathlib import PureWindowsPath
                    if PureWindowsPath(archive_name).is_absolute() or PureWindowsPath(archive_name).drive:
                        raise DocumentProcessingError("Document contains an unsafe archive path")
                    if (info.external_attr >> 16) & 0o170000 == 0o120000:
                        raise DocumentProcessingError("Document contains an unsafe archive entry")
                    total += max(0, info.file_size)
                    if total > cls.MAX_ZIP_UNCOMPRESSED:
                        raise DocumentProcessingError("Document uncompressed size exceeds safety limit")
                    if info.compress_size and info.file_size / info.compress_size > cls.MAX_COMPRESSION_RATIO:
                        raise DocumentProcessingError("Document compression ratio exceeds safety limit")
        except BadZipFile as exc:
            raise DocumentProcessingError("Malformed document archive") from exc
