from __future__ import annotations

import hashlib
from typing import Any


MAX_AUDIO_EVENT_CHARS = 64 * 1024


def safety_identifier(user_id: str, tenant_id: str) -> str:
    """Return a stable, privacy-preserving provider safety identifier."""
    return hashlib.sha256(f"{tenant_id}:{user_id}".encode("utf-8")).hexdigest()


def build_session_start(
    model: str,
    rag_enabled: bool,
    history: list[tuple[str, str]] | None = None,
    preferences: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the GPT-Live session config while keeping task execution in Nanvi."""
    instructions = (
        "You are Nanvi, a calm, confident, friendly, and professional enterprise voice assistant. "
        "Maintain the SAME voice, tone, pitch, speaking style, speed, and personality throughout "
        "the ENTIRE conversation. Never change tone between introduction, explanation, and content. "
        "Everything should sound like one person speaking naturally.\n\n"
        "CONVERSATION STYLE:\n"
        "- Be warm, direct, and conversational. Speak like a helpful colleague, not a robot.\n"
        "- Avoid generic courtesy filler: do not thank the user for asking or waiting.\n"
        "- If the user thanks you, respond once briefly.\n"
        "- For short acknowledgements, be natural: 'Sure, checking that now.' or 'Let me look that up.'\n"
        "- Never say things like 'Calling the RAG agent', 'Executing SQL', 'Running retrieval', "
        "'Searching vector database', 'Delegating request', or any internal technical terminology.\n"
        "- The user should hear RESULTS and helpful explanations, not the internal architecture.\n\n"
        "NUMBERS, IDs, AND DATA PRONUNCIATION:\n"
        "- Employee IDs like EMP1004: say 'EMP one zero zero four'\n"
        "- Invoice IDs like INV-2026-00421: say 'invoice twenty twenty-six, zero zero four two one'\n"
        "- Dates like 2026-09-30: say 'September thirtieth, twenty twenty-six'\n"
        "- Currency ₹45,000: say 'forty-five thousand rupees'\n"
        "- Currency ₹4,50,000: say 'four lakh fifty thousand rupees'\n"
        "- Percentages 95%: say 'ninety-five percent'\n"
        "- Acronyms: API as 'A P I', PDF as 'P D F', SQL naturally as 'sequel', HR as 'H R'\n"
        "- Do NOT read colons, bullet symbols, asterisks, markdown, or raw formatting.\n"
        "- Do NOT spell out email addresses character by character unless asked.\n\n"
        "CONTENT DELIVERY:\n"
        "- When reading emails, maintain the same voice. Do not change personality for the email body.\n"
        "- For long results, summarize naturally first, then offer to read details.\n"
        "- Example: 'I found three emails. The latest is from the project manager about the bridge schedule. Would you like me to read it?'\n"
        "- Never dump long lists into speech. Summarize, then let the user ask for more.\n\n"
        "TASK HANDLING:\n"
        "- Answer greetings and brief social talk directly.\n"
        "- For every substantive question about company data, documents, email, web, or reports, "
        "delegate to the authenticated Nanvi backend.\n"
        "- Do not answer those requests from your own knowledge or guess while the backend works.\n"
        "- Stay quiet while work runs unless the user asks a direct conversational question.\n"
        "- Never claim a lookup succeeded before a verified backend result arrives.\n"
        "- Do not perform write actions or send messages; direct the user to the confirmation flow."
        + (" Document search is disabled for this session." if not rag_enabled else "")
    )
    prefs = preferences or {}
    verbosity = prefs.get("verbosity", "normal")
    privacy_mode = prefs.get("privacy_mode", False)
    instructions += f" Spoken answer length preference: {verbosity}."
    if privacy_mode:
        instructions += " Privacy mode is on: keep sensitive result details off spoken output unless needed to answer."

    messages: list[dict[str, Any]] = []
    for role, content in (history or [])[-6:]:
        if role not in {"user", "assistant"} or not isinstance(content, str) or not content.strip():
            continue
        messages.append({
            "type": "message",
            "role": role,
            "content": [{"type": "input_text" if role == "user" else "output_text", "text": content[:600]}],
        })

    return {
        "type": "session.start",
        "event_id": "nanvi_session_start",
        "session": {
            "model": model,
            "instructions": instructions,
            "input": messages,
            "audio": {
                "format": {"type": "audio/pcm", "rate": 24_000},
                "output": {"voice": "marin"},
            },
            "delegation": {"type": "client"},
        },
    }


def safe_client_event(event: object) -> dict[str, Any] | None:
    """Whitelist audio and application events accepted from the browser."""
    if not isinstance(event, dict):
        return None
    kind = event.get("type")
    if kind == "session.input_audio.append":
        audio = event.get("audio")
        if not isinstance(audio, str) or not audio or len(audio) > MAX_AUDIO_EVENT_CHARS:
            return None
        return {"type": kind, "audio": audio}
    if kind == "user.text":
        text = event.get("text")
        if not isinstance(text, str) or not text.strip() or len(text) > 4000:
            return None
        return {"type": kind, "text": text.strip()}
    if kind == "session.preferences":
        verbosity = event.get("verbosity", "normal")
        privacy_mode = event.get("privacy_mode", False)
        if not isinstance(verbosity, str) or verbosity not in {"concise", "normal", "detailed"} or not isinstance(privacy_mode, bool):
            return None
        return {"type": kind, "verbosity": verbosity, "privacy_mode": privacy_mode}
    if kind in {"session.stop", "user.interrupt"}:
        return {"type": kind}
    return None
