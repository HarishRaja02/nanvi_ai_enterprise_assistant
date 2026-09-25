import type { NanviApiClient } from "../../api";
import { VoiceProfile, VoiceProfileId } from "./voiceTypes";

export type SpeechEvents = {
  onStart?: () => void;
  onEnd?: () => void;
  onError?: (err: string) => void;
  onAmplitude?: (level: number) => void;
};

/**
 * Strips all markdown asterisks, hashes, code blocks, citation tags, emojis,
 * and formatting symbols so the Speech engine speaks pure, natural human text
 * without ever pronouncing "asterisk" or stumbling over symbols.
 */
export function cleanSpokenText(text: string): string {
  if (!text || !text.trim()) return "";

  let clean = text.trim();

  // 1. Remove markdown code blocks and inline code
  clean = clean.replace(/```[\s\S]*?```/g, " Code details are available in your conversation record. ");
  clean = clean.replace(/`([^`]+)`/g, "$1");

  // 2. Remove markdown tables (| col | col | ...)
  clean = clean.replace(/(\|.*\|\r?\n?)+/g, " Detailed figures are recorded in your context panel. ");

  // 3. Remove citation tags like [1], [ref-1], [Source 2], [file.pdf]
  clean = clean.replace(/\[(?:ref|source|\d+|file|doc)[^\]]*\]/gi, "");
  // Markdown links [label](url) -> label
  clean = clean.replace(/\[([^\]]+)\]\([^\)]+\)/g, "$1");
  // Remove standalone URLs
  clean = clean.replace(/https?:\/\/\S+/g, "");

  // 4. Remove headings (#, ##, ###)
  clean = clean.replace(/^#{1,6}\s*/gm, "");

  // 5. Expand currency for smooth human pronunciation: $4.2M -> 4.2 million dollars
  clean = clean.replace(/\$(\d+(?:\.\d+)?)\s*([BMKbmk])\b/g, (_, num, mult) => {
    const map: Record<string, string> = { b: " billion dollars", m: " million dollars", k: " thousand dollars" };
    return `${num}${map[mult.toLowerCase()] || " dollars"}`;
  });
  clean = clean.replace(/\$(\d+(?:\.\d+)?)/g, "$1 dollars");

  // 6. Conversational expansions for natural human delivery
  clean = clean.replace(/\be\.g\b\.?,?\s*/gi, "for example, ");
  clean = clean.replace(/\bi\.e\b\.?,?\s*/gi, "that is, ");
  clean = clean.replace(/\betc\b\.?/gi, "and so forth");
  clean = clean.replace(/\bvs\b\.?\s*/gi, "versus ");
  clean = clean.replace(/\bQ([1-4])\b/g, "Quarter $1");
  clean = clean.replace(/&/g, " and ");

  // 7. CRITICAL: Completely strip ALL asterisks (*, **, ***), hashes (#), underscores (_), tildes (~), backticks (`), pipes (|), angle brackets (< >), curly braces ({ }), carets (^)
  clean = clean.replace(/[*#_~`|<>{}\^\\\/]/g, " ");

  // 8. Remove bullet points (- item, • item, + item, 1. item) from start of lines
  clean = clean.replace(/^[\s\-•◦▪▫+*]+\s*/gm, "");
  clean = clean.replace(/^\s*\d+[\.\)]\s*/gm, "");

  // 9. Strip emojis
  clean = clean.replace(/[\u{1F600}-\u{1F64F}\u{1F300}-\u{1F5FF}\u{1F680}-\u{1F6FF}\u{1F700}-\u{1F77F}\u{1F780}-\u{1F7FF}\u{1F800}-\u{1F8FF}\u{1F900}-\u{1F9FF}\u{1FA00}-\u{1FA6F}\u{1FA70}-\u{1FAFF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}]/gu, "");

  // 10. Turn multiple punctuation marks, semicolons or colons into natural breath pauses
  clean = clean.replace(/[:;]\s*/g, ", ");
  clean = clean.replace(/\s*--\s*/g, ", ");
  clean = clean.replace(/\s+/g, " ").trim();

  // 11. Human conversational pacing: if the response is very long, summarize the spoken portion to top 3 natural sentences
  const sentences = clean.split(/(?<=[.!?])\s+/);
  if (sentences.length > 4) {
    let spoken = sentences.slice(0, 3).join(" ");
    if (!spoken.endsWith(".") && !spoken.endsWith("!") && !spoken.endsWith("?")) {
      spoken += ".";
    }
    spoken += " Further specific details are provided in your Voice Context panel.";
    return spoken;
  }

  return clean;
}

/**
 * Cleans text for displaying in chat / transcript bubbles so it looks polished,
 * readable, and free of ugly raw asterisks, hashes, and formatting clutter.
 */
export function cleanDisplayText(text: string): string {
  if (!text) return "";
  let clean = text.trim();
  // Strip bold/bullet asterisks, hashes, backticks, pipes, citation tags
  clean = clean.replace(/[*#_~`|<>{}\^\\]/g, "");
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
    .replace(/[*#_~`|<>{}\^\\\/]/g, " ")
    .replace(/\[.*?\]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

class SpeechSynthesisService {
  private activeUtterance: SpeechSynthesisUtterance | null = null;
  private animFrameId: number | null = null;
  private isSpeaking = false;
  private amplitudePhase = 0;
  private cachedVoices: SpeechSynthesisVoice[] = [];

  // Neural TTS Audio State
  private apiClient: NanviApiClient | null = null;
  private abortController: AbortController | null = null;
  private audioContext: AudioContext | null = null;
  private currentSource: AudioBufferSourceNode | null = null;
  private currentAudioElement: HTMLAudioElement | null = null;
  private activeBlobUrl: string | null = null;
  private activeSessionId = 0;

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

    if (profileId === "nanvi-warm") {
      if (/jenny|ava|aria|samantha|karen|serena/i.test(name)) score += 40;
    } else if (profileId === "nanvi-clear") {
      if (/emma|aria|google us|victoria|sonia/i.test(name)) score += 40;
    } else if (profileId === "nanvi-concise") {
      if (/andrew|guy|christopher|daniel|george/i.test(name)) score += 40;
    } else {
      if (/jenny|ava|aria|google us english|samantha/i.test(name)) score += 35;
    }

    return score;
  }

  private pickVoice(profile: VoiceProfile): SpeechSynthesisVoice | null {
    if (!this.supported) return null;
    this.refreshVoices();
    const voices = this.cachedVoices.length > 0 ? this.cachedVoices : window.speechSynthesis.getVoices();
    if (!voices || voices.length === 0) return null;

    const enVoices = voices.filter((v) => v.lang.toLowerCase().startsWith("en"));
    const pool = enVoices.length > 0 ? enVoices : voices;

    const sorted = [...pool].sort((a, b) => this.scoreVoice(b, profile.id) - this.scoreVoice(a, profile.id));
    return sorted[0] || null;
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
    if (client) {
      const ac = new AbortController();
      this.abortController = ac;

      try {
        const blob = await client.voiceSynthesize(clean, profile.id, ac.signal);
        if (sessionId !== this.activeSessionId) return;

        await this.playNeuralAudio(blob, events, sessionId);
        return;
      } catch (err: any) {
        if (sessionId !== this.activeSessionId) return;
        if (err?.name === "AbortError" || ac.signal.aborted) {
          return;
        }
        console.warn("Neural voice synthesis failed or offline, falling back to browser speech synthesis:", err);
      }
    }

    // 2. Fallback to browser speech synthesis
    if (sessionId !== this.activeSessionId) return;
    this.speakBrowserUtterance(clean, profile, events, sessionId);
  }

  private async playNeuralAudio(
    blob: Blob,
    events: SpeechEvents,
    sessionId: number
  ): Promise<void> {
    // Attempt WebAudio buffer playback first for real acoustic amplitude & sub-millisecond precision
    try {
      const AudioCtxClass = typeof window !== "undefined"
        ? (window.AudioContext || (window as any).webkitAudioContext)
        : null;

      if (AudioCtxClass) {
        if (!this.audioContext || this.audioContext.state === "closed") {
          this.audioContext = new AudioCtxClass();
        }
        if (this.audioContext.state === "suspended") {
          await this.audioContext.resume();
        }

        const arrayBuffer = await blob.arrayBuffer();
        if (sessionId !== this.activeSessionId) return;

        const audioBuffer = await this.audioContext.decodeAudioData(arrayBuffer);
        if (sessionId !== this.activeSessionId) return;

        const source = this.audioContext.createBufferSource();
        source.buffer = audioBuffer;

        const analyser = this.audioContext.createAnalyser();
        analyser.fftSize = 256;
        analyser.smoothingTimeConstant = 0.4;

        source.connect(analyser);
        analyser.connect(this.audioContext.destination);

        this.currentSource = source;
        this.isSpeaking = true;

        events.onStart?.();
        this.startRealtimeAmplitudeLoop(analyser, events.onAmplitude);

        source.onended = () => {
          if (sessionId === this.activeSessionId) {
            this.stopAmplitudeLoop();
            this.isSpeaking = false;
            this.currentSource = null;
            events.onAmplitude?.(0);
            events.onEnd?.();
          }
        };

        source.start(0);
        return;
      }
    } catch (e) {
      console.warn("WebAudio decoding failed, attempting HTMLAudioElement fallback:", e);
    }

    // HTMLAudioElement fallback
    if (sessionId !== this.activeSessionId) return;
    const url = URL.createObjectURL(blob);
    this.activeBlobUrl = url;
    const audio = new Audio(url);
    this.currentAudioElement = audio;

    audio.onplay = () => {
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

    audio.onerror = () => {
      if (sessionId === this.activeSessionId) {
        this.stop();
        events.onError?.("Audio playback failed");
        events.onEnd?.();
      }
    };

    await audio.play();
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
