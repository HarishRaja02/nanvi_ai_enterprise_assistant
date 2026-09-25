import React, { useState, useRef, useEffect } from "react";
import { Mic, MicOff, Square, Volume2, ChevronDown, Check } from "lucide-react";
import { VoiceProfile, VoiceProfileId, VOICE_PROFILES, VoiceState } from "./voiceTypes";

interface VoiceControlsProps {
  state: VoiceState;
  isMuted: boolean;
  activeProfile: VoiceProfile;
  onToggleMute: () => void;
  onCancel: () => void;
  onSelectProfile: (profile: VoiceProfile) => void;
  className?: string;
}

export const VoiceControls: React.FC<VoiceControlsProps> = ({
  state,
  isMuted,
  activeProfile,
  onToggleMute,
  onCancel,
  onSelectProfile,
  className = "",
}) => {
  const [selectorOpen, setSelectorOpen] = useState(false);
  const selectorRef = useRef<HTMLDivElement>(null);

  // Close voice selector when clicking outside
  useEffect(() => {
    const handlePointerDown = (e: MouseEvent) => {
      if (selectorRef.current && !selectorRef.current.contains(e.target as Node)) {
        setSelectorOpen(false);
      }
    };
    if (selectorOpen) {
      document.addEventListener("mousedown", handlePointerDown);
    }
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
    };
  }, [selectorOpen]);

  // Keyboard shortcut listener (M to mute, Space to toggle speech if wanted)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (e.key === "m" || e.key === "M") {
        e.preventDefault();
        onToggleMute();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onToggleMute]);

  const canCancel = state === "speaking" || state === "processing" || state === "listening";

  return (
    <div className={`voice-controls-dock ${className}`} role="toolbar" aria-label="Voice Controls">
      <div className="voice-controls-inner">
        {/* Mute Button */}
        <button
          type="button"
          className={`voice-ctrl-btn ${isMuted ? "is-muted" : "is-active"}`}
          onClick={onToggleMute}
          title={isMuted ? "Unmute microphone (Press M)" : "Mute microphone (Press M)"}
          aria-label={isMuted ? "Unmute microphone" : "Mute microphone"}
          aria-pressed={isMuted}
        >
          <div className="voice-ctrl-icon-wrap">
            {isMuted ? <MicOff size={19} aria-hidden="true" /> : <Mic size={19} aria-hidden="true" />}
          </div>
          <span className="voice-ctrl-label">{isMuted ? "Unmute" : "Mute"}</span>
        </button>

        {/* Center Cancel Action */}
        <button
          type="button"
          className={`voice-ctrl-btn voice-cancel-btn ${canCancel ? "is-enabled" : "is-disabled"}`}
          onClick={onCancel}
          disabled={!canCancel}
          title="Stop speaking or cancel processing"
          aria-label="Cancel active action"
        >
          <div className="voice-ctrl-icon-wrap">
            <Square size={16} className="fill-current" aria-hidden="true" />
          </div>
          <span className="voice-ctrl-label">Cancel</span>
        </button>

        {/* Voice Profile Selector */}
        <div className="voice-selector-container" ref={selectorRef}>
          <button
            type="button"
            className="voice-ctrl-btn voice-selector-trigger"
            onClick={() => setSelectorOpen((prev) => !prev)}
            title="Choose Nanvi voice personality"
            aria-haspopup="listbox"
            aria-expanded={selectorOpen}
            aria-label={`Voice: ${activeProfile.name}`}
          >
            <div className="voice-ctrl-icon-wrap">
              <Volume2 size={18} aria-hidden="true" />
            </div>
            <div className="voice-selector-text">
              <span className="voice-selector-name">{activeProfile.name}</span>
            </div>
            <ChevronDown
              size={14}
              className={`voice-selector-chevron ${selectorOpen ? "is-open" : ""}`}
              aria-hidden="true"
            />
          </button>

          {selectorOpen && (
            <div className="voice-selector-popover" role="listbox" aria-label="Available Voices">
              <div className="voice-selector-head">Voice Personality</div>
              <ul className="voice-profile-list">
                {VOICE_PROFILES.map((profile) => {
                  const isSelected = profile.id === activeProfile.id;
                  return (
                    <li key={profile.id} role="option" aria-selected={isSelected}>
                      <button
                        type="button"
                        className={`voice-profile-option ${isSelected ? "is-selected" : ""}`}
                        onClick={() => {
                          onSelectProfile(profile);
                          setSelectorOpen(false);
                        }}
                      >
                        <div className="voice-profile-info">
                          <span className="voice-profile-title">{profile.name}</span>
                          <span className="voice-profile-desc">{profile.description}</span>
                        </div>
                        {isSelected && <Check size={14} className="text-primary-600" aria-hidden="true" />}
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
