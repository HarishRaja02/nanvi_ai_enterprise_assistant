# NANVI MASTER SPEC: VOICE-FIRST CONTEXT-AWARE ENTERPRISE AI INTERFACE

## 1. NON-NEGOTIABLE RULES (read first, apply always)

1. Preserve all existing working functionality. Do not remove or rewrite working code unnecessarily.
2. Extend existing agents (RAG, SQL, Web, Email, Report). Never create duplicate agents or duplicate architectures.
3. Work on a git feature branch. Put the new experience behind a feature flag (`NANVI_VOICE_UI`). The old chat UI must stay reachable at all times.
4. Never claim a feature is done unless it was actually implemented and verified. Every report must separate **REAL** from **STUBBED** from **NOT DONE**.
5. Never fake backend progress. Progress UI and progress speech must come from real backend events.
6. Never let the LLM generate HTML, JavaScript or React. It outputs a structured UI spec that is validated against a strict schema. The frontend renders only approved components.
7. Never bypass authentication or authorization. Voice, buttons and text all go through the same RBAC/ABAC checks.
8. Never hallucinate enterprise data. If evidence is insufficient, say so.
9. Never perform risky side-effect actions (send email, delete, modify data, approve) without explicit user confirmation.
10. Never expose or log secrets, API keys, JWT secrets or credentials. Do not log raw sensitive data (salary, personal details) unnecessarily.
11. Voice is short. The screen holds the detail. Voice never reads tables or charts aloud.
12. One shared conversation/task context across voice, text, UI, actions, agents and memory. No parallel incompatible state.
13. If a provider needs credentials that are missing: implement the integration cleanly, document the env variable, provide a safe fallback, and flag it clearly. Never invent credentials.
14. Do not copy any copyrighted character, voice, UI or branding. The goal is behavior, not imitation.
15. The user always stays in control. Typing must always keep working.

## 2. CURRENT STACK (discovered and populated)

```text
Frontend framework:      React 19 + TypeScript + Vite + TailwindCSS
Backend framework:       FastAPI (Python 3.11/3.12, Uvicorn)
Streaming today:         SSE (StreamingResponse on /api/chat/stream, /api/agent/stream)
Current STT:             Browser Web Speech API (webkitSpeechRecognition in Composer.tsx)
Current TTS:             Browser SpeechSynthesis (speechSynthesis.speak in ChatView.tsx)
Current avatar:          None (UI has status badges, orb/voice pulse in audio chat)
Agent orchestration:     LangGraph (StateGraph with AgentState, capability agents router, orchestrator)
Vector DB / SQL DB:      Qdrant / Chroma / In-Memory (VectorStoreFactory) + SQLite (app DB) + DuckDB/PostgreSQL (SQL agent)
Auth model:              JWT Bearer (RBAC + ABAC context, role-based tool gateway)
Provider keys available: Configured via .env (Gemini, OpenAI, Cohere, Groq, Tavily, etc.)
Am I willing to switch STT/TTS providers?  Yes / Adaptive (Browser Web Speech fallback + High-fidelity streaming provider options)
Deployment target:       Local / Docker / Vercel
```

## 3. PRODUCT VISION

Transform Nanvi from a chatbot/dashboard into a **voice-first, context-aware enterprise AI operating interface**.

```text
User speaks -> Nanvi resolves context -> determines intent -> existing agents do the work
-> real progress is streamed -> Nanvi gives a SHORT spoken answer
-> the screen builds the interface needed for the task -> 2-3 executable next actions
-> user continues naturally without typing
```

The user should feel: "I am talking to a capable enterprise assistant", not "I am typing commands into a chatbot".

**Philosophy in one sentence:** Nanvi understands what the user means, knows what they are looking at, does the work in the background, keeps them informed naturally, speaks only the important result, and builds the visual interface needed to explore or act on it.

## 4. WORKING PROTOCOL FOR THE CODING AGENT

- **Phase 0 is inspection only. Write no code.** Produce the architecture map, feature inventory, gap analysis, provider recommendation and milestone plan. Then STOP and wait for approval.
- After approval, implement **one milestone at a time**.
- After each milestone: run the build, run existing tests, add new tests, verify existing features still work, and report REAL / STUBBED / NOT DONE.
- Do not start the next milestone until told to.
- If something in the spec conflicts with the real codebase, explain the conflict and propose the smallest safe adaptation. Do not silently deviate.

### Phase 0 must identify

Frontend framework, backend framework, API architecture, auth, LangGraph implementation, RAG, SQL agent, web agent, email agent, current chat flow, current voice implementation, current streaming (SSE/WebSocket), UI component architecture, state management, databases, vector DB, document ingestion, how citations/sources are represented, env variables, deployment architecture.

## 5. TARGET ARCHITECTURE

```text
Mic -> Audio front-end (echo cancel, noise suppress) -> VAD + Turn Detection -> Streaming STT
   -> Context Engine -> Intent/Task Planner -> LangGraph Router
        -> RAG / SQL / Web / Email / Report agents (EXISTING, extended not replaced)
   -> Evidence + Sources
        -> UI Planner (validated UI spec)
        -> Human Response Planner (spoken text, highlights, actions)
   -> Sentence-level streaming TTS -> React Workspace (voice + UI + actions + captions)
```

Text input and button clicks enter at the **Intent/Task Planner** through the same pipeline as voice.

## 6. SHARED CONTRACTS

### 6.1 Context object (single source of truth)

```json
{
  "session_id": "", "conversation_id": "", "user": {"id": "", "role": "", "permissions": []},
  "active_page": {"route": "", "page_type": "", "title": ""},
  "active_entity": {"type": "invoice", "id": "", "name": ""},
  "active_document": {"document_id": "", "filename": "", "page": null},
  "last_intent": "", "last_result_ref": "", "last_ui": {}, "last_sources": [],
  "ui_entity_index": {"customer_1": {}, "customer_2": {}},
  "user_preferences": {"verbosity": "concise", "privacy_mode": true, "language": "auto"},
  "conversation_state": {"turn_state": "idle|listening|thinking|speaking|interrupted"}
}
```

Rules: pass only the relevant slice to the model. Never include secrets. Respect the existing memory architecture and do not store sensitive data unnecessarily.

### 6.2 Event protocol (SSE or WebSocket; reuse whatever exists)

Envelope: `{ "event", "task_id", "request_id", "timestamp", "payload" }`

Event types:

```text
task_started, status, partial_transcript, final_transcript, assistant_text,
audio_start, audio_chunk, audio_end, audio_cancelled,
ui_spec, action_suggestions, highlight,
source_found, source_verified, task_complete, task_error
```

Progress `status` values must reflect real lifecycle states:

- Documents: SEARCH_STARTED, SEARCHING_FILES, MATCHING_DOCUMENTS, RERANKING_RESULTS, VERIFYING_SOURCES, COMPLETE
- SQL: SQL_STARTED, GENERATING_QUERY, EXECUTING_QUERY, ANALYZING_RESULT, COMPLETE
- Web: WEB_SEARCH_STARTED, FETCHING_RESULTS, ANALYZING_RESULTS, VERIFYING, COMPLETE
- Email: EMAIL_SEARCH_STARTED, SEARCHING_MAILBOX, MATCHING_EMAILS, COMPLETE
- Report: REPORT_STARTED, COLLECTING_DATA, ANALYZING, GENERATING_REPORT, COMPLETE

### 6.3 UI spec (controlled DSL)

The LLM emits JSON. Backend validates (Pydantic or equivalent). Frontend validates again (Zod or equivalent). Reject unknown component types, arbitrary HTML/JS, unsafe URLs and invalid data types. On validation failure, fall back to a simple safe summary card and log the error.

```json
{
  "type": "financial_dashboard",
  "title": "Quarterly Revenue",
  "components": [
    {"id": "kpi_rev", "type": "kpi", "label": "Revenue", "value": 124000000, "change": 14.2, "currency": "INR"},
    {"id": "trend", "type": "line_chart", "data": []},
    {"id": "insight_1", "type": "insight", "text": "Enterprise sales drove most growth."}
  ],
  "actions": [
    {"id": "revenue_drivers", "label": "Show revenue drivers", "intent": "analyze_revenue_drivers", "parameters": {}}
  ]
}
```

Approved components: KPI card, metric grid, line/bar/area/donut chart, table, ranking list, comparison card, trend card, insight card, source/citation card, invoice card, employee card, candidate card, email composer, document preview, search results, timeline, activity feed, progress card, action buttons, expandable details, alert card, summary card, org hierarchy, funnel.

Every component has a stable `id` so highlights and references can target it.

### 6.4 Intent and action registry

One centralized registry mapping `intent -> handler, required permissions, risk level, parameter schema`. No scattered if-statements. Voice, text and buttons all resolve to registry intents.

```json
{"id": "compare_previous_quarter", "label": "Compare with last quarter",
 "intent": "compare_revenue_period", "parameters": {"period": "previous_quarter"}}
```

Clicking an action enters the same orchestration pipeline as a spoken request.

## 7. VOICE PIPELINE AND REALISM

Realism comes mainly from **timing and turn-taking**, not voice quality.

### 7.1 Audio foundations (required for barge-in to work)

- Enable mic constraints: `echoCancellation`, `noiseSuppression`, `autoGainControl`. Without echo cancellation Nanvi hears itself and interrupts itself.
- Always-visible mic state. Mute and push-to-talk option.
- Graceful fallback to text if mic, permission or connection fails.

### 7.2 Streaming and latency

- Stream STT, LLM and TTS. Speak the first sentence before the full answer exists (sentence-level TTS).
- Target under about 800 ms from end of user speech to first audio. Use a short instant acknowledgement ("Sure.") when the backend needs longer.
- Parallelize independent backend calls. Avoid unnecessary RAG/DB calls. Render UI progressively.
- Log time_to_first_audio from day one.

### 7.3 Barge-in

When the user speaks while Nanvi is speaking: stop audio within about 200 ms, cancel the TTS stream, emit `audio_cancelled`, reset speech state, keep conversation context, make the user's speech the active input. If the user says "go on", resume. Distinguish real interruptions from background noise and short backchannels ("mm-hm").

### 7.4 Smart end-of-turn detection

Do not rely on fixed silence alone. Use VAD plus a semantic completeness check. "Show me revenue for... um..." must not trigger a response. Tune the wait so users are not cut off, without adding sluggish delay.

### 7.5 Follow-up window

After Nanvi speaks, keep listening for about 8 seconds (configurable) so the user does not need a wake word. Short follow-ups ("Why?", "Only enterprise", "Open that") resolve against the previous result.

### 7.6 Understanding the user

- **Self-repair:** "Show August... no, I meant September" uses only the correction.
- **Vocabulary biasing:** feed employee, vendor and product names and acronyms (GST, PO, EBITDA, CGST) into STT where the provider supports it.
- **Code-switching:** support English mixed with Hindi/Tamil, e.g. "Revenue last quarter என்ன?" Do not force everything into English and do not translate unnecessarily.
- **Low STT confidence:** ask one short clarifying question ("Ravi Kumar or Ravi Shankar?"). Never silently execute a possibly wrong or risky action.
- **Frustration detection (optional):** become shorter and more direct, at most one brief apology.

### 7.7 Speech output quality

- Natural prosody and pauses. Emphasis on key numbers. Use SSML or an expressive model where available.
- Phrase pools so progress and acknowledgement lines never repeat identically back to back.
- Do not insert "umm/hmm" routinely. Rare, purposeful pauses only.
- Optional mild speed mirroring of the user's pace.
- Earcons: subtle sounds for listening, working, done. They can replace speech during very short waits.
- **Spoken numbers** (a separate function for TTS text, not just UI formatting): "eighteen point four crore", "twelve lakh", "about 14 percent". Never read long digit strings like 12,50,00,000.

### 7.8 Voice and screen sync

- Highlight events fire at the moment the related phrase is spoken (`{"event":"highlight","payload":{"target":"revenue_driver_enterprise"}}`).
- Deictic references resolve via `ui_entity_index`: "this one", "the second customer", "that invoice", "compare these".
- Live captions that follow spoken words. Lightweight, not visually dominant.

## 8. HUMAN RESPONSE PLANNER (critical)

Raw agent output must never go straight to TTS. Pipeline: `Agent result -> Evidence -> UI Planner -> Human Response Planner -> TTS`.

Output:

```json
{
  "spoken_response": "Sales are up 14% this quarter. Enterprise is driving most of it.",
  "screen_message": "I've put the full breakdown here.",
  "highlights": ["revenue_driver_enterprise"],
  "suggested_actions": ["revenue_drivers", "compare_previous_quarter", "top_customers"],
  "sensitivity": "normal"
}
```

Rules: conclusion first; 1 to 3 short natural sentences; no reading tables or charts; no "According to the retrieved documents"; no "As an AI"; no chain-of-thought; no formal report tone; no needless disclaimers. Adapt verbosity: short by default, longer when the user asks for detail or when no UI exists to carry the detail. Remember "shorter" and "tell me more" as preferences.

Honest uncertainty: say "I think" or "I'm not fully sure" only when real confidence is low.

## 9. PROGRESS SYSTEM

- Under about 2 seconds: say nothing.
- Around 2 to 4 seconds: a short acknowledgement ("Sure, give me a second. I'm checking the company files.").
- Longer: at most one or two more updates tied to real events ("I found a few matches. I'm narrowing them down.", "Almost there."). Then the result.
- Speak operational status only. Never fake reasoning ("I'm thinking about whether the third document...") and never expose internals ("running vector similarity search").
- Progress UI: compact glass progress card driven by the same real events.

## 10. DYNAMIC GENERATIVE UI

The workspace is generated per question, not a static dashboard.

| User asks | UI |
|---|---|
| Revenue this quarter | KPI + trend + drivers |
| Why did revenue fall/rise? | KPI + drivers/waterfall + comparison |
| Biggest customers | ranking + bars |
| Show invoice X | invoice card |
| Find the contract | document search + source preview |
| Who reports to the CTO? | org hierarchy |
| Hiring pipeline | funnel + candidate stats |
| Prepare an email | email composer |
| Compare two candidates | side-by-side comparison |

- **Ephemeral:** the workspace transforms with the conversation. "Why?" transforms the current view rather than opening an unrelated page.
- **Predictive actions:** 2 to 3 maximum, chosen from current entity, page, task, permissions, available tools and history. Every action is a real registry intent. Buttons are shortcuts; the user can always just speak.
- **No chatbot wall.** Voice, short response, dynamic workspace, actions, continue.
- Use appropriate chart types only. No meaningless charts. Use Indian number formatting in the UI (₹1,25,000, ₹12.5 lakh, ₹2.4 Cr).

## 11. RAG GROUNDING (must not weaken)

- Preserve for every result: document_id, filename, page, chunk_id, relevance score, source metadata.
- If an active document exists, prioritize or restrict retrieval to it when appropriate. "Total on this invoice?" must use the active invoice, not unrelated documents.
- Understand the existing retrieval metric (similarity vs distance vs cosine vs reranker score) before setting any threshold. Do not invent thresholds.
- If evidence is insufficient: "I couldn't find enough evidence to answer that confidently." with actions [Search all documents] [Try another query].
- Show as verified only the sources actually used for the answer (filename, page, relevant section, source type).

## 12. SECURITY, PRIVACY, CONFIRMATION

- Inherit existing authentication and RBAC/ABAC on every intent. Enforce server-side.
- **Privacy mode:** sensitive values (salary, personal data) appear on screen and are not spoken. Nanvi says "I've put it on screen."
- **Risky actions** require an explicit confirmation (spoken yes or button): send email, delete, modify data, approve candidate, change employee info, external workflows. Low-risk actions proceed without asking.
- Optional later: speaker verification before payments or highly sensitive data.
- Errors are conversational ("I couldn't reach the database right now.") with a useful action ([Try again]). Real errors go to logs.

## 13. VISUAL DESIGN

Premium enterprise glass interface: minimal, spacious, professional, subtle blur and borders, soft shadows, warm enterprise orange accents, light foundation, smooth transitions, clean typography. Preserve Nanvi's existing brand. Not a gaming HUD; no excess glow.

Voice states share one visual language and react to real system state: idle, listening (responsive waveform), thinking, searching (progress card), analyzing, generating, speaking (waveform), interrupted, success, error.

The avatar is optional and never the architecture. The system must work perfectly without one. If one exists, connect it to the new voice lifecycle.

## 14. PROACTIVE BEHAVIOR (later milestone, restrained)

Speak first only when justified ("Your finance report is ready", "Two invoices are overdue"). Never interrupt the user, provide a "not now" mode, and do not become annoying. Time and situation awareness and "callbacks" to earlier sessions only where existing memory supports it.

## 15. OBSERVABILITY AND METRICS

Log (no secrets, no unnecessary sensitive data): request_id, session_id, intent, selected agent, retrieval count, relevance scores, selected sources, UI type, suggested actions, latency per stage, STT/TTS latency, tool execution time, interruptions, errors.

Track: time_to_first_audio, total_response_latency, barge_in_latency, false_interruption_rate, wrongly_cut_off_turns, STT error rate on the company vocabulary, failed_intent_rate, hallucination_rate, retrieval_precision, action_success_rate, and a simple "did it feel natural?" rating.

## 16. MILESTONES (implement one at a time)

Each milestone has acceptance criteria. Do not move on until they pass.

**M0. Inspection and plan** (no code)
Accept: architecture map, feature inventory, gap analysis, provider recommendation with reasons (STT, TTS, VAD/turn detection), milestone plan tailored to this codebase.

**M1. Context object + event protocol + feature flag**
Accept: shared context used by text chat; unified event envelope on existing streaming (or new SSE/WebSocket); existing chat unchanged with flag off.

**M2. Streaming voice pipeline + barge-in + audio foundations**
Accept: mic with echo cancellation, streaming STT, sentence-level TTS, barge-in stops audio in about 200 ms, text fallback works, time_to_first_audio logged.

**M3. Turn detection + follow-up window**
Accept: mid-sentence pauses do not trigger responses; follow-up window works without wake word.

**M4. Human Response Planner + progress events + progress UI**
Accept: real lifecycle events from RAG/SQL/Web/Email; no speech under about 2 s; short natural progress speech; phrase variation; spoken-number formatter.

**M5. UI spec schema, validation and renderer**
Accept: backend and frontend validation; unknown components rejected with safe fallback; first component set (KPI, charts, table, ranking, insight, invoice, employee, source, email composer, progress, actions).

**M6. Dynamic workspace + suggested actions + intent registry**
Accept: UI planner picks layout per question; 2 to 3 executable actions through the same pipeline; ephemeral transitions.

**M7. Contextual follow-ups + deictic references**
Accept: "Why?", "Only enterprise", "Open the second one", "this invoice" resolve correctly through the context object and `ui_entity_index`.

**M8. Voice-screen sync + captions + earcons**
Accept: highlight events fire in sync with speech; captions follow speech.

**M9. Privacy mode + risky-action confirmation + low-confidence handling**
Accept: sensitive values not spoken; send-email needs confirmation; unclear STT triggers a clarifying question.

**M10. Indian languages/code-switching, vocabulary biasing, adaptive verbosity, memory of preferences**

**M11. Polish, performance, observability dashboard, full regression test**

## 17. REQUIRED TEST FLOWS

1. "Show revenue this quarter": short voice answer, financial UI, 2 to 3 actions.
2. "Why?": resolves to the revenue context and transforms the UI.
3. "Compare with last quarter": comparison UI.
4. "Show the biggest customers": ranking UI.
5. "Open the second one": opens customer #2 from current UI.
6. "What's the total on this invoice?": uses active invoice, correct source, invoice card.
7. Long document search: real progress events, short progress speech, final result.
8. User interrupts Nanvi: TTS stops quickly, new speech processed.
9. Send email: confirmation required.
10. Insufficient RAG evidence: honest "not enough evidence", no hallucination.
11. Permission test: a restricted user cannot fetch restricted data by voice or button.
12. Malformed UI spec from the LLM: rejected, safe fallback shown.
13. Mic denied or connection lost: text fallback works.

## 18. REPORT FORMAT AFTER EACH MILESTONE

1. What was done (files modified and files created).
2. REAL / STUBBED / NOT DONE table.
3. How it works (short).
4. Tests run and results; frontend build and backend startup status.
5. Existing-feature regression check (auth, chat, RAG, upload, citations, SQL, web, email, reports, memory, settings).
6. Config or environment variables required.
7. Known issues and the recommended next milestone.
