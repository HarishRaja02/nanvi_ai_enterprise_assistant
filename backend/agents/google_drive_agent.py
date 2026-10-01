"""GoogleDriveAgent implementation for Google Drive cloud and local file searches."""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from backend.agents.interfaces import Agent
from backend.agents.models import AgentRequest, AgentResponse, Capability
from backend.sources.models import SourceType
from backend.sources.service import SourceReferenceService

logger = logging.getLogger(__name__)


class GoogleDriveAgent(Agent):
    capability = Capability.GOOGLE_DRIVE

    def __init__(
        self,
        source_references: SourceReferenceService | None = None,
        connection_manager=None,
    ):
        self._sources = source_references
        self._conns = connection_manager

    def run(self, request: AgentRequest) -> AgentResponse:
        query = request.query.strip()
        clean_q = re.sub(r"[^\w\s\-\.]", " ", query).strip()

        # 1. Check for active Google connection in Connections Hub
        conn = None
        identity = None
        drive_scope = "https://www.googleapis.com/auth/drive.metadata.readonly"
        drive_permission_missing = False
        try:
            if self._conns is not None:
                from backend.security.models import UserIdentity

                user_id = getattr(request.user, "user_id", "admin")
                tenant_id = getattr(request.user, "tenant_id", "enterprise-tenant")
                identity = UserIdentity(subject=user_id, issuer="nanvi", tenant_id=tenant_id)
                conns = self._conns.list_connections(identity, provider="google")
                connected_google = [c for c in conns if c.status == "connected"]
                drive_permission_missing = any(
                    c.granted_scopes and drive_scope not in c.granted_scopes
                    for c in connected_google
                )
                active_conns = [
                    c for c in connected_google
                    if not c.granted_scopes or drive_scope in c.granted_scopes
                ]
                if active_conns:
                    conn = active_conns[0]
        except Exception as exc:
            logger.debug("Google connection lookup skipped: %s", exc)

        # 2. Resolve a Drive-capable token from Connections Hub or the linked mailbox.
        access_token = None
        if conn and identity:
            try:
                raw_conn = self._conns._get_raw_connection(conn.id, identity)
                creds = self._conns._encryption.decrypt(raw_conn["encrypted_credentials"])
                access_token = creds.get("access_token")
            except Exception as exc:
                logger.warning("Google Drive connection token lookup failed: %s", exc)

        # Mailbox OAuth accounts are stored separately from Connections Hub entries.
        if not access_token:
            try:
                from backend.integrations.email.user_account_service import get_user_email_account_service
                account_service = get_user_email_account_service()
                account = account_service.get_active_account(request.user.user_id)
                if account and account.is_active:
                    account_scopes = set(re.split(r"[\s,]+", account.scopes or ""))
                    has_drive_scope = drive_scope in account_scopes
                    drive_permission_missing = drive_permission_missing or not has_drive_scope
                    if has_drive_scope and account.access_token and not account.is_token_expired():
                        access_token = account.access_token
                    elif has_drive_scope and account.refresh_token:
                        from backend.integrations.email.oauth import get_google_oauth_service
                        access_token, expires_in = get_google_oauth_service().refresh_access_token(account.refresh_token)
                        if access_token:
                            account_service.update_tokens(account.id, access_token, expires_in)
            except Exception as exc:
                logger.debug("Per-user Google token lookup for Drive skipped: %s", exc)

        # 3. Search Drive metadata when the connected token has Drive read access.
        if access_token:
            try:
                import httpx

                noise = {"get", "find", "search", "the", "a", "an", "file", "files", "document", "documents", "in", "from", "drive", "google"}
                terms = [w for w in clean_q.casefold().split() if w not in noise and len(w) > 2]
                api_url = "https://www.googleapis.com/drive/v3/files"
                if terms:
                    name_terms = " or ".join(f"name contains '{term}'" for term in terms)
                    drive_q = f"({name_terms}) and trashed = false"
                else:
                    drive_q = "trashed = false"
                resp = httpx.get(
                    api_url,
                    headers={"Authorization": f"Bearer {access_token}"},
                    params={"q": drive_q, "fields": "files(id, name, mimeType, webViewLink, modifiedTime, size)", "pageSize": 10},
                    timeout=5.0,
                )
                if resp.status_code in (401, 403):
                    drive_permission_missing = True
                    logger.warning("Google Drive search was denied (HTTP %s); the connected account may need Drive read access.", resp.status_code)
                elif resp.status_code == 200:
                    drive_permission_missing = False
                    files = resp.json().get("files", [])
                    if files:
                        rows = []
                        refs = []
                        for f in files:
                            name = f.get("name", "Untitled")
                            link = f.get("webViewLink", "")
                            mime = f.get("mimeType", "")
                            mod = f.get("modifiedTime", "")[:10]
                            rows.append(f"| {name} | {mime.split('.')[-1]} | {mod} | [Open in Drive]({link}) |")
                            if self._sources is not None:
                                ref = self._sources._create(
                                    user=request.user,
                                    request_id=request.request_id,
                                    source_type=SourceType.DRIVE,
                                    source_id=f"gdrive-{f.get('id')}",
                                    display_name=f"[Drive] {name}",
                                    title=name,
                                    location=f"Google Drive: {name}",
                                    page=None,
                                    sheet=None,
                                    timestamp=None,
                                    mime_type=mime,
                                    owner_id=request.user.user_id,
                                    tenant_id=request.user.tenant_id,
                                    department=request.user.department,
                                    restricted_department=None,
                                )
                                if ref:
                                    refs.append(ref)
                        content = (
                            f"Found **{len(files)}** document(s) in **Google Drive**:\n\n"
                            f"| File Name | Type | Modified | Link |\n"
                            f"| --- | --- | --- | --- |\n"
                            + "\n".join(rows)
                        )
                        return AgentResponse(self.capability, content, tuple(refs))
            except Exception as exc:
                logger.warning("Google Drive API search failed: %s", exc)

        # 4. Check local Google Drive folder if present (e.g. C:/CompanyData/GoogleDrive)
        try:
            from backend.integrations.files.company_data_service import CompanyDataService

            active_root = CompanyDataService.for_tenant(request.user.tenant_id).root
            drive_dirs = [active_root / "GoogleDrive", Path("C:/CompanyData/GoogleDrive"), Path("./CompanyData/GoogleDrive")]
            for drive_dir in drive_dirs:
                if drive_dir.exists() and drive_dir.is_dir():
                    matching = []
                    q_lower = query.casefold()
                    for f in drive_dir.iterdir():
                        if f.is_file() and any(w in f.name.casefold() for w in q_lower.split() if len(w) > 2):
                            matching.append(f)
                    if matching:
                        rows = [f"| {f.name} | {f.suffix} | {f.stat().st_size} bytes | `{f}` |" for f in matching[:10]]
                        refs = []
                        if self._sources is not None:
                            for f in matching[:10]:
                                ref = self._sources._create(
                                    user=request.user,
                                    request_id=request.request_id,
                                    source_type=SourceType.DRIVE,
                                    source_id=f"localdrive-{f.name}",
                                    display_name=f"[Google Drive] {f.name}",
                                    title=f.name,
                                    location=str(f),
                                    page=None,
                                    sheet=None,
                                    timestamp=None,
                                    mime_type=None,
                                    owner_id=request.user.user_id,
                                    tenant_id=request.user.tenant_id,
                                    department=request.user.department,
                                    restricted_department=None,
                                )
                                if ref:
                                    refs.append(ref)
                        content = (
                            f"Found **{len(matching)}** document(s) in **Google Drive**:\n\n"
                            f"| File Name | Extension | Size | Path |\n"
                            f"| --- | --- | --- | --- |\n"
                            + "\n".join(rows)
                        )
                        return AgentResponse(self.capability, content, tuple(refs))
        except Exception as exc:
            logger.debug("Local Google Drive directory check skipped: %s", exc)

        # Explain missing connection or Drive scope for broad file searches too.
        explicit_drive = any(k in query.casefold() for k in ("google drive", "gdrive", "drive file", "drive folder", "in drive", "from drive"))
        from backend.retrieval.intent import classify_retrieval_intent, QueryIntent
        is_file_discovery = (
            classify_retrieval_intent(query) == QueryIntent.FILE_SEARCH
            and bool(re.search(r"\b(?:find|search|locate|look\s+for|where\s+is|where\s+are|show\s+me)\b", query.casefold()))
        )
        if drive_permission_missing:
            return AgentResponse(
                self.capability,
                "Google Drive is connected, but Google denied access to its file list. Reconnect Google under **Settings → Connections** and approve read-only Drive file metadata access.",
                (),
            )
        if explicit_drive or is_file_discovery:
            return AgentResponse(
                self.capability,
                "Google Drive is not connected for this account. Connect Google Workspace under **Settings → Connections** to include Drive files in searches.",
                (),
            )

        return AgentResponse(self.capability, "", ())
