import type { NanviApiClient } from "../../api";
import { formatSpokenNumbers } from "./spokenNumbers";
import { VoiceProfile, VoiceProfileId } from "./voiceTypes";

/**
 * Neural TTS timeout: allow adequate time (~3.5s) for neural voice synthesis to complete
 * over the network. Only fall back to browser speech if the backend or connection is offline.
 */
const NEURAL_TTS_TIMEOUT_MS = 3500;

/**
 * Maximum spoken sentence count for voice delivery.
 * Longer responses are summarized for speech; full content stays in the UI.
 */
const MAX_SPOKEN_SENTENCES = 8;

export type SpeechEvents = {
  onStart?: () => void;
  onEnd?: () => void;
  onError?: (err: string) => void;
  onAmplitude?: (level: number) => void;
  onFirstAudio?: (latencyMs: number) => void;
};

/**
 * Strips all markdown formatting, code blocks, tables, citation tags, emojis,
 * raw URLs, and symbols, producing pure natural conversational text for speech.
 *
 * This is the core "speech preparation" step that sits between the raw response
 * and the speech normalization layer.
 */
export function cleanSpokenText(text: string): string {
  if (!text || !text.trim()) return "";

  let clean = text.trim();

  // 1. Remove markdown code blocks and inline code
  clean = clean.replace(/```[\s\S]*?```/g, " ");
  clean = clean.replace(/`([^`]+)`/g, "$1");

  // 2. Remove markdown tables (| col | col | ...)
  clean = clean.replace(/(\|.*\|\r?\n?)+/g, " ");

  // 3. Remove citation tags like [1], [ref-1], [Source 2], [file.pdf]
  clean = clean.replace(/\[(?:ref|source|\d+|file|doc)[^\]]*\]/gi, "");
  // Markdown links [label](url) -> label
  clean = clean.replace(/\[([^\]]+)\]\([^\)]+\)/g, "$1");
  // Remove standalone URLs
  clean = clean.replace(/https?:\/\/\S+/g, "");

  // 4. Remove headings (#, ##, ###)
  clean = clean.replace(/^#{1,6}\s*/gm, "");

  // 5. Run the full speech normalization layer (numbers, IDs, dates, currencies, acronyms)
  clean = formatSpokenNumbers(clean);

  // 6. Conversational expansions for natural human delivery
  clean = clean.replace(/\be\.g\b\.?,?\s*/gi, "for example, ");
  clean = clean.replace(/\bi\.e\b\.?,?\s*/gi, "that is, ");
  clean = clean.replace(/\betc\b\.?/gi, "and so forth");
  clean = clean.replace(/\bvs\b\.?\s*/gi, "versus ");
  clean = clean.replace(/&/g, " and ");

  // 7. Strip ALL formatting symbols: asterisks, hashes, underscores, tildes, backticks, pipes, angle brackets, curly braces, carets, backslashes
  clean = clean.replace(/[*#_~`|<>{}\\\/^]/g, " ");

  // 8. Remove bullet points (- item, • item, + item, 1. item) from start of lines
  clean = clean.replace(/^[\s\-•◦▪▫+*]+\s*/gm, "");
  clean = clean.replace(/^\s*\d+[\.)\]]\s*/gm, "");

  // 9. Strip emojis
  clean = clean.replace(/[\u{1F600}-\u{1F64F}\u{1F300}-\u{1F5FF}\u{1F680}-\u{1F6FF}\u{1F700}-\u{1F77F}\u{1F780}-\u{1F7FF}\u{1F800}-\u{1F8FF}\u{1F900}-\u{1F9FF}\u{1FA00}-\u{1FA6F}\u{1FA70}-\u{1FAFF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}]/gu, "");

  // 10. Turn colons and semicolons into natural breath pauses, clean dashes
  clean = clean.replace(/[:;]\s*/g, ", ");
  clean = clean.replace(/\s*--\s*/g, ", ");

  // 11. Collapse whitespace
  clean = clean.replace(/\s+/g, " ").trim();

  // 12. Limit length for speech: summarize overly long responses
  const sentences = clean.split(/(?<=[.!?])\s+/);
  if (sentences.length > MAX_SPOKEN_SENTENCES) {
    let spoken = sentences.slice(0, MAX_SPOKEN_SENTENCES).join(" ");
    if (!spoken.endsWith(".") && !spoken.endsWith("!") && !spoken.endsWith("?")) {
      spoken += ".";
    }
    spoken += " You can see further details in your conversation panel.";
    return spoken;
  }

  return clean;
}

/**
 * Split natural language text into individual sentence units for sentence-level streaming TTS.
 */
export function splitIntoSentences(text: string): string[] {
  if (!text || !text.trim()) return [];
  const clean = cleanSpokenText(text);
  if (!clean) return [];
  const matches = clean.match(/[^.!?]+[.!?]+(?:\s+|$)|[^.!?]+$/g);
  if (!matches) return [clean];
  return matches.map((s) => s.trim()).filter((s) => s.length > 0);
}

/**
 * Cleans text for displaying in chat / transcript bubbles so it looks polished,
 * readable, and free of ugly raw asterisks, hashes, and formatting clutter.
 *
 * NOTE: This does NOT run speech normalization. The UI shows the original data values.
 */
export function cleanDisplayText(text: string): string {
  if (!text) return "";
  let clean = text.trim();
  // Strip bold/bullet asterisks, hashes, backticks, pipes, citation tags
  clean = clean.replace(/[*#_~`|<>{}\\^]/g, "");
  clean = clean.replace(/\[(?:ref|source|\d+|file|doc)[^\]]*\]/gi, "");
  // Markdown links [title](url) -> title
  clean = clean.replace(/\[([^\]]+)\]\([^\)]+\)/g, "$1");
  clean = clean.replace(/\s+/g, " ").trim();
  return clean;
}

/**
 * Cleans user speech input before giving to the AI to strip any accidental symbols.
 */
export function sanitizeUserQueryForAI(text: string): string {
  if (!text) return "";
  return text
    .replace(/[*#_~`|<>{}\\\/^]/g, " ")
    .replace(/\[.*?\]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

// ─── SpeechSynthesisService ─────────────────────────────────────────────────

class SpeechSynthesisService {
  private activeUtterance: SpeechSynthesisUtterance | null = null;
  private animFrameId: number | null = null;
  private isSpeaking = false;
  private amplitudePhase = 0;
  private cachedVoices: SpeechSynthesisVoice[] = [];
  private sessionPlaybackMode: "neural" | "browser" | null = null;
  private sessionBrowserVoices = new Map<VoiceProfileId, SpeechSynthesisVoice | null>();

  // Neural TTS Audio State
  private apiClient: NanviApiClient | null = null;
  private abortController: AbortController | null = null;
  private currentSource: AudioBufferSourceNode | null = null;
  private currentAudioElement: HTMLAudioElement | null = null;
  private activeBlobUrl: string | null = null;
  private activeSessionId = 0;

  // Session voice lock: once a voice is chosen for a session, stick with it
  private sessionVoiceProfileId: VoiceProfileId | null = null;

  constructor() {
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      this.refreshVoices();
      window.speechSynthesis.onvoiceschanged = () => {
        this.refreshVoices();
      };
    }
  }

  get supported(): boolean {
    return typeof window !== "undefined" && "speechSynthesis" in window;
  }

  setApiClient(client: NanviApiClient | null): void {
    this.apiClient = client;
  }

  beginSession(): void {
    this.stop();
    this.sessionPlaybackMode = null;
    this.sessionBrowserVoices.clear();
    this.sessionVoiceProfileId = null;
  }

  endSession(): void {
    this.stop();
    this.sessionPlaybackMode = null;
    this.sessionBrowserVoices.clear();
    this.sessionVoiceProfileId = null;
  }

  private async requestNeuralAudio(
    client: NanviApiClient,
    text: string,
    profile: VoiceProfile,
    sessionId: number
  ): Promise<Blob | null> {
    const controller = new AbortController();
    this.abortController = controller;
    let timedOut = false;

    let timeoutId = 0;
    const timeout = new Promise<null>((resolve) => {
      timeoutId = window.setTimeout(() => {
        timedOut = true;
        controller.abort();
        resolve(null);
      }, NEURAL_TTS_TIMEOUT_MS);
    });

    try {
      const blob = await Promise.race([
        client.voiceSynthesize(text, profile.id, "en-IN", controller.signal),
        timeout,
      ]);
      if (sessionId !== this.activeSessionId || timedOut) return null;
      return blob;
    } catch (error) {
      if (sessionId !== this.activeSessionId || controller.signal.aborted) return null;
      console.warn("Neural voice synthesis failed, using browser speech:", error);
      return null;
    } finally {
      window.clearTimeout(timeoutId);
      if (this.abortController === controller) this.abortController = null;
    }
  }

  private refreshVoices(): void {
    if (!this.supported) return;
    const voices = window.speechSynthesis.getVoices();
    if (voices && voices.length > 0) {
      this.cachedVoices = voices;
    }
  }

  private scoreVoice(voice: SpeechSynthesisVoice, profileId: VoiceProfileId): number {
    const name = voice.name.toLowerCase();
    const lang = voice.lang.toLowerCase();
    let score = 0;

    // Must be English
    if (!lang.startsWith("en")) return -1000;
    if (lang.includes("us") || lang.includes("en-us")) score += 20;
    else if (lang.includes("gb") || lang.includes("en-gb")) score += 15;
    else score += 5;

    // HEAVY PENALTY for old legacy robotic voices (Windows SAPI5 desktop voices, eSpeak)
    if (name.includes("desktop") || name.includes("espeak") || name.includes("sapi") || name.includes("robotic")) {
      score -= 200;
    }

    // High bonus for modern Natural / Neural / Online voices (Edge Azure neural voices, Chrome Google voices)
    if (name.includes("online (natural)") || name.includes("natural")) {
      score += 150;
    }
    if (name.includes("neural") || name.includes("enhanced") || name.includes("premium")) {
      score += 120;
    }
    if (name.includes("google")) {
      score += 90;
    }

    // CONSISTENT female vocal range for all profiles to maintain Nanvi's warm, articulate vocal identity
    if (/jenny|ava|aria|zira|samantha|karen|serena|emma|victoria|neerja|sonia/i.test(name)) {
      score += 60;
    }
    // Strongly deprioritize male voices to prevent jarring pitch drops
    if (/david|george|mark|richard|andrew|guy|christopher|daniel/i.test(name)) {
      score -= 180;
    }

    if (profileId === "nanvi-warm") {
      if (/ava|jenny|samantha/i.test(name)) score += 30;
    } else if (profileId === "nanvi-clear") {
      if (/emma|aria|victoria/i.test(name)) score += 30;
    } else if (profileId === "nanvi-concise") {
      if (/aria|jenny/i.test(name)) score += 30;
    } else {
      if (/jenny|ava|samantha/i.test(name)) score += 30;
    }

    return score;
  }

  private pickVoice(profile: VoiceProfile): SpeechSynthesisVoice | null {
    if (!this.supported) return null;

    // Use session-locked profile to prevent voice switches mid-session
    const lockId = this.sessionVoiceProfileId || profile.id;

    if (this.sessionBrowserVoices.has(lockId)) {
      return this.sessionBrowserVoices.get(lockId) ?? null;
    }
    this.refreshVoices();
    const voices = this.cachedVoices.length > 0 ? this.cachedVoices : window.speechSynthesis.getVoices();
    if (!voices || voices.length === 0) {
      this.sessionBrowserVoices.set(lockId, null);
      return null;
    }

    const enVoices = voices.filter((v) => v.lang.toLowerCase().startsWith("en"));
    const pool = enVoices.length > 0 ? enVoices : voices;

    const sorted = [...pool].sort((a, b) => this.scoreVoice(b, lockId) - this.scoreVoice(a, lockId));
    const selected = sorted[0] || null;
    this.sessionBrowserVoices.set(lockId, selected);
    // Lock the profile for the rest of this session
    this.sessionVoiceProfileId = lockId;
    return selected;
  }

  async speak(
    text: string,
    profile: VoiceProfile,
    events: SpeechEvents = {},
    api?: NanviApiClient
  ): Promise<void> {
    this.stop();
    const sessionId = ++this.activeSessionId;
    const client = api || this.apiClient;

    const clean = cleanSpokenText(text);
    if (!clean) {
      events.onEnd?.();
      return;
    }

    // 1. Try photorealistic Microsoft Azure Neural TTS first
    if (this.sessionPlaybackMode !== "browser" && client) {
      const startTime = performance.now();
      const blob = await this.requestNeuralAudio(client, clean, profile, sessionId);
      if (sessionId !== this.activeSessionId) return;
      if (blob && await this.tryPlayNeuralAudio(blob, events, sessionId)) {
        if (sessionId !== this.activeSessionId) return;
        this.sessionPlaybackMode = "neural";
        events.onFirstAudio?.(Math.round(performance.now() - startTime));
        return;
      }
      if (sessionId !== this.activeSessionId) return;
      this.sessionPlaybackMode = "browser";
    } else if (this.sessionPlaybackMode === null) {
      this.sessionPlaybackMode = "browser";
    }

    // 2. Fallback to browser speech synthesis
    if (sessionId !== this.activeSessionId) return;
    this.speakBrowserUtterance(clean, profile, events, sessionId);
  }

  async speakSingleSentence(
    cleanSentence: string,
    profile: VoiceProfile,
    events: SpeechEvents,
    client: NanviApiClient | null,
    sessionId: number,
    prefetchedBlob?: Blob | null
  ): Promise<void> {
    if (!cleanSentence || sessionId !== this.activeSessionId) {
      events.onEnd?.();
      return;
    }

    if (this.sessionPlaybackMode !== "browser" && (client || prefetchedBlob)) {
      const blob = prefetchedBlob || (await this.requestNeuralAudio(client!, cleanSentence, profile, sessionId));
      if (sessionId !== this.activeSessionId) return;
      if (blob && await this.tryPlayNeuralAudio(blob, events, sessionId)) {
        if (sessionId !== this.activeSessionId) return;
        this.sessionPlaybackMode = "neural";
        return;
      }
      if (sessionId !== this.activeSessionId) return;
      this.sessionPlaybackMode = "browser";
    } else if (this.sessionPlaybackMode === null) {
      this.sessionPlaybackMode = "browser";
    }

    if (sessionId !== this.activeSessionId) return;
    this.speakBrowserUtterance(cleanSentence, profile, events, sessionId);
  }

  /**
   * Unified speech delivery:
   * Synthesizes the response as a single, continuous, fluent neural audio stream.
   * This guarantees:
   * 1. ZERO pauses or gaps between sentences (eliminates stopping and restarting).
   * 2. ZERO pitch jumps or voice switches (voice identity and tone remain 100% consistent).
   * 3. Natural human prosody and breath pacing across the entire answer.
   */
  async speakStream(
    textOrSentences: string | string[],
    profile: VoiceProfile,
    events: SpeechEvents = {},
    api?: NanviApiClient
  ): Promise<void> {
    this.stop();
    const sessionId = ++this.activeSessionId;
    const client = api || this.apiClient;

    const fullText = Array.isArray(textOrSentences)
      ? textOrSentences.map(cleanSpokenText).filter(Boolean).join(" ")
      : cleanSpokenText(textOrSentences);

    if (!fullText) {
      events.onEnd?.();
      return;
    }

    const startTime = performance.now();

    // 1. Prefer neural TTS, but don't make the conversation wait on a slow audio service.
    if (this.sessionPlaybackMode !== "browser" && client) {
      const blob = await this.requestNeuralAudio(client, fullText, profile, sessionId);
      if (sessionId !== this.activeSessionId) return;
      if (blob && await this.tryPlayNeuralAudio(blob, events, sessionId)) {
        if (sessionId !== this.activeSessionId) return;
        this.sessionPlaybackMode = "neural";
        const latencyMs = Math.round(performance.now() - startTime);
        console.log(`[Nanvi Voice] neural audio ready in ${latencyMs}ms`);
        events.onFirstAudio?.(latencyMs);
        return;
      }
      if (sessionId !== this.activeSessionId) return;
      this.sessionPlaybackMode = "browser";
    } else if (this.sessionPlaybackMode === null) {
      this.sessionPlaybackMode = "browser";
    }

    // 2. Fallback to browser speech synthesis using ONE single consistent voice
    if (sessionId !== this.activeSessionId) return;
    this.speakBrowserUtterance(fullText, profile, events, sessionId);
  }

  private async playNeuralAudio(
    blob: Blob,
    events: SpeechEvents,
    sessionId: number
  ): Promise<void> {
    // Let the browser stream decoding and playback rather than decoding the full blob first.
    if (sessionId !== this.activeSessionId) return;
    const url = URL.createObjectURL(blob);
    this.activeBlobUrl = url;
    const audio = new Audio();
    audio.preload = "auto";
    audio.src = url;
    this.currentAudioElement = audio;

    audio.onplaying = () => {
      if (sessionId !== this.activeSessionId) return;
      this.isSpeaking = true;
      events.onStart?.();
      this.startSynthesizedAmplitudeLoop(events.onAmplitude);
    };

    audio.onended = () => {
      if (sessionId === this.activeSessionId) {
        this.stopAmplitudeLoop();
        this.isSpeaking = false;
        if (this.activeBlobUrl) {
          URL.revokeObjectURL(this.activeBlobUrl);
          this.activeBlobUrl = null;
        }
        this.currentAudioElement = null;
        events.onAmplitude?.(0);
        events.onEnd?.();
      }
    };

    let errorHandled = false;
    audio.onerror = () => {
      if (sessionId === this.activeSessionId) {
        errorHandled = true;
        this.stopAmplitudeLoop();
        this.isSpeaking = false;
        this.currentAudioElement = null;
        if (this.activeBlobUrl) URL.revokeObjectURL(this.activeBlobUrl);
        this.activeBlobUrl = null;
        events.onError?.("Audio playback failed");
        events.onEnd?.();
      }
    };

    try {
      await audio.play();
    } catch (error) {
      if (sessionId !== this.activeSessionId) return;
      this.stopAmplitudeLoop();
      this.isSpeaking = false;
      this.currentAudioElement = null;
      if (this.activeBlobUrl) URL.revokeObjectURL(this.activeBlobUrl);
      this.activeBlobUrl = null;
      if (!errorHandled) throw error;
    }
  }

  private async tryPlayNeuralAudio(blob: Blob, events: SpeechEvents, sessionId: number): Promise<boolean> {
    try {
      await this.playNeuralAudio(blob, events, sessionId);
      return true;
    } catch (error) {
      if (sessionId !== this.activeSessionId) return true;
      console.warn("Neural audio playback failed, using browser speech:", error);
      return false;
    }
  }

  private speakBrowserUtterance(
    clean: string,
    profile: VoiceProfile,
    events: SpeechEvents,
    sessionId: number
  ): void {
    if (!this.supported) {
      events.onError?.("Speech synthesis not supported in this browser.");
      events.onEnd?.();
      return;
    }

    const utterance = new SpeechSynthesisUtterance(clean);
    const voice = this.pickVoice(profile);
    if (voice) {
      utterance.voice = voice;
    }

    // Consistent rate and pitch across all profiles — narrow range prevents jarring changes
    utterance.rate = Math.max(0.92, Math.min(1.05, profile.rate));
    utterance.pitch = Math.max(0.98, Math.min(1.04, profile.pitch));
    utterance.volume = 1.0;

    utterance.onstart = () => {
      if (sessionId !== this.activeSessionId) return;
      this.isSpeaking = true;
      events.onStart?.();
      this.startSynthesizedAmplitudeLoop(events.onAmplitude);
    };

    utterance.onend = () => {
      if (sessionId !== this.activeSessionId) return;
      this.stopAmplitudeLoop();
      this.isSpeaking = false;
      this.activeUtterance = null;
      events.onAmplitude?.(0);
      events.onEnd?.();
    };

    utterance.onerror = (e) => {
      if (sessionId !== this.activeSessionId) return;
      this.stopAmplitudeLoop();
      this.isSpeaking = false;
      this.activeUtterance = null;
      events.onAmplitude?.(0);
      if (e.error !== "canceled" && e.error !== "interrupted") {
        events.onError?.(`Speech synthesis error: ${e.error}`);
      }
      events.onEnd?.();
    };

    utterance.onboundary = () => {
      this.amplitudePhase = Math.PI * 0.5;
    };

    this.activeUtterance = utterance;
    window.speechSynthesis.speak(utterance);
  }

  private startRealtimeAmplitudeLoop(
    analyser: AnalyserNode,
    onAmplitude?: (level: number) => void
  ): void {
    if (!onAmplitude) return;
    this.stopAmplitudeLoop();

    const dataArray = new Uint8Array(analyser.frequencyBinCount);

    const update = () => {
      if (!this.isSpeaking) {
        onAmplitude(0);
        return;
      }

      analyser.getByteFrequencyData(dataArray);
      let sum = 0;
      for (let i = 0; i < dataArray.length; i++) {
        sum += dataArray[i];
      }
      const avg = sum / dataArray.length;
      // Map audio energy to 0.08..1.0 range so Orb reacts organically to real voice dynamics
      const level = Math.max(0.08, Math.min(1.0, (avg / 128) * 1.3));
      onAmplitude(level);

      this.animFrameId = requestAnimationFrame(update);
    };

    this.animFrameId = requestAnimationFrame(update);
  }

  private startSynthesizedAmplitudeLoop(onAmplitude?: (level: number) => void): void {
    if (!onAmplitude) return;
    this.stopAmplitudeLoop();

    const update = () => {
      if (!this.isSpeaking) {
        onAmplitude(0);
        return;
      }

      this.amplitudePhase += 0.22;
      const pulse = 0.45 + 0.4 * Math.sin(this.amplitudePhase) * Math.cos(this.amplitudePhase * 0.7);
      const level = Math.max(0.15, Math.min(0.95, pulse));
      onAmplitude(level);

      this.animFrameId = requestAnimationFrame(update);
    };

    this.animFrameId = requestAnimationFrame(update);
  }

  private stopAmplitudeLoop(): void {
    if (this.animFrameId !== null) {
      cancelAnimationFrame(this.animFrameId);
      this.animFrameId = null;
    }
  }

  stop(): void {
    this.activeSessionId++;
    this.stopAmplitudeLoop();
    this.isSpeaking = false;

    if (this.abortController) {
      try {
        this.abortController.abort();
      } catch {}
      this.abortController = null;
    }

    if (this.currentSource) {
      try {
        this.currentSource.stop();
        this.currentSource.disconnect();
      } catch {}
      this.currentSource = null;
    }

    if (this.currentAudioElement) {
      try {
        this.currentAudioElement.pause();
        this.currentAudioElement.currentTime = 0;
        this.currentAudioElement.src = "";
      } catch {}
      this.currentAudioElement = null;
    }

    if (this.activeBlobUrl) {
      try {
        URL.revokeObjectURL(this.activeBlobUrl);
      } catch {}
      this.activeBlobUrl = null;
    }

    this.activeUtterance = null;
    if (this.supported) {
      try {
        window.speechSynthesis.cancel();
      } catch {}
    }
  }
}

export const speechSynthesisService = new SpeechSynthesisService();
