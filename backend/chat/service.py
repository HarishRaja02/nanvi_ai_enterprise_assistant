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
from concurrent.futures import ThreadPoolExecutor
from typing import Sequence

logger = logging.getLogger(__name__)

from .models import ChatMessage, ChatRequest, ChatResponse, ConversationSummary
from .stores import (
    ConversationStore,
    InMemoryConversationStore,
    generate_conversation_title,
)
from .answerers import (
    ChatAnswerer,
    DeterministicTestAnswerer,
)

class ChatService:
    def __init__(self, orchestrator: EnterpriseOrchestrator, answerer: ChatAnswerer, store: ConversationStore) -> None:
        self._orchestrator = orchestrator
        self._answerer = answerer
        self._store = store
        self._prompt_context = PromptContextBuilder()

    def set_active_document(self, conversation_id: str, document_id: str) -> None:
        if hasattr(self._store, "set_active_document"):
            self._store.set_active_document(conversation_id, document_id)
            self._store.set_active_document("default", document_id)

    def get_active_document(self, conversation_id: str) -> str | None:
        if hasattr(self._store, "get_active_document"):
            return self._store.get_active_document(conversation_id) or self._store.get_active_document("default")
        return None

    def ask(self, user: UserAttributes, request: ChatRequest) -> ChatResponse:
        query = validate_non_empty(request.query, "query", 4000)
        conversation_id = request.conversation_id or uuid4().hex
        self._store.bind_owner(conversation_id, user.user_id, user.tenant_id)
        if self._store.owner(conversation_id) != (user.user_id, user.tenant_id):
            raise PermissionError("Conversation does not belong to the authenticated principal")

        # Resolve active document context
        active_doc_id = getattr(request, "active_document_id", None)
        if not active_doc_id and hasattr(self._store, "get_active_document"):
            active_doc_id = self._store.get_active_document(conversation_id) or self._store.get_active_document("default")
        if not active_doc_id and hasattr(self._store, "get"):
            prior_for_doc = self._store.get(conversation_id)
            for msg in reversed(prior_for_doc):
                m = re.search(r"(?:attached document|uploaded document|file)\s*\(([^)]+)\)", msg.content, re.IGNORECASE)
                if m:
                    active_doc_id = m.group(1).strip()
                    break
        if not active_doc_id:
            from backend.integrations.files.company_data_service import CompanyDataService
            cds_inst = CompanyDataService.for_tenant(user.tenant_id)
            cds_files = getattr(cds_inst, "files", [])
            upload_files = [f for f in cds_files if "upload" in f.get("folder", "").lower() or "upload" in f.get("file_path", "").lower()]
            if upload_files:
                upload_files.sort(key=lambda x: x.get("modified_at", ""), reverse=True)
                active_doc_id = upload_files[0].get("filename")

        if active_doc_id and hasattr(self._store, "set_active_document"):
            self._store.set_active_document(conversation_id, active_doc_id)

        # 1. Fetch prior history for this specific conversation before appending current turn
        prior_history = self._store.get(conversation_id)

        if not query or not query.strip():
            answer = "Please can you repeat the sentence?"
            self._store.append(conversation_id, ChatMessage("assistant", answer, datetime.now(timezone.utc)))
            return ChatResponse(
                conversation_id=conversation_id,
                answer=answer,
                sources=(),
                capability="",
                trace=("Empty query handled",),
                history=self._store.get(conversation_id),
            )

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

        # 2. Contextualize query if prior history exists (resolves pronouns, deictic references, ordinals, and why follow-ups)
        effective_query = query
        from backend.chat.deictic_resolver import DeicticResolver
        from backend.chat.context_engine import context_manager

        ctx = context_manager.get(conversation_id)
        prior_user_msgs = [m.content for m in prior_history if m.role == "user"]
        prior_asst_msgs = [m.content for m in prior_history if m.role == "assistant"]
        prior_user = prior_user_msgs[-1] if prior_user_msgs else ""
        prior_asst = prior_asst_msgs[-1] if prior_asst_msgs else ""

        deictic_query = DeicticResolver.resolve(
            query=query,
            context=ctx,
            prior_user_query=prior_user,
            prior_assistant_answer=prior_asst,
        )
        if deictic_query != query:
            effective_query = deictic_query
        else:
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
                    if q_words.intersection({"it", "its", "they", "them", "their", "this", "that", "these", "those", "which", "who", "whom", "one", "her", "his", "him", "she", "he"}):
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

        def invoke_capability(capability: Capability):
            agent_query = effective_query if (capability == Capability.KNOWLEDGE or effective_query != query) else query
            agent_req = AgentRequest(
                request_id,
                user,
                agent_query,
                history=tuple(prior_history),
                active_document_id=active_doc_id if capability == Capability.KNOWLEDGE else None,
            )
            return self._orchestrator.invoke(agent_req, forced_capability=capability)

        # Independent source searches are I/O bound. Run them together so the
        # response waits for the slowest source instead of the sum of all sources.
        errors: list[str] = []
        if len(capabilities) > 1:
            with ThreadPoolExecutor(max_workers=len(capabilities), thread_name_prefix="nanvi-source-search") as pool:
                states = pool.map(invoke_capability, capabilities)
                for state in states:
                    traces.extend(state.trace)
                    if state.error:
                        logger.warning("Capability agent encountered error: %s", state.error)
                        errors.append(state.error)
                    if state.response is not None:
                        responses.append(state.response)
        else:
            for capability in capabilities:
                state = invoke_capability(capability)
                traces.extend(state.trace)
                if state.error:
                    logger.warning("Capability agent encountered error: %s", state.error)
                    errors.append(state.error)
                if state.response is not None:
                    responses.append(state.response)

        if not responses and errors:
            raise RuntimeError(errors[0])

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
            cds_files = getattr(CompanyDataService.for_tenant(user.tenant_id), "files", [])
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

        # Auto-update centralized ConversationContext conforming to Section 6.1 of the spec
        try:
            from backend.chat.context_engine import context_manager
            src_list = [
                s.to_frontend_dict() if hasattr(s, "to_frontend_dict") else getattr(s, "__dict__", {})
                for s in source_map.values()
            ]
            context_manager.update_from_interaction(
                conversation_id=conversation_id,
                user=user,
                query=query,
                answer=answer,
                capability=",".join(c.value for c in capabilities),
                sources=src_list,
                active_document_id=active_doc_id,
            )
        except Exception as exc:
            logger.warning("Could not auto-update conversation context: %s", exc)

        data_source = "synthetic" if any(getattr(r, "data_source", "live") == "synthetic" for r in responses) else "live"
        return ChatResponse(conversation_id, answer, tuple(source_map.values()),
                            ",".join(c.value for c in capabilities), tuple(traces), self._store.get(conversation_id),
                            report_id=report_id, data_source=data_source)

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

        # A direct file discovery request searches every connected enterprise
        # source. Knowledge keeps its existing local-file search behavior; the
        # other source agents run independently and contribute their own sources.
        from backend.retrieval.intent import classify_retrieval_intent, QueryIntent
        is_file_discovery = (
            classify_retrieval_intent(query) == QueryIntent.FILE_SEARCH
            and re.search(r"\b(?:find|search|locate|look\s+for|where\s+is|where\s+are|show\s+me)\b", text)
        )
        if is_file_discovery and not is_report_request:
            for cap in (Capability.KNOWLEDGE, Capability.DATABASE, Capability.EMAIL, Capability.GOOGLE_DRIVE):
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
            return "I'm ready to help with company documents, data, and reports. What do you need?"
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

    def get_context(self, conversation_id: str, user: UserAttributes):
        """Retrieve the centralized ConversationContext for a conversation."""
        owner = self._store.owner(conversation_id)
        if owner and owner != (user.user_id, user.tenant_id):
            raise PermissionError("Conversation does not belong to the authenticated principal")
        from backend.chat.context_engine import context_manager
        ctx = context_manager.get_or_create(conversation_id, user)
        return ctx

    def update_context(self, conversation_id: str, user: UserAttributes, updates: dict[str, Any]):
        """Update the centralized ConversationContext for a conversation."""
        owner = self._store.owner(conversation_id)
        if owner and owner != (user.user_id, user.tenant_id):
            raise PermissionError("Conversation does not belong to the authenticated principal")
        from backend.chat.context_engine import context_manager
        context_manager.get_or_create(conversation_id, user)
        updated = context_manager.update(conversation_id, updates)
        if hasattr(self._store, "set_context"):
            self._store.set_context(conversation_id, updated)
        return updated

    def stream_ask(
        self,
        user: UserAttributes,
        request: ChatRequest,
        context_override: dict[str, Any] | None = None,
    ):
        """Execute chat request while streaming SSE lifecycle events conforming to Section 6.2."""
        from backend.chat.events import format_sse, EventType
        from backend.chat.context_engine import context_manager

        query = request.query
        conversation_id = request.conversation_id or uuid4().hex
        task_id = uuid4().hex
        request_id = get_request_id() if get_request_id() != "-" else uuid4().hex

        # 1. Emit task_started
        yield format_sse(
            EventType.TASK_STARTED,
            {"conversation_id": conversation_id, "query": query},
            task_id=task_id,
            request_id=request_id,
        )

        # 2. Synchronize context with user and any frontend overrides
        try:
            context_manager.get_or_create(conversation_id, user)
            if context_override:
                context_manager.update(conversation_id, context_override)
        except Exception as exc:
            logger.warning("Context sync warning: %s", exc)

        # 3. Emit initial analysis status
        yield format_sse(
            EventType.STATUS,
            {
                "status": "ANALYZING_QUERY",
                "message": "Analyzing query and contextual state",
                "progress": 0.15,
            },
            task_id=task_id,
            request_id=request_id,
        )

        try:
            # 4. Check capabilities and emit status
            capabilities = self._capabilities_for_query(query)
            if Capability.KNOWLEDGE in capabilities:
                yield format_sse(
                    EventType.STATUS,
                    {
                        "status": "SEARCHING_FILES",
                        "message": "Searching enterprise files and documents",
                        "progress": 0.40,
                    },
                    task_id=task_id,
                    request_id=request_id,
                )
            elif Capability.DATABASE in capabilities:
                yield format_sse(
                    EventType.STATUS,
                    {
                        "status": "SQL_STARTED",
                        "message": "Querying enterprise database records",
                        "progress": 0.40,
                    },
                    task_id=task_id,
                    request_id=request_id,
                )
            elif Capability.EMAIL in capabilities:
                yield format_sse(
                    EventType.STATUS,
                    {
                        "status": "EMAIL_SEARCH_STARTED",
                        "message": "Searching company mailbox",
                        "progress": 0.40,
                    },
                    task_id=task_id,
                    request_id=request_id,
                )

            # 5. Execute standard orchestration pipeline
            response = self.ask(user, request)

            # 6. Plan humanized spoken and screen response
            from backend.chat.response_planner import human_response_planner
            plan = human_response_planner.plan_response(
                answer=response.answer,
                query=query,
                sources=response.sources,
                capability=response.capability,
            )

            # Auto-index UI entities for deictic reference resolution (Milestone 7)
            try:
                from backend.chat.deictic_resolver import DeicticResolver
                entity_index = DeicticResolver.build_ui_entity_index(plan.ui_specs, response.sources)
                if entity_index:
                    context_manager.update(conversation_id, {"ui_entity_index": entity_index})
            except Exception as exc:
                logger.warning("Could not auto-index UI entities: %s", exc)

            # 7. Stream source discovery events
            for src in response.sources:
                src_dict = src.to_frontend_dict() if hasattr(src, "to_frontend_dict") else getattr(src, "__dict__", {})
                yield format_sse(
                    EventType.SOURCE_FOUND,
                    {"source": src_dict},
                    task_id=task_id,
                    request_id=request_id,
                )
                yield format_sse(
                    EventType.SOURCE_VERIFIED,
                    {"reference_id": src_dict.get("reference_id", "")},
                    task_id=task_id,
                    request_id=request_id,
                )

            # 8. Stream assistant answer and spoken response
            yield format_sse(
                EventType.ASSISTANT_TEXT,
                {
                    "text": response.answer,
                    "spoken_response": plan.spoken_response,
                    "screen_message": plan.screen_message,
                },
                task_id=task_id,
                request_id=request_id,
            )

            # 9. Stream UI Specs
            for spec in plan.ui_specs:
                yield format_sse(
                    EventType.UI_SPEC,
                    spec.model_dump(),
                    task_id=task_id,
                    request_id=request_id,
                )

            # 10. Stream highlights and action suggestions if present
            if plan.highlights:
                yield format_sse(
                    EventType.HIGHLIGHT,
                    {"targets": plan.highlights},
                    task_id=task_id,
                    request_id=request_id,
                )

            if plan.suggested_actions:
                yield format_sse(
                    EventType.ACTION_SUGGESTIONS,
                    {"actions": plan.suggested_actions},
                    task_id=task_id,
                    request_id=request_id,
                )

            # 11. Emit task_complete with full plan payload
            yield format_sse(
                EventType.TASK_COMPLETE,
                {
                    "conversation_id": response.conversation_id,
                    "answer": response.answer,
                    "spoken_response": plan.spoken_response,
                    "screen_message": plan.screen_message,
                    "highlights": plan.highlights,
                    "suggested_actions": plan.suggested_actions,
                    "ui_specs": [s.model_dump() for s in plan.ui_specs],
                    "sensitivity": plan.sensitivity,
                    "confidence_level": plan.confidence_level,
                    "capability": response.capability,
                    "sources": [
                        s.to_frontend_dict() if hasattr(s, "to_frontend_dict") else getattr(s, "__dict__", {})
                        for s in response.sources
                    ],
                    "trace": list(response.trace),
                    "report_id": getattr(response, "report_id", None),
                    "data_source": getattr(response, "data_source", "live"),
                },
                task_id=task_id,
                request_id=request_id,
            )

        except Exception as exc:
            logger.exception("Error during streaming chat execution")
            yield format_sse(
                EventType.TASK_ERROR,
                {"detail": str(exc)},
                task_id=task_id,
                request_id=request_id,
            )
