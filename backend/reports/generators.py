from __future__ import annotations

from abc import ABC, abstractmethod
from html import escape
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from docx import Document
from docx.shared import Pt
from pptx import Presentation
from pptx.util import Inches, Pt as PptPt

from .models import ReportRequest


class ReportGenerator(ABC):
    extension: str

    @abstractmethod
    def generate(self, request: ReportRequest, destination: Path) -> None:
        raise NotImplementedError

    @staticmethod
    def _rows(data: Any) -> list[dict[str, Any]]:
        if isinstance(data, list) and all(isinstance(row, dict) for row in data):
            return data
        if isinstance(data, tuple) and all(isinstance(row, dict) for row in data):
            return list(data)
        if isinstance(data, dict):
            # Scalar/keyed analysis results become a compact key/value table.
            return [{"metric": key, "value": value} for key, value in data.items()]
        return [{"value": data}]

    @classmethod
    def _table_data(cls, data: Any) -> tuple[list[str], list[list[str]]]:
        rows = cls._rows(data)
        columns: list[str] = []
        for row in rows:
            for key in row:
                if key not in columns:
                    columns.append(str(key))
        values = [[cls._display(row.get(column)) for column in columns] for row in rows]
        return columns, values

    @staticmethod
    def _display(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, float):
            return f"{value:,.4f}".rstrip("0").rstrip(".")
        return str(value)

    @staticmethod
    def _excel_safe(value: Any) -> Any:
        # Prevent formula injection when untrusted strings are opened in Excel,
        # while preserving genuine numeric/date values for correct calculations.
        if isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
            return "'" + value
        return value

    @staticmethod
    def _lineage_rows(request: ReportRequest) -> list[list[str]]:
        # Reports expose human-safe lineage only; never embed raw SQL or source IDs.
        return [
            [lineage.source_type, lineage.source_label,
             ", ".join(lineage.columns), "; ".join(lineage.filters)]
            for lineage in request.lineage
        ]


class ExcelReportGenerator(ReportGenerator):
    extension = "xlsx"

    def generate(self, request: ReportRequest, destination: Path) -> None:
        from openpyxl.styles import PatternFill, Alignment, Border, Side
        from datetime import datetime, timezone

        wb = Workbook()
        ws = wb.active
        ws.title = "Report"

        # Document Header
        ws.append([self._excel_safe(request.title)])
        ws["A1"].font = Font(name="Calibri", bold=True, size=16, color="0F172A")

        if request.description:
            ws.append([self._excel_safe(request.description)])
            ws["A2"].font = Font(name="Calibri", italic=True, size=10, color="334155")
        ws.append([])

        rows_raw = self._rows(request.data)
        columns: list[str] = []
        for row in rows_raw:
            for key in row:
                if key not in columns:
                    columns.append(str(key))

        ws.append(columns or ["No data"])
        header_row = ws.max_row

        header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
        header_font = Font(name="Calibri", bold=True, size=10, color="FFFFFF")
        thin_border = Border(
            left=Side(style="thin", color="CBD5E1"),
            right=Side(style="thin", color="CBD5E1"),
            top=Side(style="thin", color="CBD5E1"),
            bottom=Side(style="thin", color="CBD5E1"),
        )
        zebra_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")

        for cell in ws[header_row]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(vertical="center", horizontal="left")

        for r_idx, row in enumerate(rows_raw):
            row_vals = []
            for c_idx, column in enumerate(columns):
                val = row.get(column)
                row_vals.append(self._excel_safe(val))
            ws.append(row_vals)
            curr_row = ws.max_row
            is_even = r_idx % 2 == 1
            for cell in ws[curr_row]:
                cell.font = Font(name="Calibri", size=10, color="0F172A")
                cell.border = thin_border
                if is_even:
                    cell.fill = zebra_fill

        for idx, column in enumerate(columns, 1):
            col_letter = get_column_letter(idx)
            max_len = max(len(str(column)), 12)
            for r in range(header_row, ws.max_row + 1):
                cell_val = ws[f"{col_letter}{r}"].value
                if cell_val is not None:
                    max_len = max(max_len, len(str(cell_val)))
            ws.column_dimensions[col_letter].width = min(max_len + 3, 40)

        lineage = wb.create_sheet("Sources")
        lineage.append(["Source Type", "Source Label", "Columns", "Filters"])
        lineage["A1"].font = Font(bold=True)
        lineage["B1"].font = Font(bold=True)
        lineage["C1"].font = Font(bold=True)
        lineage["D1"].font = Font(bold=True)
        for row in self._lineage_rows(request):
            lineage.append([self._excel_safe(str(value)) for value in row])
        for col_idx in range(1, 5):
            lineage.column_dimensions[get_column_letter(col_idx)].width = 25

        wb.save(destination)


class PDFReportGenerator(ReportGenerator):
    extension = "pdf"

    def generate(self, request: ReportRequest, destination: Path) -> None:
        from datetime import datetime, timezone

        columns, rows = self._table_data(request.data)
        if not columns:
            columns, rows = ["Result"], [["No data available"]]

        display_cols = [str(c).title().replace("_", " ") for c in columns]

        doc = SimpleDocTemplate(
            str(destination),
            pagesize=landscape(A4),
            rightMargin=36,
            leftMargin=36,
            topMargin=36,
            bottomMargin=36,
        )
        styles = getSampleStyleSheet()

        title_style = styles["Title"]
        title_style.fontName = "Helvetica-Bold"
        title_style.fontSize = 20
        title_style.leading = 24
        title_style.textColor = colors.HexColor("#0F172A")
        title_style.alignment = 0

        body_style = styles["BodyText"]
        body_style.fontName = "Helvetica"
        body_style.fontSize = 8.5
        body_style.leading = 11
        body_style.textColor = colors.HexColor("#1E293B")

        cell_header_style = styles["Normal"]
        cell_header_style.fontName = "Helvetica-Bold"
        cell_header_style.fontSize = 9
        cell_header_style.leading = 12
        cell_header_style.textColor = colors.white

        meta_style = styles["Italic"]
        meta_style.fontName = "Helvetica-Oblique"
        meta_style.fontSize = 8.5
        meta_style.leading = 11
        meta_style.textColor = colors.HexColor("#64748B")

        h2_style = styles["Heading2"]
        h2_style.fontName = "Helvetica-Bold"
        h2_style.fontSize = 12
        h2_style.leading = 16
        h2_style.textColor = colors.HexColor("#0F172A")

        now_str = datetime.now(timezone.utc).strftime("%B %d, %Y %H:%M UTC")
        story = [
            Paragraph(escape(request.title), title_style),
            Spacer(1, 4),
            Paragraph(escape(f"CONFIDENTIAL ENTERPRISE DOCUMENT  •  Generated: {now_str}  •  Tenant: {request.tenant_id}"), meta_style),
            Spacer(1, 14),
        ]

        if request.description:
            story.append(Paragraph(escape(request.description), body_style))
            story.append(Spacer(1, 12))

        # Wrap cells in Paragraph to prevent text clipping and enable neat wrapping
        formatted_rows = [
            [Paragraph(escape(str(val)), body_style) for val in row]
            for row in rows
        ]
        header_cells = [Paragraph(escape(c), cell_header_style) for c in display_cols]
        table_data = [header_cells] + formatted_rows

        # Calculate proportional column widths to fit A4 landscape (770 pt available)
        usable_width = 770.0
        num_cols = max(len(columns), 1)
        col_width = usable_width / num_cols
        table = Table(table_data, colWidths=[col_width] * num_cols, repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E293B")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 9),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
            ("TOPPADDING", (0, 0), (-1, 0), 6),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 5),
            ("TOPPADDING", (0, 1), (-1, -1), 5),
        ]))
        story.append(table)
        story.append(Spacer(1, 14))

        story.append(Paragraph("Governance & Audit Lineage", h2_style))
        for lineage in request.lineage:
            story.append(Paragraph(
                escape(f"• {lineage.source_type.upper()}: {lineage.source_label} (Columns: {', '.join(lineage.columns)})"),
                meta_style,
            ))

        doc.build(story)


class WordReportGenerator(ReportGenerator):
    extension = "docx"

    def generate(self, request: ReportRequest, destination: Path) -> None:
        from datetime import datetime, timezone
        from docx import Document
        from docx.shared import Inches, Pt, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.enum.table import WD_TABLE_ALIGNMENT
        from docx.oxml import parse_xml
        from docx.oxml.ns import nsdecls

        document = Document()

        # Page setup: Standard Letter with 1-inch margins
        for section in document.sections:
            section.top_margin = Inches(1.0)
            section.bottom_margin = Inches(1.0)
            section.left_margin = Inches(1.0)
            section.right_margin = Inches(1.0)

        # 1. Document Header / Title
        title_para = document.add_paragraph()
        title_para.alignment = WD_ALIGN_PARAGRAPH.LEFT
        title_run = title_para.add_run(request.title[:200])
        title_run.font.name = "Calibri"
        title_run.font.size = Pt(20)
        title_run.font.bold = True
        title_run.font.color.rgb = RGBColor(15, 23, 42)
        title_para.paragraph_format.space_after = Pt(4)
        title_para.paragraph_format.space_before = Pt(0)

        # 2. Metadata Banner
        meta_para = document.add_paragraph()
        meta_run1 = meta_para.add_run("CONFIDENTIAL ENTERPRISE DOCUMENT  •  ")
        meta_run1.font.name = "Calibri"
        meta_run1.font.size = Pt(9)
        meta_run1.font.bold = True
        meta_run1.font.color.rgb = RGBColor(37, 99, 235)

        now_str = datetime.now(timezone.utc).strftime("%B %d, %Y %H:%M UTC")
        meta_run2 = meta_para.add_run(f"Generated: {now_str}  •  Tenant: {request.tenant_id}")
        meta_run2.font.name = "Calibri"
        meta_run2.font.size = Pt(9)
        meta_run2.font.color.rgb = RGBColor(100, 116, 139)
        meta_para.paragraph_format.space_after = Pt(14)

        # Divider line
        div_para = document.add_paragraph()
        div_run = div_para.add_run("―" * 54)
        div_run.font.size = Pt(8)
        div_run.font.color.rgb = RGBColor(226, 232, 240)
        div_para.paragraph_format.space_after = Pt(12)

        # 3. Executive Description / Overview
        if request.description:
            desc_heading = document.add_paragraph()
            desc_h_run = desc_heading.add_run("Executive Overview")
            desc_h_run.font.name = "Calibri"
            desc_h_run.font.size = Pt(13)
            desc_h_run.font.bold = True
            desc_h_run.font.color.rgb = RGBColor(15, 23, 42)
            desc_heading.paragraph_format.space_after = Pt(4)

            desc_para = document.add_paragraph()
            desc_run = desc_para.add_run(request.description[:4000])
            desc_run.font.name = "Calibri"
            desc_run.font.size = Pt(10.5)
            desc_run.font.color.rgb = RGBColor(51, 65, 85)
            desc_para.paragraph_format.space_after = Pt(14)

        # 4. Data Section Heading
        data_heading = document.add_paragraph()
        data_h_run = data_heading.add_run("Authorized Record Schedule")
        data_h_run.font.name = "Calibri"
        data_h_run.font.size = Pt(13)
        data_h_run.font.bold = True
        data_h_run.font.color.rgb = RGBColor(15, 23, 42)
        data_heading.paragraph_format.space_after = Pt(6)

        # 5. Formatted Professional Table
        columns, rows = self._table_data(request.data)
        if not columns:
            columns, rows = ["Result"], [["No data available"]]

        num_cols = len(columns)
        table = document.add_table(rows=1, cols=num_cols)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        table.autofit = True

        header_row = table.rows[0]
        header_tr_pr = header_row._tr.get_or_add_trPr()
        header_tr_pr.append(parse_xml(f'<w:tblHeader {nsdecls("w")}/>'))

        for idx, (cell, val) in enumerate(zip(header_row.cells, columns)):
            shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="1E293B"/>')
            cell._tc.get_or_add_tcPr().append(shd)

            tc_mar = parse_xml(f'<w:tcMar {nsdecls("w")}><w:top w:w="120" w:type="dxa"/><w:bottom w:w="120" w:type="dxa"/><w:left w:w="140" w:type="dxa"/><w:right w:w="140" w:type="dxa"/></w:tcMar>')
            cell._tc.get_or_add_tcPr().append(tc_mar)

            cell.text = str(val).title().replace("_", " ")
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            for r in p.runs:
                r.font.name = "Calibri"
                r.font.bold = True
                r.font.size = Pt(9.5)
                r.font.color.rgb = RGBColor(255, 255, 255)

        for r_idx, row in enumerate(rows):
            new_row = table.add_row()
            bg_color = "F8FAFC" if r_idx % 2 == 1 else "FFFFFF"

            for c_idx, (cell, val) in enumerate(zip(new_row.cells, row)):
                shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{bg_color}"/>')
                cell._tc.get_or_add_tcPr().append(shd)

                tc_mar = parse_xml(f'<w:tcMar {nsdecls("w")}><w:top w:w="90" w:type="dxa"/><w:bottom w:w="90" w:type="dxa"/><w:left w:w="140" w:type="dxa"/><w:right w:w="140" w:type="dxa"/></w:tcMar>')
                cell._tc.get_or_add_tcPr().append(tc_mar)

                disp_val = str(val)
                cell.text = disp_val
                p = cell.paragraphs[0]
                p.alignment = WD_ALIGN_PARAGRAPH.RIGHT if (disp_val.startswith("$") or "INR" in disp_val) else WD_ALIGN_PARAGRAPH.LEFT
                for r in p.runs:
                    r.font.name = "Calibri"
                    r.font.size = Pt(9.5)
                    r.font.color.rgb = RGBColor(15, 23, 42)

        tbl_pr = table._tbl.tblPr
        tbl_borders = parse_xml(
            f'<w:tblBorders {nsdecls("w")}>'
            f'<w:top w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/>'
            f'<w:bottom w:val="single" w:sz="6" w:space="0" w:color="94A3B8"/>'
            f'<w:insideH w:val="single" w:sz="4" w:space="0" w:color="E2E8F0"/>'
            f'<w:insideV w:val="none"/>'
            f'<w:left w:val="none"/>'
            f'<w:right w:val="none"/>'
            f'</w:tblBorders>'
        )
        tbl_pr.append(tbl_borders)

        # 6. Sources & Compliance Footer
        document.add_paragraph().paragraph_format.space_before = Pt(16)
        src_h = document.add_paragraph()
        src_h_run = src_h.add_run("Governance & Audit Lineage")
        src_h_run.font.name = "Calibri"
        src_h_run.font.size = Pt(11)
        src_h_run.font.bold = True
        src_h_run.font.color.rgb = RGBColor(71, 85, 105)
        src_h.paragraph_format.space_after = Pt(4)

        for lineage in request.lineage:
            src_p = document.add_paragraph()
            src_p.paragraph_format.space_after = Pt(2)
            b_run = src_p.add_run(f"• {lineage.source_type.upper()}: ")
            b_run.font.name = "Calibri"
            b_run.font.bold = True
            b_run.font.size = Pt(9)
            b_run.font.color.rgb = RGBColor(100, 116, 139)

            d_run = src_p.add_run(f"{lineage.source_label} (Columns: {', '.join(lineage.columns)})")
            d_run.font.name = "Calibri"
            d_run.font.size = Pt(9)
            d_run.font.color.rgb = RGBColor(100, 116, 139)

        document.save(destination)


class TextReportGenerator(ReportGenerator):
    extension = "txt"

    def generate(self, request: ReportRequest, destination: Path) -> None:
        from datetime import datetime, timezone

        columns, rows = self._table_data(request.data)
        if not columns:
            columns, rows = ["Result"], [["No data available"]]

        display_cols = [str(c).title().replace("_", " ") for c in columns]
        col_widths = [len(c) for c in display_cols]
        for row in rows:
            for idx, val in enumerate(row):
                if idx < len(col_widths):
                    col_widths[idx] = max(col_widths[idx], len(str(val)))

        lines = [
            "=" * 80,
            f"  {request.title.upper()}",
            "=" * 80,
            f"Classification: CONFIDENTIAL ENTERPRISE DOCUMENT",
            f"Generated:      {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
            f"Tenant ID:      {request.tenant_id}",
            f"Format:         Plain Text (.txt)",
            "-" * 80,
        ]
        if request.description:
            lines.extend([request.description, "-" * 80])
        lines.append("")

        header_str = " | ".join(c.ljust(col_widths[i]) for i, c in enumerate(display_cols))
        sep_str = "-+-".join("-" * col_widths[i] for i in range(len(col_widths)))
        lines.append(header_str)
        lines.append(sep_str)

        for row in rows:
            row_str = " | ".join(str(row[i] if i < len(row) else "").ljust(col_widths[i]) for i in range(len(col_widths)))
            lines.append(row_str)

        lines.extend([
            "",
            "-" * 80,
            "AUDIT & DATA LINEAGE:",
        ])
        for lineage in request.lineage:
            lines.append(f"• {lineage.source_type.upper()}: {lineage.source_label} (Columns: {', '.join(lineage.columns)})")
        lines.extend([
            "=" * 80,
            "Nanvi AI Enterprise Assistant — Official Document Output",
            "=" * 80,
        ])
        destination.write_text("\n".join(lines), encoding="utf-8")


class PowerPointReportGenerator(ReportGenerator):
    extension = "pptx"

    def generate(self, request: ReportRequest, destination: Path) -> None:
        from pptx.dml.color import RGBColor
        from pptx.enum.text import PP_ALIGN
        from datetime import datetime, timezone

        prs = Presentation()
        # Set modern 16:9 widescreen layout (13.33 x 7.5 inches)
        prs.slide_width = Inches(13.333)
        prs.slide_height = Inches(7.5)

        # ── Slide 1: Executive Title Slide (Dark Sleek Slate) ──
        blank_slide_layout = prs.slide_layouts[6]
        slide1 = prs.slides.add_slide(blank_slide_layout)

        # Background fill
        bg_shape = slide1.shapes.add_shape(1, 0, 0, prs.slide_width, prs.slide_height)  # MSO_SHAPE.RECTANGLE = 1
        bg_shape.fill.solid()
        bg_shape.fill.fore_color.rgb = RGBColor(15, 23, 42)  # #0F172A
        bg_shape.line.fill.background()

        # Accent top bar
        bar_shape = slide1.shapes.add_shape(1, 0, 0, prs.slide_width, Inches(0.12))
        bar_shape.fill.solid()
        bar_shape.fill.fore_color.rgb = RGBColor(37, 99, 235)  # Royal Blue
        bar_shape.line.fill.background()

        # Title Box
        title_box = slide1.shapes.add_textbox(Inches(1.2), Inches(2.2), Inches(11.0), Inches(2.0))
        tf = title_box.text_frame
        tf.word_wrap = True
        p_title = tf.paragraphs[0]
        p_title.text = request.title[:150]
        p_title.font.name = "Calibri"
        p_title.font.size = PptPt(36)
        p_title.font.bold = True
        p_title.font.color.rgb = RGBColor(255, 255, 255)

        now_str = datetime.now(timezone.utc).strftime("%B %d, %Y")
        p_sub = tf.add_paragraph()
        p_sub.text = f"Official Executive Deck  •  {now_str}  •  Tenant: {request.tenant_id}"
        p_sub.font.name = "Calibri"
        p_sub.font.size = PptPt(14)
        p_sub.font.color.rgb = RGBColor(148, 163, 184)  # Slate 400
        p_sub.space_before = PptPt(14)

        if request.description:
            p_desc = tf.add_paragraph()
            p_desc.text = request.description[:300]
            p_desc.font.name = "Calibri"
            p_desc.font.size = PptPt(12)
            p_desc.font.color.rgb = RGBColor(203, 213, 225)
            p_desc.space_before = PptPt(10)

        # Confidentiality Tag
        conf_box = slide1.shapes.add_textbox(Inches(1.2), Inches(6.2), Inches(10.0), Inches(0.5))
        p_conf = conf_box.text_frame.paragraphs[0]
        p_conf.text = "CONFIDENTIAL ENTERPRISE DOCUMENT  —  AUTHORIZED ACCESS ONLY"
        p_conf.font.name = "Calibri"
        p_conf.font.size = PptPt(10)
        p_conf.font.bold = True
        p_conf.font.color.rgb = RGBColor(56, 189, 248)

        # ── Slide 2+: Data Schedule Slides ──
        columns, rows = self._table_data(request.data)
        if not columns:
            columns, rows = ["Result"], [["No data available"]]

        chunk_size = 12
        for offset in range(0, len(rows), chunk_size):
            chunk = rows[offset:offset + chunk_size]
            page_num = (offset // chunk_size) + 1
            total_pages = (len(rows) + chunk_size - 1) // chunk_size or 1

            slide = prs.slides.add_slide(blank_slide_layout)

            # Slide Header Banner
            header_box = slide.shapes.add_textbox(Inches(0.8), Inches(0.4), Inches(11.7), Inches(0.8))
            tf_h = header_box.text_frame
            p_h = tf_h.paragraphs[0]
            page_suffix = f" (Part {page_num} of {total_pages})" if total_pages > 1 else ""
            p_h.text = f"{request.title}{page_suffix}"
            p_h.font.name = "Calibri"
            p_h.font.size = PptPt(20)
            p_h.font.bold = True
            p_h.font.color.rgb = RGBColor(15, 23, 42)

            # Table
            num_rows = len(chunk) + 1
            num_cols = len(columns)
            table_shape = slide.shapes.add_table(
                num_rows, num_cols,
                Inches(0.8), Inches(1.3), Inches(11.7), Inches(5.4)
            )
            table = table_shape.table

            # Format headers
            for c_idx, col in enumerate(columns):
                cell = table.cell(0, c_idx)
                cell.fill.solid()
                cell.fill.fore_color.rgb = RGBColor(30, 41, 59)  # Slate 800
                cell.text = str(col).title().replace("_", " ")
                p = cell.text_frame.paragraphs[0]
                p.alignment = PP_ALIGN.LEFT
                for r in p.runs:
                    r.font.name = "Calibri"
                    r.font.bold = True
                    r.font.size = PptPt(10)
                    r.font.color.rgb = RGBColor(255, 255, 255)

            # Format data rows
            for r_idx, row_vals in enumerate(chunk, start=1):
                bg_col = RGBColor(248, 250, 252) if r_idx % 2 == 0 else RGBColor(255, 255, 255)
                for c_idx, val in enumerate(row_vals):
                    cell = table.cell(r_idx, c_idx)
                    cell.fill.solid()
                    cell.fill.fore_color.rgb = bg_col
                    disp_str = str(val)
                    cell.text = disp_str
                    p = cell.text_frame.paragraphs[0]
                    p.alignment = PP_ALIGN.RIGHT if (disp_str.startswith("$") or "INR" in disp_str) else PP_ALIGN.LEFT
                    for r in p.runs:
                        r.font.name = "Calibri"
                        r.font.size = PptPt(9.5)
                        r.font.color.rgb = RGBColor(30, 41, 59)

        # ── Final Slide: Governance & Lineage ──
        lineage_slide = prs.slides.add_slide(blank_slide_layout)
        lh_box = lineage_slide.shapes.add_textbox(Inches(0.8), Inches(0.6), Inches(11.7), Inches(0.8))
        lh_p = lh_box.text_frame.paragraphs[0]
        lh_p.text = "Governance, Security & Source Lineage"
        lh_p.font.name = "Calibri"
        lh_p.font.size = PptPt(22)
        lh_p.font.bold = True
        lh_p.font.color.rgb = RGBColor(15, 23, 42)

        content_box = lineage_slide.shapes.add_textbox(Inches(0.8), Inches(1.6), Inches(11.7), Inches(5.0))
        tf_l = content_box.text_frame
        tf_l.word_wrap = True

        p_info = tf_l.paragraphs[0]
        p_info.text = f"This official document was compiled from verified enterprise records under strict Zero-Trust RBAC security."
        p_info.font.name = "Calibri"
        p_info.font.size = PptPt(12)
        p_info.font.color.rgb = RGBColor(71, 85, 105)

        for lin in request.lineage:
            p_lin = tf_l.add_paragraph()
            p_lin.text = f"• {lin.source_type.upper()}: {lin.source_label}  |  Columns: {', '.join(lin.columns)}"
            p_lin.font.name = "Calibri"
            p_lin.font.size = PptPt(11)
            p_lin.font.bold = True
            p_lin.font.color.rgb = RGBColor(30, 41, 59)
            p_lin.space_before = PptPt(8)

        prs.save(destination)
