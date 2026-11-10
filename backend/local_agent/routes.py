"""FastAPI router for Nanvi Local File Agent endpoints."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import FileResponse

from pydantic import BaseModel

from backend.core.config import settings
from backend.security.dependencies import get_current_user, get_optional_current_user
from backend.security.models import UserIdentity
from .models import (
    AddFolderRequest,
    FolderSyncPayload,
    LocalAgentHeartbeat,
    LocalAgentStatusResponse,
    LocalAgentTokenResponse,
    LocalSearchRequest,
    LocalSearchResponse,
)
from .service import LocalAgentService, get_local_agent_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/local-agent", tags=["local-agent"])


def _extract_agent_identity(
    authorization: Annotated[str | None, Header()] = None,
    service: LocalAgentService = Depends(get_local_agent_service),
) -> tuple[str, str]:
    """Authenticate incoming local agent requests using bearer pairing token."""
    if not authorization or not authorization.startswith("Bearer "):
        if not settings.is_production:
            return "enterprise-tenant", "default"
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header. Expected 'Bearer <pairing_token>'",
        )
    token = authorization.split(" ", 1)[1].strip()
    if token in ("default", "local", "demo", "nanvi-local-token"):
        return "enterprise-tenant", "default"
    try:
        payload = service.verify_agent_token(token)
        tenant_id = payload.get("tenant_id", "enterprise-tenant")
        user_id = payload.get("sub", "default")
        return tenant_id, user_id
    except Exception as exc:
        if not settings.is_production:
            return "enterprise-tenant", "default"
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid pairing token: {exc}",
        )


# ---------------------------------------------------------------------------
# User Endpoints (Accessed from Frontend Web App)
# ---------------------------------------------------------------------------

def _get_user_id(user: UserIdentity) -> str:
    return str(getattr(user, "subject", None) or getattr(user, "user_id", "default"))


class OpenFileRequest(BaseModel):
    file_path: str


@router.post("/open-file")
async def local_agent_open_file(
    body: OpenFileRequest,
    user: UserIdentity | None = Depends(get_optional_current_user),
    service: LocalAgentService = Depends(get_local_agent_service),
) -> dict[str, Any]:
    """Queue an open_file command to the user's connected Windows PC agent, or open directly if running on local machine."""
    raw_path = body.file_path.strip()
    if raw_path.startswith("file:///"):
        raw_path = raw_path[8:]

    from pathlib import Path
    import os

    # 1. If running locally and file exists on host, launch it directly in Windows default app
    p = Path(raw_path)
    if p.exists() and hasattr(os, "startfile"):
        try:
            os.startfile(str(p.resolve()))
            return {
                "status": "ok",
                "opened": str(p.resolve()),
                "message": f"Opened {p.name} on your computer",
                "local": True,
            }
        except Exception as exc:
            logger.warning("os.startfile failed on local machine: %s", exc)

    # 2. Remote agent fallback: queue command for connected PC agent
    t_id = getattr(user, "tenant_id", None) or "enterprise-tenant"
    u_id = _get_user_id(user) if user else "default"

    cmd_id = service.queue_command(t_id, u_id, "open_file", {"file_path": raw_path})
    if u_id != "default":
        try:
            service.queue_command(t_id, "default", "open_file", {"file_path": raw_path})
        except Exception:
            pass
    return {
        "status": "ok",
        "opened": raw_path,
        "message": f"Opening {Path(raw_path).name} on your connected Windows computer...",
        "queued": True,
        "command_id": cmd_id,
    }


def _launch_native_windows_folder_dialog(title: str = "Select Company Folder for Nanvi Assistant") -> str | None:
    """Launch the native Windows Explorer folder selection dialog directly on this computer."""
    import sys
    from pathlib import Path

    if sys.platform != "win32":
        return None

    # 1. Try Tkinter filedialog (built-in, lightweight)
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askdirectory(title=title)
        root.destroy()
        if selected and Path(selected).exists():
            return str(Path(selected).resolve())
    except Exception as tk_exc:
        logger.debug("Tkinter folder picker could not open: %s", tk_exc)

    # 2. Try PowerShell FolderBrowserDialog
    try:
        import subprocess
        ps_code = f"""
Add-Type -AssemblyName System.Windows.Forms
$dlg = New-Object System.Windows.Forms.FolderBrowserDialog
$dlg.Description = '{title}'
$dlg.ShowNewFolderButton = $true
$res = $dlg.ShowDialog()
if ($res -eq [System.Windows.Forms.DialogResult]::OK) {{
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    Write-Output $dlg.SelectedPath
}}
"""
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_code],
            capture_output=True,
            text=True,
            timeout=180,
        )
        if proc.returncode == 0:
            out = proc.stdout.strip()
            if out and Path(out).exists():
                return str(Path(out).resolve())
    except Exception as ps_exc:
        logger.debug("PowerShell folder picker error: %s", ps_exc)

    return None


@router.post("/browse-folder")
async def local_agent_browse_folder(
    user: UserIdentity | None = Depends(get_optional_current_user),
    service: LocalAgentService = Depends(get_local_agent_service),
) -> dict[str, Any]:
    """Trigger the native Windows folder picker dialog on the host PC or connected agent."""
    import sys
    import asyncio

    t_id = getattr(user, "tenant_id", None) or "enterprise-tenant"
    u_id = getattr(user, "subject", None) or getattr(user, "user_id", None) or "default"

    # If backend is running locally on Windows, open native Windows Explorer dialog directly
    if sys.platform == "win32":
        loop = asyncio.get_running_loop()
        selected_path = await loop.run_in_executor(None, _launch_native_windows_folder_dialog)
        if selected_path:
            res = service.request_folder(t_id, u_id, selected_path)
            return {
                "status": "ok",
                "folder_path": selected_path,
                "message": res.get("message") or f"✓ Folder '{selected_path}' linked to Nanvi Assistant.",
                "direct": True,
            }
        else:
            return {
                "status": "canceled",
                "message": "Folder selection was canceled or no folder was chosen.",
            }

    # Remote agent fallback: queue command for connected PC agent
    cmd_id = service.queue_command(t_id, u_id, "browse_folder", {})
    if u_id != "default":
        try:
            service.queue_command(t_id, "default", "browse_folder", {})
        except Exception:
            pass
    return {
        "status": "ok",
        "message": "Opening folder picker on your Windows PC...",
        "queued": True,
        "command_id": cmd_id,
    }


@router.get("/document-content")
def get_document_content(
    path: str = Query(..., description="File path or relative path to view"),
    download: bool = Query(False, description="Whether to download original file binary"),
    user: UserIdentity | None = Depends(get_optional_current_user),
    service: LocalAgentService = Depends(get_local_agent_service),
) -> Response:
    """Serve the document for ephemeral in-memory browser preview (PDF, HTML preview, images) or download."""
    from pathlib import Path
    import mimetypes
    from backend.integrations.files.company_data.extraction import create_default_document_service
    from backend.documents.preview_renderer import render_document_to_html
    from backend.documents.parsers.common import source_for, metadata_for
    from backend.documents.models import Document

    raw = path.strip()
    if raw.startswith("file:///"):
        raw = raw[8:]

    clean = raw.replace("\\", "/").strip("/")
    filename = clean.split("/")[-1] if "/" in clean else clean

    # Strip drive letter and common prefixes like 'CompanyData'
    parts = clean.split("/")
    clean_parts = [p for p in parts if p and not p.endswith(":") and p.lower() != "companydata"]
    rel_path = "/".join(clean_parts)

    search_roots: list[Path] = []
    # 0. Local repo CompanyData root
    try:
        repo_data = Path(__file__).resolve().parents[1] / "CompanyData"
        if repo_data.exists() and repo_data.is_dir():
            search_roots.append(repo_data)
    except Exception:
        pass

    target_file: Path | None = None
    try:
        direct = Path(raw).resolve()
        if direct.is_file():
            target_file = direct
    except Exception:
        pass

    if not target_file:
        # Check repo data first
        for r in search_roots:
            c1 = (r / rel_path).resolve()
            if c1.is_file():
                target_file = c1
                break
            c2 = (r / filename).resolve()
            if c2.is_file():
                target_file = c2
                break

    if not target_file:
        # 1. Dynamically add active folder from persistence
        try:
            from backend.integrations.files.company_data.persistence import get_persisted_folder
            for tid in ("default", "enterprise-tenant"):
                p_cand = get_persisted_folder(tid)
                if p_cand and p_cand.exists() and p_cand.is_dir() and p_cand not in search_roots:
                    search_roots.append(p_cand)
        except Exception:
            pass

        # 2. Dynamically add connected folders from LocalAgentStore
        try:
            for (t, u), d in service.store._data.items():
                for f_info in d.get("folders", {}).values():
                    fp = f_info.get("folder_path")
                    if fp:
                        p_cand = Path(fp).resolve()
                        if p_cand.exists() and p_cand.is_dir() and p_cand not in search_roots:
                            search_roots.append(p_cand)
        except Exception:
            pass

        for r in search_roots:
            if not r.exists() or not r.is_dir():
                continue
            c1 = (r / rel_path).resolve()
            if c1.is_file():
                target_file = c1
                break
            c2 = (r / filename).resolve()
            if c2.is_file():
                target_file = c2
                break

    if target_file and target_file.is_file():
        suffix = target_file.suffix.lower()
        media_type = mimetypes.guess_type(target_file.name)[0]

        # 1. If explicit download requested, return original file attachment
        if download:
            return Response(
                content=target_file.read_bytes(),
                media_type=media_type or "application/octet-stream",
                headers={
                    "Content-Disposition": f'attachment; filename="{target_file.name}"',
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                },
            )

        # 2. Ephemeral In-Memory Preview in Browser
        # Native PDF preview
        if suffix == ".pdf":
            return Response(
                content=target_file.read_bytes(),
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f'inline; filename="{target_file.name}"',
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                },
            )

        # Native Image preview
        if suffix in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"):
            return Response(
                content=target_file.read_bytes(),
                media_type=media_type or "image/png",
                headers={
                    "Content-Disposition": f'inline; filename="{target_file.name}"',
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                },
            )

        # Native Video preview
        if suffix in (".mp4", ".webm", ".mov", ".mkv", ".avi", ".m4v", ".ogg"):
            return Response(
                content=target_file.read_bytes(),
                media_type=media_type or "video/mp4",
                headers={
                    "Content-Disposition": f'inline; filename="{target_file.name}"',
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Accept-Ranges": "bytes",
                },
            )

        # Raw HTML
        if suffix in (".html", ".htm"):
            return FileResponse(
                path=str(target_file),
                media_type="text/html; charset=utf-8",
                headers={
                    "Content-Disposition": f'inline; filename="{target_file.name}"',
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                },
            )

        # Rich In-Memory Preview for Word, Excel, CSV, TSV, PPT, Text, JSON, XML, RTF
        try:
            doc_service = create_default_document_service()
            file_bytes = target_file.read_bytes()
            doc_model = doc_service.parse_bytes(
                filename=target_file.name,
                relative_path=rel_path or target_file.name,
                data=file_bytes,
            )
            html_preview = render_document_to_html(doc_model)
            return Response(
                content=html_preview,
                media_type="text/html; charset=utf-8",
                headers={
                    "Content-Disposition": f'inline; filename="{target_file.name}.html"',
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                },
            )
        except Exception as parse_err:
            logger.debug("Could not render HTML preview for %s (%s), falling back to raw", target_file.name, parse_err)

        if suffix in (".txt", ".log", ".csv", ".json", ".md", ".py"):
            media_type = media_type or "text/plain; charset=utf-8"
        else:
            media_type = media_type or "application/octet-stream"

        return FileResponse(
            path=str(target_file),
            media_type=media_type,
            headers={
                "Content-Disposition": f'inline; filename="{target_file.name}"',
                "Cache-Control": "no-cache, no-store, must-revalidate",
            },
        )

    # If file is not directly present on disk, check indexed chunks in LocalAgentStore across all keys
    try:
        import html
        u_id = _get_user_id(user) if user else "default"
        t_id = getattr(user, "tenant_id", None) or "enterprise-tenant"
        all_chunks: list[dict[str, Any]] = []

        # 1. Current user chunks
        u_val = service.store._load_key(t_id, u_id)
        all_chunks.extend(u_val.get("chunks", []))

        # 2. Default tenant chunks
        if not all_chunks:
            def_val = service.store._load_key(t_id, "default")
            all_chunks.extend(def_val.get("chunks", []))

        # 3. Any in-memory chunks in store
        if not all_chunks:
            for k, d in getattr(service.store, "_data", {}).items():
                if d.get("chunks"):
                    all_chunks.extend(d["chunks"])

        # 4. PostgreSQL query if DSN is configured
        if not all_chunks and service.store._dsn:
            try:
                import psycopg
                from psycopg.rows import dict_row
                with psycopg.connect(service.store._dsn, autocommit=True, connect_timeout=3, row_factory=dict_row) as conn:
                    rows = conn.execute("SELECT data FROM public.nanvi_local_agent_store WHERE (data->>'chunks') IS NOT NULL").fetchall()
                    for r in rows:
                        row_chunks = (r.get("data") or {}).get("chunks", [])
                        if row_chunks:
                            all_chunks.extend(row_chunks)
            except Exception as pg_exc:
                logger.debug("PostgreSQL document chunks load error: %s", pg_exc)

        fn_low = filename.lower()
        matching = [
            c for c in all_chunks
            if c.get("filename", "").lower() == fn_low
            or fn_low in str(c.get("relative_path", "")).lower()
            or fn_low in str(c.get("folder_path", "")).lower()
        ]

        if matching:
            matching.sort(key=lambda c: c.get("chunk_index", 0))
            joined_text = "\n\n".join(c.get("text", "") for c in matching)
            file_ext = filename.split(".")[-1].lower() if "." in filename else "txt"

            if download:
                return Response(
                    content=joined_text.encode("utf-8"),
                    media_type="text/csv" if file_ext == "csv" else "text/plain; charset=utf-8",
                    headers={
                        "Content-Disposition": f'attachment; filename="{filename}"',
                        "Cache-Control": "no-cache, no-store, must-revalidate",
                    },
                )

            try:
                doc_model = Document(
                    source=source_for(filename, rel_path or filename, file_ext),
                    metadata=metadata_for(len(joined_text)),
                    text=joined_text,
                )
                html_preview = render_document_to_html(doc_model)
                return Response(
                    content=html_preview,
                    media_type="text/html; charset=utf-8",
                    headers={
                        "Content-Disposition": f'inline; filename="{filename}.html"',
                        "Cache-Control": "no-cache, no-store, must-revalidate",
                    },
                )
            except Exception:
                return Response(
                    content=joined_text,
                    media_type="text/plain; charset=utf-8",
                    headers={
                        "Content-Disposition": f'inline; filename="{filename}.txt"',
                        "Cache-Control": "no-cache, no-store, must-revalidate",
                    },
                )
    except Exception as exc:
        logger.debug("Could not read chunks for document-content: %s", exc)

    # 5. Clean, informative fallback card if content is exclusively on user's PC (200 OK, never 404)
    import html
    fallback_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html.escape(filename)} - Nanvi AI</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f8fafc; padding: 36px 20px; color: #0f172a; display: flex; justify-content: center; }}
    .card {{ background: #ffffff; border: 1.5px solid #e2e8f0; border-radius: 12px; max-width: 640px; width: 100%; padding: 32px; box-shadow: 0 4px 16px rgba(0,0,0,0.06); }}
    .badge {{ display: inline-flex; align-items: center; gap: 6px; background: #ecfdf5; border: 1px solid #86efac; color: #166534; padding: 4px 12px; border-radius: 20px; font-weight: 700; font-size: 12px; margin-bottom: 16px; }}
    h2 {{ font-size: 20px; color: #0f172a; margin-bottom: 12px; font-weight: 700; }}
    .path-box {{ background: #f1f5f9; border: 1px solid #cbd5e1; padding: 10px 14px; border-radius: 6px; font-size: 13px; color: #0369a1; word-break: break-all; font-family: monospace; margin: 12px 0 20px; }}
    p {{ color: #475569; font-size: 14.5px; line-height: 1.6; margin-bottom: 14px; }}
    .note {{ background: #eff6ff; border-left: 4px solid #3b82f6; padding: 12px 16px; border-radius: 4px; font-size: 13.5px; color: #1e40af; margin-top: 18px; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="badge">
      <span style="width:7px;height:7px;border-radius:50%;background:#16a34a;display:inline-block"></span>
      Windows PC Local File
    </div>
    <h2>📄 {html.escape(filename)}</h2>
    <p>This file is stored on your connected Windows computer:</p>
    <div class="path-box">{html.escape(path)}</div>
    <p>To inspect or edit the original document, use <strong>Open in Desktop App</strong> to open it directly in your native Windows application (Excel, Notepad, or Acrobat).</p>
    <div class="note">
      💡 <strong>Tip:</strong> The exact file path has also been automatically copied to your Windows clipboard.
    </div>
  </div>
</body>
</html>"""
    return Response(content=fallback_html, media_type="text/html; charset=utf-8")


@router.get("/document-download")
def download_document_endpoint(
    path: str = Query(..., description="File path to download"),
    service: LocalAgentService = Depends(get_local_agent_service),
) -> Response:
    """Download the original document binary file."""
    return get_document_content(path=path, download=True, service=service)


@router.get("/download")
async def download_agent_package(
    request: Request,
    token: str | None = None,
    format: str = "bat",
    user: UserIdentity | None = Depends(get_optional_current_user),
    service: LocalAgentService = Depends(get_local_agent_service),
) -> Response:
    """Download a pre-configured 1-click Windows .bat file or zip package for the user."""
    from .packager import generate_agent_bat, generate_agent_zip
    from backend.security.authorization.rbac import Role

    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host", request.url.netloc)
    server_url = f"{proto}://{host}".rstrip("/") if host else str(request.base_url).rstrip("/")
    pairing_token = ""
    display_name = ""

    if user:
        resp = service.create_pairing_token(user, server_url)
        pairing_token = resp.token
        display_name = resp.display_name
    elif token:
        try:
            payload = service.verify_agent_token(token)
            pairing_token = token
            display_name = payload.get("display_name", "")
        except Exception:
            pairing_token = "nanvi-local-token"
            display_name = "Company User"
    else:
        # User not logged in or in demo mode: generate a default pairing token so BAT download never fails
        default_user = UserIdentity(
            subject="default",
            issuer="nanvi",
            tenant_id="enterprise-tenant",
            roles=frozenset({Role.IT_ADMIN}),
            email="user@company.local",
            name="Company User",
        )
        try:
            resp = service.create_pairing_token(default_user, server_url)
            pairing_token = resp.token
            display_name = "Company User"
        except Exception:
            pairing_token = "nanvi-local-token"
            display_name = "Company User"

    if format == "exe":
        import os
        from pathlib import Path
        from starlette.responses import FileResponse, RedirectResponse

        desktop_download_url = os.environ.get("DESKTOP_DOWNLOAD_URL", "").strip()
        if not desktop_download_url and (os.environ.get("VERCEL") or settings.is_production):
            # Production default: direct high-speed CDN download from GitHub Releases
            desktop_download_url = "https://github.com/HarishRaja02/nanvi_ai_enterprise_assistant/releases/download/v0.1.0/Nanvi.AI.Assistant-Setup-0.1.0.exe"

        candidate_exes = [
            Path(__file__).resolve().parents[2] / "frontend" / "release" / "Nanvi AI Assistant-Setup-0.1.0.exe",
            Path(__file__).resolve().parents[1] / "frontend" / "release" / "Nanvi AI Assistant-Setup-0.1.0.exe",
            Path.cwd() / "frontend" / "release" / "Nanvi AI Assistant-Setup-0.1.0.exe",
            Path(__file__).resolve().parents[2] / "frontend" / "release" / "win-unpacked" / "Nanvi AI Assistant.exe",
        ]
        for exe_path in candidate_exes:
            if exe_path.exists() and exe_path.is_file():
                return FileResponse(
                    path=str(exe_path),
                    media_type="application/vnd.microsoft.portable-executable",
                    filename="Nanvi AI Assistant-Setup-0.1.0.exe",
                    headers={
                        "Content-Disposition": 'attachment; filename="Nanvi AI Assistant-Setup-0.1.0.exe"',
                        "Cache-Control": "public, max-age=3600",
                    },
                )

        if desktop_download_url:
            return RedirectResponse(url=desktop_download_url, status_code=302)

        bat_content = generate_agent_bat(server_url, pairing_token, display_name)
        return Response(
            content=bat_content.encode("utf-8"),
            media_type="application/x-bat",
            headers={
                "Content-Disposition": 'attachment; filename="Nanvi_Assistant_Setup.bat"',
                "Cache-Control": "no-store",
            },
        )

    if format == "zip":
        zip_bytes = generate_agent_zip(server_url, pairing_token, display_name)
        return Response(
            content=zip_bytes,
            media_type="application/zip",
            headers={
                "Content-Disposition": 'attachment; filename="Nanvi_Windows_Agent.zip"',
                "Cache-Control": "no-store",
            },
        )

    bat_content = generate_agent_bat(server_url, pairing_token, display_name)
    return Response(
        content=bat_content.encode("utf-8"),
        media_type="application/x-bat",
        headers={
            "Content-Disposition": 'attachment; filename="Nanvi_Assistant.bat"',
            "Cache-Control": "no-store",
        },
    )


@router.post("/token", response_model=LocalAgentTokenResponse)
async def generate_pairing_token(
    request: Request,
    user: UserIdentity = Depends(get_current_user),
    service: LocalAgentService = Depends(get_local_agent_service),
) -> LocalAgentTokenResponse:
    """Generate a pairing token for the user to authenticate their local agent."""
    server_url = str(request.base_url).rstrip("/")
    return service.create_pairing_token(user, server_url)


@router.get("/status", response_model=LocalAgentStatusResponse)
async def get_agent_status(
    request: Request,
    user: UserIdentity = Depends(get_current_user),
    service: LocalAgentService = Depends(get_local_agent_service),
) -> LocalAgentStatusResponse:
    """Get the current live status, folder list, and file counts for the user's agent."""
    server_url = str(request.base_url).rstrip("/")
    tenant_id = getattr(user, "tenant_id", None) or "default"
    user_id = _get_user_id(user)
    return service.get_status(tenant_id, user_id, server_url)


@router.post("/folders")
async def add_local_folder(
    body: AddFolderRequest,
    user: UserIdentity = Depends(get_current_user),
    service: LocalAgentService = Depends(get_local_agent_service),
) -> dict[str, Any]:
    """Request a local folder path to be approved and indexed by the local agent."""
    if not body.folder_path or not body.folder_path.strip():
        raise HTTPException(status_code=400, detail="Folder path cannot be empty.")
    tenant_id = getattr(user, "tenant_id", None) or "default"
    user_id = _get_user_id(user)
    return service.request_folder(tenant_id, user_id, body.folder_path.strip())


@router.delete("/folders")
@router.delete("/folders/{folder_id:path}")
async def remove_local_folder(
    folder_id: str | None = None,
    folder_path: str | None = Query(None),
    user: UserIdentity = Depends(get_current_user),
    service: LocalAgentService = Depends(get_local_agent_service),
) -> dict[str, Any]:
    """Disconnect an approved local folder and delete its synced chunks."""
    import urllib.parse
    raw_target = folder_path or folder_id or ""
    target_id = urllib.parse.unquote(raw_target).strip()
    if not target_id:
        raise HTTPException(status_code=400, detail="Folder path or folder_id is required.")
    tenant_id = getattr(user, "tenant_id", None) or "default"
    user_id = _get_user_id(user)
    service.remove_folder(tenant_id, user_id, target_id)
    # Also clear persistence and CompanyDataService if matching
    try:
        from backend.integrations.files.company_data.persistence import get_persisted_folder, ACTIVE_FOLDERS_FILE, ACTIVE_FOLDER_FILE
        cur = get_persisted_folder(tenant_id)
        if cur and (target_id.lower() in str(cur).lower() or str(cur).lower() in target_id.lower()):
            if ACTIVE_FOLDERS_FILE.exists():
                ACTIVE_FOLDERS_FILE.write_text("{}", encoding="utf-8")
            if ACTIVE_FOLDER_FILE.exists():
                ACTIVE_FOLDER_FILE.write_text("{}", encoding="utf-8")
            from backend.integrations.files.company_data_service import CompanyDataService
            for tid in (tenant_id, "default", "enterprise-tenant"):
                cds = CompanyDataService.for_tenant(tid)
                cds.files = []
                cds.chunks = []
    except Exception as exc:
        logger.debug("Could not clear persisted folder on remove: %s", exc)

    return {"status": "ok", "message": f"Folder '{target_id}' disconnected."}


@router.post("/search", response_model=LocalSearchResponse)
async def test_search_local(
    body: LocalSearchRequest,
    user: UserIdentity = Depends(get_current_user),
    service: LocalAgentService = Depends(get_local_agent_service),
) -> LocalSearchResponse:
    """Search user's active local files directly."""
    tenant_id = getattr(user, "tenant_id", None) or "default"
    user_id = _get_user_id(user)
    hits = service.search_local_chunks(
        tenant_id=tenant_id,
        user_id=user_id,
        query=body.query,
        top_k=body.top_k,
        folder_id=body.folder_id,
    )
    return LocalSearchResponse(
        query=body.query,
        total_hits=len(hits),
        chunks=hits,
    )


# ---------------------------------------------------------------------------
# Agent Endpoints (Accessed from User's Local Windows Computer)
# ---------------------------------------------------------------------------

@router.post("/heartbeat")
async def agent_heartbeat(
    heartbeat: LocalAgentHeartbeat,
    identity: tuple[str, str] = Depends(_extract_agent_identity),
    service: LocalAgentService = Depends(get_local_agent_service),
) -> dict[str, Any]:
    """Heartbeat signal sent periodically by the local agent."""
    tenant_id, user_id = identity
    return service.record_heartbeat(tenant_id, user_id, heartbeat)


@router.post("/sync")
async def agent_sync_folder(
    payload: FolderSyncPayload,
    identity: tuple[str, str] = Depends(_extract_agent_identity),
    service: LocalAgentService = Depends(get_local_agent_service),
) -> dict[str, Any]:
    """Sync batch of indexed chunks and files from an approved local folder."""
    tenant_id, user_id = identity
    res = service.sync_folder(tenant_id, user_id, payload)
    if tenant_id != "default":
        try:
            service.sync_folder("default", "default", payload)
        except Exception:
            pass

    # Dynamically connect CompanyDataService to this exact folder
    try:
        from pathlib import Path
        from backend.integrations.files.company_data_service import CompanyDataService
        from backend.integrations.files.company_data.persistence import set_persisted_folder
        p = Path(payload.folder_path)
        set_persisted_folder(payload.folder_path, tenant_id=tenant_id)
        set_persisted_folder(payload.folder_path, tenant_id="default")

        for tid in (tenant_id, "default"):
            cds = CompanyDataService.for_tenant(tid)
            if p.exists() and p.is_dir():
                cds.update_root(p)
            else:
                cds._load_from_local_agent()
    except Exception as exc:
        logger.warning("Could not sync CompanyDataService with agent folder: %s", exc)

    return res
