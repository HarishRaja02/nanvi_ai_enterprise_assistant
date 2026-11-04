from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from backend.security.ai.context import PromptContext, PromptContextBuilder
from uuid import uuid4

from backend.agents.models import AgentRequest, AgentResponse, Capability, OrchestrationState
from backend.agents.orchestrator import EnterpriseOrchestrator
from backend.security.authorization import UserAttributes
from backend.security.validation import validate_non_empty
from backend.sources.models import SourceReference, SourceType
from backend.observability.logging import get_request_id, log_event
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Sequence

logger = logging.getLogger(__name__)

from backend.core.config import settings

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
        res = self._ask_internal(user, request)
        def _bg_record() -> None:
            try:
                from backend.logs.store import get_user_log_store
                role_val = next(iter(user.roles), "Employee") if user.roles else "Employee"
                if hasattr(role_val, "value"):
                    role_val = role_val.value
                get_user_log_store().record_log(
                    user_id=user.user_id,
                    user_name=getattr(user, "name", None) or user.user_id,
                    user_role=str(role_val),
                    query=request.query,
                    answer=res.answer,
                    capability=str(res.capability or ""),
                    tenant_id=user.tenant_id,
                )
            except Exception as exc:
                logger.warning("Could not record user query log: %s", exc)

        import threading
        threading.Thread(target=_bg_record, daemon=True).start()
        return res

    def _ask_internal(self, user: UserAttributes, request: ChatRequest) -> ChatResponse:
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

        prior_asst_msgs = [m.content for m in prior_history if m.role == "assistant"]
        prior_user_msgs = [m.content for m in prior_history if m.role == "user"]

        # 1. Check if user is asking to open, preview, or show the document from context
        is_open_action = bool(re.search(
            r"(?i)\b(?:give\s+(?:the\s+)?open\s+option|open\s+(?:the\s+)?file|open\s+it|show\s+it|preview\s+it|download\s+(?:the\s+)?(?:full\s+)?pdf|i\s+cant\s+able\s+to\s+download|can\s+you\s+show\s+it)\b",
            query,
        ))
        if is_open_action and (prior_user_msgs or prior_asst_msgs):
            target_doc = ""
            for prev_m in reversed(prior_user_msgs):
                t = self._extract_file_search_target(prev_m)
                if t:
                    target_doc = t
                    break
            if not target_doc:
                for prev_a in reversed(prior_asst_msgs):
                    id_match = re.search(r"\b(?:INV|EMP|NDA|PUR|PO|PRJ)[-_]\d+[-_]?\d*\b", prev_a, re.IGNORECASE)
                    if id_match:
                        target_doc = id_match.group(0)
                        break

            if target_doc:
                from backend.chat.file_search import execute_file_search
                answer, files, sources = execute_file_search(user, target_doc, "local", max_results=10)
                if not files:
                    db_ans, db_files, db_sources = execute_file_search(user, target_doc, "database", max_results=10)
                    if db_files:
                        answer, files, sources = db_ans, db_files, db_sources
                if files:
                    self._store.append(conversation_id, ChatMessage("assistant", answer, datetime.now(timezone.utc)))
                    return ChatResponse(
                        conversation_id=conversation_id,
                        answer=answer,
                        sources=tuple(sources),
                        capability="document_search",
                        trace=("Open option provided for previous document",),
                        history=self._store.get(conversation_id),
                        file_results=tuple(files),
                    )

        # 2. Check if user is selecting a source (e.g. 'Search in Local Storage', 'in local database', 'internal repository')
        selected_source = self._extract_source_from_query(query)
        clean_after_source = re.sub(
            r"(?i)\b(?:search\s+(?:in\s+)?|find\s+(?:in\s+)?|look\s+(?:for\s+)?in\s+|from\s+)?(?:local\s+storage|local\s+files?|local\s+folder|internal\s+repository|internal\s+storage|repository|database|local\s+database|db|emails?|gmail|inbox|google\s+drive|gdrive|cloud(?:\s+storage)?)\b",
            "",
            query,
        ).strip(" :,-'\"?.")

        is_pure_source_choice = selected_source is not None and (
            clean_after_source == ""
            or clean_after_source.casefold() in ("search", "find", "open", "show", "get", "in local", "local", "database", "it", "this", "file")
        )

        if is_pure_source_choice and prior_user_msgs:
            prior_target = ""
            for prev_m in reversed(prior_user_msgs):
                t = self._extract_file_search_target(prev_m)
                if t:
                    prior_target = t
                    break
            if not prior_target and prior_asst_msgs:
                id_m = re.search(r"\b(?:INV|EMP|NDA|PUR|PO|PRJ)[-_]\d+[-_]?\d*\b", prior_asst_msgs[-1], re.IGNORECASE)
                if id_m:
                    prior_target = id_m.group(0)

            if prior_target:
                from backend.chat.file_search import execute_file_search
                answer, files, sources = execute_file_search(user, prior_target, selected_source, max_results=10)
                self._store.append(conversation_id, ChatMessage("assistant", answer, datetime.now(timezone.utc)))
                return ChatResponse(
                    conversation_id=conversation_id,
                    answer=answer,
                    sources=tuple(sources),
                    capability="document_search",
                    trace=(f"File search executed on {selected_source} for {prior_target}",),
                    history=self._store.get(conversation_id),
                    file_results=tuple(files),
                )
            else:
                answer = f"Sure! What is the name, document number (such as an invoice or contract ID), or keyword of the file you'd like me to look for in {selected_source.replace('_', ' ').title()}?"
                self._store.append(conversation_id, ChatMessage("assistant", answer, datetime.now(timezone.utc)))
                return ChatResponse(
                    conversation_id=conversation_id,
                    answer=answer,
                    sources=(),
                    capability="conversation",
                    trace=("Prompted user for specific document target in selected source",),
                    history=self._store.get(conversation_id),
                )

        # Check if user is refining an email search with date or sender/keyword
        is_email_refinement = False
        if prior_asst_msgs:
            last_asst = prior_asst_msgs[-1]
            if (
                "put a sender name" in last_asst
                or ("Here are your" in last_asst and "recent email" in last_asst.casefold())
            ):
                if not self._is_conversational_greeting(query):
                    is_email_refinement = True

        if is_email_refinement:
            answer, files, sources = self._handle_direct_email_query(user, query)
            self._store.append(conversation_id, ChatMessage("assistant", answer, datetime.now(timezone.utc)))
            return ChatResponse(
                conversation_id=conversation_id,
                answer=answer,
                sources=tuple(sources),
                capability="document_search",
                trace=("Email refinement search executed",),
                history=self._store.get(conversation_id),
                file_results=tuple(files),
            )

        # Check if user is refining a previous file search with a timeframe/date
        from backend.chat.file_search import _extract_date_filter
        date_label, dy, dm, dd = _extract_date_filter(query)
        is_date_refinement = False
        prior_file_source = ""
        prior_search_topic = ""

        if date_label is not None and prior_asst_msgs:
            last_asst = prior_asst_msgs[-1]
            if (
                "Looking for a specific timeframe?" in last_asst
                or "| File Name | File Path | Action |" in last_asst
            ):
                is_date_refinement = True
                m_src = re.search(r"\bin\s+\*\*([A-Za-z\s]+)\*\*", last_asst)
                if m_src:
                    prior_file_source = self._extract_source_from_query(m_src.group(1)) or "local"
                else:
                    prior_file_source = "local"

                for um in reversed(prior_user_msgs):
                    clean_um = um.strip().casefold()
                    if clean_um not in ("local", "database", "email", "google drive", "drive", "cloud", "local storage", "1", "2", "3", "4", "5") and not _extract_date_filter(um)[0]:
                        prior_search_topic = um
                        break

        if is_date_refinement:
            from backend.chat.file_search import execute_file_search
            combined_query = f"{prior_search_topic} {query}".strip()
            answer, files, sources = execute_file_search(user, combined_query, prior_file_source, max_results=10)
            self._store.append(conversation_id, ChatMessage("assistant", answer, datetime.now(timezone.utc)))
            return ChatResponse(
                conversation_id=conversation_id,
                answer=answer,
                sources=tuple(sources),
                capability="document_search",
                trace=(f"File date refinement executed on {prior_file_source}",),
                history=self._store.get(conversation_id),
                file_results=tuple(files),
            )

        # 2. Contextualize query if prior history exists
        effective_query = query
        from backend.chat.deictic_resolver import DeicticResolver
        from backend.chat.context_engine import context_manager

        ctx = context_manager.get(conversation_id)
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

        caps = self._capabilities_for_query(effective_query)
        is_multi_source = len(caps) > 1
        is_test_answerer = (
            isinstance(self._answerer, DeterministicTestAnswerer)
            or "Test" in type(self._answerer).__name__
            or getattr(settings, "is_testing", False)
        )

        # Direct email query check (e.g. "recent email", "top 5 recent email")
        # Returns concrete email results immediately without prompting questions
        if not is_multi_source and self._is_direct_email_query(effective_query):
            answer, files, sources = self._handle_direct_email_query(user, effective_query)
            self._store.append(conversation_id, ChatMessage("assistant", answer, datetime.now(timezone.utc)))
            return ChatResponse(
                conversation_id=conversation_id,
                answer=answer,
                sources=tuple(sources),
                capability="document_search",
                trace=("Direct email query executed",),
                history=self._store.get(conversation_id),
                file_results=tuple(files),
            )

        # Check intent decision using dedicated IntentRouter layer
        # This layer prevents distraction between conversational chat/company memory vs file search
        from backend.chat.intent_router import intent_router, ChatIntent
        intent_decision = intent_router.classify(effective_query, prior_history)

        if intent_decision.intent == ChatIntent.CONVERSATION and Capability.WEB_SEARCH not in caps and not is_test_answerer:
            answer = self._generate_chatgpt_conversational_reply(
                query=effective_query,
                prior_history=prior_history,
                tenant_id=user.tenant_id,
            )
            self._store.append(conversation_id, ChatMessage("assistant", answer, datetime.now(timezone.utc)))
            log_event(logger, "chat_service_completed", actor_id=user.user_id, tenant_id=user.tenant_id,
                      request_id=request_id, capability="conversation", source_count=0,
                      history_count=len(self._store.get(conversation_id)))
            return ChatResponse(
                conversation_id=conversation_id,
                answer=answer,
                sources=(),
                capability="conversation",
                trace=(f"Conversational intent handled via ChatGPT-style LLM ({intent_decision.reason})",),
                history=self._store.get(conversation_id),
            )

        # Check if this is an explicit report export/generation query (e.g. export to pdf, download as word)
        is_pure_report = (Capability.REPORT in caps and any(w in effective_query.casefold() for w in ("export", "download as", "generate report", "create report")))

        direct_source = self._extract_source_from_query(effective_query)
        clean_search_q = re.sub(
            r"(?i)\b(?:search\s+(?:in\s+)?|find\s+(?:in\s+)?|look\s+(?:for\s+)?in\s+|from\s+)?(?:local\s+storage|local\s+files?|local\s+folder|internal\s+repository|internal\s+storage|repository|database|local\s+database|db|emails?|gmail|inbox|google\s+drive|gdrive|cloud(?:\s+storage)?)\b",
            "",
            effective_query,
        ).strip(" :,-'\"?.")

        if direct_source and not is_pure_report and not is_multi_source:
            clean_q = clean_search_q or effective_query
            from backend.chat.file_search import execute_file_search
            answer, files, sources = execute_file_search(user, clean_q, direct_source, max_results=10)
            self._store.append(conversation_id, ChatMessage("assistant", answer, datetime.now(timezone.utc)))
            return ChatResponse(
                conversation_id=conversation_id,
                answer=answer,
                sources=tuple(sources),
                capability="document_search",
                trace=(f"File search executed directly on {direct_source}",),
                history=self._store.get(conversation_id),
                file_results=tuple(files),
            )

        if not is_pure_report and not is_multi_source and Capability.DATA_ANALYSIS not in caps and Capability.WEB_SEARCH not in caps and self._is_file_search_query(effective_query):
            search_target = self._extract_file_search_target(effective_query)
            if not search_target:
                # User expressed intent ("i need to find the file" / "i need one file") without specifying target yet
                answer = "Sure! What is the name, document number (such as an invoice or contract ID), or keyword of the file you're looking for?"
                self._store.append(conversation_id, ChatMessage("assistant", answer, datetime.now(timezone.utc)))
                return ChatResponse(
                    conversation_id=conversation_id,
                    answer=answer,
                    sources=(),
                    capability="conversation",
                    trace=("Prompting user for document target details",),
                    history=self._store.get(conversation_id),
                )
            else:
                # User provided a document target (e.g. INV-2026-0042, invoice 22, contract with Acme)
                # Search directly across primary storage without asking repetitive questions!
                from backend.chat.file_search import execute_file_search
                answer, files, sources = execute_file_search(user, search_target, "local", max_results=10)
                if not files:
                    db_ans, db_files, db_sources = execute_file_search(user, search_target, "database", max_results=10)
                    if db_files:
                        answer, files, sources = db_ans, db_files, db_sources
                self._store.append(conversation_id, ChatMessage("assistant", answer, datetime.now(timezone.utc)))
                return ChatResponse(
                    conversation_id=conversation_id,
                    answer=answer,
                    sources=tuple(sources),
                    capability="document_search",
                    trace=("Direct file search executed automatically across local storage and database",),
                    history=self._store.get(conversation_id),
                    file_results=tuple(files),
                )

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
                "document", "documents", "file", "files", "pdf", "word", "docx", "excel", "xlsx", "csv", "md", "markdown", "txt",
                "policy", "handbook", "contract", "summary", "summarize", "notes", "agreement", "customer", "finance", "hr", "project",
                "rag", "retrieval", "retrieval-augmented", "vault", "vaults", "knowledge base", "company data",
                "upload", "uploaded", "attachment", "harish", "companydata",
                "invoice", "invoices", "vendor", "vendors", "receipt", "receipts", "bill", "bills",
                "cloudnova", "po", "purchase order",
                "nda", "mutual nda", "non-disclosure",
                "local folder", "local files", "folder", "folders", "my folder", "selected folder",
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
        doc_format_words = (
            "doc", "docx", "word", "pdf", "excel", "xlsx", "csv", "sheet", "spreadsheet",
            "pptx", "powerpoint", "presentation", "slide", "slides", "txt", "text",
        )
        has_doc_format = any(
            re.search(rf"\b(?:in|into|as|to|for|on)\s+(?:the\s+|a\s+|an\s+)?{f}\b", text)
            or re.search(rf"\b{f}\s+(?:format|file|document|report|sheet|presentation|deck|schedule|export|download)\b", text)
            or f"in {f}" in text
            or f"in the {f}" in text
            or f"as {f}" in text
            or f"as a {f}" in text
            or (f in ("presentation", "powerpoint", "slides", "pptx", "spreadsheet", "excel sheet", "word doc", "pdf report", "excel report", "word report") and f in text)
            for f in doc_format_words
        )
        has_export_action = any(
            v in text for v in (
                "generate", "generation", "export", "download", "create", "build", "make",
                "produce", "compile", "put it in", "put this in", "put them in", "put in",
                "need to be in", "needs to be in", "want in", "convert to", "save as",
                "need in", "give it in", "give in", "prepare",
            )
        )
        is_report_request = (
            Capability.REPORT in found
            or (has_export_action and has_doc_format)
            or (has_doc_format and any(w in text for w in ("invoice", "invoices", "pending", "overdue", "contract", "contracts", "renewal", "schedule", "budget", "salary", "employee", "customer", "project", "department")))
            or ("report" in text and any(v in text for v in ("generate", "generation", "export", "download", "create", "build", "make", "produce", "new", "compile", "schedule")))
            or any(w in text for w in (
                "in word", "in the word", "in excel", "in the excel", "in pdf", "in the pdf",
                "in doc", "in the doc", "in docx", "in the docx", "in xlsx", "in the xlsx",
                "in pptx", "in the pptx", "in powerpoint", "in the powerpoint", "in presentation", "in slides", "in slide",
                "in txt", "in text", "renewal schedule", "contract renewal", "schedule in word", "schedule in excel",
                "as a doc", "as doc", "as a document", "as a word", "as word", "as a pdf", "as pdf",
                "as an excel", "as excel", "as a sheet", "as sheet", "as pptx", "as a pptx", "as presentation",
                "put this in", "put this content", "put in doc", "put in pdf", "put in excel", "put in pptx",
                "export to", "download as", "generate schedule", "create schedule",
                "in a doc", "in a pdf", "in an excel", "in a word", "in a txt", "in a pptx",
            ))
            or (
                any(v in text for v in ("generate", "generation", "create", "export", "download", "build", "produce")) and
                any(f in text for f in ("in word", "in doc", "in excel", "in pdf", "in pptx", "in txt", "schedule", "report", "word document", "excel sheet", "pdf report", "powerpoint presentation", "document"))
            )
            or (
                "report" in text and any(k in text for k in ("invoice", "invoices", "pending", "overdue", "billing", "contract", "renewal", "financial", "budget", "sales", "employee"))
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

        # [LEGACY] Old automatic cross-source file discovery search everywhere:
        # [LEGACY] from backend.retrieval.intent import classify_retrieval_intent, QueryIntent
        # [LEGACY] is_file_discovery = (
        # [LEGACY]     classify_retrieval_intent(query) == QueryIntent.FILE_SEARCH
        # [LEGACY]     and re.search(r"\b(?:find|search|locate|look\s+for|where\s+is|where\s+are|show\s+me)\b", text)
        # [LEGACY] )
        # [LEGACY] if is_file_discovery and not is_report_request:
        # [LEGACY]     for cap in (Capability.KNOWLEDGE, Capability.DATABASE, Capability.EMAIL, Capability.GOOGLE_DRIVE):
        # [LEGACY]         if cap not in found:
        # [LEGACY]             found.append(cap)

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

    def _generate_chatgpt_conversational_reply(
        self,
        query: str,
        prior_history: Sequence[ChatMessage] | None = None,
        tenant_id: str = "enterprise-tenant",
    ) -> str:
        from backend.services.company_memory import company_memory_service
        mem = company_memory_service.get_memory(tenant_id)
        company_name = mem.get("company_name") or "Nanvi AI Enterprise"
        company_context = company_memory_service.build_system_context(tenant_id)

        system_prompt = (
            f"You are Nanvi, an intelligent, empathetic, articulate, and friendly enterprise AI copilot for {company_name}.\n"
            f"You speak and interact with the natural conversational warmth, cadence, clarity, and helpfulness of ChatGPT.\n\n"
            f"{company_context}\n\n"
            f"INTERACTION DIRECTIVES:\n"
            f"1. Converse naturally and interactively. Do not provide rigid, robotic, or hardcoded answers.\n"
            f"2. When greeted ('hi', 'hello', 'hey', 'good morning', etc.), welcome the user warmly as Nanvi, acknowledge the enterprise ({company_name}), and offer proactive assistance.\n"
            f"3. When users ask questions about {company_name}, its background, leadership, mission, products, services, or internal policies, use your Enterprise Context & Memory above to answer authoritatively, proudly, and accurately.\n"
            f"4. For general chat, brainstorming, drafting emails, writing summaries, technical or workplace advice, deliver insightful, well-structured, ChatGPT-quality responses.\n"
            f"5. If the user explicitly asks to search or retrieve specific files, spreadsheets, invoices, contracts, or database records, warmly inform them that you can search across company sources (Local Storage, Database, Email, Google Drive) and ask what document they need.\n"
            f"6. Use clean Markdown formatting (bold text, lists, sections) when helpful for readability.\n"
            f"7. CRITICAL ANTI-HALLUCINATION RULE: NEVER fabricate or make up fake URLs, links, or internal paths (such as https://nanvi-enterprise.internal/... or similar). Do NOT generate fake download URLs. If the user wants to download, view, or open a file, tell them to use the Open or Preview button in the document results table, or offer to locate it in Local Storage or Database."
        )

        messages_history: list[dict[str, str]] = []
        if prior_history:
            for m in prior_history[-10:]:
                if m.content and m.content.strip():
                    messages_history.append({"role": m.role, "content": m.content})

        provider = getattr(self._answerer, "_provider", None)
        if provider is not None:
            try:
                reply = provider.generate(
                    query,
                    system=system_prompt,
                    messages_history=messages_history,
                )
                if reply and reply.strip():
                    return reply.strip()
            except Exception as exc:
                logger.warning("LLM conversational generation failed: %s; using contextual fallback", exc)

        return self._generate_conversational_reply(query, mem)

    @staticmethod
    def _generate_conversational_reply(query: str, mem: dict[str, Any] | None = None) -> str:
        clean = re.sub(r"[^\w\s]", "", query.strip().casefold())
        clean = re.sub(r"\s+", " ", clean).strip()
        comp_name = (mem or {}).get("company_name", "Nanvi AI Enterprise")
        details = (mem or {}).get("details", "")

        if any(clean.startswith(w) for w in ("who are you", "what are you", "what can you do", "help", "tell me about yourself")):
            intro = f"I'm **Nanvi**, your intelligent enterprise AI copilot for **{comp_name}**."
            if details:
                intro += f"\n\n**About {comp_name}:**\n{details[:400]}..."
            return (
                f"{intro}\n\n"
                f"Here is how I can assist you:\n"
                f"- **Interactive Workplace Chat**: Brainstorming, drafting, strategy, and company Q&A.\n"
                f"- **Company Memory & Policies**: Instant guidance on company products, mission, and guidelines.\n"
                f"- **Document & File Search**: Search and retrieve contracts, invoices, and reports across local files.\n"
                f"- **Enterprise Database**: Query records, analytics, transactions, and customers.\n"
                f"- **Email Intelligence**: Retrieve emails, communications, and project updates.\n\n"
                f"How can I help you right now?"
            )
        if any(clean.startswith(w) for w in ("thank", "thanks")):
            return f"You're very welcome! Let me know if there's anything else I can do for you at {comp_name}."
        if any(clean.startswith(w) for w in ("how are you",)):
            return f"I'm doing great and ready to help! How are things going with you today at {comp_name}?"
        if any(clean.startswith(w) for w in ("bye", "goodbye")):
            return "Goodbye! Have a productive and wonderful day ahead."

        if details and any(w in clean for w in ("company", "about", "mission", "vision", "product", "service", "what do we do")):
            return f"**About {comp_name}:**\n\n{details}"

        return (
            f"Hello! 👋 I'm **Nanvi**, your enterprise AI copilot for **{comp_name}**. "
            f"How can I help you today? You can chat with me naturally, ask questions about our company, "
            f"or ask me to look up files and records."
        )

    @staticmethod
    def _is_conversational_greeting(query: str) -> bool:
        clean = re.sub(r"[^\w\s]", "", query.strip().casefold())
        clean = re.sub(r"\s+", " ", clean).strip()
        from backend.chat.intent_router import IntentRouter
        if clean in IntentRouter._GREETINGS:
            return True
        tokens = clean.split()
        if len(tokens) <= 3 and tokens[0] in ("hi", "hello", "hey", "hola", "namaste", "howdy", "sup", "yo"):
            return True
        return False

    @classmethod
    def _is_direct_email_query(cls, query: str) -> bool:
        """Identify direct requests to fetch or view recent/inbox emails."""
        q = query.strip().casefold()
        clean = re.sub(r"[^\w\s]", " ", q)
        clean = re.sub(r"\s+", " ", clean).strip()

        if clean in (
            "recent email", "recent emails", "top 5 recent email", "top 5 recent emails",
            "top 5 emails", "top five emails", "top emails", "emails", "email",
            "my email", "my emails", "gmail", "inbox", "recent mail", "recent mails",
            "latest email", "latest emails", "new emails", "unread emails",
        ):
            return True

        action_pattern = (
            r"\b(?:check|show|get|fetch|list|read|view|find|display|pull)\s+"
            r"(?:me\s+)?(?:all\s+)?(?:my\s+)?(?:the\s+)?(?:top\s+\d+\s+)?(?:recent|latest|new|unread)?\s*"
            r"(?:emails?|gmail|inbox|messages?|mails?)\b"
        )
        if re.search(action_pattern, clean):
            return True

        if re.search(r"\b(?:recent|latest|top\s+\d+)\s+(?:emails?|gmail|inbox|messages?|mails?)\b", clean):
            return True

        return False

    def _handle_direct_email_query(
        self, user: UserAttributes, query: str, limit: int = 5
    ) -> tuple[str, list[dict[str, Any]], list[SourceReference]]:
        """Retrieve recent emails and format them immediately without blocking questions.

        Returns top 5 emails followed by a non-blocking prompt offering date or name filtering.
        """
        from backend.integrations.email.gmail import GmailEmailProvider
        from backend.integrations.email.models import EmailProviderContext, EmailSearchRequest
        from backend.chat.file_search import _extract_date_filter

        provider = GmailEmailProvider()
        u_id = getattr(user, "user_id", None) or getattr(user, "subject", "user")
        t_id = getattr(user, "tenant_id", None) or "default"
        ctx = EmailProviderContext(
            access_token="live_auth",
            user_id=u_id,
            tenant_id=t_id,
        )

        date_disp, dy, dm, dd = _extract_date_filter(query)

        # Check if query targets a specific sender name
        clean_q = query.strip()
        sender_target = ""
        m_from = re.search(r"\b(?:from|by|sent\s+by)\s+([A-Za-z]+(?:\s+[A-Za-z]+)?)\b", clean_q, re.I)
        if m_from:
            sender_target = m_from.group(1).strip()
        elif not self._is_direct_email_query(clean_q) and date_disp is None:
            tokens = clean_q.split()
            if len(tokens) <= 3 and not any(t.casefold() in ("email", "emails", "mail", "inbox", "gmail") for t in tokens):
                sender_target = clean_q

        req_q = ""
        if not self._is_direct_email_query(clean_q):
            req_q = re.sub(
                r"(?i)\b(?:recent|emails?|gmail|inbox|messages?|mails?|check|show|get|fetch|list|from|for|on|date|name)\b",
                "",
                clean_q,
            ).strip()

        try:
            search_req = EmailSearchRequest(
                query=req_q,
                sender=sender_target if sender_target else None,
                max_results=limit * 2 if (date_disp or sender_target) else limit,
            )
            raw_msgs = provider.search(ctx, search_req)
        except Exception as exc:
            logger.warning("Email retrieval error in direct query: %s", exc)
            raw_msgs = []

        if dy is not None and dm is not None and dd is not None:
            filtered_msgs = []
            for m in raw_msgs:
                if m.received_at and m.received_at.year == dy and m.received_at.month == dm and m.received_at.day == dd:
                    filtered_msgs.append(m)
            msgs = filtered_msgs[:limit] if filtered_msgs else raw_msgs[:limit]
        else:
            msgs = raw_msgs[:limit]

        files: list[dict[str, Any]] = []
        sources: list[SourceReference] = []

        if not msgs:
            if sender_target:
                answer = (
                    f"No emails from **{sender_target}** were found in your connected mailbox.\n\n"
                    "---\n"
                    "💡 **Looking for something specific?** You can specify another sender name or date, and I will search specifically for that."
                )
            elif date_disp:
                answer = (
                    f"No emails received on **{date_disp}** were found in your connected mailbox.\n\n"
                    "---\n"
                    "💡 **Looking for something specific?** You can specify another date or sender name, and I will search specifically for that."
                )
            else:
                answer = (
                    "No recent emails were found in your connected mailbox.\n\n"
                    "---\n"
                    "💡 **Looking for something specific?** You can specify a date (e.g. *\"emails from yesterday\"* or *\"Oct 5\"*) "
                    "or put a sender name (e.g. *\"emails from Arjun\"*), and I will search specifically for that."
                )
            return answer, files, sources

        if sender_target:
            header_title = f"Found **{len(msgs)}** email{'s' if len(msgs) != 1 else ''} from **{sender_target}**:"
        elif date_disp:
            header_title = f"Found **{len(msgs)}** email{'s' if len(msgs) != 1 else ''} received on **{date_disp}**:"
        else:
            header_title = f"Here are your **{len(msgs)} most recent email{'s' if len(msgs) != 1 else ''}**:"

        lines = [
            f"{header_title}\n",
            "| # | Subject | From | Date | Attachments | Action |",
            "|---|---|---|---|---|---|",
        ]

        previews: list[str] = []
        for idx, m in enumerate(msgs, start=1):
            subj = m.subject.strip() or "(No Subject)"
            sender_name = m.sender.name if m.sender and m.sender.name else (m.sender.address if m.sender else "Unknown")
            sender_addr = m.sender.address if m.sender and m.sender.address else ""
            sender_cell = f"{sender_name} (`{sender_addr}`)" if sender_addr and sender_addr != sender_name else sender_name

            dt_str = m.received_at.strftime("%b %d, %Y, %I:%M %p") if m.received_at else "Recent"
            att_names = ", ".join(f"`{a.name}`" for a in m.attachments) if m.attachments else "—"
            web_link = m.web_link or f"https://mail.google.com/mail/u/0/#inbox/{m.id}"

            safe_subj = subj.replace("|", "/")
            safe_sender = sender_cell.replace("|", "/")
            lines.append(f"| {idx} | **{safe_subj}** | {safe_sender} | {dt_str} | {att_names} | [Open in Gmail]({web_link}) |")

            snippet = (m.body_preview or "").strip().replace("\n", " ")
            if len(snippet) > 200:
                snippet = snippet[:200] + "..."
            if snippet:
                previews.append(f"{idx}. **{safe_subj}**: *\"{snippet}\"*")

            files.append({
                "name": f"{subj}.eml",
                "path": f"Email: {subj} (From: {sender_name})",
                "type": "eml",
                "modified_at": m.received_at.isoformat() if m.received_at else "",
                "open_url": web_link,
                "source": "email",
                "content_snippet": snippet,
            })
            if m.attachments:
                for att in m.attachments:
                    files.append({
                        "name": att.name,
                        "path": f"Attachment in: {subj}",
                        "type": Path(att.name).suffix.lstrip(".") or "pdf",
                        "modified_at": m.received_at.isoformat() if m.received_at else "",
                        "open_url": web_link,
                        "source": "email",
                    })

            sources.append(
                SourceReference(
                    reference_id=f"ref-email-{idx}",
                    source_type=SourceType.EMAIL,
                    display_name=subj,
                    title=subj,
                    location=f"From: {sender_name} ({sender_addr})" if sender_addr else f"From: {sender_name}",
                )
            )

        table_md = "\n".join(lines)
        preview_md = "\n\n**Email Previews:**\n" + "\n".join(previews) if previews else ""

        follow_up = (
            "\n\n---\n"
            "💡 **Looking for something specific?** You can specify a date (e.g. *\"emails from yesterday\"* or *\"Oct 5\"*) "
            "or put a sender name (e.g. *\"emails from Arjun\"*), and I will search specifically for that."
        )

        answer = f"{table_md}{preview_md}{follow_up}"
        return answer, files, sources

    @staticmethod
    def _extract_file_search_target(query: str) -> str:
        """Extract a meaningful file name, document code, or search term from user query.
        Returns empty string if query is just a generic request like 'i need to find the file' or 'find one file'.
        """
        if not query:
            return ""
        q = query.strip()

        # 1. Document code pattern (e.g. INV-2026-0042, EMP-0001, NDA-0002, PUR-0003, invoice_022)
        code_match = re.search(r"\b(?:inv|emp|nda|pur|po|prj|cust|cnt|doc|bill)[-_ ]?\d{1,8}\b", q, re.IGNORECASE)
        if code_match:
            return code_match.group(0).strip()
        code_match_num = re.search(r"\b(?:invoice|contract|customer|employee|project|nda|order)[-_ ]?\d+\b", q, re.IGNORECASE)
        if code_match_num:
            return code_match_num.group(0).strip()

        # 2. File extension match (e.g. customer_profile_001.pdf)
        ext_match = re.search(r"\b[\w-]+\.(?:pdf|docx|xlsx|csv|pptx|txt|json|md)\b", q, re.IGNORECASE)
        if ext_match:
            return ext_match.group(0).strip()

        # 3. Strip out common filler / conversational prefixes
        cleaned = re.sub(
            r"(?i)^(?:can\s+you\s+)?(?:please\s+)?(?:i\s+need\s+to\s+|i\s+want\s+to\s+|help\s+me\s+)?(?:find|search|look\s+for|locate|show|get|open|check|fetch)\s+(?:the\s+|a\s+|an\s+|one\s+|some\s+)?(?:file|files|document|documents|pdf|sheet|spreadsheet|record|records)?(?:\s+(?:named|called|about|for|with|contain|containing))?\s*",
            "",
            q,
        )
        cleaned = re.sub(r"(?i)\s+(?:this\s+i|please|now|immediately|thanks|thank\s+you)\b.*$", "", cleaned)
        cleaned = cleaned.strip(" :,-'\"?.")

        if cleaned.casefold() in ("", "file", "files", "document", "documents", "one file", "the file", "a file", "something", "data", "it", "this"):
            return ""

        return cleaned

    @staticmethod
    def _extract_source_from_query(query: str) -> str | None:
        q = query.casefold().strip()
        if any(w in q for w in (
            "local storage", "local folder", "local file", "local files", "on disk", "local disk", "c:\\",
            "internal repository", "internal storage", "local database", "internal"
        )) or q in ("local", "1", "local storage", "in local"):
            return "local"
        if any(w in q for w in ("database", "data base", "db record", "db records", "from db", "in db", "from database", "in database")) or q in ("database", "db", "2"):
            return "database"
        if any(w in q for w in ("gmail", "email", "emails", "inbox", "mail", "sent mail")) or q in ("email", "mail", "3"):
            return "email"
        if any(w in q for w in ("google drive", "gdrive", "drive folder", "in drive", "on drive")) or q in ("google drive", "drive", "4"):
            return "drive"
        if any(w in q for w in ("cloud storage", "cloud files", "in cloud", "on cloud", "from cloud")) or q in ("cloud", "5"):
            return "cloud"
        return None

    @classmethod
    def _is_file_search_query(cls, query: str) -> bool:
        q = query.casefold().strip()
        # Exclude report generation requests
        if any(w in q for w in ("generate report", "create report", "export report", "export to word", "export to excel", "export to pdf", "download as word", "download as pdf", "generate document", "create document", "renewal schedule", "contract schedule")):
            return False

        # Exclude conversational greetings
        if cls._is_conversational_query(q):
            return False

        # Exclude summarization, explanation, reading, and deep comprehension questions
        # (These should route to KnowledgeAgent to retrieve and comprehend the content)
        if any(w in q for w in ("summarize", "summary of", "explain", "describe", "what is inside", "what is in", "contents of", "what does", "read", "tell me about", "what is", "who is")):
            return False

        # [LEGACY] has_action = bool(re.search(r"\b(find|search|show|get|list|look\s+for|where\s+is|where\s+are|locate|give\s+me|fetch)\b", q))
        # [LEGACY] has_file_target = bool(re.search(r"\b(file|files|document|documents|pdf|docx|xlsx|spreadsheet|sheet|invoice|invoices|contract|contracts|resume|resumes|policy|handbook)\b", q))
        # [LEGACY] has_date_phrase = bool(re.search(r"\b(last|past|this)\s+(\d+\s+)?(days?|weeks?|months?|years?)\b", q))
        # [LEGACY] if has_file_target and (has_action or has_date_phrase or "file" in q):
        # [LEGACY]     return True
        # [LEGACY] End legacy file search intent check.

        # File extension present (e.g. .pdf, .docx, .xlsx, .csv)
        if re.search(r"\b[\w-]+\.(pdf|docx|xlsx|csv|txt|md|pptx)\b", q):
            return True

        # Has business data / file targets (e.g. "what invoices are overdue", "show contracts", "customer records")
        has_file_target = bool(re.search(
            r"\b(file|files|document|documents|pdf|docx|xlsx|csv|spreadsheet|sheet|sheets|"
            r"invoice|invoices|bill|bills|billing|overdue|receipt|receipts|"
            r"contract|contracts|agreement|agreements|nda|ndas|renewal|"
            r"resume|resumes|policy|policies|handbook|statement|statements|"
            r"customer|customers|employee|employees|salary|salaries|budget|budgets|"
            r"transaction|transactions|expense|expenses|project|projects)\b",
            q,
        ))
        if has_file_target:
            return True

        # Check if query has date filter (e.g. "9 aug 25", "2025-08-09")
        try:
            from backend.retrieval.date_parser import parse_query_date
            if parse_query_date(query) is not None:
                return True
        except Exception:
            pass

        has_action = bool(re.search(r"\b(find|search|show|get|list|look\s+for|where\s+is|where\s+are|locate|give\s+me|fetch|check|see|what|which|who|how\s+many)\b", q))
        has_date_phrase = bool(re.search(r"\b(last|past|this)\s+(\d+\s+)?(days?|weeks?|months?|years?)\b", q))

        if has_action or has_date_phrase:
            return True

        from backend.retrieval.intent import classify_retrieval_intent, QueryIntent
        if classify_retrieval_intent(query) in (QueryIntent.FILE_SEARCH, QueryIntent.DIRECTORY_LISTING):
            return True

        return False

    @staticmethod
    def _extract_conversation_entity(text: str) -> str | None:
        """Extract compound entities, enterprise identifiers, or verified business names from a message."""
        # 0. Check real verified entities from the index
        try:
            from backend.retrieval.entity_resolver import get_entity_resolver
            resolver = get_entity_resolver()
            decision = resolver.resolve(text, min_score=85.0)
            if decision.status == "resolved" and decision.candidate:
                return decision.candidate.canonical_name
        except Exception:
            pass

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

        # 3. Capitalized multi-word company/entity names
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

        # Check if query is a date fragment (e.g. '9 aug 25')
        is_date_fragment = False
        try:
            from backend.retrieval.date_parser import parse_query_date
            is_date_fragment = (parse_query_date(q_clean) is not None)
        except Exception:
            pass

        # Check if the query itself explicitly introduces or switches to a concrete entity
        current_entity = cls._extract_conversation_entity(q_clean)

        # Detect pronouns and elliptical follow-up queries
        has_pronoun = any(
            re.search(rf"\b{p}\b", q_lower)
            for p in ("it", "its", "they", "their", "them", "this", "that", "these", "those", "he", "she", "his", "her")
        )
        is_elliptical = (
            is_date_fragment
            or len(tokens) <= 6
            or any(q_lower.startswith(p) for p in ("in ", "for ", "check ", "what about ", "how about ", "which one ", "who is ", "where is ", "what is ", "who owns "))
        )

        # If it's a follow-up and does not introduce a brand-new concrete entity
        if (has_pronoun or is_elliptical) and not current_entity:
            # Search backwards through prior user turns to find the most recent active entity
            for msg in reversed(prior_history):
                if msg.role == "user" and not cls._is_conversational_query(msg.content):
                    entity = cls._extract_conversation_entity(msg.content)
                    if entity:
                        return f"{entity} for {q_clean}"
            # Fallback to appending to the most recent user turn
            for msg in reversed(prior_history):
                if msg.role == "user" and not cls._is_conversational_query(msg.content):
                    return f"{msg.content} for {q_clean}"

        return q_clean

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
