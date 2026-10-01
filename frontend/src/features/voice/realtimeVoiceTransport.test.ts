import { describe, expect, it } from "vitest";
import { pcm16ToBase64, toPcm16 } from "./realtimeVoiceTransport";

describe("realtime voice PCM framing", () => {
  it("converts float audio to little-endian 24 kHz PCM16 without clipping errors", () => {
    const pcm = toPcm16(new Float32Array([-1, -0.5, 0, 0.5, 1]), 24_000);
    expect(Array.from(pcm)).toEqual([-32768, -16384, 0, 16383, 32767]);
  });

  it("resamples common 48 kHz microphone input to 24 kHz and base64 encodes bytes", () => {
    const pcm = toPcm16(new Float32Array([0.25, 0.75, -0.25, -0.75]), 48_000);
    expect(Array.from(pcm)).toEqual([16383, -16384]);

    const decoded = atob(pcm16ToBase64(pcm));
    const view = new DataView(Uint8Array.from(decoded, (char) => char.charCodeAt(0)).buffer);
    expect(view.getInt16(0, true)).toBe(16383);
    expect(view.getInt16(2, true)).toBe(-16384);
  });
});
