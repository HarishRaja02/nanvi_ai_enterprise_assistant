"""RTF (Rich Text Format) parser — strips RTF control words and extracts plain text."""
import re
from datetime import datetime
from ..parser import DocumentParser
from ..models import Document
from .common import source_for, metadata_for


class RTFParser(DocumentParser):
    extensions = frozenset({".rtf"})

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

        text = self._strip_rtf(decoded)
        return Document(source_for(filename, relative_path, "rtf"),
                        metadata_for(len(data), modified_at), text, [], ["RTF"])

    @staticmethod
    def _strip_rtf(rtf: str) -> str:
        """Simplistic RTF-to-plaintext: remove control words, groups, and escapes."""
        # Remove binary data blocks
        result = re.sub(r'\\pict[^}]*}', '', rtf)
        result = re.sub(r'\\fonttbl[^}]*}', '', result)
        result = re.sub(r'\\colortbl[^}]*}', '', result)
        result = re.sub(r'\\stylesheet[^}]*}', '', result)
        result = re.sub(r'\\info[^}]*}', '', result)
        # Replace common RTF paragraph/line breaks with newlines
        result = re.sub(r'\\par\b', '\n', result)
        result = re.sub(r'\\line\b', '\n', result)
        result = re.sub(r'\\tab\b', '\t', result)
        # Remove all remaining RTF control words (e.g. \b, \i, \fs24, \f0)
        result = re.sub(r'\\[a-z]{1,32}-?\d*\s?', '', result)
        # Remove hex escapes like \'e9
        result = re.sub(r"\\'[0-9a-fA-F]{2}", '', result)
        # Remove braces
        result = result.replace('{', '').replace('}', '')
        # Clean up whitespace
        result = re.sub(r'\n{3,}', '\n\n', result)
        return result.strip()

