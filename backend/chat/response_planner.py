"""Human Response Planner & Spoken Number Formatter.

Implements Section 8 (Human Response Planner), Section 9 (Progress System),
and Section 7.7 (Spoken Numbers) of docs/NANVI_SPEC.md.

Enforces:
- Conclusion first.
- 1 to 3 short natural sentences for voice delivery.
- Zero AI clichés ('According to retrieved documents', 'As an AI', etc.).
- No table or raw chart reading.
- Conversational spoken-number formatting (e.g., 18.4 crore, 12 lakh, 4.2 million, about 14 percent).
- Non-repeating phrase pools for acknowledgements and progress speech.
"""
from __future__ import annotations

import random
import re
from typing import Any, Sequence
from pydantic import BaseModel, Field

from backend.chat.ui_dsl import UISpec, UISpecBuilder


class HumanResponsePlan(BaseModel):
    """Structured response plan tailored for dual voice and screen presentation."""
    spoken_response: str
    screen_message: str
    highlights: list[str] = Field(default_factory=list)
    suggested_actions: list[str] = Field(default_factory=list)
    sensitivity: str = "normal"  # "normal" | "sensitive" | "restricted"
    confidence_level: str = "high"  # "high" | "moderate" | "low"
    ui_specs: list[UISpec] = Field(default_factory=list)


class SpokenNumberFormatter:
    """Formats numeric values and currencies into natural spoken phrasings.

    Adheres to Indian numbering system (crores, lakhs) and international abbreviations.
    Never reads long raw digit sequences like 12,50,00,000.
    """

    @classmethod
    def format_number_value(cls, val: float, currency_symbol: str = "") -> str:
        """Convert a raw float into spoken phrase like '18.4 crore' or '12 lakh'."""
        is_inr = currency_symbol in ("₹", "rs", "inr")
        is_usd = currency_symbol in ("$", "usd")
        curr_label = " rupees" if is_inr else (" dollars" if is_usd else "")

        if is_inr:
            if val >= 10_000_000:  # 1 Crore
                crores = val / 10_000_000
                formatted = f"{crores:.1f}".rstrip("0").rstrip(".")
                return f"{formatted} crore{curr_label}"
            elif val >= 100_000:  # 1 Lakh
                lakhs = val / 100_000
                formatted = f"{lakhs:.1f}".rstrip("0").rstrip(".")
                return f"{formatted} lakh{curr_label}"
            elif val >= 1_000:
                k = val / 1_000
                formatted = f"{k:.1f}".rstrip("0").rstrip(".")
                return f"{formatted} thousand{curr_label}"
            else:
                formatted = f"{val:.0f}" if val.is_integer() else f"{val:.2f}"
                return f"{formatted}{curr_label}"

        # Standard international (USD / neutral)
        if val >= 1_000_000_000:
            billions = val / 1_000_000_000
            formatted = f"{billions:.1f}".rstrip("0").rstrip(".")
            return f"{formatted} billion{curr_label}"
        elif val >= 1_000_000:
            millions = val / 1_000_000
            formatted = f"{millions:.1f}".rstrip("0").rstrip(".")
            return f"{formatted} million{curr_label}"
        elif val >= 1_000:
            thousands = val / 1_000
            formatted = f"{thousands:.1f}".rstrip("0").rstrip(".")
            return f"{formatted} thousand{curr_label}"
        else:
            formatted = f"{val:.0f}" if val.is_integer() else f"{val:.2f}"
            return f"{formatted}{curr_label}"

    @classmethod
    def format(cls, text: str) -> str:
        """Convert all numbers, currencies, and percentages in text into natural spoken speech."""
        if not text:
            return ""

        s = text

        # 1. Rupee amounts with crore / lakh abbreviations: ₹15.5 Cr, ₹2.3L, Rs 40 Lakhs, 15 Lacs
        s = re.sub(
            r"(?:₹|rs\.?|inr)\s*(\d+(?:\.\d+)?)\s*(?:cr|crore|crores)\b",
            r"\1 crore rupees",
            s,
            flags=re.IGNORECASE,
        )
        s = re.sub(
            r"(?:₹|rs\.?|inr)\s*(\d+(?:\.\d+)?)\s*(?:l|lac|lacs|lakh|lakhs)\b",
            r"\1 lakh rupees",
            s,
            flags=re.IGNORECASE,
        )

        # 2. Dollar amounts with B / M / K: $4.2M, $100K, $5B
        s = re.sub(
            r"\$\s*(\d+(?:\.\d+)?)\s*b(?:illion)?\b",
            r"\1 billion dollars",
            s,
            flags=re.IGNORECASE,
        )
        s = re.sub(
            r"\$\s*(\d+(?:\.\d+)?)\s*m(?:illion)?\b",
            r"\1 million dollars",
            s,
            flags=re.IGNORECASE,
        )
        s = re.sub(
            r"\$\s*(\d+(?:\.\d+)?)\s*k(?: thousand)?\b",
            r"\1 thousand dollars",
            s,
            flags=re.IGNORECASE,
        )

        # 3. Formatted Rupee numbers with commas (e.g. ₹18,40,00,000 or ₹12,00,000)
        def _replace_inr_digits(m: re.Match) -> str:
            raw_str = m.group(1).replace(",", "").strip()
            try:
                val = float(raw_str)
                return cls.format_number_value(val, currency_symbol="₹")
            except ValueError:
                return m.group(0)

        s = re.sub(r"(?:₹|rs\.?|inr)\s*(\d{1,3}(?:,\d{2,3})*(?:\.\d+)?)\b", _replace_inr_digits, s, flags=re.IGNORECASE)

        # 4. Formatted Dollar numbers with commas (e.g. $4,200,000)
        def _replace_usd_digits(m: re.Match) -> str:
            raw_str = m.group(1).replace(",", "").strip()
            try:
                val = float(raw_str)
                return cls.format_number_value(val, currency_symbol="$")
            except ValueError:
                return m.group(0)

        s = re.sub(r"\$\s*(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\b", _replace_usd_digits, s)

        # 5. Percentages (e.g. 14.2% -> about 14 percent, 14% -> 14 percent)
        def _replace_percentage(m: re.Match) -> str:
            pct_str = m.group(1)
            try:
                pct = float(pct_str)
                if pct.is_integer():
                    return f"{int(pct)} percent"
                # If rounded close to integer, say "about X percent"
                rounded = round(pct)
                if abs(pct - rounded) < 0.3:
                    return f"about {rounded} percent"
                return f"{pct:.1f} percent"
            except ValueError:
                return f"{pct_str} percent"

        s = re.sub(r"(\d+(?:\.\d+)?)\s*%", _replace_percentage, s)

        # 6. Large unadorned digit strings (e.g. 12500000 or 150000)
        def _replace_raw_large_number(m: re.Match) -> str:
            raw_str = m.group(1).replace(",", "")
            # Preserve 4-digit calendar years between 1900 and 2099
            if len(raw_str) == 4 and raw_str.startswith(("19", "20")):
                return raw_str
            try:
                val = float(raw_str)
                if val >= 100_000:
                    return cls.format_number_value(val)
                return m.group(0)
            except ValueError:
                return m.group(0)

        s = re.sub(r"\b(\d{1,3}(?:,\d{2,3})+|\d{5,})\b", _replace_raw_large_number, s)

        # 7. Common enterprise abbreviations expanded for clear pronunciation
        s = re.sub(r"\bQ([1-4])\b", r"Quarter \1", s)
        s = re.sub(r"\bFY\s*(\d{2,4})\b", r"Fiscal Year \1", s, flags=re.IGNORECASE)
        s = re.sub(r"\bMoM\b", "month over month", s, flags=re.IGNORECASE)
        s = re.sub(r"\bYoY\b", "year over year", s, flags=re.IGNORECASE)
        s = re.sub(r"\be\.g\b\.?,?\s*", "for example, ", s, flags=re.IGNORECASE)
        s = re.sub(r"\bi\.e\b\.?,?\s*", "that is, ", s, flags=re.IGNORECASE)

        return s


class PhrasePool:
    """Phrase pool ensuring operational acknowledgements and progress speech never repeat identically back to back."""

    POOLS: dict[str, list[str]] = {
        "KNOWLEDGE_SEARCH": [
            "Checking the company files now.",
            "Searching through authorized documents.",
            "Looking into the latest company records.",
            "Reviewing internal files.",
        ],
        "SQL_QUERY": [
            "Querying the database now.",
            "Looking up the database records.",
            "Pulling the latest figures from the database.",
            "Accessing structured records.",
        ],
        "EMAIL_SEARCH": [
            "Checking your company mailbox.",
            "Scanning authorized email threads.",
            "Looking through relevant messages.",
            "Reviewing email correspondence.",
        ],
        "WEB_SEARCH": [
            "Checking online sources for recent information.",
            "Searching external records.",
            "Looking up current references.",
        ],
        "INTERMEDIATE_UPDATE": [
            "I found a few matches. Narrowing them down.",
            "Analyzing the records now.",
            "Verifying the details with our sources.",
            "Synthesizing the verified information.",
        ],
        "GENERAL_ACK": [
            "Looking that up for you.",
            "Give me a moment, checking on that.",
            "One moment, pulling that together.",
            "Checking our systems now.",
        ],
    }

    def __init__(self) -> None:
        self._last_used: dict[str, str] = {}

    def get_phrase(self, category: str) -> str:
        """Get an acknowledgement or progress phrase that is guaranteed not to repeat the previous phrase."""
        pool = self.POOLS.get(category, self.POOLS["GENERAL_ACK"])
        last = self._last_used.get(category)
        candidates = [p for p in pool if p != last]
        chosen = random.choice(candidates) if candidates else pool[0]
        self._last_used[category] = chosen
        return chosen


class HumanResponsePlanner:
    """Transforms raw agent output and retrieved evidence into high-quality humanized voice responses."""

    DISCLAIMER_PATTERNS = [
        r"^According to the (?:retrieved|provided|attached)?\s*(?:documents?|files?|context|records?|data)[,\s]*",
        r"^Based on (?:the|our)\s*(?:retrieved|provided|attached)?\s*(?:documents?|files?|context|records?|data)[,\s]*",
        r"^As an AI(?: language model)?[,\s]*",
        r"^I am an AI assistant[,\s]*",
        r"^In summary,?\s*",
        r"^To summarize,?\s*",
        r"^Here is the (?:information|breakdown|summary)[,\s]*:?\s*",
    ]

    def __init__(self) -> None:
        self.phrase_pool = PhrasePool()

    def plan_response(
        self,
        answer: str,
        query: str,
        sources: Sequence[Any] = (),
        verbosity_preference: str = "normal",
        capability: str = "",
        privacy_mode: bool = False,
        language: str = "auto",
    ) -> HumanResponsePlan:
        """Formulate conclusion-first spoken response, screen message, highlights, and suggested actions."""
        if not answer or not answer.strip():
            return HumanResponsePlan(
                spoken_response="I couldn't find relevant records for that query.",
                screen_message="No matching records found in authorized data.",
                highlights=[],
                suggested_actions=["search_again", "browse_documents"],
                sensitivity="normal",
                confidence_level="low",
                ui_specs=[],
            )

        # 1. Clean markdown elements that should never be spoken
        cleaned = answer.strip()
        # Remove code blocks
        cleaned = re.sub(r"```[\s\S]*?```", "", cleaned)
        cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)
        # Remove markdown tables
        cleaned = re.sub(r"(\|.*\|\n?)+", "", cleaned)
        # Remove citations [1], [ref-1], [Source 2]
        cleaned = re.sub(r"\[(?:ref|source|\d+|file|doc)[^\]]*\]", "", cleaned, flags=re.IGNORECASE)
        # Convert markdown links [title](url) to title
        cleaned = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", cleaned)
        cleaned = re.sub(r"https?://\S+", "", cleaned)
        # Remove markdown headers
        cleaned = re.sub(r"^#{1,6}\s*", "", cleaned, flags=re.MULTILINE)
        # Remove bullet points
        cleaned = re.sub(r"^[\*\-•\◦\▪\▫\+]\s*", "", cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r"^\d+[\.\)]\s*", "", cleaned, flags=re.MULTILINE)

        # 2. Split into candidate sentences and clean each sentence
        raw_sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", cleaned) if s.strip()]
        filtered_sentences: list[str] = []

        for s in raw_sentences:
            sentence_clean = s.strip()
            for pat in self.DISCLAIMER_PATTERNS:
                sentence_clean = re.sub(pat, "", sentence_clean, flags=re.IGNORECASE).strip()
            # Skip empty or pure AI meta-commentary sentences
            if not sentence_clean or len(sentence_clean) < 4:
                continue
            if re.search(r"\b(?:as an ai|language model|retrieved documents?|provided context|my knowledge cutoff)\b", sentence_clean, re.IGNORECASE):
                continue
            # Ensure capitalized first letter
            sentence_clean = sentence_clean[0].upper() + sentence_clean[1:]
            filtered_sentences.append(sentence_clean)

        if not filtered_sentences:
            filtered_sentences = [cleaned[0].upper() + cleaned[1:]] if cleaned else ["Here is the requested information."]

        # 3. Enforce conclusion first and adapt verbosity
        max_sentences = 2
        if verbosity_preference in ("long", "tell_me_more", "detailed"):
            max_sentences = 4
        elif verbosity_preference in ("short", "concise"):
            max_sentences = 1

        selected_sentences = filtered_sentences[:max_sentences]
        spoken_core = " ".join(selected_sentences).strip()

        # 4. Format numbers for speech (crore, lakh, percent, dollars)
        spoken_response = SpokenNumberFormatter.format(spoken_core)

        # 5. Honest uncertainty check
        low_confidence_cues = ["not entirely sure", "could not confirm", "no direct mention", "partial information", "approximate"]
        confidence_level = "high"
        if any(c in spoken_response.lower() for c in low_confidence_cues):
            confidence_level = "moderate"
            if not spoken_response.lower().startswith(("i think", "i'm not fully sure")):
                spoken_response = f"I'm not fully sure, but {spoken_response[0].lower()}{spoken_response[1:]}"

        # 6. Sensitivity & Privacy Mode classification (Section 12 of NANVI_SPEC)
        sensitivity = "normal"
        sensitive_patterns = [
            r"\b(?:salary|compensation|ctc|annual pay|monthly pay|base pay|bonus)\b",
            r"\b(?:ssn|pan|aadhaar|passport|bank account|account number|password|secret|api_key|credentials)\b",
        ]
        is_sensitive_query = any(re.search(pat, query, re.IGNORECASE) for pat in sensitive_patterns)
        is_sensitive_answer = any(re.search(pat, answer, re.IGNORECASE) for pat in sensitive_patterns)

        if is_sensitive_query or is_sensitive_answer:
            sensitivity = "sensitive"

        # Privacy mode: sensitive values (salary, personal data) appear on screen and are not spoken.
        # Nanvi says "I've put it on screen."
        if privacy_mode or (sensitivity == "sensitive" and (is_sensitive_query or re.search(r"(?:₹|\$|rs\.?|inr|usd|\d+[\d,]*\s*(?:lakh|crore|k|m|lpa))\b", answer, re.IGNORECASE))):
            spoken_response = "I've put it on screen."
            screen_message = "Confidential details displayed on screen for privacy."
        else:
            # 7. Formulate Screen Message & Highlights
            has_table_or_details = "|" in answer or len(raw_sentences) > len(selected_sentences) or len(sources) > 0
            if has_table_or_details:
                screen_message = "I've displayed the full verified breakdown and citations on your screen."
            else:
                screen_message = "Verified response displayed above."

        # Extract entity/metric highlights
        highlights: list[str] = []
        metrics = re.findall(r"\b(?:\d+(?:\.\d+)?%|\$\d+(?:\.\d+)?[BMKbmk]?|₹\d+(?:,\d+)*(?:\.\d+)?)\b", answer)
        highlights.extend(metrics[:3])

        # 8. Formulate Suggested Actions
        suggested_actions = self._generate_suggested_actions(query, answer)

        # 9. Controlled UI Specs
        ui_specs = UISpecBuilder.build_specs(
            query=query,
            answer=answer,
            capability=capability,
            sources=sources,
            suggested_actions=suggested_actions,
            highlights=highlights,
        )

        return HumanResponsePlan(
            spoken_response=spoken_response,
            screen_message=screen_message,
            highlights=highlights,
            suggested_actions=suggested_actions,
            sensitivity=sensitivity,
            confidence_level=confidence_level,
            ui_specs=ui_specs,
        )

    @classmethod
    def create_clarification_plan(
        cls,
        query: str = "",
        suggestions: list[str] | None = None,
        reason: str = "low_confidence",
    ) -> HumanResponsePlan:
        """Create a structured clarification plan when STT or intent confidence is low."""
        actions = suggestions or ["Check Revenue", "Search Files", "Draft Email"]
        spoken = "I didn't quite catch that. Please can you repeat the sentence?"
        if reason == "ambiguous":
            spoken = "Please can you repeat the sentence?"

        from backend.chat.ui_dsl import ActionCardData, ActionItem, UICardType, UISpec
        action_data = ActionCardData(
            title="Suggested Next Steps",
            actions=[
                ActionItem(
                    label=act,
                    intent=act.lower().replace(" ", "_"),
                    variant="primary" if idx == 0 else "secondary",
                )
                for idx, act in enumerate(actions[:3])
            ],
        )
        action_spec = UISpec(
            card_type=UICardType.ACTION_CARD,
            priority=0,
            data=action_data.model_dump(),
        )

        return HumanResponsePlan(
            spoken_response=spoken,
            screen_message="Please can you repeat the sentence?",
            highlights=[],
            suggested_actions=[act.lower().replace(" ", "_") for act in actions[:3]],
            sensitivity="normal",
            confidence_level="low",
            ui_specs=[action_spec],
        )

    def _generate_suggested_actions(self, query: str, answer: str) -> list[str]:
        """Derive 2-3 logical conversational follow-up action intents."""
        q_lower = query.lower()
        actions: list[str] = []

        if any(k in q_lower for k in ("revenue", "sales", "earnings", "profit", "finance")):
            actions.extend(["compare_previous_quarter", "revenue_drivers", "top_customers"])
        elif any(k in q_lower for k in ("customer", "client", "account")):
            actions.extend(["customer_invoices", "contact_details", "compare_accounts"])
        elif any(k in q_lower for k in ("invoice", "bill", "payment", "po")):
            actions.extend(["download_invoice", "view_line_items", "payment_status"])
        elif any(k in q_lower for k in ("employee", "team", "cto", "cfo", "reports to")):
            actions.extend(["view_org_chart", "contact_info", "team_projects"])
        elif any(k in q_lower for k in ("email", "mail", "draft", "message")):
            actions.extend(["review_draft", "send_confirmation", "find_replies"])
        else:
            actions.extend(["show_more_detail", "verify_sources", "export_summary"])

        return actions[:3]


# Singleton instance
human_response_planner = HumanResponsePlanner()
