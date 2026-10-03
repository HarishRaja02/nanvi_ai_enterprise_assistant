import { useCallback, useEffect, useRef, useState } from "react";
import type { ChatSource, NanviApiClient, UserIdentity } from "../../api";
import { uid } from "../../lib/id";
import { toSourceView } from "../../lib/sources";
import type { Message } from "../../types";
import { BargeInDetector } from "./bargeInDetector";
import { speechRecognitionService } from "./speechRecognitionService";
import {
  speechSynthesisService,
  cleanSpokenText,
  cleanDisplayText,
  sanitizeUserQueryForAI,
} from "./speechSynthesisService";
import {
  VOICE_PROFILES,
  VoiceContextState,
  VoiceProfile,
  VoiceState,
  VoiceTurn,
} from "./voiceTypes";
import { resolveSelfRepair, TURN_TIMEOUTS } from "./turnDetector";
import { phrasePool } from "./phrasePool";
import { earconService } from "./earconService";
import { RealtimeVoiceEvent, RealtimeVoiceTransport } from "./realtimeVoiceTransport";

interface UseVoiceSessionOptions {
  api: NanviApiClient;
  identity: UserIdentity | null;
  conversationId?: string;
  ragEnabled?: boolean;
  onUpdateConversationId?: (id: string) => void;
  onAddChatMessage?: (userText: string, assistantReply: { text: string; sources?: any[] }) => void;
  onInterceptQuery?: (text: string) => boolean | Promise<boolean>;
  isOpen: boolean;
  initialPrivacyMode?: boolean;
}

const STORAGE_KEY_VOICE = "nanvi_selected_voice_profile";
const STORAGE_KEY_VERBOSITY = "nanvi_voice_verbosity";

export type VerbosityPreference = "concise" | "normal" | "detailed";

export function useVoiceSession({
  api,
  identity,
  conversationId,
  ragEnabled = true,
  onUpdateConversationId,
  onAddChatMessage,
  onInterceptQuery,
  isOpen,
  initialPrivacyMode = false,
}: UseVoiceSessionOptions) {
  const [state, setState] = useState<VoiceState>("idle");
  const [realtimeMode, setRealtimeMode] = useState<"checking" | "enabled" | "disabled">("checking");
  const [audioLevel, setAudioLevel] = useState(0);
  const [isMuted, setIsMuted] = useState(false);
  const [privacyMode, setPrivacyMode] = useState<boolean>(initialPrivacyMode);
  const [verbosity, setVerbosityState] = useState<VerbosityPreference>(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY_VERBOSITY);
      if (saved === "concise" || saved === "normal" || saved === "detailed") {
        return saved;
      }
      return "normal";
    } catch {
      return "normal";
    }
  });
  const setVerbosity = useCallback((v: VerbosityPreference) => {
    setVerbosityState(v);
    try {
      localStorage.setItem(STORAGE_KEY_VERBOSITY, v);
    } catch {
      // ignore
    }
  }, []);

  const [activeProfile, setActiveProfile] = useState<VoiceProfile>(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY_VOICE);
      const found = VOICE_PROFILES.find((p) => p.id === saved);
      return found || VOICE_PROFILES[0];
    } catch {
      return VOICE_PROFILES[0];
    }
  });

  const [contextState, setContextState] = useState<VoiceContextState>({
    currentQuery: "",
    interimTranscript: "",
    spokenAnswer: "",
    fullAnswer: "",
    importantPoints: [],
    sources: [],
    recentTurns: [],
    lastError: null,
  });

  const [capabilities, setCapabilities] = useState<string[]>([]);
  const [isFollowUpWindow, setIsFollowUpWindow] = useState(false);
  const [followUpSecondsRemaining, setFollowUpSecondsRemaining] = useState(0);

  // Refs for tracking mutable loop state
  const stateRef = useRef<VoiceState>("idle");
  stateRef.current = state;

  const isMutedRef = useRef(false);
  isMutedRef.current = isMuted;

  const conversationIdRef = useRef<string | undefined>(conversationId);
  conversationIdRef.current = conversationId;

  const bargeInDetectorRef = useRef<BargeInDetector | null>(null);
  const activeQueryRef = useRef<string>("");
  const pendingInterimRef = useRef<string>("");
  const isOpenRef = useRef(false);
  isOpenRef.current = isOpen;

  const followUpTimerRef = useRef<number | null>(null);
  const followUpIntervalRef = useRef<number | null>(null);

  const realtimeTransportRef = useRef<RealtimeVoiceTransport | null>(null);
  const realtimeModeRef = useRef<"checking" | "enabled" | "disabled">("checking");
  realtimeModeRef.current = realtimeMode;
  const realtimeRetryRef = useRef(0);
  const realtimeRetryTimerRef = useRef<number | null>(null);
  const realtimeTranscriptRef = useRef("");
  const realtimeUserTextRef = useRef("");
  const realtimeAnswerTextRef = useRef("");
  const realtimeFullAnswerRef = useRef("");
  const realtimeSourcesRef = useRef<ReturnType<typeof toSourceView>[]>([]);
  const realtimeImportantPointsRef = useRef<string[]>([]);
  const realtimeToolUsedRef = useRef(false);
  const realtimeEventHandlerRef = useRef<(event: RealtimeVoiceEvent) => void>(() => {});
  const realtimeConnectRef = useRef<() => Promise<void>>(async () => {});

  const progressIntervalRef = useRef<number | null>(null);

  useEffect(() => {
    if (!isOpen) return;
    speechSynthesisService.beginSession();
    return () => speechSynthesisService.endSession();
  }, [isOpen]);

  // Configure SpeechSynthesisService with current API client for photorealistic Neural TTS
  useEffect(() => {
    speechSynthesisService.setApiClient(api);
  }, [api]);

  // Cancel any active operational progress timers
  const clearProgressTimers = useCallback(() => {
    if (progressIntervalRef.current !== null) {
      clearInterval(progressIntervalRef.current);
      progressIntervalRef.current = null;
    }
    setContextState((prev) => ({
      ...prev,
      progressStage: null,
      progressElapsed: 0,
    }));
  }, []);

  // Cancel any active follow-up listening window
  const cancelFollowUpWindow = useCallback(() => {
    if (followUpTimerRef.current !== null) {
      clearTimeout(followUpTimerRef.current);
      followUpTimerRef.current = null;
    }
    if (followUpIntervalRef.current !== null) {
      clearInterval(followUpIntervalRef.current);
      followUpIntervalRef.current = null;
    }
    setIsFollowUpWindow(false);
    setFollowUpSecondsRemaining(0);
    setContextState((prev) => ({
      ...prev,
      isFollowUpWindow: false,
      followUpSecondsRemaining: 0,
    }));
  }, []);

  // Forward declarations for mutual references
  const sendVoiceQueryRef = useRef<(text: string) => Promise<void>>(async () => {});
  const startListeningLoopRef = useRef<() => Promise<void>>(async () => {});

  const handleRealtimeEvent = useCallback((event: RealtimeVoiceEvent) => {
    const text = typeof event.text === "string" ? event.text : "";
    switch (event.type) {
      case "session.connecting":
        setState("connecting");
        break;
      case "session.started":
        if (typeof event.conversation_id === "string") {
          conversationIdRef.current = event.conversation_id;
          onUpdateConversationId?.(event.conversation_id);
        }
        realtimeRetryRef.current = 0;
        setContextState((prev) => ({ ...prev, lastError: null }));
        setState(isMutedRef.current ? "muted" : "listening");
        break;
      case "speech.started":
        setAudioLevel(0.12);
        break;
      case "speech.stopped":
        setAudioLevel(0);
        break;
      case "transcript.delta":
        realtimeTranscriptRef.current += text;
        setContextState((prev) => ({ ...prev, interimTranscript: realtimeTranscriptRef.current, lastError: null }));
        break;
      case "transcript.completed":
        realtimeUserTextRef.current = text.trim();
        realtimeTranscriptRef.current = "";
        realtimeAnswerTextRef.current = "";
        realtimeFullAnswerRef.current = "";
        realtimeSourcesRef.current = [];
        realtimeImportantPointsRef.current = [];
        realtimeToolUsedRef.current = false;
        setContextState((prev) => ({
          ...prev,
          currentQuery: text.trim(),
          interimTranscript: "",
          spokenAnswer: "",
          fullAnswer: "",
          lastError: null,
        }));
        setState("processing");
        break;
      case "assistant.started":
        realtimeAnswerTextRef.current = "";
        setContextState((prev) => ({ ...prev, spokenAnswer: "" }));
        setState("speaking");
        break;
      case "assistant.text.delta":
        setState("speaking");
        realtimeAnswerTextRef.current += text;
        setContextState((prev) => ({ ...prev, spokenAnswer: prev.spokenAnswer + text }));
        break;
      case "assistant.audio.level":
      case "microphone.level":
        if (typeof event.level === "number") setAudioLevel(Math.min(1, Math.max(0, event.level)));
        break;
      case "assistant.awaiting_tool":
        setState("processing");
        setContextState((prev) => ({ ...prev, progressStage: typeof event.status === "string" ? event.status : "Waiting for Nanvi's sources" }));
        break;
      case "tool.started":
        setState("processing");
        setContextState((prev) => ({
          ...prev,
          spokenAnswer: typeof event.message === "string" ? event.message : prev.spokenAnswer,
          progressStage: typeof event.status === "string" ? event.status : "Working on your request",
          progressElapsed: 0,
        }));
        break;
      case "tool.completed": {
        const answer = typeof event.answer === "string" ? event.answer : "";
        const rawSources = Array.isArray(event.sources) ? event.sources as ChatSource[] : [];
        const sourceViews = rawSources.map(toSourceView);
        const points = Array.isArray(event.important_points)
          ? event.important_points.filter((point): point is string => typeof point === "string").map(cleanDisplayText)
          : [];
        realtimeFullAnswerRef.current = answer;
        realtimeSourcesRef.current = sourceViews;
        realtimeImportantPointsRef.current = points;
        realtimeToolUsedRef.current = true;
        if (typeof event.conversation_id === "string" && event.conversation_id !== conversationIdRef.current) {
          conversationIdRef.current = event.conversation_id;
          onUpdateConversationId?.(event.conversation_id);
        }
        if (typeof event.capability === "string" && event.capability) {
          setCapabilities(event.capability.split(",").filter(Boolean));
        }
        setContextState((prev) => ({
          ...prev,
          fullAnswer: answer,
          importantPoints: points,
          sources: sourceViews,
          uiSpecs: Array.isArray(event.ui_specs) ? event.ui_specs as VoiceContextState["uiSpecs"] : [],
          highlights: Array.isArray(event.highlights) ? event.highlights.filter((item): item is string => typeof item === "string") : [],
          progressStage: null,
        }));
        const query = realtimeUserTextRef.current;
        if (query && answer) onAddChatMessage?.(query, { text: answer, sources: sourceViews });
        break;
      }
      case "assistant.interrupted":
        setAudioLevel(0);
        setState("interrupted");
        break;
      case "assistant.completed": {
        const spoken = cleanDisplayText(realtimeAnswerTextRef.current);
        const answer = realtimeFullAnswerRef.current || spoken;
        const query = realtimeUserTextRef.current;
        const turn: VoiceTurn = {
          id: uid(),
          userText: query,
          spokenText: spoken,
          fullAnswer: answer,
          sources: realtimeSourcesRef.current,
          importantPoints: realtimeImportantPointsRef.current,
          timestamp: Date.now(),
        };
        if (query && answer && !realtimeToolUsedRef.current) {
          onAddChatMessage?.(query, { text: answer });
        }
        setContextState((prev) => ({
          ...prev,
          spokenAnswer: spoken,
          fullAnswer: answer,
          recentTurns: query && answer ? [turn, ...prev.recentTurns].slice(0, 20) : prev.recentTurns,
          progressStage: null,
          progressElapsed: 0,
        }));
        setAudioLevel(0);
        setState(isMutedRef.current ? "muted" : "listening");
        break;
      }
      case "session.disconnected":
        setState("reconnecting");
        break;
      case "error":
        setContextState((prev) => ({
          ...prev,
          lastError: text || "Realtime voice could not complete the request.",
          progressStage: null,
        }));
        setState("error");
        break;
    }
  }, [onAddChatMessage, onUpdateConversationId]);
  realtimeEventHandlerRef.current = handleRealtimeEvent;

  const handleSelectProfile = useCallback((profile: VoiceProfile) => {
    setActiveProfile(profile);
    try {
      localStorage.setItem(STORAGE_KEY_VOICE, profile.id);
    } catch {
      // ignore
    }
  }, []);

  const handleBargeIn = useCallback((reason?: string) => {
    cancelFollowUpWindow();
    if (realtimeModeRef.current === "enabled" && realtimeTransportRef.current) {
      realtimeTransportRef.current.interrupt();
      setState("interrupted");
      api.reportVoiceBargeIn(120).catch(() => {});
      return;
    }
    // 1. Immediately stop TTS speech playback (< 50ms)
    speechSynthesisService.stop();
    console.log(`[Nanvi Voice] Barge-in triggered (${reason || "user_voice_energy"}). Spoken audio cancelled.`);

    // Report barge-in event to backend telemetry (Milestone 11)
    api.reportVoiceBargeIn(180).catch(() => {});

    // 2. Set interrupted state briefly and resume listening without losing context
    setState("interrupted");
    setTimeout(() => {
      if (isOpenRef.current && !isMutedRef.current) {
        setState("listening");
        void startListeningLoopRef.current();
      }
    }, 120);
  }, [cancelFollowUpWindow]);

  // Initialize Barge-In Detector with sub-200ms trigger response
  useEffect(() => {
    bargeInDetectorRef.current = new BargeInDetector({
      speechThreshold: 0.28,
      minSpeechDurationMs: 180,
      onInterrupt: (reason) => {
        handleBargeIn(reason);
      },
    });
  }, [handleBargeIn]);

  const startListeningLoop = useCallback(async () => {
    if (isMutedRef.current || !isOpenRef.current) return;

    setState("listening");
    earconService.playListening();

    await speechRecognitionService.startListening({
      onSpeechStarted: () => {
        cancelFollowUpWindow();
      },
      onInterimText: (interim) => {
        if (!isOpenRef.current) return;
        cancelFollowUpWindow();
        pendingInterimRef.current = interim;

        // If currently speaking, check barge-in
        if (stateRef.current === "speaking" && bargeInDetectorRef.current) {
          bargeInDetectorRef.current.processTranscript(interim);
          return;
        }

        setContextState((prev) => ({
          ...prev,
          interimTranscript: interim,
          lastError: null,
        }));
      },
      onFinalText: (final) => {
        if (!isOpenRef.current) return;
        cancelFollowUpWindow();
        pendingInterimRef.current = "";

        // If assistant was speaking, barge-in handles it
        if (stateRef.current === "speaking") {
          handleBargeIn();
        }

        if (final.trim()) {
          void sendVoiceQueryRef.current(final.trim());
        }
      },
      onAudioLevel: (level) => {
        if (!isOpenRef.current) return;

        if (stateRef.current === "speaking") {
          // Check for vocal interruption in background while Nanvi is speaking
          bargeInDetectorRef.current?.processAudioLevel(level);
        } else if (stateRef.current === "listening") {
          setAudioLevel(level);
        }
      },
      onSilenceTimeout: async () => {
        // User finished speaking after sentence
        if (stateRef.current !== "listening") return;
        cancelFollowUpWindow();

        const accumulated = speechRecognitionService.finalizeAccumulated();
        const candidate = (accumulated || pendingInterimRef.current).trim();

        if (candidate.length > 2) {
          pendingInterimRef.current = "";
          void sendVoiceQueryRef.current(candidate);
          return;
        }

        // Seamless fallback to Groq Whisper when Web Speech API did not emit text
        setState("processing");
        try {
          const whisperText = await speechRecognitionService.transcribeViaBackend(api);
          if (whisperText && whisperText.trim()) {
            speechRecognitionService.clearRecordedAudio();
            void sendVoiceQueryRef.current(whisperText.trim());
          } else {
            // Unintelligible or empty input: ask user to repeat the sentence
            setState("speaking");
            const repeatPrompt = "Please can you repeat the sentence?";
            setContextState((prev) => ({
              ...prev,
              spokenAnswer: repeatPrompt,
              currentQuery: "",
              interimTranscript: "",
              lastError: null,
            }));
            await speechSynthesisService.speak(repeatPrompt);
            void startListeningLoopRef.current();
          }
        } catch {
          setState("speaking");
          const repeatPrompt = "Please can you repeat the sentence?";
          setContextState((prev) => ({
            ...prev,
            spokenAnswer: repeatPrompt,
            currentQuery: "",
            interimTranscript: "",
            lastError: null,
          }));
          await speechSynthesisService.speak(repeatPrompt);
          void startListeningLoopRef.current();
        }
      },
      onError: (err) => {
        if (!isOpenRef.current) return;
        setContextState((prev) => ({ ...prev, lastError: err }));
      },
    });
  }, [api, handleBargeIn]);
  startListeningLoopRef.current = startListeningLoop;

  const startFollowUpWindow = useCallback(
    (durationMs: number = TURN_TIMEOUTS.FOLLOW_UP_WINDOW_MS) => {
      cancelFollowUpWindow();

      const totalSeconds = Math.round(durationMs / 1000);
      setIsFollowUpWindow(true);
      setFollowUpSecondsRemaining(totalSeconds);
      setContextState((prev) => ({
        ...prev,
        isFollowUpWindow: true,
        followUpSecondsRemaining: totalSeconds,
      }));

      let remaining = totalSeconds;
      followUpIntervalRef.current = window.setInterval(() => {
        remaining -= 1;
        if (remaining >= 0) {
          setFollowUpSecondsRemaining(remaining);
          setContextState((prev) => ({
            ...prev,
            followUpSecondsRemaining: remaining,
          }));
        }
      }, 1000);

      followUpTimerRef.current = window.setTimeout(() => {
        cancelFollowUpWindow();
        if (stateRef.current === "listening") {
          console.log("[Nanvi Voice] Follow-up listening window expired. Transitioning to standby idle.");
          speechRecognitionService.stopListening();
          setState("idle");
          setAudioLevel(0);
        }
      }, durationMs);
    },
    [cancelFollowUpWindow]
  );

  const sendVoiceQuery = useCallback(
    async (queryText: string) => {
      cancelFollowUpWindow();
      // 1. Resolve conversational self-repair (e.g. "Show August... no, I meant September")
      const repaired = resolveSelfRepair(queryText.trim());
      // 2. Sanitize user input before giving to the AI: remove stray symbols, asterisks, brackets
      const clean = sanitizeUserQueryForAI(repaired);
      if (!clean || !identity) return;

      // 3. Check if query should be intercepted (e.g., verbal confirmation of high-risk actions)
      if (onInterceptQuery) {
        const intercepted = await onInterceptQuery(clean);
        if (intercepted) {
          return;
        }
      }

      if (realtimeModeRef.current === "enabled" && realtimeTransportRef.current) {
        activeQueryRef.current = clean;
        realtimeUserTextRef.current = clean;
        realtimeTranscriptRef.current = "";
        realtimeAnswerTextRef.current = "";
        realtimeFullAnswerRef.current = "";
        realtimeSourcesRef.current = [];
        realtimeImportantPointsRef.current = [];
        realtimeToolUsedRef.current = false;
        setContextState((prev) => ({ ...prev, currentQuery: clean, interimTranscript: "", spokenAnswer: "", lastError: null }));
        setState("processing");
        realtimeTransportRef.current.sendText(clean);
        return;
      }

      activeQueryRef.current = clean;
      setState("processing");
      earconService.playWorking();
      speechRecognitionService.pauseRecognition();

      clearProgressTimers();
      const category = phrasePool.detectCategoryFromQuery(clean);
      const isChitchat = /^(?:hello|hi|hey|good\s+morning|good\s+afternoon|good\s+evening|thanks|thank\s+you)\b/i.test(clean);
      const ackPhrase = !isChitchat ? phrasePool.getPhrase(category) : "";

      setContextState((prev) => ({
        ...prev,
        currentQuery: clean,
        interimTranscript: "",
        spokenAnswer: ackPhrase,
        lastError: null,
        progressStage: "Checking that now",
        progressElapsed: 0,
      }));

      // Start immediate natural spoken acknowledgement in parallel (Master Prompt Section 9)
      let ackPromise: Promise<void> | null = null;
      if (ackPhrase && isOpenRef.current) {
        ackPromise = speechSynthesisService.speak(ackPhrase, activeProfile, {}, api);
      }

      // Section 9 Elapsed Timer ticking every 1s
      let elapsedSeconds = 0;
      progressIntervalRef.current = window.setInterval(() => {
        elapsedSeconds += 1;
        setContextState((prev) => ({ ...prev, progressElapsed: elapsedSeconds }));
      }, 1000);

      try {
        // Execute query through existing Nanvi orchestration & permissions
        let answer = "";
        let spokenText = "";
        let points: string[] = [];
        let sourcesList: any[] = [];
        let uiSpecsList: any[] = [];
        let highlightsList: string[] = [];
        let newConvId = conversationIdRef.current;
        let returnedCaps: string[] = [];

        try {
          const confidence = speechRecognitionService.getLastConfidence();
          const res = await api.voiceRespond(
            clean,
            conversationIdRef.current,
            ragEnabled,
            { privacy_mode: privacyMode, verbosity, language: "en-IN" },
            confidence,
          );
          answer = res.answer;
          // Ensure spokenText is completely stripped of asterisks and formatting symbols
          spokenText = cleanSpokenText(res.spoken_text || res.answer);
          points = (res.important_points || []).map(cleanDisplayText);
          sourcesList = res.sources || [];
          uiSpecsList = res.ui_specs || [];
          highlightsList = res.highlights || [];
          newConvId = res.conversation_id;
          if (res.capability) {
            returnedCaps = res.capability.split(",").filter(Boolean);
          }
          if (res.user_preferences) {
            if (
              res.user_preferences.verbosity &&
              (res.user_preferences.verbosity === "concise" ||
                res.user_preferences.verbosity === "normal" ||
                res.user_preferences.verbosity === "detailed")
            ) {
              setVerbosity(res.user_preferences.verbosity);
            }
            if (typeof res.user_preferences.privacy_mode === "boolean") {
              setPrivacyMode(res.user_preferences.privacy_mode);
            }
          }
        } catch {
          // Fallback to standard chat endpoint if voice respond fails
          const chatRes = await api.chat(clean, conversationIdRef.current, ragEnabled);
          answer = chatRes.answer;
          spokenText = cleanSpokenText(chatRes.answer);
          sourcesList = chatRes.sources || [];
          newConvId = chatRes.conversation_id;
          if (chatRes.capability) {
            returnedCaps = chatRes.capability.split(",").filter(Boolean);
          }
        }

        // Wait for acknowledgement speech if still active
        if (ackPromise) {
          try {
            await ackPromise;
          } catch {}
        }

        // Processing complete — stop any scheduled progress timers
        clearProgressTimers();

        earconService.playDone();

        if (newConvId && newConvId !== conversationIdRef.current) {
          conversationIdRef.current = newConvId;
          onUpdateConversationId?.(newConvId);
        }

        const sourceViews = sourcesList.map(toSourceView);

        // Record in voice context
        const turn: VoiceTurn = {
          id: uid(),
          userText: clean,
          spokenText,
          fullAnswer: answer,
          sources: sourceViews,
          importantPoints: points,
          timestamp: Date.now(),
          uiSpecs: uiSpecsList,
        };

        setContextState((prev) => ({
          ...prev,
          spokenAnswer: spokenText,
          fullAnswer: answer,
          importantPoints: points.length > 0 ? points : prev.importantPoints,
          sources: sourceViews.length > 0 ? sourceViews : prev.sources,
          uiSpecs: uiSpecsList,
          highlights: highlightsList,
          recentTurns: [turn, ...prev.recentTurns],
        }));

        if (returnedCaps.length > 0) {
          setCapabilities(returnedCaps);
        }

        // Add to main chat message history so timeline is 100% unified!
        onAddChatMessage?.(clean, {
          text: answer,
          sources: sourceViews,
        });

        // 3. Begin Sentence-Level Streaming TTS Spoken Response
        if (!isOpenRef.current) return;

        setState("speaking");
        bargeInDetectorRef.current?.start();
        if (highlightsList.length > 0) {
          setContextState((prev) => ({ ...prev, activeHighlight: highlightsList[0] }));
        }

        speechSynthesisService.speakStream(
          spokenText,
          activeProfile,
          {
            onFirstAudio: (latencyMs) => {
              console.log(`[Nanvi Voice] time_to_first_audio: ${latencyMs}ms from response formulation`);
            },
            onAmplitude: (level) => {
              if (isOpenRef.current && stateRef.current === "speaking") {
                setAudioLevel(level);
              }
            },
            onEnd: () => {
              bargeInDetectorRef.current?.stop();
              setAudioLevel(0);
              setContextState((prev) => ({ ...prev, activeHighlight: null }));
              if (isOpenRef.current && !isMutedRef.current) {
                // Return smoothly to listening and enter the 8-second follow-up window
                void startListeningLoop();
                startFollowUpWindow(TURN_TIMEOUTS.FOLLOW_UP_WINDOW_MS);
              } else {
                setState("idle");
              }
            },
            onError: () => {
              bargeInDetectorRef.current?.stop();
              setAudioLevel(0);
              setContextState((prev) => ({ ...prev, activeHighlight: null }));
              if (isOpenRef.current && !isMutedRef.current) {
                void startListeningLoop();
                startFollowUpWindow(TURN_TIMEOUTS.FOLLOW_UP_WINDOW_MS);
              } else {
                setState("idle");
              }
            },
          },
          api
        );
      } catch (err: any) {
        clearProgressTimers();
        setState("error");
        setContextState((prev) => ({
          ...prev,
          lastError: err?.message || "Nanvi could not complete the voice query.",
        }));
      }
    },
    [
      api,
      identity,
      ragEnabled,
      privacyMode,
      activeProfile,
      onInterceptQuery,
      onUpdateConversationId,
      onAddChatMessage,
      startListeningLoop,
      cancelFollowUpWindow,
      startFollowUpWindow,
      clearProgressTimers,
    ]
  );

  sendVoiceQueryRef.current = sendVoiceQuery;

  // Toggle Mute
  const toggleMute = useCallback(() => {
    cancelFollowUpWindow();
    clearProgressTimers();
    setIsMuted((prev) => {
      const next = !prev;
      if (realtimeModeRef.current === "enabled" && realtimeTransportRef.current) {
        realtimeTransportRef.current.setMuted(next);
        setState(next ? "muted" : "listening");
        setAudioLevel(0);
        return next;
      }
      if (next) {
        speechRecognitionService.stopListening();
        speechSynthesisService.stop();
        bargeInDetectorRef.current?.stop();
        setState("muted");
        setAudioLevel(0);
      } else {
        if (isOpenRef.current) {
          void startListeningLoop();
        }
      }
      return next;
    });
  }, [cancelFollowUpWindow, clearProgressTimers, startListeningLoop]);

  // Cancel action
  const cancelActiveAction = useCallback(() => {
    cancelFollowUpWindow();
    clearProgressTimers();
    if (realtimeModeRef.current === "enabled" && realtimeTransportRef.current) {
      realtimeTransportRef.current.interrupt();
      setContextState((prev) => ({ ...prev, interimTranscript: "", progressStage: null }));
      setState(isMutedRef.current ? "muted" : "listening");
      return;
    }
    speechSynthesisService.stop();
    speechRecognitionService.stopListening();
    bargeInDetectorRef.current?.stop();
    setAudioLevel(0);

    setContextState((prev) => ({
      ...prev,
      interimTranscript: "",
    }));

    if (isOpenRef.current && !isMutedRef.current) {
      void startListeningLoop();
    } else {
      setState("idle");
    }
  }, [cancelFollowUpWindow, clearProgressTimers, startListeningLoop]);

  const connectRealtimeSession = useCallback(async () => {
    if (!isOpenRef.current || realtimeModeRef.current !== "enabled") return;
    realtimeTransportRef.current?.stop();
    const transport = new RealtimeVoiceTransport(api, {
      onEvent: (event) => realtimeEventHandlerRef.current(event),
      onClose: (code, reason) => {
        if (!isOpenRef.current || realtimeModeRef.current !== "enabled") return;
        if (code === 4401 || code === 4403 || code === 4404 || code === 4429) {
          setContextState((prev) => ({ ...prev, lastError: reason || "Realtime voice session was rejected." }));
          setState("error");
          return;
        }
        const attempts = realtimeRetryRef.current + 1;
        realtimeRetryRef.current = attempts;
        if (attempts > 4) {
          setContextState((prev) => ({ ...prev, lastError: "Realtime voice disconnected. Please reconnect and try again." }));
          setState("error");
          return;
        }
        setState("reconnecting");
        const delay = Math.min(500 * 2 ** (attempts - 1), 4000);
        realtimeRetryTimerRef.current = window.setTimeout(() => {
          realtimeRetryTimerRef.current = null;
          void realtimeConnectRef.current();
        }, delay);
      },
    });
    realtimeTransportRef.current = transport;
    setState("connecting");
    try {
      await transport.start(conversationIdRef.current, ragEnabled, { verbosity, privacy_mode: privacyMode });
      realtimeRetryRef.current = 0;
    } catch (error) {
      if (!isOpenRef.current) return;
      setContextState((prev) => ({
        ...prev,
        lastError: error instanceof Error ? error.message : "Realtime voice could not connect.",
      }));
      setState("error");
    }
  }, [api, ragEnabled, privacyMode, verbosity]);
  realtimeConnectRef.current = connectRealtimeSession;

  useEffect(() => {
    if (realtimeMode === "enabled") {
      realtimeTransportRef.current?.updatePreferences({ verbosity, privacy_mode: privacyMode });
    }
  }, [privacyMode, realtimeMode, verbosity]);

  // Lifecycle when Voice Mode opens or closes
  useEffect(() => {
    let disposed = false;
    if (isOpen) {
      setIsMuted(false);
      setState("connecting");
      setRealtimeMode("checking");
      const realtimeStatus = typeof api.getRealtimeVoiceStatus === "function"
        ? api.getRealtimeVoiceStatus()
        : Promise.resolve({ enabled: false, model: null });
      void realtimeStatus
        .then((status) => {
          if (disposed) return;
          if (status.enabled) {
            setRealtimeMode("enabled");
            realtimeModeRef.current = "enabled";
            void realtimeConnectRef.current();
          } else {
            setRealtimeMode("disabled");
            realtimeModeRef.current = "disabled";
            void startListeningLoop();
          }
        })
        .catch(() => {
          if (disposed) return;
          // Preserve the existing authenticated browser voice path if the optional
          // realtime provider is not configured or its status endpoint is unavailable.
          setRealtimeMode("disabled");
          realtimeModeRef.current = "disabled";
          void startListeningLoop();
        });
    } else {
      setRealtimeMode("disabled");
      realtimeModeRef.current = "disabled";
      cancelFollowUpWindow();
      clearProgressTimers();
      speechRecognitionService.stopListening();
      speechSynthesisService.stop();
      realtimeTransportRef.current?.stop();
      realtimeTransportRef.current = null;
      bargeInDetectorRef.current?.stop();
      setState("idle");
      setAudioLevel(0);
    }

    return () => {
      disposed = true;
      cancelFollowUpWindow();
      clearProgressTimers();
      speechRecognitionService.stopListening();
      speechSynthesisService.stop();
      if (realtimeRetryTimerRef.current !== null) {
        window.clearTimeout(realtimeRetryTimerRef.current);
        realtimeRetryTimerRef.current = null;
      }
      realtimeTransportRef.current?.stop();
      realtimeTransportRef.current = null;
      bargeInDetectorRef.current?.stop();
    };
  }, [api, isOpen, cancelFollowUpWindow, clearProgressTimers, startListeningLoop]);

  // Manually finalize and send current speech immediately (either interim text or Whisper fallback)
  const manualDoneSpeaking = useCallback(async () => {
    if (realtimeModeRef.current === "enabled") return;
    cancelFollowUpWindow();
    if (stateRef.current !== "listening") return;

    const accumulated = speechRecognitionService.finalizeAccumulated();
    const candidateText = (accumulated || pendingInterimRef.current).trim();

    if (candidateText.length > 1) {
      pendingInterimRef.current = "";
      void sendVoiceQuery(candidateText);
      return;
    }

    setState("processing");
    try {
      const whisperText = await speechRecognitionService.transcribeViaBackend(api);
      if (whisperText && whisperText.trim()) {
        speechRecognitionService.clearRecordedAudio();
        void sendVoiceQuery(whisperText.trim());
      } else {
        setState("speaking");
        const repeatPrompt = "Please can you repeat the sentence?";
        setContextState((prev) => ({
          ...prev,
          spokenAnswer: repeatPrompt,
          currentQuery: "",
          interimTranscript: "",
          lastError: null,
        }));
        await speechSynthesisService.speak(repeatPrompt);
        void startListeningLoopRef.current();
      }
    } catch {
      setState("speaking");
      const repeatPrompt = "Please can you repeat the sentence?";
      setContextState((prev) => ({
        ...prev,
        spokenAnswer: repeatPrompt,
        currentQuery: "",
        interimTranscript: "",
        lastError: null,
      }));
      await speechSynthesisService.speak(repeatPrompt);
      void startListeningLoopRef.current();
    }
  }, [api, cancelFollowUpWindow, sendVoiceQuery]);

  const requestMicrophonePermission = useCallback(async () => {
    setContextState((prev) => ({ ...prev, lastError: null }));
    if (realtimeModeRef.current === "enabled") {
      if (!realtimeTransportRef.current) await realtimeConnectRef.current();
      return;
    }
    await startListeningLoop();
  }, [startListeningLoop]);

  return {
    state,
    realtimeMode,
    audioLevel,
    isMuted,
    isFollowUpWindow,
    followUpSecondsRemaining,
    activeProfile,
    contextState,
    capabilities,
    privacyMode,
    togglePrivacyMode: () => setPrivacyMode((p) => !p),
    verbosity,
    setVerbosity,
    toggleMute,
    cancelActiveAction,
    manualDoneSpeaking,
    requestMicrophonePermission,
    startListening: startListeningLoop,
    selectProfile: handleSelectProfile,
    sendQuery: sendVoiceQuery,
  };
}
