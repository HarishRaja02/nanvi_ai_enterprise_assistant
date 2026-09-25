import type { ConversationSummary } from "../types";

export function initials(name: string): string {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join("").toUpperCase() || "U";
}

export function formatTime(ms: number): string {
  return new Date(ms).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export function formatDate(value?: string): string {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function formatDateTime(value?: string): string {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleString();
}

export function conversationTitle(c: Pick<ConversationSummary, "conversation_id" | "title">): string {
  return c.title?.trim() || `Conversation ${c.conversation_id.slice(0, 8)}`;
}

/** "database_query" → "Database query", "knowledge" → "RAG Retrieval". */
export function humanize(value: string): string {
  const norm = value.toLowerCase().trim();
  if (norm === "knowledge") return "RAG Retrieval";
  if (norm === "knowledge_search") return "RAG Search";
  if (norm === "rag") return "RAG Retrieval";
  const spaced = value.replace(/[_-]+/g, " ").trim();
  return spaced ? spaced[0].toUpperCase() + spaced.slice(1) : "";
}

export type ConversationGroup = { label: string; items: ConversationSummary[] };

/** Group by recency using the backend's updated_at. Undated items fall into "Earlier". */
export function groupByRecency(items: ConversationSummary[], now: Date = new Date()): ConversationGroup[] {
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const DAY = 86_400_000;
  const buckets: ConversationGroup[] = [
    { label: "Today", items: [] },
    { label: "Previous 7 days", items: [] },
    { label: "Earlier", items: [] },
  ];
  const stamp = (c: ConversationSummary) => (c.updated_at ? new Date(c.updated_at).getTime() : NaN);
  const sorted = [...items].sort((a, b) => (Number.isNaN(stamp(b)) ? -Infinity : stamp(b)) - (Number.isNaN(stamp(a)) ? -Infinity : stamp(a)));
  for (const c of sorted) {
    const t = stamp(c);
    if (Number.isNaN(t)) buckets[2].items.push(c);
    else if (t >= startOfToday) buckets[0].items.push(c);
    else if (t >= startOfToday - 6 * DAY) buckets[1].items.push(c);
    else buckets[2].items.push(c);
  }
  return buckets.filter((b) => b.items.length > 0);
}
