"""Dedicated Speech Normalization Layer for Nanvi AI Enterprise Assistant.

Converts structured enterprise data and text into natural, fluent human speech.
Strictly conforms to Section 6 (Speech Normalization) of the Voice Engine Specification:
- UI display text and spoken text are NEVER identical.
- EMP1004 -> "employee one zero zero four"
- ₹45,000 -> "forty-five thousand rupees"
- ₹4,50,000 -> "four lakh fifty thousand rupees"
- 2025-09-14 -> "September fourteenth, twenty twenty-five"
- hr@nanvi.ai -> "H R at nanvi dot A I"
- https://example.com/report -> "the report link"
- Never reads markdown, JSON, HTML, code, raw DB rows, UUIDs char-by-char, citation metadata, internal tool details.
"""
from __future__ import annotations

import re
from typing import Match

_ONES = [
    "", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
    "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
    "seventeen", "eighteen", "nineteen",
]
_TENS = [
    "", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety",
]

_MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

_ORDINALS = {
    1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth",
    6: "sixth", 7: "seventh", 8: "eighth", 9: "ninth", 10: "tenth",
    11: "eleventh", 12: "twelfth", 13: "thirteenth", 14: "fourteenth",
    15: "fifteenth", 16: "sixteenth", 17: "seventeenth", 18: "eighteenth",
    19: "nineteenth", 20: "twentieth", 21: "twenty-first", 22: "twenty-second",
    23: "twenty-third", 24: "twenty-fourth", 25: "twenty-fifth", 26: "twenty-sixth",
    27: "twenty-seventh", 28: "twenty-eighth", 29: "twenty-ninth", 30: "thirtieth",
    31: "thirty-first",
}

_PREFIX_NAMES: dict[str, str] = {
    "EMP": "employee",
    "INV": "invoice",
    "PROJ": "project",
    "TICK": "ticket",
    "ORD": "order",
    "PO": "P O",
    "REQ": "request",
    "DOC": "document",
    "RPT": "report",
    "ACCT": "account",
    "CUST": "customer",
    "VEND": "vendor",
    "SKU": "S K U",
}

_SPELLED_ACRONYMS: dict[str, str] = {
    "API": "A P I", "PDF": "P D F", "CSV": "C S V", "HR": "H R",
    "IT": "I T", "UI": "U I", "UX": "U X", "AI": "A I",
    "ML": "M L", "CEO": "C E O", "CTO": "C T O", "CFO": "C F O",
    "COO": "C O O", "VP": "V P", "KPI": "K P I", "ROI": "R O I",
    "SLA": "S L A", "NDA": "N D A", "GST": "G S T", "TDS": "T D S",
    "CTC": "C T C", "PAN": "P A N", "URL": "U R L", "HTTP": "H T T P",
    "SSO": "S S O", "RBAC": "R BAC", "LLM": "L L M", "AWS": "A W S",
    "GCP": "G C P", "CRM": "C R M", "ERP": "E R P", "PR": "P R",
    "ARR": "A R R", "MRR": "M R R",
}

_PRONOUNCED_ACRONYMS: dict[str, str] = {
    "SQL": "sequel",
    "POSTGRESQL": "postgres sequel",
    "MYSQL": "my sequel",
    "EBITDA": "E-BIT-DA",
}

_FORBIDDEN_TECH_PHRASES: list[re.Pattern] = [
    re.compile(r"\bthe\s+rag\s+agent\s+(?:found|returned|retrieved)\b", re.IGNORECASE),
    re.compile(r"\bthe\s+sql\s+agent\s+(?:found|returned|executed|queried)\b", re.IGNORECASE),
    re.compile(r"\bi\s+am\s+querying\s+(?:the\s+)?database\b", re.IGNORECASE),
    re.compile(r"\baccording\s+to\s+(?:the\s+)?(?:retrieved|provided|attached)?\s*(?:documents?|files?|context|database|records?)\b[,\s]*", re.IGNORECASE),
    re.compile(r"\bbased\s+on\s+(?:the\s+)?(?:retrieved|provided|attached)?\s*(?:documents?|files?|context|database|records?)\b[,\s]*", re.IGNORECASE),
    re.compile(r"\bcalling\s+(?:the\s+)?langgraph(?:\s+agent)?\b", re.IGNORECASE),
    re.compile(r"\bsearching\s+(?:the\s+)?vector\s+database\b", re.IGNORECASE),
    re.compile(r"\bas\s+an\s+ai(?:\s+language\s+model)?[,\s]*", re.IGNORECASE),
    re.compile(r"\bi'm\s+an\s+ai\s+assistant[,\s]*", re.IGNORECASE),
    re.compile(r"\bsure,?\s+i\s+can\s+help\s+you\s+with\s+that[.,!]*\s*", re.IGNORECASE),
]


def strip_technical_jargon(text: str) -> str:
    """Strips mentions of internal tools, agents, vector databases, and robot clichés."""
    if not text:
        return ""
    res = text
    for pat in _FORBIDDEN_TECH_PHRASES:
        res = pat.sub("", res)
    res = re.sub(r"\b(?:langgraph|vector databases?|embeddings?)\b", "", res, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", res).strip()



def number_to_words(n: int) -> str:
    """Convert an integer to natural English words (e.g. 45 -> forty-five)."""
    if n < 0:
        return "minus " + number_to_words(-n)
    if n == 0:
        return "zero"
    if n < 20:
        return _ONES[n]
    if n < 100:
        t, o = divmod(n, 10)
        return f"{_TENS[t]}-{_ONES[o]}" if o else _TENS[t]
    if n < 1000:
        h, rem = divmod(n, 100)
        return f"{_ONES[h]} hundred {number_to_words(rem)}" if rem else f"{_ONES[h]} hundred"
    if n < 100_000:  # up to 99 thousand
        th, rem = divmod(n, 1000)
        return f"{number_to_words(th)} thousand {number_to_words(rem)}" if rem else f"{number_to_words(th)} thousand"
    if n < 10_000_000:  # up to 99 lakh
        lk, rem = divmod(n, 100_000)
        return f"{number_to_words(lk)} lakh {number_to_words(rem)}" if rem else f"{number_to_words(lk)} lakh"
    if n < 1_000_000_000:  # up to 99 crore
        cr, rem = divmod(n, 10_000_000)
        return f"{number_to_words(cr)} crore {number_to_words(rem)}" if rem else f"{number_to_words(cr)} crore"
    b, rem = divmod(n, 1_000_000_000)
    return f"{number_to_words(b)} billion {number_to_words(rem)}" if rem else f"{number_to_words(b)} billion"


def spell_digits(digits: str) -> str:
    """Spell each digit individually (e.g. '1004' -> 'one zero zero four')."""
    d_map = {"0": "zero", "1": "one", "2": "two", "3": "three", "4": "four",
             "5": "five", "6": "six", "7": "seven", "8": "eight", "9": "nine"}
    return " ".join(d_map.get(d, d) for d in digits)


def year_to_words(year: int) -> str:
    """Format calendar year (e.g. 2025 -> twenty twenty-five)."""
    if 2000 <= year < 2010:
        rem = year - 2000
        return f"two thousand {number_to_words(rem)}" if rem else "two thousand"
    if 2010 <= year < 2100:
        tens = year - 2000
        return f"twenty {number_to_words(tens)}"
    if 1900 <= year < 2000:
        tens = year - 1900
        return f"nineteen {number_to_words(tens)}"
    return number_to_words(year)


def normalize_enterprise_id(match: Match) -> str:
    """EMP1004 -> 'employee one zero zero four'."""
    prefix = match.group(1).upper()
    digits = match.group(2)
    spoken_prefix = _PREFIX_NAMES.get(prefix, prefix)
    return f"{spoken_prefix} {spell_digits(digits)}"


def normalize_dashed_id(match: Match) -> str:
    """INV-2026-00421 -> 'invoice twenty twenty-six, zero zero four two one'."""
    prefix = match.group(1).upper()
    rest = match.group(2)
    spoken_prefix = _PREFIX_NAMES.get(prefix, prefix)
    parts = rest.split("-")
    spoken_parts: list[str] = []
    for part in parts:
        if part.isdigit():
            if len(part) == 4 and (part.startswith("19") or part.startswith("20")):
                spoken_parts.append(year_to_words(int(part)))
            else:
                spoken_parts.append(spell_digits(part))
        else:
            spoken_parts.append(part)
    return f"{spoken_prefix} {', '.join(spoken_parts)}"


def normalize_currency(text: str) -> str:
    """Convert Indian and international currency to spoken words."""
    # 1. Rupee abbreviations: ₹18.4 Cr, ₹12L, Rs 40 Lakhs
    def _replace_cr(m: Match) -> str:
        val = float(m.group(1))
        int_part = int(val)
        dec_part = round((val - int_part) * 10)
        if dec_part > 0:
            return f"{number_to_words(int_part)} point {number_to_words(dec_part)} crore rupees"
        return f"{number_to_words(int_part)} crore rupees"

    text = re.sub(r"(?:₹|rs\.?|inr)\s*(\d+(?:\.\d+)?)\s*(?:cr|crore|crores)\b", _replace_cr, text, flags=re.IGNORECASE)

    def _replace_lk(m: Match) -> str:
        val = float(m.group(1))
        int_part = int(val)
        dec_part = round((val - int_part) * 10)
        if dec_part > 0:
            return f"{number_to_words(int_part)} point {number_to_words(dec_part)} lakh rupees"
        return f"{number_to_words(int_part)} lakh rupees"

    text = re.sub(r"(?:₹|rs\.?|inr)\s*(\d+(?:\.\d+)?)\s*(?:l|lac|lacs|lakh|lakhs)\b", _replace_lk, text, flags=re.IGNORECASE)

    # 2. Indian formatted or raw rupees: ₹45,000, ₹4,50,000
    def _spoken_inr(m: Match) -> str:
        raw_val = m.group(1).replace(",", "")
        num = float(raw_val)
        int_num = int(num)
        return f"{number_to_words(int_num)} rupees"

    text = re.sub(r"(?:₹|rs\.?|inr)\s*(\d{1,3}(?:,\d{2,3})*(?:\.\d+)?)\b", _spoken_inr, text, flags=re.IGNORECASE)

    # 3. Dollar amounts with abbreviations: $4.2M, $100K, $5B
    def _spoken_usd_abbr(m: Match) -> str:
        val = m.group(1)
        suffix = m.group(2).lower()
        scale = {"b": " billion", "m": " million", "k": " thousand"}[suffix]
        return f"{val}{scale} dollars"

    text = re.sub(r"\$(\d+(?:\.\d+)?)\s*([BMKbmk])\b", _spoken_usd_abbr, text)

    def _spoken_usd(m: Match) -> str:
        raw_val = m.group(1).replace(",", "")
        num = float(raw_val)
        int_num = int(num)
        return f"{number_to_words(int_num)} dollars"

    text = re.sub(r"\$(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\b", _spoken_usd, text)
    text = re.sub(r"\$(\d+(?:\.\d+)?)", _spoken_usd, text)

    return text


def normalize_date(text: str) -> str:
    """2025-09-14 -> 'September fourteenth, twenty twenty-five'."""
    def _format_iso(m: Match) -> str:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= mo <= 12 and 1 <= d <= 31:
            month_name = _MONTHS[mo - 1]
            day_name = _ORDINALS.get(d, f"{d}th")
            y_words = year_to_words(y)
            return f"{month_name} {day_name}, {y_words}"
        return m.group(0)

    text = re.sub(r"\b(\d{4})-(\d{2})-(\d{2})\b", _format_iso, text)

    # DD/MM/YYYY
    def _format_dmy(m: Match) -> str:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= mo <= 12 and 1 <= d <= 31:
            month_name = _MONTHS[mo - 1]
            day_name = _ORDINALS.get(d, f"{d}th")
            y_words = year_to_words(y)
            return f"{month_name} {day_name}, {y_words}"
        return m.group(0)

    text = re.sub(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", _format_dmy, text)
    return text


def normalize_time(text: str) -> str:
    """10:30 AM -> 'ten thirty A M'."""
    def _format_time(m: Match) -> str:
        h, mn, period = int(m.group(1)), int(m.group(2)), m.group(3).upper()
        h_word = number_to_words(h)
        p_spelled = " ".join(list(period.replace(".", "")))
        if mn == 0:
            return f"{h_word} {p_spelled}"
        mn_word = number_to_words(mn) if mn >= 10 else f"oh {number_to_words(mn)}"
        return f"{h_word} {mn_word} {p_spelled}"

    return re.sub(r"\b(\d{1,2}):(\d{2})\s*(AM|PM|am|pm|a\.m\.|p\.m\.)\b", _format_time, text)


def normalize_email(text: str) -> str:
    """hr@nanvi.ai -> 'H R at nanvi dot A I'."""
    def _format_email(m: Match) -> str:
        user_part = m.group(1)
        domain_part = m.group(2)
        tld_part = m.group(3)

        # Spell acronym user part if 2-3 uppercase or lowercase letters
        if len(user_part) <= 3:
            spoken_user = " ".join(list(user_part.upper()))
        else:
            spoken_user = user_part

        if len(tld_part) <= 3:
            spoken_tld = " ".join(list(tld_part.upper()))
        else:
            spoken_tld = tld_part

        return f"{spoken_user} at {domain_part} dot {spoken_tld}"

    return re.sub(r"\b([a-zA-Z0-9._%+-]+)@([a-zA-Z0-9.-]+)\.([a-zA-Z]{2,})\b", _format_email, text)


def normalize_urls(text: str) -> str:
    """https://example.com/report -> 'the report link'."""
    def _format_url(m: Match) -> str:
        url = m.group(0).lower()
        if "report" in url:
            return "the report link"
        if "invoice" in url:
            return "the invoice link"
        if "doc" in url or "file" in url or "pdf" in url:
            return "the document link"
        if "contract" in url:
            return "the contract link"
        return "the link"

    return re.sub(r"https?://\S+", _format_url, text)


def normalize_percentages(text: str) -> str:
    """95% -> 'ninety-five percent', 12% -> 'twelve percent'."""
    def _format_pct(m: Match) -> str:
        val_str = m.group(1)
        if "." in val_str:
            num = float(val_str)
            int_p = int(num)
            dec_p = round((num - int_p) * 10)
            if dec_p > 0:
                return f"{number_to_words(int_p)} point {number_to_words(dec_p)} percent"
            return f"{number_to_words(int_p)} percent"
        return f"{number_to_words(int(val_str))} percent"

    return re.sub(r"(\d+(?:\.\d+)?)\s*%", _format_pct, text)


def normalize_acronyms(text: str) -> str:
    """Convert acronyms: API -> 'A P I', SQL -> 'sequel', HR -> 'H R'."""
    # Pronounced
    for acr, spoken in _PRONOUNCED_ACRONYMS.items():
        text = re.sub(rf"\b{acr}\b", spoken, text, flags=re.IGNORECASE)
    # Spelled
    for acr, spoken in _SPELLED_ACRONYMS.items():
        text = re.sub(rf"\b{acr}\b", spoken, text)
    return text


def normalize_filenames(text: str) -> str:
    """quarterly_report_2025.pdf -> 'quarterly report twenty twenty-five P D F'."""
    def _format_fn(m: Match) -> str:
        base = m.group(1).replace("_", " ").replace("-", " ")
        ext = m.group(2).upper()
        spoken_ext = " ".join(list(ext))
        # normalize any numbers in base
        base_clean = re.sub(r"\b(\d{4})\b", lambda ym: year_to_words(int(ym.group(1))), base)
        return f"{base_clean} {spoken_ext}"

    return re.sub(r"\b([a-zA-Z0-9_\-]+)\.(pdf|csv|xlsx?|docx?)\b", _format_fn, text, flags=re.IGNORECASE)


def normalize_for_speech(raw_text: str) -> str:
    """Full pipeline transforming written/UI assistant text into natural conversational voice text."""
    if not raw_text or not raw_text.strip():
        return "I have completed your request."

    import html
    text = html.unescape(raw_text.strip())
    # Strip invisible/zero-width formatting unicode characters
    text = re.sub(r"[\u034f\u200b-\u200f\ufeff\u202a-\u202e\u2060-\u206f]", "", text)

    # 1. Strip raw code blocks and inline code
    text = re.sub(r"```[\s\S]*?```", " Code details are available in your conversation record. ", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)

    # 2. Strip JSON structures
    text = re.sub(r"\{[^{}]*:[^{}]*\}", " ", text)

    # 3. Strip HTML
    text = re.sub(r"<[^>]+>", " ", text)

    # 4. Strip markdown tables
    if "|" in text:
        text = re.sub(r"(\|.*\|\n?)+", " Detailed figures are recorded in your context panel. ", text)

    # 5. Strip citations [1], [Source 2], [file.pdf]
    text = re.sub(r"\[(?:ref|source|\d+|file|doc)[^\]]*\]", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)

    # 6. Normalize URLs before general regex
    text = normalize_urls(text)

    # 7. Strip markdown headers
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)

    # 8. Strip forbidden tech clichés & robot language
    for pat in _FORBIDDEN_TECH_PHRASES:
        text = pat.sub("", text)

    # 9. Normalize Enterprise IDs (EMP1004 -> "employee one zero zero four")
    text = re.sub(r"\b([A-Z]{2,6})-(\d[\d-]+\d)\b", normalize_dashed_id, text)
    text = re.sub(r"\b([A-Z]{2,6})(\d{3,})\b", normalize_enterprise_id, text)

    # 10. Dates & Times
    text = normalize_date(text)
    text = normalize_time(text)

    # 11. Currencies & Percentages
    text = normalize_currency(text)
    text = normalize_percentages(text)

    # 12. Emails & Filenames
    text = normalize_email(text)
    text = normalize_filenames(text)

    # 13. Acronyms
    text = normalize_acronyms(text)

    # 14. Conversational expansions
    text = re.sub(r"\be\.g\b\.?,?\s*", "for example, ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bi\.e\b\.?,?\s*", "that is, ", text, flags=re.IGNORECASE)
    text = re.sub(r"\betc\b\.?", "and so forth", text, flags=re.IGNORECASE)
    text = re.sub(r"\bvs\b\.?\s*", "versus ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bQ([1-4])\b", r"Quarter \1", text)
    text = re.sub(r"\bFY\s*(\d{2,4})\b", r"Fiscal Year \1", text, flags=re.IGNORECASE)
    text = re.sub(r"&", " and ", text)

    # 15. UUID character-by-character replacement
    text = re.sub(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b", "the record ID", text)

    # 16. Strip formatting symbols (*, #, _, ~, `, |, <, >, ^, \\)
    text = re.sub(r"[\*\#\_~\|<>{}\^\\\/]", "", text)

    # 17. Clean bullet markers
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    processed_lines: list[str] = []
    for l in lines:
        l = re.sub(r"^[\-\•\◦\▪\▫\+]\s*", "", l)
        l = re.sub(r"^\d+[\.\)]\s*", "", l)
        processed_lines.append(l)

    cleaned_body = " ".join(processed_lines)
    cleaned_body = re.sub(r"[\U00010000-\U0010ffff]", "", cleaned_body)
    cleaned_body = re.sub(r"\s+", " ", cleaned_body).strip()

    # 18. Natural conversational pacing: limit to top 6 sentences for normal voice turns
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", cleaned_body) if s.strip()]
    if len(sentences) > 6:
        spoken = " ".join(sentences[:5])
        if not spoken.endswith((".", "!", "?")):
            spoken += "."
        spoken += " Further details are displayed in your panel."
        return spoken

    return cleaned_body
