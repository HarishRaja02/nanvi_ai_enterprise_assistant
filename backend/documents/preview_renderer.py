"""HTML Preview Generator for in-memory ephemeral document preview in browser.

Converts documents (Word, Excel, PowerPoint, CSV, TSV, JSON, XML, RTF, Text)
into self-contained, beautifully styled HTML pages that render seamlessly
inside the ephemeral browser preview iframe.
"""
from __future__ import annotations

import html
from pathlib import Path
from backend.documents.models import Document


def render_document_to_html(doc: Document) -> str:
    """Render a parsed Document model into an elegant, standalone HTML preview."""
    filename = html.escape(doc.source.filename)
    file_type = doc.source.file_type.lower()

    if file_type in ("xlsx", "xls", "xlsm", "csv", "tsv") or doc.tables:
        body_content = _render_spreadsheet(doc)
    elif file_type in ("docx", "doc", "rtf"):
        body_content = _render_word_doc(doc)
    elif file_type in ("pptx", "ppt"):
        body_content = _render_presentation(doc)
    elif file_type in ("json", "jsonl", "xml"):
        body_content = _render_code_view(doc, language=file_type)
    else:
        body_content = _render_text_view(doc)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{filename}</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background: #f8fafc;
      color: #0f172a;
      line-height: 1.6;
      padding: 24px;
      -webkit-font-smoothing: antialiased;
    }}
    .preview-container {{
      max-width: 1100px;
      margin: 0 auto;
    }}
    .doc-paper {{
      background: #ffffff;
      border: 1px solid #e2e8f0;
      border-radius: 8px;
      box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05);
      padding: 36px 44px;
      margin-bottom: 24px;
      min-height: 480px;
    }}
    .doc-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-bottom: 16px;
      margin-bottom: 24px;
      border-bottom: 2px solid #e2e8f0;
    }}
    .doc-title {{
      font-size: 20px;
      font-weight: 700;
      color: #0f172a;
    }}
    .doc-badge {{
      display: inline-block;
      padding: 4px 10px;
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      border-radius: 9999px;
      background: #e0f2fe;
      color: #0284c7;
    }}
    /* Spreadsheet table styling */
    .table-section {{
      margin-bottom: 32px;
    }}
    .table-section-title {{
      font-size: 15px;
      font-weight: 700;
      color: #334155;
      margin-bottom: 10px;
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .table-wrapper {{
      overflow-x: auto;
      border: 1px solid #cbd5e1;
      border-radius: 6px;
      background: #ffffff;
      margin-bottom: 16px;
    }}
    table.data-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
      text-align: left;
    }}
    table.data-table th {{
      background: #f1f5f9;
      color: #334155;
      font-weight: 600;
      padding: 10px 14px;
      border-bottom: 2px solid #cbd5e1;
      border-right: 1px solid #e2e8f0;
      white-space: nowrap;
      position: sticky;
      top: 0;
    }}
    table.data-table th:last-child {{
      border-right: none;
    }}
    table.data-table td {{
      padding: 9px 14px;
      border-bottom: 1px solid #e2e8f0;
      border-right: 1px solid #f1f5f9;
      color: #1e293b;
      white-space: nowrap;
    }}
    table.data-table td:last-child {{
      border-right: none;
    }}
    table.data-table tr:hover td {{
      background: #f8fafc;
    }}
    table.data-table tr:last-child td {{
      border-bottom: none;
    }}
    /* Document text styling */
    .doc-paragraph {{
      margin-bottom: 14px;
      font-size: 14.5px;
      line-height: 1.7;
      color: #334155;
      white-space: pre-wrap;
    }}
    .doc-heading {{
      font-size: 18px;
      font-weight: 700;
      color: #0f172a;
      margin-top: 24px;
      margin-bottom: 12px;
      padding-bottom: 6px;
      border-bottom: 1px solid #e2e8f0;
    }}
    /* Slide styling */
    .slide-card {{
      background: #ffffff;
      border: 1px solid #e2e8f0;
      border-radius: 8px;
      padding: 24px 30px;
      margin-bottom: 20px;
      box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }}
    .slide-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 14px;
      padding-bottom: 8px;
      border-bottom: 1px solid #e2e8f0;
    }}
    .slide-badge {{
      font-size: 12px;
      font-weight: 700;
      color: #2563eb;
      background: #eff6ff;
      padding: 3px 8px;
      border-radius: 4px;
    }}
    /* Code styling */
    pre.code-block {{
      background: #0f172a;
      color: #f8fafc;
      padding: 20px;
      border-radius: 8px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
      font-size: 13px;
      line-height: 1.6;
      overflow-x: auto;
      white-space: pre-wrap;
      word-break: break-all;
    }}
  </style>
</head>
<body>
  <div class="preview-container">
    {body_content}
  </div>
</body>
</html>"""


def _render_spreadsheet(doc: Document) -> str:
    """Render spreadsheet sheets and tabular data into clean HTML tables."""
    sections: list[str] = []

    # If structured tables exist
    if doc.tables:
        for tbl in doc.tables:
            label = html.escape(tbl.source_label or "Table")
            header_cells = "".join(f"<th>{html.escape(h)}</th>" for h in tbl.headers)
            header_row = f"<tr>{header_cells}</tr>" if header_cells else ""

            body_rows = []
            for row in tbl.rows:
                cells = "".join(f"<td>{html.escape(cell)}</td>" for cell in row)
                body_rows.append(f"<tr>{cells}</tr>")

            rows_html = "\n".join(body_rows)
            count = len(tbl.rows)
            sections.append(f"""
            <div class="table-section">
              <div class="table-section-title">
                <span>📊 {label}</span>
                <span class="doc-badge">{count} row{'s' if count != 1 else ''}</span>
              </div>
              <div class="table-wrapper">
                <table class="data-table">
                  <thead>{header_row}</thead>
                  <tbody>{rows_html}</tbody>
                </table>
              </div>
            </div>
            """)

    # If no structured tables parsed, or fallback to text chunk
    if not sections and doc.text.strip():
        # Check if text contains pipe-separated or comma-separated rows
        lines = [l.strip() for l in doc.text.splitlines() if l.strip()]
        if any("|" in l for l in lines):
            header = lines[0].split("|")
            headers_html = "".join(f"<th>{html.escape(h.strip())}</th>" for h in header)
            data_rows = []
            for line in lines[1:]:
                if "---" in line:
                    continue
                parts = line.split("|")
                cells_html = "".join(f"<td>{html.escape(p.strip())}</td>" for p in parts)
                data_rows.append(f"<tr>{cells_html}</tr>")
            sections.append(f"""
            <div class="table-section">
              <div class="table-wrapper">
                <table class="data-table">
                  <thead><tr>{headers_html}</tr></thead>
                  <tbody>{'\n'.join(data_rows)}</tbody>
                </table>
              </div>
            </div>
            """)
        else:
            escaped_text = html.escape(doc.text)
            sections.append(f'<div class="doc-paper"><pre style="font-family: monospace; font-size: 13px; white-space: pre-wrap;">{escaped_text}</pre></div>')

    return f"""
    <div class="doc-paper">
      <div class="doc-header">
        <h1 class="doc-title">{html.escape(doc.source.filename)}</h1>
        <span class="doc-badge">{html.escape(doc.source.file_type.upper())} SPREADSHEET</span>
      </div>
      {''.join(sections)}
    </div>
    """


def _render_word_doc(doc: Document) -> str:
    """Render Word / RTF documents into clean document pages."""
    paragraphs: list[str] = []
    for line in doc.text.split("\n\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith("[Table ") and "]" in line:
            continue
        if len(line) < 80 and not line.endswith((".", ",", ";", ":", "?", "!")) and "\n" not in line:
            paragraphs.append(f'<h2 class="doc-heading">{html.escape(line)}</h2>')
        else:
            paragraphs.append(f'<p class="doc-paragraph">{html.escape(line)}</p>')

    # Append any structured tables
    tables_html = []
    if doc.tables:
        for tbl in doc.tables:
            label = html.escape(tbl.source_label or "Table")
            header_cells = "".join(f"<th>{html.escape(h)}</th>" for h in tbl.headers)
            body_rows = ["<tr>" + "".join(f"<td>{html.escape(c)}</td>" for c in row) + "</tr>" for row in tbl.rows]
            tables_html.append(f"""
            <div class="table-section">
              <div class="table-section-title"><span>{label}</span></div>
              <div class="table-wrapper">
                <table class="data-table">
                  <thead><tr>{header_cells}</tr></thead>
                  <tbody>{'\n'.join(body_rows)}</tbody>
                </table>
              </div>
            </div>
            """)

    return f"""
    <div class="doc-paper">
      <div class="doc-header">
        <h1 class="doc-title">{html.escape(doc.source.filename)}</h1>
        <span class="doc-badge">{html.escape(doc.source.file_type.upper())} DOCUMENT</span>
      </div>
      <div class="doc-body">
        {''.join(paragraphs)}
        {''.join(tables_html)}
      </div>
    </div>
    """


def _render_presentation(doc: Document) -> str:
    """Render presentation slides into individual visual cards."""
    slides = []
    chunks = doc.text.split("[Slide ")
    if len(chunks) > 1:
        for chunk in chunks[1:]:
            parts = chunk.split("]\n", 1)
            slide_no = parts[0]
            slide_text = parts[1] if len(parts) > 1 else ""
            lines_html = "".join(f'<p class="doc-paragraph">• {html.escape(l.strip())}</p>' for l in slide_text.splitlines() if l.strip())
            slides.append(f"""
            <div class="slide-card">
              <div class="slide-header">
                <span class="slide-badge">Slide {html.escape(slide_no)}</span>
              </div>
              <div>{lines_html}</div>
            </div>
            """)
    else:
        escaped_text = html.escape(doc.text)
        slides.append(f'<div class="slide-card"><pre class="doc-paragraph">{escaped_text}</pre></div>')

    return f"""
    <div style="max-width: 900px; margin: 0 auto;">
      <div class="doc-header" style="background: #ffffff; padding: 18px 24px; border-radius: 8px; margin-bottom: 20px; border: 1px solid #e2e8f0;">
        <h1 class="doc-title">{html.escape(doc.source.filename)}</h1>
        <span class="doc-badge">PRESENTATION</span>
      </div>
      {''.join(slides)}
    </div>
    """


def _render_code_view(doc: Document, language: str) -> str:
    """Render JSON, XML, or code files with monospace formatted blocks."""
    escaped = html.escape(doc.text)
    return f"""
    <div class="doc-paper">
      <div class="doc-header">
        <h1 class="doc-title">{html.escape(doc.source.filename)}</h1>
        <span class="doc-badge">{html.escape(language.upper())}</span>
      </div>
      <pre class="code-block"><code>{escaped}</code></pre>
    </div>
    """


def _render_text_view(doc: Document) -> str:
    """Render plain text, markdown, or log files."""
    escaped = html.escape(doc.text)
    return f"""
    <div class="doc-paper">
      <div class="doc-header">
        <h1 class="doc-title">{html.escape(doc.source.filename)}</h1>
        <span class="doc-badge">{html.escape(doc.source.file_type.upper())} FILE</span>
      </div>
      <div style="font-family: inherit; font-size: 14.5px; line-height: 1.7; white-space: pre-wrap; color: #1e293b;">
        {escaped}
      </div>
    </div>
    """

