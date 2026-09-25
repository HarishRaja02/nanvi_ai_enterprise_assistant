from __future__ import annotations

from dataclasses import asdict
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from backend.chat.models import ChatRequest
from backend.chat.service import ChatService
from backend.security.authorization import UserAttributes
from backend.security.dependencies import get_current_user
from backend.security.models import UserIdentity
from backend.security.authorization.rbac import Role
from backend.observability.logging import log_event
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

class UploadDocumentBody(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_base64: str = Field(min_length=1)

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".csv", ".txt", ".md"}

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
def chat(body: ChatBody, user: UserAttributes = Depends(current_attributes), service: ChatService = Depends(get_chat_service)):
    started = time.perf_counter()
    log_event(logger, "api_chat_started", actor_id=user.user_id, tenant_id=user.tenant_id,
              query_length=len(body.query), has_conversation=bool(body.conversation_id))
    try:
        response = service.ask(user, ChatRequest(body.query, body.conversation_id, body.rag_enabled))
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
    }


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

    # Save to active company data folder Uploads or local fallback
    from backend.integrations.files.company_data_service import CompanyDataService
    active_root = CompanyDataService.get_instance().root
    upload_dir = active_root / "Uploads"
    try:
        upload_dir.mkdir(parents=True, exist_ok=True)
        dest = upload_dir / clean_filename
        dest.write_bytes(data)
    except Exception as exc:
        logger.warning("Failed to write to %s (%s), falling back to local CompanyData", upload_dir, exc)
        fallback_dir = Path("./CompanyData/Uploads")
        fallback_dir.mkdir(parents=True, exist_ok=True)
        dest = fallback_dir / clean_filename
        dest.write_bytes(data)

    # Trigger re-index in company data service
    try:
        knowledge_agent = service._orchestrator.agents.get(Capability.KNOWLEDGE)
        if knowledge_agent and hasattr(knowledge_agent, "_company_data") and knowledge_agent._company_data:
            knowledge_agent._company_data.ensure_indexed(force=True)
    except Exception as exc:
        logger.warning("Could not re-index after upload: %s", exc)

    return {
        "status": "ok",
        "filename": clean_filename,
        "path": f"Uploads/{clean_filename}",
        "size_bytes": len(data),
        "message": f"Successfully ingested {clean_filename} into RAG Knowledge Vault",
    }

