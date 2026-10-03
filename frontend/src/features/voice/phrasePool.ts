/**
 * Phrase Pool for Voice Operational Progress & Acknowledgements
 *
 * Implements Section 9 of docs/NANVI_SPEC.md.
 * Ensures progress and acknowledgement lines never repeat identically back to back.
 */

export type PhraseCategory =
  | "KNOWLEDGE_SEARCH"
  | "SQL_QUERY"
  | "EMAIL_SEARCH"
  | "WEB_SEARCH"
  | "INTERMEDIATE_UPDATE"
  | "GENERAL_ACK";

const PHRASE_POOLS: Record<PhraseCategory, string[]> = {
  KNOWLEDGE_SEARCH: [
    "Sure, I'm checking that.",
    "One moment, finding those documents.",
    "Okay, let me look that up.",
    "Checking that now.",
  ],
  SQL_QUERY: [
    "Sure, give me a second.",
    "Okay, checking the records now.",
    "Let me look that up for you.",
    "One moment, pulling that up.",
  ],
  EMAIL_SEARCH: [
    "Sure, checking your messages now.",
    "One moment, looking through the emails.",
    "Checking that email now.",
    "Let me check your inbox.",
  ],
  WEB_SEARCH: [
    "One moment, checking online.",
    "Looking that up now.",
    "Sure, checking current information.",
  ],
  INTERMEDIATE_UPDATE: [
    "I found a few matches. Narrowing them down.",
    "Checking the details now.",
    "Pulling together the verified information.",
  ],
  GENERAL_ACK: [
    "Sure, give me a second.",
    "Okay, I'm checking that now.",
    "One moment, let me look that up.",
    "Looking that up for you.",
  ],
};

export class PhrasePool {
  private lastUsed: Map<PhraseCategory, string> = new Map();

  getPhrase(category: PhraseCategory = "GENERAL_ACK"): string {
    const pool = PHRASE_POOLS[category] || PHRASE_POOLS.GENERAL_ACK;
    const last = this.lastUsed.get(category);
    const candidates = pool.filter((p) => p !== last);
    const chosen = candidates[Math.floor(Math.random() * candidates.length)] || pool[0];
    this.lastUsed.set(category, chosen);
    return chosen;
  }

  detectCategoryFromQuery(query: string): PhraseCategory {
    const q = query.toLowerCase();
    if (q.includes("revenue") || q.includes("sales") || q.includes("invoice") || q.includes("customer") || q.includes("sql") || q.includes("database")) {
      return "SQL_QUERY";
    }
    if (q.includes("email") || q.includes("mail") || q.includes("message") || q.includes("inbox") || q.includes("thread")) {
      return "EMAIL_SEARCH";
    }
    if (q.includes("web") || q.includes("google") || q.includes("online") || q.includes("market") || q.includes("competitor")) {
      return "WEB_SEARCH";
    }
    if (q.includes("file") || q.includes("doc") || q.includes("handbook") || q.includes("policy") || q.includes("contract") || q.includes("pdf")) {
      return "KNOWLEDGE_SEARCH";
    }
    return "GENERAL_ACK";
  }
}

export const phrasePool = new PhrasePool();
