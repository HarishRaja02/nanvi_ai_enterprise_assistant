import { useCallback, useEffect, useRef, useState } from "react";
import type { NanviApiClient, UserIdentity } from "../../api";
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

interface UseVoiceSessionOptions {
  api: NanviApiClient;
  identity: UserIdentity | null;
  conversationId?: string;
  ragEnabled?: boolean;
  onUpdateConversationId?: (id: string) => void;
  onAddChatMessage?: (userText: string, assistantReply: { text: string; sources?: any[] }) => void;
  isOpen: boolean;
}

const STORAGE_KEY_VOICE = "nanvi_selected_voice_profile";

export function useVoiceSession({
  api,
  identity,
  conversationId,
  ragEnabled = true,
  onUpdateConversationId,
  onAddChatMessage,
  isOpen,
}: UseVoiceSessionOptions) {
  const [state, setState] = useState<VoiceState>("idle");
  const [audioLevel, setAudioLevel] = useState(0);
  const [isMuted, setIsMuted] = useState(false);
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

  // Configure SpeechSynthesisService with current API client for photorealistic Neural TTS
  useEffect(() => {
    speechSynthesisService.setApiClient(api);
  }, [api]);

  // Initialize Barge-In Detector
  useEffect(() => {
    bargeInDetectorRef.current = new BargeInDetector({
      speechThreshold: 0.28,
      minSpeechDurationMs: 260,
      onInterrupt: () => {
        // Natural interruption triggered!
        handleBargeIn();
      },
    });
  }, []);

  const handleSelectProfile = useCallback((profile: VoiceProfile) => {
    setActiveProfile(profile);
    try {
      localStorage.setItem(STORAGE_KEY_VOICE, profile.id);
    } catch {
      // ignore
    }
  }, []);

  // Forward declaration of sendQuery to be referenced in startListeningLoop
  const sendVoiceQueryRef = useRef<(text: string) => Promise<void>>(async () => {});

  const handleBargeIn = useCallback(() => {
    // 1. Immediately stop TTS speech playback
    speechSynthesisService.stop();

    // 2. Set interrupted state briefly and resume listening
    setState("interrupted");
    setTimeout(() => {
      if (isOpenRef.current && !isMutedRef.current) {
        setState("listening");
        startListeningLoop();
      }
    }, 280);
  }, []);

  const startListeningLoop = useCallback(async () => {
    if (isMutedRef.current || !isOpenRef.current) return;

    setState("listening");

    await speechRecognitionService.startListening({
      onInterimText: (interim) => {
        if (!isOpenRef.current) return;
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

        if (pendingInterimRef.current.trim().length > 3) {
          const query = pendingInterimRef.current.trim();
          pendingInterimRef.current = "";
          void sendVoiceQueryRef.current(query);
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
            setState("listening");
          }
        } catch {
          setState("listening");
        }
      },
      onError: (err) => {
        if (!isOpenRef.current) return;
        setContextState((prev) => ({ ...prev, lastError: err }));
      },
    });
  }, [api, handleBargeIn]);

  const sendVoiceQuery = useCallback(
    async (queryText: string) => {
      // 1. Sanitize user input before giving to the AI: remove stray symbols, asterisks, brackets
      const clean = sanitizeUserQueryForAI(queryText.trim());
      if (!clean || !identity) return;

      activeQueryRef.current = clean;
      setState("processing");
      speechRecognitionService.stopListening();
      bargeInDetectorRef.current?.stop();

      setContextState((prev) => ({
        ...prev,
        currentQuery: clean,
        interimTranscript: "",
        lastError: null,
      }));

      try {
        // Execute query through existing Nanvi orchestration & permissions
        let answer = "";
        let spokenText = "";
        let points: string[] = [];
        let sourcesList: any[] = [];
        let newConvId = conversationIdRef.current;
        let returnedCaps: string[] = [];

        try {
          const res = await api.voiceRespond(clean, conversationIdRef.current, ragEnabled);
          answer = res.answer;
          // Ensure spokenText is completely stripped of asterisks and formatting symbols
          spokenText = cleanSpokenText(res.spoken_text || res.answer);
          points = (res.important_points || []).map(cleanDisplayText);
          sourcesList = res.sources || [];
          newConvId = res.conversation_id;
          if (res.capability) {
            returnedCaps = res.capability.split(",").filter(Boolean);
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
        };

        setContextState((prev) => ({
          ...prev,
          spokenAnswer: spokenText,
          fullAnswer: answer,
          importantPoints: points.length > 0 ? points : prev.importantPoints,
          sources: sourceViews.length > 0 ? sourceViews : prev.sources,
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

        // 3. Begin TTS Spoken Response
        if (!isOpenRef.current) return;

        setState("speaking");
        bargeInDetectorRef.current?.start();

        speechSynthesisService.speak(
          spokenText,
          activeProfile,
          {
            onAmplitude: (level) => {
              if (isOpenRef.current && stateRef.current === "speaking") {
                setAudioLevel(level);
              }
            },
            onEnd: () => {
              bargeInDetectorRef.current?.stop();
              setAudioLevel(0);
              if (isOpenRef.current && !isMutedRef.current) {
                // Return smoothly to listening for continuous conversation
                startListeningLoop();
              } else {
                setState("idle");
              }
            },
            onError: () => {
              bargeInDetectorRef.current?.stop();
              setAudioLevel(0);
              if (isOpenRef.current && !isMutedRef.current) {
                startListeningLoop();
              } else {
                setState("idle");
              }
            },
          },
          api
        );
      } catch (err: any) {
        setState("error");
        setContextState((prev) => ({
          ...prev,
          lastError: err?.message || "Nanvi could not complete the voice query.",
        }));
      }
    },
    [api, identity, ragEnabled, activeProfile, onUpdateConversationId, onAddChatMessage, startListeningLoop]
  );

  sendVoiceQueryRef.current = sendVoiceQuery;

  // Toggle Mute
  const toggleMute = useCallback(() => {
    setIsMuted((prev) => {
      const next = !prev;
      if (next) {
        speechRecognitionService.stopListening();
        speechSynthesisService.stop();
        bargeInDetectorRef.current?.stop();
        setState("muted");
        setAudioLevel(0);
      } else {
        if (isOpenRef.current) {
          startListeningLoop();
        }
      }
      return next;
    });
  }, [startListeningLoop]);

  // Cancel action
  const cancelActiveAction = useCallback(() => {
    speechSynthesisService.stop();
    speechRecognitionService.stopListening();
    bargeInDetectorRef.current?.stop();
    setAudioLevel(0);

    setContextState((prev) => ({
      ...prev,
      interimTranscript: "",
    }));

    if (isOpenRef.current && !isMutedRef.current) {
      startListeningLoop();
    } else {
      setState("idle");
    }
  }, [startListeningLoop]);

  // Lifecycle when Voice Mode opens or closes
  useEffect(() => {
    if (isOpen) {
      setIsMuted(false);
      startListeningLoop();
    } else {
      speechRecognitionService.stopListening();
      speechSynthesisService.stop();
      bargeInDetectorRef.current?.stop();
      setState("idle");
      setAudioLevel(0);
    }

    return () => {
      speechRecognitionService.stopListening();
      speechSynthesisService.stop();
      bargeInDetectorRef.current?.stop();
    };
  }, [isOpen, startListeningLoop]);

  // Manually finalize and send current speech immediately (either interim text or Whisper fallback)
  const manualDoneSpeaking = useCallback(async () => {
    if (stateRef.current !== "listening") return;

    if (pendingInterimRef.current.trim().length > 1) {
      const q = pendingInterimRef.current.trim();
      pendingInterimRef.current = "";
      void sendVoiceQuery(q);
      return;
    }

    setState("processing");
    try {
      const whisperText = await speechRecognitionService.transcribeViaBackend(api);
      if (whisperText && whisperText.trim()) {
        speechRecognitionService.clearRecordedAudio();
        void sendVoiceQuery(whisperText.trim());
      } else {
        setState("listening");
        setContextState((prev) => ({
          ...prev,
          lastError: "No speech recognized. Please speak and try again.",
        }));
      }
    } catch {
      setState("listening");
    }
  }, [api, sendVoiceQuery]);

  const requestMicrophonePermission = useCallback(async () => {
    setContextState((prev) => ({ ...prev, lastError: null }));
    await startListeningLoop();
  }, [startListeningLoop]);

  return {
    state,
    audioLevel,
    isMuted,
    activeProfile,
    contextState,
    capabilities,
    toggleMute,
    cancelActiveAction,
    manualDoneSpeaking,
    requestMicrophonePermission,
    selectProfile: handleSelectProfile,
    sendQuery: sendVoiceQuery,
  };
}
