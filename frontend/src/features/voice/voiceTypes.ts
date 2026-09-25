import type { SourceView } from "../../lib/sources";

export type VoiceState =
  | "idle"
  | "listening"
  | "processing"
  | "speaking"
  | "interrupted"
  | "muted"
  | "error";

export type VoiceProfileId = "nanvi-pro" | "nanvi-warm" | "nanvi-clear" | "nanvi-concise";

export interface VoiceProfile {
  id: VoiceProfileId;
  name: string;
  description: string;
  rate: number;
  pitch: number;
}

export const VOICE_PROFILES: VoiceProfile[] = [
  {
    id: "nanvi-pro",
    name: "Nanvi Professional",
    description: "Balanced, articulate human delivery",
    rate: 0.98,
    pitch: 1.0,
  },
  {
    id: "nanvi-warm",
    name: "Nanvi Warm",
    description: "Approachable, conversational warmth",
    rate: 0.96,
    pitch: 1.02,
  },
  {
    id: "nanvi-clear",
    name: "Nanvi Clear",
    description: "Crisp enunciation & articulate clarity",
    rate: 1.0,
    pitch: 1.03,
  },
  {
    id: "nanvi-concise",
    name: "Nanvi Concise",
    description: "Efficient, fluent briefing",
    rate: 1.05,
    pitch: 1.0,
  },
];

export interface VoiceTurn {
  id: string;
  userText: string;
  spokenText: string;
  fullAnswer: string;
  sources: SourceView[];
  importantPoints: string[];
  timestamp: number;
}

export interface VoiceContextState {
  currentQuery: string;
  interimTranscript: string;
  spokenAnswer: string;
  fullAnswer: string;
  importantPoints: string[];
  sources: SourceView[];
  recentTurns: VoiceTurn[];
  lastError: string | null;
}
