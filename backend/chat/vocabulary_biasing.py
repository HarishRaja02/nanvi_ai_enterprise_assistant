"""Enterprise Vocabulary Biasing & Phonetic Correction for Nanvi AI.

Implements Section 7.6 of docs/NANVI_SPEC.md.
Provides enterprise domain vocabulary biasing for speech recognition (Groq Whisper,
Web Speech API) and phonetic/mishearing corrections for company names, projects,
personnel, and Indian financial/enterprise terminology.
"""
from __future__ import annotations

import re
from typing import Any

# Domain-specific enterprise entities and terminology
ENTERPRISE_COMPANIES = [
    "Asteron Technologies",
    "CloudNova",
    "BluePeak",
    "NexaCorp",
    "Horizon Dynamics",
    "QuantumTech",
    "Alpha Corp",
]

ENTERPRISE_PROJECTS = [
    "Project Phoenix",
    "Project Titan",
    "Project Horizon",
    "Project Odyssey",
    "Project Nexus",
]

ENTERPRISE_EXECUTIVES = [
    "Arjun Mehta",
    "Priya Sharma",
    "Rahul Patel",
    "Kavita Reddy",
    "Deepak Kumar",
    "Anita Desai",
    "Vikram Malhotra",
]

ENTERPRISE_ACRONYMS = [
    "GST",
    "CGST",
    "SGST",
    "IGST",
    "PO",
    "EBITDA",
    "CTC",
    "TDS",
    "ARR",
    "MRR",
    "SKU",
    "SLA",
    "NDA",
    "RAG",
    "SQL",
    "FY24",
    "FY25",
    "Q1",
    "Q2",
    "Q3",
    "Q4",
    "INR",
    "Lakh",
    "Crore",
]

# Combined list for vocabulary biasing
ALL_ENTERPRISE_TERMS = (
    ENTERPRISE_COMPANIES
    + ENTERPRISE_PROJECTS
    + ENTERPRISE_EXECUTIVES
    + ENTERPRISE_ACRONYMS
)

# Whisper prompt biasing string (injected into Whisper-large-v3 prompt)
WHISPER_BIASING_PROMPT = ", ".join(ALL_ENTERPRISE_TERMS)

# Phonetic corrections for common speech-to-text mishearings
PHONETIC_CORRECTIONS: list[tuple[re.Pattern, str]] = [
    # Company names
    (re.compile(r"\baster\s*on(?:\s*tech(?:nologies)?)?\b", re.IGNORECASE), "Asteron Technologies"),
    (re.compile(r"\bcloud\s+nova\b", re.IGNORECASE), "CloudNova"),
    (re.compile(r"\bblue\s+peak\b", re.IGNORECASE), "BluePeak"),
    (re.compile(r"\bnexa\s*corp\b", re.IGNORECASE), "NexaCorp"),
    (re.compile(r"\bhorizon\s+dynamics?\b", re.IGNORECASE), "Horizon Dynamics"),
    (re.compile(r"\bquantum\s*tech\b", re.IGNORECASE), "QuantumTech"),
    
    # Project names
    (re.compile(r"\bproject\s+fenix\b", re.IGNORECASE), "Project Phoenix"),
    (re.compile(r"\bproject\s+phenix\b", re.IGNORECASE), "Project Phoenix"),
    
    # Acronyms & Enterprise terms
    (re.compile(r"\bebidta\b", re.IGNORECASE), "EBITDA"),
    (re.compile(r"\bebit\s*da\b", re.IGNORECASE), "EBITDA"),
    (re.compile(r"\bg\s*s\s*t\b", re.IGNORECASE), "GST"),
    (re.compile(r"\bt\s*d\s*s\b", re.IGNORECASE), "TDS"),
    (re.compile(r"\bc\s*t\s*c\b", re.IGNORECASE), "CTC"),
    (re.compile(r"\bp\s*o\b", re.IGNORECASE), "PO"),
    
    # Indian numbering mishearings
    (re.compile(r"\b(\d+(?:\.\d+)?)\s*lacs?\b", re.IGNORECASE), r"\1 lakh"),
    (re.compile(r"\b(\d+(?:\.\d+)?)\s*crs?\b", re.IGNORECASE), r"\1 crore"),
]


def apply_phonetic_corrections(transcript: str) -> str:
    """Correct frequent STT mishearings of enterprise entities and terms."""
    if not transcript:
        return ""
    text = transcript
    for pattern, replacement in PHONETIC_CORRECTIONS:
        text = pattern.sub(replacement, text)
    return text


def get_vocabulary_summary() -> dict[str, list[str]]:
    """Return dictionary of categorized enterprise vocabulary terms."""
    return {
        "companies": ENTERPRISE_COMPANIES,
        "projects": ENTERPRISE_PROJECTS,
        "executives": ENTERPRISE_EXECUTIVES,
        "acronyms": ENTERPRISE_ACRONYMS,
    }
