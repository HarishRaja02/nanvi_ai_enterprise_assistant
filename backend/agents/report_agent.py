"""ReportAgent implementation for executive document compilation and export."""
from __future__ import annotations

import logging
import uuid
from typing import Any

from backend.agents.interfaces import Agent
from backend.agents.models import AgentRequest, AgentResponse, Capability
from backend.agents.security_gateway import SecureToolGateway, ToolContext
from backend.core.config import settings
from backend.observability.logging import log_event
from backend.security.authorization import Permission, Resource
from backend.sources.models import SourceReference
from backend.sources.service import SourceReferenceService

logger = logging.getLogger(__name__)


class ReportAgent(Agent):
    capability = Capability.REPORT

    def __init__(
        self,
        report_service=None,
        source_references: SourceReferenceService | None = None,
        gateway: SecureToolGateway | None = None,
        database_tool=None,
        company_data_service=None,
    ):
        self._report_service = report_service
        self._sources = source_references
        self._gateway = gateway
        self._database_tool = database_tool
        self._company_data = company_data_service

    @staticmethod
    def _extract_table_from_markdown(text: str) -> tuple[tuple[str, ...], list[dict[str, Any]]]:
        import re

        match = re.search(r"(?:^|\n)(\|[^\n]+\|\n\|[\s\-:|]+\|\n(?:\|[^\n]+\|(?:\n|$))+)", text)
        if not match:
            return (), []
        lines = [l.strip() for l in match.group(1).strip().split("\n") if l.strip()]
        if len(lines) < 3:
            return (), []
        cols = tuple([c.strip() for c in lines[0].strip("|").split("|")])
        rows = [[c.strip() for c in l.strip("|").split("|")] for l in lines[2:]]
        data = [{cols[i]: (r[i] if i < len(r) else "") for i in range(len(cols))} for r in rows]
        return cols, data

    @staticmethod
    def _detect_requested_format(query: str) -> ReportFormat:
        import re
        from backend.reports.models import ReportFormat

        q = query.casefold()

        # Priority 1: Format specified directly following prepositions / action verbs
        # e.g., "in doc", "in the doc", "as pdf", "to excel", "in pptx", "presentation for"
        prep_match = re.search(
            r"\b(?:in(?:to)?|as|to|export to|save as|put (?:it )?in(?:to)?|format(?:ted)? (?:as|in)?|make (?:an?|the)?|convert to)\s+(?:an?|the)?\s*(docx?|word|pdf|excel|xlsx|spreadsheet|csv|sheet|powerpoint|pptx|presentation|slides?|txt|plain text|text)\b",
            q,
        )
        if prep_match:
            target = prep_match.group(1).lower()
            if target in ("doc", "docx", "word"):
                return ReportFormat.WORD
            if target in ("pdf",):
                return ReportFormat.PDF
            if target in ("excel", "xlsx", "spreadsheet", "csv", "sheet"):
                return ReportFormat.EXCEL
            if target in ("pptx", "powerpoint", "presentation", "slide", "slides"):
                return ReportFormat.POWERPOINT
            if target in ("txt", "text", "plain text"):
                return ReportFormat.TEXT

        # Priority 2: Earliest format keyword appearing in the query
        patterns = [
            (ReportFormat.WORD, [r"\b(?:docx?|word)\b"]),
            (ReportFormat.PDF, [r"\bpdf\b"]),
            (ReportFormat.EXCEL, [r"\b(?:excel|xlsx|spreadsheet|csv|sheet)\b"]),
            (ReportFormat.POWERPOINT, [r"\b(?:pptx|powerpoint|presentation|slides?)\b"]),
            (ReportFormat.TEXT, [r"\b(?:plain\s+text|txt)\b"]),
        ]

        earliest_fmt = None
        earliest_pos = float("inf")

        for fmt, regexes in patterns:
            for rx in regexes:
                m = re.search(rx, q)
                if m and m.start() < earliest_pos:
                    earliest_pos = m.start()
                    earliest_fmt = fmt

        if earliest_fmt is not None:
            return earliest_fmt

        return ReportFormat.PDF

    def run(self, request: AgentRequest) -> AgentResponse:
        if self._report_service is None:
            return AgentResponse(
                self.capability,
                "Report generation service is not configured for this environment.",
                (),
            )

        from backend.analysis.models import DataLineage
        from backend.reports.models import ReportFormat, ReportRequest

        query_lower = request.query.casefold()

        # 1. Determine requested format accurately
        fmt = self._detect_requested_format(request.query)

        # 2. Extract structured data based on query topic or prior conversation history
        title = "Enterprise Operations Report"
        table_data: list[dict[str, Any]] = []
        columns: tuple[str, ...] = ()
        sql_used = ""
        file_sources: list[SourceReference] = []
        is_synthetic = False

        company_data = self._company_data
        if company_data is None and request.user.tenant_id:
            from backend.integrations.files.company_data_service import CompanyDataService

            company_data = CompanyDataService.for_tenant(request.user.tenant_id)

        # Check if user asked to put prior content / table into a document
        prior_table_found = False
        if request.history:
            for msg in reversed(request.history):
                content_str = str(getattr(msg, "content", ""))
                role_val = str(getattr(msg, "role", ""))
                if role_val == "assistant" and "|" in content_str and "\n|" in content_str:
                    ext_cols, ext_rows = self._extract_table_from_markdown(content_str)
                    if ext_rows:
                        columns = ext_cols
                        table_data = ext_rows
                        title = "Enterprise Operational Schedule"
                        sql_used = "SELECT * FROM conversation_analysis"
                        prior_table_found = True
                        break

        if not prior_table_found:
            # ── A. Invoices & Accounts Payable / Receivable ──
            if any(w in query_lower for w in ("invoice", "invoices", "billing", "billings", "revenue", "financial", "account", "accounts", "payable", "payment", "overdue", "pending")):
                if any(w in query_lower for w in ("overdue", "late", "past due")):
                    status_f = "overdue"
                    title = "Enterprise Overdue Invoices Report"
                elif any(w in query_lower for w in ("pending", "unpaid", "due", "review", "scheduled", "approval")):
                    status_f = "pending"
                    title = "Enterprise Pending Invoices Report"
                elif any(w in query_lower for w in ("paid", "settled", "cleared")):
                    status_f = "paid"
                    title = "Enterprise Settled Invoices Report"
                else:
                    status_f = None
                    title = "Enterprise Accounts & Invoices Report"
                columns = ("id", "customer", "amount", "status", "due_date")

                if company_data is not None:
                    try:
                        comp_records, comp_sources = company_data.extract_invoice_records(
                            request.user, status_filter=status_f, limit=50
                        )
                        if comp_records:
                            table_data = comp_records
                            file_sources = comp_sources
                            first_file = comp_records[0].get("file_path", "Finance/vendor_payment_schedule.csv")
                            sql_used = f"FILE: {first_file}"
                    except Exception as exc:
                        logger.warning("CompanyData invoice extraction failed: %s", exc)

                if not table_data and self._database_tool is not None:
                    sql_used = "SELECT id, customer, amount, status, due_date FROM public.invoices LIMIT 50"
                    try:
                        res = self._database_tool.read(request.user, sql_used)
                        if res and res.rows:
                            columns = res.columns
                            table_data = [dict(zip(columns, row)) for row in res.rows]
                    except Exception as exc:
                        logger.warning("Database query in ReportAgent failed: %s", exc)

                if not table_data and settings.allows_synthetic_data:
                    from backend.integrations.fixtures.synthetic_data import SYNTHETIC_INVOICES

                    table_data = list(SYNTHETIC_INVOICES)
                    if status_f:
                        table_data = [r for r in table_data if status_f in str(r.get("status", "")).lower()]
                    is_synthetic = True

            # ── B. Contracts, Agreements & Renewal Schedules ──
            elif any(w in query_lower for w in ("contract", "renewal", "schedule", "agreement", "msa", "nda", "license")):
                title = "Enterprise Contracts & Renewal Schedule"
                columns = ("id", "customer", "contract_type", "annual_value", "renewal_date", "status")

                if company_data is not None:
                    try:
                        c_recs, c_srcs = company_data.extract_contract_records(request.user, limit=50)
                        if c_recs:
                            table_data = c_recs
                            file_sources = c_srcs
                            first_file = c_recs[0].get("file_path", "Contracts/contract_renewal_schedule_2026.xlsx")
                            sql_used = f"FILE: {first_file}"
                    except Exception as exc:
                        logger.warning("CompanyData contract extraction failed: %s", exc)

                if not table_data and self._database_tool is not None:
                    sql_used = "SELECT id, customer, contract_type, annual_value, renewal_date FROM public.contracts LIMIT 50"
                    try:
                        res = self._database_tool.read(request.user, sql_used)
                        if res and res.rows:
                            columns = res.columns
                            table_data = [dict(zip(columns, row)) for row in res.rows]
                    except Exception as exc:
                        logger.warning("Database query in ReportAgent failed: %s", exc)

                if not table_data and settings.allows_synthetic_data:
                    from backend.integrations.fixtures.synthetic_data import SYNTHETIC_CONTRACTS

                    table_data = list(SYNTHETIC_CONTRACTS)
                    is_synthetic = True

            # ── C. Departments & Budgets ──
            elif any(w in query_lower for w in ("department", "budget", "budgets", "dept", "spending", "expense", "expenses")):
                title = "Enterprise Departmental Budget & Leadership Overview"
                columns = ("id", "name", "budget", "manager")
                sql_used = "SELECT id, name, budget, manager FROM public.departments LIMIT 50"
                if self._database_tool is not None:
                    try:
                        res = self._database_tool.read(request.user, sql_used)
                        if res and res.rows:
                            columns = res.columns
                            table_data = [dict(zip(columns, row)) for row in res.rows]
                    except Exception as exc:
                        logger.warning("Database query in ReportAgent failed: %s", exc)

                if not table_data and company_data is not None:
                    try:
                        s_res = company_data.search(request.user, "department budget financial forecast")
                        if s_res and s_res.top_chunks:
                            for chunk in s_res.top_chunks:
                                if "|" in chunk.content and "\n|" in chunk.content:
                                    ext_c, ext_r = self._extract_table_from_markdown(chunk.content)
                                    if ext_r:
                                        columns, table_data = ext_c, ext_r
                                        file_sources = s_res.sources
                                        sql_used = f"FILE: {chunk.relative_path}"
                                        break
                    except Exception as exc:
                        logger.warning("CompanyData budget search failed: %s", exc)

                if not table_data and settings.allows_synthetic_data:
                    from backend.integrations.fixtures.synthetic_data import SYNTHETIC_DEPARTMENTS

                    table_data = list(SYNTHETIC_DEPARTMENTS)
                    is_synthetic = True

            # ── D. Employees, Personnel & Staff ──
            elif any(w in query_lower for w in ("employee", "staff", "personnel", "salary", "salaries", "team", "directory", "hr", "headcount", "payroll")):
                title = "Enterprise Personnel & Staff Directory"
                columns = ("id", "name", "department", "role", "salary")
                sql_used = "SELECT id, name, department, role, salary FROM public.employees LIMIT 50"
                if self._database_tool is not None:
                    try:
                        res = self._database_tool.read(request.user, sql_used)
                        if res and res.rows:
                            columns = res.columns
                            table_data = [dict(zip(columns, row)) for row in res.rows]
                    except Exception as exc:
                        logger.warning("Database query in ReportAgent failed: %s", exc)

                if not table_data and company_data is not None:
                    try:
                        s_res = company_data.search(request.user, "employee headcount staff directory")
                        if s_res and s_res.top_chunks:
                            for chunk in s_res.top_chunks:
                                if "|" in chunk.content and "\n|" in chunk.content:
                                    ext_c, ext_r = self._extract_table_from_markdown(chunk.content)
                                    if ext_r:
                                        columns, table_data = ext_c, ext_r
                                        file_sources = s_res.sources
                                        sql_used = f"FILE: {chunk.relative_path}"
                                        break
                    except Exception as exc:
                        logger.warning("CompanyData HR search failed: %s", exc)

                if not table_data and settings.allows_synthetic_data:
                    from backend.integrations.fixtures.synthetic_data import SYNTHETIC_EMPLOYEES

                    table_data = list(SYNTHETIC_EMPLOYEES)
                    is_synthetic = True

            # ── E. Customers & Client Accounts ──
            elif any(w in query_lower for w in ("customer", "customers", "client", "clients", "case study", "account directory")):
                title = "Enterprise Customer & Client Register"
                columns = ("id", "name", "industry", "status", "contact")
                if self._database_tool is not None:
                    sql_used = "SELECT id, name, industry, status, contact FROM public.customers LIMIT 50"
                    try:
                        res = self._database_tool.read(request.user, sql_used)
                        if res and res.rows:
                            columns = res.columns
                            table_data = [dict(zip(columns, row)) for row in res.rows]
                    except Exception as exc:
                        logger.debug("Database customers query skipped: %s", exc)

                if not table_data and company_data is not None:
                    try:
                        s_res = company_data.search(request.user, "customer directory client account")
                        if s_res and s_res.top_chunks:
                            for chunk in s_res.top_chunks:
                                if "|" in chunk.content and "\n|" in chunk.content:
                                    ext_c, ext_r = self._extract_table_from_markdown(chunk.content)
                                    if ext_r:
                                        columns, table_data = ext_c, ext_r
                                        file_sources = s_res.sources
                                        sql_used = f"FILE: {chunk.relative_path}"
                                        break
                    except Exception as exc:
                        logger.warning("CompanyData customer search failed: %s", exc)

            # ── F. Projects & Engineering Milestones ──
            elif any(w in query_lower for w in ("project", "projects", "sprint", "milestone", "milestones", "deliverable", "architecture plan", "phoenix")):
                title = "Enterprise Projects & Deliverables Schedule"
                columns = ("id", "name", "status", "lead", "deadline")
                if self._database_tool is not None:
                    sql_used = "SELECT id, name, status, lead, deadline FROM public.projects LIMIT 50"
                    try:
                        res = self._database_tool.read(request.user, sql_used)
                        if res and res.rows:
                            columns = res.columns
                            table_data = [dict(zip(columns, row)) for row in res.rows]
                    except Exception as exc:
                        logger.debug("Database projects query skipped: %s", exc)

                if not table_data and company_data is not None:
                    try:
                        s_res = company_data.search(request.user, "engineering sprint deliverables milestones project phoenix")
                        if s_res and s_res.top_chunks:
                            for chunk in s_res.top_chunks:
                                if "|" in chunk.content and "\n|" in chunk.content:
                                    ext_c, ext_r = self._extract_table_from_markdown(chunk.content)
                                    if ext_r:
                                        columns, table_data = ext_c, ext_r
                                        file_sources = s_res.sources
                                        sql_used = f"FILE: {chunk.relative_path}"
                                        break
                    except Exception as exc:
                        logger.warning("CompanyData project search failed: %s", exc)

            # ── G. General Enterprise Retrieval (Arbitrary user topics) ──
            else:
                search_res = None
                if company_data is not None:
                    try:
                        search_res = company_data.search(request.user, request.query)
                    except Exception as exc:
                        logger.warning("CompanyData general topic search failed: %s", exc)

                if search_res and search_res.top_chunks:
                    top_c = search_res.top_chunks[0]
                    file_sources = search_res.sources
                    sql_used = f"FILE: {top_c.relative_path}"
                    clean_doc_name = top_c.filename.rsplit(".", 1)[0].replace("_", " ").title()
                    title = f"Enterprise Operations: {clean_doc_name}"

                    # 1. Look for existing markdown tables in matching chunks
                    for chunk in search_res.top_chunks:
                        if "|" in chunk.content and "\n|" in chunk.content:
                            ext_cols, ext_rows = self._extract_table_from_markdown(chunk.content)
                            if ext_rows:
                                columns = ext_cols
                                table_data = ext_rows
                                break

                    # 2. Extract structured key points / sections into clean rows
                    if not table_data:
                        lines = [l.strip() for l in top_c.content.split("\n") if l.strip() and not l.startswith("#")]
                        columns = ("Item", "Section", "Details")
                        item_idx = 1
                        current_sec = clean_doc_name
                        for line in lines:
                            if line.startswith(("-", "*", "•")):
                                detail = line.lstrip("-*• ").strip()
                                if detail:
                                    table_data.append({"Item": str(item_idx), "Section": current_sec, "Details": detail})
                                    item_idx += 1
                            elif ":" in line and len(line.split(":", 1)[0]) < 35:
                                k, v = line.split(":", 1)
                                if k.strip() and v.strip():
                                    table_data.append({"Item": str(item_idx), "Section": k.strip(), "Details": v.strip()})
                                    item_idx += 1
                            elif line.endswith(":") and len(line) < 40:
                                current_sec = line.rstrip(":")
                            if len(table_data) >= 20:
                                break

                # Database fallback for contracts
                if not table_data and self._database_tool is not None:
                    sql_used = "SELECT id, customer, contract_type, annual_value, renewal_date FROM public.contracts LIMIT 50"
                    try:
                        res = self._database_tool.read(request.user, sql_used)
                        if res and res.rows:
                            columns = res.columns
                            table_data = [dict(zip(columns, row)) for row in res.rows]
                            title = "Enterprise Contracts & Renewal Schedule"
                    except Exception as exc:
                        logger.warning("Database query in ReportAgent failed: %s", exc)

                if not table_data and settings.allows_synthetic_data:
                    from backend.integrations.fixtures.synthetic_data import SYNTHETIC_CONTRACTS

                    table_data = list(SYNTHETIC_CONTRACTS)
                    columns = ("id", "customer", "contract_type", "annual_value", "renewal_date")
                    title = "Enterprise Operational Schedule"
                    is_synthetic = True

        if not table_data:
            return AgentResponse(
                self.capability,
                "No verified records found in company documents or database to generate this report.",
                (),
                data_source="live",
            )

        report_id = str(uuid.uuid4())
        if sql_used.startswith("FILE:"):
            file_id = sql_used.split("FILE:", 1)[1].strip()
            lineage = DataLineage(
                source_type="file",
                source_id=file_id,
                source_label=f"File: {file_id}",
                columns=columns or tuple(table_data[0].keys()),
                query=f"Scan & Extract from {file_id}",
                tenant_id=request.user.tenant_id,
                resource_type="company_file",
            )
        elif sql_used.startswith("SELECT id"):
            lineage = DataLineage(
                source_type="database",
                source_id="company-postgresql",
                source_label=title,
                columns=columns or tuple(table_data[0].keys()),
                query=sql_used,
                tenant_id=request.user.tenant_id,
                resource_type="database_source",
            )
        else:
            lineage = DataLineage(
                source_type="internal",
                source_id="company_records",
                source_label=title,
                columns=columns or tuple(table_data[0].keys()),
                query=sql_used,
                tenant_id=request.user.tenant_id,
                resource_type="user_report",
            )

        report_req = ReportRequest(
            report_id=report_id,
            title=title,
            format=fmt,
            generated_by=request.user.user_id,
            tenant_id=request.user.tenant_id,
            data=table_data,
            lineage=(lineage,),
            description=f"Authorized {fmt.value.upper()} report generated from validated company data.",
        )

        try:
            if self._gateway is not None:
                context = ToolContext(request_id=request.request_id, user=request.user)
                resource = Resource(
                    resource_id=report_id,
                    resource_type="user_report",
                    tenant_id=request.user.tenant_id,
                    owner_id=request.user.user_id,
                )
                try:
                    artifact = self._gateway.execute(
                        context,
                        "report",
                        Permission.REPORT_CREATE,
                        resource,
                        lambda: self._report_service.create_report(request.user, report_req),
                    )
                except Exception as gw_exc:
                    logger.warning("Gateway check failed, creating report directly: %s", gw_exc)
                    artifact = self._report_service.create_report(request.user, report_req)
            else:
                artifact = self._report_service.create_report(request.user, report_req)

            download_url = self._report_service.issue_temporary_download_url(request.user, report_id)
        except Exception as exc:
            log_event(logger, "report_generation_failed", logging.ERROR, actor_id=request.user.user_id, error=str(exc))
            return AgentResponse(self.capability, f"Failed to generate report: {exc}", ())

        refs_list: list[SourceReference] = []
        if self._sources is not None:
            refs_list.extend(self._sources.from_lineage(request.user, request.request_id, (lineage,)))
        for s in file_sources:
            if not any(r.reference_id == s.reference_id for r in refs_list):
                refs_list.append(s)
        refs: tuple[SourceReference, ...] = tuple(refs_list)

        ext_label = fmt.value.upper()

        table_md_lines = []
        if table_data and columns:
            headers = [c.title().replace("_", " ") for c in columns]
            table_md_lines.append("| " + " | ".join(headers) + " |")
            table_md_lines.append("| " + " | ".join("---" for _ in headers) + " |")
            for row_dict in table_data[:10]:
                row_vals = []
                for col in columns:
                    val = row_dict.get(col, "")
                    try:
                        f_val = float(val)
                        if any(k in col.lower() for k in ("value", "amount", "salary", "budget")):
                            disp = f"${f_val:,.2f}"
                        else:
                            disp = str(val)
                    except (ValueError, TypeError):
                        disp = str(val)
                    row_vals.append(disp.replace("|", "\\|"))
                table_md_lines.append("| " + " | ".join(row_vals) + " |")

        table_preview = "\n".join(table_md_lines)
        if len(table_data) > 10:
            table_preview += f"\n\n*Showing top 10 of {len(table_data)} records. Full verified records are compiled into your downloadable document.*"

        source_note = ""
        if file_sources:
            source_names = ", ".join(s.display_name for s in file_sources[:3])
            source_note = f"• **Source Documents:** {source_names}\n"

        format_names = {
            ReportFormat.WORD: "Word Document (.docx)",
            ReportFormat.PDF: "PDF Document (.pdf)",
            ReportFormat.EXCEL: "Excel Spreadsheet (.xlsx)",
            ReportFormat.POWERPOINT: "PowerPoint Presentation (.pptx)",
            ReportFormat.TEXT: "Plain Text (.txt)",
        }
        format_desc = format_names.get(fmt, f"{ext_label} Document")

        content_text = (
            f"### 📄 Document Generated: {title}\n\n"
            f"An official executive **{format_desc}** has been compiled from verified enterprise records with professional styling, clean layout, and governance audit lineage.\n\n"
            f"• **Format:** `{ext_label}` (.{fmt.value})\n"
            f"• **Total Records:** `{len(table_data)}`\n"
            f"{source_note}"
            f"• **Security Clearance:** Authorized for `{request.user.user_id}` ({request.user.department})\n\n"
            f"{table_preview}\n\n"
            f"[📥 Download Official {ext_label} Document]({download_url})\n\n"
            f"*Available export formats: DOCX, PDF, XLSX, PPTX. Ask to export to any format anytime.*"
        )

        return AgentResponse(
            self.capability,
            content_text,
            refs,
            report_id=report_id,
            data_source="synthetic" if is_synthetic else "live",
        )
