"""Enterprise Services Catalog & Granular Permission Resolver.

Defines the individual services available under each enterprise provider,
manages per-service enabled/disabled states, OAuth scope verification,
and backend permission checks for AI assistant retrieval.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from backend.connections.schemas import ServicePermission, ServiceState

logger = logging.getLogger(__name__)


@dataclass
class ServiceDefinition:
    id: str
    name: str
    description: str
    icon: str
    required_scopes: list[str] = field(default_factory=list)
    permissions: list[dict[str, Any]] = field(default_factory=list)
    default_enabled: bool = True


# ═══════════════════════════════════════════════════════════════
# Declarative Services Registry
# ═══════════════════════════════════════════════════════════════

PROVIDER_SERVICES: dict[str, list[ServiceDefinition]] = {
    "google": [
        ServiceDefinition(
            id="gmail",
            name="Gmail",
            description="Read and search authorized email messages and threads. Access attachments when permitted.",
            icon="gmail",
            required_scopes=[
                "https://www.googleapis.com/auth/gmail.readonly",
            ],
            permissions=[
                {"id": "read", "label": "Read emails", "description": "Read email message bodies and metadata", "default": True},
                {"id": "search", "label": "Search messages", "description": "Search inbox and email threads", "default": True},
                {"id": "attachments", "label": "Email attachments", "description": "Analyze attached documents and PDFs", "default": True},
                {"id": "send", "label": "Send emails", "description": "Send emails or save drafts when authorized", "default": False},
            ],
            default_enabled=True,
        ),
        ServiceDefinition(
            id="drive",
            name="Google Drive",
            description="Search and retrieve authorized documents, files, and folders across My Drive.",
            icon="googledrive",
            required_scopes=[
                "https://www.googleapis.com/auth/drive.metadata.readonly",
            ],
            permissions=[
                {"id": "read", "label": "Read files", "description": "Read authorized document contents", "default": True},
                {"id": "search", "label": "Search files", "description": "Search Drive filenames and full text", "default": True},
                {"id": "download", "label": "File download", "description": "Download documents for AI analysis", "default": True},
            ],
            default_enabled=True,
        ),
        ServiceDefinition(
            id="docs",
            name="Google Docs",
            description="Search and read authorized text documents and reports.",
            icon="googledocs",
            required_scopes=[
                "https://www.googleapis.com/auth/drive.metadata.readonly",
            ],
            permissions=[
                {"id": "read", "label": "Read documents", "description": "Read Google Docs text and structure", "default": True},
                {"id": "search", "label": "Search documents", "description": "Locate Docs by keyword or title", "default": True},
            ],
            default_enabled=True,
        ),
        ServiceDefinition(
            id="sheets",
            name="Google Sheets",
            description="Read authorized spreadsheets and tabular data for financial and operational queries.",
            icon="googlesheets",
            required_scopes=[
                "https://www.googleapis.com/auth/spreadsheets.readonly",
            ],
            permissions=[
                {"id": "read", "label": "Read spreadsheets", "description": "Query cell values and sheet tabs", "default": True},
                {"id": "search", "label": "Search sheets", "description": "Search sheets by filename or content", "default": True},
            ],
            default_enabled=False,
        ),
        ServiceDefinition(
            id="slides",
            name="Google Slides",
            description="Search and read authorized presentations and slide decks.",
            icon="googleslides",
            required_scopes=[
                "https://www.googleapis.com/auth/presentations.readonly",
            ],
            permissions=[
                {"id": "read", "label": "Read slides", "description": "Extract slide content and speaker notes", "default": True},
                {"id": "search", "label": "Search presentations", "description": "Locate presentations by keyword", "default": True},
            ],
            default_enabled=False,
        ),
        ServiceDefinition(
            id="calendar",
            name="Google Calendar",
            description="Read authorized events, meetings, and schedules for schedule-aware assistance.",
            icon="googlecalendar",
            required_scopes=[
                "https://www.googleapis.com/auth/calendar.readonly",
            ],
            permissions=[
                {"id": "read", "label": "Read events", "description": "Inspect calendar event times and attendees", "default": True},
                {"id": "search", "label": "Search calendar", "description": "Find meetings by title or participant", "default": True},
            ],
            default_enabled=False,
        ),
        ServiceDefinition(
            id="shared_drives",
            name="Google Shared Drives",
            description="Access authorized organizational shared-drive content with team permissions.",
            icon="googledrive",
            required_scopes=[
                "https://www.googleapis.com/auth/drive.metadata.readonly",
            ],
            permissions=[
                {"id": "read", "label": "Read shared drive content", "description": "Access shared team files", "default": True},
                {"id": "search", "label": "Search shared drives", "description": "Search across organizational shared drives", "default": True},
            ],
            default_enabled=False,
        ),
    ],
    "google_workspace": [
        # Alias for google
    ],
    "microsoft365": [
        ServiceDefinition(
            id="outlook",
            name="Outlook Mail",
            description="Read and search corporate emails, threads, and mailbox metadata via Microsoft Graph.",
            icon="outlook",
            required_scopes=["Mail.Read", "Mail.ReadWrite"],
            permissions=[
                {"id": "read", "label": "Read emails", "description": "Read Outlook email messages", "default": True},
                {"id": "search", "label": "Search inbox", "description": "Search messages by subject, sender, date", "default": True},
                {"id": "attachments", "label": "Email attachments", "description": "Analyze Outlook document attachments", "default": True},
                {"id": "send", "label": "Send emails", "description": "Create drafts or send emails when authorized", "default": False},
            ],
            default_enabled=True,
        ),
        ServiceDefinition(
            id="onedrive",
            name="OneDrive for Business",
            description="Search and retrieve personal and business OneDrive files and folders.",
            icon="onedrive",
            required_scopes=["Files.Read", "Files.Read.All"],
            permissions=[
                {"id": "read", "label": "Read files", "description": "Read Word, Excel, PowerPoint, and PDF files", "default": True},
                {"id": "search", "label": "Search OneDrive", "description": "Search OneDrive directory and contents", "default": True},
                {"id": "download", "label": "Download files", "description": "Retrieve documents for AI summarization", "default": True},
            ],
            default_enabled=True,
        ),
        ServiceDefinition(
            id="sharepoint",
            name="SharePoint Online",
            description="Access corporate team sites, document libraries, and authorized organizational folders.",
            icon="sharepoint",
            required_scopes=["Sites.Read.All"],
            permissions=[
                {"id": "read", "label": "Read site documents", "description": "Access files in SharePoint document libraries", "default": True},
                {"id": "search", "label": "Search SharePoint", "description": "Search team sites and document repositories", "default": True},
                {"id": "download", "label": "Download files", "description": "Download files for AI analysis", "default": True},
            ],
            default_enabled=True,
        ),
        ServiceDefinition(
            id="teams",
            name="Microsoft Teams",
            description="Search authorized team channels and public chat discussions.",
            icon="teams",
            required_scopes=["ChannelMessage.Read.All"],
            permissions=[
                {"id": "read", "label": "Read messages", "description": "Read channel discussions and meeting transcripts", "default": True},
                {"id": "search", "label": "Search discussions", "description": "Search team communications", "default": True},
            ],
            default_enabled=False,
        ),
        ServiceDefinition(
            id="calendar",
            name="Outlook Calendar",
            description="Read corporate schedules, meeting invitations, and room availability.",
            icon="calendar",
            required_scopes=["Calendars.Read"],
            permissions=[
                {"id": "read", "label": "Read schedule", "description": "Inspect corporate calendar events", "default": True},
                {"id": "search", "label": "Search meetings", "description": "Find past and upcoming corporate meetings", "default": True},
            ],
            default_enabled=False,
        ),
    ],
    "outlook": [
        ServiceDefinition(
            id="outlook_email",
            name="Outlook Mailbox",
            description="Search and read Microsoft Outlook messages, drafts, and attachments.",
            icon="outlook",
            required_scopes=["Mail.Read"],
            permissions=[
                {"id": "read", "label": "Read emails", "description": "Read email messages", "default": True},
                {"id": "search", "label": "Search emails", "description": "Search inbox and archives", "default": True},
                {"id": "attachments", "label": "Attachments", "description": "Extract file attachments", "default": True},
                {"id": "send", "label": "Send emails", "description": "Draft or send emails", "default": False},
            ],
            default_enabled=True,
        ),
    ],
    "yahoo": [
        ServiceDefinition(
            id="yahoo_mail",
            name="Yahoo Mailbox",
            description="Search and read Yahoo Mail messages, folders, and message headers.",
            icon="yahoo",
            required_scopes=["mail-r"],
            permissions=[
                {"id": "read", "label": "Read emails", "description": "Read Yahoo email messages", "default": True},
                {"id": "search", "label": "Search emails", "description": "Search mailbox by sender or query", "default": True},
                {"id": "attachments", "label": "Attachments", "description": "Access email attachments", "default": True},
            ],
            default_enabled=True,
        ),
    ],
    "imap": [
        ServiceDefinition(
            id="imap_inbox",
            name="IMAP Mailbox Reader",
            description="Read and search authorized email folders via standard IMAP over TLS/SSL.",
            icon="mail",
            permissions=[
                {"id": "read", "label": "Read emails", "description": "Fetch email contents via IMAP", "default": True},
                {"id": "search", "label": "Search emails", "description": "Search headers and text via IMAP SEARCH", "default": True},
                {"id": "attachments", "label": "Attachments", "description": "Download attachments for analysis", "default": True},
            ],
            default_enabled=True,
        ),
    ],
    "smtp": [
        ServiceDefinition(
            id="smtp_sender",
            name="SMTP Outbound Dispatcher",
            description="Send authorized enterprise emails, alerts, and report summaries via SMTP.",
            icon="send",
            permissions=[
                {"id": "send", "label": "Send email", "description": "Send outbound emails with explicit approval", "default": True},
            ],
            default_enabled=True,
        ),
    ],
    "box": [
        ServiceDefinition(
            id="box_storage",
            name="Box Enterprise Storage",
            description="Search and retrieve enterprise files, shared folders, and corporate records.",
            icon="box",
            required_scopes=["root_readwrite", "manage_webhook"],
            permissions=[
                {"id": "read", "label": "Read files", "description": "Read enterprise documents", "default": True},
                {"id": "search", "label": "Search storage", "description": "Search Box directories and document contents", "default": True},
                {"id": "download", "label": "File download", "description": "Download files for AI analysis", "default": True},
            ],
            default_enabled=True,
        ),
    ],
    "dropbox": [
        ServiceDefinition(
            id="dropbox_storage",
            name="Dropbox Business Files",
            description="Access corporate team folders, shared documents, and file versions.",
            icon="dropbox",
            required_scopes=["files.metadata.read", "files.content.read"],
            permissions=[
                {"id": "read", "label": "Read files", "description": "Read Dropbox files and documents", "default": True},
                {"id": "search", "label": "Search folders", "description": "Search Dropbox files and folders", "default": True},
                {"id": "download", "label": "File download", "description": "Retrieve files for AI summarization", "default": True},
            ],
            default_enabled=True,
        ),
    ],
    "egnyte": [
        ServiceDefinition(
            id="egnyte_storage",
            name="Egnyte Hybrid Repository",
            description="Access enterprise file repository with strict permission-aware document retrieval.",
            icon="egnyte",
            required_scopes=["egnyte.filesystem"],
            permissions=[
                {"id": "read", "label": "Read repository", "description": "Access Egnyte files and folders", "default": True},
                {"id": "search", "label": "Search repository", "description": "Search Egnyte metadata and documents", "default": True},
                {"id": "download", "label": "File download", "description": "Download documents for AI processing", "default": True},
            ],
            default_enabled=True,
        ),
    ],
    "onedrive": [
        ServiceDefinition(
            id="onedrive_files",
            name="Microsoft OneDrive",
            description="Search and retrieve cloud documents, spreadsheets, and presentations.",
            icon="onedrive",
            required_scopes=["Files.Read"],
            permissions=[
                {"id": "read", "label": "Read files", "description": "Read OneDrive documents", "default": True},
                {"id": "search", "label": "Search storage", "description": "Search files by name and content", "default": True},
                {"id": "download", "label": "Download files", "description": "Retrieve files for AI analysis", "default": True},
            ],
            default_enabled=True,
        ),
    ],
    "sharepoint": [
        ServiceDefinition(
            id="sharepoint_sites",
            name="Microsoft SharePoint",
            description="Search document libraries across authorized SharePoint corporate sites.",
            icon="sharepoint",
            required_scopes=["Sites.Read.All"],
            permissions=[
                {"id": "read", "label": "Read libraries", "description": "Access SharePoint document libraries", "default": True},
                {"id": "search", "label": "Search sites", "description": "Search across SharePoint sites and folders", "default": True},
                {"id": "download", "label": "Download files", "description": "Download files for AI analysis", "default": True},
            ],
            default_enabled=True,
        ),
    ],
    "supabase": [
        ServiceDefinition(
            id="rest_api",
            name="PostgREST API",
            description="Query and filter relational tables and views over Supabase REST.",
            icon="supabase",
            permissions=[
                {"id": "read", "label": "Read tables", "description": "Query database rows and records", "default": True},
                {"id": "search", "label": "Search records", "description": "Filter and search across tables", "default": True},
            ],
            default_enabled=True,
        ),
        ServiceDefinition(
            id="postgres_db",
            name="Direct PostgreSQL Database",
            description="Execute read-only SQL queries and introspect database schemas.",
            icon="postgresql",
            permissions=[
                {"id": "read", "label": "Execute SQL queries", "description": "Run read-only analytical SQL queries", "default": True},
            ],
            default_enabled=True,
        ),
        ServiceDefinition(
            id="storage",
            name="Supabase Storage",
            description="Access and download files stored in authorized Supabase storage buckets.",
            icon="folder",
            permissions=[
                {"id": "read", "label": "Read buckets", "description": "List and read bucket objects", "default": True},
                {"id": "download", "label": "Download objects", "description": "Download files for analysis", "default": True},
            ],
            default_enabled=False,
        ),
    ],
    "postgres": [
        ServiceDefinition(
            id="sql_engine",
            name="PostgreSQL Query Engine",
            description="Execute read-only SQL queries and generate automated analytical reports.",
            icon="postgresql",
            permissions=[
                {"id": "read", "label": "Read & Query", "description": "Execute read-only SELECT queries", "default": True},
            ],
            default_enabled=True,
        ),
    ],
    "mysql": [
        ServiceDefinition(
            id="sql_engine",
            name="MySQL Query Engine",
            description="Execute read-only SQL queries on MySQL databases.",
            icon="mysql",
            permissions=[
                {"id": "read", "label": "Read & Query", "description": "Execute read-only SELECT queries", "default": True},
            ],
            default_enabled=True,
        ),
    ],
    "mariadb": [
        ServiceDefinition(
            id="sql_engine",
            name="MariaDB Query Engine",
            description="Execute read-only SQL queries on MariaDB relational databases.",
            icon="mariadb",
            permissions=[
                {"id": "read", "label": "Read & Query", "description": "Execute read-only SELECT queries", "default": True},
            ],
            default_enabled=True,
        ),
    ],
    "sqlite": [
        ServiceDefinition(
            id="sql_engine",
            name="SQLite Embedded Engine",
            description="Execute read-only queries against local or embedded SQLite databases.",
            icon="sqlite",
            permissions=[
                {"id": "read", "label": "Read & Query", "description": "Execute read-only SELECT queries", "default": True},
            ],
            default_enabled=True,
        ),
    ],
    "github": [
        ServiceDefinition(
            id="repos",
            name="GitHub Repositories",
            description="Search repositories, review pull requests, inspect commit history, and analyze code.",
            icon="github",
            required_scopes=["repo", "read:org"],
            permissions=[
                {"id": "read", "label": "Read code", "description": "Read file contents and pull requests", "default": True},
                {"id": "search", "label": "Search code", "description": "Search code, issues, and commit messages", "default": True},
            ],
            default_enabled=True,
        ),
    ],
    "local_files": [
        ServiceDefinition(
            id="local_storage",
            name="Local Storage & Documents",
            description="Access authorized local company folders via Desktop Agent or server-side mount.",
            icon="folder",
            permissions=[
                {"id": "read", "label": "Read files", "description": "Read PDFs, spreadsheets, and documents", "default": True},
                {"id": "search", "label": "Search documents", "description": "Full-text search indexed local files", "default": True},
            ],
            default_enabled=True,
        ),
    ],
    "custom_api": [
        ServiceDefinition(
            id="api_endpoints",
            name="REST API Endpoints",
            description="Query connected external REST API endpoints using secure API key or Bearer token.",
            icon="api",
            permissions=[
                {"id": "read", "label": "Call endpoints", "description": "Execute GET/POST queries against configured endpoints", "default": True},
            ],
            default_enabled=True,
        ),
    ],
}

# Mirror google_workspace to google
PROVIDER_SERVICES["google_workspace"] = PROVIDER_SERVICES["google"]


# ═══════════════════════════════════════════════════════════════
# Resolution and Permission Verification Logic
# ═══════════════════════════════════════════════════════════════

def _parse_granted_scopes(raw_scopes: Any) -> list[str]:
    """Parse scopes stored as array, comma-string, or json."""
    if not raw_scopes:
        return []
    if isinstance(raw_scopes, list):
        return [str(s).strip() for s in raw_scopes if s]
    if isinstance(raw_scopes, str):
        try:
            parsed = json.loads(raw_scopes)
            if isinstance(parsed, list):
                return [str(s).strip() for s in parsed if s]
        except Exception:
            pass
        return [s.strip() for s in raw_scopes.split(",") if s.strip()]
    return []


def _has_required_scope(granted_scopes: list[str], required_scopes: list[str]) -> bool:
    """Check if all required scopes are satisfied by granted scopes."""
    if not required_scopes:
        return True
    
    # Check if any granted scope matches or grants broad access
    for req in required_scopes:
        satisfied = False
        for g in granted_scopes:
            if g == req:
                satisfied = True
                break
            # Broad drive scope satisfies metadata.readonly or readonly
            if "auth/drive" in g and "auth/drive" in req:
                if g == "https://www.googleapis.com/auth/drive" or g.endswith("/drive"):
                    satisfied = True
                    break
            # Microsoft Graph prefix checks
            if req.lower() in g.lower():
                satisfied = True
                break
        if not satisfied:
            return False
    return True


def resolve_services_for_connection(
    provider_id: str,
    services_config_raw: Any = None,
    granted_scopes_raw: Any = None,
    connection_status: str = "CONNECTED",
) -> list[ServiceState]:
    """Build the list of ServiceState objects for a connection.
    
    Adheres strictly to the requirement:
    - Never display a service as enabled if required OAuth scope is missing.
    - Preserves user overrides stored in services_config.
    """
    definitions = PROVIDER_SERVICES.get(provider_id)
    if not definitions:
        # Default single service for unknown or generic providers
        return [
            ServiceState(
                id=f"{provider_id}_service",
                name=f"{provider_id.capitalize()} Integration",
                icon="plug",
                description="Core integration service",
                enabled=connection_status == "CONNECTED",
                status="ENABLED" if connection_status == "CONNECTED" else "DISABLED",
                status_reason=None,
                permissions=[
                    ServicePermission(
                        id="read",
                        label="Read Access",
                        description="Read data from connected service",
                        granted=True,
                        required_scopes=[],
                    )
                ],
                required_scopes=[],
                granted_scopes=[],
                last_synced_at=None,
                sync_frequency="1h",
                sync_status="IDLE",
                item_count=None,
            )
        ]

    # Parse stored config
    saved_config: dict[str, Any] = {}
    if services_config_raw:
        if isinstance(services_config_raw, dict):
            saved_config = services_config_raw
        elif isinstance(services_config_raw, str):
            try:
                saved_config = json.loads(services_config_raw)
            except Exception:
                saved_config = {}

    granted_scopes = _parse_granted_scopes(granted_scopes_raw)
    result: list[ServiceState] = []

    for spec in definitions:
        has_scopes = _has_required_scope(granted_scopes, spec.required_scopes)
        user_cfg = saved_config.get(spec.id, {})
        user_enabled_pref = user_cfg.get("enabled")

        # Determine effective enabled status
        if not has_scopes and spec.required_scopes:
            # Cannot be enabled if required OAuth permissions were not granted
            enabled = False
            status = "UNAUTHORIZED"
            status_reason = "Required OAuth scope not granted by provider account"
        elif user_enabled_pref is not None:
            enabled = bool(user_enabled_pref)
            status = "ENABLED" if enabled else "DISABLED"
            status_reason = None if enabled else "Disabled by administrator"
        else:
            # Default state based on catalog spec
            enabled = spec.default_enabled and (has_scopes or not spec.required_scopes)
            status = "ENABLED" if enabled else "DISABLED"
            status_reason = None

        # Build permissions list
        saved_perms = set(user_cfg.get("permissions", []))
        permissions_list: list[ServicePermission] = []
        for p in spec.permissions:
            is_granted = (p["id"] in saved_perms) if user_cfg.get("permissions") is not None else p.get("default", True)
            permissions_list.append(
                ServicePermission(
                    id=p["id"],
                    label=p["label"],
                    description=p["description"],
                    granted=is_granted if enabled else False,
                    required_scopes=spec.required_scopes,
                )
            )

        sync_freq = user_cfg.get("sync_frequency", "1h")
        last_sync = user_cfg.get("last_synced_at")

        result.append(
            ServiceState(
                id=spec.id,
                name=spec.name,
                icon=spec.icon,
                description=spec.description,
                enabled=enabled,
                status=status,
                status_reason=status_reason,
                permissions=permissions_list,
                required_scopes=spec.required_scopes,
                granted_scopes=[s for s in granted_scopes if any(req in s for req in spec.required_scopes)] if spec.required_scopes else [],
                last_synced_at=last_sync,
                sync_frequency=sync_freq,
                sync_status="IDLE",
                item_count=user_cfg.get("item_count"),
            )
        )

    return result


def is_service_enabled_for_connection(
    connection_row: dict[str, Any],
    service_id: str,
    required_permission: str | None = None,
) -> bool:
    """Backend authorization gate: Returns True ONLY if service is enabled and permission is granted.
    
    Used by AI Assistant before executing queries or retrieving documents.
    """
    status = connection_row.get("status")
    if status != "CONNECTED":
        return False

    provider_id = connection_row.get("provider", "")
    services_config_raw = connection_row.get("services_config")
    granted_scopes_raw = connection_row.get("granted_scopes")

    services = resolve_services_for_connection(
        provider_id=provider_id,
        services_config_raw=services_config_raw,
        granted_scopes_raw=granted_scopes_raw,
        connection_status=status,
    )

    for svc in services:
        if svc.id == service_id:
            if not svc.enabled:
                return False
            if required_permission:
                granted_perms = {p.id for p in svc.permissions if p.granted}
                return required_permission in granted_perms
            return True

    return False
