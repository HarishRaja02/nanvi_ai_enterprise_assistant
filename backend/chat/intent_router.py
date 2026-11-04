"""Intent Classification and Routing Layer for Nanvi AI Assistant.

Ensures the assistant does not get distracted by file retrieval or database
lookups when the user is engaging in normal conversation or inquiring about
the company from its institutional memory. Decides whether the user's intent is:
1. CONVERSATION: Greetings, conversational chat, ChatGPT-style assistance,
   brainstorming, or inquiries about the company's background/mission/policies.
2. FILE_OR_DATA_QUERY: Requests to search, retrieve, extract, query, or export
   specific enterprise files, documents, database records, emails, or reports.
"""
from __future__ import annotations

import enum
import logging
import re
from typing import Sequence
from backend.chat.models import ChatMessage

logger = logging.getLogger(__name__)


class ChatIntent(str, enum.Enum):
    CONVERSATION = "conversation"
    FILE_OR_DATA_QUERY = "file_or_data_query"


class IntentDecision:
    def __init__(self, intent: ChatIntent, confidence: float, reason: str, suggested_action: str = "") -> None:
        self.intent = intent
        self.confidence = confidence
        self.reason = reason
        self.suggested_action = suggested_action

    def __repr__(self) -> str:
        return f"<IntentDecision intent={self.intent.value} confidence={self.confidence:.2f} reason='{self.reason}'>"


class IntentRouter:
    """Decides if the turn is a conversational chat or an enterprise file/data query."""

    _GREETINGS = frozenset({
        "hi", "hello", "hey", "hola", "namaste", "howdy", "sup", "yo",
        "good morning", "good afternoon", "good evening", "good day",
        "greetings", "hi nanvi", "hello nanvi", "hey nanvi",
        "thanks", "thank you", "thx", "appreciate it", "cheers",
        "ok", "okay", "alright", "got it", "cool", "great", "nice",
        "bye", "goodbye", "see you", "cya", "take care",
    })

    _CONVERSATIONAL_COMPANY_PHRASES = (
        "what does our company do", "what do we do", "about our company",
        "tell me about the company", "tell me about our company", "about this company",
        "who is our ceo", "who is the ceo", "who is our founder", "who founded",
        "our mission", "what is our mission", "our vision", "what is our vision",
        "our values", "what are our values", "company background", "company profile",
        "company overview", "company details", "what services do we provide",
        "what products do we offer", "what do we sell", "what is our business",
        "tell me about yourself", "who are you", "what can you do", "what are you",
        "how can you help me", "introduce yourself", "how are you", "how are you doing",
    )

    _CONVERSATIONAL_PROMPTS = (
        "help me write", "help me draft", "can you write", "give me advice",
        "how do i", "explain to me", "can you explain", "summarize what we",
        "tell me a joke", "brainstorm", "give me some ideas", "suggest some",
        "what is the difference between", "what do you think", "can we chat",
        "how does", "why is", "what is",
    )

    _EXPLICIT_FILE_PATTERNS = (
        # File extensions
        r"\b[\w-]+\.(?:pdf|docx|xlsx|csv|pptx|txt|json|xml|md|markdown|log|html|htm)\b",
        # Document and invoice identification codes (e.g. INV-2026-0042, INV-00022, invoice_022, EMP-0001, NDA-0001)
        r"\b(?:inv|emp|nda|pur|po|prj|cust|cnt|doc|bill)[-_ ]?\d{1,8}\b",
        r"\binv[-_ ]?\d{4}[-_ ]?\d+\b",
        r"\binvoice[-_ ]?\d+\b",
        # Direct document action prompts (e.g. "just give the open option for that file", "show it", "download the full pdf")
        r"\b(?:open\s+option|give\s+the\s+open|show\s+(?:the\s+)?file|open\s+(?:the\s+)?file|download\s+(?:the\s+)?(?:full\s+)?pdf|open\s+it|show\s+it)\b",
        # Explicit sources
        r"\b(?:in|from|on)\s+(?:local\s+storage|local\s+files?|local\s+folder|internal\s+repository|internal\s+storage|repository|database|local\s+database|db|emails?|inbox|gmail|google\s+drive|gdrive|cloud(?:\s+storage)?)\b",
        # Storage keywords
        r"\b(?:local\s+storage|internal\s+repository|internal\s+storage|google\s+drive|gdrive|database\s+record|db\s+records?|c:\\)\b",
        # Folder queries
        r"\b(?:what\s+files|what\s+documents|what\s+is\s+in|what\s+is\s+inside|files\s+in|documents\s+in|contents\s+of)\s+(?:my\s+|the\s+)?(?:folder|folders|directory)\b",
        r"\b(?:my\s+folder|connected\s+folder|selected\s+folder|local\s+folder|approved\s+folder)\b",
        # Explicit file actions
        r"\b(?:check|find|search|locate|look\s+for|where\s+is|fetch)\s+(?:the\s+)?(?:file|files|document|documents|pdf|sheet|spreadsheet|invoice|invoices|contract|contracts|resume|resumes|emails?|records)\b",
        r"\b(?:list|show|browse)\s+(?:all\s+)?(?:files|documents|folders?|invoices|contracts|records|emails?)\b",
        # Email directives
        r"\b(?:recent|latest|unread|top\s+\d+|check|show|get|fetch|list|search|find|view|read)\s+(?:my\s+)?(?:emails?|gmail|inbox|messages?|mails?)\b",
        r"\b(?:recent\s+emails?|top\s+\d+\s+emails?)\b",
        # Explicit report generation / export
        r"\b(?:export|download|generate)\s+(?:report|document|schedule|as\s+pdf|as\s+excel|as\s+word|as\s+docx)\b",
        # SQL and DB execution
        r"\b(?:sql|query\s+database|select\s+\*|table\s+rows?|database\s+table)\b",
    )

    _ENTERPRISE_KEYWORDS_PATTERN = (
        r"\b("
        r"project|projects|invoice|invoices|inv|contract|contracts|customer|customers|"
        r"employee|employees|database|record|records|ledger|file|files|document|documents|"
        r"balance|salary|salaries|email|emails|gmail|inbox|mail|message|messages|nda|pur|emp|po|prj|"
        r"sales|revenue|profit|cost|margin|analysis|analytics|total|sum|average|metric|metrics|kpi|"
        r"vendor|vendors|billing|bill|bills|receipt|receipts|report|reports|atlas|chennai"
        r")\b"
    )

    @classmethod
    def classify(cls, query: str, history: Sequence[ChatMessage] | None = None) -> IntentDecision:
        """Classify user intent into CONVERSATION or FILE_OR_DATA_QUERY."""
        q_raw = query.strip()
        q_lower = q_raw.casefold()
        q_clean = re.sub(r"[^\w\s]", "", q_lower)
        q_clean = re.sub(r"\s+", " ", q_clean).strip()

        # 1. Check for pure greetings and pleasantries
        if q_clean in cls._GREETINGS:
            return IntentDecision(
                ChatIntent.CONVERSATION,
                confidence=0.98,
                reason=f"Standard conversational greeting or pleasantry ('{q_clean}')",
                suggested_action="chatgpt_conversational_response",
            )

        # 2. Check for short greeting tokens (e.g. "hi there", "hello assistant")
        tokens = q_clean.split()
        if len(tokens) <= 3 and tokens[0] in ("hi", "hello", "hey", "hola", "namaste", "howdy", "sup", "yo"):
            if not any(cls._matches_any_file_pattern(q_lower)):
                return IntentDecision(
                    ChatIntent.CONVERSATION,
                    confidence=0.95,
                    reason="Short greeting phrase without file search directives",
                    suggested_action="chatgpt_conversational_response",
                )

        # 3. Check for company memory inquiries (about the company, mission, founder, products)
        if any(phrase in q_clean for phrase in cls._CONVERSATIONAL_COMPANY_PHRASES):
            return IntentDecision(
                ChatIntent.CONVERSATION,
                confidence=0.95,
                reason="Question targets company identity, mission, products, or memory",
                suggested_action="company_memory_conversational_response",
            )

        # 4. Check for explicit file, document, or database indicators
        matched_file_patterns = [p for p in cls._EXPLICIT_FILE_PATTERNS if re.search(p, q_lower)]
        if matched_file_patterns:
            return IntentDecision(
                ChatIntent.FILE_OR_DATA_QUERY,
                confidence=0.95,
                reason=f"Matched explicit file/data pattern ({len(matched_file_patterns)} matches)",
                suggested_action="execute_file_or_data_pipeline",
            )

        # 5. Check if query asks for specific business entities combined with search/list/find verbs
        has_action_verb = bool(re.search(r"\b(check|find|search|show|get|list|look\s+for|locate|where\s+is|fetch|pull|read|display|give\s+me|give)\b", q_lower))
        has_file_noun = bool(re.search(r"\b(file|files|document|documents|pdf|docx|xlsx|csv|attachment|folder|directory|email|emails|mail|mails|message|messages|inbox)\b", q_lower))
        if has_action_verb and has_file_noun:
            return IntentDecision(
                ChatIntent.FILE_OR_DATA_QUERY,
                confidence=0.90,
                reason="Query combines search action verb with file/document noun",
                suggested_action="execute_file_or_data_pipeline",
            )

        # 6. Check if user is asking for general conversational assistance or advice (ChatGPT style)
        if any(q_lower.startswith(prefix) for prefix in cls._CONVERSATIONAL_PROMPTS) and not re.search(cls._ENTERPRISE_KEYWORDS_PATTERN, q_lower):
            return IntentDecision(
                ChatIntent.CONVERSATION,
                confidence=0.88,
                reason="User is seeking conversational advice, explanation, or ChatGPT-style assistance",
                suggested_action="chatgpt_conversational_response",
            )

        # 7. Check if query is conversational general Q&A (e.g. "what is artificial intelligence", "can you tell me a story")
        if not re.search(cls._ENTERPRISE_KEYWORDS_PATTERN, q_lower):
            # No enterprise data keywords present
            return IntentDecision(
                ChatIntent.CONVERSATION,
                confidence=0.80,
                reason="General conversation without enterprise data or file targets",
                suggested_action="chatgpt_conversational_response",
            )
            # No enterprise data keywords present
            return IntentDecision(
                ChatIntent.CONVERSATION,
                confidence=0.80,
                reason="General conversation without enterprise data or file targets",
                suggested_action="chatgpt_conversational_response",
            )

        # 8. Enterprise queries (e.g. "tell me about project atlas", "what is project atlas", "status of invoice 2")
        # Route to enterprise data and knowledge orchestrator
        return IntentDecision(
            ChatIntent.FILE_OR_DATA_QUERY,
            confidence=0.85,
            reason="Contains business keywords; routing to enterprise data pipeline",
            suggested_action="execute_file_or_data_pipeline",
        )

        # Default fallback: focused file or data retrieval
        return IntentDecision(
            ChatIntent.FILE_OR_DATA_QUERY,
            confidence=0.65,
            reason="Contains business keywords; routing to enterprise data pipeline",
            suggested_action="execute_file_or_data_pipeline",
        )

    @classmethod
    def _matches_any_file_pattern(cls, text: str) -> list[str]:
        return [p for p in cls._EXPLICIT_FILE_PATTERNS if re.search(p, text)]


intent_router = IntentRouter()
