import type { SourceView } from "./lib/sources";

export type FileResultItem = {
  name: string;
  path: string;
  type?: string;
  open_url?: string;
  modified_at?: string;
  source?: string;
};

export type Message = {
  id: string;
  role: "user" | "assistant";
  text: string;
  createdAt: number;
  sources?: SourceView[];
  /** Ordered steps reported by the backend for this answer (ChatResponse.trace). */
  trace?: string[];
  /** Backend-reported capability that handled the request (ChatResponse.capability). */
  capability?: string;
  reportId?: string | null;
  dataSource?: "live" | "synthetic" | string;
  error?: boolean;
  retryAfter?: number;
  sourceSelectionRequired?: boolean;
  pendingSearchQuery?: string;
  fileResults?: FileResultItem[];
};

export type ConversationSummary = { conversation_id: string; title?: string | null; updated_at?: string };

/** A conversation picked from history. The API exposes no message-fetch endpoint, so its earlier turns can't be shown. */
export type ResumedConversation = { id: string; title: string };
