"""HTML parser — extracts visible text content from HTML documents."""
import re
from datetime import datetime
from ..parser import DocumentParser
from ..models import Document
from .common import source_for, metadata_for


class HTMLParser(DocumentParser):
    extensions = frozenset({".html", ".htm"})

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
        return Document(source_for(filename, relative_path, "html"),
                        metadata_for(len(data), modified_at), text, [], ["HTML"])

    @staticmethod
    def _extract_text(html: str) -> str:
        """Extract visible text from HTML using lxml if available, else regex fallback."""
        try:
            from lxml import etree
            from lxml.html import fromstring, tostring
            doc = fromstring(html)
            # Remove script, style, and head elements
            for element in doc.iter("script", "style", "head", "noscript"):
                element.getparent().remove(element)
            text = doc.text_content()
            # Normalize whitespace
            text = re.sub(r'\n{3,}', '\n\n', text)
            return text.strip()
        except Exception:
            # Regex fallback
            result = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
            result = re.sub(r'<style[^>]*>.*?</style>', '', result, flags=re.DOTALL | re.IGNORECASE)
            result = re.sub(r'<head[^>]*>.*?</head>', '', result, flags=re.DOTALL | re.IGNORECASE)
            result = re.sub(r'<br\s*/?\s*>', '\n', result, flags=re.IGNORECASE)
            result = re.sub(r'</(?:p|div|h[1-6]|li|tr|td|th|blockquote|pre)>', '\n', result, flags=re.IGNORECASE)
            result = re.sub(r'<[^>]+>', '', result)
            result = re.sub(r'&nbsp;', ' ', result)
            result = re.sub(r'&amp;', '&', result)
            result = re.sub(r'&lt;', '<', result)
            result = re.sub(r'&gt;', '>', result)
            result = re.sub(r'&quot;', '"', result)
            result = re.sub(r'&#?\w+;', '', result)
            result = re.sub(r'\n{3,}', '\n\n', result)
            return result.strip()

