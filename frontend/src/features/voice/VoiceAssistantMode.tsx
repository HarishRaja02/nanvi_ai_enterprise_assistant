import React, { useEffect } from "react";
import { X, Mic, AlertCircle, Sparkles, Volume2, Shield, ArrowUp } from "lucide-react";
import { NanviNeuralCore } from "./NanviNeuralCore";
import { VoiceContextPanel } from "./VoiceContextPanel";
import { VoiceControls } from "./VoiceControls";
import { useVoiceSession } from "./useVoiceSession";
import { cleanDisplayText, speechSynthesisService } from "./speechSynthesisService";
import { speechRecognitionService } from "./speechRecognitionService";
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
  const voice = useVoiceSession({
    api,
    identity,
    conversationId,
    ragEnabled,
    onUpdateConversationId,
    onAddChatMessage,
    isOpen: true,
  });

  const handleExit = () => {
    speechRecognitionService.stopListening();
    speechSynthesisService.stop();
    onClose();
  };

  // Global keydown listener: Escape to exit, Enter to immediately finalize speech
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        handleExit();
      } else if (e.key === "Enter" && voice.state === "listening") {
        e.preventDefault();
        void voice.manualDoneSpeaking();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose, voice]);

  // Derived state labels & status descriptions
  let stateLabel = "Listening...";
  let stateHint = "Speak naturally — Nanvi is listening";

  switch (voice.state) {
    case "idle":
      stateLabel = "Ready";
      stateHint = "Say something to begin";
      break;
    case "listening":
      stateLabel = voice.audioLevel > 0.08 ? "Hearing Voice..." : "Listening...";
      stateHint = voice.audioLevel > 0.08 ? "Audio detected — speak your query" : "Speak naturally or press Enter when done";
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

        <div className="voice-topbar-right">
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
            </div>

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

            {/* Error banner if permission or audio issue */}
            {voice.contextState.lastError && (
              <div className="voice-error-toast" role="alert">
                <AlertCircle size={15} aria-hidden="true" />
                <span>{voice.contextState.lastError}</span>
                <button
                  type="button"
                  className="voice-retry-mic-btn"
                  onClick={() => void voice.requestMicrophonePermission()}
                >
                  Enable Microphone
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
    </div>
  );
};
