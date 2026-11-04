from __future__ import annotations

from dataclasses import asdict
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse, FileResponse, HTMLResponse, Response
from pydantic import BaseModel, Field

from backend.chat.models import ChatRequest
from backend.chat.service import ChatService
from backend.security.authorization import UserAttributes
from backend.security.dependencies import get_current_user
from backend.security.models import UserIdentity
from backend.security.authorization.rbac import Role
from backend.observability.logging import log_event
from backend.uecp import require_uecp_access
import logging
import time

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])

import base64
from pathlib import Path
from backend.agents.models import Capability

class ChatBody(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = Field(default=None, min_length=1, max_length=128)
    rag_enabled: bool = Field(default=True)
    active_document_id: str | None = Field(default=None)
    context_override: dict[str, Any] | None = Field(default=None)

class UploadDocumentBody(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_base64: str = Field(min_length=1)
    conversation_id: str | None = Field(default=None)

ALLOWED_EXTENSIONS = {
    ".pdf",
    ".doc", ".docx",
    ".xls", ".xlsx", ".xlsm", ".xltx",
    ".csv", ".tsv",
    ".txt", ".text", ".md", ".markdown", ".log",
    ".rtf",
    ".json", ".jsonl",
    ".xml",
    ".html", ".htm",
    ".ppt", ".pptx",
    ".yaml", ".yml",
}

def get_chat_service() -> ChatService:
    return _chat_service_instance


def _init_chat_service() -> ChatService:
    """Create the singleton ChatService using the bootstrap module.

    Lazy-initialized at module import so startup errors are visible immediately.
    """
    try:
        from backend.bootstrap import create_chat_service
        return create_chat_service()
    except Exception as exc:
        logger.error("Failed to initialize ChatService: %s", type(exc).__name__)
        raise


_chat_service_instance = _init_chat_service()

def current_attributes(identity: UserIdentity = Depends(get_current_user)) -> UserAttributes:
    if not identity.tenant_id or not identity.roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Authorization context is incomplete")
    return UserAttributes(identity.subject, identity.tenant_id, identity.department, identity.roles)

@router.post("")
def chat(
    body: ChatBody,
    user: UserAttributes = Depends(current_attributes),
    service: ChatService = Depends(get_chat_service),
    _uecp: Any = Depends(require_uecp_access(permission="ai.chat")),
):
    started = time.perf_counter()
    log_event(logger, "api_chat_started", actor_id=user.user_id, tenant_id=user.tenant_id,
              query_length=len(body.query), has_conversation=bool(body.conversation_id))
    try:
        response = service.ask(
            user,
            ChatRequest(
                body.query,
                body.conversation_id,
                body.rag_enabled,
                active_document_id=body.active_document_id,
            ),
        )
    except PermissionError:
        log_event(logger, "api_chat_failed", logging.WARNING, actor_id=user.user_id, tenant_id=user.tenant_id,
                  outcome="not_found", duration_ms=round((time.perf_counter() - started) * 1000, 2))
        raise HTTPException(status_code=404, detail="Conversation not found")
    except ValueError as exc:
        log_event(logger, "api_chat_failed", logging.WARNING, actor_id=user.user_id, tenant_id=user.tenant_id,
                  outcome="validation_error", exception_type=type(exc).__name__, duration_ms=round((time.perf_counter() - started) * 1000, 2))
        raise HTTPException(status_code=422, detail=str(exc))
    except RuntimeError as exc:
        log_event(logger, "api_chat_failed", logging.ERROR, actor_id=user.user_id, tenant_id=user.tenant_id,
                  outcome="orchestration_error", exception_type=type(exc).__name__, duration_ms=round((time.perf_counter() - started) * 1000, 2))
        raise HTTPException(status_code=502, detail="AI orchestration failed")
    except Exception as exc:
        log_event(logger, "api_chat_failed", logging.ERROR, actor_id=user.user_id, tenant_id=user.tenant_id,
                  outcome="unexpected_error", exception_type=type(exc).__name__, duration_ms=round((time.perf_counter() - started) * 1000, 2))
        logger.exception("Unexpected error in chat endpoint: %s", exc)
        return {
            "conversation_id": body.conversation_id or "default",
            "answer": "I encountered an unexpected issue while processing your request. Please try again or rephrase your query.",
            "capability": "conversation",
            "sources": [],
            "trace": [f"Error: {type(exc).__name__}"],
            "history": [],
            "report_id": None,
            "data_source": "live",
            "source_selection_required": False,
            "pending_search_query": None,
            "file_results": None,
        }
    log_event(logger, "api_chat_completed", actor_id=user.user_id, tenant_id=user.tenant_id,
              capability=str(response.capability), source_count=len(response.sources),
              duration_ms=round((time.perf_counter() - started) * 1000, 2))
    # Ensure all sources in the response are securely registered in the source store
    try:
        from backend.sources.dependencies import get_source_store
        store = get_source_store()
        for s in response.sources:
            stype = s.source_type.value if hasattr(s.source_type, "value") else str(s.source_type)
            store.save(
                reference=s,
                owner_id=user.user_id,
                tenant_id=user.tenant_id,
                source_id=s.reference_id,
                source_type=stype,
                department=user.department,
                restricted_department=None,
            )
    except Exception as exc:
        logger.warning("Could not auto-register sources: %s", exc)

    return {
        "conversation_id": response.conversation_id,
        "answer": response.answer,
        "capability": response.capability,
        "sources": [s.to_frontend_dict() for s in response.sources],
        "trace": list(response.trace),
        "history": [asdict(m) for m in response.history],
        "report_id": getattr(response, "report_id", None),
        "data_source": getattr(response, "data_source", "live"),
        "source_selection_required": getattr(response, "source_selection_required", False),
        "pending_search_query": getattr(response, "pending_search_query", None),
        "file_results": list(getattr(response, "file_results", []) or []) if getattr(response, "file_results", None) else None,
    }


class ContextUpdateBody(BaseModel):
    active_page: dict[str, Any] | None = None
    active_entity: dict[str, Any] | None = None
    active_document: dict[str, Any] | None = None
    ui_entity_index: dict[str, Any] | None = None
    user_preferences: dict[str, Any] | None = None


@router.post("/stream")
def chat_stream(
    body: ChatBody,
    user: UserAttributes = Depends(current_attributes),
    service: ChatService = Depends(get_chat_service),
    _uecp: Any = Depends(require_uecp_access(permission="ai.chat")),
):
    """Streaming chat endpoint emitting Server-Sent Events conforming to Section 6.2."""
    generator = service.stream_ask(
        user,
        ChatRequest(
            body.query,
            body.conversation_id,
            body.rag_enabled,
            active_document_id=body.active_document_id,
        ),
        context_override=body.context_override,
    )
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/context/{conversation_id}")
def get_conversation_context(
    conversation_id: str,
    user: UserAttributes = Depends(current_attributes),
    service: ChatService = Depends(get_chat_service),
):
    """Retrieve the centralized conversation context."""
    try:
        ctx = service.get_context(conversation_id, user)
        return ctx.model_dump()
    except PermissionError:
        raise HTTPException(status_code=403, detail="Forbidden")
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.put("/context/{conversation_id}")
def update_conversation_context(
    conversation_id: str,
    body: ContextUpdateBody,
    user: UserAttributes = Depends(current_attributes),
    service: ChatService = Depends(get_chat_service),
):
    """Update active page, active entity, or preferences in centralized context."""
    try:
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        updated = service.update_context(conversation_id, user, updates)
        return updated.model_dump()
    except PermissionError:
        raise HTTPException(status_code=403, detail="Forbidden")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/history")
def history(user: UserAttributes = Depends(current_attributes), service: ChatService = Depends(get_chat_service)):
    conversations = []
    for item in service.history(user):
        data = asdict(item)
        data["updated_at"] = item.last_message_at.isoformat() if item.last_message_at else None
        data["created_at"] = data["updated_at"]
        conversations.append(data)
    return {"conversations": conversations}


@router.get("/history/{conversation_id}")
def get_conversation_history(conversation_id: str, user: UserAttributes = Depends(current_attributes), service: ChatService = Depends(get_chat_service)):
    owner = service._store.owner(conversation_id)
    if not owner or owner != (user.user_id, user.tenant_id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    messages = service._store.get(conversation_id)
    return {"conversation_id": conversation_id, "messages": [asdict(m) for m in messages]}


@router.post("/upload")
def upload_document_for_rag(
    body: UploadDocumentBody,
    user: UserAttributes = Depends(current_attributes),
    service: ChatService = Depends(get_chat_service),
    _uecp: Any = Depends(require_uecp_access(permission="documents.write")),
):
    """Upload a document directly from chat into the RAG knowledge vault."""
    ext = Path(body.filename).suffix.casefold()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    clean_filename = Path(body.filename).name.strip()
    if not clean_filename:
        clean_filename = "uploaded_document" + ext

    try:
        data = base64.b64decode(body.content_base64)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 document content")

    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File exceeds maximum size of 15MB")

    # Save to active company data folder Uploads or storage fallback
    from backend.integrations.files.company_data_service import CompanyDataService
    active_root = CompanyDataService.for_tenant(user.tenant_id).root
    dest = None
    if active_root and str(active_root) and active_root.exists() and active_root.is_dir():
        upload_dir = active_root / "Uploads"
        try:
            upload_dir.mkdir(parents=True, exist_ok=True)
            dest = upload_dir / clean_filename
            dest.write_bytes(data)
        except Exception as exc:
            logger.warning("Failed to write to %s (%s)", upload_dir, exc)

    if not dest or not dest.exists():
        fallback_dir = Path(__file__).resolve().parent.parent / "storage" / "uploads"
        fallback_dir.mkdir(parents=True, exist_ok=True)
        dest = fallback_dir / clean_filename
        dest.write_bytes(data)

    # Trigger re-index in company data service
    try:
        CompanyDataService.for_tenant(user.tenant_id).ensure_indexed(force=True)
    except Exception as exc:
        logger.warning("Could not re-index after upload: %s", exc)

    # Register active document in chat service for conversation continuity
    cid = getattr(body, "conversation_id", None) or "default"
    if hasattr(service, "set_active_document"):
        service.set_active_document(cid, clean_filename)
        service.set_active_document("default", clean_filename)

    return {
        "status": "ok",
        "filename": clean_filename,
        "path": f"Uploads/{clean_filename}",
        "document_id": f"Uploads/{clean_filename}",
        "size_bytes": len(data),
        "message": f"Successfully ingested {clean_filename} into RAG Knowledge Vault",
    }


class FileSearchBody(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    source: str = Field(description="local, database, email, drive, or cloud")
    conversation_id: str | None = None
    max_results: int = 10


class OpenFileBody(BaseModel):
    file_path: str = Field(min_length=1)


@router.post("/file-search")
def file_search(
    body: FileSearchBody,
    user: UserAttributes = Depends(current_attributes),
    service: ChatService = Depends(get_chat_service),
    _uecp: Any = Depends(require_uecp_access(permission="documents.read")),
):
    """Targeted search for files across a user-chosen enterprise source."""
    from backend.chat.file_search import execute_file_search
    from backend.chat.models import ChatMessage
    from datetime import datetime, timezone

    conversation_id = body.conversation_id or "default"
    answer, files, sources = execute_file_search(
        user=user,
        query=body.query,
        source=body.source,
        max_results=body.max_results,
    )

    if hasattr(service, "_store") and service._store is not None:
        try:
            service._store.append(conversation_id, ChatMessage("assistant", answer, datetime.now(timezone.utc)))
        except Exception as exc:
            logger.warning("Could not append file search to store: %s", exc)

    return {
        "conversation_id": conversation_id,
        "answer": answer,
        "files": files,
        "total_count": len(files),
        "source": body.source,
        "capability": "document_search",
        "sources": [s.to_frontend_dict() for s in sources],
    }


@router.post("/open-file")
def open_local_file(
    body: OpenFileBody,
    user: UserAttributes = Depends(current_attributes),
):
    """Open a local file in the system default application or queue for Windows PC agent."""
    raw_path = body.file_path.strip()
    if raw_path.startswith("file:///"):
        raw_path = raw_path[8:]

    p = Path(raw_path)

    # 1. If running locally on server host with file available (local development)
    if p.is_absolute() and p.exists():
        try:
            import os
            if hasattr(os, "startfile"):
                os.startfile(str(p.resolve()))
                return {"status": "ok", "opened": str(p.resolve()), "message": f"Opened {p.name} on your computer"}
        except Exception as exc:
            logger.warning("os.startfile failed: %s", exc)

    # 2. Fast Cloud / Vercel fallback: Queue the open_file command to the user's connected Windows PC agent
    try:
        from backend.local_agent.service import get_local_agent_service
        local_svc = get_local_agent_service()
        u_id = user.user_id or "default"
        t_id = user.tenant_id or "default"
        cmd_id = local_svc.queue_command(t_id, u_id, "open_file", {"file_path": raw_path})
        return {
            "status": "ok",
            "opened": raw_path,
            "message": f"Opening {Path(raw_path).name} on your connected Windows computer...",
            "queued": True,
            "command_id": cmd_id,
        }
    except Exception as exc:
        logger.warning("Could not queue open command to agent: %s", exc)
        return {"status": "ok", "opened": raw_path, "message": f"Opening {Path(raw_path).name} on your computer..."}


@router.get("/download-file")
def download_local_file(
    path: str,
    token: str | None = Query(None),
):
    """Serve a local file for browser preview or download.

    Supports direct browser navigation with ?token=<jwt> or public access for authenticated sessions.
    If the file is located on the user's connected Windows computer, serves a clean HTML preview.
    """
    raw_path = path.strip()
    if raw_path.startswith("file:///"):
        raw_path = raw_path[8:]

    p = Path(raw_path)

    # 1. Check if real file exists on server filesystem
    if p.is_file():
        return FileResponse(path=str(p.resolve()), filename=p.name)

    try:
        from backend.integrations.files.company_data_service import CompanyDataService
        root = CompanyDataService.for_tenant("default").root
        if root and str(root) and root.exists() and root.is_dir():
            root_res = root.resolve()
            candidate = (root_res / raw_path).resolve()
            if candidate.is_file():
                return FileResponse(path=str(candidate), filename=candidate.name)
            matches = [m for m in root_res.rglob(p.name) if m.is_file()]
            if matches:
                return FileResponse(path=str(matches[0]), filename=matches[0].name)
    except Exception:
        pass

    # 2. Look up chunks in LocalAgentStore (for files on user's connected Windows PC)
    matching_chunks = []
    try:
        from backend.local_agent.service import get_local_agent_service
        local_svc = get_local_agent_service()
        val = local_svc.store._load_key("default", "default")
        chunks = val.get("chunks", [])
        if not chunks:
            for _, d in local_svc.store._data.items():
                if d.get("chunks"):
                    chunks = d.get("chunks")
                    break

        fn_low = p.name.casefold()
        matching_chunks = [
            c for c in chunks
            if c.get("filename", "").casefold() == fn_low or fn_low in c.get("relative_path", "").casefold()
        ]
        matching_chunks.sort(key=lambda c: c.get("chunk_index", 0))
    except Exception as exc:
        logger.debug("Error looking up chunks for preview: %s", exc)

    title = p.name
    folder = ""
    joined_text = ""
    if matching_chunks:
        title = matching_chunks[0].get("filename", p.name)
        folder = matching_chunks[0].get("folder_name", "")
        joined_text = "\n\n".join(c.get("text", "") for c in matching_chunks)

    escaped_raw_path = raw_path.replace("\\", "\\\\").replace("'", "\\'")

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} - Nanvi Enterprise Assistant</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      line-height: 1.6;
      color: #0f172a;
      background: #f8fafc;
      margin: 0;
      padding: 32px 16px;
    }}
    .container {{
      max-width: 860px;
      margin: 0 auto;
      background: #ffffff;
      border-radius: 12px;
      box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1);
      border: 1px solid #e2e8f0;
      overflow: hidden;
    }}
    .header {{
      padding: 24px 32px;
      border-bottom: 1px solid #e2e8f0;
      background: #f1f5f9;
    }}
    .badge {{
      display: inline-block;
      padding: 4px 10px;
      background: #e0f2fe;
      color: #0369a1;
      font-size: 12px;
      font-weight: 600;
      border-radius: 6px;
      margin-bottom: 10px;
    }}
    h1 {{
      margin: 0 0 12px;
      font-size: 20px;
      color: #0f172a;
      word-break: break-all;
    }}
    .path-card {{
      background: #ffffff;
      border: 1px solid #cbd5e1;
      border-radius: 8px;
      padding: 12px 16px;
      margin-top: 12px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
    }}
    .path-text {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 13px;
      color: #0284c7;
      word-break: break-all;
      flex: 1;
      min-width: 200px;
    }}
    .copy-btn {{
      background: #0284c7;
      color: #ffffff;
      border: none;
      border-radius: 6px;
      padding: 8px 16px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      transition: background 0.15s ease;
      flex-shrink: 0;
    }}
    .copy-btn:hover {{
      background: #0369a1;
    }}
    .instructions {{
      background: #f0fdf4;
      border: 1px solid #bbf7d0;
      border-radius: 8px;
      padding: 14px 18px;
      margin: 24px 32px 0;
      font-size: 13.5px;
      color: #166534;
    }}
    .instructions strong {{
      color: #14532d;
    }}
    .instructions kbd {{
      background: #ffffff;
      border: 1px solid #cbd5e1;
      border-radius: 4px;
      padding: 2px 6px;
      font-family: monospace;
      font-size: 12px;
      box-shadow: 0 1px 1px rgba(0,0,0,0.1);
    }}
    .content {{
      padding: 24px 32px 32px;
      font-size: 14.5px;
      color: #334155;
    }}
    .content-title {{
      font-size: 13px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: #64748b;
      margin-bottom: 8px;
    }}
    .text-box {{
      background: #f8fafc;
      border: 1px solid #e2e8f0;
      border-radius: 8px;
      padding: 20px;
      white-space: pre-wrap;
      max-height: 500px;
      overflow-y: auto;
      line-height: 1.6;
    }}
    .footer {{
      padding: 16px 32px;
      background: #f8fafc;
      border-top: 1px solid #e2e8f0;
      font-size: 13px;
      color: #94a3b8;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div class="badge">Local Windows PC Document</div>
      <h1>{title}</h1>
      <div class="path-card">
        <div class="path-text" id="filePath">{raw_path}</div>
        <button type="button" class="copy-btn" id="copyBtn" onclick="copyFilePath()">
          <span>Copy File Path</span>
        </button>
      </div>
    </div>

    <div class="instructions">
      <strong>💡 How to open on your computer:</strong><br>
      1. Click <strong>"Copy File Path"</strong> above.<br>
      2. Press <kbd>Win</kbd> + <kbd>R</kbd> on your keyboard (or open Windows File Explorer).<br>
      3. Paste the path and press <kbd>Enter</kbd> to open directly in your default app.
    </div>

    <div class="content">
      {f'<div class="content-title">Indexed Document Content</div><div class="text-box">{joined_text}</div>' if joined_text else '<div style="color: #64748b; font-style: italic; padding: 12px 0;">This file is stored on your connected computer. Copy the path above to open the original file.</div>'}
    </div>

    <div class="footer">
      <span>Nanvi Enterprise Assistant</span>
      <span>Indexed from your local storage</span>
    </div>
  </div>

  <script>
    function copyFilePath() {{
      const text = '{escaped_raw_path}';
      navigator.clipboard.writeText(text).then(() => {{
        const btn = document.getElementById('copyBtn');
        btn.innerHTML = '<span>✅ Copied!</span>';
        btn.style.background = '#16a34a';
        setTimeout(() => {{
          btn.innerHTML = '<span>Copy File Path</span>';
          btn.style.background = '#0284c7';
        }}, 2500);
      }}).catch(() => {{
        prompt('Copy this file path:', text);
      }});
    }}
  </script>
</body>
</html>"""
    return HTMLResponse(content=html_content)



