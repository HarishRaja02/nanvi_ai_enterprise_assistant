import { afterEach, describe, expect, it, vi } from "vitest";
import type { NanviApiClient } from "../../api";
import { speechSynthesisService } from "./speechSynthesisService";
import { VOICE_PROFILES } from "./voiceTypes";

describe("speechSynthesisService startup", () => {
  afterEach(() => {
    speechSynthesisService.endSession();
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it("falls back to browser speech promptly when neural synthesis is slow", async () => {
    vi.useFakeTimers();
    const onError = vi.fn();
    const api = {
      voiceSynthesize: vi.fn(() => new Promise<Blob>(() => {})),
    } as unknown as NanviApiClient;

    const response = speechSynthesisService.speakStream("A short answer.", VOICE_PROFILES[0], { onError }, api);
    await vi.advanceTimersByTimeAsync(4000);
    await response;

    expect(api.voiceSynthesize).toHaveBeenCalledOnce();
    expect(onError).toHaveBeenCalledWith("Speech synthesis not supported in this browser.");
  });

  it("keeps one speech engine for the rest of the voice session after fallback", async () => {
    vi.useFakeTimers();
    speechSynthesisService.beginSession();
    const api = {
      voiceSynthesize: vi.fn(() => new Promise<Blob>(() => {})),
    } as unknown as NanviApiClient;

    const firstTurn = speechSynthesisService.speakStream("First answer.", VOICE_PROFILES[0], {}, api);
    await vi.advanceTimersByTimeAsync(4000);
    await firstTurn;
    await speechSynthesisService.speakStream("Second answer.", VOICE_PROFILES[0], {}, api);

    expect(api.voiceSynthesize).toHaveBeenCalledOnce();
  });

  it("falls back to browser speech when neural audio playback is rejected", async () => {
    const onError = vi.fn();
    class RejectedAudio {
      onplaying: (() => void) | null = null;
      onended: (() => void) | null = null;
      onerror: (() => void) | null = null;
      preload = "";
      src = "";
      currentTime = 0;
      pause() {}
      play() { return Promise.reject(new Error("Playback unavailable")); }
    }
    vi.stubGlobal("Audio", RejectedAudio);
    vi.stubGlobal("URL", {
      createObjectURL: vi.fn(() => "blob:voice-test"),
      revokeObjectURL: vi.fn(),
    });
    const api = {
      voiceSynthesize: vi.fn().mockResolvedValue(new Blob(["audio"])),
    } as unknown as NanviApiClient;

    await speechSynthesisService.speakStream("A short answer.", VOICE_PROFILES[0], { onError }, api);

    expect(onError).toHaveBeenCalledWith("Speech synthesis not supported in this browser.");
  });
});
