from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.nanvi_rtc.arbitrator import InterruptionArbitrator, InterruptionDecision
from backend.nanvi_rtc.providers.base import Capabilities, LLMProvider
from backend.nanvi_rtc.providers.registry import registry
from backend.nanvi_rtc.session import AgentSession
from backend.nanvi_rtc.types import ResponseCheckpoint, ResponseStatus


class MockSink:
    def __init__(self):
        self.sent = []
        self.stops = []
        self.events = []

    async def send_chunk(self, **kwargs):
        self.sent.append(kwargs)

    async def stop(self, generation_id):
        self.stops.append(generation_id)

    async def pause(self, generation_id):
        self.events.append({"type": "pause_sink", "generation_id": generation_id})

    async def emit(self, event):
        self.events.append(event)


class SimpleScriptedLLM(LLMProvider):
    name = "scripted"
    capabilities = Capabilities()

    def __init__(self, sentences: list[str]):
        self.sentences = sentences
        self.calls = []

    async def stream(self, messages, *, system=None):
        self.calls.append(messages)
        for s in self.sentences:
            await asyncio.sleep(0.01)
            yield s + " "


@pytest.fixture
def mock_sink():
    return MockSink()


def test_interruption_arbitrator_classification():
    # False interrupts -> RESUME
    assert InterruptionArbitrator.classify("") == InterruptionDecision.RESUME
    assert InterruptionArbitrator.classify("   ") == InterruptionDecision.RESUME
    assert InterruptionArbitrator.classify("[cough]") == InterruptionDecision.RESUME
    assert InterruptionArbitrator.classify("...") == InterruptionDecision.RESUME
    assert InterruptionArbitrator.classify("yeah") == InterruptionDecision.RESUME
    assert InterruptionArbitrator.classify("uh-huh") == InterruptionDecision.RESUME
    assert InterruptionArbitrator.classify("mhm") == InterruptionDecision.RESUME
    assert InterruptionArbitrator.classify("ok") == InterruptionDecision.RESUME
    assert InterruptionArbitrator.classify("okay") == InterruptionDecision.RESUME
    assert InterruptionArbitrator.classify("yeah okay") == InterruptionDecision.RESUME
    assert InterruptionArbitrator.classify("right") == InterruptionDecision.RESUME
    assert InterruptionArbitrator.classify("continue") == InterruptionDecision.RESUME
    assert InterruptionArbitrator.classify("please go on") == InterruptionDecision.RESUME

    # Holds -> HOLD
    assert InterruptionArbitrator.classify("wait") == InterruptionDecision.HOLD
    assert InterruptionArbitrator.classify("hold on") == InterruptionDecision.HOLD
    assert InterruptionArbitrator.classify("give me a second") == InterruptionDecision.HOLD

    # Valid interrupts -> CUT_AND_RESPOND
    assert InterruptionArbitrator.classify("Wait, what is the price?") == InterruptionDecision.CUT_AND_RESPOND
    assert InterruptionArbitrator.classify("How many invoices do we have?") == InterruptionDecision.CUT_AND_RESPOND
    assert InterruptionArbitrator.classify("No, that is incorrect.") == InterruptionDecision.CUT_AND_RESPOND
    assert InterruptionArbitrator.classify("Can you check the Q3 report instead?") == InterruptionDecision.CUT_AND_RESPOND
    assert InterruptionArbitrator.classify("stop") == InterruptionDecision.CUT_AND_RESPOND


@pytest.mark.anyio
async def test_false_interrupt_backchannel_resumes_paused_agent(mock_sink):
    sentences = [
        "First point about enterprise revenue.",
        "Second point regarding invoice processing.",
        "Third point concerning Q3 growth.",
    ]
    llm = SimpleScriptedLLM(sentences)
    session = AgentSession("test-s1", llm, mock_sink, window=5)

    # User initiates dialogue
    await session.handle_user_text("Give me the status report")
    await session.wait_generation()

    # Client receives chunks, acks the first chunk
    assert len(mock_sink.sent) > 0
    first_chunk = mock_sink.sent[0]
    await session.on_chunk_ack(first_chunk["response_id"], first_chunk["generation_id"], 0)

    # User starts speaking (e.g. coughs or makes a sound) -> tentative pause
    assert await session.pause("user_speech")
    assert session.checkpoint.status == ResponseStatus.PAUSED
    assert session.is_paused

    # User input is transcribed as a backchannel: "uh-huh"
    await session.handle_user_text("uh-huh")

    # Session detects FALSE INTERRUPT and automatically resumes!
    assert not session.is_paused
    assert session.checkpoint.status in (ResponseStatus.SPEAKING, ResponseStatus.COMPLETED)
    assert any(e.get("type") == "resumed" and e.get("reason") == "false_interrupt" for e in mock_sink.events)

    # Conversation history did NOT record "uh-huh" as a user query
    user_turns = [t for t in session.conversation.turns if t.role == "user"]
    assert len(user_turns) == 1
    assert user_turns[0].text == "Give me the status report"


@pytest.mark.anyio
async def test_valid_interrupt_cuts_off_old_and_answers_new_question(mock_sink):
    sentences = [
        "First point about enterprise revenue.",
        "Second point regarding invoice processing.",
        "Third point concerning Q3 growth.",
    ]
    llm = SimpleScriptedLLM(sentences)
    session = AgentSession("test-s2", llm, mock_sink, window=5)

    await session.handle_user_text("Tell me about sales")
    await session.wait_generation()

    # User heard chunk 0
    first_chunk = mock_sink.sent[0]
    await session.on_chunk_ack(first_chunk["response_id"], first_chunk["generation_id"], 0)

    # User interrupts with a real question
    await session.handle_user_text("Wait, how much tax did we pay?")
    await session.wait_generation()

    # Previous response was cut off and marked interrupted in history with only chunk 0
    first_assistant_turn = session.conversation.turns[1]
    assert first_assistant_turn.interrupted
    assert sentences[0] in first_assistant_turn.text
    assert sentences[1] not in first_assistant_turn.text

    # New user turn was registered and responded to
    new_user_turn = session.conversation.turns[2]
    assert new_user_turn.text == "Wait, how much tax did we pay?"
    assert any(e.get("type") == "interrupted" for e in mock_sink.events)


@pytest.mark.anyio
async def test_hold_command_keeps_session_paused(mock_sink):
    sentences = ["Point one.", "Point two."]
    llm = SimpleScriptedLLM(sentences)
    session = AgentSession("test-s3", llm, mock_sink, window=5)

    await session.handle_user_text("Start speaking")
    await session.wait_generation()

    # User says "hold on"
    await session.handle_user_text("hold on")
    assert session.checkpoint.status == ResponseStatus.PAUSED
    assert session.is_paused
    assert any(e.get("type") == "holding" for e in mock_sink.events)


def test_registry_has_nanvi_enterprise_provider():
    assert "nanvi" in registry.names("llm")
    assert "mock" in registry.names("llm")
    provider = registry.create("llm", "nanvi")
    assert provider.name == "nanvi"
    assert provider.capabilities.streaming is True


def test_live_voice_demo_endpoint():
    client = TestClient(app)
    resp = client.get("/api/voice/live/demo")
    assert resp.status_code == 200
    assert "Voice agent" in resp.text
    assert "speechSynthesis" in resp.text


def test_live_voice_websocket_roundtrip():
    client = TestClient(app)
    with client.websocket_connect("/api/voice/live") as ws:
        ready = ws.receive_json()
        assert ready["type"] == "ready"
        assert "providers" in ready

        # Switch to mock provider for fast deterministic testing
        ws.send_json({"type": "set_provider", "name": "mock"})
        prov_event = ws.receive_json()
        assert prov_event["type"] == "provider"

        # Send user text
        ws.send_json({"type": "user_text", "text": "hello"})
        speak_event = ws.receive_json()
        assert speak_event["type"] == "speak"
        assert "text" in speak_event

        # Client detects speech and pauses
        ws.send_json({"type": "pause"})
        stop_event = ws.receive_json()
        assert stop_event["type"] == "stop"
        pause_event = ws.receive_json()
        assert pause_event["type"] == "paused"

        # User said "uh-huh" -> false interrupt
        ws.send_json({"type": "user_text", "text": "uh-huh"})
        resumed_event = ws.receive_json()
        assert resumed_event["type"] == "resumed"
        assert resumed_event["reason"] == "false_interrupt"

