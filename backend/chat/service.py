from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone

from backend.security.ai.context import PromptContext, PromptContextBuilder
from uuid import uuid4

from backend.agents.models import AgentRequest, AgentResponse, Capability, OrchestrationState
from backend.agents.orchestrator import EnterpriseOrchestrator
from backend.security.authorization import UserAttributes
from backend.security.validation import validate_non_empty
from backend.observability.logging import get_request_id, log_event
import logging
import re
import time
from typing import Sequence

logger = logging.getLogger(__name__)

from .models import ChatMessage, ChatRequest, ChatResponse, ConversationSummary

class ConversationStore(ABC):
    @abstractmethod
    def append(self, conversation_id: str, message: ChatMessage) -> None: ...
    @abstractmethod
    def get(self, conversation_id: str) -> tuple[ChatMessage, ...]: ...
    @abstractmethod
    def list_for_user(self, user_id: str, tenant_id: str) -> tuple[ConversationSummary, ...]: ...
    @abstractmethod
    def bind_owner(self, conversation_id: str, user_id: str, tenant_id: str) -> None: ...
    @abstractmethod
    def owner(self, conversation_id: str) -> tuple[str, str] | None: ...

def generate_conversation_title(query: str) -> str:
    """Generate a clean, meaningful conversation title from the initial prompt."""
    import re
    clean = query.strip().rstrip("?.!")
    pattern = r"^(can you please |can you |could you |please |tell me |show me |what is |what are |search the web for |search online for |search for |find |check my |lookup |look up )"
    stripped = re.sub(pattern, "", clean, flags=re.IGNORECASE).strip()
    if stripped:
        clean = stripped
    words = clean.split()
    title_words = []
    lower_words = {"in", "on", "at", "for", "to", "of", "and", "or", "the", "a", "an", "with"}
    for idx, w in enumerate(words):
        if idx > 0 and w.lower() in lower_words:
            title_words.append(w.lower())
        else:
            title_words.append(w[:1].upper() + w[1:])
    result = " ".join(title_words)
    if len(result) > 42:
        result = result[:39].rsplit(" ", 1)[0] + "…"
    return result or "New Conversation"


class InMemoryConversationStore(ConversationStore):
    """Development/test conversation store. Production must use a tenant-scoped durable repository."""
    def __init__(self) -> None:
        self._messages: dict[str, list[ChatMessage]] = {}
        self._owners: dict[str, tuple[str, str]] = {}
        self._titles: dict[str, str] = {}

    def bind_owner(self, conversation_id: str, user_id: str, tenant_id: str) -> None:
        existing = self._owners.get(conversation_id)
        if existing and existing != (user_id, tenant_id):
            raise PermissionError("Conversation does not belong to the authenticated principal")
        self._owners[conversation_id] = (user_id, tenant_id)
        self._messages.setdefault(conversation_id, [])

    def owner(self, conversation_id: str):
        return self._owners.get(conversation_id)

    def append(self, conversation_id: str, message: ChatMessage) -> None:
        if conversation_id not in self._owners:
            raise PermissionError("Conversation is not bound to an authenticated principal")
        self._messages.setdefault(conversation_id, []).append(message)
        if conversation_id not in self._titles and message.role == "user" and message.content:
            self._titles[conversation_id] = generate_conversation_title(message.content)

    def get(self, conversation_id: str) -> tuple[ChatMessage, ...]:
        return tuple(self._messages.get(conversation_id, ()))

    def list_for_user(self, user_id: str, tenant_id: str) -> tuple[ConversationSummary, ...]:
        items = []
        for cid, (owner, owner_tenant) in self._owners.items():
            if owner != user_id or owner_tenant != tenant_id:
                continue
            messages = self._messages.get(cid, [])
            if messages:
                title = self._titles.get(cid)
                if not title:
                    user_msgs = [m for m in messages if m.role == "user"]
                    if user_msgs:
                        title = generate_conversation_title(user_msgs[0].content)
                        self._titles[cid] = title
                    else:
                        title = "New Conversation"
                items.append(ConversationSummary(cid, len(messages), messages[-1].created_at, title=title))
        return tuple(sorted(items, key=lambda x: x.last_message_at, reverse=True))

class ChatAnswerer(ABC):
    @abstractmethod
    def answer(self, context: PromptContext) -> str: ...

class DeterministicTestAnswerer(ChatAnswerer):
    """Test-only answerer. It deliberately does not pretend to be a production LLM."""
    _GREETINGS = frozenset({
        "hi", "hello", "hey", "hola", "namaste",
        "good morning", "good afternoon", "good evening",
        "greetings", "help", "who are you", "what can you do",
        "what are you", "how are you", "hi nanvi", "hello nanvi",
    })

    def answer(self, context: PromptContext) -> str:
        query_norm = context.user.value.strip().casefold().rstrip("!?.,")
        if query_norm in self._GREETINGS:
            return "Hello! I'm Nanvi, your enterprise assistant. Ask me about company files, email, operational data, or reports you're authorized to access."
        if not context.retrieved and not context.tool_results:
            return "I couldn't find any authorized information matching your request."
        parts: list[str] = []
        for item in context.retrieved:
            parts.append(item.value)
        for item in context.tool_results:
            content = item.value
            if hasattr(content, "explanation") and content.explanation:
                parts.append(str(content.explanation))
            elif hasattr(content, "columns") and hasattr(content, "rows") and content.columns:
                if content.rows:
                    headers = " | ".join(str(c) for c in content.columns)
                    sep = " | ".join("---" for _ in content.columns)
                    row_lines = [" | ".join(str(val) for val in row) for row in content.rows]
                    table_str = f"| {headers} |\n| {sep} |\n" + "\n".join(f"| {r} |" for r in row_lines)
                    parts.append(table_str)
                else:
                    parts.append("Database: No matching records found.")
            else:
                parts.append(str(content))
        return "\n\n".join(parts)

class ChatService:
    def __init__(self, orchestrator: EnterpriseOrchestrator, answerer: ChatAnswerer, store: ConversationStore) -> None:
        self._orchestrator = orchestrator
        self._answerer = answerer
        self._store = store
        self._prompt_context = PromptContextBuilder()

    def ask(self, user: UserAttributes, request: ChatRequest) -> ChatResponse:
        query = validate_non_empty(request.query, "query", 4000)
        conversation_id = request.conversation_id or uuid4().hex
        self._store.bind_owner(conversation_id, user.user_id, user.tenant_id)
        if self._store.owner(conversation_id) != (user.user_id, user.tenant_id):
            raise PermissionError("Conversation does not belong to the authenticated principal")

        # 1. Fetch prior history for this specific conversation before appending current turn
        prior_history = self._store.get(conversation_id)

        now = datetime.now(timezone.utc)
        self._store.append(conversation_id, ChatMessage("user", query, now))

        request_id = get_request_id() if get_request_id() != "-" else uuid4().hex

        # Check for conversational greeting / chitchat first (never trigger RAG or load files on greetings)
        if self._is_conversational_query(query):
            answer = self._generate_conversational_reply(query)
            self._store.append(conversation_id, ChatMessage("assistant", answer, datetime.now(timezone.utc)))
            log_event(logger, "chat_service_completed", actor_id=user.user_id, tenant_id=user.tenant_id,
                      request_id=request_id, capability="", source_count=0,
                      history_count=len(self._store.get(conversation_id)))
            return ChatResponse(
                conversation_id=conversation_id,
                answer=answer,
                sources=(),
                capability="",
                trace=("Conversational greeting handled directly",),
                history=self._store.get(conversation_id),
            )

        # 2. Contextualize query if prior history exists (resolves pronouns like "it", "they", "this" for RAG)
        effective_query = query
        from backend.retrieval.intent import classify_retrieval_intent, QueryIntent
        intent = classify_retrieval_intent(query)

        if prior_history and intent != QueryIntent.FILE_SEARCH:
            # Deterministic heuristic contextualization first to avoid unnecessary LLM calls
            heuristic_query = self._fallback_contextualize(query, prior_history)
            if heuristic_query != query:
                effective_query = heuristic_query
            elif hasattr(self._answerer, "_provider") and hasattr(self._answerer._provider, "contextualize_query"):
                # Only invoke LLM contextualization if query contains unresolved pronouns
                q_words = set(query.casefold().split())
                if q_words.intersection({"it", "its", "they", "them", "their", "this", "that"}):
                    try:
                        effective_query = self._answerer._provider.contextualize_query(query, prior_history)
                    except Exception as exc:
                        logger.warning("Query contextualization skipped: %s", exc)
                        effective_query = heuristic_query

        # 3. Route capabilities using effective query
        capabilities = self._capabilities_for_query(effective_query)
        if not getattr(request, "rag_enabled", True):
            capabilities = tuple(c for c in capabilities if c != Capability.KNOWLEDGE)
            if not capabilities:
                capabilities = (Capability.KNOWLEDGE,)

        log_event(logger, "chat_service_started", actor_id=user.user_id, tenant_id=user.tenant_id, query_length=len(query), capability_count=len(capabilities))
        responses: list[AgentResponse] = []
        traces: list[str] = []
        for capability in capabilities:
            agent_query = effective_query if capability == Capability.KNOWLEDGE else query
            agent_req = AgentRequest(request_id, user, agent_query, history=tuple(prior_history))
            state = self._orchestrator.invoke(agent_req, forced_capability=capability)
            traces.extend(state.trace)
            if state.error:
                raise RuntimeError(state.error)
            if state.response is not None:
                responses.append(state.response)

        # Dynamic fallback to Web Search:
        has_actionable_info = any(
            r.capability != Capability.KNOWLEDGE or (
                r.content and "couldn't find" not in str(r.content).lower() and r.sources
            )
            for r in responses
        )
        text = effective_query.casefold()
        if not isinstance(self._answerer, DeterministicTestAnswerer):
            from backend.integrations.files.company_data_service import CompanyDataService
            cds_files = getattr(CompanyDataService.get_instance(), "files", [])
            has_local_files = bool(cds_files)
            query_references_local_file = False
            if has_local_files:
                q_words = set(re.findall(r"\w+", text))
                for f in cds_files:
                    fn_words = set(re.findall(r"\w+", f.get("filename", "").casefold()))
                    if q_words.intersection(fn_words):
                        query_references_local_file = True
                        break

            is_internal_only = (
                any(k in text for k in ("project", "contract", "internal", "policy", "handbook", "c:\\"))
                or query_references_local_file
                or any(k in text for k in ("file", "files", "document", "documents", "folder", "company", "report", "reports", "handover", "overview", "readme", "guide", "summary", "data", "sheet", "pdf"))
            )
            is_convo_question = any(k in query.casefold() for k in ("what was my", "first question", "previous question", "what did i", "what did we"))
            has_web_agent = bool(getattr(self._orchestrator, "agents", None) and Capability.WEB_SEARCH in self._orchestrator.agents)
            if not has_actionable_info and not is_internal_only and not is_convo_question and Capability.WEB_SEARCH not in capabilities and has_web_agent:
                try:
                    web_state = self._orchestrator.invoke(
                        AgentRequest(request_id, user, effective_query, history=tuple(prior_history)), forced_capability=Capability.WEB_SEARCH
                    )
                    traces.extend(web_state.trace)
                    if (
                        web_state.response is not None
                        and web_state.response.content
                        and "couldn't find" not in str(web_state.response.content).lower()
                        and "not configured" not in str(web_state.response.content).lower()
                    ):
                        responses = [r for r in responses if r.capability != Capability.KNOWLEDGE]
                        responses.append(web_state.response)
                        capabilities = (*capabilities, Capability.WEB_SEARCH)
                except Exception as exc:
                    logger.warning("Dynamic web search fallback failed: %s", exc)

        # If a deterministic or report response was generated, use its content directly (0 Groq calls)
        report_resp = next((r for r in responses if r.capability == Capability.REPORT), None)
        deterministic_resp = next((r for r in responses if getattr(r, "deterministic", False)), None)

        # Collect all non-empty responses from every capability for multi-source merging
        non_empty_responses = [
            r for r in responses
            if r.content
            and str(r.content).strip()
            and "not configured" not in str(r.content).lower()
            and "couldn't find" not in str(r.content).lower()
            and "could not be completed" not in str(r.content).lower()
            and "do not have permission" not in str(r.content).lower()
            and "is not configured" not in str(r.content).lower()
        ]

        if report_resp and report_resp.content:
            answer = str(report_resp.content)
        elif hasattr(self._answerer, "calls"):
            context = self._prompt_context.build(query, tuple(responses), history=prior_history)
            answer = self._answerer.answer(context)
        elif len(non_empty_responses) > 1:
            # Multiple sources returned results — merge them together with clear headers
            answer = self._merge_multi_source_answer(non_empty_responses)
        elif len(non_empty_responses) == 1 and non_empty_responses[0].capability == Capability.DATABASE:
            answer = str(non_empty_responses[0].content)
        elif deterministic_resp and deterministic_resp.content:
            answer = str(deterministic_resp.content)
        else:
            context = self._prompt_context.build(query, tuple(responses), history=prior_history)
            answer = self._answerer.answer(context)

        self._store.append(conversation_id, ChatMessage("assistant", answer, datetime.now(timezone.utc)))
        source_map: dict[str, object] = {}
        for response in responses:
            for source in response.sources:
                source_map[source.reference_id] = source
        log_event(logger, "chat_service_completed", actor_id=user.user_id, tenant_id=user.tenant_id,
                  request_id=request_id, capability=",".join(c.value for c in capabilities), source_count=len(source_map),
                  history_count=len(self._store.get(conversation_id)))
        report_id = None
        for r in responses:
            if getattr(r, "report_id", None):
                report_id = r.report_id
            elif hasattr(r.content, "metadata") and hasattr(r.content.metadata, "report_id"):
                report_id = r.content.metadata.report_id

        return ChatResponse(conversation_id, answer, tuple(source_map.values()),
                            ",".join(c.value for c in capabilities), tuple(traces), self._store.get(conversation_id),
                            report_id=report_id)

    @staticmethod
    def _capabilities_for_query(query: str) -> tuple[Capability, ...]:
        text = query.casefold()
        found: list[Capability] = []
        rules = (
            (Capability.EMAIL, (
                "email", "emails", "mail", "gmail", "inbox", "thread", "threads", "message", "messages",
                "sent", "received", "from:", "to:", "subject:", "priya", "kavita", "rahul", "david", "deepak",
            )),
            (Capability.DATABASE, (
                "sql", "database", "data base", "db record", "db records",
                "invoice", "invoices", "overdue",
                "transaction", "transactions", "ledger", "balance",
                "employee record", "employee records", "customer record", "customer records",
                "from db", "from the db", "in db", "in the db",
                "from database", "from the database", "from data base", "from the data base",
                "in database", "in the database", "in data base", "in the data base",
                "search database", "search the database", "query database", "check database",
                "look in database", "look in the database", "look up in database",
                "database record", "database records", "db",
            )),
            (Capability.DATA_ANALYSIS, ("average", "total", "compare", "trend", "sales metric")),
            (Capability.REPORT, (
                "generate report", "export report", "create report", "download report",
                "make report", "build report", "new report", "report generation", "generation of report",
                "in word", "in excel", "in pdf", "in doc", "in docx", "in xlsx", "in txt", "in text",
                "renewal schedule", "contract schedule", "schedule in word", "schedule in excel",
                "export to word", "export to excel", "export to pdf", "export to txt",
                "download as word", "download as pdf", "download as excel", "download as docx",
                "generate document", "create document", "put this in a doc", "put this in doc", "put this in word",
                "generate contract renewal schedule", "invoice report", "overdue report", "billing report",
            )),
            (Capability.KNOWLEDGE, (
                "document", "documents", "file", "files", "pdf", "word", "docx", "excel", "xlsx", "csv",
                "policy", "handbook", "contract", "summary", "agreement", "customer", "finance", "hr", "project",
                "rag", "retrieval", "retrieval-augmented", "vault", "vaults", "knowledge base", "company data",
                "upload", "uploaded", "attachment", "harish", "companydata",
                "invoice", "invoices", "vendor", "vendors", "receipt", "receipts", "bill", "bills",
                "cloudnova", "po", "purchase order",
                "nda", "mutual nda", "non-disclosure",
                "local folder", "local files", "local folder",
                "google drive", "drive", "gdrive",
            )),
            (Capability.GOOGLE_DRIVE, (
                "google drive", "gdrive", "drive folder", "drive file", "in drive", "from drive", "on drive",
                "in google drive", "from google drive", "on google drive", "google doc", "google docs", "google sheet", "google sheets",
            )),
            (Capability.WEB_SEARCH, (
                "web", "search the web", "search online", "browse web", "browse the web", "google", "tavily",
                "internet", "market trend", "industry news", "world news", "external research", "competitors",
                "gold", "silver", "price", "prices", "weather", "today", "today's", "chennai", "india", "news",
                "rate", "rates", "stock", "stocks", "crypto", "bitcoin", "ipl", "score", "live",
            )),
        )
        for capability, keywords in rules:
            if any(k in text for k in keywords):
                found.append(capability)

        # Single-file inspection queries strictly target local file knowledge
        is_single_file_inspection = any(p in text for p in (
            "describe the contents of this file", "describe this file",
            "summarize this file", "summarize the contents of this file",
            "what is in this file", "what is inside this file",
            "explain this file", "read this file", "open this file",
            "i need this file", "contents of this file", "about this file",
            "tell me about this file",
        ))
        if is_single_file_inspection:
            return (Capability.KNOWLEDGE,)

        # Cross-source / "search everywhere" detection:
        # When user explicitly asks to search all sources, across sources, or everywhere
        cross_source_patterns = (
            "all sources", "across all", "search everywhere", "every source",
            "all available sources", "from all", "check all", "look everywhere",
            "search all", "across sources", "in all sources", "everywhere",
            "all places", "all systems", "across systems",
        )
        if any(p in text for p in cross_source_patterns):
            for cap in (Capability.KNOWLEDGE, Capability.DATABASE, Capability.EMAIL, Capability.GOOGLE_DRIVE):
                if cap not in found:
                    found.append(cap)

        # Document / Report generation detection (strictly isolate ReportAgent)
        is_report_request = (
            Capability.REPORT in found
            or ("report" in text and any(v in text for v in ("generate", "generation", "export", "download", "create", "build", "make", "produce", "new")))
            or any(w in text for w in (
                "in word", "in excel", "in pdf", "in doc", "in docx", "in xlsx", "in txt", "in text",
                "renewal schedule", "contract renewal", "schedule in word", "schedule in excel",
                "as a doc", "as a document", "as a word", "as a pdf", "as an excel", "as a sheet",
                "put this in", "put this content", "export to", "download as", "generate schedule", "create schedule",
                "in a doc", "in a pdf", "in an excel", "in a word", "in a txt",
            ))
            or (
                any(v in text for v in ("generate", "generation", "create", "export", "download", "build", "produce")) and
                any(f in text for f in ("in word", "in doc", "in excel", "in pdf", "in txt", "schedule", "report", "word document", "excel sheet", "pdf report", "document"))
            )
            or (
                "report" in text and any(k in text for k in ("invoice", "invoices", "overdue", "billing", "contract", "renewal"))
            )
        )
        if is_report_request:
            return (Capability.REPORT,)

        # Explicit web search request priority
        web_explicit = ("search the web", "search online", "browse web", "browse the web", "look up online", "tavily", "google search")
        if any(w in text for w in web_explicit):
            if Capability.WEB_SEARCH not in found:
                found.insert(0, Capability.WEB_SEARCH)
            # If user explicitly asked to search the web, prioritize it over local file knowledge
            if Capability.KNOWLEDGE in found and not any(k in text for k in ("document", "file", "pdf", "docx", "policy", "handbook", "c:\\")):
                found.remove(Capability.KNOWLEDGE)

        # Prioritize Knowledge whenever user explicitly asks for a file, document, or invoice (and NOT a document generation request)
        if not is_report_request and any(w in text for w in (
            "file", "files", "document", "documents", "pdf", "docx", "xlsx", "find the file", "invoice file",
            "companydata", "company data", "folder", "search file", "search files", "find file", "find files"
        )):
            if Capability.KNOWLEDGE not in found:
                found.insert(0, Capability.KNOWLEDGE)
            elif found[0] != Capability.KNOWLEDGE:
                found.remove(Capability.KNOWLEDGE)
                found.insert(0, Capability.KNOWLEDGE)

        # Multi-source search queries mentioning mail, database, or drive
        if any(w in text for w in ("mail", "email", "gmail", "inbox")) and Capability.EMAIL not in found:
            found.append(Capability.EMAIL)
        if any(w in text for w in ("database", "data base", "db", "sql", "postgres")) and Capability.DATABASE not in found:
            found.append(Capability.DATABASE)
        if any(w in text for w in ("drive", "google drive", "gdrive")) and Capability.GOOGLE_DRIVE not in found:
            found.append(Capability.GOOGLE_DRIVE)

        # Automatic cross-source relevance for contracts and NDAs (Local files + Database + Google Drive)
        if any(w in text for w in ("nda", "mutual nda", "non-disclosure", "contract", "contracts", "agreement", "agreements")):
            for cap in (Capability.KNOWLEDGE, Capability.DATABASE, Capability.GOOGLE_DRIVE):
                if cap not in found:
                    found.append(cap)

        # Automatic cross-source relevance for invoices and billing (Database + Local files + Email)
        if any(w in text for w in ("invoice", "invoices", "overdue", "billing", "payment schedule", "vendor payment")):
            for cap in (Capability.KNOWLEDGE, Capability.DATABASE, Capability.EMAIL):
                if cap not in found:
                    found.append(cap)

        # Recruitment, resume, and candidate queries search across Documents, Email (attachments & inbox), and Database (HR records)
        recruitment_keywords = (
            "resume", "resumes", "cv", "curriculum vitae", "candidate", "candidates",
            "applicant", "applicants", "hiring", "recruit", "recruitment", "interview",
            "job application", "profile",
        )
        if any(k in text for k in recruitment_keywords):
            for cap in (Capability.KNOWLEDGE, Capability.EMAIL, Capability.DATABASE):
                if cap not in found:
                    found.append(cap)

        # Default to Knowledge for general queries
        if not found:
            found = [Capability.KNOWLEDGE]
        elif Capability.KNOWLEDGE in found:
            # If query mentions updates, projects, people, or communications, also check Email
            if any(k in text for k in ("update", "latest", "recent", "status", "phoenix", "acme", "renewal", "alert", "notice", "news")):
                if Capability.EMAIL not in found:
                    found.append(Capability.EMAIL)

        return tuple(dict.fromkeys(found))


    _GREETINGS_OR_CONVERSATIONAL = frozenset({
        "hi", "hello", "hey", "hola", "namaste",
        "good morning", "good afternoon", "good evening",
        "greetings", "help", "who are you", "what can you do",
        "what are you", "how are you", "hi nanvi", "hello nanvi",
        "hey nanvi", "thanks", "thank you", "ok", "okay",
        "bye", "goodbye", "tell me about yourself",
    })

    @classmethod
    def _is_conversational_query(cls, query: str) -> bool:
        clean = re.sub(r"[^\w\s]", "", query.strip().casefold())
        clean = re.sub(r"\s+", " ", clean).strip()
        if clean in cls._GREETINGS_OR_CONVERSATIONAL:
            return True
        tokens = clean.split()
        if len(tokens) <= 3 and any(tokens[0] == g for g in ("hi", "hello", "hey", "hola")):
            if not any(k in clean for k in ("file", "document", "invoice", "report", "email", "database", "data", "search")):
                return True
        return False

    @staticmethod
    def _generate_conversational_reply(query: str) -> str:
        clean = re.sub(r"[^\w\s]", "", query.strip().casefold())
        clean = re.sub(r"\s+", " ", clean).strip()
        if any(clean.startswith(w) for w in ("who are you", "what are you", "what can you do", "help", "tell me about yourself")):
            return (
                "I'm **Nanvi**, your enterprise AI copilot designed for secure and intelligent workplace assistance.\n\n"
                "Here is what I can help you with:\n"
                "- **Document Retrieval (RAG)**: Search and extract information across PDFs, Word docs, Excel sheets, and CSVs.\n"
                "- **Enterprise Database**: Query business records, transactions, invoices, and analytics.\n"
                "- **Email Intelligence**: Retrieve messages, communications, and project updates.\n"
                "- **Data Analysis & Calculations**: Aggregate numbers, analyze trends, and compute metrics.\n"
                "- **Executive Reports**: Generate structured reports with source citations.\n"
                "- **Web Intelligence**: Search live web data when needed.\n\n"
                "All operations strictly enforce enterprise Zero-Trust RBAC access policies. What would you like to explore today?"
            )
        if any(clean.startswith(w) for w in ("thank", "thanks")):
            return "You're very welcome! Let me know if you need anything else."
        if any(clean.startswith(w) for w in ("how are you",)):
            return "I'm doing well, thank you! Ready to assist you with any company documents, data, or reports. How can I help you today?"
        if any(clean.startswith(w) for w in ("bye", "goodbye")):
            return "Goodbye! Have a productive day ahead."
        return (
            "Hello! I'm **Nanvi**, your enterprise assistant. "
            "How can I assist you today? You can ask me to search company documents, query the database, check emails, or generate reports."
        )

    @staticmethod
    def _extract_conversation_entity(text: str) -> str | None:
        """Extract compound entities, enterprise identifiers, or capitalized business names from a message."""
        # 1. Compound enterprise entities: Customer 015, Project P-001-005, Employee 1005, etc.
        m = re.search(
            r"\b((?:Customer|Employee|Project|Account|Vendor|Contract|Invoice|Task|Order)\s+(\d{1,6}(?:-[A-Za-z0-9]+)*|[A-Za-z]{1,5}-\d{2,6}[A-Za-z0-9-]*|[A-Za-z]+\d+[A-Za-z0-9-]*))\b",
            text,
            re.IGNORECASE,
        )
        if m:
            return m.group(1).strip()

        # 2. Alphanumeric enterprise identifiers (P-001-005, CTR-01-005, CUST-1005, etc.)
        m_id = re.search(r"\b([A-Za-z]{1,5}(?:-[A-Za-z0-9]{2,6})+)\b", text)
        if m_id:
            return m_id.group(1).strip()

        # 3. Capitalized multi-word company/entity names (Asteron Technologies, Apex Global, etc.)
        excluded = {
            "what", "when", "where", "which", "who", "whom", "whose", "why", "how",
            "tell", "show", "give", "find", "list", "can", "could", "would", "should",
            "does", "is", "are", "now", "go back", "here", "available", "department",
        }
        multi = re.findall(r"\b([A-Z][a-zA-Z0-9]+(?:\s+[A-Z][a-zA-Z0-9]+)+)\b", text)
        for name in multi:
            if name.casefold() not in excluded and not any(name.casefold().startswith(x + " ") for x in excluded):
                return name.strip()
        return None

    @classmethod
    def _fallback_contextualize(cls, query: str, prior_history: Sequence[ChatMessage]) -> str:
        """Contextualize multi-turn follow-ups, resolving pronouns and topic continuity across prior turns."""
        q_clean = query.strip()
        q_lower = q_clean.casefold()
        tokens = q_clean.split()

        # Check if the query itself explicitly introduces or switches to a concrete entity
        current_entity = cls._extract_conversation_entity(q_clean)

        # Detect pronouns and elliptical follow-up queries
        has_pronoun = any(
            re.search(rf"\b{p}\b", q_lower)
            for p in ("it", "its", "they", "their", "them", "this", "that", "these", "those", "he", "she", "his", "her")
        )
        is_elliptical = (
            len(tokens) <= 6
            or any(q_lower.startswith(p) for p in ("in ", "for ", "check ", "what about ", "how about ", "which one ", "who is ", "where is ", "what is ", "who owns "))
        )

        # If it's a follow-up and does not introduce a brand-new concrete entity
        if (has_pronoun or is_elliptical) and not current_entity:
            # Search backwards through prior user turns to find the most recent active entity
            for msg in reversed(prior_history):
                if msg.role == "user" and not cls._is_conversational_query(msg.content):
                    entity = cls._extract_conversation_entity(msg.content)
                    if entity:
                        return f"{entity} {q_clean}"
            # Fallback to appending to the most recent user turn
            for msg in reversed(prior_history):
                if msg.role == "user" and not cls._is_conversational_query(msg.content):
                    return f"{msg.content} {q_clean}"

        return q_clean

    @staticmethod
    def _merge_multi_source_answer(responses) -> str:
        """Merge results from multiple capability agents into a unified answer with source headers."""
        from backend.agents.models import Capability

        _CAPABILITY_LABELS = {
            Capability.KNOWLEDGE: ("📁 Local Files / Documents", 1),
            Capability.DATABASE: ("🗄️ Database Records", 2),
            Capability.EMAIL: ("✉️ Email", 3),
            Capability.GOOGLE_DRIVE: ("☁️ Google Drive", 4),
            Capability.DATA_ANALYSIS: ("📊 Data Analysis", 5),
            Capability.WEB_SEARCH: ("🌐 Web Search", 6),
        }

        sections: list[tuple[int, str, str]] = []
        for resp in responses:
            label, order = _CAPABILITY_LABELS.get(resp.capability, (resp.capability.value.title(), 99))
            content = str(resp.content).strip()
            if content:
                sections.append((order, label, content))

        # Sort by display order (Local Files first, then Database, then Email, etc.)
        sections.sort(key=lambda s: s[0])

        if len(sections) == 1:
            return sections[0][2]

        parts: list[str] = []
        parts.append("I found relevant information across **multiple sources**:\n")
        for _, label, content in sections:
            parts.append(f"### {label}\n")
            parts.append(content)
            parts.append("")  # blank line separator

        return "\n".join(parts).strip()

    def history(self, user: UserAttributes):
        return self._store.list_for_user(user.user_id, user.tenant_id)
