"""Application composition root.

Wires all dependencies into a single ``ChatService`` instance ready for the
API layer.  This module is the ONLY place where infrastructure dependencies
(LLM keys, database connections, file system roots) are assembled.
The API layer receives fully-constructed services with no knowledge of wiring.

Security invariants:
- GROQ_API_KEY stays in the LLM provider; never in graph state / prompts / responses
- DATABASE_URL stays in the repository; never exposed to agents or LLM
- JWT_SECRET stays in the dev token validator; never exposed externally
"""
from __future__ import annotations

import logging

from backend.core.config import settings
from backend.observability.logging import log_event

logger = logging.getLogger(__name__)


def _create_llm_provider():
    """Create an LLM provider from settings.  Returns None if not configured."""
    from backend.llm.provider import LLMNotConfiguredError

    provider_name = settings.llm_provider
    model = settings.llm_model

    if provider_name == "groq":
        from backend.llm.groq_provider import GroqProvider
        try:
            return GroqProvider(api_key=settings.groq_api_key, model=model)
        except LLMNotConfiguredError:
            log_event(logger, "llm_not_configured", logging.WARNING, provider="groq")
            return None
    else:
        log_event(
            logger, "llm_provider_unsupported", logging.WARNING,
            provider=provider_name,
        )
        return None


def _create_authorization():
    from backend.security.authorization import AuthorizationService
    return AuthorizationService()


def _create_audit():
    from backend.security.audit import AuditLogger, InMemoryAuditSink
    return AuditLogger(InMemoryAuditSink())


def _create_source_references(authorization, audit):
    from backend.sources.service import SourceReferenceService
    from backend.sources.dependencies import get_source_store
    store = get_source_store()
    return SourceReferenceService(authorization, audit, store)


def _create_tool_gateway(authorization, audit):
    from backend.agents.security_gateway import SecureToolGateway
    return SecureToolGateway(authorization, audit)


def _create_retrieval_service(authorization, audit, source_references):
    """Create the knowledge retrieval service if possible."""
    from backend.retrieval.keyword import KeywordRetriever
    from backend.retrieval.reranker import NoOpReranker
    from backend.retrieval.service import KnowledgeRetrievalService

    try:
        return KnowledgeRetrievalService(
            embedding_provider=None,  # Vector search is optional
            vector_store=None,
            keyword_retriever=KeywordRetriever(),
            reranker=NoOpReranker(),
            authorization=authorization,
            audit_logger=audit,
            source_references=source_references,
        )
    except Exception as exc:
        log_event(
            logger, "retrieval_service_init_failed", logging.WARNING,
            exception_type=type(exc).__name__,
        )
        return None


def _create_agents(
    retrieval_service,
    source_references,
    gateway,
    authorization,
    audit,
):
    """Create fully wired capability agents."""
    from backend.agents.capability_agents import (
        KnowledgeAgent, DatabaseAgent, EmailAgent,
        DataAnalysisAgent, ReportAgent,
    )
    from backend.agents.models import Capability
    from backend.integrations.files.company_data_service import CompanyDataService
    from backend.integrations.email.gmail import GmailEmailProvider
    from backend.integrations.email.service import EmailService

    agents = {}

    # Initialize company data service using the persisted active folder path
    company_data = CompanyDataService.get_instance()
    try:
        company_data.ensure_indexed()
    except Exception as exc:
        logger.warning("Could not pre-index CompanyData: %s", exc)

    # Knowledge Agent — wired to local C:\CompanyData and RAG retrieval
    knowledge = KnowledgeAgent(
        retrieval_service=retrieval_service,
        source_references=source_references,
        gateway=gateway,
        company_data_service=company_data,
    )
    agents[knowledge.capability] = knowledge

    # Database Service & Agent — supports Supabase Cloud PostgreSQL, Local PostgreSQL, and SQLite
    from backend.integrations.database import (
        DatabaseService, DatabaseTool, ReadOnlySQLValidator, SQLValidationPipeline,
        PostgreSQLRepository, SQLiteEnterpriseRepository, ENTERPRISE_TABLE_POLICY,
    )
    from backend.integrations.database.planner import DefaultDatabaseQueryPlanner

    db_repo = None

    # First check Connections Hub for configured PostgreSQL or Supabase connection
    try:
        from backend.connections.manager import get_connection_manager
        from backend.security.models import UserIdentity
        from backend.security.authorization.rbac import Role
        cm = get_connection_manager()
        sys_user = UserIdentity(
            subject="system",
            issuer="internal",
            tenant_id="enterprise-tenant",
            roles=frozenset({Role.IT_ADMIN, Role.CEO}),
        )
        try:
            client = cm.get_client_for_agent("postgresql", sys_user)
            if hasattr(client, "execute_query") or hasattr(client, "_pool"):
                db_repo = client
                logger.info("DatabaseService connected via Connections Hub PostgreSQL connection.")
        except Exception:
            pass
    except Exception as exc:
        logger.debug("Connections Hub DB check skipped: %s", exc)

    if db_repo is None:
        target_dsn = settings.supabase_database_url or settings.database_url
        if target_dsn:
            try:
                db_repo = PostgreSQLRepository(
                    target_dsn,
                    pool_min_size=settings.database_pool_min_size,
                    pool_max_size=settings.database_pool_max_size,
                    timeout_ms=settings.database_statement_timeout_ms,
                )
                with db_repo._pool.connection() as test_conn:
                    pass
                logger.info(
                    "Connected DatabaseService to %s database successfully",
                    "Supabase Cloud" if settings.supabase_database_url else "Local PostgreSQL",
                )
            except Exception as exc:
                logger.warning("Could not connect to PostgreSQL/Supabase (%s). Using local SQLite fallback.", exc)
                db_repo = None

    if db_repo is None:
        db_repo = SQLiteEnterpriseRepository()


    db_validator = ReadOnlySQLValidator(ENTERPRISE_TABLE_POLICY, require_column_policy=True)
    database_service = DatabaseService(
        repository=db_repo,
        authorization=authorization,
        audit_logger=audit,
        validation=SQLValidationPipeline(db_validator),
        tenant_id="enterprise-tenant",
    )
    database_tool = DatabaseTool(database_service)
    database_planner = DefaultDatabaseQueryPlanner()

    database = DatabaseAgent(
        tool=database_tool,
        planner=database_planner,
        sources=source_references,
        gateway=gateway,
    )
    agents[database.capability] = database

    # Email Agent — wired to Google Gmail provider
    gmail_provider = GmailEmailProvider()
    email_service = EmailService(
        repository=gmail_provider,
        authorization=authorization,
        audit_logger=audit,
        source_service=source_references,
    )
    email = EmailAgent(
        email_service=email_service,
        source_references=source_references,
        gateway=gateway,
    )
    agents[email.capability] = email

    # Data Analysis Agent — wired to deterministic engine and database tool
    from backend.analysis.engine import DeterministicAnalysisEngine
    analysis = DataAnalysisAgent(
        analysis_engine=DeterministicAnalysisEngine(),
        source_references=source_references,
        gateway=gateway,
        database_tool=database_tool,
        company_data_service=company_data,
    )
    agents[analysis.capability] = analysis

    # Report Agent — wired to real ReportService, database tool, and company data
    from backend.reports.service import ReportService
    from backend.api.report_routes import _storage as report_storage
    report_service = ReportService(report_storage, authorization, audit)
    report = ReportAgent(
        report_service=report_service,
        source_references=source_references,
        gateway=gateway,
        database_tool=database_tool,
        company_data_service=company_data,
    )
    agents[report.capability] = report

    # Web Search Agent — wired to Tavily Web Search and secure gateway
    from backend.integrations.web.service import WebSearchService
    from backend.agents.capability_agents import WebSearchAgent

    web_service = WebSearchService(settings.tavily_api_key)
    web_agent = WebSearchAgent(
        web_search_service=web_service,
        sources=source_references,
        gateway=gateway,
    )
    agents[web_agent.capability] = web_agent

    # Google Drive Agent
    from backend.agents.capability_agents import GoogleDriveAgent
    conn_mgr = None
    try:
        from backend.connections.manager import get_connection_manager
        conn_mgr = get_connection_manager()
    except Exception:
        pass
    drive_agent = GoogleDriveAgent(
        source_references=source_references,
        connection_manager=conn_mgr,
    )
    agents[drive_agent.capability] = drive_agent

    return agents


def create_chat_service():
    """Assemble the complete ChatService with all real dependencies.

    This is the single entrypoint called by the API layer.
    """
    from backend.agents.orchestrator import EnterpriseOrchestrator
    from backend.chat.service import ChatService, InMemoryConversationStore, DeterministicTestAnswerer

    # Core security services
    authorization = _create_authorization()
    audit = _create_audit()
    source_references = _create_source_references(authorization, audit)
    gateway = _create_tool_gateway(authorization, audit)

    # LLM provider
    llm_provider = _create_llm_provider()

    # Answerer: use LLM if configured, otherwise fall back to deterministic
    if llm_provider is not None:
        from backend.llm.answerer import LLMChatAnswerer
        answerer = LLMChatAnswerer(llm_provider)
        log_event(logger, "chat_service_llm_configured", provider=settings.llm_provider, model=settings.llm_model)
    else:
        answerer = DeterministicTestAnswerer()
        log_event(logger, "chat_service_deterministic_answerer", logging.WARNING)

    # Retrieval service for KnowledgeAgent
    retrieval_service = _create_retrieval_service(authorization, audit, source_references)

    # All capability agents
    agents = _create_agents(retrieval_service, source_references, gateway, authorization, audit)

    # Orchestrator
    orchestrator = EnterpriseOrchestrator(agents=agents)

    # Conversation store (in-memory for development; production uses durable store)
    store = InMemoryConversationStore()

    service = ChatService(orchestrator, answerer, store)
    log_event(logger, "chat_service_ready", agent_count=len(agents))
    return service
