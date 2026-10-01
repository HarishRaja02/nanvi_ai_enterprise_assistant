import React, { useEffect, useState, useRef, useCallback } from "react";
import { X, Mic, AlertCircle, AlertTriangle, Sparkles, Volume2, Shield, ArrowUp, Activity, Settings2, Languages } from "lucide-react";
import { NanviNeuralCore } from "./NanviNeuralCore";
import { VoiceContextPanel } from "./VoiceContextPanel";
import { VoiceControls } from "./VoiceControls";
import { GlassProgressCard } from "./GlassProgressCard";
import { GlassUICard } from "./GlassUICard";
import { LiveCaptionBar } from "./LiveCaptionBar";
import { VoiceTelemetryModal } from "./VoiceTelemetryModal";
import { useVoiceSession } from "./useVoiceSession";
import { cleanDisplayText, speechSynthesisService } from "./speechSynthesisService";
import { speechRecognitionService } from "./speechRecognitionService";
import { earconService } from "./earconService";
import { isHighRiskIntent, getIntentMetadata, type FrontendIntentDef } from "./intentRegistry";
import type { NanviApiClient, UserIdentity } from "../../api";
import type { SourceView } from "../../lib/sources";

interface VoiceAssistantModeProps {
  api: NanviApiClient;
  identity: UserIdentity | null;
  conversationId?: string;
  ragEnabled?: boolean;
  onClose: () => void;
  onOpenSource: (source: SourceView) => void;
  onUpdateConversationId?: (id: string) => void;
  onAddChatMessage?: (userText: string, assistantReply: { text: string; sources?: any[] }) => void;
}

export const VoiceAssistantMode: React.FC<VoiceAssistantModeProps> = ({
  api,
  identity,
  conversationId,
  ragEnabled = true,
  onClose,
  onOpenSource,
  onUpdateConversationId,
  onAddChatMessage,
}) => {
  const [pendingConfirmation, setPendingConfirmation] = useState<{
    intentId: string;
    meta: FrontendIntentDef;
  } | null>(null);
  const [isTelemetryOpen, setIsTelemetryOpen] = useState(false);
  const [voiceSettingsOpen, setVoiceSettingsOpen] = useState(false);
  const voiceSettingsRef = useRef<HTMLDivElement>(null);

  const pendingConfirmationRef = useRef(pendingConfirmation);
  useEffect(() => {
    pendingConfirmationRef.current = pendingConfirmation;
  }, [pendingConfirmation]);

  const voiceSendQueryRef = useRef<((q: string) => Promise<void>) | null>(null);

  const handleInterceptQuery = useCallback((clean: string) => {
    const pending = pendingConfirmationRef.current;
    if (!pending) return false;

    const lower = clean.trim().toLowerCase();
    const isAffirmative = /\b(yes|confirm|proceed|go ahead|do it|sure|execute|confirm and proceed|send it)\b/i.test(lower);
    const isNegative = /\b(no|cancel|stop|abort|don't|do not|don't do it)\b/i.test(lower);

    if (isAffirmative) {
      const label = pending.meta.label;
      setPendingConfirmation(null);
      void voiceSendQueryRef.current?.(`Confirm and execute: ${label}`);
      return true;
    }

    if (isNegative) {
      setPendingConfirmation(null);
      earconService.playListening();
      return true;
    }

    return false;
  }, []);

  const voice = useVoiceSession({
    api,
    identity,
    conversationId,
    ragEnabled,
    onUpdateConversationId,
    onAddChatMessage,
    onInterceptQuery: handleInterceptQuery,
    isOpen: true,
  });

  voiceSendQueryRef.current = voice.sendQuery;

  const handleExit = useCallback(() => {
    speechRecognitionService.stopListening();
    speechSynthesisService.stop();
    onClose();
  }, [onClose]);

  useEffect(() => {
    if (!voiceSettingsOpen) return;
    const closeOnOutsidePointer = (event: PointerEvent) => {
      if (!voiceSettingsRef.current?.contains(event.target as Node)) {
        setVoiceSettingsOpen(false);
      }
    };
    document.addEventListener("pointerdown", closeOnOutsidePointer);
    return () => document.removeEventListener("pointerdown", closeOnOutsidePointer);
  }, [voiceSettingsOpen]);

  // Global keydown listener: Escape to exit, Enter to immediately finalize speech
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (voiceSettingsOpen) {
          e.preventDefault();
          setVoiceSettingsOpen(false);
          return;
        }
        handleExit();
      } else if (e.key === "Enter" && voice.state === "listening") {
        e.preventDefault();
        void voice.manualDoneSpeaking();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleExit, voice, voiceSettingsOpen]);

  // Derived state labels & status descriptions
  let stateLabel = "Listening...";
  let stateHint = "Speak naturally — Nanvi is listening";

  switch (voice.state) {
    case "idle":
      stateLabel = "Ready";
      stateHint = "Tap to speak or press Enter to begin";
      break;
    case "connecting":
      stateLabel = "Connecting...";
      stateHint = "Opening your protected realtime voice session";
      break;
    case "reconnecting":
      stateLabel = "Reconnecting...";
      stateHint = "Restoring the voice session";
      break;
    case "listening":
      if (voice.isFollowUpWindow) {
        stateLabel = `Follow-Up Window (${voice.followUpSecondsRemaining}s)`;
        stateHint = "Listening for follow-up... (e.g. 'Why?', 'Show more', 'Compare with last quarter')";
      } else {
        stateLabel = voice.audioLevel > 0.08 ? "Hearing Voice..." : "Listening...";
        stateHint =
          voice.audioLevel > 0.08 ? "Audio detected — speak your query" : "Speak naturally or press Enter when done";
      }
      break;
    case "processing":
      stateLabel = "Understanding...";
      stateHint = "Searching authorized files, databases & emails";
      break;
    case "speaking":
      stateLabel = "Nanvi is speaking...";
      stateHint = "Interrupt anytime — just speak";
      break;
    case "interrupted":
      stateLabel = "Listening to you...";
      stateHint = "Resuming new request";
      break;
    case "muted":
      stateLabel = "Microphone Muted";
      stateHint = "Click Unmute or press M to speak";
      break;
    case "error":
      stateLabel = "Notice";
      stateHint = voice.contextState.lastError || "Could not complete request";
      break;
  }

  // Clean transcription display — zero asterisks, zero raw markdown symbols
  const rawUserText = voice.contextState.interimTranscript || voice.contextState.currentQuery;
  const activeUserText = cleanDisplayText(rawUserText);
  const activeAssistantText = cleanDisplayText(voice.contextState.spokenAnswer);

  return (
    <div
      className="voice-assistant-overlay"
      role="dialog"
      aria-modal="true"
      aria-label="Nanvi Voice Assistant Workspace"
    >
      {/* Background radial ambient backdrop */}
      <div className="voice-ambient-backdrop" aria-hidden="true" />

      {/* Top Header Bar */}
      <header className="voice-topbar">
        <div className="voice-topbar-left">
          <div className="voice-brand-mark">
            <span className="voice-brand-pulse" aria-hidden="true" />
            <Sparkles size={16} className="text-primary-500" aria-hidden="true" />
          </div>
          <div className="voice-brand-titles">
            <h1 className="voice-brand-name">Nanvi Voice Assistant</h1>
            <span className="voice-brand-status">
              <Shield size={11} className="inline mr-1 text-emerald-600" />
              Enterprise Protected Session
            </span>
          </div>
        </div>

        <div className="voice-topbar-right flex items-center gap-2">
          <div className="voice-settings-wrap" ref={voiceSettingsRef}>
            <button
              type="button"
              className="voice-settings-trigger"
              aria-expanded={voiceSettingsOpen}
              aria-controls="voice-settings-panel"
              data-testid="voice-settings-toggle"
              onClick={() => setVoiceSettingsOpen((open) => !open)}
            >
              <Settings2 size={15} aria-hidden="true" />
              <span>Voice settings</span>
            </button>
            {voiceSettingsOpen && (
              <div id="voice-settings-panel" className="voice-settings-popover" aria-label="Voice settings">
                <div className="voice-settings-section" data-testid="voice-verbosity-selector">
                  <span className="voice-settings-label">Answer length</span>
                  <div className="voice-verbosity-options">
                    {(["concise", "normal", "detailed"] as const).map((value) => (
                      <button
                        key={value}
                        type="button"
                        aria-pressed={voice.verbosity === value}
                        className={`voice-setting-choice${voice.verbosity === value ? " is-selected" : ""}`}
                        onClick={() => voice.setVerbosity(value)}
                      >
                        {value}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="voice-settings-section">
                  <span className="voice-settings-label">Language</span>
                  <div className="voice-language-static" data-testid="voice-language-label">
                    <Languages size={14} aria-hidden="true" />
                    <strong>English only</strong>
                    <span>Voice input and replies</span>
                  </div>
                </div>

                <div className="voice-settings-section">
                  <span className="voice-settings-label">Privacy</span>
                  <button
                    type="button"
                    className="voice-setting-action"
                    aria-pressed={voice.privacyMode}
                    onClick={voice.togglePrivacyMode}
                    data-testid="voice-privacy-toggle"
                  >
                    <Shield size={14} aria-hidden="true" />
                    {voice.privacyMode ? "Privacy mode on" : "Privacy mode off"}
                  </button>
                </div>

                <button
                  type="button"
                  className="voice-setting-action"
                  onClick={() => {
                    setVoiceSettingsOpen(false);
                    setIsTelemetryOpen(true);
                  }}
                  data-testid="voice-telemetry-toggle"
                >
                  <Activity size={14} aria-hidden="true" />
                  Voice diagnostics
                </button>
              </div>
            )}
          </div>

          <button
            type="button"
            className="voice-exit-btn"
            onClick={handleExit}
            title="Exit Voice Mode (Escape)"
            aria-label="Exit Voice Assistant"
          >
            <span>Exit Voice</span>
            <X size={15} aria-hidden="true" />
          </button>
        </div>
      </header>

      {/* Main 3-Zone Workspace */}
      <div className="voice-workspace-grid">
        {/* Central Intelligence Zone */}
        <section className="voice-center-zone" aria-label="Voice Interaction Area">
          <div className="voice-center-content">
            {/* Visualizer Container */}
            <div className="voice-visualizer-container">
              <NanviNeuralCore state={voice.state} audioLevel={voice.audioLevel} size={340} />
            </div>

            {/* Status & State Feedback */}
            <div className="voice-status-block">
              <div className={`voice-state-pill is-${voice.state}`}>
                {voice.state === "listening" && <span className="voice-pill-dot" aria-hidden="true" />}
                {voice.state === "speaking" && <Volume2 size={13} className="text-primary-600 animate-pulse" />}
                {voice.state === "muted" && <span className="voice-pill-dot is-muted" aria-hidden="true" />}
                {voice.state === "error" && <AlertCircle size={13} className="text-danger-fg" />}
                <span className="voice-state-text">{stateLabel}</span>
              </div>

              {/* Dynamic VU Meter Equalizer Bars (visual feedback that mic is active) */}
              {voice.state === "listening" && (
                <div className="voice-audio-bars" aria-label="Microphone volume meter" title={`Mic volume: ${Math.round(voice.audioLevel * 100)}%`}>
                  {[0.7, 1.1, 1.6, 1.1, 0.7].map((mult, idx) => {
                    const h = Math.max(4, Math.min(22, voice.audioLevel * 28 * mult));
                    return (
                      <span
                        key={idx}
                        className={`voice-audio-bar ${voice.audioLevel > 0.08 ? "is-active" : ""}`}
                        style={{ height: `${h}px` }}
                        aria-hidden="true"
                      />
                    );
                  })}
                </div>
              )}

              <p className="voice-state-hint">{stateHint}</p>

              {/* Quick Done Speaking action button */}
              {voice.state === "listening" && (
                <button
                  type="button"
                  className="voice-done-speaking-btn"
                  onClick={() => void voice.manualDoneSpeaking()}
                  title="Click when done speaking (or press Enter)"
                >
                  <ArrowUp size={13} aria-hidden="true" />
                  <span>Done Speaking (Send ↵)</span>
                </button>
              )}

              {/* Tap to Speak button when session is idle or recovering from an error */}
              {(voice.state === "idle" || voice.state === "error") && (
                <button
                  type="button"
                  className="voice-done-speaking-btn"
                  onClick={() => void voice.startListening()}
                  title="Click to resume speaking"
                >
                  <Mic size={13} aria-hidden="true" />
                  <span>Tap to Speak</span>
                </button>
              )}
            </div>

            {/* Operational Progress Glass Card (driven by real operational state) */}
            {voice.state === "processing" && (
              <GlassProgressCard
                stage={voice.contextState.progressStage || "Processing request..."}
                detail="Searching authorized records & verifying RBAC permissions"
                elapsedSeconds={voice.contextState.progressElapsed || 0}
                sourcesFound={voice.contextState.sources.length}
              />
            )}

            {/* Subtle Live Transcript Box (Non-intrusive enterprise design) */}
            <div className="voice-transcript-wrapper" aria-live="polite">
              {activeUserText ? (
                <div className="voice-transcript-bubble is-user">
                  <span className="voice-transcript-speaker">You</span>
                  <p className="voice-transcript-body">“{activeUserText}”</p>
                </div>
              ) : null}

              {voice.state === "speaking" && activeAssistantText ? (
                <div className="voice-transcript-bubble is-assistant">
                  <span className="voice-transcript-speaker">Nanvi</span>
                  <p className="voice-transcript-body">“{activeAssistantText}”</p>
                </div>
              ) : null}
            </div>

            {/* Live Synchronized Spoken Caption Bar (Milestone 8) */}
            <LiveCaptionBar
              spokenText={voice.contextState.spokenAnswer}
              isSpeaking={voice.state === "speaking"}
              className="my-3 max-w-xl mx-auto"
            />

            {/* Dynamic Generative UI Glass Cards (Milestone 5 Controlled DSL) */}
            {voice.contextState.uiSpecs && voice.contextState.uiSpecs.length > 0 && voice.state !== "processing" && (
              <div className="voice-ui-specs-grid" data-testid="voice-ui-specs-container">
                {voice.contextState.uiSpecs.map((spec, sIdx) => {
                  const isHighlighted = Boolean(
                    voice.contextState.activeHighlight &&
                      (JSON.stringify(spec.data).includes(voice.contextState.activeHighlight) || sIdx === 0)
                  );
                  return (
                    <GlassUICard
                      key={sIdx}
                      spec={spec}
                      isHighlighted={isHighlighted}
                      onActionClick={(intent) => {
                        if (isHighRiskIntent(intent)) {
                          setPendingConfirmation({
                            intentId: intent,
                            meta: getIntentMetadata(intent),
                          });
                        } else {
                          const meta = getIntentMetadata(intent);
                          void voice.sendQuery(meta.label);
                        }
                      }}
                    />
                  );
                })}
              </div>
            )}

            {/* Error banner if permission or audio issue */}
            {voice.contextState.lastError && (
              <div className="voice-error-toast" role="alert">
                <AlertCircle size={15} aria-hidden="true" />
                <span>{voice.contextState.lastError}</span>
                <button
                  type="button"
                  className="voice-retry-mic-btn"
                  onClick={() => {
                    if (voice.contextState.lastError?.toLowerCase().includes("mic")) {
                      void voice.requestMicrophonePermission();
                    } else {
                      void voice.startListening();
                    }
                  }}
                >
                  {voice.contextState.lastError?.toLowerCase().includes("mic") ? "Enable Microphone" : "Tap to Speak"}
                </button>
              </div>
            )}
          </div>

          {/* Bottom Voice Controls */}
          <div className="voice-bottom-controls-wrap">
            <VoiceControls
              state={voice.state}
              isMuted={voice.isMuted}
              activeProfile={voice.activeProfile}
              onToggleMute={voice.toggleMute}
              onCancel={voice.cancelActiveAction}
              onSelectProfile={voice.selectProfile}
            />
          </div>
        </section>

        {/* Right Voice Context Panel */}
        <VoiceContextPanel
          importantPoints={voice.contextState.importantPoints}
          sources={voice.contextState.sources}
          capabilities={voice.capabilities}
          onOpenSource={onOpenSource}
        />
      </div>

      {/* High-Risk Action Confirmation Dialog (Milestone 6 / Section 12) */}
      {pendingConfirmation && (
        <div
          className="fixed inset-0 z-[110] flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-md"
          role="alertdialog"
          aria-labelledby="confirm-dialog-title"
          aria-describedby="confirm-dialog-desc"
          data-testid="high-risk-confirmation-modal"
        >
          <div className="w-full max-w-md rounded-2xl border border-amber-500/30 bg-slate-900/95 p-6 shadow-2xl backdrop-blur-xl">
            <div className="flex items-center gap-3 mb-3 text-amber-400">
              <AlertTriangle className="w-6 h-6 shrink-0" />
              <h2 id="confirm-dialog-title" className="text-base font-bold text-slate-100">
                Action Requires Confirmation
              </h2>
            </div>
            <p id="confirm-dialog-desc" className="text-xs text-slate-300 mb-3 leading-relaxed">
              You are about to execute <strong className="text-white">“{pendingConfirmation.meta.label}”</strong>.
              {" "}{pendingConfirmation.meta.description}
            </p>
            <div className="flex items-center gap-2 mb-4 text-[11px] text-amber-300/90 bg-amber-500/10 border border-amber-500/20 px-3 py-2 rounded-xl">
              <Sparkles size={13} className="shrink-0 text-amber-400" />
              <span>Say <strong className="text-amber-200">“Confirm”</strong> or <strong className="text-amber-200">“Cancel”</strong>, or click the buttons below.</span>
            </div>
            <div className="flex items-center justify-end gap-3 pt-3 border-t border-white/10">
              <button
                type="button"
                className="px-4 py-2 text-xs font-semibold rounded-xl text-slate-300 hover:bg-white/10 transition-colors"
                onClick={() => setPendingConfirmation(null)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="px-4 py-2 text-xs font-semibold rounded-xl bg-gradient-to-r from-[#006583] to-[#005166] text-white shadow-lg shadow-[#006583]/20 hover:shadow-[#006583]/40 transition-all hover:-translate-y-0.5"
                onClick={() => {
                  const label = pendingConfirmation.meta.label;
                  setPendingConfirmation(null);
                  void voice.sendQuery(`Confirm and execute: ${label}`);
                }}
              >
                Confirm & Proceed
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Voice Telemetry & Observability Modal (Milestone 11) */}
      <VoiceTelemetryModal
        api={api}
        isOpen={isTelemetryOpen}
        onClose={() => setIsTelemetryOpen(false)}
      />
    </div>
  );
};
