import type { NanviApiClient } from "../../api";
import pcmCaptureWorkletUrl from "./pcmCaptureWorklet.js?url&no-inline";

export type RealtimeVoiceEvent = Record<string, unknown> & { type: string };

type RealtimeVoiceTransportOptions = {
  onEvent: (event: RealtimeVoiceEvent) => void;
  onClose: (code: number, reason: string) => void;
};

const PROVIDER_SAMPLE_RATE = 24_000;

/**
 * Minimum sustained transcript delta duration (ms) before treating it as an intentional
 * barge-in. Prevents echo/noise from accidentally interrupting the assistant.
 */
const BARGE_IN_TRANSCRIPT_DEBOUNCE_MS = 400;

/**
 * Grace period (ms) after the last audio chunk before dispatching "assistant.completed".
 * This prevents premature completion signals during normal streaming.
 */
const COMPLETION_GRACE_MS = 600;

export function toPcm16(samples: Float32Array, sourceRate: number): Int16Array {
  const ratio = sourceRate / PROVIDER_SAMPLE_RATE;
  const output = new Int16Array(Math.max(1, Math.floor(samples.length / ratio)));
  for (let index = 0; index < output.length; index += 1) {
    const start = Math.floor(index * ratio);
    const end = Math.max(start + 1, Math.floor((index + 1) * ratio));
    let sum = 0;
    let count = 0;
    for (let sourceIndex = start; sourceIndex < Math.min(end, samples.length); sourceIndex += 1) {
      sum += samples[sourceIndex];
      count += 1;
    }
    const value = Math.max(-1, Math.min(1, count ? sum / count : samples[start] || 0));
    output[index] = value < 0 ? value * 0x8000 : value * 0x7fff;
  }
  return output;
}

export function pcm16ToBase64(pcm: Int16Array): string {
  const bytes = new Uint8Array(pcm.buffer, pcm.byteOffset, pcm.byteLength);
  let binary = "";
  const blockSize = 0x6000;
  for (let index = 0; index < bytes.length; index += blockSize) {
    binary += String.fromCharCode(...bytes.subarray(index, index + blockSize));
  }
  return btoa(binary);
}

export class RealtimeVoiceTransport {
  private socket: WebSocket | null = null;
  private stream: MediaStream | null = null;
  private audioContext: AudioContext | null = null;
  private processor: ScriptProcessorNode | null = null;
  private captureNode: AudioWorkletNode | null = null;
  private source: MediaStreamAudioSourceNode | null = null;
  private silentGain: GainNode | null = null;
  private readonly audioSources = new Set<AudioBufferSourceNode>();
  private readonly options: RealtimeVoiceTransportOptions;
  private stopping = false;
  private muted = false;
  private scheduledUntil = 0;
  private completionTimer: number | null = null;
  private transcriptTimer: number | null = null;
  private pendingTranscript = "";

  /**
   * Track whether we are currently in an assistant audio response.
   * This prevents transcript deltas from spuriously interrupting playback.
   */
  private isAssistantSpeaking = false;

  /**
   * Track the server-sent assistant.completed event so we can dispatch it
   * AFTER all buffered audio finishes playing.
   */
  private pendingCompletionEvent: RealtimeVoiceEvent | null = null;

  /**
   * Debounced barge-in: tracks the time when transcript deltas started arriving
   * while the assistant is speaking. Only triggers interruption after sustained input.
   */
  private bargeInStartTime: number | null = null;

  constructor(
    private readonly api: NanviApiClient,
    options: RealtimeVoiceTransportOptions,
  ) {
    this.options = options;
  }

  async start(
    conversationId: string | undefined,
    ragEnabled: boolean,
    preferences: { verbosity: string; privacy_mode: boolean },
  ): Promise<void> {
    const socket = await this.api.openRealtimeVoiceSocket(conversationId, ragEnabled, preferences);
    this.socket = socket;

    await new Promise<void>((resolve, reject) => {
      let settled = false;
      const timeoutId = window.setTimeout(() => {
        if (settled) return;
        settled = true;
        reject(new Error("Realtime voice connection timed out."));
      }, 18_000);

      const finish = (error?: Error) => {
        if (settled) return;
        settled = true;
        window.clearTimeout(timeoutId);
        if (error) reject(error);
        else resolve();
      };

      socket.addEventListener("message", (message: MessageEvent<string>) => {
        let event: RealtimeVoiceEvent;
        try {
          const parsed: unknown = JSON.parse(message.data);
          if (!parsed || typeof parsed !== "object" || !("type" in parsed) || typeof parsed.type !== "string") return;
          event = parsed as RealtimeVoiceEvent;
        } catch {
          return;
        }

        if (event.type === "session.started") {
          void this.startMicrophone()
            .then(() => {
              this.options.onEvent(event);
              finish();
            })
            .catch((error: unknown) => {
              const messageText = error instanceof DOMException && error.name === "NotAllowedError"
                ? "Microphone permission was denied. Allow microphone access and try again."
                : error instanceof Error
                  ? error.message
                  : "The microphone is unavailable.";
              this.options.onEvent({ type: "error", code: "microphone_unavailable", message: messageText });
              finish(error instanceof Error ? error : new Error(messageText));
              this.stop();
            });
          return;
        }

        if (event.type === "error") {
          this.options.onEvent(event);
          if (!settled) finish(new Error(typeof event.message === "string" ? event.message : "Realtime voice could not start."));
          return;
        }

        // ─── Transcript Deltas ───────────────────────────────────────
        if (event.type === "transcript.delta" && typeof event.text === "string") {
          this.pendingTranscript += event.text;

          // Debounced transcript finalization
          if (this.transcriptTimer !== null) window.clearTimeout(this.transcriptTimer);
          this.transcriptTimer = window.setTimeout(() => {
            this.transcriptTimer = null;
            const transcript = this.pendingTranscript.trim();
            this.pendingTranscript = "";
            if (transcript) this.options.onEvent({ type: "transcript.completed", text: transcript });
          }, 700);

          // Barge-in detection: only interrupt if the user has been speaking for a sustained period
          if (this.isAssistantSpeaking && this.audioSources.size > 0) {
            const now = Date.now();
            if (this.bargeInStartTime === null) {
              this.bargeInStartTime = now;
            } else if (now - this.bargeInStartTime >= BARGE_IN_TRANSCRIPT_DEBOUNCE_MS) {
              // Sustained user speech detected — this is an intentional barge-in
              this.stopPlayback();
              this.isAssistantSpeaking = false;
              this.bargeInStartTime = null;
              this.options.onEvent({ type: "assistant.interrupted" });
            }
          }

          // Forward the delta to the UI for live transcript display
          this.options.onEvent(event);
          return;
        }

        // ─── Assistant Audio Chunks ──────────────────────────────────
        if (event.type === "assistant.audio.delta" && typeof event.audio === "string") {
          this.isAssistantSpeaking = true;
          this.bargeInStartTime = null; // Reset barge-in tracking on new audio
          this.playAudio(event.audio);
          // Forward audio level event but do NOT dispatch completion here
          this.options.onEvent(event);
          return;
        }

        // ─── Assistant Started ───────────────────────────────────────
        if (event.type === "assistant.started") {
          this.isAssistantSpeaking = true;
          this.bargeInStartTime = null;
          this.pendingCompletionEvent = null;
          this.options.onEvent(event);
          return;
        }

        // ─── Assistant Completed (from server) ───────────────────────
        if (event.type === "assistant.completed") {
          // Don't dispatch immediately — wait until all buffered audio finishes playing
          this.scheduleCompletionAfterPlayback(event);
          return;
        }

        // ─── Assistant Interrupted ───────────────────────────────────
        if (event.type === "assistant.interrupted") {
          this.stopPlayback();
          this.isAssistantSpeaking = false;
          this.bargeInStartTime = null;
          this.options.onEvent(event);
          return;
        }

        // ─── All other events ────────────────────────────────────────
        this.options.onEvent(event);
      });

      socket.addEventListener("close", (event: CloseEvent) => {
        finish(new Error(event.reason || "Realtime voice connection closed."));
        if (!this.stopping) this.options.onClose(event.code, event.reason);
      });
      socket.addEventListener("error", () => {
        finish(new Error("Realtime voice could not connect."));
      });
    });
  }

  sendText(text: string): void {
    this.send({ type: "user.text", text });
  }

  setMuted(muted: boolean): void {
    this.muted = muted;
    for (const track of this.stream?.getAudioTracks() ?? []) track.enabled = !muted;
  }

  updatePreferences(preferences: { verbosity: string; privacy_mode: boolean }): void {
    this.send({ type: "session.preferences", ...preferences });
  }

  interrupt(): void {
    this.stopPlayback();
    this.isAssistantSpeaking = false;
    this.bargeInStartTime = null;
    this.send({ type: "user.interrupt" });
  }

  stop(): void {
    if (this.stopping) return;
    this.stopping = true;
    if (this.completionTimer !== null) window.clearTimeout(this.completionTimer);
    if (this.transcriptTimer !== null) window.clearTimeout(this.transcriptTimer);
    this.completionTimer = null;
    this.transcriptTimer = null;
    this.isAssistantSpeaking = false;
    this.bargeInStartTime = null;
    this.pendingCompletionEvent = null;
    this.stopPlayback();
    if (this.captureNode) {
      this.captureNode.port.onmessage = null;
      this.captureNode.disconnect();
      this.captureNode = null;
    }
    if (this.processor) {
      this.processor.onaudioprocess = null;
      this.processor.disconnect();
      this.processor = null;
    }
    this.source?.disconnect();
    this.source = null;
    this.silentGain?.disconnect();
    this.silentGain = null;
    for (const track of this.stream?.getTracks() ?? []) track.stop();
    this.stream = null;
    const context = this.audioContext;
    this.audioContext = null;
    if (context && context.state !== "closed") void context.close().catch(() => {});
    if (this.socket) {
      if (this.socket.readyState === WebSocket.OPEN) {
        try {
          this.socket.send(JSON.stringify({ type: "session.stop" }));
        } catch {
          // The socket may already be closing.
        }
      }
      this.socket.close(1000, "Voice session ended");
      this.socket = null;
    }
  }

  private async startMicrophone(): Promise<void> {
    if (!navigator.mediaDevices?.getUserMedia) throw new Error("This browser cannot access a microphone.");
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 },
    });

    const AudioContextConstructor = window.AudioContext;
    try {
      this.audioContext = new AudioContextConstructor({ sampleRate: PROVIDER_SAMPLE_RATE, latencyHint: "interactive" });
    } catch {
      this.audioContext = new AudioContextConstructor({ latencyHint: "interactive" });
    }
    if (this.audioContext.state === "suspended") await this.audioContext.resume();

    this.source = this.audioContext.createMediaStreamSource(this.stream);
    this.silentGain = this.audioContext.createGain();
    this.silentGain.gain.value = 0;

    if (this.audioContext.audioWorklet && typeof AudioWorkletNode !== "undefined") {
      try {
        await this.audioContext.audioWorklet.addModule(pcmCaptureWorkletUrl);
        this.captureNode = new AudioWorkletNode(this.audioContext, "nanvi-pcm-capture", {
          numberOfInputs: 1,
          numberOfOutputs: 1,
          outputChannelCount: [1],
        });
        this.captureNode.port.onmessage = (event: MessageEvent<Float32Array>) => {
          if (event.data instanceof Float32Array) this.processMicrophoneSamples(event.data);
        };
        this.source.connect(this.captureNode);
        this.captureNode.connect(this.silentGain);
      } catch {
        this.captureNode = null;
      }
    }

    if (!this.captureNode) {
      this.processor = this.audioContext.createScriptProcessor(2048, 1, 1);
      this.processor.onaudioprocess = (event: AudioProcessingEvent) => {
        this.processMicrophoneSamples(event.inputBuffer.getChannelData(0));
      };
      this.source.connect(this.processor);
      this.processor.connect(this.silentGain);
    }
    this.silentGain.connect(this.audioContext.destination);
  }

  private processMicrophoneSamples(samples: Float32Array): void {
    let energy = 0;
    for (let index = 0; index < samples.length; index += 1) energy += samples[index] * samples[index];
    const level = Math.min(1, Math.sqrt(energy / Math.max(samples.length, 1)) * 4);
    this.options.onEvent({ type: "microphone.level", level: this.muted ? 0 : level });
    if (this.muted || !this.socket || this.socket.readyState !== WebSocket.OPEN || this.socket.bufferedAmount > 256_000) return;
    const pcm = toPcm16(samples, this.audioContext?.sampleRate ?? PROVIDER_SAMPLE_RATE);
    this.send({ type: "session.input_audio.append", audio: pcm16ToBase64(pcm) });
  }

  /**
   * Decode a base64-encoded PCM16 audio chunk and schedule it for gapless playback.
   * Audio chunks are queued sequentially using Web Audio API's precise scheduling,
   * ensuring smooth, continuous playback with no gaps or overlaps.
   */
  private playAudio(encodedAudio: string): void {
    const context = this.audioContext;
    if (!context || context.state === "closed") return;
    try {
      const binary = atob(encodedAudio);
      const samples = new Float32Array(Math.floor(binary.length / 2));
      const bytes = Uint8Array.from(binary, (character) => character.charCodeAt(0));
      const data = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
      let energy = 0;
      for (let index = 0; index < samples.length; index += 1) {
        const value = data.getInt16(index * 2, true) / 32768;
        samples[index] = value;
        energy += value * value;
      }
      if (samples.length === 0) return;
      const buffer = context.createBuffer(1, samples.length, PROVIDER_SAMPLE_RATE);
      buffer.copyToChannel(samples, 0);
      const source = context.createBufferSource();
      source.buffer = buffer;
      source.connect(context.destination);

      // Schedule gapless playback: each chunk starts exactly when the previous one ends
      const startsAt = Math.max(context.currentTime + 0.02, this.scheduledUntil);
      source.onended = () => this.audioSources.delete(source);
      this.audioSources.add(source);
      source.start(startsAt);
      this.scheduledUntil = startsAt + buffer.duration;

      // Emit audio level for visual feedback
      this.options.onEvent({
        type: "assistant.audio.level",
        level: Math.min(1, Math.sqrt(energy / samples.length) * 4),
      });

      // Reset the completion timer: we're still receiving audio
      this.scheduleCompletionAfterPlayback(this.pendingCompletionEvent || { type: "assistant.completed" });
    } catch {
      this.options.onEvent({ type: "error", code: "audio_decode_failed", message: "Nanvi audio could not be played." });
    }
  }

  /**
   * Immediately stop all queued and playing audio.
   * Called during barge-in, interruption, and session cleanup.
   */
  private stopPlayback(): void {
    if (this.completionTimer !== null) window.clearTimeout(this.completionTimer);
    this.completionTimer = null;
    this.pendingCompletionEvent = null;
    for (const source of this.audioSources) {
      try {
        source.stop();
      } catch {
        // A source that already ended cannot be stopped a second time.
      }
    }
    this.audioSources.clear();
    this.scheduledUntil = this.audioContext?.currentTime ?? 0;
  }

  /**
   * Schedule the completion event to fire AFTER all buffered audio has finished playing.
   * This is the key fix for "speech randomly stopping" — we only signal completion
   * when there is genuinely no more audio to play.
   */
  private scheduleCompletionAfterPlayback(event: RealtimeVoiceEvent | null): void {
    if (this.completionTimer !== null) window.clearTimeout(this.completionTimer);
    this.pendingCompletionEvent = event;

    if (!event) return;

    const remainingSeconds = Math.max(0, this.scheduledUntil - (this.audioContext?.currentTime ?? 0));
    this.completionTimer = window.setTimeout(() => {
      this.completionTimer = null;
      this.pendingCompletionEvent = null;
      this.isAssistantSpeaking = false;
      this.bargeInStartTime = null;
      this.options.onEvent(event);
    }, Math.ceil(remainingSeconds * 1000) + COMPLETION_GRACE_MS);
  }

  private send(event: Record<string, unknown>): void {
    if (this.socket?.readyState === WebSocket.OPEN) this.socket.send(JSON.stringify(event));
  }
}
