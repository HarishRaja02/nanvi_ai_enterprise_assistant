from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class SourceType(StrEnum):
    FILE = "file"
    EMAIL = "email"
    DATABASE = "database"
    DOCUMENT = "document"
    WEBSITE = "website"  # reserved for a future connector
    DRIVE = "drive"


@dataclass(frozen=True)
class SourceReference:
    """Safe, frontend-facing citation metadata.

    Deliberately excludes raw content, filesystem paths, SQL text, access tokens,
    database credentials, and other infrastructure details. ``reference_id`` is
    an opaque identifier used by the secure source endpoint.
    """

    reference_id: str
    source_type: SourceType
    display_name: str
    title: str | None = None
    location: str | None = None
    page: int | None = None
    sheet: str | None = None
    timestamp: datetime | None = None
    mime_type: str | None = None
    href: str | None = None

    def to_frontend_dict(self) -> dict:
        return {
            "reference_id": self.reference_id,
            "source_type": self.source_type.value,
            "display_name": self.display_name,
            "title": self.title,
            "location": self.location,
            "page": self.page,
            "sheet": self.sheet,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "mime_type": self.mime_type,
            "href": self.href,
        }
