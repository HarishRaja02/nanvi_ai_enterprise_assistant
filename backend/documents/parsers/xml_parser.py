"""XML parser — extracts text content from XML documents."""
import re
from datetime import datetime
from ..parser import DocumentParser
from ..models import Document
from .common import source_for, metadata_for


class XMLParser(DocumentParser):
    extensions = frozenset({".xml"})

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

        text = self._extract_text(decoded)
        return Document(source_for(filename, relative_path, "xml"),
                        metadata_for(len(data), modified_at), text, [], ["XML"])

    @staticmethod
    def _extract_text(xml_content: str) -> str:
        """Extract text content from XML using lxml if available, else regex fallback."""
        try:
            from lxml import etree
            root = etree.fromstring(xml_content.encode("utf-8"))
            texts = []
            for element in root.iter():
                if element.text and element.text.strip():
                    texts.append(element.text.strip())
                if element.tail and element.tail.strip():
                    texts.append(element.tail.strip())
            return "\n".join(texts) if texts else xml_content
        except Exception:
            # Regex fallback: strip XML tags, preserve text
            result = re.sub(r'<[^>]+>', ' ', xml_content)
            result = re.sub(r'\s+', ' ', result)
            return result.strip()

