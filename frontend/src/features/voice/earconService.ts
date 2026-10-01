/**
 * Subtle Enterprise Earcon Service — Milestone 8.
 *
 * Uses the Web Audio API to synthesize discrete, warm, non-intrusive auditory cues (earcons)
 * for listening, working, and done states in accordance with Section 7.7 of docs/NANVI_SPEC.md.
 *
 * Synthesized purely via native oscillators and envelope gains — zero external MP3/WAV assets needed.
 */
class EarconService {
  private audioCtx: AudioContext | null = null;
  private enabled: boolean = true;
  private masterGain: number = 0.06; // Soft, ambient, executive volume

  private getContext(): AudioContext | null {
    if (typeof window === "undefined") return null;
    const AudioContextClass = window.AudioContext || (window as any).webkitAudioContext;
    if (!AudioContextClass) return null;

    if (!this.audioCtx) {
      try {
        this.audioCtx = new AudioContextClass();
      } catch {
        return null;
      }
    }
    if (this.audioCtx.state === "suspended") {
      void this.audioCtx.resume();
    }
    return this.audioCtx;
  }

  public setEnabled(enabled: boolean): void {
    this.enabled = enabled;
  }

  public isEnabled(): boolean {
    return this.enabled;
  }

  /**
   * Listening earcon: Gentle rising two-tone chime (440Hz -> 660Hz)
   * Signals that Nanvi is now listening.
   */
  public playListening(): void {
    if (!this.enabled) return;
    const ctx = this.getContext();
    if (!ctx) return;

    try {
      const now = ctx.currentTime;
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();

      osc.type = "sine";
      osc.frequency.setValueAtTime(440, now);
      osc.frequency.exponentialRampToValueAtTime(659.25, now + 0.12);

      gain.gain.setValueAtTime(0.001, now);
      gain.gain.linearRampToValueAtTime(this.masterGain, now + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.22);

      osc.connect(gain);
      gain.connect(ctx.destination);

      osc.start(now);
      osc.stop(now + 0.24);
    } catch {
      // Audio autoplay policy fallback
    }
  }

  /**
   * Working earcon: Soft, discrete subtle ping (520Hz)
   * Signals that agent processing has started.
   */
  public playWorking(): void {
    if (!this.enabled) return;
    const ctx = this.getContext();
    if (!ctx) return;

    try {
      const now = ctx.currentTime;
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();

      osc.type = "sine";
      osc.frequency.setValueAtTime(523.25, now); // C5 note

      gain.gain.setValueAtTime(0.001, now);
      gain.gain.linearRampToValueAtTime(this.masterGain * 0.7, now + 0.015);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.15);

      osc.connect(gain);
      gain.connect(ctx.destination);

      osc.start(now);
      osc.stop(now + 0.16);
    } catch {
      // Audio autoplay policy fallback
    }
  }

  /**
   * Done earcon: Pleasant completion chime (587Hz -> 880Hz)
   * Signals that verified data and response have completed.
   */
  public playDone(): void {
    if (!this.enabled) return;
    const ctx = this.getContext();
    if (!ctx) return;

    try {
      const now = ctx.currentTime;
      const osc1 = ctx.createOscillator();
      const osc2 = ctx.createOscillator();
      const gain = ctx.createGain();

      osc1.type = "sine";
      osc1.frequency.setValueAtTime(587.33, now); // D5
      osc1.frequency.exponentialRampToValueAtTime(880, now + 0.14); // A5

      osc2.type = "triangle";
      osc2.frequency.setValueAtTime(880, now + 0.07);

      gain.gain.setValueAtTime(0.001, now);
      gain.gain.linearRampToValueAtTime(this.masterGain, now + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.28);

      osc1.connect(gain);
      osc2.connect(gain);
      gain.connect(ctx.destination);

      osc1.start(now);
      osc1.stop(now + 0.3);
      osc2.start(now + 0.07);
      osc2.stop(now + 0.3);
    } catch {
      // Audio autoplay policy fallback
    }
  }
}

export const earconService = new EarconService();
