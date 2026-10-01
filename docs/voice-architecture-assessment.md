# Voice architecture assessment

## Current application

- React and TypeScript live under `frontend/src`; the authenticated `VoiceAssistantMode` uses `useVoiceSession`, browser speech recognition, browser playback, and voice-specific UI components.
- FastAPI mounts `backend/api/voice_routes.py` under `/api/voice`. `/respond` calls the same synchronous `ChatService.ask` path as text chat; `/transcribe` uses Groq Whisper and the synthesis route delegates to the configured speech service.
- `ChatService` owns conversation history and routes through `EnterpriseOrchestrator` and its LangGraph capability nodes. Those agents enforce the existing user and tenant permissions. The Groq chat-completions provider is synchronous and does not expose a streaming interface here.
- There is no persistent voice WebSocket today. The browser recognizes a complete utterance, posts it to `/voice/respond`, waits for the full result, then starts speech playback. The current barge-in detector stops browser playback, but does not cancel the backend request.
- Authentication is bearer-token based through `get_current_user`; browser WebSockets cannot set that header, so a new socket must authenticate its first message and validate it with the existing token validator before opening a provider session.

## Integration decision

Keep `VoiceAssistantMode`, the text chat, `voice_respond`, and the existing LangGraph/authorization path. Add an optional persistent FastAPI WebSocket for audio transport and session events. Use the server-side OpenAI GPT-Live WebSocket with client delegation for full-duplex audio; route substantive requests back through the existing voice response function. The provider credential stays on the backend. If no GPT-Live credential is configured, keep the current voice flow operational.

The existing Groq integration remains the text and agent provider. Its current API surface does not provide the persistent speech-to-speech session needed for low-latency full-duplex voice. GPT-Live therefore requires a separately configured server-side OpenAI API key. Synchronous LangGraph agents cannot be forcibly stopped once inside a blocking provider or integration call; cancellation stops local playback immediately, cancels the session task, and suppresses stale results, while the underlying blocking call may still finish.

## Deployment limits

- The active-session claim and conversation-query locks are process-local. A multi-worker deployment needs a shared lease/lock store to enforce one active session per user and serialize cancelled-but-still-running graph calls across workers.
- The browser test suite covers the PCM transport, and a mocked WebSocket integration test covers authentication through delegated agent result and audio event relay. This workspace has no configured OpenAI API key, so provider connectivity, device behavior, and real time-to-first-audio still need a staging run.
- Browser capture uses an `AudioWorklet` with a `ScriptProcessorNode` compatibility fallback. Test microphone permission, echo cancellation, playback, and interruptions on the supported device/browser matrix before rollout.
