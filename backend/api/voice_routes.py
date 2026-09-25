from __future__ import annotations

import logging
import re
import time
from dataclasses import asdict
from typing import Sequence

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from backend.api.chat_routes import current_attributes, get_chat_service
from backend.chat.models import ChatRequest
from backend.chat.service import ChatService
from backend.core.config import settings
from backend.observability.logging import log_event
from backend.security.authorization import UserAttributes

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voice", tags=["voice"])


class VoiceChatBody(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = Field(default=None, min_length=1, max_length=128)
    rag_enabled: bool = Field(default=True)


class TranscribeResponse(BaseModel):
    text: str
    confidence: float = 1.0


def clean_spoken_text(text: str) -> str:
    """Format an enterprise assistant answer into natural, fluent humanized spoken text.

    Completely strips all asterisks (*), markdown formatting, hashes (#), code blocks,
    raw URLs, citation tags, emojis, and bullet markers, producing warm, natural,
    conversational speech suitable for humanized voice synthesis.
    """
    if not text or not text.strip():
        return "I have completed your request."

    cleaned = text.strip()

    # 1. Remove markdown code blocks
    cleaned = re.sub(r"```[\s\S]*?```", " Code details are available in your conversation record. ", cleaned)
    cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)

    # 2. Remove markdown tables (| col | col | ...) and summarize
    if "|" in cleaned:
        cleaned = re.sub(r"(\|.*\|\n?)+", " Detailed figures are recorded in your context panel. ", cleaned)

    # 3. Remove citation brackets like [1], [ref-1], [Source 2], etc.
    cleaned = re.sub(r"\[(?:ref|source|\d+|file|doc)[^\]]*\]", "", cleaned, flags=re.IGNORECASE)
    # Convert markdown links [title](url) to title
    cleaned = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", cleaned)
    # Remove raw URLs
    cleaned = re.sub(r"https?://\S+", "", cleaned)

    # 4. Remove headers (###, ##, #)
    cleaned = re.sub(r"^#{1,6}\s*", "", cleaned, flags=re.MULTILINE)

    # 5. Currency & Numbers spoken expansions for natural human delivery
    # $4.2M -> 4.2 million dollars, $100K -> 100 thousand dollars, $5B -> 5 billion dollars
    cleaned = re.sub(
        r"\$(\d+(?:\.\d+)?)\s*([BMKbmk])\b",
        lambda m: m.group(1) + {"b": " billion", "m": " million", "k": " thousand"}[m.group(2).lower()] + " dollars",
        cleaned,
    )
    cleaned = re.sub(r"\$(\d+(?:\.\d+)?)", r"\1 dollars", cleaned)

    # 6. Conversational expansions
    cleaned = re.sub(r"\be\.g\b\.?,?\s*", "for example, ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bi\.e\b\.?,?\s*", "that is, ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\betc\b\.?", "and so forth", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bvs\b\.?\s*", "versus ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bQ([1-4])\b", r"Quarter \1", cleaned)
    cleaned = re.sub(r"&", " and ", cleaned)

    # 7. CRITICAL: Completely strip ALL asterisks (*), hashes (#), underscores (_), tildes (~), backticks, pipes (|), angle brackets (< >)
    cleaned = re.sub(r"[\*\#\_~\|<>{}\^\\\/]", "", cleaned)

    # 8. Remove bullet points (- item, * item, 1. item, • item)
    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    processed_lines: list[str] = []
    for line in lines:
        l = re.sub(r"^[\-\•\◦\▪\▫\+]\s*", "", line)
        l = re.sub(r"^\d+[\.\)]\s*", "", l)
        processed_lines.append(l)

    text_body = " ".join(processed_lines)

    # 9. Strip any remaining symbols and emojis
    text_body = re.sub(r"[\*\#\_~\|]", "", text_body)
    # Strip emojis
    text_body = re.sub(r"[\U00010000-\U0010ffff]", "", text_body)
    # Clean redundant whitespaces
    text_body = re.sub(r"\s+", " ", text_body).strip()

    # 10. Natural human pacing: limit spoken response to top 3-4 natural conversational sentences
    sentences = re.split(r"(?<=[.!?])\s+", text_body)
    if len(sentences) > 4:
        spoken = " ".join(sentences[:3])
        if not spoken.endswith((".", "!", "?")):
            spoken += "."
        spoken += " Further specific details are provided in your Voice Context panel."
        return spoken

    return text_body


def extract_important_points(answer: str, sources: Sequence[object]) -> list[str]:
    """Extract key enterprise takeaways from the answer and retrieved sources for the Voice Context panel."""
    points: list[str] = []

    # Look for bullet points or numbered lists in answer first
    raw_lines = [l.strip() for l in answer.splitlines() if l.strip()]
    for line in raw_lines:
        m = re.match(r"^[\*\-•\d+\.]\s+(.*)$", line)
        if m:
            clean_point = re.sub(r"[\*\#\_~\|`]", "", m.group(1)).strip()
            # Remove link syntax
            clean_point = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", clean_point)
            clean_point = re.sub(r"\[(?:ref|source|\d+|file)[^\]]*\]", "", clean_point, flags=re.IGNORECASE).strip()
            if len(clean_point) > 10 and not clean_point.startswith("|"):
                points.append(clean_point)
                if len(points) >= 4:
                    break

    # If no bullet points found, extract declarative sentences
    if not points:
        sentences = re.split(r"(?<=[.!?])\s+", answer)
        for s in sentences:
            cleaned_s = re.sub(r"[\#\*_`~\|]", "", s).strip()
            cleaned_s = re.sub(r"\[(?:ref|source|\d+|file)[^\]]*\]", "", cleaned_s, flags=re.IGNORECASE).strip()
            if 15 < len(cleaned_s) < 140 and not cleaned_s.startswith("|"):
                points.append(cleaned_s)
                if len(points) >= 4:
                    break

    # Ensure points have neat punctuation and zero symbols
    final_points: list[str] = []
    for p in points:
        p = re.sub(r"[\*\#\_~\|`]", "", p).strip()
        if not p.endswith((".", "!", "?")):
            p += "."
        final_points.append(p)

    return final_points[:4]


@router.post("/respond")
def voice_respond(
    body: VoiceChatBody,
    user: UserAttributes = Depends(current_attributes),
    service: ChatService = Depends(get_chat_service),
):
    """Execute enterprise voice query through the exact same LangGraph agent orchestration,

    RBAC, and source retrieval layer as standard chat, returning both the structured
    answer, speech-optimized conversational text, and Voice Context panel highlights.
    """
    started = time.perf_counter()
    log_event(
        logger,
        "voice_query_started",
        actor_id=user.user_id,
        tenant_id=user.tenant_id,
        query_length=len(body.query),
        has_conversation=bool(body.conversation_id),
    )

    try:
        response = service.ask(user, ChatRequest(body.query, body.conversation_id, body.rag_enabled))
    except PermissionError:
        log_event(logger, "voice_query_failed", logging.WARNING, actor_id=user.user_id, outcome="not_found")
        raise HTTPException(status_code=404, detail="Conversation not found")
    except ValueError as exc:
        log_event(logger, "voice_query_failed", logging.WARNING, actor_id=user.user_id, outcome="validation_error")
        raise HTTPException(status_code=422, detail=str(exc))
    except RuntimeError as exc:
        log_event(logger, "voice_query_failed", logging.ERROR, actor_id=user.user_id, outcome="orchestration_error")
        raise HTTPException(status_code=502, detail="AI voice orchestration failed")

    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    log_event(
        logger,
        "voice_query_completed",
        actor_id=user.user_id,
        tenant_id=user.tenant_id,
        source_count=len(response.sources),
        duration_ms=duration_ms,
    )

    # Auto-register sources into the source store for verified permission re-checking
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
        logger.warning("Could not auto-register voice sources: %s", exc)

    spoken = clean_spoken_text(response.answer)
    important_points = extract_important_points(response.answer, response.sources)

    return {
        "conversation_id": response.conversation_id,
        "answer": response.answer,
        "spoken_text": spoken,
        "important_points": important_points,
        "capability": response.capability,
        "sources": [s.to_frontend_dict() for s in response.sources],
        "trace": list(response.trace),
        "history": [asdict(m) for m in response.history],
        "report_id": getattr(response, "report_id", None),
    }


import base64

class TranscribeBody(BaseModel):
    audio_base64: str = Field(min_length=1)
    mime_type: str = Field(default="audio/webm")
    filename: str = Field(default="recording.webm")


@router.post("/transcribe")
async def voice_transcribe(
    body: TranscribeBody,
    user: UserAttributes = Depends(current_attributes),
):
    """Transcribe captured voice audio using high-speed Whisper speech-to-text.

    Provides server-side audio transcription fallback whenever browser SpeechRecognition
    is unavailable or when higher accuracy is requested.
    """
    if not settings.groq_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Speech-to-text service is not configured (GROQ_API_KEY required).",
        )

    try:
        content = base64.b64decode(body.audio_base64)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 audio data.")

    if not content:
        raise HTTPException(status_code=400, detail="Empty audio content provided.")

    files = {"file": (body.filename, content, body.mime_type)}
    data = {"model": "whisper-large-v3", "response_format": "json"}
    headers = {"Authorization": f"Bearer {settings.groq_api_key}"}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                files=files,
                data=data,
                headers=headers,
            )
            if resp.status_code != 200:
                logger.error("Groq Whisper transcription failed: %s %s", resp.status_code, resp.text)
                raise HTTPException(status_code=502, detail="Audio transcription failed.")
            res_data = resp.json()
            return {"text": res_data.get("text", "").strip(), "confidence": 1.0}
    except httpx.RequestError as exc:
        logger.error("Groq Whisper connection error: %s", exc)
        raise HTTPException(status_code=503, detail="Audio transcription service unreachable.")


class SynthesizeBody(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    profile_id: str = Field(default="nanvi-warm")


# Ultra-realistic Azure Neural conversational voices matching voice profiles
# These voices have natural human breathing, subtle vocal inflections, and conversational cadence
PROFILE_TO_EDGE_VOICE = {
    "nanvi-warm": "en-US-AvaNeural",       # Ultra-realistic conversational human voice (warm, expressive, natural breathing)
    "nanvi-pro": "en-US-JennyNeural",     # Natural, articulate, warm executive conversationalist
    "nanvi-clear": "en-US-EmmaNeural",     # Crisp, pleasant, expressive clarity
    "nanvi-concise": "en-US-AndrewNeural", # Warm, friendly, grounded conversational male
}


@router.post("/synthesize")
async def voice_synthesize(
    body: SynthesizeBody,
    user: UserAttributes = Depends(current_attributes),
):
    """Synthesize photorealistic human neural voice using Microsoft Edge Neural TTS.

    Generates natural human speech with realistic breathing, pitch inflections,
    and conversational cadence that feels like speaking directly to a real person.
    """
    if not body.text or not body.text.strip():
        raise HTTPException(status_code=400, detail="Empty text provided for synthesis.")

    clean = clean_spoken_text(body.text)
    if not clean.strip():
        raise HTTPException(status_code=400, detail="Empty text provided for synthesis.")

    voice = PROFILE_TO_EDGE_VOICE.get(body.profile_id, "en-US-JennyNeural")

    try:
        import edge_tts

        communicate = edge_tts.Communicate(clean, voice)
        audio_data = bytearray()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data.extend(chunk["data"])

        if not audio_data:
            raise HTTPException(status_code=502, detail="No audio data generated by neural synthesizer.")

        return Response(content=bytes(audio_data), media_type="audio/mpeg")
    except Exception as exc:
        logger.error("Neural voice synthesis failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"Neural voice synthesis failed: {exc}")
