import type { SourceView } from "../../lib/sources";

export type VoiceState =
  | "idle"
  | "connecting"
  | "reconnecting"
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

export type UICardType =
  | "kpi_card"
  | "table_card"
  | "source_list"
  | "timeline_card"
  | "status_card"
  | "action_card";

export interface KPICardData {
  metric_label: string;
  value: string;
  unit?: string;
  trend?: "up" | "down" | "flat" | "";
  trend_value?: string;
  comparison_label?: string;
}

export interface TableColumn {
  key: string;
  label: string;
  align?: "left" | "right" | "center";
}

export interface TableCardData {
  title?: string;
  columns: TableColumn[];
  rows: Record<string, any>[];
  total_rows?: number;
  truncated?: boolean;
}

export interface SourceItem {
  title: string;
  reference_id?: string;
  file_type?: string;
  relevance_score?: number;
  snippet?: string;
}

export interface SourceListData {
  sources: SourceItem[];
  query_context?: string;
}

export interface TimelineItem {
  timestamp: string;
  title: string;
  detail?: string;
  icon?: string;
}

export interface TimelineCardData {
  title?: string;
  items: TimelineItem[];
}

export interface StatusCardData {
  status: "success" | "warning" | "error" | "info" | "pending";
  title: string;
  detail?: string;
  icon?: string;
}

export interface ActionItem {
  label: string;
  intent: string;
  icon?: string;
  variant?: "primary" | "secondary" | "ghost";
}

export interface ActionCardData {
  title?: string;
  actions: ActionItem[];
}

export interface UISpec {
  card_type: UICardType;
  priority?: number;
  data: Record<string, any>;
}

export interface VoiceTurn {
  id: string;
  userText: string;
  spokenText: string;
  fullAnswer: string;
  sources: SourceView[];
  importantPoints: string[];
  timestamp: number;
  uiSpecs?: UISpec[];
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
  isFollowUpWindow?: boolean;
  followUpSecondsRemaining?: number;
  progressStage?: string | null;
  progressElapsed?: number;
  uiSpecs?: UISpec[];
  highlights?: string[];
  activeHighlight?: string | null;
}
