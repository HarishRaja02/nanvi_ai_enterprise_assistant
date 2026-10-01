from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from threading import Lock
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, AsyncIterator
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from backend.api.chat_routes import get_chat_service
from backend.core.config import settings
from backend.observability.logging import log_event
from backend.realtime.protocol import build_session_start, safe_client_event, safety_identifier
from backend.security.dependencies import get_authentication_service
from backend.security.authorization import UserAttributes

logger = logging.getLogger(__name__)
router = APIRouter(tags=["voice-realtime"])

_MAX_START_FRAME_CHARS = 20_000
_MAX_CLIENT_FRAME_CHARS = 96 * 1024
_ACTIVE_SESSIONS: set[tuple[str, str]] = set()
_ACTIVE_SESSIONS_LOCK = asyncio.Lock()
_VOICE_QUERY_LOCKS = tuple(Lock() for _ in range(64))


@dataclass
class DelegatedTask:
    task_id: str
    delegation_id: str | None
    query: str
    cancelled: bool = False
    task: asyncio.Task[None] | None = None


@asynccontextmanager
async def _session_claim(key: tuple[str, str]) -> AsyncIterator[bool]:
    async with _ACTIVE_SESSIONS_LOCK:
        claimed = key not in _ACTIVE_SESSIONS
        if claimed:
            _ACTIVE_SESSIONS.add(key)
    if not claimed:
        yield False
        return
    try:
        yield True
    finally:
        async with _ACTIVE_SESSIONS_LOCK:
            _ACTIVE_SESSIONS.discard(key)


async def _authenticate(access_token: str) -> Any:
    service = get_authentication_service()
    return await run_in_threadpool(service.authenticate_access_token, access_token)


def _origin_allowed(origin: str | None) -> bool:
    if not origin or not settings.cors_origins:
        return True
    normalized = origin.rstrip("/")
    if normalized in settings.cors_origins:
        return True
    if settings.is_production:
        return False
    parsed = urlparse(normalized)
    if parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        return False
    return any(
        (allowed := urlparse(configured.rstrip("/"))).hostname in {"localhost", "127.0.0.1", "::1"}
        and allowed.port == parsed.port
        and allowed.scheme == parsed.scheme
        for configured in settings.cors_origins
    )


def _history_for_session(service: Any, conversation_id: str, user: UserAttributes) -> list[tuple[str, str]]:
    owner = service._store.owner(conversation_id)
    if owner is not None and owner != (user.user_id, user.tenant_id):
        raise PermissionError("Conversation not found")
    if owner is None:
        return []
    return [(message.role, message.content) for message in service._store.get(conversation_id)[-6:]]


def _voice_query(body: dict[str, Any], user: UserAttributes, service: Any) -> dict[str, Any]:
    # Reuse the established voice route so conversation ownership, agent routing,
    # document permissions, SQL policy, and source registration stay in force.
    from backend.api.voice_routes import VoiceChatBody, voice_respond

    return voice_respond(
        VoiceChatBody(
            query=body["query"],
            conversation_id=body["conversation_id"],
            rag_enabled=body["rag_enabled"],
            context_override=body["context_override"],
        ),
        user=user,
        service=service,
    )


def _serialized_voice_query(body: dict[str, Any], user: UserAttributes, service: Any) -> dict[str, Any]:
    """Serialize blocking agent runs for a conversation within this worker process."""
    lock_key = hashlib.blake2s(
        f"{user.tenant_id}:{body['conversation_id']}".encode("utf-8"), digest_size=2
    ).digest()
    lock_index = int.from_bytes(lock_key, byteorder="big") % len(_VOICE_QUERY_LOCKS)
    with _VOICE_QUERY_LOCKS[lock_index]:
        return _voice_query(body, user, service)


@router.websocket("/realtime")
async def realtime_voice_socket(websocket: WebSocket) -> None:
    origin = websocket.headers.get("origin")
    if not _origin_allowed(origin):
        await websocket.close(code=4403, reason="Origin is not allowed")
        return
    if settings.is_production and websocket.url.scheme != "wss":
        await websocket.close(code=4403, reason="Secure WebSocket required")
        return

    await websocket.accept()
    if not settings.realtime_voice_enabled or not settings.openai_api_key:
        await websocket.send_json({"type": "error", "code": "voice_unavailable", "message": "Realtime voice is not configured on this server."})
        await websocket.close(code=1013, reason="Realtime voice unavailable")
        return

    try:
        raw_start = await asyncio.wait_for(websocket.receive_text(), timeout=8)
        if len(raw_start) > _MAX_START_FRAME_CHARS:
            raise ValueError("Invalid session start")
        start = json.loads(raw_start)
        if not isinstance(start, dict) or start.get("type") != "session.start":
            raise ValueError("Invalid session start")
        token = start.get("access_token")
        if not isinstance(token, str) or not token or len(token) > 16_384:
            await websocket.send_json({"type": "error", "code": "unauthorized", "message": "Authentication required."})
            await websocket.close(code=4401, reason="Authentication required")
            return

        try:
            identity = await _authenticate(token)
        except Exception:
            await websocket.send_json({"type": "error", "code": "unauthorized", "message": "Authentication required."})
            await websocket.close(code=4401, reason="Invalid or expired access token")
            return
        if not identity.tenant_id or not identity.roles:
            await websocket.close(code=4403, reason="Authorization context is incomplete")
            return
        user = UserAttributes(identity.subject, identity.tenant_id, identity.department, identity.roles)
        service = get_chat_service()

        conversation_id = start.get("conversation_id")
        if conversation_id is not None and (not isinstance(conversation_id, str) or not conversation_id or len(conversation_id) > 128):
            raise ValueError("Invalid conversation id")
        conversation_id = conversation_id or uuid4().hex
        rag_enabled = start.get("rag_enabled", True)
        if not isinstance(rag_enabled, bool):
            raise ValueError("Invalid voice session options")
        preferences = start.get("preferences", {})
        if not isinstance(preferences, dict):
            raise ValueError("Invalid voice session preferences")
        requested_verbosity = preferences.get("verbosity", "normal")
        preferences = {
            "verbosity": requested_verbosity if isinstance(requested_verbosity, str) and requested_verbosity in {"concise", "normal", "detailed"} else "normal",
            "privacy_mode": preferences.get("privacy_mode", False) if isinstance(preferences.get("privacy_mode", False), bool) else False,
        }

        history = await run_in_threadpool(_history_for_session, service, conversation_id, user)
        session_key = (user.tenant_id, user.user_id)
        async with _session_claim(session_key) as claimed:
            if not claimed:
                await websocket.send_json({"type": "error", "code": "session_exists", "message": "A Nanvi voice session is already active for this account."})
                await websocket.close(code=4429, reason="Voice session already active")
                return
            await websocket.send_json({"type": "session.connecting", "conversation_id": conversation_id})
            await _run_provider_session(
                websocket=websocket,
                user=user,
                service=service,
                access_token=token,
                conversation_id=conversation_id,
                rag_enabled=rag_enabled,
                preferences=preferences,
                history=history,
            )
    except WebSocketDisconnect:
        pass
    except (json.JSONDecodeError, ValueError, TimeoutError):
        try:
            await websocket.send_json({"type": "error", "code": "invalid_session", "message": "Nanvi could not start this voice session."})
            await websocket.close(code=4400, reason="Invalid session")
        except Exception:
            pass
    except PermissionError:
        try:
            await websocket.send_json({"type": "error", "code": "conversation_unavailable", "message": "Conversation not found."})
            await websocket.close(code=4404, reason="Conversation not found")
        except Exception:
            pass
    except Exception as exc:
        log_event(logger, "voice_realtime_session_failed", logging.ERROR, exception_type=type(exc).__name__)
        try:
            await websocket.send_json({"type": "error", "code": "provider_unavailable", "message": "Nanvi voice could not connect. Please try again."})
            await websocket.close(code=1011, reason="Voice provider unavailable")
        except Exception:
            pass


async def _run_provider_session(
    *,
    websocket: WebSocket,
    user: UserAttributes,
    service: Any,
    access_token: str,
    conversation_id: str,
    rag_enabled: bool,
    preferences: dict[str, Any],
    history: list[tuple[str, str]],
) -> None:
    client_send_lock = asyncio.Lock()
    provider_send_lock = asyncio.Lock()
    started_at = time.perf_counter()
    first_output_audio_logged = False
    last_tool_result_sent_at: float | None = None
    transcript_segments: list[tuple[int, int, str]] = []
    used_transcript_until = 0
    delegated_tasks: dict[str, DelegatedTask] = {}
    session_preferences = dict(preferences)

    async def send_client(event: dict[str, Any]) -> None:
        async with client_send_lock:
            await websocket.send_json(event)

    async def send_provider(provider: Any, event: dict[str, Any]) -> None:
        async with provider_send_lock:
            await provider.send(json.dumps(event, separators=(",", ":")))

    async with connect(
        "wss://api.openai.com/v1/live/sessions",
        additional_headers={
            "Authorization": f"Bearer {settings.openai_api_key}",
            "OpenAI-Safety-Identifier": safety_identifier(user.user_id, user.tenant_id),
        },
        open_timeout=10,
        close_timeout=4,
        ping_interval=20,
        ping_timeout=20,
        max_size=2 * 1024 * 1024,
    ) as provider:
        await provider.send(json.dumps(build_session_start(settings.realtime_voice_model, rag_enabled, history, preferences)))
        session_ready = False
        deadline = time.monotonic() + 15
        while not session_ready:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Live provider session setup timed out")
            initial_event = json.loads(await asyncio.wait_for(provider.recv(), timeout=remaining))
            if initial_event.get("type") == "error":
                raise RuntimeError("Live provider rejected the session configuration")
            if initial_event.get("type") == "session.started":
                session_ready = True

        log_event(logger, "voice_realtime_session_started", actor_id=user.user_id, tenant_id=user.tenant_id,
                  model=settings.realtime_voice_model, has_history=bool(history))
        await send_client({
            "type": "session.started",
            "conversation_id": conversation_id,
            "model": settings.realtime_voice_model,
            "connection_ms": round((time.perf_counter() - started_at) * 1000, 2),
        })

        async def run_voice_query(task: DelegatedTask) -> None:
            nonlocal last_tool_result_sent_at
            query = task.query
            started = time.perf_counter()
            log_event(logger, "voice_tool_started", actor_id=user.user_id, tenant_id=user.tenant_id,
                      capability="routed_by_chat_service", query_length=len(query))
            await send_client({
                "type": "tool.started",
                "message": "Let me check that.",
                "status": "Searching authorized Nanvi sources",
            })
            try:
                current_identity = await _authenticate(access_token)
                if current_identity.subject != user.user_id or current_identity.tenant_id != user.tenant_id:
                    raise PermissionError("Voice session identity changed")
                tool_user = UserAttributes(
                    current_identity.subject,
                    current_identity.tenant_id,
                    current_identity.department,
                    current_identity.roles,
                )
                result = await asyncio.to_thread(
                    _serialized_voice_query,
                    {
                        "query": query,
                        "conversation_id": conversation_id,
                        "rag_enabled": rag_enabled,
                        "context_override": dict(session_preferences),
                    },
                    tool_user,
                    service,
                )
                if task.cancelled or delegated_tasks.get(task.task_id) is not task:
                    return
                from fastapi.encoders import jsonable_encoder

                safe_result = jsonable_encoder({
                    key: result.get(key)
                    for key in (
                        "conversation_id", "answer", "spoken_text", "screen_message", "highlights",
                        "ui_specs", "important_points", "capability", "sources", "report_id",
                        "user_preferences",
                    )
                })
                await send_client({"type": "tool.completed", **safe_result})
                speech = str(result.get("spoken_text") or result.get("answer") or "I couldn't find an answer.")[:12_000]
                last_tool_result_sent_at = time.perf_counter()
                await send_provider(provider, {
                    "type": "session.commentary.append",
                    "event_id": uuid4().hex,
                    "delegation_id": task.delegation_id,
                    "content": speech,
                })
                log_event(logger, "voice_tool_completed", actor_id=user.user_id, tenant_id=user.tenant_id,
                          capability=str(result.get("capability", "")),
                          duration_ms=round((time.perf_counter() - started) * 1000, 2))
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if task.cancelled or delegated_tasks.get(task.task_id) is not task:
                    return
                log_event(logger, "voice_tool_failed", logging.ERROR, actor_id=user.user_id,
                          tenant_id=user.tenant_id, exception_type=type(exc).__name__)
                await send_client({"type": "error", "code": "voice_query_failed", "message": "Nanvi could not complete that request. Please try again."})
                await send_provider(provider, {
                    "type": "session.commentary.append",
                    "event_id": uuid4().hex,
                    "delegation_id": task.delegation_id,
                    "content": "I couldn't complete that request. Please try again.",
                })
            finally:
                if delegated_tasks.get(task.task_id) is task:
                    delegated_tasks.pop(task.task_id, None)

        async def cancel_delegated_tasks() -> None:
            if not delegated_tasks:
                return
            for task in list(delegated_tasks.values()):
                task.cancelled = True
                if task.task and not task.task.done():
                    task.task.cancel()
            delegated_tasks.clear()
            await send_client({"type": "assistant.interrupted"})

        async def start_delegated_query(provider: Any, event: dict[str, Any]) -> None:
            nonlocal used_transcript_until
            delegation = event.get("delegation") or {}
            delegation_id = delegation.get("id")
            if delegation.get("target") != "client" or not isinstance(delegation_id, str) or not delegation_id:
                return
            offset = event.get("offset_ms")
            if not isinstance(offset, int) or offset < 0:
                offset = max((segment[1] for segment in transcript_segments), default=used_transcript_until)
            await asyncio.sleep(0.2)  # transcript delivery can trail its session-timeline timestamp
            parts = [text for start_ms, end_ms, text in transcript_segments if used_transcript_until <= start_ms and end_ms <= offset]
            query = "".join(parts).strip()
            used_transcript_until = max(used_transcript_until, offset)
            transcript_segments[:] = [segment for segment in transcript_segments if segment[1] > used_transcript_until][-128:]
            if not query or len(query) > 4000:
                await send_client({"type": "error", "code": "transcript_unavailable", "message": "I missed that request. Please say it again."})
                await send_provider(provider, {
                    "type": "session.commentary.append",
                    "event_id": uuid4().hex,
                    "delegation_id": delegation_id,
                    "content": "I missed the request. Could you repeat it?",
                })
                return
            await cancel_delegated_tasks()
            task_id = uuid4().hex
            task = DelegatedTask(task_id=task_id, delegation_id=delegation_id, query=query)
            task.task = asyncio.create_task(run_voice_query(task))
            delegated_tasks[task_id] = task

        async def client_to_provider() -> None:
            nonlocal session_preferences
            while True:
                raw = await websocket.receive_text()
                if len(raw) > _MAX_CLIENT_FRAME_CHARS:
                    await send_client({"type": "error", "code": "frame_too_large", "message": "Voice audio packet is too large."})
                    continue
                try:
                    client_event = json.loads(raw)
                except json.JSONDecodeError:
                    await send_client({"type": "error", "code": "invalid_event", "message": "Invalid voice event."})
                    continue
                if isinstance(client_event, dict) and client_event.get("type") == "session.stop":
                    await send_provider(provider, {"type": "session.close", "event_id": uuid4().hex})
                    return
                safe_event = safe_client_event(client_event)
                if safe_event is None:
                    await send_client({"type": "error", "code": "unsupported_event", "message": "Unsupported voice event."})
                    continue
                kind = safe_event["type"]
                if kind == "session.input_audio.append":
                    await send_provider(provider, safe_event)
                elif kind == "user.text":
                    await cancel_delegated_tasks()
                    text = safe_event["text"]
                    task_id = uuid4().hex
                    task = DelegatedTask(task_id=task_id, delegation_id=None, query=text)
                    task.task = asyncio.create_task(run_voice_query(task))
                    delegated_tasks[task_id] = task
                elif kind == "session.preferences":
                    session_preferences = {
                        "verbosity": safe_event["verbosity"],
                        "privacy_mode": safe_event["privacy_mode"],
                    }
                    pref = safe_event["verbosity"]
                    privacy = "on" if safe_event["privacy_mode"] else "off"
                    await send_provider(provider, {
                        "type": "session.instructions.append",
                        "event_id": uuid4().hex,
                        "delegation_id": None,
                        "content": f"Spoken answer length preference is now {pref}. Privacy mode is {privacy}.",
                    })
                    await send_client({"type": "session.preferences.updated"})
                elif kind == "user.interrupt":
                    await cancel_delegated_tasks()
                    await send_provider(provider, {
                        "type": "session.instructions.append",
                        "event_id": uuid4().hex,
                        "delegation_id": None,
                        "content": "The user interrupted. Stop speaking immediately and wait for the user to continue.",
                    })

        async def provider_to_client() -> None:
            nonlocal used_transcript_until, first_output_audio_logged, last_tool_result_sent_at
            while True:
                raw = await provider.recv()
                if not isinstance(raw, str):
                    continue
                try:
                    event = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                kind = event.get("type", "")
                if kind == "error":
                    provider_error = event.get("error") or {}
                    log_event(logger, "voice_realtime_provider_error", logging.WARNING,
                              provider_code=str(provider_error.get("code", ""))[:100])
                    await send_client({"type": "error", "code": "provider_error", "message": "Nanvi voice encountered a provider error."})
                elif kind == "session.input_transcript.delta":
                    text = event.get("delta")
                    start_ms = event.get("start_ms")
                    end_ms = event.get("end_ms")
                    if isinstance(text, str) and text:
                        if isinstance(start_ms, int) and isinstance(end_ms, int) and end_ms >= start_ms:
                            transcript_segments.append((start_ms, end_ms, text))
                            transcript_segments[:] = transcript_segments[-256:]
                        await send_client({"type": "transcript.delta", "text": text})
                elif kind == "session.output_transcript.delta":
                    text = event.get("delta")
                    if isinstance(text, str) and text:
                        await send_client({"type": "assistant.text.delta", "text": text})
                elif kind == "session.output_audio.delta":
                    delta = event.get("delta")
                    if isinstance(delta, str) and delta:
                        now = time.perf_counter()
                        if not first_output_audio_logged:
                            first_output_audio_logged = True
                            log_event(logger, "voice_first_audio_chunk", actor_id=user.user_id,
                                      duration_ms=round((now - started_at) * 1000, 2))
                        if last_tool_result_sent_at is not None:
                            log_event(logger, "voice_first_audio_after_tool_result", actor_id=user.user_id,
                                      duration_ms=round((now - last_tool_result_sent_at) * 1000, 2))
                            last_tool_result_sent_at = None
                        await send_client({"type": "assistant.audio.delta", "audio": delta})
                elif kind == "session.delegation.created":
                    asyncio.create_task(start_delegated_query(provider, event))
                elif kind == "session.closed":
                    await cancel_delegated_tasks()
                    await send_client({"type": "session.disconnected", "reason": event.get("reason", "closed")})
                    return

        client_task = asyncio.create_task(client_to_provider())
        provider_task = asyncio.create_task(provider_to_client())
        done, _ = await asyncio.wait({client_task, provider_task}, return_when=asyncio.FIRST_COMPLETED)
        if client_task in done:
            try:
                await asyncio.wait_for(provider_task, timeout=8)
            except (TimeoutError, ConnectionClosed, WebSocketDisconnect):
                provider_task.cancel()
                await asyncio.gather(provider_task, return_exceptions=True)
        else:
            client_task.cancel()
            await asyncio.gather(client_task, return_exceptions=True)
        for task in delegated_tasks.values():
            task.cancelled = True
            if task.task and not task.task.done():
                task.task.cancel()
        log_event(logger, "voice_realtime_session_ended", actor_id=user.user_id, tenant_id=user.tenant_id)
