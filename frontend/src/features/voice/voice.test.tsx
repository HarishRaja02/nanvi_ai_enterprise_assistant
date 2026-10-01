import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import React from "react";
import { BargeInDetector } from "./bargeInDetector";
import { VoiceControls } from "./VoiceControls";
import { VoiceContextPanel } from "./VoiceContextPanel";
import { GlassUICard } from "./GlassUICard";
import { LiveCaptionBar } from "./LiveCaptionBar";
import { earconService } from "./earconService";
import { VoiceAssistantMode } from "./VoiceAssistantMode";
import { VOICE_PROFILES } from "./voiceTypes";
import { isHighRiskIntent, getIntentMetadata } from "./intentRegistry";
import type { SourceView } from "../../lib/sources";
import { Composer } from "../../components/chat/Composer";
import {
  cleanSpokenText,
  cleanDisplayText,
  sanitizeUserQueryForAI,
  splitIntoSentences,
  speechSynthesisService,
} from "./speechSynthesisService";
import {
  speechRecognitionService,
  applyPhoneticCorrections,
} from "./speechRecognitionService";
import {
  analyzeCompleteness,
  resolveSelfRepair,
  TURN_TIMEOUTS,
} from "./turnDetector";

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

  describe("Milestone 2 — Sentence-Level Streaming & Low-Latency Audio", () => {
    it("splitIntoSentences accurately decomposes multi-sentence text", () => {
      const text = "Revenue is up 14% this quarter. Enterprise sales drove most growth! Would you like the breakdown?";
      const sentences = splitIntoSentences(text);

      expect(sentences).toHaveLength(3);
      expect(sentences[0]).toBe("Revenue is up 14 percent this quarter.");
      expect(sentences[1]).toBe("Enterprise sales drove most growth!");
      expect(sentences[2]).toBe("Would you like the breakdown?");
    });

    it("BargeInDetector interrupts within 180ms of sustained vocal energy", () => {
      const handleInterrupt = vi.fn();
      const detector = new BargeInDetector({
        speechThreshold: 0.28,
        minSpeechDurationMs: 180,
        onInterrupt: handleInterrupt,
      });

      detector.start();

      // User begins speaking: audio level 0.40
      detector.processAudioLevel(0.40);
      vi.advanceTimersByTime(100);
      expect(handleInterrupt).not.toHaveBeenCalled();

      // Sustained past 180ms (< 200ms target)
      vi.advanceTimersByTime(85);
      detector.processAudioLevel(0.42);

      expect(handleInterrupt).toHaveBeenCalledTimes(1);
    });

    it("speechSynthesisService.stop cancels playback immediately", () => {
      speechSynthesisService.stop();
      expect((speechSynthesisService as any).isSpeaking).toBe(false);
      expect((speechSynthesisService as any).currentSource).toBeNull();
      expect((speechSynthesisService as any).currentAudioElement).toBeNull();
    });
  });

  describe("Milestone 3 — Semantic Completeness Analysis (Turn Detection)", () => {
    it("detects trailing hesitation words as incomplete and recommends extended wait time", () => {
      const result = analyzeCompleteness("Show me revenue for... um...");
      expect(result.status).toBe("incomplete");
      expect(result.reason).toBe("trailing_hesitation");
      expect(result.recommendedWaitMs).toBe(TURN_TIMEOUTS.EXTENDED_INCOMPLETE);
    });

    it("detects trailing conjunctions as incomplete thoughts", () => {
      const result = analyzeCompleteness("Show total expenses and");
      expect(result.status).toBe("incomplete");
      expect(result.reason).toBe("trailing_conjunction");
      expect(result.recommendedWaitMs).toBe(TURN_TIMEOUTS.EXTENDED_INCOMPLETE);
    });

    it("detects trailing prepositions as incomplete thoughts", () => {
      const result = analyzeCompleteness("Find invoice for");
      expect(result.status).toBe("incomplete");
      expect(result.reason).toBe("trailing_preposition");
      expect(result.recommendedWaitMs).toBe(TURN_TIMEOUTS.EXTENDED_INCOMPLETE);
    });

    it("detects trailing determiners as incomplete thoughts", () => {
      const result = analyzeCompleteness("Who is the");
      expect(result.status).toBe("incomplete");
      expect(result.reason).toBe("trailing_determiner");
      expect(result.recommendedWaitMs).toBe(TURN_TIMEOUTS.EXTENDED_INCOMPLETE);
    });

    it("flags hesitation-only vocal utterances to prevent spurious backend execution", () => {
      const res1 = analyzeCompleteness("um...");
      expect(res1.status).toBe("hesitation_only");
      expect(res1.recommendedWaitMs).toBe(TURN_TIMEOUTS.HESITATION_ONLY);

      const res2 = analyzeCompleteness("uh hmm");
      expect(res2.status).toBe("hesitation_only");
    });

    it("identifies grammatically complete thoughts and concise follow-ups with snappy wait times", () => {
      const completeRes = analyzeCompleteness("What was our Q2 revenue?");
      expect(completeRes.status).toBe("complete");
      expect(completeRes.reason).toBe("terminal_punctuation");
      expect(completeRes.recommendedWaitMs).toBe(TURN_TIMEOUTS.SNAPPY_COMPLETE);

      const followUpRes = analyzeCompleteness("Why?");
      expect(followUpRes.status).toBe("complete");
      expect(followUpRes.recommendedWaitMs).toBe(TURN_TIMEOUTS.SNAPPY_COMPLETE);

      const conciseRes = analyzeCompleteness("Only enterprise");
      expect(conciseRes.status).toBe("complete");
    });
  });

  describe("Milestone 3 — Conversational Self-Repair Resolution", () => {
    it("resolves entity corrections with 'no, I meant'", () => {
      const resolved = resolveSelfRepair("Show August... no, I meant September");
      expect(resolved).toBe("Show September");
    });

    it("resolves date/number corrections with 'sorry'", () => {
      const resolved = resolveSelfRepair("Revenue for 2023, sorry, 2024");
      expect(resolved).toBe("Revenue for 2024");
    });

    it("resolves department/entity corrections with 'actually'", () => {
      const resolved = resolveSelfRepair("List employees in marketing, actually, engineering");
      expect(resolved).toBe("List employees in engineering");
    });

    it("resolves full statement replacement with 'scratch that'", () => {
      const resolved = resolveSelfRepair("Delete draft, scratch that, show the invoices");
      expect(resolved).toBe("show the invoices");
    });

    it("preserves unmodified conversational queries unchanged", () => {
      const query = "What are the top three customers by revenue?";
      expect(resolveSelfRepair(query)).toBe(query);
    });
  });

  describe("Milestone 3 — Smart Turn Finalization & Hesitation Filtering", () => {
    beforeEach(() => {
      vi.useFakeTimers();
    });

    it("SpeechRecognitionService accumulates transcripts and clears on stopListening", () => {
      speechRecognitionService.stopListening();
      expect(speechRecognitionService.getAccumulatedTranscript()).toBe("");

      (speechRecognitionService as any).accumulatedTranscript = "Show me";
      (speechRecognitionService as any).currentInterim = "expenses";
      expect(speechRecognitionService.getAccumulatedTranscript()).toBe("Show me expenses");

      const finalized = speechRecognitionService.finalizeAccumulated();
      expect(finalized).toBe("Show me expenses");
      expect(speechRecognitionService.getAccumulatedTranscript()).toBe("");
    });
  });

  describe("Milestone 5 — Controlled Generative UI DSL Cards", () => {
    it("renders KPI Card correctly with metric label, value and trend", () => {
      render(
        <GlassUICard
          spec={{
            card_type: "kpi_card",
            priority: 0,
            data: {
              metric_label: "Total ARR",
              value: "$14.2M",
              unit: "USD",
              trend: "up",
              trend_value: "+18%",
              comparison_label: "vs. prior year",
            },
          }}
        />
      );

      expect(screen.getByTestId("ui-kpi-card")).toBeInTheDocument();
      expect(screen.getByText("Total ARR")).toBeInTheDocument();
      expect(screen.getByText("$14.2M")).toBeInTheDocument();
      expect(screen.getByText("+18%")).toBeInTheDocument();
      expect(screen.getByText("vs. prior year")).toBeInTheDocument();
    });

    it("renders Table Card with column headers and rows", () => {
      render(
        <GlassUICard
          spec={{
            card_type: "table_card",
            priority: 1,
            data: {
              title: "Quarterly Revenue",
              columns: [
                { key: "quarter", label: "Quarter" },
                { key: "amount", label: "Amount", align: "right" },
              ],
              rows: [
                { quarter: "Q1", amount: "$3.2M" },
                { quarter: "Q2", amount: "$4.1M" },
              ],
              total_rows: 2,
            },
          }}
        />
      );

      expect(screen.getByTestId("ui-table-card")).toBeInTheDocument();
      expect(screen.getByText("Quarterly Revenue")).toBeInTheDocument();
      expect(screen.getByText("Quarter")).toBeInTheDocument();
      expect(screen.getByText("Q1")).toBeInTheDocument();
      expect(screen.getByText("$4.1M")).toBeInTheDocument();
    });

    it("renders Source List card with file badges and relevance", () => {
      render(
        <GlassUICard
          spec={{
            card_type: "source_list",
            priority: 2,
            data: {
              sources: [
                {
                  title: "Financial_Report_2024.pdf",
                  file_type: "pdf",
                  relevance_score: 0.95,
                  snippet: "Full annual accounts approved by board.",
                },
              ],
            },
          }}
        />
      );

      expect(screen.getByTestId("ui-source-list")).toBeInTheDocument();
      expect(screen.getByText("Financial_Report_2024.pdf")).toBeInTheDocument();
      expect(screen.getByText("95%")).toBeInTheDocument();
      expect(screen.getByText("Full annual accounts approved by board.")).toBeInTheDocument();
    });

    it("renders Timeline Card with timestamped items", () => {
      render(
        <GlassUICard
          spec={{
            card_type: "timeline_card",
            priority: 1,
            data: {
              title: "Project Milestones",
              items: [
                { timestamp: "Jan 15", title: "Project Inception", detail: "Charter ratified" },
                { timestamp: "Feb 20", title: "Alpha Deployment", detail: "Internal testing" },
              ],
            },
          }}
        />
      );

      expect(screen.getByTestId("ui-timeline-card")).toBeInTheDocument();
      expect(screen.getByText("Project Milestones")).toBeInTheDocument();
      expect(screen.getByText("Jan 15")).toBeInTheDocument();
      expect(screen.getByText("Project Inception")).toBeInTheDocument();
      expect(screen.getByText("Charter ratified")).toBeInTheDocument();
    });

    it("renders Status Card with status and message", () => {
      render(
        <GlassUICard
          spec={{
            card_type: "status_card",
            priority: 0,
            data: {
              status: "success",
              title: "Export Ready",
              detail: "CSV summary generated successfully.",
            },
          }}
        />
      );

      expect(screen.getByTestId("ui-status-card")).toBeInTheDocument();
      expect(screen.getByText("Export Ready")).toBeInTheDocument();
      expect(screen.getByText("success")).toBeInTheDocument();
      expect(screen.getByText("CSV summary generated successfully.")).toBeInTheDocument();
    });

    it("renders Action Card and invokes onActionClick callback", () => {
      const handleAction = vi.fn();
      render(
        <GlassUICard
          spec={{
            card_type: "action_card",
            priority: 5,
            data: {
              title: "Recommended Follow-ups",
              actions: [
                { label: "Compare with Last Year", intent: "compare_last_year" },
                { label: "View Invoices", intent: "view_invoices" },
              ],
            },
          }}
          onActionClick={handleAction}
        />
      );

      expect(screen.getByTestId("ui-action-card")).toBeInTheDocument();
      const btn = screen.getByRole("button", { name: /Compare with Last Year/i });
      expect(btn).toBeInTheDocument();

      fireEvent.click(btn);
      expect(handleAction).toHaveBeenCalledWith("compare_last_year");
    });
  });

  describe("Milestone 6 — Intent Registry & Risk-Gated Confirmation", () => {
    it("distinguishes high-risk actions from low-risk read-only actions", () => {
      expect(isHighRiskIntent("send_confirmation")).toBe(true);
      expect(isHighRiskIntent("compare_previous_quarter")).toBe(false);
      expect(isHighRiskIntent("revenue_drivers")).toBe(false);
      expect(isHighRiskIntent("unknown_action")).toBe(false);
    });

    it("retrieves rich metadata for registered intents and formats unregistered ones cleanly", () => {
      const qMeta = getIntentMetadata("compare_previous_quarter");
      expect(qMeta.label).toBe("Compare with Last Quarter");
      expect(qMeta.category).toBe("finance");
      expect(qMeta.riskLevel).toBe("low");

      const sendMeta = getIntentMetadata("send_confirmation");
      expect(sendMeta.label).toBe("Confirm & Send Email");
      expect(sendMeta.riskLevel).toBe("high");

      const fallbackMeta = getIntentMetadata("custom_metric_breakdown");
      expect(fallbackMeta.label).toBe("Custom Metric Breakdown");
      expect(fallbackMeta.riskLevel).toBe("low");
    });
  });

  describe("Milestone 8 — Voice-Screen Sync, Captions & Earcons", () => {
    it("renders LiveCaptionBar with words and live badge when speaking", () => {
      render(
        <LiveCaptionBar
          spokenText="Revenue increased by fourteen percent this quarter."
          isSpeaking={true}
        />
      );

      expect(screen.getByTestId("live-caption-bar")).toBeInTheDocument();
      expect(screen.getByText(/Revenue/i)).toBeInTheDocument();
      expect(screen.getByText(/fourteen/i)).toBeInTheDocument();
      expect(screen.getByText(/Live/i)).toBeInTheDocument();
    });

    it("renders nothing in LiveCaptionBar when not speaking", () => {
      const { container } = render(
        <LiveCaptionBar
          spokenText="Revenue increased by fourteen percent this quarter."
          isSpeaking={false}
        />
      );
      expect(container.firstChild).toBeNull();
    });

    it("earconService supports enabling, disabling and safe execution", () => {
      expect(earconService.isEnabled()).toBe(true);
      earconService.setEnabled(false);
      expect(earconService.isEnabled()).toBe(false);

      // Verify safe calls do not throw when disabled
      expect(() => earconService.playListening()).not.toThrow();
      expect(() => earconService.playWorking()).not.toThrow();
      expect(() => earconService.playDone()).not.toThrow();

      // Re-enable
      earconService.setEnabled(true);
      expect(earconService.isEnabled()).toBe(true);
    });

    it("renders GlassUICard with highlighted styling when isHighlighted is true", () => {
      render(
        <GlassUICard
          spec={{
            card_type: "kpi_card",
            priority: 0,
            data: {
              metric_label: "Active Highlight Metric",
              value: "₹25.0 Cr",
            },
          }}
          isHighlighted={true}
        />
      );

      const kpiCard = screen.getByTestId("ui-kpi-card");
      expect(kpiCard).toBeInTheDocument();
      expect(kpiCard.className).toContain("border-cyan-400");
    });
  });

  describe("Milestone 9 — Privacy Mode, Sensitive Value Suppression & Low-Confidence Fallback", () => {
    it("tracks and resets speech recognition confidence", () => {
      expect(speechRecognitionService.getLastConfidence()).toBe(1.0);
      (speechRecognitionService as any).lastConfidence = 0.54;
      expect(speechRecognitionService.getLastConfidence()).toBe(0.54);

      speechRecognitionService.stopListening();
      expect(speechRecognitionService.getLastConfidence()).toBe(1.0);
    });

    it("renders Privacy Mode toggle button in VoiceAssistantMode and shows confirmation hint", () => {
      render(
        <VoiceAssistantMode
          api={{} as any}
          identity={{
            subject: "test",
            issuer: "nanvi",
            roles: ["Finance"],
            email: "test@nanvi.com",
            name: "Test User",
            department: "Finance",
            tenant_id: "tenant-1",
          }}
          conversationId="conv-test"
          onClose={vi.fn()}
          onOpenSource={vi.fn()}
        />
      );

      act(() => fireEvent.click(screen.getByTestId("voice-settings-toggle")));
      const privacyToggle = screen.getByTestId("voice-privacy-toggle");
      expect(privacyToggle).toBeInTheDocument();
      expect(privacyToggle).toHaveTextContent(/Privacy mode off/i);

      act(() => {
        fireEvent.click(privacyToggle);
      });
      expect(privacyToggle).toHaveTextContent(/Privacy mode on/i);
    });
  });

  describe("Milestone 10 — Indian Languages, Vocabulary Biasing, Adaptive Verbosity & Memory", () => {
    it("applies phonetic corrections to common enterprise mishearings", () => {
      expect(applyPhoneticCorrections("Status of aster on tech invoice")).toBe(
        "Status of Asteron Technologies invoice"
      );
      expect(applyPhoneticCorrections("Show me cloud nova documents")).toBe(
        "Show me CloudNova documents"
      );
      expect(applyPhoneticCorrections("Budget for project fenix")).toBe(
        "Budget for Project Phoenix"
      );
      expect(applyPhoneticCorrections("What is our ebidta margin?")).toBe(
        "What is our EBITDA margin?"
      );
      expect(applyPhoneticCorrections("Total spend was 15 lacs")).toBe(
        "Total spend was 15 lakh"
      );
    });

    it("keeps speech recognition fixed to English", () => {
      expect(speechRecognitionService.getPreferredLanguage()).toBe("en-IN");
    });

    it("renders verbosity controls and an English-only language label in VoiceAssistantMode", () => {
      render(
        <VoiceAssistantMode
          api={{} as any}
          identity={{
            subject: "test",
            issuer: "nanvi",
            roles: ["Finance"],
            email: "test@nanvi.com",
            name: "Test User",
            department: "Finance",
            tenant_id: "tenant-1",
          }}
          conversationId="conv-test"
          onClose={vi.fn()}
          onOpenSource={vi.fn()}
        />
      );

      act(() => fireEvent.click(screen.getByTestId("voice-settings-toggle")));
      const verbositySelector = screen.getByTestId("voice-verbosity-selector");
      expect(verbositySelector).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /concise/i })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /normal/i })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /detailed/i })).toBeInTheDocument();

      expect(screen.getByTestId("voice-language-label")).toHaveTextContent("English only");
      expect(screen.queryByTestId("voice-language-toggle")).not.toBeInTheDocument();

      act(() => {
        fireEvent.click(screen.getByRole("button", { name: /concise/i }));
      });
      expect(screen.getByRole("button", { name: /concise/i }).className).toContain("is-selected");

    });

    it("keeps advanced controls collapsed and Escape closes settings without exiting voice mode", () => {
      const onClose = vi.fn();
      render(
        <VoiceAssistantMode
          api={{} as any}
          identity={{ subject: "test", issuer: "nanvi", roles: ["Finance"] }}
          onClose={onClose}
          onOpenSource={vi.fn()}
        />
      );

      expect(screen.queryByTestId("voice-verbosity-selector")).not.toBeInTheDocument();
      act(() => fireEvent.click(screen.getByTestId("voice-settings-toggle")));
      expect(screen.getByTestId("voice-verbosity-selector")).toBeInTheDocument();
      act(() => fireEvent.keyDown(window, { key: "Escape" }));
      expect(screen.queryByTestId("voice-verbosity-selector")).not.toBeInTheDocument();
      expect(onClose).not.toHaveBeenCalled();
    });
  });
});
