import type { NanviApiClient } from "../../api";

type RecognitionCallbacks = {
  onInterimText?: (text: string) => void;
  onFinalText?: (text: string) => void;
  onError?: (error: string) => void;
  onAudioLevel?: (level: number) => void;
  onSilenceTimeout?: () => void;
  onSpeechStarted?: () => void;
};

// Cross-browser speech recognition typing
interface IWindowSpeechRecognition extends EventTarget {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  maxAlternatives: number;
  start: () => void;
  stop: () => void;
  abort: () => void;
  onresult: ((event: any) => void) | null;
  onerror: ((event: any) => void) | null;
  onend: (() => void) | null;
  onstart: (() => void) | null;
}

class SpeechRecognitionService {
  private recognition: IWindowSpeechRecognition | null = null;
  private audioContext: AudioContext | null = null;
  private mediaStream: MediaStream | null = null;
  private analyser: AnalyserNode | null = null;
  private animFrameId: number | null = null;
  private isListening = false;
  private callbacks: RecognitionCallbacks = {};
  private silenceTimer: number | null = null;
  private lastSpokenTime = 0;
  private speechDetected = false;
  private mediaRecorder: MediaRecorder | null = null;
  private audioChunks: Blob[] = [];
  private sourceNode: MediaStreamAudioSourceNode | null = null;
  private activeSessionId = 0;

  constructor() {
    if (typeof window !== "undefined") {
      window.addEventListener("beforeunload", () => {
        this.stopListening();
      });
      window.addEventListener("pagehide", () => {
        this.stopListening();
      });
    }
  }

  get supported(): boolean {
    return (
      typeof window !== "undefined" &&
      ("SpeechRecognition" in window ||
        "webkitSpeechRecognition" in window ||
        Boolean(navigator.mediaDevices?.getUserMedia))
    );
  }

  async checkPermission(): Promise<"granted" | "denied" | "prompt"> {
    try {
      if (navigator.permissions && navigator.permissions.query) {
        const status = await navigator.permissions.query({ name: "microphone" as PermissionName });
        return status.state;
      }
    } catch {
      // ignore
    }
    return "prompt";
  }

  async requestMicrophone(): Promise<MediaStream | null> {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      return null;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true, // Enable AGC so Bluetooth headsets (e.g. Rockerz) and quiet mics receive adequate gain
        },
      });
      return stream;
    } catch (err: any) {
      if (err.name === "NotAllowedError" || err.name === "PermissionDeniedError") {
        this.callbacks.onError?.("Microphone permission was denied. Please allow microphone in browser address bar.");
      }
      return null;
    }
  }

  async startListening(callbacks: RecognitionCallbacks): Promise<boolean> {
    this.callbacks = callbacks;
    this.stopListening();

    const sessionId = ++this.activeSessionId;
    this.isListening = true;

    try {
      // 1. Obtain microphone stream
      const stream = await this.requestMicrophone();

      // Guard against race condition: if user exited voice mode while permission prompt was open
      if (sessionId !== this.activeSessionId || !this.isListening) {
        if (stream) {
          stream.getTracks().forEach((track) => {
            track.stop();
            track.enabled = false;
          });
        }
        return false;
      }

      if (!stream) {
        callbacks.onError?.("Microphone access is required for Voice Assistant. Please click 'Allow Microphone'.");
        this.isListening = false;
        return false;
      }

      this.mediaStream = stream;

      // 2. Setup AudioContext analyser for live VU meter & speech activity
      this.setupAudioAnalysis(this.mediaStream);

      // 3. Setup continuous MediaRecorder for bulletproof Whisper fallback
      this.startMediaRecorder(this.mediaStream);

      // 4. Initialize browser SpeechRecognition if available
      const SpeechClass =
        (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

      if (SpeechClass) {
        try {
          const recognition: IWindowSpeechRecognition = new SpeechClass();
          // Using continuous = false is significantly more reliable across Chrome versions
          // because it fires final results immediately upon sentence pauses instead of buffering
          recognition.continuous = true;
          recognition.interimResults = true;
          recognition.lang = "en-US";
          recognition.maxAlternatives = 1;

          recognition.onstart = () => {
            this.isListening = true;
            console.log("[Nanvi Voice] SpeechRecognition started.");
          };

          recognition.onresult = (event: any) => {
            let interim = "";
            let final = "";

            for (let i = event.resultIndex; i < event.results.length; ++i) {
              const transcript = event.results[i][0].transcript;
              if (event.results[i].isFinal) {
                final += transcript;
              } else {
                interim += transcript;
              }
            }

            if (interim) {
              this.speechDetected = true;
              this.lastSpokenTime = Date.now();
              this.callbacks.onSpeechStarted?.();
              this.callbacks.onInterimText?.(interim);
              this.resetSilenceTimer();
            }

            if (final.trim()) {
              this.speechDetected = false;
              this.lastSpokenTime = Date.now();
              this.clearSilenceTimer();
              console.log("[Nanvi Voice] SpeechRecognition final transcript:", final.trim());
              this.callbacks.onFinalText?.(final.trim());
            }
          };

          recognition.onerror = (event: any) => {
            console.warn("[Nanvi Voice] SpeechRecognition notice:", event.error);
            if (event.error === "no-speech") {
              return;
            }
            if (event.error === "network") {
              console.log("[Nanvi Voice] Google speech network unavailable; Whisper audio fallback active.");
              return;
            }
            if (event.error === "not-allowed") {
              this.callbacks.onError?.("Microphone permission was denied.");
              this.stopListening();
              return;
            }
          };

          recognition.onend = () => {
            // In Chrome, restart cleanly with a micro-delay to prevent InvalidStateError
            if (this.isListening && this.recognition === recognition) {
              setTimeout(() => {
                if (this.isListening && this.recognition === recognition) {
                  try {
                    recognition.start();
                  } catch (e) {
                    // Ignore if already running or shutting down
                  }
                }
              }, 120);
            }
          };

          this.recognition = recognition;
          recognition.start();
        } catch (recErr) {
          console.warn("[Nanvi Voice] SpeechRecognition initialization failed, relying on Whisper fallback:", recErr);
        }
      }

      this.isListening = true;
      return true;
    } catch (err: any) {
      this.callbacks.onError?.(err?.message || "Failed to start speech recognition.");
      return false;
    }
  }

  private setupAudioAnalysis(stream: MediaStream) {
    try {
      const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
      if (!AudioCtx) return;

      this.audioContext = new AudioCtx();
      if (this.audioContext.state === "suspended") {
        void this.audioContext.resume();
      }

      const source = this.audioContext.createMediaStreamSource(stream);
      const analyser = this.audioContext.createAnalyser();
      analyser.fftSize = 256;
      analyser.smoothingTimeConstant = 0.5;
      source.connect(analyser);
      this.sourceNode = source;
      this.analyser = analyser;

      const dataArray = new Uint8Array(analyser.frequencyBinCount);

      const checkVolume = () => {
        if (!this.analyser || !this.isListening) return;

        this.analyser.getByteFrequencyData(dataArray);
        let sum = 0;
        for (let i = 0; i < dataArray.length; i++) {
          sum += dataArray[i];
        }
        const avg = sum / dataArray.length;
        // Resilient volume normalization across all hardware types (Bluetooth headsets like Rockerz, laptops, USB mics)
        // Background floor in quiet room is avg < 2.5. Human voice raises avg to 8 - 45.
        const normalized = Math.min(1.0, Math.max(0, (avg - 2.5) / 42));

        // Detect user speech activity via microphone volume
        if (normalized > 0.08) {
          this.lastSpokenTime = Date.now();
          if (!this.speechDetected) {
            this.speechDetected = true;
            this.callbacks.onSpeechStarted?.();
          }
          this.resetSilenceTimer();
        }

        this.callbacks.onAudioLevel?.(normalized);
        this.animFrameId = requestAnimationFrame(checkVolume);
      };

      this.animFrameId = requestAnimationFrame(checkVolume);
    } catch (e) {
      console.warn("[Nanvi Voice] AudioContext setup error:", e);
    }
  }

  private startMediaRecorder(stream: MediaStream) {
    try {
      this.audioChunks = [];
      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : MediaRecorder.isTypeSupported("audio/webm")
        ? "audio/webm"
        : "audio/ogg";

      const recorder = new MediaRecorder(stream, { mimeType });
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          this.audioChunks.push(e.data);
          // Keep sliding window of last ~15 seconds to avoid memory ballooning
          if (this.audioChunks.length > 60) {
            this.audioChunks.splice(0, 10);
          }
        }
      };
      this.mediaRecorder = recorder;
      recorder.start(250);
    } catch (e) {
      console.warn("[Nanvi Voice] MediaRecorder start error:", e);
    }
  }

  async getRecordedAudioBlob(): Promise<Blob | null> {
    if (this.mediaRecorder && this.mediaRecorder.state === "recording") {
      try {
        this.mediaRecorder.requestData();
      } catch {
        // ignore
      }
    }
    // Short wait for dataavailable event to push latest audio chunk
    await new Promise((r) => setTimeout(r, 80));
    if (!this.audioChunks || this.audioChunks.length === 0) return null;
    const mimeType = this.mediaRecorder?.mimeType || "audio/webm";
    return new Blob(this.audioChunks, { type: mimeType });
  }

  clearRecordedAudio(): void {
    this.audioChunks = [];
    this.speechDetected = false;
  }

  async transcribeViaBackend(api: NanviApiClient): Promise<string | null> {
    const blob = await this.getRecordedAudioBlob();
    if (!blob || blob.size < 1000) return null;

    try {
      const base64 = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onloadend = () => {
          const res = reader.result as string;
          const base64Data = res.split(",")[1];
          resolve(base64Data);
        };
        reader.onerror = reject;
        reader.readAsDataURL(blob);
      });

      const mimeType = blob.type || "audio/webm";
      console.log(`[Nanvi Voice] Sending ${Math.round(blob.size / 1024)} KB audio to Groq Whisper...`);
      const res = await api.voiceTranscribe(base64, mimeType);
      console.log("[Nanvi Voice] Groq Whisper transcribed:", res.text);
      return res.text;
    } catch (err) {
      console.warn("[Nanvi Voice] Backend transcription fallback error:", err);
      return null;
    }
  }

  private resetSilenceTimer() {
    this.clearSilenceTimer();
    // 1500ms of silence after detected speech triggers finalization
    this.silenceTimer = window.setTimeout(() => {
      if (this.speechDetected && Date.now() - this.lastSpokenTime >= 1200) {
        this.speechDetected = false;
        this.callbacks.onSilenceTimeout?.();
      }
    }, 1500);
  }

  private clearSilenceTimer() {
    if (this.silenceTimer !== null) {
      clearTimeout(this.silenceTimer);
      this.silenceTimer = null;
    }
  }

  stopListening(): void {
    // Invalidate any in-flight requests immediately
    this.activeSessionId++;
    this.isListening = false;
    this.speechDetected = false;
    this.clearSilenceTimer();

    if (this.animFrameId !== null) {
      cancelAnimationFrame(this.animFrameId);
      this.animFrameId = null;
    }

    if (this.recognition) {
      try {
        this.recognition.abort();
      } catch {
        // ignore
      }
      this.recognition = null;
    }

    if (this.mediaRecorder) {
      try {
        if (this.mediaRecorder.state !== "inactive") {
          this.mediaRecorder.stop();
        }
      } catch {
        // ignore
      }
      this.mediaRecorder = null;
    }

    // Forcefully stop and disable all audio tracks to immediately release hardware mic
    if (this.mediaStream) {
      try {
        this.mediaStream.getTracks().forEach((track) => {
          track.stop();
          track.enabled = false;
        });
      } catch (e) {
        console.warn("[Nanvi Voice] Error stopping media tracks:", e);
      }
      this.mediaStream = null;
    }

    if (this.sourceNode) {
      try {
        this.sourceNode.disconnect();
      } catch {
        // ignore
      }
      this.sourceNode = null;
    }

    if (this.analyser) {
      try {
        this.analyser.disconnect();
      } catch {
        // ignore
      }
      this.analyser = null;
    }

    if (this.audioContext) {
      try {
        void this.audioContext.close().catch(() => {});
      } catch {
        // ignore
      }
      this.audioContext = null;
    }

    this.callbacks.onAudioLevel?.(0);
  }
}

export const speechRecognitionService = new SpeechRecognitionService();
