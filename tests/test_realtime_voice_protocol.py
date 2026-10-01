from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from backend.realtime.protocol import (
    MAX_AUDIO_EVENT_CHARS,
    build_session_start,
    safe_client_event,
    safety_identifier,
)
from backend.security.exceptions import AuthenticationError
from backend.security.authorization import UserAttributes


def test_live_session_uses_full_duplex_audio_and_client_delegation():
    payload = build_session_start(
        "gpt-live-1",
        rag_enabled=True,
        history=[("user", "What is RAG?"), ("assistant", "Retrieval-Augmented Generation.")],
    )["session"]

    assert payload["model"] == "gpt-live-1"
    assert payload["delegation"] == {"type": "client"}
    assert payload["audio"]["format"] == {"type": "audio/pcm", "rate": 24_000}
    assert payload["audio"]["output"]["voice"] == "marin"
    assert len(payload["input"]) == 2
    assert payload["input"][1]["content"][0]["text"] == "Retrieval-Augmented Generation."
    assert "do not thank the user for asking" in payload["instructions"]
    assert "Stay quiet while work runs" in payload["instructions"]


def test_conversational_fallback_does_not_add_automatic_thanks():
    from backend.chat.service import ChatService

    reply = ChatService._generate_conversational_reply("How are you?")
    assert "thank you" not in reply.casefold()


def test_client_event_boundary_only_allows_audio_text_and_preferences():
    assert safe_client_event({"type": "session.update", "session": {"instructions": "override"}}) is None
    assert safe_client_event({"type": "session.input_audio.append", "audio": "A" * (MAX_AUDIO_EVENT_CHARS + 1)}) is None
    assert safe_client_event({"type": "session.input_audio.append", "audio": "AQID"}) == {
        "type": "session.input_audio.append", "audio": "AQID",
    }
    assert safe_client_event({"type": "session.start", "session": {"model": "attacker-model"}}) is None
    assert safe_client_event({"type": "user.text", "text": " "}) is None
    assert safe_client_event({"type": "user.text", "text": "  Hello Nanvi  "}) == {
        "type": "user.text",
        "text": "Hello Nanvi",
    }
    assert safe_client_event({"type": "user.interrupt"}) == {"type": "user.interrupt"}
    assert safe_client_event({"type": "user.interrupt", "provider_event": "response.cancel"}) == {"type": "user.interrupt"}


def test_safety_identifier_is_stable_and_does_not_reveal_identity():
    first = safety_identifier("employee-1004", "tenant-a")
    assert first == safety_identifier("employee-1004", "tenant-a")
    assert first != safety_identifier("employee-1005", "tenant-a")
    assert "employee-1004" not in first
    assert len(first) == 64


def test_blocking_voice_graph_runs_are_serialized_per_conversation(monkeypatch: pytest.MonkeyPatch):
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor
    from backend.realtime import websocket as realtime_websocket

    first_entered = threading.Event()
    release_first = threading.Event()
    started_queries: list[str] = []

    def fake_query(body, _user, _service):
        started_queries.append(body["query"])
        if body["query"] == "first":
            first_entered.set()
            assert release_first.wait(timeout=2)
        return {"answer": body["query"]}

    monkeypatch.setattr(realtime_websocket, "_voice_query", fake_query)
    user = SimpleNamespace(tenant_id="tenant-1")
    service = object()
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(
            realtime_websocket._serialized_voice_query,
            {"query": "first", "conversation_id": "conversation-1"},
            user,
            service,
        )
        assert first_entered.wait(timeout=2)
        second = executor.submit(
            realtime_websocket._serialized_voice_query,
            {"query": "second", "conversation_id": "conversation-1"},
            user,
            service,
        )
        time.sleep(0.05)
        assert started_queries == ["first"]
        release_first.set()
        assert first.result(timeout=2) == {"answer": "first"}
        assert second.result(timeout=2) == {"answer": "second"}


def test_voice_realtime_status_never_returns_provider_secret(monkeypatch: pytest.MonkeyPatch):
    from backend.api import voice_routes

    monkeypatch.setattr(
        voice_routes,
        "settings",
        SimpleNamespace(realtime_voice_enabled=True, openai_api_key="server-only-secret", realtime_voice_model="gpt-live-1"),
    )
    response = voice_routes.realtime_voice_status(
        UserAttributes("user-1", "tenant-1", None, frozenset({"Employee"}))
    )
    assert response == {"enabled": True, "model": "gpt-live-1"}
    assert "server-only-secret" not in str(response)


def test_websocket_authenticates_first_message_before_provider_connect(monkeypatch: pytest.MonkeyPatch):
    from backend.main import app
    from backend.realtime import websocket as realtime_websocket

    monkeypatch.setattr(
        realtime_websocket,
        "settings",
        SimpleNamespace(
            is_production=False,
            cors_origins=(),
            realtime_voice_enabled=True,
            openai_api_key="server-only-secret",
            realtime_voice_model="gpt-live-1",
        ),
    )

    async def reject_token(_token: str):
        raise AuthenticationError("invalid")

    monkeypatch.setattr(realtime_websocket, "_authenticate", reject_token)

    with TestClient(app).websocket_connect("/api/voice/realtime") as socket:
        socket.send_json({"type": "session.start", "access_token": "invalid-token", "rag_enabled": True})
        error = socket.receive_json()
        assert error == {"type": "error", "code": "unauthorized", "message": "Authentication required."}
        with pytest.raises(WebSocketDisconnect) as closed:
            socket.receive_json()
        assert closed.value.code == 4401


def test_websocket_relays_audio_through_authenticated_voice_agent(monkeypatch: pytest.MonkeyPatch):
    import asyncio
    import json
    from contextlib import asynccontextmanager
    from backend.main import app
    from backend.realtime import websocket as realtime_websocket

    monkeypatch.setattr(
        realtime_websocket,
        "settings",
        SimpleNamespace(
            is_production=False,
            cors_origins=(),
            realtime_voice_enabled=True,
            openai_api_key="server-only-secret",
            realtime_voice_model="gpt-live-1",
        ),
    )

    identity = SimpleNamespace(subject="user-1", tenant_id="tenant-1", department="Operations", roles=("Employee",))

    async def authenticate(_token: str):
        return identity

    class Store:
        def owner(self, _conversation_id: str):
            return None

        def get(self, _conversation_id: str):
            return ()

    service = SimpleNamespace(_store=Store())
    executed_queries: list[str] = []

    def voice_query(body, _user, _service):
        executed_queries.append(body["query"])
        return {
            "conversation_id": body["conversation_id"],
            "answer": "The leave policy grants 18 annual days.",
            "spoken_text": "The policy grants 18 annual leave days.",
            "capability": "knowledge_search",
            "sources": [],
            "important_points": ["Annual leave: 18 days."],
            "user_preferences": {"verbosity": "normal", "privacy_mode": False},
        }

    class FakeProvider:
        def __init__(self):
            self.events = asyncio.Queue()
            self.sent = []

        async def send(self, raw: str):
            event = json.loads(raw)
            self.sent.append(event)
            if event["type"] == "session.start":
                await self.events.put(json.dumps({"type": "session.started", "session": {"id": "live-1"}}))
            elif event["type"] == "session.input_audio.append":
                await self.events.put(json.dumps({
                    "type": "session.input_transcript.delta",
                    "delta": "Summarize the leave policy.",
                    "start_ms": 100,
                    "end_ms": 600,
                }))
                await self.events.put(json.dumps({
                    "type": "session.delegation.created",
                    "offset_ms": 600,
                    "delegation": {"id": "delegation-1", "type": "delegation", "target": "client"},
                }))
            elif event["type"] == "session.commentary.append":
                await self.events.put(json.dumps({"type": "session.output_transcript.delta", "delta": event["content"]}))
                await self.events.put(json.dumps({"type": "session.output_audio.delta", "delta": "AAA="}))
            elif event["type"] == "session.close":
                await self.events.put(json.dumps({"type": "session.closed", "reason": "close_requested"}))

        async def recv(self):
            return await self.events.get()

    provider = FakeProvider()

    @asynccontextmanager
    async def fake_connect(uri, **kwargs):
        assert uri == "wss://api.openai.com/v1/live/sessions"
        assert "Authorization" in kwargs["additional_headers"]
        assert "server-only-secret" in kwargs["additional_headers"]["Authorization"]
        yield provider

    monkeypatch.setattr(realtime_websocket, "_authenticate", authenticate)
    monkeypatch.setattr(realtime_websocket, "get_chat_service", lambda: service)
    monkeypatch.setattr(realtime_websocket, "_voice_query", voice_query)
    monkeypatch.setattr(realtime_websocket, "connect", fake_connect)

    with TestClient(app).websocket_connect("/api/voice/realtime") as socket:
        socket.send_json({
            "type": "session.start",
            "access_token": "valid-token",
            "conversation_id": "conversation-1",
            "rag_enabled": True,
            "preferences": {"verbosity": "normal", "privacy_mode": False},
        })
        assert socket.receive_json()["type"] == "session.connecting"
        assert socket.receive_json()["type"] == "session.started"
        socket.send_json({"type": "session.input_audio.append", "audio": "AAA="})

        observed_types = []
        while "tool.completed" not in observed_types or "assistant.audio.delta" not in observed_types:
            event = socket.receive_json()
            observed_types.append(event["type"])

        assert "transcript.delta" in observed_types
        assert "tool.started" in observed_types
        assert "assistant.text.delta" in observed_types
        socket.send_json({"type": "session.stop"})
        assert socket.receive_json()["type"] == "session.disconnected"

    assert executed_queries == ["Summarize the leave policy."]
    assert any(event["type"] == "session.commentary.append" and event["delegation_id"] == "delegation-1" for event in provider.sent)
