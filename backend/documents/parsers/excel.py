from datetime import datetime
from io import BytesIO, StringIO
import csv
import re
from ..parser import DocumentParser
from ..models import Document, DocumentTable
from .common import source_for, metadata_for, clean


class ExcelParser(DocumentParser):
    extensions = frozenset({".xlsx", ".xlsm", ".xltx", ".xltm", ".xls"})

    def parse_bytes(self, *, filename: str, relative_path: str, data: bytes, modified_at: datetime | None = None) -> Document:
        ext = filename.casefold().split(".")[-1] if "." in filename else "xlsx"
        file_type = ext

        # OOXML OpenPyXL handling (.xlsx, .xlsm, .xltx, .xltm or zip-based .xls)
        if data.startswith(b"PK\x03\x04") or ext in ("xlsx", "xlsm", "xltx", "xltm"):
            try:
                from openpyxl import load_workbook
                workbook = load_workbook(BytesIO(data), read_only=True, data_only=True)
                tables, chunks, locations = [], [], []
                try:
                    for sheet in workbook.worksheets:
                        rows = [[clean(v) for v in row] for row in sheet.iter_rows(values_only=True)]
                        rows = [r for r in rows if any(r)]
                        headers, body = (rows[0], rows[1:]) if rows else ([], [])
                        if len(rows) >= 2:
                            header_line = " | ".join(rows[0])
                            sep_line = " | ".join(["---"] * len(rows[0]))
                            data_lines = [" | ".join(r) for r in rows[1:]]
                            chunks.append(f"[Sheet {sheet.title}]\n" + "\n".join([header_line, sep_line, *data_lines]))
                            tables.append(DocumentTable(headers=headers, rows=body, source_label=f"Sheet {sheet.title}"))
                        else:
                            chunks.append(f"[Sheet {sheet.title}]\n" + "\n".join(" | ".join(r) for r in rows))
                        locations.append(f"Sheet {sheet.title}")
                finally:
                    workbook.close()

                return Document(
                    source_for(filename, relative_path, file_type),
                    metadata_for(len(data), modified_at),
                    "\n\n".join(chunks),
                    tables,
                    locations,
                )
            except Exception as exc:
                if ext != "xls":
                    raise ValueError(f"Malformed {ext.upper()} document") from exc

        # Handling for legacy .xls (SpreadsheetML XML, HTML table, CSV-in-XLS, or binary BIFF)
        tables, chunks, locations = self._parse_legacy_xls(data, filename)
        return Document(
            source_for(filename, relative_path, "xls"),
            metadata_for(len(data), modified_at),
            "\n\n".join(chunks),
            tables,
            locations or ["Sheet 1"],
        )

    @classmethod
    def _parse_legacy_xls(cls, data: bytes, filename: str) -> tuple[list[DocumentTable], list[str], list[str]]:
        """Parse legacy .xls files: handles XML SpreadsheetML, HTML tables, and binary streams."""
        # Try text decoding first
        decoded = None
        for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
            try:
                decoded = data.decode(enc)
                break
            except UnicodeDecodeError:
                continue

        if decoded:
            # 1. Check for XML SpreadsheetML format (very common in enterprise exports named .xls)
            if "<Workbook" in decoded and "<Worksheet" in decoded:
                try:
                    from lxml import etree
                    # Strip namespace prefixes for easier parsing
                    clean_xml = re.sub(r'\sxmlns(:\w+)?="[^"]+"', '', decoded)
                    root = etree.fromstring(clean_xml.encode("utf-8"))
                    tables, chunks, locations = [], [], []
                    for ws in root.xpath("//Worksheet"):
                        sheet_name = ws.get("Name") or ws.get("name") or "Sheet"
                        rows = []
                        for row in ws.xpath(".//Row"):
                            row_cells = []
                            for cell in row.xpath(".//Cell"):
                                data_elem = cell.find("Data")
                                text = data_elem.text if data_elem is not None and data_elem.text else ""
                                row_cells.append(clean(text))
                            if any(row_cells):
                                rows.append(row_cells)
                        if rows:
                            headers, body = (rows[0], rows[1:]) if len(rows) >= 2 else (rows[0], [])
                            header_line = " | ".join(rows[0])
                            data_lines = [" | ".join(r) for r in rows[1:]]
                            chunks.append(f"[Sheet {sheet_name}]\n" + "\n".join([header_line, *data_lines]))
                            tables.append(DocumentTable(headers=headers, rows=body, source_label=f"Sheet {sheet_name}"))
                            locations.append(f"Sheet {sheet_name}")
                    if tables or chunks:
                        return tables, chunks, locations
                except Exception:
                    pass

            # 2. Check for HTML Table in .xls (used by web apps exporting to Excel)
            if "<table" in decoded.lower():
                try:
                    from lxml.html import fromstring
                    doc = fromstring(decoded)
                    tables, chunks, locations = [], [], []
                    for idx, tbl in enumerate(doc.xpath("//table"), start=1):
                        rows = []
                        for tr in tbl.xpath(".//tr"):
                            cells = [clean(c.text_content()) for c in tr.xpath(".//td | .//th")]
                            if any(cells):
                                rows.append(cells)
                        if rows:
                            headers, body = (rows[0], rows[1:]) if len(rows) >= 2 else (rows[0], [])
                            header_line = " | ".join(rows[0])
                            data_lines = [" | ".join(r) for r in rows[1:]]
                            chunks.append(f"[Table {idx}]\n" + "\n".join([header_line, *data_lines]))
                            tables.append(DocumentTable(headers=headers, rows=body, source_label=f"Table {idx}"))
                            locations.append(f"Table {idx}")
                    if tables or chunks:
                        return tables, chunks, locations
                except Exception:
                    pass

        # 3. Binary BIFF stream text extraction
        runs = [
            m.group(0).strip()
            for m in re.finditer(r"[A-Za-z0-9\s.,!?:;\-\'\"()/@#$%+=<>{}\[\]]{3,}", data.decode("latin-1", errors="ignore"))
            if len(m.group(0).strip()) >= 3 and not m.group(0).strip().startswith(("\x00", "Workbook", "Root Entry"))
        ]
        text_content = "\n".join(runs) if runs else "Spreadsheet data loaded."
        chunk = f"[Sheet 1]\n{text_content}"
        return [], [chunk], ["Sheet 1"]
