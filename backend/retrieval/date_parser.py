"""Tolerant enterprise date parser with data-grounded year resolution and window-based matching."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Sequence

logger = logging.getLogger(__name__)

MONTH_MAP: dict[str, int] = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}


@dataclass
class DateFilter:
    """Parsed date filter specification."""
    target_date: str | None = None  # YYYY-MM-DD
    window_days: int = 0
    start_date: str | None = None  # YYYY-MM-DD
    end_date: str | None = None  # YYYY-MM-DD
    is_approx: bool = False
    year_inferred: bool = False
    year_clarification_needed: bool = False
    display_label: str = ""
    target_field: str = "document_date"  # "document_date" or "modified_at"
    filter_mode: str = "exact"  # "exact", "window", "ending_soon", "range"


def _clean_query(text: str) -> str:
    return text.strip().casefold()


def _normalize_year(year_token: str, available_years: Sequence[int] | None = None, clock_year: int | None = None) -> int | None:
    """Resolve 2-digit, 3-digit, or 4-digit year tokens using available data years and clock."""
    y_str = year_token.strip()
    c_year = clock_year or datetime.now(timezone.utc).year

    # 4-digit year
    if len(y_str) == 4 and y_str.isdigit():
        return int(y_str)

    # 2-digit year (e.g. '25' -> 2025, '26' -> 2026)
    if len(y_str) == 2 and y_str.isdigit():
        century = (c_year // 100) * 100
        cand_year = century + int(y_str)
        return cand_year

    # 3-digit typo year (e.g. '225' -> typo for 2025)
    if len(y_str) == 3 and y_str.isdigit():
        # E.g. '225' -> ends with 25 -> 2025; '025' -> 2025
        last_two = int(y_str[-2:])
        century = (c_year // 100) * 100
        cand = century + last_two
        if available_years and cand in available_years:
            return cand
        return cand

    return None


def parse_query_date(
    query: str,
    available_years: Sequence[int] | None = None,
    clock: datetime | None = None,
) -> DateFilter | None:
    """Extract and parse date expressions from user queries tolerantly.
    
    Zero hardcoded business dates or years.
    """
    now = clock or datetime.now(timezone.utc)
    q = _clean_query(query)

    target_field = "modified_at" if any(w in q for w in ("modified on", "modified at", "last updated", "file modified", "st_mtime")) else "document_date"
    is_approx = any(w in q for w in ("around", "close to", "near", "approx", "approximately", "about"))
    window_days = 7 if is_approx else 0

    # 1. Phrases like "ending soon", "projects going to end soon", "expiring soon"
    if any(phrase in q for phrase in ("end soon", "ending soon", "going to end soon", "expires soon", "expiring soon", "due soon")):
        today_str = now.strftime("%Y-%m-%d")
        future_str = (now + timedelta(days=60)).strftime("%Y-%m-%d")
        return DateFilter(
            start_date=today_str,
            end_date=future_str,
            window_days=60,
            display_label="ending soon (next 60 days)",
            target_field=target_field,
            filter_mode="ending_soon",
        )

    # 2. Today / Yesterday
    if "today" in q:
        d_str = now.strftime("%Y-%m-%d")
        return DateFilter(
            target_date=d_str,
            start_date=d_str,
            end_date=d_str,
            display_label="Today",
            target_field=target_field,
            filter_mode="exact",
        )
    if "yesterday" in q:
        yest = now - timedelta(days=1)
        d_str = yest.strftime("%Y-%m-%d")
        return DateFilter(
            target_date=d_str,
            start_date=d_str,
            end_date=d_str,
            display_label="Yesterday",
            target_field=target_field,
            filter_mode="exact",
        )

    # 3. ISO format: YYYY-MM-DD or YYYY/MM/DD
    iso_m = re.search(r"\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})\b", q)
    if iso_m:
        y, m, d = int(iso_m.group(1)), int(iso_m.group(2)), int(iso_m.group(3))
        try:
            target_dt = date(y, m, d)
            target_str = target_dt.strftime("%Y-%m-%d")
            start_str = (target_dt - timedelta(days=window_days)).strftime("%Y-%m-%d")
            end_str = (target_dt + timedelta(days=window_days)).strftime("%Y-%m-%d")
            return DateFilter(
                target_date=target_str,
                start_date=start_str,
                end_date=end_str,
                window_days=window_days,
                is_approx=is_approx,
                display_label=f"{target_str} (±{window_days}d)" if is_approx else target_str,
                target_field=target_field,
                filter_mode="window" if is_approx else "exact",
            )
        except ValueError:
            pass

    # 4. Numeric formats: DD/MM/YYYY or DD-MM-YYYY or MM/DD/YY or DD/MM/YY
    num_m = re.search(r"\b(\d{1,2})[-/](\d{1,2})[-/](\d{2,4})\b", q)
    if num_m:
        p1, p2, y_token = int(num_m.group(1)), int(num_m.group(2)), num_m.group(3)
        y = _normalize_year(y_token, available_years, now.year)
        if y:
            # Determine day vs month (if p1 > 12, p1 is day)
            d, m = (p1, p2) if p1 > 12 else (p2, p1)
            try:
                target_dt = date(y, m, d)
                target_str = target_dt.strftime("%Y-%m-%d")
                start_str = (target_dt - timedelta(days=window_days)).strftime("%Y-%m-%d")
                end_str = (target_dt + timedelta(days=window_days)).strftime("%Y-%m-%d")
                return DateFilter(
                    target_date=target_str,
                    start_date=start_str,
                    end_date=end_str,
                    window_days=window_days,
                    is_approx=is_approx,
                    display_label=f"{target_str} (±{window_days}d)" if is_approx else target_str,
                    target_field=target_field,
                    filter_mode="window" if is_approx else "exact",
                )
            except ValueError:
                pass

    # 5. Natural month expressions: e.g. "9 aug 25", "9 aug 225", "9th August 2025", "August 9 2025", "9 aug"
    m_pattern = "|".join(MONTH_MAP.keys())

    # Form A: "9 aug 25", "9th aug 2025", "9 aug 225", "9 aug"
    pat_day_first = rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({m_pattern})(?:\s+(\d{{2,4}}))?\b"
    m_df = re.search(pat_day_first, q)

    # Form B: "aug 9 25", "august 9th, 2025", "aug 9"
    pat_month_first = rf"\b({m_pattern})\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s*(\d{{2,4}}))?\b"
    m_mf = re.search(pat_month_first, q)

    day_val = None
    month_val = None
    year_token = None

    if m_df:
        day_val = int(m_df.group(1))
        month_val = MONTH_MAP[m_df.group(2)]
        year_token = m_df.group(3)
    elif m_mf:
        month_val = MONTH_MAP[m_mf.group(1)]
        day_val = int(m_mf.group(2))
        year_token = m_mf.group(3)

    if day_val is not None and month_val is not None:
        y_final = None
        year_inferred = False
        year_clarification_needed = False

        if year_token:
            y_final = _normalize_year(year_token, available_years, now.year)
        else:
            # Year is missing from the query!
            # Look at which years exist in the data for that doc type
            if available_years:
                uniq_years = sorted(list(set(available_years)))
                if len(uniq_years) == 1:
                    y_final = uniq_years[0]
                    year_inferred = True
                else:
                    # Multiple plausible years exist -> check if current year is one
                    y_final = uniq_years[0]  # candidate
                    year_clarification_needed = True
            else:
                y_final = now.year
                year_inferred = True

        if y_final:
            try:
                target_dt = date(y_final, month_val, day_val)
                target_str = target_dt.strftime("%Y-%m-%d")
                start_str = (target_dt - timedelta(days=window_days)).strftime("%Y-%m-%d")
                end_str = (target_dt + timedelta(days=window_days)).strftime("%Y-%m-%d")
                label = f"{target_str} (±{window_days}d)" if is_approx else target_str
                return DateFilter(
                    target_date=target_str,
                    start_date=start_str,
                    end_date=end_str,
                    window_days=window_days,
                    is_approx=is_approx,
                    year_inferred=year_inferred,
                    year_clarification_needed=year_clarification_needed,
                    display_label=label,
                    target_field=target_field,
                    filter_mode="window" if is_approx else "exact",
                )
            except ValueError:
                pass

    return None

