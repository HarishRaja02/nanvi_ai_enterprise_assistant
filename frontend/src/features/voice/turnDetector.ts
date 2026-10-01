/**
 * Nanvi Voice — Turn Detection & Semantic Completeness Engine
 *
 * Implements Section 7.4 (Smart End-of-Turn Detection), Section 7.5 (Follow-Up Window),
 * and Section 7.6 (Self-Repair & Correction Resolution) of NANVI_SPEC.md.
 */

export type TurnCompletenessStatus = "complete" | "incomplete" | "hesitation_only";

export interface TurnCompletenessResult {
  status: TurnCompletenessStatus;
  reason?: string;
  recommendedWaitMs: number;
}

export const TURN_TIMEOUTS = {
  /** Snappy timeout for complete sentences with terminal punctuation or complete clauses */
  SNAPPY_COMPLETE: 1200,
  /** Standard silence timeout for normal speech phrases */
  STANDARD_PAUSE: 1700,
  /** Extended wait time when speech ends on trailing conjunctions, prepositions, or hesitation */
  EXTENDED_INCOMPLETE: 2800,
  /** Silence timeout when only hesitation sounds have been uttered */
  HESITATION_ONLY: 3500,
  /** Post-speech continuous listening window without requiring wake word */
  FOLLOW_UP_WINDOW_MS: 8000,
};

// Hesitation words & vocal fillers
const HESITATION_REGEX = /^(?:um+|uh+|er+|ah+|hmm+|mm+|like|you know)$/i;

const TRAILING_HESITATION_REGEX = /\b(?:um+|uh+|er+|ah+|hmm+|mm+|like|you know)\s*[.…—\-]*$/i;

// Trailing coordinating & subordinating conjunctions
const TRAILING_CONJUNCTIONS_REGEX = /\b(?:and|or|but|so|because|since|although|while|if|unless|yet|as|whereas)\s*[.…—\-]*$/i;

// Trailing prepositions & connectives
const TRAILING_PREPOSITIONS_REGEX = /\b(?:for|to|with|in|on|at|about|from|into|by|of|under|over|through|between|against|during|before|after|without|within)\s*[.…—\-]*$/i;

// Trailing determiners & articles
const TRAILING_DETERMINERS_REGEX = /\b(?:the|a|an|this|that|these|those|my|our|their|his|her|its)\s*[.…—\-]*$/i;

// Trailing auxiliary & linking verbs
const TRAILING_VERBS_REGEX = /\b(?:is|are|was|were|be|been|being|have|has|had|do|does|did|can|could|will|would|shall|should|may|might|must)\s*[.…—\-]*$/i;

// Trailing relative / interrogative pronouns leading into an incomplete clause
const TRAILING_RELATIVE_REGEX = /\b(?:which|whose|who|whom|where|when|why|how|what)\s*[.…—\-]*$/i;

// Trailing ellipsis or dashes indicating an interrupted train of thought
const TRAILING_SUSPENSION_REGEX = /(?:\.{2,}|…|—|-)\s*$/;

/**
 * Evaluates semantic completeness of transcribed speech.
 * Determines whether Nanvi should fire immediately or wait for the user to complete their thought.
 */
export function analyzeCompleteness(transcript: string): TurnCompletenessResult {
  const clean = transcript.trim();
  if (!clean) {
    return {
      status: "incomplete",
      reason: "empty_transcript",
      recommendedWaitMs: TURN_TIMEOUTS.STANDARD_PAUSE,
    };
  }

  // 1. Check if the entire transcript is merely vocal filler/hesitation
  const tokens = clean.toLowerCase().replace(/[.,!?;:…—\-]/g, " ").split(/\s+/).filter(Boolean);
  const isOnlyHesitation = tokens.length > 0 && tokens.every((tok) => HESITATION_REGEX.test(tok));
  if (isOnlyHesitation) {
    return {
      status: "hesitation_only",
      reason: "hesitation_only",
      recommendedWaitMs: TURN_TIMEOUTS.HESITATION_ONLY,
    };
  }

  // 2. Check for trailing hesitation markers (e.g. "Show me revenue for... um...")
  if (TRAILING_HESITATION_REGEX.test(clean)) {
    return {
      status: "incomplete",
      reason: "trailing_hesitation",
      recommendedWaitMs: TURN_TIMEOUTS.EXTENDED_INCOMPLETE,
    };
  }

  // 3. Check for trailing ellipses or em-dashes
  if (TRAILING_SUSPENSION_REGEX.test(clean)) {
    return {
      status: "incomplete",
      reason: "trailing_suspension",
      recommendedWaitMs: TURN_TIMEOUTS.EXTENDED_INCOMPLETE,
    };
  }

  // 4. Check for trailing conjunctions (e.g. "Show expenses and...")
  if (TRAILING_CONJUNCTIONS_REGEX.test(clean)) {
    return {
      status: "incomplete",
      reason: "trailing_conjunction",
      recommendedWaitMs: TURN_TIMEOUTS.EXTENDED_INCOMPLETE,
    };
  }

  // 5. Check for trailing prepositions (e.g. "What about invoices for...")
  if (TRAILING_PREPOSITIONS_REGEX.test(clean)) {
    return {
      status: "incomplete",
      reason: "trailing_preposition",
      recommendedWaitMs: TURN_TIMEOUTS.EXTENDED_INCOMPLETE,
    };
  }

  // 6. Check for trailing determiners/articles (e.g. "Check the...")
  if (TRAILING_DETERMINERS_REGEX.test(clean)) {
    return {
      status: "incomplete",
      reason: "trailing_determiner",
      recommendedWaitMs: TURN_TIMEOUTS.EXTENDED_INCOMPLETE,
    };
  }

  // 7. Check for trailing auxiliary verbs (e.g. "The active customer is...")
  if (TRAILING_VERBS_REGEX.test(clean)) {
    return {
      status: "incomplete",
      reason: "trailing_verb",
      recommendedWaitMs: TURN_TIMEOUTS.EXTENDED_INCOMPLETE,
    };
  }

  // 8. Check for trailing relative / interrogatives with no predicate (e.g. "Tell me why...")
  // Only flags if not a standalone single-word follow-up question like "Why?" or "What?"
  if (tokens.length > 1 && TRAILING_RELATIVE_REGEX.test(clean)) {
    return {
      status: "incomplete",
      reason: "trailing_relative",
      recommendedWaitMs: TURN_TIMEOUTS.EXTENDED_INCOMPLETE,
    };
  }

  // 9. Check for terminal punctuation indicating complete thoughts
  const hasTerminalPunctuation = /[.!?]$/.test(clean);
  if (hasTerminalPunctuation) {
    return {
      status: "complete",
      reason: "terminal_punctuation",
      recommendedWaitMs: TURN_TIMEOUTS.SNAPPY_COMPLETE,
    };
  }

  // 10. Standalone elliptical follow-ups ("Why?", "How come?", "Only enterprise", "Open that", "Show more")
  if (tokens.length <= 4) {
    return {
      status: "complete",
      reason: "concise_phrase",
      recommendedWaitMs: TURN_TIMEOUTS.SNAPPY_COMPLETE,
    };
  }

  // Default to complete with standard pause
  return {
    status: "complete",
    reason: "standard_complete",
    recommendedWaitMs: TURN_TIMEOUTS.STANDARD_PAUSE,
  };
}

/**
 * Resolves conversational self-repairs in user speech.
 * Example:
 *   "Show August... no, I meant September" -> "Show September"
 *   "Revenue for 2023, sorry, 2024" -> "Revenue for 2024"
 *   "List marketing employees, actually, engineering" -> "List engineering employees"
 *   "Delete draft, scratch that, send email" -> "send email"
 */
export function resolveSelfRepair(transcript: string): string {
  if (!transcript || !transcript.trim()) return "";
  let text = transcript.trim();

  // Pattern A: "scratch that, <new command>" or "cancel that, <new command>"
  const scratchMatch = text.match(/(?:scratch that|cancel that|forget that)[,\s]+(.+)$/i);
  if (scratchMatch && scratchMatch[1]) {
    return scratchMatch[1].trim();
  }

  // Pattern B: "<prefix>... no/sorry, I meant <correction>" or "no I mean <correction>"
  const meantMatch = text.match(/^(.*?)(?:[.,;—\- ]+)(?:no|sorry|wait)[,\s]+(?:I meant|I mean|make that)\s+(.+)$/i);
  if (meantMatch) {
    const prefix = meantMatch[1].trim();
    const correction = meantMatch[2].trim();

    if (!prefix) return correction;

    // If correction has multiple words with a verb, it replaces the entire statement
    const correctionTokens = correction.split(/\s+/);
    if (correctionTokens.length >= 3 && /^(?:show|find|list|what|get|open|create|send)/i.test(correction)) {
      return correction;
    }

    // Replace the last entity/token of the prefix with the correction
    // e.g. "Show August" with correction "September" -> "Show September"
    const prefixTokens = prefix.split(/\s+/);
    if (prefixTokens.length > 0) {
      prefixTokens[prefixTokens.length - 1] = correction;
      return prefixTokens.join(" ");
    }
    return `${prefix} ${correction}`;
  }

  // Pattern C: "<prefix>, actually, <correction>" (requires punctuation like comma, dash, ellipsis, or explicit 'no/wait')
  const actuallyMatch = text.match(/^(.*?)(?:[.,;—\-]+|\b(?:no|wait)\b)[,\s]*(?:actually|no wait|wait no)[,\s]+(.+)$/i);
  if (actuallyMatch) {
    const prefix = actuallyMatch[1].trim();
    const correction = actuallyMatch[2].trim();

    if (!prefix) return correction;

    const correctionTokens = correction.split(/\s+/);
    if (correctionTokens.length >= 3 && /^(?:show|find|list|what|get|open|create|send)/i.test(correction)) {
      return correction;
    }

    const prefixTokens = prefix.split(/\s+/);
    if (prefixTokens.length > 0) {
      prefixTokens[prefixTokens.length - 1] = correction;
      return prefixTokens.join(" ");
    }
    return `${prefix} ${correction}`;
  }

  // Pattern D: "<prefix>, sorry, <single token>" e.g. "Revenue for 2023, sorry, 2024"
  const sorryMatch = text.match(/^(.*?)(?:[.,;—\-]+|\bwait\b)[,\s]*(?:sorry)[,\s]+([a-z0-9]+)$/i);
  if (sorryMatch) {
    const prefix = sorryMatch[1].trim();
    const correction = sorryMatch[2].trim();
    const prefixTokens = prefix.split(/\s+/);
    if (prefixTokens.length > 0) {
      prefixTokens[prefixTokens.length - 1] = correction;
      return prefixTokens.join(" ");
    }
  }

  return text;
}
