"""JSON parser — renders JSON files as readable structured text."""
import json
from datetime import datetime
from ..parser import DocumentParser
from ..models import Document
from .common import source_for, metadata_for


class JSONParser(DocumentParser):
    extensions = frozenset({".json", ".jsonl"})

    def parse_bytes(self, *, filename: str, relative_path: str, data: bytes,
                    modified_at: datetime | None = None) -> Document:
        decoded = None
        for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
            try:
                decoded = data.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if decoded is None:
            decoded = data.decode("utf-8", errors="replace")

        # Try to parse and pretty-print JSON
        try:
            if filename.casefold().endswith(".jsonl"):
                # Handle JSON Lines format
                lines = []
                for line in decoded.strip().splitlines():
                    line = line.strip()
                    if line:
                        try:
                            obj = json.loads(line)
                            lines.append(json.dumps(obj, indent=2, ensure_ascii=False))
                        except json.JSONDecodeError:
                            lines.append(line)
                text = "\n---\n".join(lines)
            else:
                parsed = json.loads(decoded)
                text = json.dumps(parsed, indent=2, ensure_ascii=False)
        except json.JSONDecodeError:
            # If JSON is invalid, just use raw text
            text = decoded

        return Document(source_for(filename, relative_path, "json"),
                        metadata_for(len(data), modified_at), text, [], ["JSON"])

