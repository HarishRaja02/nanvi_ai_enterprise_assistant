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


from backend.chat.speech_normalizer import normalize_for_speech


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
                rounded = round(pct)
                if abs(pct - rounded) < 0.3:
                    return f"about {rounded} percent"
                return f"{pct:.1f} percent"
            except ValueError:
                return f"{pct_str} percent"

        s = re.sub(r"(\d+(?:\.\d+)?)\s*%", _replace_percentage, s)

        # 6. Conversational expansions & year preservation
        s = re.sub(r"\bYoY\b", "year over year", s)
        s = re.sub(r"\bQoQ\b", "quarter over quarter", s)
        s = re.sub(r"\bFY\s*(\d{2,4})\b", r"Fiscal Year \1", s)

        return s


class PhrasePool:
    """Phrase pool ensuring operational acknowledgements and progress speech never repeat identically back to back."""

    POOLS: dict[str, list[str]] = {
        "KNOWLEDGE_SEARCH": [
            "Sure, I'm checking that.",
            "One moment, finding those documents.",
            "Okay, let me look that up.",
            "Checking that now.",
        ],
        "SQL_QUERY": [
            "Sure, give me a second.",
            "Okay, checking the records now.",
            "Let me look that up for you.",
            "One moment, pulling that up.",
        ],
        "EMAIL_SEARCH": [
            "Sure, checking your messages now.",
            "One moment, looking through the emails.",
            "Checking that email now.",
            "Let me check your inbox.",
        ],
        "WEB_SEARCH": [
            "One moment, checking online.",
            "Looking that up now.",
            "Sure, checking current information.",
        ],
        "INTERMEDIATE_UPDATE": [
            "I found a few matches. Narrowing them down.",
            "Checking the details now.",
            "Pulling together the verified information.",
        ],
        "GENERAL_ACK": [
            "Sure, give me a second.",
            "Okay, I'm checking that now.",
            "One moment, let me look that up.",
            "Looking that up for you.",
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
        r"^Sure,?\s*I can help you with that[.,!]*\s*",
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
                spoken_response="I couldn't find matching records for that request.",
                screen_message="No matching records found in authorized data.",
                highlights=[],
                suggested_actions=["search_again", "browse_documents"],
                sensitivity="normal",
                confidence_level="low",
                ui_specs=[],
            )

        cleaned = answer.strip()

        # 1. Clean markdown and technical syntax
        cleaned = re.sub(r"```[\s\S]*?```", "", cleaned)
        cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)
        cleaned = re.sub(r"(\|.*\|\n?)+", "", cleaned)
        cleaned = re.sub(r"\[(?:ref|source|\d+|file|doc)[^\]]*\]", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", cleaned)
        cleaned = re.sub(r"https?://\S+", "", cleaned)
        cleaned = re.sub(r"^#{1,6}\s*", "", cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r"^[\*\-•\◦\▪\▫\+]\s*", "", cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r"^\d+[\.\)]\s*", "", cleaned, flags=re.MULTILINE)

        # Strip email headers from general text early so they are never spoken aloud
        cleaned = re.sub(r"^(?:From|To|Subject|Date|Cc|Bcc):[^\n]*\n?", "", cleaned, flags=re.IGNORECASE | re.MULTILINE)

        # 2. Email-specific natural conversational formulation (Master Prompt Section 7)
        is_email = capability == "email" or bool(re.search(r"(?:\bFrom:\s*|\bSubject:\s*|\bDear\s+[A-Z]|\bHi\s+[A-Z])", answer, re.IGNORECASE))
        read_whole_email = bool(re.search(r"\b(?:read\s+(?:the\s+)?(?:(?:whole|full|entire)\s+)?email)\b", query, re.IGNORECASE))

        if is_email:
            if read_whole_email:
                # Natural reading with greeting and body
                greeting_m = re.search(r"\b((?:Hi|Hello|Dear)\s+[^,\n]+[,!])", answer)
                greeting = greeting_m.group(1) if greeting_m else ""
                body_clean = re.sub(r"^(?:From|To|Subject|Date):[^\n]*\n?", "", cleaned, flags=re.IGNORECASE | re.MULTILINE)
                body_clean = re.sub(r"^[\*\#_`~|]", "", body_clean).strip()
                if greeting and body_clean.startswith(greeting):
                    body_clean = body_clean[len(greeting):].strip()
                spoken_email = f"I found the email. It starts with, '{greeting or 'Hi'}' {body_clean}" if greeting else f"I found the email: {body_clean}"
                spoken_response = normalize_for_speech(spoken_email[:600])
                return HumanResponsePlan(
                    spoken_response=spoken_response,
                    screen_message="Full email displayed on screen.",
                    highlights=["Email thread"],
                    suggested_actions=["reply_email", "forward_email"],
                    sensitivity="normal",
                    confidence_level="high",
                    ui_specs=[],
                )
            else:
                # Short spoken email summary
                first_lines = [l.strip() for l in cleaned.splitlines() if l.strip() and not l.lower().startswith(("from:", "to:", "subject:", "date:"))]
                summary_text = first_lines[0] if first_lines else "the details are in your mailbox"
                for pat in self.DISCLAIMER_PATTERNS:
                    summary_text = re.sub(pat, "", summary_text, flags=re.IGNORECASE).strip()
                spoken_response = f"I found the email. The main point is that {summary_text[0].lower() + summary_text[1:]}"
                spoken_response = normalize_for_speech(spoken_response)
                return HumanResponsePlan(
                    spoken_response=spoken_response,
                    screen_message="Email summary displayed above.",
                    highlights=["Email message"],
                    suggested_actions=["read_whole_email", "reply_email"],
                    sensitivity="normal",
                    confidence_level="high",
                    ui_specs=[],
                )

        # 3. Split into candidate sentences and clean each sentence
        raw_sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", cleaned) if s.strip()]
        filtered_sentences: list[str] = []

        for s in raw_sentences:
            sentence_clean = s.strip()
            for pat in self.DISCLAIMER_PATTERNS:
                sentence_clean = re.sub(pat, "", sentence_clean, flags=re.IGNORECASE).strip()
            if not sentence_clean or len(sentence_clean) < 4:
                continue
            if re.search(r"\b(?:as an ai|language model|retrieved documents?|provided context|my knowledge cutoff|rag agent|sql agent|vector database)\b", sentence_clean, re.IGNORECASE):
                continue
            sentence_clean = sentence_clean[0].upper() + sentence_clean[1:]
            filtered_sentences.append(sentence_clean)

        if not filtered_sentences:
            filtered_sentences = [cleaned[0].upper() + cleaned[1:]] if cleaned else ["Here is the information."]

        # 4. Long Responses Handling (Master Prompt Section 8)
        # Never dump a huge answer through voice
        max_sentences = 2
        if verbosity_preference in ("long", "tell_me_more", "detailed"):
            max_sentences = 4
        elif verbosity_preference in ("short", "concise"):
            max_sentences = 1

        if len(filtered_sentences) > 4 and verbosity_preference == "normal":
            # 1. Short spoken summary, 2. Offer key points, 3. Invite user for details
            summary_point = filtered_sentences[0]
            second_point = filtered_sentences[1]
            spoken_core = f"{summary_point} {second_point} I can read the remaining details if you'd like."
        else:
            selected_sentences = filtered_sentences[:max_sentences]
            spoken_core = " ".join(selected_sentences).strip()

        # 5. Format numbers and IDs for speech using speech normalizer
        spoken_response = normalize_for_speech(spoken_core)

        # 6. Honest uncertainty check
        low_confidence_cues = ["not entirely sure", "could not confirm", "no direct mention", "partial information", "approximate"]
        confidence_level = "high"
        if any(c in spoken_response.lower() for c in low_confidence_cues):
            confidence_level = "moderate"
            if not spoken_response.lower().startswith(("i think", "i'm not fully sure")):
                spoken_response = f"I'm not fully sure, but {spoken_response[0].lower()}{spoken_response[1:]}"

        # 7. Sensitivity & Privacy Mode classification
        sensitivity = "normal"
        credential_patterns = [
            r"\b(?:password|secret|api_key|credentials|aadhaar|ssn|bank account|account number)\b",
        ]
        is_credential = any(re.search(pat, answer, re.IGNORECASE) for pat in credential_patterns)
        if is_credential:
            sensitivity = "restricted"

        # Privacy mode: sensitive details appear on screen and are not spoken.
        if privacy_mode or (is_credential and "salary" not in query.lower()):
            spoken_response = "I've put it on screen."
            screen_message = "Confidential details displayed on screen for privacy."
        else:
            has_table_or_details = "|" in answer or len(raw_sentences) > len(filtered_sentences[:max_sentences]) or len(sources) > 0
            if has_table_or_details:
                screen_message = "I've displayed the full verified details and records on your screen."
            else:
                screen_message = "Verified response displayed above."

        # Extract entity/metric highlights
        highlights: list[str] = []
        metrics = re.findall(r"\b(?:\d+(?:\.\d+)?%|\$\d+(?:\.\d+)?[BMKbmk]?|₹\d+(?:,\d+)*(?:\.\d+)?)\b", answer)
        highlights.extend(metrics[:3])

        # 8. Suggested Actions & UI Specs
        suggested_actions = self._generate_suggested_actions(query, answer)
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
