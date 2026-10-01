"""Document extraction and structured record extraction routines."""
from __future__ import annotations

import logging
import re
from typing import Any, Callable

from backend.documents.parsers import CSVParser, ExcelParser, PDFParser, TextParser, WordParser
from backend.documents.service import DocumentProcessingService
from backend.security.authorization import UserAttributes
from backend.sources.models import SourceReference, SourceType

logger = logging.getLogger(__name__)


def create_default_document_service() -> DocumentProcessingService:
    """Instantiate the standard multi-format document processing engine."""
    return DocumentProcessingService([
        PDFParser(),
        WordParser(),
        ExcelParser(),
        CSVParser(),
        TextParser(),
    ])


def extract_invoice_records_from_files(
    indexed_files: dict[str, dict[str, Any]],
    is_folder_authorized: Callable[[UserAttributes, str], bool],
    user: UserAttributes,
    status_filter: str | None = None,
    entity_filter: str | None = None,
    limit: int = 50,
) -> tuple[list[dict[str, Any]], list[SourceReference]]:
    """Extract structured invoice records from real company finance documents."""
    records: list[dict[str, Any]] = []
    sources: list[SourceReference] = []
    seen_ids: set[str] = set()
    seen_refs: set[str] = set()

    for rel_path, info in indexed_files.items():
        folder = info.get("folder", "General")
        if not is_folder_authorized(user, folder):
            continue
        filename = info["filename"]
        content = info.get("content", "")
        if (
            "invoice" not in filename.lower()
            and "invoice" not in content.lower()
            and "payment" not in filename.lower()
            and "billing" not in filename.lower()
        ):
            continue

        # 1. Check for tabular rows (e.g. CSV or spreadsheet schedules with pipe |)
        table_lines = [l.strip() for l in content.split("\n") if "|" in l]
        if len(table_lines) >= 2:
            header_line = table_lines[0].casefold()
            if "invoice" in header_line or "vendor" in header_line or "amount" in header_line:
                raw_headers = [h.strip().casefold() for h in table_lines[0].split("|")]
                for line in table_lines[1:]:
                    parts = [p.strip() for p in line.split("|")]
                    if len(parts) != len(raw_headers):
                        continue
                    row_dict = dict(zip(raw_headers, parts))
                    inv_id = None
                    amount = None
                    status = "Pending"
                    due_date = ""
                    comp_name = ""
                    vendor = ""
                    for h, val in row_dict.items():
                        if "invoice id" in h or h == "inv" or (not inv_id and val.upper().startswith("INV-")):
                            inv_id = val
                        elif any(k in h for k in ("amount", "total", "cost", "price")):
                            amount = val
                        elif "status" in h:
                            status = val
                        elif any(k in h for k in ("due", "date")):
                            if not due_date or "due" in h:
                                due_date = val
                        elif any(k in h for k in ("customer", "client", "account")):
                            comp_name = val
                        elif "vendor" in h:
                            vendor = val

                    if inv_id and amount:
                        if inv_id in seen_ids:
                            continue
                        if status_filter and status_filter.casefold() not in status.casefold():
                            continue
                        if entity_filter:
                            ef = entity_filter.casefold()
                            if ef not in comp_name.casefold() and ef not in vendor.casefold() and ef not in inv_id.casefold():
                                continue
                        seen_ids.add(inv_id)
                        display_comp = comp_name or vendor or "Enterprise Client"
                        records.append({
                            "id": inv_id,
                            "customer": display_comp,
                            "vendor": vendor,
                            "amount": amount,
                            "status": status,
                            "due_date": due_date,
                            "file_path": rel_path,
                        })
                        if rel_path not in seen_refs:
                            seen_refs.add(rel_path)
                            sources.append(SourceReference(
                                reference_id=f"ref-inv-{inv_id}",
                                source_type=SourceType.FILE,
                                display_name=f"[Finance] {filename}",
                                title=f"{filename} - {inv_id}",
                                location=info.get("full_path") or info.get("file_path", ""),
                            ))
                        if len(records) >= limit:
                            break

        if len(records) >= limit:
            break

        # 2. Key-value formatted documents (PDF, DOCX, TXT)
        inv_id_m = re.search(r"(?:Invoice\s*(?:ID|#|No|Number)?|INV)\s*[:\n\-]\s*([A-Za-z0-9-]+)", content, re.IGNORECASE)
        total_m = re.search(r"(?:Total\s*Amount|Amount\s*Due|Grand\s*Total|Total|Amount|Balance)\s*[:\n\-]\s*([^\n|]+)", content, re.IGNORECASE)
        if not inv_id_m or not total_m:
            continue

        inv_id = inv_id_m.group(1).strip()
        if inv_id in seen_ids:
            continue

        vendor_m = re.search(r"(?:Vendor\s*(?:Name)?|Provider|From|Billed\s*By)\s*[:\n\-]\s*([^\n|]+)", content, re.IGNORECASE)
        customer_m = re.search(r"(?:Customer\s*(?:Name)?|Client|Bill\s*To|Billed\s*To|Company)\s*[:\n\-]\s*([^\n|]+)", content, re.IGNORECASE)
        status_m = re.search(r"(?:Payment\s*Status|Status)\s*[:\n\-]\s*([^\n|]+)", content, re.IGNORECASE)
        date_m = re.search(r"(?:Due\s*Date|Invoice\s*Date|Date)\s*[:\n\-]\s*([^\n|]+)", content, re.IGNORECASE)

        vendor = vendor_m.group(1).strip() if vendor_m else ""
        customer = customer_m.group(1).strip() if customer_m else ""
        status = status_m.group(1).strip() if status_m else ("Overdue" if "overdue" in content.lower() else "Pending")
        date_str = date_m.group(1).strip() if date_m else ""
        total_raw = total_m.group(1).strip()

        if status_filter and status_filter.casefold() not in status.casefold():
            continue

        if entity_filter:
            ef = entity_filter.casefold()
            if ef not in customer.casefold() and ef not in vendor.casefold() and ef not in inv_id.casefold():
                continue

        seen_ids.add(inv_id)
        comp_name = customer if customer and customer != "Synthetic" else (vendor or "Enterprise Client")

        records.append({
            "id": inv_id,
            "customer": comp_name,
            "vendor": vendor,
            "amount": total_raw,
            "status": status,
            "due_date": date_str,
            "file_path": rel_path,
        })

        if rel_path not in seen_refs:
            seen_refs.add(rel_path)
            sources.append(SourceReference(
                reference_id=f"ref-inv-{inv_id}",
                source_type=SourceType.FILE,
                display_name=f"[Finance] {filename}",
                title=f"{filename} - {inv_id}",
                location=info.get("full_path") or info.get("file_path", ""),
            ))

        if len(records) >= limit:
            break

    if not status_filter:
        records.sort(key=lambda r: 0 if "overdue" in r["status"].lower() else 1)

    return records, sources


def extract_contract_records_from_files(
    indexed_files: dict[str, dict[str, Any]],
    is_folder_authorized: Callable[[UserAttributes, str], bool],
    user: UserAttributes,
    entity_filter: str | None = None,
    limit: int = 50,
) -> tuple[list[dict[str, Any]], list[SourceReference]]:
    """Extract structured contract renewal and agreement records."""
    records: list[dict[str, Any]] = []
    sources: list[SourceReference] = []
    seen_ids: set[str] = set()

    for rel_path, info in indexed_files.items():
        folder = info.get("folder", "General")
        if not is_folder_authorized(user, folder):
            continue
        filename = info["filename"]
        content = info.get("content", "")

        if "renewal" in filename.lower() or "schedule" in filename.lower() or "register" in filename.lower():
            lines = [l.strip() for l in content.split("\n") if "|" in l]
            for line in lines:
                parts = [p.strip() for p in line.split("|")]
                if len(parts) >= 5 and parts[0].upper().startswith(("CNT-", "CTR-")):
                    cid = parts[0]
                    if cid in seen_ids:
                        continue
                    if entity_filter:
                        ef = entity_filter.casefold()
                        if not any(ef in p.casefold() for p in parts[:4]):
                            continue
                    seen_ids.add(cid)
                    records.append({
                        "id": cid,
                        "customer": parts[1] if len(parts) > 1 else "",
                        "contract_type": parts[2] if len(parts) > 2 else "Standard Agreement",
                        "annual_value": parts[3] if len(parts) > 3 else "N/A",
                        "renewal_date": parts[4] if len(parts) > 4 else "",
                        "status": parts[6] if len(parts) > 6 else "Active",
                        "file_path": rel_path,
                    })

            if records:
                sources.append(SourceReference(
                    reference_id=f"ref-contract-{filename.split('.')[0]}",
                    source_type=SourceType.FILE,
                    display_name=f"[Contracts] {filename}",
                    title=f"{filename}",
                    location=info.get("full_path") or info.get("file_path", ""),
                ))
                break

    return records[:limit], sources
