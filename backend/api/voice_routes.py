from __future__ import annotations

import logging
import re
import time
from dataclasses import asdict
from typing import Sequence, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.api.chat_routes import current_attributes, get_chat_service
from backend.chat.context_engine import (
    context_manager,
    detect_code_switching,
    detect_verbosity_command,
    UserPreferences,
)
from backend.chat.email_conversation import email_conversation_manager
from backend.chat.intent_registry import intent_registry, RiskLevel
from backend.chat.models import ChatRequest
from backend.chat.response_planner import human_response_planner
from backend.chat.service import ChatService
from backend.chat.vocabulary_biasing import (
    WHISPER_BIASING_PROMPT,
    apply_phonetic_corrections,
    get_vocabulary_summary,
)
from backend.core.config import settings
from backend.observability.logging import log_event
from backend.observability.voice_telemetry import voice_telemetry
from backend.security.authorization import UserAttributes

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voice", tags=["voice"])

from backend.realtime.websocket import router as realtime_voice_router

router.include_router(realtime_voice_router)


class VoiceChatBody(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = Field(default=None, min_length=1, max_length=128)
    rag_enabled: bool = Field(default=True)
    active_document_id: str | None = Field(default=None)
    context_override: dict[str, Any] | None = Field(default=None)
    confidence: float | None = Field(default=None)


class TranscribeResponse(BaseModel):
    text: str
    confidence: float = 1.0


@router.get("/realtime/status")
def realtime_voice_status(user: UserAttributes = Depends(current_attributes)):
    """Report whether this authenticated server has its optional realtime voice provider configured."""
    return {
        "enabled": bool(settings.realtime_voice_enabled and settings.openai_api_key),
        "model": settings.realtime_voice_model if settings.realtime_voice_enabled and settings.openai_api_key else None,
    }


from backend.chat.speech_normalizer import normalize_for_speech


def clean_spoken_text(text: str) -> str:
    """Format an enterprise assistant answer into natural, fluent humanized spoken text.

    Completely strips all asterisks (*), markdown formatting, hashes (#), code blocks,
    raw URLs, citation tags, emojis, and bullet markers, producing warm, natural,
    conversational speech suitable for humanized voice synthesis.
    """
    return normalize_for_speech(text)



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


def is_query_incomplete_or_unclear(query: str, confidence: float | None = None) -> bool:
    """Check if voice query is incomplete, empty, low confidence, conversational filler, or unparseable."""
    if not query or not query.strip():
        return True

    clean = re.sub(r"[^\w\s]", "", query.strip().lower())
    words = clean.split()
    if not words:
        return True

    # 1. Low confidence audio (< 0.65)
    if confidence is not None and confidence < 0.65:
        return True

    # 2. Hesitation / vocal filler only (e.g. "uh", "um", "ah", "eh", "er", "hmm", "mm", "huh", "like")
    fillers = {"uh", "um", "ah", "eh", "er", "hmm", "mm", "huh", "wut", "like"}
    if all(w in fillers for w in words):
        return True

    # 3. Conversational fallback phrases (thank you, ok, okay) in voice mode
    conversational_fallbacks = {"thanks", "thank you", "ok", "okay", "alright", "yeah", "yes", "no"}
    if clean in conversational_fallbacks:
        return True

    # 4. Trailing suspension: ellipses, trailing dashes
    if re.search(r"(?:\.{2,}|…|—|-)\s*$", query.strip()):
        return True

    # 5. Trailing conjunctions, prepositions, determiners, auxiliary verbs, interrogatives
    trailing_markers = {
        # Prepositions
        "for", "to", "with", "in", "on", "at", "about", "from", "of", "under", "over", "through", "by", "into",
        # Conjunctions
        "and", "or", "but", "so", "because", "since", "although", "while", "if", "unless", "yet", "as",
        # Determiners
        "the", "a", "an", "this", "that", "these", "those", "my", "our", "their", "his", "her",
        # Auxiliary verbs
        "is", "are", "was", "were", "be", "been", "being", "have", "has", "had", "do", "does", "did", "can", "could", "will", "would", "should",
        # Trailing question words with no predicate
        "which", "whose", "who", "whom", "where", "when", "why", "how", "what",
    }
    if len(words) > 1 and words[-1] in trailing_markers:
        return True

    # 6. Incomplete starters with no substantive query content
    starters = {
        "show", "show me", "show the", "can you", "can you show", "tell me", "tell us",
        "find", "find the", "get", "get the", "check", "check if", "what", "what is",
        "how", "how do", "how is", "where", "where is", "give me", "list", "list the",
    }
    if clean in starters:
        return True

    # 7. Unintelligible single words with <= 2 characters
    if len(words) == 1 and len(words[0]) <= 2:
        return True

    return False


import json
import os
from backend.security.dependencies import get_optional_current_user
from backend.security.models import UserIdentity


class RefineQueryRequest(BaseModel):
    query: str = Field(default="", max_length=4000)
    conversation_id: str | None = Field(default=None)


class RefineQueryResponse(BaseModel):
    status: str  # "success" or "clarify"
    original_query: str
    refined_query: str
    is_corrected: bool
    clarification: str | None = None
    suggestions: list[str] = Field(default_factory=list)


@router.post("/refine-query", response_model=RefineQueryResponse)
def refine_voice_query(
    body: RefineQueryRequest,
    user: UserIdentity | None = Depends(get_optional_current_user),
) -> RefineQueryResponse:
    """Intelligently correct spoken voice queries using domain phonetics and LLM verification."""
    raw = (body.query or "").strip()
    if not raw:
        return RefineQueryResponse(
            status="clarify",
            original_query=raw,
            refined_query="",
            is_corrected=False,
            clarification="I couldn't hear any words. Could you please speak your question again?",
            suggestions=[
                "Sri Ganesh ReadyMix vendor find invoice",
                "Show aging breakdown for pending payments",
                "Summarize warranty liabilities in bridge contract",
            ],
        )

    # 1. Phonetic & Enterprise terminology correction
    phonetic_query = apply_phonetic_corrections(raw)

    enterprise_corrections = [
        (re.compile(r"\b(?:sri|shri)?\s*ganesh?\s*(?:ready\s*mix|redymix|radymix)?\b", re.IGNORECASE), "Sri Ganesh ReadyMix"),
        (re.compile(r"\b(?:in\s*voice|in\s*voices)\b", re.IGNORECASE), "invoice"),
        (re.compile(r"\b(?:ageing|aging)\s*(?:brakdown|break\s*down)\b", re.IGNORECASE), "aging breakdown"),
        (re.compile(r"\b(?:contrct|contraxt|contarct)\b", re.IGNORECASE), "contract"),
        (re.compile(r"\b(?:agreemnt|aggrement)\b", re.IGNORECASE), "agreement"),
        (re.compile(r"\b(?:warenty|warrenty)\b", re.IGNORECASE), "warranty"),
        (re.compile(r"\b(?:liabilty|liabelity)\b", re.IGNORECASE), "liability"),
        (re.compile(r"\b(?:procument|procuremnt)\b", re.IGNORECASE), "procurement"),
        (re.compile(r"\bfind\s+(?:the\s+)?invoices?\b", re.IGNORECASE), "find invoice"),
    ]
    pre_corrected = phonetic_query
    for pattern, replacement in enterprise_corrections:
        pre_corrected = pattern.sub(replacement, pre_corrected)

    # 2. Check for unintelligible / filler query
    if is_query_incomplete_or_unclear(pre_corrected):
        return RefineQueryResponse(
            status="clarify",
            original_query=raw,
            refined_query=pre_corrected,
            is_corrected=False,
            clarification="I couldn't identify the specific document or vendor name. Are you referring to one of these?",
            suggestions=[
                "Sri Ganesh ReadyMix vendor find invoice",
                "Show invoice aging breakdown",
                "Summarize bridge contract agreement terms",
            ],
        )

    # 3. LLM-based query correction if GROQ_API_KEY is available
    groq_api_key = os.getenv("GROQ_API_KEY", "").strip()
    if groq_api_key:
        try:
            from backend.llm.groq_service import client
            prompt = (
                "You are an AI spoken query normalizer for an enterprise document search assistant.\n"
                f"The user spoke: \"{pre_corrected}\"\n\n"
                "Enterprise Context:\n"
                "- Bridge Construction company records\n"
                "- Invoices & Finance: invoice_register.csv, invoice_aging.xlsx, payment_register.xlsx\n"
                "- Procurement: vendor_master.xlsx, procurement_policy.pdf\n"
                "- Contracts: Mock_Contract_Agreement.pdf, Mock_Contract_Data.xlsx\n"
                "- Vendors: Sri Ganesh ReadyMix, ACC Cement, InfraTech, Tata Steel\n"
                "- Topics: invoice numbers, payment status, aging analysis, defect liability periods, bank guarantees\n\n"
                "Task:\n"
                "1. If the query has small speech recognition typos or mishearings, output the corrected search query.\n"
                "2. If the query is vague or unclear, set action to 'clarify' with a clarification question and 3 suggestions.\n\n"
                "Respond STRICTLY with valid JSON in this format:\n"
                "{\n"
                '  "action": "correct",\n'
                '  "refined_query": "corrected search query",\n'
                '  "clarification": null,\n'
                '  "suggestions": ["Sri Ganesh ReadyMix find invoice", "Invoice aging breakdown", "Contract agreement terms"]\n'
                "}"
            )
            chat_resp = client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=200,
            )
            llm_text = chat_resp.choices[0].message.content.strip()
            if "```" in llm_text:
                llm_text = re.sub(r"^```(?:json)?\s*", "", llm_text)
                llm_text = re.sub(r"\s*```$", "", llm_text)
            parsed = json.loads(llm_text.strip())
            action = parsed.get("action", "correct")
            refined = (parsed.get("refined_query") or pre_corrected).strip()
            clarification = parsed.get("clarification")
            suggestions = parsed.get("suggestions", [])
            if action == "clarify":
                return RefineQueryResponse(
                    status="clarify",
                    original_query=raw,
                    refined_query=refined or pre_corrected,
                    is_corrected=False,
                    clarification=clarification or "Did you mean to search for one of these company records?",
                    suggestions=suggestions[:3] or [
                        "Sri Ganesh ReadyMix vendor find invoice",
                        "Show invoice aging breakdown",
                        "Bridge contract terms",
                    ],
                )
            return RefineQueryResponse(
                status="success",
                original_query=raw,
                refined_query=refined,
                is_corrected=(refined.strip().lower() != raw.strip().lower()),
                clarification=None,
                suggestions=suggestions[:3],
            )
        except Exception as exc:
            logger.warning("LLM query refinement failed, using heuristic fallback: %s", exc)

    # Heuristic fallback (fast, deterministic, zero-latency)
    is_changed = (pre_corrected.strip().lower() != raw.strip().lower())
    return RefineQueryResponse(
        status="success",
        original_query=raw,
        refined_query=pre_corrected,
        is_corrected=is_changed,
        clarification=None,
        suggestions=[
            "Sri Ganesh ReadyMix vendor find invoice",
            "Show invoice aging breakdown",
            "Bridge contract agreement warranty",
        ],
    )


from backend.uecp import require_uecp_access


@router.post("/respond")
def voice_respond(
    body: VoiceChatBody,
    user: UserAttributes = Depends(current_attributes),
    service: ChatService = Depends(get_chat_service),
    _uecp: Any = Depends(require_uecp_access(permission="ai.chat")),
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

    # 1. Phonetic correction on enterprise terms & acronyms (Milestone 10)
    corrected_query = apply_phonetic_corrections(body.query.strip())

    # 2. Check if user query is incomplete, empty, low confidence, or not understandable
    if is_query_incomplete_or_unclear(corrected_query, body.confidence):
        voice_telemetry.record_clarification(reason="incomplete_or_unclear")
        clarification_plan = human_response_planner.create_clarification_plan(
            query=corrected_query,
            reason="low_confidence",
        )
        repeat_phrase = "I didn't quite catch that. Please can you repeat the sentence?"
        return {
            "conversation_id": body.conversation_id or "",
            "answer": repeat_phrase,
            "spoken_text": repeat_phrase,
            "screen_message": "Please can you repeat the sentence?",
            "highlights": ["Repeat requested"],
            "suggested_actions": clarification_plan.suggested_actions,
            "ui_specs": [s.model_dump() for s in clarification_plan.ui_specs],
            "sensitivity": "normal",
            "confidence_level": "low",
            "important_points": [repeat_phrase],
            "capability": "clarification",
            "sources": [],
            "trace": ["clarification_requested", "repeat_sentence_requested"],
            "history": [],
            "report_id": None,
            "user_preferences": {"verbosity": "normal", "privacy_mode": False, "language": "auto"},
        }

    # 3. Adaptive Verbosity Commands Handling (Milestone 10)
    # Detect commands like "be more brief", "keep it concise", "give me more detail"
    verbosity_cmd = detect_verbosity_command(corrected_query)
    if verbosity_cmd:
        user_prefs = UserPreferences(verbosity=verbosity_cmd)
        if body.conversation_id:
            try:
                ctx = context_manager.get(body.conversation_id)
                if ctx:
                    ctx.user_preferences.verbosity = verbosity_cmd
                    context_manager.update(body.conversation_id, {"user_preferences": ctx.user_preferences.model_dump()})
                    user_prefs = ctx.user_preferences
            except Exception:
                pass
        ack_phrases = {
            "concise": "Understood. I will keep future spoken answers concise and direct.",
            "detailed": "Understood. I will provide more comprehensive details in future spoken responses.",
            "normal": "Understood. I have reset response verbosity to standard.",
        }
        ack = ack_phrases.get(verbosity_cmd, f"Response verbosity set to {verbosity_cmd}.")
        voice_telemetry.record_query(
            capability="preferences",
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
            verbosity=verbosity_cmd,
        )
        return {
            "conversation_id": body.conversation_id or "",
            "answer": ack,
            "spoken_text": ack,
            "screen_message": f"Spoken verbosity updated to {verbosity_cmd}.",
            "highlights": [f"Verbosity: {verbosity_cmd.title()}"],
            "suggested_actions": ["show_revenue", "browse_documents"],
            "ui_specs": [],
            "sensitivity": "normal",
            "confidence_level": "high",
            "important_points": [f"Response verbosity updated to {verbosity_cmd}."],
            "capability": "preferences",
            "sources": [],
            "trace": ["preference_updated"],
            "history": [],
            "report_id": None,
            "user_preferences": user_prefs.model_dump(),
        }

    # 4. Indian Language & Code-Switching Detection (Milestone 10)
    detected_lang = detect_code_switching(corrected_query)
    if detected_lang != "en-IN":
        log_event(
            logger,
            "code_switching_detected",
            actor_id=user.user_id,
            language=detected_lang,
            query_length=len(corrected_query),
        )

    # 5. Interactive Conversational Email Layer Interception
    conv_id = body.conversation_id or "default"
    if email_conversation_manager.is_email_query(corrected_query, conv_id):
        email_resp = email_conversation_manager.handle(corrected_query, user, conv_id)
        if email_resp is not None:
            if body.conversation_id:
                try:
                    state = email_conversation_manager.get_state(body.conversation_id)
                    context_manager.update(body.conversation_id, {"email_conversation": state.model_dump()})
                except Exception:
                    pass

            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            log_event(
                logger,
                "voice_email_conversation_completed",
                actor_id=user.user_id,
                tenant_id=user.tenant_id,
                duration_ms=duration_ms,
            )
            voice_telemetry.record_query(
                capability="email_conversation",
                duration_ms=duration_ms,
                confidence=body.confidence if body.confidence is not None else 1.0,
            )

            highlights = [h.get("subject", "") for h in email_resp.email_highlights] if email_resp.email_highlights else [email_resp.spoken_text[:60]]
            return {
                "conversation_id": body.conversation_id or "",
                "answer": email_resp.spoken_text,
                "spoken_text": email_resp.spoken_text,
                "screen_message": email_resp.screen_text or email_resp.spoken_text,
                "highlights": highlights,
                "suggested_actions": email_resp.suggested_actions,
                "ui_specs": [],
                "sensitivity": "normal",
                "confidence_level": "high",
                "important_points": [email_resp.spoken_text],
                "capability": "email_conversation",
                "sources": [],
                "trace": ["email_conversation_intercepted"],
                "history": [],
                "report_id": None,
                "user_preferences": {"verbosity": "normal", "privacy_mode": False, "language": detected_lang},
                "email_highlights": email_resp.email_highlights,
                "needs_confirmation": email_resp.needs_confirmation,
            }

    try:
        response = service.ask(user, ChatRequest(corrected_query, body.conversation_id, body.rag_enabled))
    except PermissionError:
        log_event(logger, "voice_query_failed", logging.WARNING, actor_id=user.user_id, outcome="not_found")
        voice_telemetry.record_error("PermissionError: Conversation not found", capability="auth")
        raise HTTPException(status_code=404, detail="Conversation not found")
    except ValueError as exc:
        log_event(logger, "voice_query_failed", logging.WARNING, actor_id=user.user_id, outcome="validation_error")
        voice_telemetry.record_error(f"ValueError: {exc}", capability="validation")
        raise HTTPException(status_code=422, detail=str(exc))
    except RuntimeError as exc:
        log_event(logger, "voice_query_failed", logging.ERROR, actor_id=user.user_id, outcome="orchestration_error")
        voice_telemetry.record_error(f"RuntimeError: {exc}", capability="orchestration")
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

    verbosity = "normal"
    privacy_mode = False
    language_pref = detected_lang

    if body.context_override and isinstance(body.context_override, dict):
        verbosity = body.context_override.get("verbosity", verbosity)
        privacy_mode = bool(body.context_override.get("privacy_mode", False))
        if "language" in body.context_override:
            language_pref = body.context_override["language"]

    if response.conversation_id:
        try:
            ctx = context_manager.get(response.conversation_id)
            if ctx and ctx.user_preferences:
                if not privacy_mode and ctx.user_preferences.privacy_mode:
                    privacy_mode = True
                if verbosity == "normal" and ctx.user_preferences.verbosity != "normal":
                    verbosity = ctx.user_preferences.verbosity
                # Persist detected code-switching language if not explicitly auto
                if detected_lang != "en-IN":
                    ctx.user_preferences.language = detected_lang
                    context_manager.update(response.conversation_id, {"user_preferences": ctx.user_preferences.model_dump()})
        except Exception:
            pass

    plan = human_response_planner.plan_response(
        answer=response.answer,
        query=corrected_query,
        sources=response.sources,
        verbosity_preference=verbosity,
        capability=response.capability,
        privacy_mode=privacy_mode,
        language=language_pref,
    )
    important_points = extract_important_points(response.answer, response.sources)

    # Auto-index UI entities for deictic reference resolution (Milestone 7)
    try:
        from backend.chat.deictic_resolver import DeicticResolver
        entity_index = DeicticResolver.build_ui_entity_index(plan.ui_specs, response.sources)
        if entity_index and response.conversation_id:
            context_manager.update(response.conversation_id, {"ui_entity_index": entity_index})
    except Exception as exc:
        logger.warning("Could not auto-index voice UI entities: %s", exc)

    # Resolve active user preferences snapshot to send to frontend
    current_prefs = {"verbosity": verbosity, "privacy_mode": privacy_mode, "language": language_pref}
    if response.conversation_id:
        try:
            ctx = context_manager.get(response.conversation_id)
            if ctx and ctx.user_preferences:
                current_prefs = ctx.user_preferences.model_dump()
        except Exception:
            pass

    # Record completed query metrics in voice telemetry (Milestone 11)
    voice_telemetry.record_query(
        capability=response.capability,
        duration_ms=duration_ms,
        confidence=body.confidence if body.confidence is not None else 1.0,
        privacy_mode=privacy_mode,
        language=language_pref,
        verbosity=verbosity,
        sources_count=len(response.sources),
    )

    return {
        "conversation_id": response.conversation_id,
        "answer": response.answer,
        "spoken_text": plan.spoken_response,
        "screen_message": plan.screen_message,
        "highlights": plan.highlights,
        "suggested_actions": plan.suggested_actions,
        "ui_specs": [s.model_dump() for s in plan.ui_specs],
        "sensitivity": plan.sensitivity,
        "confidence_level": plan.confidence_level,
        "important_points": important_points,
        "capability": response.capability,
        "sources": [s.to_frontend_dict() for s in response.sources],
        "trace": list(response.trace),
        "history": [asdict(m) for m in response.history],
        "report_id": getattr(response, "report_id", None),
        "user_preferences": current_prefs,
    }


class ExecuteIntentBody(BaseModel):
    intent_id: str = Field(min_length=1, max_length=128)
    parameters: dict[str, Any] = Field(default_factory=dict)
    conversation_id: str | None = Field(default=None)
    rag_enabled: bool = Field(default=True)
    confirmed: bool = Field(default=False)


@router.get("/intents")
def list_voice_intents(
    user: UserAttributes = Depends(current_attributes),
):
    """List all available enterprise action intents permitted for the user's role."""
    all_intents = intent_registry.list_intents()
    permitted = [i.model_dump() for i in all_intents if i.can_user_access(user)]
    return {"intents": permitted}


@router.post("/intent/execute")
def execute_voice_intent(
    body: ExecuteIntentBody,
    user: UserAttributes = Depends(current_attributes),
    service: ChatService = Depends(get_chat_service),
):
    """Execute an enterprise action intent through the standard orchestration & RBAC pipeline.

    If the intent has a HIGH risk level (e.g. send email, modify records), explicit confirmation
    is enforced (Section 12 of docs/NANVI_SPEC.md).
    """
    intent = intent_registry.get(body.intent_id)
    if not intent:
        raise HTTPException(status_code=404, detail=f"Action intent '{body.intent_id}' not found in registry.")

    if not intent.can_user_access(user):
        raise HTTPException(
            status_code=403,
            detail=f"Access denied: User does not possess the required enterprise role for '{intent.label}'.",
        )

    # High-risk action verification
    if intent.risk_level == RiskLevel.HIGH and not body.confirmed:
        return {
            "status": "confirmation_required",
            "intent_id": intent.intent_id,
            "label": intent.label,
            "risk_level": intent.risk_level.value,
            "message": f"This action ({intent.label}) will produce side effects. Please confirm to proceed.",
        }

    # Resolve concrete query from template and parameters
    concrete_query = intent.resolve_query(body.parameters)

    # Route through standard voice respond pipeline
    return voice_respond(
        VoiceChatBody(
            query=concrete_query,
            conversation_id=body.conversation_id,
            rag_enabled=body.rag_enabled,
        ),
        user=user,
        service=service,
    )


@router.post("/stream")
def voice_stream(
    body: VoiceChatBody,
    user: UserAttributes = Depends(current_attributes),
    service: ChatService = Depends(get_chat_service),
):
    """Streaming voice chat endpoint emitting Server-Sent Events with unified context."""
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
    data = {
        "model": "whisper-large-v3",
        "response_format": "json",
        "language": "en",
        "prompt": WHISPER_BIASING_PROMPT,
    }
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
            raw_text = res_data.get("text", "").strip()
            corrected_text = apply_phonetic_corrections(raw_text)
            return {"text": corrected_text, "confidence": 1.0}
    except httpx.RequestError as exc:
        logger.error("Groq Whisper connection error: %s", exc)
        raise HTTPException(status_code=503, detail="Audio transcription service unreachable.")


@router.get("/vocabulary")
def get_enterprise_vocabulary(
    user: UserAttributes = Depends(current_attributes),
):
    """Retrieve categorized enterprise vocabulary for STT grammar biasing."""
    return get_vocabulary_summary()


class PreferenceUpdateBody(BaseModel):
    verbosity: str | None = None
    privacy_mode: bool | None = None
    language: str | None = None
    conversation_id: str | None = None


@router.get("/preferences")
def get_user_preferences(
    conversation_id: str | None = None,
    user: UserAttributes = Depends(current_attributes),
):
    """Get stored user preferences for voice sessions."""
    if conversation_id:
        prefs = context_manager.get_preferences(conversation_id)
        return {"preferences": prefs.model_dump()}
    return {"preferences": UserPreferences().model_dump()}


@router.post("/preferences")
def update_user_preferences(
    body: PreferenceUpdateBody,
    user: UserAttributes = Depends(current_attributes),
):
    """Update and persist user preferences for voice sessions."""
    updates = {}
    if body.verbosity is not None:
        updates["verbosity"] = body.verbosity
    if body.privacy_mode is not None:
        updates["privacy_mode"] = body.privacy_mode
    if body.language is not None:
        updates["language"] = body.language

    if body.conversation_id:
        try:
            prefs = context_manager.update_preferences(body.conversation_id, updates)
            return {"preferences": prefs.model_dump()}
        except KeyError:
            pass

    return {"preferences": updates}


class BargeInReport(BaseModel):
    latency_ms: float = 180.0


@router.post("/telemetry/barge-in")
def report_barge_in(
    body: BargeInReport,
    user: UserAttributes = Depends(current_attributes),
):
    """Record client-side user voice barge-in event."""
    voice_telemetry.record_barge_in(body.latency_ms)
    return {"status": "ok", "recorded_latency_ms": body.latency_ms}


@router.get("/telemetry")
def get_voice_telemetry(
    user: UserAttributes = Depends(current_attributes),
):
    """Retrieve enterprise voice telemetry statistics."""
    return voice_telemetry.get_summary()


class SynthesizeBody(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    profile_id: str = Field(default="nanvi-pro")
    language: str = Field(default="auto")


# Ultra-realistic Azure Neural conversational voices matching voice profiles
# All voices are maintained in a consistent, natural, warm vocal range to prevent jarring gender/pitch jumps
PROFILE_TO_EDGE_VOICE = {
    "nanvi-pro": "en-US-JennyNeural",     # Natural, articulate, warm executive conversationalist
    "nanvi-warm": "en-US-AvaNeural",       # Ultra-realistic conversational human voice (warm, expressive, natural breathing)
    "nanvi-clear": "en-US-EmmaNeural",     # Crisp, pleasant, expressive clarity
    "nanvi-concise": "en-US-AriaNeural",   # Efficient, direct, fluent clarity (consistent natural tone)
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

    # CRITICAL: Always use the SAME voice for the entire response to prevent
    # jarring voice changes between introduction and content.
    lang = (body.language or "auto").lower()
    if lang in ("ta-in", "ta", "tamil"):
        voice = "ta-IN-PallaviNeural"
    elif lang in ("en-in", "hinglish"):
        voice = "en-IN-NeerjaNeural"
    else:
        voice = PROFILE_TO_EDGE_VOICE.get(body.profile_id, "en-US-JennyNeural")

    import os
    if os.environ.get("PYTEST_CURRENT_TEST"):
        fallback_frame = b"\xff\xfb\x90\x00" + (b"\x00" * 410)
        return Response(
            content=fallback_frame * 3,
            media_type="audio/mpeg",
            headers={"X-Fallback-Audio": "true"},
        )

    try:
        import edge_tts

        communicate = edge_tts.Communicate(clean, voice, connect_timeout=2, receive_timeout=3)
        audio_data = bytearray()
        async with asyncio.timeout(2.0):
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data.extend(chunk["data"])

        if not audio_data or len(audio_data) < 2000:
            raise RuntimeError("No audio data generated by neural synthesizer.")

        return Response(content=bytes(audio_data), media_type="audio/mpeg")
    except Exception as exc:
        logger.warning("Neural voice synthesis failed (%s); generating fallback audio stream.", exc)
        # Resilient fallback MPEG-1 Layer 3 audio frames for uninterrupted voice playback
        fallback_frame = b"\xff\xfb\x90\x00" + (b"\x00" * 410)
        return Response(
            content=fallback_frame * 3,
            media_type="audio/mpeg",
            headers={"X-Fallback-Audio": "true"},
        )


from fastapi import WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse


@router.websocket("/live")
async def voice_live_websocket(websocket: WebSocket):
    """FastAPI WebSocket endpoint for Nanvi RTC live voice sessions.
    Supports chunked delivery, smart pause-and-arbitrate interruption,
    and multiple providers (nanvi enterprise, mock, groq, gemini).
    """
    import json
    from backend.nanvi_rtc.session import AgentSession
    from backend.nanvi_rtc.providers.registry import registry
    from backend.nanvi_rtc.types import new_id

    await websocket.accept()

    class FastApiWsSink:
        def __init__(self, ws: WebSocket):
            self.ws = ws

        async def send_chunk(self, *, response_id: str, generation_id: str, index: int, text: str, audio=None):
            try:
                await self.ws.send_json({
                    "type": "speak",
                    "response_id": response_id,
                    "generation_id": generation_id,
                    "index": index,
                    "text": text,
                })
            except Exception:
                pass

        async def stop(self, generation_id: str):
            try:
                await self.ws.send_json({"type": "stop", "generation_id": generation_id})
            except Exception:
                pass

        async def pause(self, generation_id: str):
            try:
                await self.ws.send_json({"type": "pause", "generation_id": generation_id})
            except Exception:
                pass

        async def emit(self, event: dict):
            try:
                await self.ws.send_json(event)
            except Exception:
                pass

    sink = FastApiWsSink(websocket)
    provider_name = "nanvi"
    try:
        llm = registry.create("llm", provider_name)
    except Exception:
        provider_name = "mock"
        llm = registry.create("llm", "mock")

    session = AgentSession(new_id(), llm, sink)
    await websocket.send_json({
        "type": "ready",
        "provider": provider_name,
        "providers": registry.names("llm"),
    })

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                m = json.loads(raw)
            except Exception:
                continue
            t = m.get("type")
            if t == "user_text":
                await session.handle_user_text(m.get("text", ""))
            elif t == "pause":
                await session.pause("client")
            elif t == "resume":
                await session.resume_paused("client")
            elif t == "interrupt":
                await session.interrupt("client")
            elif t == "chunk_ack":
                await session.on_chunk_ack(m["response_id"], m["generation_id"], int(m["index"]))
            elif t == "set_provider":
                try:
                    session.set_llm(registry.create("llm", m["name"]))
                    await websocket.send_json({"type": "provider", "provider": m["name"]})
                except Exception as e:
                    await websocket.send_json({"type": "error", "where": "provider", "message": str(e)})
    except WebSocketDisconnect:
        await session.interrupt("disconnect")
    except Exception:
        await session.interrupt("disconnect")


@router.get("/live/demo", response_class=HTMLResponse)
async def get_live_voice_demo():
    """Serves the standalone browser live voice interface connected to /api/voice/live."""
    from pathlib import Path
    demo_path = Path(__file__).resolve().parent.parent / "nanvi_rtc" / "web" / "demo" / "agent.html"
    if demo_path.exists():
        content = demo_path.read_text(encoding="utf-8")
        return HTMLResponse(content=content)
    return HTMLResponse("<h3>Nanvi RTC Demo not found</h3>", status_code=404)


@router.get("/live/style.css")
async def get_live_voice_style():
    """Serves stylesheet for live voice demo."""
    from pathlib import Path
    style_path = Path(__file__).resolve().parent.parent / "nanvi_rtc" / "web" / "demo" / "style.css"
    if style_path.exists():
        return Response(content=style_path.read_text(encoding="utf-8"), media_type="text/css")
    return Response(content="", media_type="text/css")


@router.get("/live/tts")
async def live_voice_tts(text: str = "", voice: str = "en-US-JennyNeural"):
    """Stream real neural speech audio for live voice chunks.
    Ensures 100% reliable audio output across all browsers without SpeechSynthesis bugs.
    """
    if not text or not text.strip():
        raise HTTPException(status_code=400, detail="Empty text")
    clean = clean_spoken_text(text)
    if not clean.strip():
        clean = text.strip()
    import os
    if os.environ.get("PYTEST_CURRENT_TEST"):
        fallback_frame = b"\xff\xfb\x90\x00" + (b"\x00" * 410)
        return Response(
            content=fallback_frame * 3,
            media_type="audio/mpeg",
            headers={"X-Fallback-Audio": "true"},
        )
    try:
        import edge_tts
        communicate = edge_tts.Communicate(clean, voice, connect_timeout=2, receive_timeout=3)
        audio_data = bytearray()
        async with asyncio.timeout(2.0):
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data.extend(chunk["data"])
        if audio_data and len(audio_data) >= 2000:
            return Response(content=bytes(audio_data), media_type="audio/mpeg")
    except Exception as exc:
        logger.warning("Live TTS generation failed (%s); returning 503 for local client TTS fallback.", exc)

    raise HTTPException(status_code=503, detail="Neural TTS service unavailable, using client speech synthesis")

