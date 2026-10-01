"""Provider Registry — data-driven catalog of all providers.

The registry holds provider metadata and code implementations.  The frontend
renders the catalog from ``GET /api/connections/providers`` and hard-codes no
provider list.  Providers that lack required server configuration report
``available: false, reason: "not_configured"``.

Adding a new provider = one module + ``registry.register(provider)``.
"""
from __future__ import annotations

import logging
from typing import Any

from backend.connections.base import BaseProvider, ProviderMetadata
from backend.connections.schemas import ProviderPublic

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# Phase 2 catalog entries (data only, no code)
# ═══════════════════════════════════════════════════════════════

_CATALOG_ENTRIES: list[dict[str, Any]] = [
    # ── Communication ────────────────────────────────────────
    {"id": "outlook", "name": "Outlook", "categories": ["Communication"], "icon": "outlook", "description": "Microsoft Outlook email and calendar", "auth_type": "oauth2"},
    {"id": "microsoft365", "name": "Microsoft 365", "categories": ["Communication"], "icon": "microsoft365", "description": "Microsoft 365 suite (Outlook, Teams, OneDrive)", "auth_type": "oauth2"},
    {"id": "slack", "name": "Slack", "categories": ["Communication"], "icon": "slack", "description": "Slack workspace messaging and channels", "auth_type": "oauth2"},
    {"id": "teams", "name": "Microsoft Teams", "categories": ["Communication"], "icon": "teams", "description": "Microsoft Teams chat and meetings", "auth_type": "oauth2"},
    {"id": "discord", "name": "Discord", "categories": ["Communication"], "icon": "discord", "description": "Discord server messaging", "auth_type": "oauth2"},
    {"id": "zoom", "name": "Zoom", "categories": ["Communication"], "icon": "zoom", "description": "Zoom meetings and webinars", "auth_type": "oauth2"},
    {"id": "imap", "name": "IMAP", "categories": ["Communication"], "icon": "mail", "description": "Generic IMAP email connection", "auth_type": "db_password"},
    {"id": "smtp", "name": "SMTP", "categories": ["Communication"], "icon": "mail", "description": "Generic SMTP email sending", "auth_type": "db_password"},
    # ── Storage / Documents ──────────────────────────────────
    {"id": "google_drive", "name": "Google Drive", "categories": ["Storage / Documents"], "icon": "googledrive", "description": "Google Drive files and documents", "auth_type": "oauth2"},
    {"id": "onedrive", "name": "OneDrive", "categories": ["Storage / Documents"], "icon": "onedrive", "description": "Microsoft OneDrive cloud storage", "auth_type": "oauth2"},
    {"id": "sharepoint", "name": "SharePoint", "categories": ["Storage / Documents"], "icon": "sharepoint", "description": "Microsoft SharePoint document libraries", "auth_type": "oauth2"},
    {"id": "dropbox", "name": "Dropbox", "categories": ["Storage / Documents"], "icon": "dropbox", "description": "Dropbox cloud storage", "auth_type": "oauth2"},
    {"id": "box", "name": "Box", "categories": ["Storage / Documents"], "icon": "box", "description": "Box enterprise cloud storage", "auth_type": "oauth2"},
    {"id": "s3", "name": "Amazon S3", "categories": ["Storage / Documents", "Cloud"], "icon": "aws", "description": "AWS S3 object storage", "auth_type": "api_key"},
    {"id": "azure_blob", "name": "Azure Blob Storage", "categories": ["Storage / Documents", "Cloud"], "icon": "azure", "description": "Azure Blob Storage", "auth_type": "api_key"},
    {"id": "gcs", "name": "Google Cloud Storage", "categories": ["Storage / Documents", "Cloud"], "icon": "gcp", "description": "GCS buckets and objects", "auth_type": "service_account"},
    {"id": "minio", "name": "MinIO", "categories": ["Storage / Documents"], "icon": "minio", "description": "MinIO S3-compatible object storage", "auth_type": "api_key"},
    {"id": "ftp", "name": "FTP", "categories": ["Storage / Documents"], "icon": "folder", "description": "FTP file transfer", "auth_type": "db_password"},
    {"id": "sftp", "name": "SFTP", "categories": ["Storage / Documents"], "icon": "folder", "description": "SFTP secure file transfer", "auth_type": "db_password"},
    {"id": "network_folder", "name": "Network Folder", "categories": ["Storage / Documents"], "icon": "folder", "description": "SMB / NFS network shared folder", "auth_type": "filesystem"},
    # ── SQL Databases ────────────────────────────────────────
    {"id": "mysql", "name": "MySQL", "categories": ["SQL Databases"], "icon": "mysql", "description": "MySQL relational database", "auth_type": "db_password"},
    {"id": "mariadb", "name": "MariaDB", "categories": ["SQL Databases"], "icon": "mariadb", "description": "MariaDB relational database", "auth_type": "db_password"},
    {"id": "sqlserver", "name": "SQL Server", "categories": ["SQL Databases"], "icon": "sqlserver", "description": "Microsoft SQL Server", "auth_type": "db_password"},
    {"id": "oracle", "name": "Oracle", "categories": ["SQL Databases"], "icon": "oracle", "description": "Oracle Database", "auth_type": "db_password"},
    {"id": "sqlite", "name": "SQLite", "categories": ["SQL Databases"], "icon": "sqlite", "description": "SQLite embedded database", "auth_type": "filesystem"},
    {"id": "db2", "name": "IBM Db2", "categories": ["SQL Databases"], "icon": "ibm", "description": "IBM Db2 database", "auth_type": "db_password"},
    {"id": "cockroachdb", "name": "CockroachDB", "categories": ["SQL Databases"], "icon": "cockroachdb", "description": "CockroachDB distributed SQL", "auth_type": "db_password"},
    {"id": "tidb", "name": "TiDB", "categories": ["SQL Databases"], "icon": "tidb", "description": "TiDB distributed SQL", "auth_type": "db_password"},
    # ── NoSQL / Data Stores ──────────────────────────────────
    {"id": "mongodb", "name": "MongoDB", "categories": ["NoSQL / Data Stores"], "icon": "mongodb", "description": "MongoDB document database", "auth_type": "db_password"},
    {"id": "atlas", "name": "MongoDB Atlas", "categories": ["NoSQL / Data Stores", "Cloud"], "icon": "mongodb", "description": "MongoDB Atlas cloud database", "auth_type": "db_password"},
    {"id": "redis", "name": "Redis", "categories": ["NoSQL / Data Stores"], "icon": "redis", "description": "Redis in-memory data store", "auth_type": "db_password"},
    {"id": "dynamodb", "name": "DynamoDB", "categories": ["NoSQL / Data Stores", "Cloud"], "icon": "aws", "description": "AWS DynamoDB", "auth_type": "api_key"},
    {"id": "cassandra", "name": "Cassandra", "categories": ["NoSQL / Data Stores"], "icon": "cassandra", "description": "Apache Cassandra", "auth_type": "db_password"},
    {"id": "couchbase", "name": "Couchbase", "categories": ["NoSQL / Data Stores"], "icon": "couchbase", "description": "Couchbase document database", "auth_type": "db_password"},
    {"id": "firestore", "name": "Firestore", "categories": ["NoSQL / Data Stores", "Cloud"], "icon": "firebase", "description": "Google Cloud Firestore", "auth_type": "service_account"},
    {"id": "neo4j", "name": "Neo4j", "categories": ["NoSQL / Data Stores"], "icon": "neo4j", "description": "Neo4j graph database", "auth_type": "db_password"},
    # ── Vector / Search ──────────────────────────────────────
    {"id": "pinecone", "name": "Pinecone", "categories": ["Vector / Search"], "icon": "pinecone", "description": "Pinecone vector database", "auth_type": "api_key"},
    {"id": "qdrant", "name": "Qdrant", "categories": ["Vector / Search"], "icon": "qdrant", "description": "Qdrant vector search engine", "auth_type": "api_key"},
    {"id": "weaviate", "name": "Weaviate", "categories": ["Vector / Search"], "icon": "weaviate", "description": "Weaviate vector database", "auth_type": "api_key"},
    {"id": "milvus", "name": "Milvus", "categories": ["Vector / Search"], "icon": "milvus", "description": "Milvus vector database", "auth_type": "api_key"},
    {"id": "chroma", "name": "Chroma", "categories": ["Vector / Search"], "icon": "chroma", "description": "Chroma embedding database", "auth_type": "api_key"},
    {"id": "faiss", "name": "FAISS", "categories": ["Vector / Search"], "icon": "meta", "description": "Facebook AI Similarity Search", "auth_type": "none"},
    {"id": "pgvector", "name": "pgvector", "categories": ["Vector / Search", "SQL Databases"], "icon": "postgresql", "description": "PostgreSQL pgvector extension", "auth_type": "db_password"},
    {"id": "redis_vector", "name": "Redis Vector", "categories": ["Vector / Search"], "icon": "redis", "description": "Redis vector similarity search", "auth_type": "db_password"},
    {"id": "elasticsearch", "name": "Elasticsearch", "categories": ["Vector / Search"], "icon": "elasticsearch", "description": "Elasticsearch search and analytics", "auth_type": "api_key"},
    {"id": "opensearch", "name": "OpenSearch", "categories": ["Vector / Search"], "icon": "opensearch", "description": "OpenSearch search engine", "auth_type": "api_key"},
    {"id": "meilisearch", "name": "Meilisearch", "categories": ["Vector / Search"], "icon": "meilisearch", "description": "Meilisearch instant search", "auth_type": "api_key"},
    {"id": "typesense", "name": "Typesense", "categories": ["Vector / Search"], "icon": "typesense", "description": "Typesense search engine", "auth_type": "api_key"},
    {"id": "algolia", "name": "Algolia", "categories": ["Vector / Search"], "icon": "algolia", "description": "Algolia search-as-a-service", "auth_type": "api_key"},
    # ── Developer Tools ──────────────────────────────────────
    {"id": "gitlab", "name": "GitLab", "categories": ["Developer Tools"], "icon": "gitlab", "description": "GitLab repositories and CI/CD", "auth_type": "oauth2"},
    {"id": "bitbucket", "name": "Bitbucket", "categories": ["Developer Tools"], "icon": "bitbucket", "description": "Bitbucket repositories", "auth_type": "oauth2"},
    {"id": "azure_devops", "name": "Azure DevOps", "categories": ["Developer Tools"], "icon": "azure", "description": "Azure DevOps boards and repos", "auth_type": "oauth2"},
    {"id": "jira", "name": "Jira", "categories": ["Developer Tools"], "icon": "jira", "description": "Atlassian Jira project tracking", "auth_type": "oauth2"},
    {"id": "linear", "name": "Linear", "categories": ["Developer Tools"], "icon": "linear", "description": "Linear project management", "auth_type": "oauth2"},
    {"id": "trello", "name": "Trello", "categories": ["Developer Tools"], "icon": "trello", "description": "Trello boards and cards", "auth_type": "api_key"},
    {"id": "asana", "name": "Asana", "categories": ["Developer Tools"], "icon": "asana", "description": "Asana work management", "auth_type": "oauth2"},
    {"id": "clickup", "name": "ClickUp", "categories": ["Developer Tools"], "icon": "clickup", "description": "ClickUp project management", "auth_type": "oauth2"},
    {"id": "jenkins", "name": "Jenkins", "categories": ["Developer Tools"], "icon": "jenkins", "description": "Jenkins CI/CD automation", "auth_type": "api_key"},
    {"id": "github_actions", "name": "GitHub Actions", "categories": ["Developer Tools"], "icon": "github", "description": "GitHub Actions CI/CD", "auth_type": "oauth2"},
    {"id": "gitlab_ci", "name": "GitLab CI", "categories": ["Developer Tools"], "icon": "gitlab", "description": "GitLab CI/CD pipelines", "auth_type": "oauth2"},
    # ── Cloud ────────────────────────────────────────────────
    {"id": "aws", "name": "AWS", "categories": ["Cloud"], "icon": "aws", "description": "Amazon Web Services", "auth_type": "api_key"},
    {"id": "azure", "name": "Azure", "categories": ["Cloud"], "icon": "azure", "description": "Microsoft Azure", "auth_type": "oauth2"},
    {"id": "gcp", "name": "Google Cloud", "categories": ["Cloud"], "icon": "gcp", "description": "Google Cloud Platform", "auth_type": "service_account"},
    {"id": "cloudflare", "name": "Cloudflare", "categories": ["Cloud"], "icon": "cloudflare", "description": "Cloudflare CDN and services", "auth_type": "api_key"},
    {"id": "digitalocean", "name": "DigitalOcean", "categories": ["Cloud"], "icon": "digitalocean", "description": "DigitalOcean cloud infrastructure", "auth_type": "api_key"},
    {"id": "oracle_cloud", "name": "Oracle Cloud", "categories": ["Cloud"], "icon": "oracle", "description": "Oracle Cloud Infrastructure", "auth_type": "api_key"},
    {"id": "ibm_cloud", "name": "IBM Cloud", "categories": ["Cloud"], "icon": "ibm", "description": "IBM Cloud platform", "auth_type": "api_key"},
    {"id": "vercel", "name": "Vercel", "categories": ["Cloud"], "icon": "vercel", "description": "Vercel deployment platform", "auth_type": "api_key"},
    {"id": "netlify", "name": "Netlify", "categories": ["Cloud"], "icon": "netlify", "description": "Netlify web deployment", "auth_type": "api_key"},
    {"id": "render", "name": "Render", "categories": ["Cloud"], "icon": "render", "description": "Render cloud platform", "auth_type": "api_key"},
    {"id": "railway", "name": "Railway", "categories": ["Cloud"], "icon": "railway", "description": "Railway deployment platform", "auth_type": "api_key"},
    {"id": "flyio", "name": "Fly.io", "categories": ["Cloud"], "icon": "flyio", "description": "Fly.io edge compute platform", "auth_type": "api_key"},
    {"id": "firebase", "name": "Firebase", "categories": ["Cloud"], "icon": "firebase", "description": "Google Firebase platform", "auth_type": "service_account"},
    # ── CRM / Sales ──────────────────────────────────────────
    {"id": "salesforce", "name": "Salesforce", "categories": ["CRM / Sales"], "icon": "salesforce", "description": "Salesforce CRM", "auth_type": "oauth2"},
    {"id": "hubspot", "name": "HubSpot", "categories": ["CRM / Sales"], "icon": "hubspot", "description": "HubSpot CRM and marketing", "auth_type": "oauth2"},
    {"id": "zoho_crm", "name": "Zoho CRM", "categories": ["CRM / Sales"], "icon": "zoho", "description": "Zoho CRM platform", "auth_type": "oauth2"},
    {"id": "dynamics", "name": "Dynamics 365", "categories": ["CRM / Sales"], "icon": "microsoft365", "description": "Microsoft Dynamics 365", "auth_type": "oauth2"},
    {"id": "pipedrive", "name": "Pipedrive", "categories": ["CRM / Sales"], "icon": "pipedrive", "description": "Pipedrive sales CRM", "auth_type": "api_key"},
    {"id": "freshsales", "name": "Freshsales", "categories": ["CRM / Sales"], "icon": "freshworks", "description": "Freshsales CRM", "auth_type": "api_key"},
    # ── HR ───────────────────────────────────────────────────
    {"id": "workday", "name": "Workday", "categories": ["HR"], "icon": "workday", "description": "Workday HCM", "auth_type": "oauth2"},
    {"id": "successfactors", "name": "SuccessFactors", "categories": ["HR"], "icon": "sap", "description": "SAP SuccessFactors", "auth_type": "oauth2"},
    {"id": "bamboohr", "name": "BambooHR", "categories": ["HR"], "icon": "bamboohr", "description": "BambooHR platform", "auth_type": "api_key"},
    {"id": "zoho_people", "name": "Zoho People", "categories": ["HR"], "icon": "zoho", "description": "Zoho People HRMS", "auth_type": "oauth2"},
    {"id": "keka", "name": "Keka", "categories": ["HR"], "icon": "keka", "description": "Keka HR platform", "auth_type": "api_key"},
    {"id": "darwinbox", "name": "Darwinbox", "categories": ["HR"], "icon": "darwinbox", "description": "Darwinbox HCM", "auth_type": "api_key"},
    {"id": "adp", "name": "ADP", "categories": ["HR"], "icon": "adp", "description": "ADP workforce management", "auth_type": "oauth2"},
    # ── Finance ──────────────────────────────────────────────
    {"id": "sap", "name": "SAP", "categories": ["Finance"], "icon": "sap", "description": "SAP ERP and financial systems", "auth_type": "oauth2"},
    {"id": "oracle_financials", "name": "Oracle Financials", "categories": ["Finance"], "icon": "oracle", "description": "Oracle Financial Cloud", "auth_type": "oauth2"},
    {"id": "quickbooks", "name": "QuickBooks", "categories": ["Finance"], "icon": "quickbooks", "description": "Intuit QuickBooks accounting", "auth_type": "oauth2"},
    {"id": "xero", "name": "Xero", "categories": ["Finance"], "icon": "xero", "description": "Xero cloud accounting", "auth_type": "oauth2"},
    {"id": "zoho_books", "name": "Zoho Books", "categories": ["Finance"], "icon": "zoho", "description": "Zoho Books accounting", "auth_type": "oauth2"},
    {"id": "tally", "name": "Tally", "categories": ["Finance"], "icon": "tally", "description": "Tally ERP accounting", "auth_type": "api_key"},
    {"id": "netsuite", "name": "NetSuite", "categories": ["Finance"], "icon": "oracle", "description": "Oracle NetSuite ERP", "auth_type": "oauth2"},
    {"id": "stripe", "name": "Stripe", "categories": ["Finance"], "icon": "stripe", "description": "Stripe payments platform", "auth_type": "api_key"},
    {"id": "razorpay", "name": "Razorpay", "categories": ["Finance"], "icon": "razorpay", "description": "Razorpay payments", "auth_type": "api_key"},
    {"id": "paypal", "name": "PayPal", "categories": ["Finance"], "icon": "paypal", "description": "PayPal payments", "auth_type": "oauth2"},
    # ── BI / Analytics ───────────────────────────────────────
    {"id": "powerbi", "name": "Power BI", "categories": ["BI / Analytics"], "icon": "powerbi", "description": "Microsoft Power BI", "auth_type": "oauth2"},
    {"id": "tableau", "name": "Tableau", "categories": ["BI / Analytics"], "icon": "tableau", "description": "Tableau data visualization", "auth_type": "api_key"},
    {"id": "looker", "name": "Looker", "categories": ["BI / Analytics"], "icon": "looker", "description": "Google Looker analytics", "auth_type": "oauth2"},
    {"id": "looker_studio", "name": "Looker Studio", "categories": ["BI / Analytics"], "icon": "looker", "description": "Google Looker Studio (Data Studio)", "auth_type": "oauth2"},
    {"id": "qlik", "name": "Qlik", "categories": ["BI / Analytics"], "icon": "qlik", "description": "Qlik analytics platform", "auth_type": "api_key"},
    {"id": "metabase", "name": "Metabase", "categories": ["BI / Analytics"], "icon": "metabase", "description": "Metabase open-source BI", "auth_type": "api_key"},
    {"id": "superset", "name": "Apache Superset", "categories": ["BI / Analytics"], "icon": "superset", "description": "Apache Superset data exploration", "auth_type": "api_key"},
    {"id": "grafana", "name": "Grafana", "categories": ["BI / Analytics", "Monitoring"], "icon": "grafana", "description": "Grafana dashboards and monitoring", "auth_type": "api_key"},
    {"id": "excel", "name": "Excel", "categories": ["BI / Analytics"], "icon": "excel", "description": "Microsoft Excel spreadsheets", "auth_type": "oauth2"},
    {"id": "google_sheets", "name": "Google Sheets", "categories": ["BI / Analytics"], "icon": "googlesheets", "description": "Google Sheets spreadsheets", "auth_type": "oauth2"},
    # ── AI / LLM ─────────────────────────────────────────────
    {"id": "openai", "name": "OpenAI", "categories": ["AI / LLM"], "icon": "openai", "description": "OpenAI GPT models", "auth_type": "api_key"},
    {"id": "anthropic", "name": "Anthropic", "categories": ["AI / LLM"], "icon": "anthropic", "description": "Anthropic Claude models", "auth_type": "api_key"},
    {"id": "gemini", "name": "Google Gemini", "categories": ["AI / LLM"], "icon": "gemini", "description": "Google Gemini AI", "auth_type": "api_key"},
    {"id": "groq", "name": "Groq", "categories": ["AI / LLM"], "icon": "groq", "description": "Groq inference platform", "auth_type": "api_key"},
    {"id": "mistral", "name": "Mistral", "categories": ["AI / LLM"], "icon": "mistral", "description": "Mistral AI models", "auth_type": "api_key"},
    {"id": "cohere", "name": "Cohere", "categories": ["AI / LLM"], "icon": "cohere", "description": "Cohere NLP models", "auth_type": "api_key"},
    {"id": "azure_openai", "name": "Azure OpenAI", "categories": ["AI / LLM", "Cloud"], "icon": "azure", "description": "Azure-hosted OpenAI models", "auth_type": "api_key"},
    {"id": "bedrock", "name": "AWS Bedrock", "categories": ["AI / LLM", "Cloud"], "icon": "aws", "description": "AWS Bedrock foundation models", "auth_type": "api_key"},
    {"id": "vertex_ai", "name": "Vertex AI", "categories": ["AI / LLM", "Cloud"], "icon": "gcp", "description": "Google Vertex AI platform", "auth_type": "service_account"},
    {"id": "nvidia", "name": "NVIDIA", "categories": ["AI / LLM"], "icon": "nvidia", "description": "NVIDIA AI inference", "auth_type": "api_key"},
    {"id": "huggingface", "name": "Hugging Face", "categories": ["AI / LLM"], "icon": "huggingface", "description": "Hugging Face model hub", "auth_type": "api_key"},
    {"id": "ollama", "name": "Ollama", "categories": ["AI / LLM"], "icon": "ollama", "description": "Ollama local LLM server", "auth_type": "none"},
    # ── Monitoring ───────────────────────────────────────────
    {"id": "sentry", "name": "Sentry", "categories": ["Monitoring"], "icon": "sentry", "description": "Sentry error tracking", "auth_type": "api_key"},
    {"id": "datadog", "name": "Datadog", "categories": ["Monitoring"], "icon": "datadog", "description": "Datadog monitoring and analytics", "auth_type": "api_key"},
    {"id": "newrelic", "name": "New Relic", "categories": ["Monitoring"], "icon": "newrelic", "description": "New Relic observability", "auth_type": "api_key"},
    {"id": "prometheus", "name": "Prometheus", "categories": ["Monitoring"], "icon": "prometheus", "description": "Prometheus metrics", "auth_type": "none"},
    {"id": "splunk", "name": "Splunk", "categories": ["Monitoring"], "icon": "splunk", "description": "Splunk data analytics", "auth_type": "api_key"},
    {"id": "elastic", "name": "Elastic", "categories": ["Monitoring"], "icon": "elastic", "description": "Elastic observability stack", "auth_type": "api_key"},
    {"id": "cloudwatch", "name": "CloudWatch", "categories": ["Monitoring", "Cloud"], "icon": "aws", "description": "AWS CloudWatch monitoring", "auth_type": "api_key"},
    {"id": "azure_monitor", "name": "Azure Monitor", "categories": ["Monitoring", "Cloud"], "icon": "azure", "description": "Azure Monitor and Log Analytics", "auth_type": "oauth2"},
    {"id": "gcloud_logging", "name": "Google Cloud Logging", "categories": ["Monitoring", "Cloud"], "icon": "gcp", "description": "Google Cloud Logging", "auth_type": "service_account"},
    # ── Identity ─────────────────────────────────────────────
    {"id": "google_workspace", "name": "Google Workspace", "categories": ["Identity", "Communication"], "icon": "google", "description": "Google Workspace directory and SSO", "auth_type": "oauth2"},
    {"id": "entra_id", "name": "Microsoft Entra ID", "categories": ["Identity"], "icon": "microsoft365", "description": "Microsoft Entra ID (Azure AD)", "auth_type": "oauth2"},
    {"id": "okta", "name": "Okta", "categories": ["Identity"], "icon": "okta", "description": "Okta identity platform", "auth_type": "oauth2"},
    {"id": "auth0", "name": "Auth0", "categories": ["Identity"], "icon": "auth0", "description": "Auth0 identity platform", "auth_type": "oauth2"},
    {"id": "keycloak", "name": "Keycloak", "categories": ["Identity"], "icon": "keycloak", "description": "Keycloak open-source IAM", "auth_type": "oauth2"},
    {"id": "ping", "name": "Ping Identity", "categories": ["Identity"], "icon": "ping", "description": "Ping Identity platform", "auth_type": "oauth2"},
    {"id": "onelogin", "name": "OneLogin", "categories": ["Identity"], "icon": "onelogin", "description": "OneLogin identity management", "auth_type": "oauth2"},
    # ── Custom ───────────────────────────────────────────────
    {"id": "custom_graphql", "name": "Custom GraphQL", "categories": ["Custom"], "icon": "api", "description": "Connect to any GraphQL API", "auth_type": "bearer"},
    {"id": "webhook", "name": "Webhook", "categories": ["Custom"], "icon": "webhook", "description": "Inbound/outbound webhook endpoint", "auth_type": "api_key"},
    {"id": "generic_oauth2", "name": "Generic OAuth 2.0", "categories": ["Custom"], "icon": "lock", "description": "Connect via any OAuth 2.0 provider", "auth_type": "oauth2"},
    {"id": "generic_oidc", "name": "Generic OIDC", "categories": ["Custom"], "icon": "lock", "description": "Connect via any OpenID Connect provider", "auth_type": "oauth2"},
    {"id": "generic_database", "name": "Generic Database", "categories": ["Custom"], "icon": "database", "description": "Connect to any SQL database", "auth_type": "db_password"},
    {"id": "generic_sftp", "name": "Generic SFTP", "categories": ["Custom"], "icon": "folder", "description": "Connect to any SFTP server", "auth_type": "db_password"},
]


class ProviderRegistry:
    """Central registry for all connection providers.

    Code-backed providers are registered with ``register()`` and provide
    full functionality.  Catalog-only entries appear as "Coming soon".
    """

    def __init__(self) -> None:
        self._providers: dict[str, BaseProvider] = {}
        self._catalog: dict[str, dict[str, Any]] = {}

        # Load phase-2 catalog entries
        for entry in _CATALOG_ENTRIES:
            self._catalog[entry["id"]] = entry

        # Register default code-backed providers
        try:
            from backend.connections.providers import register_all_providers
            register_all_providers(self)
        except Exception as exc:
            logger.warning("Could not auto-register default providers: %s", exc)

    def register(self, provider: BaseProvider) -> None:
        """Register a code-backed provider."""
        meta = provider.get_metadata()
        self._providers[meta.id] = provider
        # Remove from catalog-only if it was there
        self._catalog.pop(meta.id, None)
        logger.info("Registered connection provider: %s (%s)", meta.id, meta.name)

    def get_provider(self, provider_id: str) -> BaseProvider | None:
        """Get a registered (code-backed) provider by ID."""
        return self._providers.get(provider_id)

    def list_all(self) -> list[ProviderPublic]:
        """Return all providers for the catalog API.

        Code-backed providers use their metadata; catalog-only entries
        appear as unavailable ("Coming soon").
        """
        result: list[ProviderPublic] = []

        # Code-backed providers first
        for pid, provider in sorted(self._providers.items()):
            meta = provider.get_metadata()
            result.append(ProviderPublic(
                id=meta.id,
                name=meta.name,
                categories=list(meta.categories),
                icon=meta.icon,
                description=meta.description,
                auth_type=meta.auth_type.value,
                capabilities=[c.value for c in meta.capabilities],
                available=meta.available,
                available_reason=meta.available_reason,
                configuration_schema=meta.configuration_schema,
            ))

        # Catalog-only entries (coming soon)
        for cid, entry in sorted(self._catalog.items()):
            if cid not in self._providers:
                result.append(ProviderPublic(
                    id=entry["id"],
                    name=entry["name"],
                    categories=entry.get("categories", []),
                    icon=entry.get("icon", "plug"),
                    description=entry.get("description", ""),
                    auth_type=entry.get("auth_type", "none"),
                    capabilities=[],
                    available=False,
                    available_reason="coming_soon",
                ))

        return result

    def get_categories(self) -> list[str]:
        """Return all unique categories across all providers."""
        cats: set[str] = set()
        for provider in self._providers.values():
            cats.update(provider.get_metadata().categories)
        for entry in self._catalog.values():
            cats.update(entry.get("categories", []))
        return sorted(cats)

    @property
    def provider_ids(self) -> list[str]:
        return list(self._providers.keys())


# ═══════════════════════════════════════════════════════════════
# Module-level singleton
# ═══════════════════════════════════════════════════════════════

_registry: ProviderRegistry | None = None


def get_provider_registry() -> ProviderRegistry:
    global _registry
    if _registry is None:
        _registry = ProviderRegistry()
    return _registry
