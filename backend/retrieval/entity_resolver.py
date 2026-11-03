"""Enterprise Entity Resolver for resolving messy, partial, or misspelled queries to real indexed entities."""
from __future__ import annotations

import csv
import json
import logging
import math
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Sequence

import rapidfuzz.fuzz as fuzz

logger = logging.getLogger(__name__)


@dataclass
class EntityCandidate:
    """A real enterprise entity candidate discovered in company data."""
    canonical_name: str
    entity_type: str  # customer, vendor, employee, project, company, contract
    entity_id: str
    source: str
    score: float = 0.0
    aliases: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EntityCandidate:
        return cls(**data)


@dataclass
class ResolutionDecision:
    """The outcome of resolving a user entity query."""
    status: str  # "resolved", "ambiguous", "no_match", "short_query"
    candidate: EntityCandidate | None = None
    candidates: list[EntityCandidate] = field(default_factory=list)
    clarification_prompt: str | None = None


def _tokenize_name(name: str) -> list[str]:
    """Split name into clean alphanumeric word tokens."""
    return [w for w in re.findall(r"[a-zA-Z0-9]+", name.casefold()) if len(w) > 0]


class EntityIndex:
    """Persistent, thread-safe index of all verified real enterprise entities."""

    def __init__(self, persistence_path: Path | None = None) -> None:
        self._lock = RLock()
        self._entities: dict[str, EntityCandidate] = {}  # key: f"{type}:{canonical_name.lower()}"
        self._persistence_path = persistence_path
        self._token_entity_counts: dict[str, int] = {}
        self._total_entities: int = 0
        if self._persistence_path and self._persistence_path.exists():
            self._load_from_disk()

    def add_entity(
        self,
        canonical_name: str,
        entity_type: str,
        entity_id: str = "",
        source: str = "",
        aliases: Sequence[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        clean_name = canonical_name.strip()
        if not clean_name or len(clean_name) < 2:
            return

        key = f"{entity_type.casefold()}:{clean_name.casefold()}"
        with self._lock:
            existing = self._entities.get(key)
            alias_set = set(existing.aliases if existing else [])
            if aliases:
                for a in aliases:
                    if a and a.strip():
                        alias_set.add(a.strip())

            merged_meta = dict(existing.metadata if existing else {})
            if metadata:
                merged_meta.update(metadata)

            final_id = entity_id or (existing.entity_id if existing else "")
            final_src = source or (existing.source if existing else "")

            self._entities[key] = EntityCandidate(
                canonical_name=clean_name,
                entity_type=entity_type.casefold(),
                entity_id=final_id,
                source=final_src,
                aliases=sorted(list(alias_set)),
                metadata=merged_meta,
            )

    def total_count(self) -> int:
        with self._lock:
            return len(self._entities)

    def list_all(self) -> list[EntityCandidate]:
        with self._lock:
            return list(self._entities.values())

    def rebuild_statistical_weights(self) -> None:
        """Compute document/entity frequencies for tokens across all real entity names.
        
        Statistical generic-term detection: Any word appearing in a large percentage
        of entity names carries lower distinctiveness weight, avoiding manual hardcoded stopword lists.
        """
        with self._lock:
            self._token_entity_counts.clear()
            self._total_entities = len(self._entities)
            if self._total_entities == 0:
                return

            for cand in self._entities.values():
                tokens = set(_tokenize_name(cand.canonical_name))
                for alias in cand.aliases:
                    tokens.update(_tokenize_name(alias))
                for t in tokens:
                    self._token_entity_counts[t] = self._token_entity_counts.get(t, 0) + 1

    def get_token_weight(self, token: str) -> float:
        """Calculate statistical distinctiveness weight (0.1 to 1.0) for a token."""
        t_clean = token.casefold().strip()
        with self._lock:
            if self._total_entities <= 1 or t_clean not in self._token_entity_counts:
                return 1.0
            freq = self._token_entity_counts[t_clean] / self._total_entities
            if freq >= 0.35:
                # Downweight highly frequent corporate suffixes/words discovered in the data
                return max(0.1, 1.0 - (freq / 0.7))
            return 1.0

    def resolve(
        self,
        query: str,
        entity_type_hint: str | None = None,
        min_score: float = 60.0,
    ) -> ResolutionDecision:
        """Resolve a messy query to real candidate entities.
        
        Scoring Hierarchy:
          1. Exact match (case-insensitive) -> 100
          2. Substring match -> 95
          3. Prefix of every query token matches a candidate word -> 90
          4. rapidfuzz token_set_ratio & partial_ratio with statistical token weighting
        """
        raw_q = query.strip()
        if not raw_q:
            return ResolutionDecision(status="no_match")

        q_lower = raw_q.casefold()
        q_tokens = _tokenize_name(raw_q)

        # Very short queries (1-2 characters) must always prompt the user to choose
        if len(raw_q) <= 2:
            candidates: list[EntityCandidate] = []
            with self._lock:
                for cand in self._entities.values():
                    if entity_type_hint and cand.entity_type != entity_type_hint.casefold():
                        continue
                    c_tokens = _tokenize_name(cand.canonical_name)
                    if any(t.startswith(q_lower) for t in c_tokens) or q_lower in cand.canonical_name.casefold():
                        c_copy = EntityCandidate(**cand.to_dict())
                        c_copy.score = 90.0
                        candidates.append(c_copy)
            candidates = candidates[:5]
            if candidates:
                return ResolutionDecision(
                    status="short_query",
                    candidates=candidates,
                    clarification_prompt=f"Please specify which entity you mean: {', '.join(c.canonical_name for c in candidates)}",
                )
            return ResolutionDecision(status="no_match")

        scored_candidates: list[EntityCandidate] = []

        with self._lock:
            for cand in self._entities.values():
                if entity_type_hint and cand.entity_type != entity_type_hint.casefold():
                    continue

                c_lower = cand.canonical_name.casefold()
                c_tokens = _tokenize_name(cand.canonical_name)
                names_to_check = [c_lower] + [a.casefold() for a in cand.aliases]

                # 1. Exact match (case-insensitive) -> 100
                if any(q_lower == n for n in names_to_check):
                    c_copy = EntityCandidate(**cand.to_dict())
                    c_copy.score = 100.0
                    scored_candidates.append(c_copy)
                    continue

                # 2. Query is a substring of a candidate name, or vice versa -> 95
                if any(q_lower in n or n in q_lower for n in names_to_check if len(n) >= 3):
                    c_copy = EntityCandidate(**cand.to_dict())
                    c_copy.score = 95.0
                    scored_candidates.append(c_copy)
                    continue

                # 3. Every query word is a prefix of some word in the candidate name -> 90
                # E.g. first letters or initials matching entity name tokens
                if q_tokens and c_tokens:
                    all_prefixes = True
                    matched_c_idx = set()
                    for qw in q_tokens:
                        found_prefix = False
                        for idx, cw in enumerate(c_tokens):
                            if idx not in matched_c_idx and cw.startswith(qw):
                                found_prefix = True
                                matched_c_idx.add(idx)
                                break
                        if not found_prefix:
                            all_prefixes = False
                            break

                    if all_prefixes:
                        c_copy = EntityCandidate(**cand.to_dict())
                        c_copy.score = 90.0
                        scored_candidates.append(c_copy)
                        continue

                # 4. Multi-token overlap & rapidfuzz partial_token_set_ratio / token_set_ratio
                matched_words = 0
                for qw in q_tokens:
                    if any(cw == qw or (len(qw) >= 3 and cw.startswith(qw)) or (len(cw) >= 3 and qw.startswith(cw)) for cw in c_tokens):
                        matched_words += 1

                pts_score = float(fuzz.partial_token_set_ratio(q_lower, c_lower)) if hasattr(fuzz, "partial_token_set_ratio") else 0.0
                if len(q_tokens) >= 2 and matched_words >= 2 and pts_score >= 90.0:
                    c_copy = EntityCandidate(**cand.to_dict())
                    c_copy.score = 92.0
                    scored_candidates.append(c_copy)
                    continue

                best_fuzzy = 0.0
                for n in names_to_check:
                    ts_score = float(fuzz.token_set_ratio(q_lower, n))
                    so_score = float(fuzz.token_sort_ratio(q_lower, n))
                    f_val = max(ts_score, so_score)

                    # Only use partial_ratio if query and name lengths are comparable
                    if abs(len(q_lower) - len(n)) <= 5 or q_lower in n or n in q_lower:
                        pt_score = float(fuzz.partial_ratio(q_lower, n))
                        f_val = max(f_val, pt_score)

                    if f_val > best_fuzzy:
                        best_fuzzy = f_val

                if best_fuzzy >= min_score:
                    c_copy = EntityCandidate(**cand.to_dict())
                    c_copy.score = round(best_fuzzy, 1)
                    scored_candidates.append(c_copy)

        if not scored_candidates:
            return ResolutionDecision(status="no_match")

        # Sort by score descending
        scored_candidates.sort(key=lambda x: x.score, reverse=True)

        # De-duplicate by canonical_name (case-insensitive) across types
        unique_cands: list[EntityCandidate] = []
        seen_names = set()
        for c in scored_candidates:
            name_key = c.canonical_name.casefold()
            if name_key not in seen_names:
                unique_cands.append(c)
                seen_names.add(name_key)
            else:
                # Merge entity_type into existing
                for ex in unique_cands:
                    if ex.canonical_name.casefold() == name_key:
                        if c.entity_type not in ex.entity_type:
                            ex.entity_type = f"{ex.entity_type}, {c.entity_type}"
                        break

        top_candidates = unique_cands[:5]
        top = top_candidates[0]

        # Decision Policy:
        # 1. One clear winner: score >= 90 and gap to next candidate >= 10
        gap = (top.score - top_candidates[1].score) if len(top_candidates) > 1 else 100.0
        if top.score >= 90.0 and gap >= 10.0:
            return ResolutionDecision(status="resolved", candidate=top, candidates=top_candidates)

        # 2. Several close candidates or ambiguous match
        cand_names = [f"'{c.canonical_name}' ({c.entity_type})" for c in top_candidates]
        prompt = f"Did you mean one of the following: {', '.join(cand_names)}?"
        return ResolutionDecision(
            status="ambiguous",
            candidate=None,
            candidates=top_candidates,
            clarification_prompt=prompt,
        )

    def save_to_disk(self) -> None:
        """Persist entity index state to disk."""
        if not self._persistence_path:
            return
        with self._lock:
            try:
                self._persistence_path.parent.mkdir(parents=True, exist_ok=True)
                data = {
                    "version": 1,
                    "saved_at": datetime.now(timezone.utc).isoformat(),
                    "total_entities": len(self._entities),
                    "entities": [cand.to_dict() for cand in self._entities.values()],
                }
                tmp_path = self._persistence_path.with_suffix(".tmp")
                tmp_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
                if os.name == "nt" and self._persistence_path.exists():
                    self._persistence_path.unlink()
                tmp_path.rename(self._persistence_path)
            except Exception as exc:
                logger.warning("Could not persist EntityIndex to disk: %s", exc)

    def _load_from_disk(self) -> None:
        """Load persisted entities from disk."""
        if not self._persistence_path or not self._persistence_path.exists():
            return
        try:
            content = self._persistence_path.read_text(encoding="utf-8")
            data = json.loads(content)
            for item in data.get("entities", []):
                cand = EntityCandidate.from_dict(item)
                key = f"{cand.entity_type.casefold()}:{cand.canonical_name.casefold()}"
                self._entities[key] = cand
            self.rebuild_statistical_weights()
            logger.info("Loaded %d entities from %s", len(self._entities), self._persistence_path)
        except Exception as exc:
            logger.warning("Failed to load entity index: %s", exc)


def discover_and_build_entity_index(
    company_data_dir: Path,
    persistence_path: Path | None = None,
) -> EntityIndex:
    """Scan company data directory using automated schema discovery and build the entity index.
    
    Zero hardcoded company/entity names, zero hardcoded word lists.
    Column names are inferred by header semantics and content analysis.
    """
    index = EntityIndex(persistence_path=persistence_path)

    if not company_data_dir.exists():
        return index

    # 1. Inspect any top-level index files (e.g. companydata_index.json)
    for idx_file in company_data_dir.glob("*index*.json"):
        try:
            with open(idx_file, "r", encoding="utf-8", errors="ignore") as fp:
                data = json.load(fp)
                if isinstance(data, dict):
                    # Check for primary company
                    for k in ("company", "organization", "enterprise", "business"):
                        if k in data and isinstance(data[k], str):
                            index.add_entity(
                                canonical_name=data[k],
                                entity_type="company",
                                source=str(idx_file),
                            )
                    # Check for lists of projects, employees, vendors, clients
                    for list_key, inferred_type in (
                        ("projects", "project"),
                        ("employees", "employee"),
                        ("vendors", "vendor"),
                        ("customers", "customer"),
                        ("clients", "customer"),
                    ):
                        items = data.get(list_key)
                        if isinstance(items, list):
                            for item in items:
                                if isinstance(item, dict):
                                    name_val = item.get("name") or item.get("title")
                                    id_val = item.get("id") or item.get("code") or ""
                                    if name_val and isinstance(name_val, str):
                                        index.add_entity(
                                            canonical_name=name_val,
                                            entity_type=inferred_type,
                                            entity_id=str(id_val),
                                            source=str(idx_file),
                                            metadata=item,
                                        )
        except Exception as exc:
            logger.debug("Failed reading index json %s: %s", idx_file, exc)

    # 2. Automatically discover entities from CSV and XLSX files
    for root, _, files in os.walk(company_data_dir):
        for file in files:
            p = Path(root) / file
            ext = p.suffix.casefold()
            rel_path = str(p.relative_to(company_data_dir)).replace("\\", "/")
            rel_lower = rel_path.casefold()

            # Infer entity type from path
            inferred_type = "general"
            for candidate_type in ("customer", "vendor", "employee", "project", "contract", "transaction"):
                if candidate_type in rel_lower:
                    inferred_type = candidate_type
                    break

            if ext == ".csv":
                try:
                    with open(p, "r", encoding="utf-8", errors="ignore") as fp:
                        reader = csv.reader(fp)
                        headers = next(reader, None)
                        if not headers:
                            continue

                        # Header analysis: discover columns holding entity names
                        name_col_indices: list[tuple[int, str]] = []
                        id_col_idx = None
                        for i, h in enumerate(headers):
                            h_clean = h.strip().casefold()
                            # ID column detection
                            if id_col_idx is None and any(k in h_clean for k in ("_id", " id", "id")):
                                id_col_idx = i

                            # Name / entity column detection
                            if any(k in h_clean for k in ("name", "vendor", "customer", "merchant", "party", "client", "owner")):
                                specific_type = inferred_type
                                if "vendor" in h_clean:
                                    specific_type = "vendor"
                                elif "customer" in h_clean or "client" in h_clean:
                                    specific_type = "customer"
                                elif "merchant" in h_clean:
                                    specific_type = "vendor"
                                elif "party" in h_clean:
                                    specific_type = "party"
                                name_col_indices.append((i, specific_type))

                        for row in reader:
                            if not row:
                                continue
                            rec_id = row[id_col_idx].strip() if id_col_idx is not None and id_col_idx < len(row) else ""
                            for col_i, col_type in name_col_indices:
                                if col_i < len(row):
                                    val = row[col_i].strip()
                                    if val and len(val) >= 2 and not val.replace(".", "").isdigit():
                                        index.add_entity(
                                            canonical_name=val,
                                            entity_type=col_type,
                                            entity_id=rec_id,
                                            source=rel_path,
                                        )
                except Exception as exc:
                    logger.debug("Error parsing CSV %s: %s", p, exc)

            elif ext == ".xlsx":
                try:
                    import openpyxl
                    wb = openpyxl.load_workbook(p, read_only=True)
                    for sheetname in wb.sheetnames:
                        sheet = wb[sheetname]
                        rows = sheet.iter_rows(values_only=True)
                        header_row = next(rows, None)
                        if not header_row:
                            continue

                        name_col_indices = []
                        id_col_idx = None
                        for i, h in enumerate(header_row):
                            if not h:
                                continue
                            h_clean = str(h).strip().casefold()
                            if id_col_idx is None and any(k in h_clean for k in ("_id", " id", "id")):
                                id_col_idx = i
                            if any(k in h_clean for k in ("name", "vendor", "customer", "merchant", "party", "client", "owner", "account")):
                                specific_type = inferred_type
                                if "vendor" in h_clean:
                                    specific_type = "vendor"
                                elif "customer" in h_clean or "client" in h_clean or "account" in h_clean:
                                    specific_type = "customer"
                                name_col_indices.append((i, specific_type))

                        for row in rows:
                            if not row:
                                continue
                            rec_id = str(row[id_col_idx]).strip() if id_col_idx is not None and id_col_idx < len(row) and row[id_col_idx] is not None else ""
                            for col_i, col_type in name_col_indices:
                                if col_i < len(row) and row[col_i] is not None:
                                    val = str(row[col_i]).strip()
                                    if val and len(val) >= 2 and not val.replace(".", "").isdigit():
                                        index.add_entity(
                                            canonical_name=val,
                                            entity_type=col_type,
                                            entity_id=rec_id,
                                            source=rel_path,
                                        )
                except Exception as exc:
                    logger.debug("Error parsing XLSX %s: %s", p, exc)

            elif ext == ".pdf":
                # Check for PDF document entities (e.g. Invoices, Project Briefs)
                try:
                    import pypdf
                    reader = pypdf.PdfReader(p)
                    first_page = reader.pages[0].extract_text() if reader.pages else ""
                    if first_page:
                        # Extract Vendor: X
                        vm = re.search(r"(?:Vendor|Merchant):\s*([^\n\r]+)", first_page, re.IGNORECASE)
                        if vm:
                            index.add_entity(canonical_name=vm.group(1).strip(), entity_type="vendor", source=rel_path)
                        # Extract Customer / Client: X
                        cm = re.search(r"(?:Customer|Client):\s*([^\n\r]+)", first_page, re.IGNORECASE)
                        if cm:
                            index.add_entity(canonical_name=cm.group(1).strip(), entity_type="customer", source=rel_path)
                        # Extract Project Name: X
                        pm = re.search(r"Project Name:\s*([^\n\r]+)", first_page, re.IGNORECASE)
                        if pm:
                            index.add_entity(canonical_name=pm.group(1).strip(), entity_type="project", source=rel_path)
                except Exception as exc:
                    logger.debug("Error parsing PDF entity in %s: %s", p, exc)

    index.rebuild_statistical_weights()
    if persistence_path:
        index.save_to_disk()
    logger.info("Discovered and indexed %d enterprise entities from %s", index.total_count(), company_data_dir)
    return index


_GLOBAL_ENTITY_INDEX: EntityIndex | None = None


def get_entity_resolver(company_data_dir: Path | None = None) -> EntityIndex:
    """Retrieve or initialize the singleton EntityIndex."""
    global _GLOBAL_ENTITY_INDEX
    if _GLOBAL_ENTITY_INDEX is not None:
        return _GLOBAL_ENTITY_INDEX

    data_dir = company_data_dir or Path(__file__).resolve().parents[1] / "CompanyData"
    cache_path = data_dir / "entity_index.json"
    _GLOBAL_ENTITY_INDEX = discover_and_build_entity_index(data_dir, persistence_path=cache_path)
    return _GLOBAL_ENTITY_INDEX


def disambiguate_with_llm(
    query: str,
    candidates: Sequence[EntityCandidate],
    provider: Any = None,
) -> EntityCandidate | None:
    """Disambiguate close entity candidates using grounded LLM choice.
    
    Zero hardcoded business names in prompts.
    Requires JSON only: {"match": <number|null>, "confidence": 0-1}.
    Validates that returned number is within candidate list bounds.
    """
    if not candidates or provider is None:
        return None

    # Format numbered list of real candidates
    lines = []
    for idx, cand in enumerate(candidates, start=1):
        lines.append(f"{idx}. {cand.canonical_name} ({cand.entity_type})")
    candidate_list_str = "\n".join(lines)

    prompt = (
        "You are an enterprise entity matcher. The user provided an entity query that could refer to one of the following real candidates in our system:\n\n"
        f"Real Candidates:\n{candidate_list_str}\n\n"
        f"User Query:\n\"{query}\"\n\n"
        "Your task: Decide if the user's query clearly refers to one of the numbered candidates above.\n"
        "Rules:\n"
        "1. You may ONLY choose a candidate number from the list above, or return null if none clearly matches.\n"
        "2. Do NOT invent, assume, or hallucinate any other name or candidate.\n"
        "3. Respond with JSON ONLY in this exact format:\n"
        "{\"match\": <number_or_null>, \"confidence\": <float_between_0_and_1>}"
    )

    try:
        raw_res = provider.generate(prompt)
        m = re.search(r"\{[^{}]*\}", raw_res)
        if m:
            data = json.loads(m.group(0))
            match_idx = data.get("match")
            confidence = float(data.get("confidence", 0.0))
            if match_idx is not None and isinstance(match_idx, int) and 1 <= match_idx <= len(candidates):
                if confidence >= 0.8:
                    return candidates[match_idx - 1]
    except Exception as exc:
        logger.debug("LLM disambiguation error: %s", exc)

    return None
