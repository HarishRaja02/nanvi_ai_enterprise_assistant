import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import React from "react";
import { BargeInDetector } from "./bargeInDetector";
import { VoiceControls } from "./VoiceControls";
import { VoiceContextPanel } from "./VoiceContextPanel";
import { VOICE_PROFILES } from "./voiceTypes";
import type { SourceView } from "../../lib/sources";
import { Composer } from "../../components/chat/Composer";
import {
  cleanSpokenText,
  cleanDisplayText,
  sanitizeUserQueryForAI,
} from "./speechSynthesisService";
import { speechRecognitionService } from "./speechRecognitionService";

describe("Voice Assistant Mode — Core & Component Tests", () => {
  describe("Composer Voice Trigger Button", () => {
    it("renders the Voice Assistant trigger button when onOpenVoiceMode is provided", () => {
      const handleOpenVoice = vi.fn();
      render(
        <Composer
          busy={false}
          onSend={async () => true}
          focusToken={0}
          onOpenVoiceMode={handleOpenVoice}
        />
      );

      const voiceBtn = screen.getByRole("button", { name: /Open Voice Assistant Mode/i });
      expect(voiceBtn).toBeInTheDocument();
      expect(voiceBtn).toHaveTextContent(/Voice/i);

      fireEvent.click(voiceBtn);
      expect(handleOpenVoice).toHaveBeenCalledTimes(1);
    });
  });

  describe("Barge-In Detector & Noise Filtering", () => {
    beforeEach(() => {
      vi.useFakeTimers();
    });

    it("does NOT interrupt assistant for brief accidental noises (< 250ms)", () => {
      const handleInterrupt = vi.fn();
      const detector = new BargeInDetector({
        speechThreshold: 0.28,
        minSpeechDurationMs: 250,
        onInterrupt: handleInterrupt,
      });

      detector.start();

      // Simulate a brief noise spike (e.g. keyboard click, mic tap) of 100ms
      detector.processAudioLevel(0.65);
      vi.advanceTimersByTime(100);
      detector.processAudioLevel(0.05); // noise drops
      vi.advanceTimersByTime(200);

      expect(handleInterrupt).not.toHaveBeenCalled();
    });

    it("interrupts assistant when user speaks continuously for >= 250ms", () => {
      const handleInterrupt = vi.fn();
      const detector = new BargeInDetector({
        speechThreshold: 0.28,
        minSpeechDurationMs: 250,
        onInterrupt: handleInterrupt,
      });

      detector.start();

      // Sustained speech audio
      detector.processAudioLevel(0.45);
      vi.advanceTimersByTime(120);
      detector.processAudioLevel(0.5);
      vi.advanceTimersByTime(150);
      detector.processAudioLevel(0.52);

      expect(handleInterrupt).toHaveBeenCalledTimes(1);
    });

    it("immediately triggers interruption when recognized speech words are received", () => {
      const handleInterrupt = vi.fn();
      const detector = new BargeInDetector({
        speechThreshold: 0.28,
        minSpeechDurationMs: 250,
        onInterrupt: handleInterrupt,
      });

      detector.start();
      detector.processTranscript("Wait, only expenses");

      expect(handleInterrupt).toHaveBeenCalledTimes(1);
    });
  });

  describe("VoiceControls Component", () => {
    it("renders Mute, Cancel, and Voice Selector with proper accessibility", () => {
      const handleToggleMute = vi.fn();
      const handleCancel = vi.fn();
      const handleSelectProfile = vi.fn();

      render(
        <VoiceControls
          state="speaking"
          isMuted={false}
          activeProfile={VOICE_PROFILES[0]}
          onToggleMute={handleToggleMute}
          onCancel={handleCancel}
          onSelectProfile={handleSelectProfile}
        />
      );

      // Mute button
      const muteBtn = screen.getByRole("button", { name: /Mute microphone/i });
      expect(muteBtn).toBeInTheDocument();
      fireEvent.click(muteBtn);
      expect(handleToggleMute).toHaveBeenCalledTimes(1);

      // Cancel button
      const cancelBtn = screen.getByRole("button", { name: /Cancel active action/i });
      expect(cancelBtn).toBeInTheDocument();
      fireEvent.click(cancelBtn);
      expect(handleCancel).toHaveBeenCalledTimes(1);

      // Voice Selector trigger
      const voiceTrigger = screen.getByRole("button", { name: /Voice: Nanvi Professional/i });
      expect(voiceTrigger).toBeInTheDocument();
      fireEvent.click(voiceTrigger);

      // Should open popover
      const warmOption = screen.getByText("Nanvi Warm");
      expect(warmOption).toBeInTheDocument();
      fireEvent.click(warmOption);
      expect(handleSelectProfile).toHaveBeenCalledWith(VOICE_PROFILES[1]);
    });

    it("displays unmuted state when isMuted is true", () => {
      render(
        <VoiceControls
          state="muted"
          isMuted={true}
          activeProfile={VOICE_PROFILES[0]}
          onToggleMute={vi.fn()}
          onCancel={vi.fn()}
          onSelectProfile={vi.fn()}
        />
      );

      const unmuteBtn = screen.getByRole("button", { name: /Unmute microphone/i });
      expect(unmuteBtn).toBeInTheDocument();
      expect(unmuteBtn).toHaveTextContent("Unmute");
    });
  });

  describe("VoiceContextPanel Component", () => {
    const mockSources: SourceView[] = [
      {
        id: "src-1",
        kind: "document",
        format: "PDF",
        title: "Finance_Q2_Report.pdf",
        page: 12,
      },
      {
        id: "src-2",
        kind: "email",
        format: "MAIL",
        title: "Q2 Financial Review from finance@company.com",
      },
    ];

    const mockPoints = [
      "Revenue increased by 12 percent.",
      "Cloud infrastructure was the largest software expense.",
    ];

    it("renders empty state messages when no data is present", () => {
      render(
        <VoiceContextPanel
          importantPoints={[]}
          sources={[]}
          onOpenSource={vi.fn()}
        />
      );

      expect(screen.getByText("Important points will appear here as we talk.")).toBeInTheDocument();
      expect(screen.getByText("No sources used yet.")).toBeInTheDocument();
    });

    it("renders populated Important Points and clickable Sources correctly", () => {
      const handleOpenSource = vi.fn();
      render(
        <VoiceContextPanel
          importantPoints={mockPoints}
          sources={mockSources}
          capabilities={["DATABASE", "EMAIL"]}
          onOpenSource={handleOpenSource}
        />
      );

      // Key points
      expect(screen.getByText("01")).toBeInTheDocument();
      expect(screen.getByText("Revenue increased by 12 percent.")).toBeInTheDocument();
      expect(screen.getByText("02")).toBeInTheDocument();
      expect(screen.getByText("Cloud infrastructure was the largest software expense.")).toBeInTheDocument();

      // Sources
      expect(screen.getByText("2 sources")).toBeInTheDocument();
      const pdfSourceBtn = screen.getByRole("button", { name: /Inspect citation: Finance_Q2_Report.pdf/i });
      expect(pdfSourceBtn).toBeInTheDocument();
      expect(screen.getByText("Page 12")).toBeInTheDocument();

      fireEvent.click(pdfSourceBtn);
      expect(handleOpenSource).toHaveBeenCalledWith(mockSources[0]);
    });
  });

  describe("Text Sanitization & Humanization for Speech", () => {
    it("cleanSpokenText strips all asterisks, markdown, hashes, and code blocks", () => {
      const raw = `
### Summary of Operations
According to **Q2** records [1], revenue grew to $4.2M.

* Total *expenses* dropped by 6%.
* Vendor contracts renewed.

Details at https://example.com/data
\`\`\`sql
SELECT * FROM users;
\`\`\`
`;
      const spoken = cleanSpokenText(raw);

      // Must NEVER contain asterisks
      expect(spoken).not.toContain("*");
      expect(spoken).not.toContain("###");
      expect(spoken).not.toContain("[1]");
      expect(spoken).not.toContain("https://");
      expect(spoken).not.toContain("```");

      // Currencies and figures expanded humanely
      expect(spoken).toContain("4.2 million dollars");
      expect(spoken).toContain("Quarter 2");
      expect(spoken).toContain("Total expenses dropped");
    });

    it("cleanDisplayText removes asterisks and markdown tokens for chat bubble readability", () => {
      const formatted = "**Quarterly Highlights:** * Revenue up * Churn down [Source 1]";
      const clean = cleanDisplayText(formatted);

      expect(clean).not.toContain("*");
      expect(clean).not.toContain("[Source 1]");
      expect(clean).toBe("Quarterly Highlights: Revenue up Churn down");
    });

    it("sanitizeUserQueryForAI removes stray symbols from voice transcription before AI processing", () => {
      const rawUserVoice = "What was the *total* revenue in #Q2? <script>";
      const sanitized = sanitizeUserQueryForAI(rawUserVoice);

      expect(sanitized).not.toContain("*");
      expect(sanitized).not.toContain("#");
      expect(sanitized).not.toContain("<");
      expect(sanitized).not.toContain(">");
      expect(sanitized).toBe("What was the total revenue in Q2? script");
    });
  });

  describe("Microphone Lifecycle & Immediate Hardware Release on Exit", () => {
    it("stopListening immediately stops and disables all media tracks", () => {
      const mockTrackStop = vi.fn();
      const mockTrack = {
        stop: mockTrackStop,
        enabled: true,
      };

      // Assign mock stream
      (speechRecognitionService as any).mediaStream = {
        getTracks: () => [mockTrack],
      };

      expect((speechRecognitionService as any).mediaStream).not.toBeNull();

      speechRecognitionService.stopListening();

      // Tracks must be stopped and disabled so browser hardware light turns off
      expect(mockTrackStop).toHaveBeenCalledTimes(1);
      expect(mockTrack.enabled).toBe(false);
      expect((speechRecognitionService as any).mediaStream).toBeNull();
    });

    it("invalidates activeSessionId so in-flight microphone prompt is aborted if user exits", () => {
      const prevSession = (speechRecognitionService as any).activeSessionId;
      speechRecognitionService.stopListening();
      const nextSession = (speechRecognitionService as any).activeSessionId;

      expect(nextSession).toBeGreaterThan(prevSession);
    });
  });
});
