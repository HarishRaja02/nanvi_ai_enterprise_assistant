"""Unified Streaming Event Protocol for Nanvi AI Enterprise Assistant.

Defines the event envelope and lifecycle events shared across SSE, WebSockets,
and Voice pipelines in strict accordance with Section 6.2 of docs/NANVI_SPEC.md.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4
from pydantic import BaseModel, Field


class EventType(str, Enum):
    TASK_STARTED = "task_started"
    STATUS = "status"
    PARTIAL_TRANSCRIPT = "partial_transcript"
    FINAL_TRANSCRIPT = "final_transcript"
    ASSISTANT_TEXT = "assistant_text"
    AUDIO_START = "audio_start"
    AUDIO_CHUNK = "audio_chunk"
    AUDIO_END = "audio_end"
    AUDIO_CANCELLED = "audio_cancelled"
    UI_SPEC = "ui_spec"
    ACTION_SUGGESTIONS = "action_suggestions"
    HIGHLIGHT = "highlight"
    SOURCE_FOUND = "source_found"
    SOURCE_VERIFIED = "source_verified"
    TASK_COMPLETE = "task_complete"
    TASK_ERROR = "task_error"


class DocumentProgress(str, Enum):
    SEARCH_STARTED = "SEARCH_STARTED"
    SEARCHING_FILES = "SEARCHING_FILES"
    MATCHING_DOCUMENTS = "MATCHING_DOCUMENTS"
    RERANKING_RESULTS = "RERANKING_RESULTS"
    VERIFYING_SOURCES = "VERIFYING_SOURCES"
    COMPLETE = "COMPLETE"


class SQLProgress(str, Enum):
    SQL_STARTED = "SQL_STARTED"
    GENERATING_QUERY = "GENERATING_QUERY"
    EXECUTING_QUERY = "EXECUTING_QUERY"
    ANALYZING_RESULT = "ANALYZING_RESULT"
    COMPLETE = "COMPLETE"


class WebProgress(str, Enum):
    WEB_SEARCH_STARTED = "WEB_SEARCH_STARTED"
    FETCHING_RESULTS = "FETCHING_RESULTS"
    ANALYZING_RESULTS = "ANALYZING_RESULTS"
    VERIFYING = "VERIFYING"
    COMPLETE = "COMPLETE"


class EmailProgress(str, Enum):
    EMAIL_SEARCH_STARTED = "EMAIL_SEARCH_STARTED"
    SEARCHING_MAILBOX = "SEARCHING_MAILBOX"
    MATCHING_EMAILS = "MATCHING_EMAILS"
    COMPLETE = "COMPLETE"


class ReportProgress(str, Enum):
    REPORT_STARTED = "REPORT_STARTED"
    COLLECTING_DATA = "COLLECTING_DATA"
    ANALYZING = "ANALYZING"
    GENERATING_REPORT = "GENERATING_REPORT"
    COMPLETE = "COMPLETE"


class EventEnvelope(BaseModel):
    event: EventType
    task_id: str = Field(default_factory=lambda: uuid4().hex)
    request_id: str = Field(default_factory=lambda: uuid4().hex)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    payload: dict[str, Any] = Field(default_factory=dict)

    def to_sse(self) -> str:
        """Format envelope as a Server-Sent Event frame."""
        data_str = json.dumps(self.model_dump())
        return f"event: {self.event.value}\ndata: {data_str}\n\n"


def make_event(
    event: EventType | str,
    payload: dict[str, Any] | None = None,
    task_id: str | None = None,
    request_id: str | None = None,
) -> EventEnvelope:
    """Helper to instantiate an event envelope."""
    evt_enum = EventType(event) if isinstance(event, str) else event
    return EventEnvelope(
        event=evt_enum,
        task_id=task_id or uuid4().hex,
        request_id=request_id or uuid4().hex,
        payload=payload or {},
    )


def format_sse(
    event: EventType | str,
    payload: dict[str, Any] | None = None,
    task_id: str | None = None,
    request_id: str | None = None,
) -> str:
    """Convenience function returning formatted SSE string."""
    envelope = make_event(event, payload, task_id, request_id)
    return envelope.to_sse()
