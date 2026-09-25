export interface BargeInConfig {
  speechThreshold: number; // Volume threshold 0.0 - 1.0 (default 0.28)
  minSpeechDurationMs: number; // Sustained duration in ms to filter accidental clicks/noise (default 260ms)
  onInterrupt: () => void;
}

export class BargeInDetector {
  private config: BargeInConfig;
  private speechStartTime: number | null = null;
  private isMonitoring = false;
  private triggered = false;

  constructor(config: BargeInConfig) {
    this.config = {
      speechThreshold: config.speechThreshold ?? 0.38,
      minSpeechDurationMs: config.minSpeechDurationMs ?? 320,
      onInterrupt: config.onInterrupt,
    };
  }

  start() {
    this.isMonitoring = true;
    this.speechStartTime = null;
    this.triggered = false;
  }

  stop() {
    this.isMonitoring = false;
    this.speechStartTime = null;
    this.triggered = false;
  }

  /**
   * Process continuous audio volume from the microphone analyser.
   * Filters out transient keyboard clicks, mic taps, and brief noises (< 260ms).
   */
  processAudioLevel(level: number) {
    if (!this.isMonitoring || this.triggered) return;

    const now = Date.now();

    if (level >= this.config.speechThreshold) {
      if (this.speechStartTime === null) {
        this.speechStartTime = now;
      } else {
        const sustainedDuration = now - this.speechStartTime;
        if (sustainedDuration >= this.config.minSpeechDurationMs) {
          // Intentional sustained vocal speech detected during playback!
          this.triggerBargeIn("sustained_vocal_energy");
        }
      }
    } else {
      // Audio level dipped below threshold — reset window unless momentary pause in speech
      if (this.speechStartTime !== null && now - this.speechStartTime < 80) {
        // Allow tiny micro-gap between syllables
      } else {
        this.speechStartTime = null;
      }
    }
  }

  /**
   * Called when speech recognition emits interim words while assistant is speaking.
   * Speech transcript is high-confidence proof of intentional human speech!
   */
  processTranscript(interimText: string) {
    if (!this.isMonitoring || this.triggered) return;

    const clean = interimText.trim();
    if (clean.length >= 2) {
      // Intentional speech recognized
      this.triggerBargeIn("recognized_speech_words");
    }
  }

  private triggerBargeIn(reason: string) {
    if (this.triggered) return;
    this.triggered = true;
    this.isMonitoring = false;
    this.speechStartTime = null;
    this.config.onInterrupt();
  }
}
