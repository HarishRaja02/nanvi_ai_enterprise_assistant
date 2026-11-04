"""Simplified document file search across selected enterprise sources."""
from __future__ import annotations

import logging
import os
import re
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from backend.integrations.files.company_data.service import CompanyDataService
from backend.security.authorization import UserAttributes
from backend.sources.models import SourceReference, SourceType

logger = logging.getLogger(__name__)


def _get_database_tool():
    """Retrieve the active enterprise DatabaseTool instance."""
    try:
        from backend.api.chat_routes import get_chat_service
        from backend.agents.models import Capability
        svc = get_chat_service()
        if svc and hasattr(svc, "_orchestrator") and svc._orchestrator:
            db_agent = svc._orchestrator.agents.get(Capability.DATABASE)
            if db_agent and getattr(db_agent, "_tool", None):
                return db_agent._tool
    except Exception:
        pass

    try:
        from backend.bootstrap import create_chat_service
        from backend.agents.models import Capability
        svc = create_chat_service()
        db_agent = svc._orchestrator.agents.get(Capability.DATABASE)
        return getattr(db_agent, "_tool", None)
    except Exception as exc:
        logger.warning("Could not initialize database tool: %s", exc)
        return None


def _classify_query(query: str) -> tuple[bool, str, list[str], list[str], str]:
    """Determine if query is generic (e.g. 'list invoice file', 'show invoices') or specific.

    Returns:
        (is_generic, category, primary_tokens, expanded_tokens, specific_phrase)
    """
    q_low = query.strip().casefold()
    q_clean = re.sub(r"[^\w\s-]", " ", q_low)
    tokens = [w for w in q_clean.split() if w]

    noise_words = {
        "list", "show", "find", "get", "give", "all", "the", "file", "files",
        "document", "documents", "recently", "recent", "latest", "added", "new",
        "last", "any", "fetch", "check", "see", "me", "you", "can", "please",
        "what", "which", "how", "many", "our", "company", "in", "from", "for",
        "storage", "database", "email", "drive", "cloud", "where", "is", "are",
        "tell", "need", "want", "there", "do", "we", "have", "by", "with",
        "inside", "every", "search", "searching", "look", "looking", "open",
        "button", "path", "format", "formate", "table", "client", "clients",
        "customer", "customers", "vendor", "vendors", "name", "names", "id",
        "ids", "code", "no", "number", "numbers", "specifi", "specify", "specified",
        "specific", "data", "info", "information", "detail", "details", "about",
        "called", "named", "to", "of", "and", "or", "a", "an", "as", "at", "it",
        "this", "that", "these", "those", "related", "realted", "associated",
        "regarding", "pertaining", "concerning", "linked"
    }

    # Category classification
    category = "general"
    if any(w in q_low for w in ("invoice", "invoices", "bill", "bills", "billing")) or re.search(r"\binv[-_ ]?\d+", q_low) or q_low.startswith("inv-"):
        category = "invoice"
    elif any(w in q_low for w in ("contract", "contracts", "agreement", "agreements", "nda", "ndas", "renewal")) or re.search(r"\b(?:cnt|ctr|emp|nda|pur)[-_ ]?\d+", q_low):
        category = "contract"
    elif any(w in q_low for w in ("receipt", "receipts", "ticket", "tickets")):
        category = "receipt"
    elif any(w in q_low for w in ("policy", "policies", "handbook", "guide")):
        category = "policy"
    elif any(w in q_low for w in ("resume", "resumes", "cv", "candidate", "candidates")):
        category = "resume"

    category_terms = {
        "invoice", "invoices", "inv", "bill", "bills", "billing", "contract", "contracts",
        "agreement", "agreements", "nda", "ndas", "emp", "pur", "document", "documents", "file",
        "files", "receipt", "receipts", "policy", "policies", "handbook", "resume", "resumes"
    }

    # Check for specific entity / client / ID / status
    has_status = any(w in q_low for w in ("overdue", "unpaid", "pending", "paid", "expired", "draft", "active"))
    has_id = bool(re.search(r"\b(?:cust|inv|cnt|ctr|po|proj|task)?[-_]?\d{1,6}\b", q_low))
    primary_tokens = [w for w in tokens if w not in noise_words and w not in category_terms]

    # Specific phrase for multi-word entity (e.g. "Acme Corp", "Globex Global", "Initech Solutions")
    specific_phrase = " ".join(primary_tokens) if len(primary_tokens) > 1 else ""

    # Expand tokens with numeric IDs and code prefixes (e.g. INV-2026-003 -> 003, invoice_003)
    expanded_tokens = list(primary_tokens)
    id_nums = re.findall(r"\d+", q_low)
    for num in id_nums:
        num_int = int(num)
        expanded_tokens.append(f"{num_int:03d}")
        expanded_tokens.append(f"{num_int}")
        expanded_tokens.append(f"invoice_{num_int:03d}")
        expanded_tokens.append(f"cust-{num_int:03d}")
        expanded_tokens.append(f"cnt-{num_int:03d}")

    expanded_tokens = list(dict.fromkeys(expanded_tokens))
    is_generic = not (has_status or has_id or bool(primary_tokens))
    return is_generic, category, primary_tokens, expanded_tokens, specific_phrase


def _to_clean_display_path(file_path: Path, repo_root: Path) -> str:
    """Format path relative to data root or project directory for portable display."""
    try:
        if file_path.is_relative_to(repo_root):
            return str(file_path.relative_to(repo_root)).replace("\\", "/")
    except Exception:
        pass
    # If not relative to repo_root, clean any absolute drive prefixes
    p_str = str(file_path).replace("\\", "/")
    for marker in ("CompanyData/", "08_Finance/", "01_Company/", "02_Contracts/"):
        idx = p_str.find(marker)
        if idx != -1:
            return p_str[idx:]
    return file_path.name


def _extract_document_date(filename: str, path_str: str, content_str: str) -> str | None:
    """Extract real document date from text, invoice headers, project briefs, or spreadsheets."""
    # 1. Invoice Date: YYYY-MM-DD
    m_inv = re.search(r"Invoice Date\s*(\d{4}-\d{2}-\d{2})", content_str, re.IGNORECASE)
    if m_inv:
        return m_inv.group(1)
    # 2. Target End / Target Date / End: YYYY-MM-DD
    m_end = re.search(r"(?:Target End|Target Date|End):\s*(\d{4}-\d{2}-\d{2})", content_str, re.IGNORECASE)
    if m_end:
        return m_end.group(1)
    # 3. Start: YYYY-MM-DD
    m_start = re.search(r"Start:\s*(\d{4}-\d{2}-\d{2})", content_str, re.IGNORECASE)
    if m_start:
        return m_start.group(1)
    # 4. Standard ISO date
    m_iso = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", content_str)
    if m_iso:
        return m_iso.group(1)
    return None


def _file_matches_doc_type(file_path: Path, doc_type: str | None, content_str: str = "") -> bool:
    """Strictly verify if a file belongs to the requested document category."""
    if not doc_type or doc_type == "general":
        return True

    fn_low = file_path.name.casefold()
    path_low = str(file_path).casefold()

    if doc_type == "invoice":
        is_inv = any(k in fn_low for k in ("invoice", "inv-", "inv_", "bill")) or ("finance" in path_low and "invoice" in path_low)
        # Exclude unrelated files
        if any(bad in fn_low for bad in ("attendance", "employee_data", "customer_data", "project_data", "tasks_", "orders_")):
            return False
        return is_inv or "invoice" in content_str[:300].casefold()

    if doc_type == "project":
        is_proj = any(k in fn_low for k in ("project", "milestone", "roadmap", "status_report", "tasks_")) or ("project" in path_low)
        if any(bad in fn_low for bad in ("customer_profile", "customer_data", "attendance", "invoice")):
            return False
        return is_proj or "project" in content_str[:300].casefold()

    if doc_type == "contract":
        is_ctr = any(k in fn_low for k in ("contract", "agreement", "nda", "renewal", "license", "policy", "handbook", "sop", "guideline", "review", "budget", "forecast")) or ("contract" in path_low) or ("policy" in path_low)
        if any(bad in fn_low for bad in ("attendance", "employee_data", "customer_data")):
            return False
        return is_ctr

    if doc_type == "employee":
        return any(k in fn_low for k in ("employee", "attendance", "salary", "payroll", "hr")) or ("hr" in path_low)

    if doc_type == "customer":
        return any(k in fn_low for k in ("customer", "client", "order")) or ("customer" in path_low)

    return True


def _extract_date_filter(query: str) -> tuple[str | None, int | None, int | None, int | None]:
    """Extract explicit date expression from query without hardcoding any year.

    Returns:
        (display_str, year, month, day) or (None, None, None, None)
    """
    from backend.retrieval.date_parser import parse_query_date
    df = parse_query_date(query)
    if not df or not df.target_date:
        return None, None, None, None
    try:
        dt = datetime.strptime(df.target_date, "%Y-%m-%d").date()
        return df.display_label, dt.year, dt.month, dt.day
    except ValueError:
        return None, None, None, None


def _get_all_disk_files(cds: Any) -> tuple[Path | None, list[Path]]:
    """Discover server disk files dynamically from connected CompanyData root or fallback."""
    project_dir = Path(__file__).resolve().parents[2]
    repo_root_cand = Path(cds.root) if str(cds.root) else None
    repo_root = None
    if repo_root_cand and str(repo_root_cand).strip() not in ("", "."):
        try:
            res_cand = repo_root_cand.resolve()
            if res_cand != project_dir and res_cand.exists() and res_cand.is_dir():
                norm_root = str(res_cand).replace("\\", "/").lower()
                if "/var/task" not in norm_root and "var/task" not in norm_root and "pytest" not in norm_root:
                    repo_root = res_cand
        except Exception:
            repo_root = None

    if not repo_root:
        default_data = project_dir / "backend" / "CompanyData"
        if default_data.exists() and default_data.is_dir():
            repo_root = default_data

    all_disk_files: list[Path] = []
    if repo_root:
        for p in repo_root.rglob("*"):
            if not p.is_file():
                continue
            p_name = p.name.casefold()
            if p_name.startswith(".") or p_name.startswith("~$") or p_name.startswith(".~"):
                continue
            if p_name.endswith("_index.json") or p_name in ("companydata_index.json", "desktop.ini", "thumbs.db"):
                continue
            if p.suffix.casefold() in (".tmp", ".temp", ".log", ".bak", ".swp", ".pyc"):
                continue
            all_disk_files.append(p)
    return repo_root, all_disk_files


def execute_file_search(
    user: UserAttributes,
    query: str,
    source: str,
    max_results: int = 10,
) -> tuple[str, list[dict[str, Any]], list[SourceReference]]:
    """Execute targeted file search strictly on the single user-chosen source.

    Returns:
        (markdown_table, files_list, source_references)
    """
    clean_src = source.casefold().strip().replace(" ", "_")
    clean_q = query.strip()
    is_generic, category, primary_tokens, expanded_tokens, specific_phrase = _classify_query(clean_q)

    # Tolerant query understanding and entity resolution
    try:
        from backend.integrations.files.company_data.service import CompanyDataService
        from backend.retrieval.entity_resolver import get_entity_resolver
        from backend.retrieval.tolerant_understanding import understand_query, TolerantQuery

        entity_resolver = get_entity_resolver()
        tq = understand_query(clean_q, entity_resolver=entity_resolver)
    except Exception as exc:
        logger.warning("Entity resolution / tolerant query understanding failed, falling back: %s", exc)
        from backend.retrieval.tolerant_understanding import TolerantQuery
        tq = TolerantQuery(original_query=clean_q)

    if tq.needs_user_clarification and tq.candidate_options:
        # Check if candidate files uniquely resolve the ambiguity against real disk files
        try:
            cds_check = CompanyDataService.for_tenant(getattr(user, "tenant_id", "default"))
            _, disk_files_check = _get_all_disk_files(cds_check)
            if tq.date_filter or tq.doc_type:
                cds_check.ensure_indexed()
                indexed = getattr(cds_check, "_indexed_files", {})
                viable_cands = []
                for cand in tq.candidate_options:
                    c_canon = cand.canonical_name.casefold()
                    c_tokens = [w.casefold() for w in re.findall(r"\w+", cand.canonical_name) if len(w) >= 3]
                    has_match = False
                    for p in disk_files_check:
                        if tq.doc_type and not _file_matches_doc_type(p, tq.doc_type):
                            continue
                        fn_low = p.name.casefold()
                        p_full = str(p).replace("\\", "/").casefold()

                        content = ""
                        for rel_k, info in indexed.items():
                            fpath = str(info.get("file_path", "")).replace("\\", "/").casefold()
                            rel_clean = rel_k.replace("\\", "/").casefold()
                            if fpath == p_full or rel_clean in p_full or p.name.casefold() == info.get("filename", "").casefold():
                                content = info.get("content", "").casefold()
                                break

                        cand_in_file = any(tok in fn_low for tok in c_tokens) or (c_canon in content)
                        if not cand_in_file:
                            continue

                        if tq.date_filter and tq.date_filter.target_date:
                            df = tq.date_filter
                            doc_date = _extract_document_date(p.name, str(p), content)
                            if doc_date:
                                try:
                                    d_doc = datetime.strptime(doc_date, "%Y-%m-%d").date()
                                    d_target = datetime.strptime(df.target_date, "%Y-%m-%d").date()
                                    delta = abs((d_doc - d_target).days)
                                    if delta <= (df.window_days or 7):
                                        has_match = True
                                        break
                                except Exception:
                                    pass
                        else:
                            has_match = True
                            break

                    if has_match:
                        viable_cands.append(cand)

                if len(viable_cands) == 1:
                    tq.resolved_candidate = viable_cands[0]
                    tq.entity = viable_cands[0].canonical_name
                    tq.needs_user_clarification = False
        except Exception:
            pass

    if tq.needs_user_clarification and tq.candidate_options:
        cand_lines = "\n".join(f"- **{c.canonical_name}** ({c.entity_type})" for c in tq.candidate_options)
        clarification_text = (
            f"Your search for **\"{clean_q}\"** matches multiple possible records:\n\n"
            f"{cand_lines}\n\n"
            "Please specify which one you'd like to view."
        )
        return clarification_text, [], []

    if tq.doc_type:
        category = tq.doc_type

    if tq.resolved_candidate:
        cand_tokens = [w.casefold() for w in re.findall(r"\w+", tq.resolved_candidate.canonical_name) if len(w) > 1]
        for ct in cand_tokens:
            if ct not in primary_tokens:
                primary_tokens.append(ct)
            if ct not in expanded_tokens:
                expanded_tokens.append(ct)
        is_generic = False

    specific_tokens = expanded_tokens
    files: list[dict[str, Any]] = []
    sources: list[SourceReference] = []

    SOURCE_LABELS = {
        "local": "Local Storage",
        "local_storage": "Local Storage",
        "database": "Database",
        "db": "Database",
        "email": "Email",
        "mail": "Email",
        "gmail": "Email",
        "inbox": "Email",
        "google_drive": "Google Drive",
        "drive": "Google Drive",
        "gdrive": "Google Drive",
        "cloud": "Cloud Storage",
        "cloud_storage": "Cloud Storage",
    }
    friendly_source = SOURCE_LABELS.get(clean_src, source.replace("_", " ").title())

    # 1. Local Storage
    if clean_src in ("local", "local_storage", "disk", "folder"):
        try:
            # 1A. Query Windows Local File Agent (synced from user's PC)
            u_id = str(getattr(user, "user_id", None) or getattr(user, "subject", None) or "default")
            t_id = str(getattr(user, "tenant_id", None) or "default")

            agent_files: list[dict[str, Any]] = []
            try:
                from backend.local_agent.service import get_local_agent_service
                local_svc = get_local_agent_service()

                if is_generic:
                    all_agent_files = local_svc.get_all_local_files(t_id, u_id)
                    if category == "invoice":
                        agent_files = [
                            f for f in all_agent_files
                            if any(k in f["name"].lower() or k in f["path"].lower() for k in ("invoice", "invoices", "bill", "billing", "aging", "ledger"))
                        ]
                    elif category == "contract":
                        agent_files = [
                            f for f in all_agent_files
                            if any(k in f["name"].lower() or k in f["path"].lower() for k in ("contract", "contracts", "agreement", "nda", "renewal"))
                        ]
                    else:
                        agent_files = all_agent_files
                else:
                    hits = local_svc.search_local_chunks(t_id, u_id, clean_q, top_k=max_results * 2)
                    if not hits and specific_phrase and specific_phrase != clean_q:
                        hits = local_svc.search_local_chunks(t_id, u_id, specific_phrase, top_k=max_results * 2)
                    if not hits and primary_tokens:
                        hits = local_svc.search_local_chunks(t_id, u_id, " ".join(primary_tokens), top_k=max_results * 2)

                    seen_agent_files = set()
                    for h in hits:
                        fn_key = h.filename.lower()
                        if fn_key in seen_agent_files:
                            continue

                        # 1. Hard doc_type check
                        if tq.doc_type and not _file_matches_doc_type(Path(h.filename), tq.doc_type, h.text or ""):
                            continue

                        # 2. Document date check
                        doc_d = _extract_document_date(h.filename, h.relative_path or "", h.text or "")
                        if tq.date_filter:
                            df = tq.date_filter
                            if df.target_field != "modified_at" and doc_d:
                                if df.filter_mode == "exact" and doc_d != df.target_date:
                                    continue
                                elif df.filter_mode == "window" and df.target_date:
                                    try:
                                        d_doc = datetime.strptime(doc_d, "%Y-%m-%d").date()
                                        d_target = datetime.strptime(df.target_date, "%Y-%m-%d").date()
                                        if abs((d_doc - d_target).days) > df.window_days:
                                            continue
                                    except ValueError:
                                        continue
                                elif df.filter_mode == "ending_soon":
                                    try:
                                        d_doc = datetime.strptime(doc_d, "%Y-%m-%d").date()
                                        d_start = datetime.strptime(df.start_date, "%Y-%m-%d").date()
                                        d_end = datetime.strptime(df.end_date, "%Y-%m-%d").date()
                                        if not (d_start <= d_doc <= d_end):
                                            continue
                                    except ValueError:
                                        continue
                            elif df.target_date:
                                continue

                        # 3. Ensure chunk matches primary tokens if primary tokens exist
                        if primary_tokens:
                            text_and_fn = (h.filename + " " + (h.text or "")).lower()
                            if not any(t in text_and_fn for t in primary_tokens):
                                continue

                        seen_agent_files.add(fn_key)

                        disp_path = h.citation or f"{h.folder_name}/{h.relative_path}".strip("/")
                        full_open = ""
                        if h.folder_path and h.relative_path:
                            full_open = f"{h.folder_path}\\{h.relative_path}".replace("/", "\\")
                        elif h.folder_path:
                            full_open = h.folder_path
                        else:
                            full_open = disp_path

                        exact_full_path = full_open if (":" in full_open or full_open.startswith("\\\\")) else (h.folder_path or disp_path)

                        agent_files.append({
                            "name": h.filename,
                            "path": exact_full_path,
                            "full_path": exact_full_path,
                            "display_path": disp_path,
                            "type": Path(h.filename).suffix.lstrip("."),
                            "modified_at": h.modified_at or "",
                            "open_url": exact_full_path,
                            "source": "local",
                            "content_snippet": (h.text or "")[:400],
                        })
            except Exception as agent_exc:
                logger.debug("Local agent search error: %s", agent_exc)

            # 1B. Discover server disk files (only if an explicit valid folder is connected)
            server_disk_files: list[dict[str, Any]] = []
            cds = CompanyDataService.for_tenant(user.tenant_id)
            repo_root, all_disk_files = _get_all_disk_files(cds)

            if is_generic and repo_root:
                # Category filter if requested, e.g. "list invoice file"
                matched_files: list[Path] = []
                for p in all_disk_files:
                    fn_low = p.name.casefold()
                    path_low = str(p).casefold()
                    if category == "invoice":
                        is_inv = any(k in fn_low for k in ("invoice", "invoices", "bill", "billing")) or ("finance" in path_low and any(k in fn_low for k in ("aging", "register", "ledger")))
                        if not is_inv:
                            continue
                    elif category == "contract":
                        is_ctr = any(k in fn_low for k in ("contract", "contracts", "agreement", "nda", "renewal", "schedule"))
                        if not is_ctr:
                            continue
                    matched_files.append(p)

                if not matched_files and category != "general":
                    matched_files = all_disk_files

                # Sort by recently added / modified time descending
                matched_files.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)

                for p in matched_files[:max_results]:
                    disp_path = _to_clean_display_path(p, repo_root)
                    server_disk_files.append({
                        "name": p.name,
                        "path": disp_path,
                        "type": p.suffix.lstrip("."),
                        "modified_at": datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).isoformat(),
                        "open_url": disp_path,
                        "source": "local",
                    })
            else:
                # Specific search by keywords / client name / id:
                # Search inside the content of EVERY file as well as the filename!
                cds.ensure_indexed()
                indexed = getattr(cds, "_indexed_files", {})

                doc_dates: dict[Path, str | None] = {}
                scored: list[tuple[float, Path]] = []
                for p in all_disk_files:
                    fn_low = p.name.casefold()
                    path_low = str(p).casefold()
                    p_full = str(p).replace("\\", "/").casefold()

                    # Hard doc_type check upfront
                    if tq.doc_type and not _file_matches_doc_type(p, tq.doc_type, content_str=""):
                        continue

                    # Retrieve parsed content of file (PDF, Word, Excel, CSV, text)
                    content_str = ""
                    for rel_k, info in indexed.items():
                        fpath = str(info.get("file_path", "")).replace("\\", "/").casefold()
                        rel_clean = rel_k.replace("\\", "/").casefold()
                        if fpath == p_full or rel_clean in p_full or p.name.casefold() == info.get("filename", "").casefold():
                            content_str = info.get("content", "").casefold()
                            if content_str:
                                break

                    if not content_str:
                        ext = p.suffix.casefold()
                        if ext in (".txt", ".csv", ".tsv", ".json", ".jsonl", ".md", ".py", ".html", ".htm", ".log", ".yaml", ".yml", ".ini", ".conf"):
                            try:
                                content_str = p.read_text(encoding="utf-8", errors="ignore")[:50000].casefold()
                            except Exception:
                                pass
                        elif ext in (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".xlsm", ".pptx", ".ppt", ".rtf", ".xml"):
                            try:
                                doc = cds._doc_service.parse_bytes(
                                    filename=p.name,
                                    relative_path=p.name,
                                    data=p.read_bytes(),
                                    modified_at=datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc),
                                )
                                content_str = (doc.text or "").casefold()
                            except Exception:
                                pass

                    # Verify doc_type with parsed content
                    if tq.doc_type and not _file_matches_doc_type(p, tq.doc_type, content_str=content_str):
                        continue

                    doc_date_str = _extract_document_date(p.name, str(p), content_str)
                    doc_dates[p] = doc_date_str

                    score = 0.0

                    # 1. Exact phrase match inside content or filename
                    if specific_phrase and len(primary_tokens) > 1:
                        if specific_phrase in fn_low:
                            score += 400.0
                        if specific_phrase in content_str:
                            score += 350.0

                    # 1.5 Grounded resolved entity match
                    if tq.resolved_candidate:
                        c_canon = tq.resolved_candidate.canonical_name.casefold()
                        if c_canon in fn_low:
                            score += 800.0
                        if c_canon in content_str:
                            score += 600.0
                        res_tokens = [w.casefold() for w in re.findall(r"\w+", c_canon) if len(w) >= 3]
                        for rt in res_tokens:
                            w = entity_resolver.get_token_weight(rt)
                            if w >= 0.5:
                                if rt in fn_low:
                                    score += 300.0 * w
                                if rt in content_str:
                                    score += 200.0 * w

                    # 2. Primary exact client name / ID matches weighted by distinctiveness
                    primary_matches_fn = 0
                    primary_matches_ct = 0
                    for token in primary_tokens:
                        w = entity_resolver.get_token_weight(token)
                        if token in fn_low:
                            primary_matches_fn += 1
                            score += 300.0 * w
                        if token in content_str:
                            primary_matches_ct += 1
                            score += 250.0 * w

                    # 3. Expanded numeric / code variants
                    exp_matches_fn = 0
                    exp_matches_ct = 0
                    for token in expanded_tokens:
                        if token in primary_tokens:
                            continue
                        if token in fn_low:
                            exp_matches_fn += 1
                            score += 50.0
                        if token in content_str:
                            exp_matches_ct += 1
                            score += 30.0

                    # 4. Date filter scoring
                    if tq.date_filter:
                        df = tq.date_filter
                        date_bonus = 0.0
                        if df.target_field == "modified_at":
                            f_dt_str = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).strftime("%Y-%m-%d")
                            if f_dt_str == df.target_date:
                                date_bonus += 400.0
                        elif doc_date_str:
                            if df.filter_mode == "exact":
                                if doc_date_str == df.target_date:
                                    date_bonus += 400.0
                            elif df.filter_mode == "window" and df.target_date:
                                try:
                                    d_doc = datetime.strptime(doc_date_str, "%Y-%m-%d").date()
                                    d_target = datetime.strptime(df.target_date, "%Y-%m-%d").date()
                                    diff = abs((d_doc - d_target).days)
                                    if diff <= df.window_days:
                                        date_bonus += 400.0 - (diff * 15.0)
                                except ValueError:
                                    pass
                            elif df.filter_mode == "ending_soon":
                                try:
                                    d_doc = datetime.strptime(doc_date_str, "%Y-%m-%d").date()
                                    d_start = datetime.strptime(df.start_date, "%Y-%m-%d").date()
                                    d_end = datetime.strptime(df.end_date, "%Y-%m-%d").date()
                                    if d_start <= d_doc <= d_end and "completed" not in content_str:
                                        date_bonus += 400.0
                                except ValueError:
                                    pass

                        if date_bonus > 0.0:
                            score += date_bonus
                        elif df.target_date or df.filter_mode == "ending_soon":
                            # Date explicitly requested, but this file does not match the timeframe!
                            continue

                    total_matches = primary_matches_fn + primary_matches_ct + exp_matches_fn + exp_matches_ct
                    if total_matches == 0 and not tq.date_filter:
                        continue

                    # Bonus for matching all primary tokens
                    if primary_tokens and (primary_matches_fn + primary_matches_ct) >= len(primary_tokens):
                        score += 100.0

                    # Category bonus if category was mentioned (e.g. invoice, contract)
                    if category != "general" and (category in fn_low or category in path_low):
                        score += 30.0

                    if score >= 120.0 or is_generic:
                        scored.append((score, p))

                scored.sort(key=lambda x: (x[0], x[1].stat().st_mtime if x[1].exists() else 0), reverse=True)
                for _, p in scored[:max_results]:
                    disp_path = _to_clean_display_path(p, repo_root)
                    d_val = doc_dates.get(p)
                    server_disk_files.append({
                        "name": p.name,
                        "path": disp_path,
                        "type": p.suffix.lstrip("."),
                        "modified_at": d_val or datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).isoformat(),
                        "open_url": disp_path,
                        "source": "local",
                    })

            # Merge results: Windows Local Agent first, then server disk
            seen_names = set()
            for f in agent_files:
                fn_lower = f["name"].lower()
                if fn_lower not in seen_names:
                    files.append(f)
                    seen_names.add(fn_lower)

            for f in server_disk_files:
                fn_lower = f["name"].lower()
                if fn_lower not in seen_names:
                    files.append(f)
                    seen_names.add(fn_lower)

            if not files:
                try:
                    from backend.local_agent.service import get_local_agent_service
                    l_svc = get_local_agent_service()
                    st = l_svc.get_status(t_id, u_id)
                    if not st.connected_folders and not repo_root:
                        answer = (
                            "**No Local Company Folder Connected**\n\n"
                            "Nanvi AI accesses documents exclusively from the folder you specify in the Windows BAT file agent.\n\n"
                            "👉 **To connect your folder:**\n"
                            "1. Go to **Settings** → **Company Folder** and click **Download Nanvi_Assistant.bat**\n"
                            "2. Double-click the downloaded file on your Windows computer and enter the folder path."
                        )
                        return answer, [], []
                except Exception:
                    pass

            for idx, f in enumerate(files, start=1):
                sources.append(
                    SourceReference(
                        reference_id=f"ref-local-{idx}-{Path(f['name']).stem}",
                        source_type=SourceType.FILE,
                        display_name=f["name"],
                        title=f["name"],
                        location=f["path"],
                    )
                )
        except Exception as exc:
            logger.warning("Local storage search failed: %s", exc)

    # 2. Database
    elif clean_src in ("database", "db"):
        try:
            tool = _get_database_tool()
            cds = CompanyDataService.for_tenant(user.tenant_id)
            repo_root = Path(cds.root)

            if tool is not None:
                # 2a. Invoices Search in Database
                if category == "invoice" or not is_generic or any(w in clean_q.casefold() for w in ("invoice", "bill", "due", "overdue")):
                    q_lower = clean_q.casefold()
                    is_overdue = any(w in q_lower for w in ("overdue", "unpaid", "past due"))
                    try:
                        if is_overdue:
                            res = tool.read(
                                user,
                                "SELECT id, customer, amount, status, due_date FROM public.invoices WHERE LOWER(status) LIKE %s ORDER BY due_date DESC LIMIT 50",
                                ("%overdue%",),
                            )
                        elif not is_generic and specific_tokens:
                            # Search by specific client name or ID across invoices
                            conds = []
                            params = []
                            for t in specific_tokens[:3]:
                                conds.append("(LOWER(customer) LIKE %s OR LOWER(id) LIKE %s)")
                                p = f"%{t}%"
                                params.extend([p, p])
                            where_sql = " OR ".join(conds) if conds else "1=1"
                            res = tool.read(
                                user,
                                f"SELECT id, customer, amount, status, due_date FROM public.invoices WHERE {where_sql} ORDER BY due_date DESC LIMIT 50",
                                tuple(params),
                            )
                        else:
                            # Common generic query: list recently added invoices
                            res = tool.read(
                                user,
                                "SELECT id, customer, amount, status, due_date FROM public.invoices ORDER BY due_date DESC, id DESC LIMIT 50",
                                (),
                            )

                        for row in res.rows:
                            inv_id = str(row[0])
                            cust = str(row[1])
                            stat = str(row[3])
                            due = str(row[4])

                            # Dynamically locate matching PDF on disk anywhere under repo_root without hardcoded paths
                            num_matches = re.findall(r"\d+", inv_id)
                            candidate_file = None
                            if num_matches and repo_root.exists():
                                num_int = int(num_matches[-1])
                                for cand_pattern in (f"invoice_{num_int:03d}.pdf", f"invoice_{num_int}.pdf", f"*{inv_id}*.pdf"):
                                    found = list(repo_root.rglob(cand_pattern))
                                    if found:
                                        rel_path = _to_clean_display_path(found[0], repo_root)
                                        candidate_file = (found[0].name, rel_path, rel_path)
                                        break

                            if candidate_file:
                                fn, fpath, open_target = candidate_file
                            else:
                                fn = f"invoice_{inv_id}.pdf"
                                fpath = f"Database: public.invoices ({inv_id} - {cust}, {stat})"
                                open_target = fpath

                            files.append({
                                "name": fn,
                                "path": fpath,
                                "type": "pdf",
                                "modified_at": due,
                                "open_url": open_target,
                                "source": "database",
                            })
                            if len(files) >= max_results:
                                break
                    except Exception as db_exc:
                        logger.warning("Database invoices query error: %s", db_exc)

                # 2b. Contracts Search in Database
                if len(files) < max_results and (category == "contract" or not is_generic or any(w in clean_q.casefold() for w in ("contract", "agreement", "nda", "renewal"))):
                    try:
                        if not is_generic and specific_tokens:
                            conds = []
                            params = []
                            for t in specific_tokens[:3]:
                                conds.append("(LOWER(customer) LIKE %s OR LOWER(id) LIKE %s OR LOWER(contract_type) LIKE %s)")
                                p = f"%{t}%"
                                params.extend([p, p, p])
                            where_sql = " OR ".join(conds) if conds else "1=1"
                            res = tool.read(
                                user,
                                f"SELECT id, customer, contract_type, annual_value, renewal_date, status FROM public.contracts WHERE {where_sql} ORDER BY renewal_date DESC LIMIT 50",
                                tuple(params),
                            )
                        else:
                            res = tool.read(
                                user,
                                "SELECT id, customer, contract_type, annual_value, renewal_date, status FROM public.contracts ORDER BY renewal_date DESC LIMIT 50",
                                (),
                            )

                        for row in res.rows:
                            cid = str(row[0])
                            cust = str(row[1])
                            ren = str(row[4])

                            candidate_file = None
                            cust_token = cust.split()[0].lower()
                            if repo_root.exists():
                                for cand_pattern in (f"*{cust_token}*.docx", f"*{cust_token}*.pdf", f"*{cid.lower()}*.*"):
                                    found = list(repo_root.rglob(cand_pattern))
                                    if found:
                                        rel_path = _to_clean_display_path(found[0], repo_root)
                                        candidate_file = (found[0].name, rel_path, rel_path)
                                        break

                            if candidate_file:
                                fn, fpath, open_target = candidate_file
                            else:
                                fn = f"Contract_{cust.replace(' ', '_')}_{cid}.docx"
                                fpath = f"Database: public.contracts ({cid} - {cust}, {ren})"
                                open_target = fpath

                            files.append({
                                "name": fn,
                                "path": fpath,
                                "type": Path(fn).suffix.lstrip(".") or "docx",
                                "modified_at": ren,
                                "open_url": open_target,
                                "source": "database",
                            })
                            if len(files) >= max_results:
                                break
                    except Exception as db_exc:
                        logger.warning("Database contracts query error: %s", db_exc)

                # 2c. Real Files Registry Search in Database
                if len(files) < max_results:
                    try:
                        if not is_generic and specific_tokens:
                            param = f"%{specific_tokens[0]}%"
                            res = tool.read(
                                user,
                                "SELECT filename, folder, full_path FROM public.files WHERE LOWER(filename) LIKE %s OR LOWER(folder) LIKE %s LIMIT 50",
                                (param, param),
                            )
                        else:
                            res = tool.read(
                                user,
                                "SELECT filename, folder, full_path FROM public.files ORDER BY id DESC LIMIT 50",
                                (),
                            )
                        for row in res.rows:
                            fn = str(row[0])
                            raw_p = Path(str(row[2]))
                            clean_disp = _to_clean_display_path(raw_p, repo_root)
                            files.append({
                                "name": fn,
                                "path": clean_disp,
                                "type": Path(fn).suffix.lstrip("."),
                                "modified_at": "",
                                "open_url": clean_disp,
                                "source": "database",
                            })
                            if len(files) >= max_results:
                                break
                    except Exception as db_exc:
                        logger.warning("Database files query error: %s", db_exc)

            for idx, f in enumerate(files, start=1):
                sources.append(
                    SourceReference(
                        reference_id=f"ref-db-{idx}",
                        source_type=SourceType.DATABASE,
                        display_name=f["name"],
                        title=f["name"],
                        location=f["path"],
                    )
                )
        except Exception as exc:
            logger.warning("Database search failed: %s", exc)

    # 3. Email
    elif clean_src in ("email", "mail", "gmail", "inbox"):
        try:
            from backend.connections.manager import get_connection_manager
            from backend.connections.services_catalog import is_service_enabled_for_connection

            # Authorization Gate: Verify service is enabled in Connections Hub
            cm = get_connection_manager()
            tenant_id = user.tenant_id or "enterprise-tenant"
            google_conns = cm._query(
                "SELECT * FROM public.connections WHERE tenant_id = %s AND provider = 'google' AND deleted_at IS NULL AND status = 'CONNECTED';",
                "SELECT * FROM connections WHERE tenant_id = ? AND provider = 'google' AND deleted_at IS NULL AND status = 'CONNECTED';",
                (tenant_id,),
            )
            if google_conns:
                active_google = None
                for gc in google_conns:
                    if gc.get("scope_level") == "user" and gc.get("owner_user_id") == user.user_id:
                        active_google = gc
                        break
                    if gc.get("scope_level") == "organization":
                        active_google = gc
                if active_google and not is_service_enabled_for_connection(active_google, "gmail", "search"):
                    logger.info("Gmail search skipped because Gmail service is disabled in Connections Hub.")
                    answer = "Gmail integration is currently disabled in your Connections Hub settings. You can enable it in Settings → Connections Hub."
                    return answer, [], []

            from backend.integrations.email.gmail import GmailEmailProvider
            from backend.integrations.email.models import EmailProviderContext, EmailSearchRequest

            provider = GmailEmailProvider()
            ctx = EmailProviderContext(
                access_token="live_auth",
                user_id=user.user_id,
                tenant_id=user.tenant_id,
            )

            # Build targeted Gmail query
            if is_generic:
                search_q = category if category != "general" else ""
            else:
                search_q = " ".join(specific_tokens) if specific_tokens else clean_q

            msgs = provider.search(ctx, EmailSearchRequest(query=search_q, max_results=max_results))
            for m in msgs:
                clean_subj = m.subject.strip() or "(No Subject)"
                sender_display = m.sender.address if m.sender and m.sender.address else (m.sender.name if m.sender else "Unknown")
                email_link = m.web_link or f"https://mail.google.com/mail/u/0/#all/{m.id}"

                if getattr(m, "attachments", None) and len(m.attachments) > 0:
                    for att in m.attachments:
                        files.append({
                            "name": att.name,
                            "path": f"Email: {clean_subj} (From: {sender_display})",
                            "type": Path(att.name).suffix.lstrip(".") or "pdf",
                            "modified_at": m.received_at.isoformat() if m.received_at else "",
                            "open_url": email_link,
                            "source": "email",
                        })
                        if len(files) >= max_results:
                            break
                else:
                    files.append({
                        "name": f"{clean_subj}.eml",
                        "path": f"Email: {clean_subj} (From: {sender_display})",
                        "type": "eml",
                        "modified_at": m.received_at.isoformat() if m.received_at else "",
                        "open_url": email_link,
                        "source": "email",
                    })
                if len(files) >= max_results:
                    break

            for idx, f in enumerate(files, start=1):
                sources.append(
                    SourceReference(
                        reference_id=f"ref-email-{idx}",
                        source_type=SourceType.EMAIL,
                        display_name=f["name"],
                        title=f["name"],
                        location=f["path"],
                    )
                )
        except Exception as exc:
            logger.warning("Email file search failed: %s", exc)

    # 4. Google Drive
    elif clean_src in ("google_drive", "drive", "gdrive"):
        try:
            from backend.connections.manager import get_connection_manager
            from backend.connections.services_catalog import is_service_enabled_for_connection

            # Authorization Gate: Verify Google Drive is enabled in Connections Hub
            cm = get_connection_manager()
            tenant_id = user.tenant_id or "enterprise-tenant"
            google_conns = cm._query(
                "SELECT * FROM public.connections WHERE tenant_id = %s AND provider = 'google' AND deleted_at IS NULL AND status = 'CONNECTED';",
                "SELECT * FROM connections WHERE tenant_id = ? AND provider = 'google' AND deleted_at IS NULL AND status = 'CONNECTED';",
                (tenant_id,),
            )
            if google_conns:
                active_google = None
                for gc in google_conns:
                    if gc.get("scope_level") == "user" and gc.get("owner_user_id") == user.user_id:
                        active_google = gc
                        break
                    if gc.get("scope_level") == "organization":
                        active_google = gc
                if active_google and not is_service_enabled_for_connection(active_google, "drive", "search"):
                    logger.info("Google Drive search skipped because Google Drive service is disabled in Connections Hub.")
                    answer = "Google Drive access is currently disabled in your Connections Hub settings. You can enable it in Settings → Connections Hub."
                    return answer, [], []

            from backend.integrations.email.gmail import GmailEmailProvider
            from backend.integrations.email.models import EmailProviderContext

            provider = GmailEmailProvider()
            ctx = EmailProviderContext(
                access_token="live_auth",
                user_id=user.user_id,
                tenant_id=user.tenant_id,
            )
            token = provider._resolve_access_token(ctx)
            if token:
                headers = {"Authorization": f"Bearer {token}"}
                q_filter = "trashed = false"

                if not is_generic and specific_tokens:
                    clauses = []
                    for w in specific_tokens[:2]:
                        safe_w = w.replace("'", "")
                        clauses.append(f"name contains '{safe_w}' or fullText contains '{safe_w}'")
                    q_filter += f" and ({' or '.join(clauses)})"
                elif category != "general":
                    q_filter += f" and (name contains '{category}' or fullText contains '{category}')"

                url = (
                    f"https://www.googleapis.com/drive/v3/files"
                    f"?q={urllib.parse.quote(q_filter)}"
                    f"&pageSize={max_results}"
                    f"&orderBy=modifiedTime desc"
                    f"&fields=files(id,name,mimeType,webViewLink,modifiedTime)"
                )
                res = requests.get(url, headers=headers, timeout=10)
                if res.status_code == 200:
                    drive_items = res.json().get("files", [])
                    for item in drive_items:
                        name = item.get("name", "Document")
                        link = item.get("webViewLink") or f"https://drive.google.com/file/d/{item.get('id')}/view"
                        files.append({
                            "name": name,
                            "path": f"Google Drive: /{name}",
                            "type": Path(name).suffix.lstrip(".") or "gdoc",
                            "modified_at": item.get("modifiedTime", ""),
                            "open_url": link,
                            "source": "drive",
                        })
                        if len(files) >= max_results:
                            break

            for idx, f in enumerate(files, start=1):
                sources.append(
                    SourceReference(
                        reference_id=f"ref-drive-{idx}",
                        source_type=SourceType.DRIVE,
                        display_name=f["name"],
                        title=f["name"],
                        location=f["path"],
                    )
                )
        except Exception as exc:
            logger.warning("Google Drive file search failed: %s", exc)

    # 5. Cloud
    elif clean_src in ("cloud", "cloud_storage"):
        answer = f"No documents matching **\"{clean_q}\"** were found in **Cloud Storage**."
        return answer, [], []

    # Date filtering feedback & zero misleading fallbacks
    date_label = tq.date_filter.display_label if tq.date_filter else None
    summary = ""
    if tq.date_filter is not None:
        df = tq.date_filter
        if files:
            cat_desc = f"{tq.doc_type} " if tq.doc_type else ""
            summary = f"Found **{len(files)}** {cat_desc}document{'s' if len(files) != 1 else ''} matching **{df.display_label}** in **{friendly_source}**:"
        else:
            cat_desc = f"{tq.doc_type} " if tq.doc_type else ""
            entity_desc = f" for **{tq.entity}**" if tq.entity else ""
            answer = (
                f"No {cat_desc}documents{entity_desc} matching **\"{clean_q}\"** for date **{df.display_label}** were found in **{friendly_source}**.\n\n"
                "---\n"
                "💡 **Would you like to widen the search?** You can specify a broader timeframe or remove the date filter."
            )
            return answer, [], []

    # If no files found at all in this specific source, return clean empty result
    if not files:
        cat_desc = f"{tq.doc_type} " if tq.doc_type else ""
        entity_desc = f" for **{tq.entity}**" if tq.entity else ""
        answer = (
            f"No {cat_desc}documents{entity_desc} matching **\"{clean_q}\"** were found in **{friendly_source}**.\n\n"
            "---\n"
            "💡 **Would you like to search another source?** You can choose:\n"
            "- **Local Storage**\n- **Database**\n- **Email**\n- **Google Drive**\n- **Cloud**"
        )
        return answer, [], []

    # Limit to max_results (top 5 to 10)
    files = files[:max_results]

    q_low = clean_q.casefold()
    if any(f.get("is_category_fallback") for f in files):
        summary = f"We couldn't find an exact match for **\"{clean_q}\"**, but here are the available {category} documents in **{friendly_source}**:"
    elif date_label is not None and summary:
        pass  # summary already formatted above
    elif is_generic:
        cat_desc = f"{category} " if category != "general" else ""
        summary = f"Found **{len(files)}** recently added {cat_desc}document{'s' if len(files) != 1 else ''} in **{friendly_source}**:"
    elif "overdue" in q_low and any(w in q_low for w in ("invoice", "invoices", "bill", "due")):
        summary = f"Found **{len(files)}** overdue invoice document{'s' if len(files) != 1 else ''} in **{friendly_source}**:"
    elif any(w in q_low for w in ("invoice", "invoices", "bill")):
        summary = f"Found **{len(files)}** invoice document{'s' if len(files) != 1 else ''} in **{friendly_source}**:"
    elif any(w in q_low for w in ("contract", "contracts", "agreement", "nda")):
        summary = f"Found **{len(files)}** contract document{'s' if len(files) != 1 else ''} in **{friendly_source}**:"
    else:
        summary = f"Found **{len(files)}** matching document{'s' if len(files) != 1 else ''} in **{friendly_source}**:"

    # Exact 3-column table: File Name | File Path | Action
    lines = [
        "| File Name | File Path | Action |",
        "| --- | --- | --- |",
    ]
    for f in files:
        name = f["name"]
        path = f.get("full_path") or f.get("open_url") or f["path"]
        open_target = f.get("open_url") or path
        lines.append(f"| {name} | `{path}` | [Open]({open_target}) |")

    answer = f"{summary}\n\n" + "\n".join(lines)
    snippets = [f for f in files if f.get("content_snippet")]
    if snippets:
        answer += "\n\n**Relevant Document Excerpts:**\n"
        for s in snippets[:3]:
            snip = s["content_snippet"].strip().replace("\n", " ")
            if len(snip) > 220:
                snip = snip[:220] + "..."
            answer += f"• **{s['name']}**: *\"{snip}\"*\n"

    # Offer follow-up date filter prompt if query didn't already have one
    if date_label is None:
        answer += (
            "\n\n---\n"
            "💡 **Looking for a specific timeframe?** You can provide a specific date "
            "(e.g. *\"files modified on Oct 5\"* or *\"modified last week\"*), "
            "and I'll filter for files updated on that day."
        )

    return answer, files, sources

