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
    if any(w in q_low for w in ("invoice", "invoices", "bill", "bills", "billing")):
        category = "invoice"
    elif any(w in q_low for w in ("contract", "contracts", "agreement", "agreements", "nda", "ndas", "renewal")):
        category = "contract"
    elif any(w in q_low for w in ("receipt", "receipts", "ticket", "tickets")):
        category = "receipt"
    elif any(w in q_low for w in ("policy", "policies", "handbook", "guide")):
        category = "policy"
    elif any(w in q_low for w in ("resume", "resumes", "cv", "candidate", "candidates")):
        category = "resume"

    category_terms = {
        "invoice", "invoices", "bill", "bills", "billing", "contract", "contracts",
        "agreement", "agreements", "nda", "ndas", "document", "documents", "file",
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


def _extract_date_filter(query: str) -> tuple[str | None, int | None, int | None, int | None]:
    """Extract explicit date expression from query.

    Returns:
        (display_str, year, month, day) or (None, None, None, None)
    """
    q = query.casefold()

    if "today" in q:
        d = datetime.now(timezone.utc)
        return "Today", d.year, d.month, d.day
    if "yesterday" in q:
        from datetime import timedelta
        d = datetime.now(timezone.utc) - timedelta(days=1)
        return "Yesterday", d.year, d.month, d.day

    # ISO formats: 2026-10-05, 2026/10/05, 2026-03-14
    iso_m = re.search(r"\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})\b", q)
    if iso_m:
        y, m, d = int(iso_m.group(1)), int(iso_m.group(2)), int(iso_m.group(3))
        return f"{y:04d}-{m:02d}-{d:02d}", y, m, d

    # Numeric formats: 10/05/2026, 05-10-2026
    dmy_m = re.search(r"\b(\d{1,2})[-/](\d{1,2})[-/](\d{4})\b", q)
    if dmy_m:
        p1, p2, y = int(dmy_m.group(1)), int(dmy_m.group(2)), int(dmy_m.group(3))
        if p1 > 12:
            d, m = p1, p2
        else:
            m, d = p1, p2
        return f"{y:04d}-{m:02d}-{d:02d}", y, m, d

    months = {
        "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
        "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
        "aug": 8, "august": 8, "sep": 9, "september": 9, "oct": 10, "october": 10,
        "nov": 11, "november": 11, "dec": 12, "december": 12,
    }
    m_names = "|".join(months.keys())

    # Form A: "Oct 5", "October 5th, 2026"
    pat_a = rf"\b({m_names})\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s*(\d{{4}}))?\b"
    match_a = re.search(pat_a, q)
    if match_a:
        m_str = match_a.group(1)
        day_val = int(match_a.group(2))
        year_val = int(match_a.group(3)) if match_a.group(3) else 2026
        month_val = months[m_str]
        disp = f"{m_str.capitalize()} {day_val}, {year_val}"
        return disp, year_val, month_val, day_val

    # Form B: "5th Oct", "5 October 2026"
    pat_b = rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({m_names})(?:,?\s*(\d{{4}}))?\b"
    match_b = re.search(pat_b, q)
    if match_b:
        day_val = int(match_b.group(1))
        m_str = match_b.group(2)
        year_val = int(match_b.group(3)) if match_b.group(3) else 2026
        month_val = months[m_str]
        disp = f"{m_str.capitalize()} {day_val}, {year_val}"
        return disp, year_val, month_val, day_val

    return None, None, None, None


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

            # 1B. Discover server disk files (CompanyData folder)
            server_disk_files: list[dict[str, Any]] = []
            cds = CompanyDataService.for_tenant(user.tenant_id)
            repo_root = Path(cds.root)

            all_disk_files: list[Path] = []
            if repo_root.exists() and repo_root.is_dir():
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

            if is_generic:
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

                scored: list[tuple[float, Path]] = []
                for p in all_disk_files:
                    fn_low = p.name.casefold()
                    path_low = str(p).casefold()
                    p_full = str(p).replace("\\", "/").casefold()

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
                        if ext in (".txt", ".csv", ".json", ".md", ".py"):
                            try:
                                content_str = p.read_text(encoding="utf-8", errors="ignore")[:50000].casefold()
                            except Exception:
                                pass
                        elif ext in (".pdf", ".docx", ".xlsx", ".pptx"):
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

                    score = 0.0

                    # 1. Exact phrase match inside content or filename (e.g. "Acme Corp", "Globex Global")
                    if specific_phrase and len(primary_tokens) > 1:
                        if specific_phrase in fn_low:
                            score += 400.0
                        if specific_phrase in content_str:
                            score += 350.0

                    # 2. Primary exact client name / ID matches (e.g. 'initech', 'cust-002', 'acme')
                    primary_matches_fn = 0
                    primary_matches_ct = 0
                    for token in primary_tokens:
                        if token in fn_low:
                            primary_matches_fn += 1
                            score += 300.0
                        if token in content_str:
                            primary_matches_ct += 1
                            score += 250.0

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

                    total_matches = primary_matches_fn + primary_matches_ct + exp_matches_fn + exp_matches_ct
                    if total_matches == 0:
                        continue

                    # Bonus for matching all primary tokens
                    if primary_tokens and (primary_matches_fn + primary_matches_ct) >= len(primary_tokens):
                        score += 100.0

                    # Category bonus if category was mentioned (e.g. invoice, contract)
                    if category != "general" and (category in fn_low or category in path_low):
                        score += 30.0

                    scored.append((score, p))

                scored.sort(key=lambda x: (x[0], x[1].stat().st_mtime if x[1].exists() else 0), reverse=True)
                for _, p in scored[:max_results]:
                    disp_path = _to_clean_display_path(p, repo_root)
                    server_disk_files.append({
                        "name": p.name,
                        "path": disp_path,
                        "type": p.suffix.lstrip("."),
                        "modified_at": datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).isoformat(),
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

    # Check if query requests a specific date
    date_label, dy, dm, dd = _extract_date_filter(clean_q)
    summary = ""
    if date_label is not None:
        date_matched_files = []
        for f in files:
            m_str = f.get("modified_at") or ""
            if m_str:
                target_iso = f"{dy:04d}-{dm:02d}-{dd:02d}"
                if target_iso in m_str:
                    date_matched_files.append(f)
                    continue
                try:
                    f_dt = datetime.fromisoformat(m_str.replace("Z", "+00:00"))
                    if f_dt.year == dy and f_dt.month == dm and f_dt.day == dd:
                        date_matched_files.append(f)
                        continue
                except Exception:
                    pass
        if date_matched_files:
            files = date_matched_files
            summary = f"Found **{len(files)}** document{'s' if len(files) != 1 else ''} modified on **{date_label}** in **{friendly_source}**:"
        else:
            summary = f"No documents modified specifically on **{date_label}** were found in **{friendly_source}**. Here are the most recent documents in this source:"

    # If no files found at all in this specific source, return clean empty result
    if not files:
        answer = (
            f"No documents matching **\"{clean_q}\"** were found in **{friendly_source}**.\n\n"
            "---\n"
            "💡 **Would you like to search another source?** You can choose:\n"
            "- **Local Storage**\n- **Database**\n- **Email**\n- **Google Drive**\n- **Cloud**"
        )
        return answer, [], []

    # Limit to max_results (top 5 to 10)
    files = files[:max_results]

    q_low = clean_q.casefold()
    if date_label is not None and summary:
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

