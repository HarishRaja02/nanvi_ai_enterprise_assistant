import { FormEvent, KeyboardEvent, useEffect, useLayoutEffect, useRef, useState } from "react";
import { ArrowUp, BookOpen, FileText, Loader2, Mic, Paperclip, Sparkles, X } from "lucide-react";
import type { NanviApiClient } from "../../api";

const MAX_LENGTH = 4000;
const WARN_AT = 3600;
const MAX_HEIGHT = 180;

type Props = {
  busy: boolean;
  onSend: (text: string, rag?: boolean, activeDocumentId?: string) => Promise<boolean>;
  focusToken: number;
  ragEnabled?: boolean;
  onToggleRag?: (enabled: boolean) => void;
  api?: NanviApiClient;
  onOpenVoiceMode?: () => void;
};

export function Composer({
  busy,
  onSend,
  focusToken,
  ragEnabled = true,
  onToggleRag,
  api,
  onOpenVoiceMode,
}: Props) {
  const [value, setValue] = useState("");
  const [attachedFile, setAttachedFile] = useState<{ name: string; size: number } | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);

  // Hands-free Voice Input & Query Refinement State
  const [isListening, setIsListening] = useState(false);
  const [isRefining, setIsRefining] = useState(false);
  const [clarification, setClarification] = useState<{
    message: string;
    suggestions: string[];
  } | null>(null);

  const ref = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const recognitionRef = useRef<any>(null);
  const silenceTimerRef = useRef<any>(null);
  const accumulatedTranscriptRef = useRef<string>("");

  // Clean up speech recognition on unmount
  useEffect(() => {
    return () => {
      if (silenceTimerRef.current) {
        clearTimeout(silenceTimerRef.current);
      }
      if (recognitionRef.current) {
        try {
          recognitionRef.current.stop();
        } catch {
          // ignore
        }
      }
    };
  }, []);

  const stopListening = () => {
    if (silenceTimerRef.current) {
      clearTimeout(silenceTimerRef.current);
      silenceTimerRef.current = null;
    }
    if (recognitionRef.current) {
      try {
        recognitionRef.current.stop();
      } catch {
        // ignore
      }
      recognitionRef.current = null;
    }
    setIsListening(false);
  };

  const handleFinishSpeaking = async (rawSpokenText: string) => {
    stopListening();
    const spoken = rawSpokenText.trim();
    if (!spoken) return;

    setIsRefining(true);
    try {
      let refinedText = spoken;
      let shouldClarify = false;
      let clarificationMsg: string | null = null;
      let suggestionsList: string[] = [];

      if (api?.refineSpokenQuery) {
        try {
          const res = await api.refineSpokenQuery(spoken);
          if (res.status === "clarify") {
            shouldClarify = true;
            clarificationMsg =
              res.clarification ||
              "I couldn't identify the specific document or vendor name. Are you referring to one of these?";
            suggestionsList = res.suggestions || [];
          } else if (res.refined_query) {
            refinedText = res.refined_query;
          }
        } catch (apiErr) {
          console.warn("Refine query API call failed, using raw spoken text:", apiErr);
        }
      }

      if (shouldClarify) {
        setClarification({
          message:
            clarificationMsg || "Are you referring to one of these documents or vendors?",
          suggestions:
            suggestionsList.length > 0
              ? suggestionsList
              : [
                  "Sri Ganesh ReadyMix vendor find invoice",
                  "Show invoice aging breakdown",
                  "Summarize bridge contract agreement terms",
                ],
        });
        setIsRefining(false);
        return;
      }

      // Populate corrected query into textarea
      setValue(refinedText);
      setIsRefining(false);

      // Auto-send query hands-free without requiring the user to click anything!
      if (refinedText && !busy) {
        const sent = await onSend(refinedText, ragEnabled, attachedFile?.name);
        if (sent) {
          setValue("");
          setAttachedFile(null);
          if (fileInputRef.current) fileInputRef.current.value = "";
          if (ref.current) ref.current.style.height = "auto";
        }
      }
    } catch (err) {
      console.warn("Error processing refined voice query:", err);
      setIsRefining(false);
    }
  };

  const startListening = () => {
    setClarification(null);
    const SpeechClass =
      typeof window !== "undefined"
        ? (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
        : null;

    if (!SpeechClass) {
      setIsListening(true);
      return;
    }

    try {
      stopListening();
      const recognition = new SpeechClass();
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.lang =
        typeof navigator !== "undefined" && navigator.language ? navigator.language : "en-IN";

      recognition.onstart = () => {
        setIsListening(true);
        accumulatedTranscriptRef.current = "";
      };

      recognition.onresult = (event: any) => {
        let interim = "";
        let final = "";
        for (let i = 0; i < event.results.length; ++i) {
          const item = event.results[i][0];
          const transcript = item?.transcript || "";
          if (event.results[i].isFinal) {
            final = final ? `${final} ${transcript}` : transcript;
          } else {
            interim = interim ? `${interim} ${transcript}` : transcript;
          }
        }
        const currentFull = (final ? `${final} ${interim}` : interim).trim();
        if (currentFull) {
          accumulatedTranscriptRef.current = currentFull;
          setValue(currentFull);

          // Hands-free auto-detect end of speech: 1400ms of silence triggers query refinement & send
          if (silenceTimerRef.current) {
            clearTimeout(silenceTimerRef.current);
          }
          silenceTimerRef.current = setTimeout(() => {
            void handleFinishSpeaking(accumulatedTranscriptRef.current);
          }, 1400);
        }
      };

      recognition.onerror = (event: any) => {
        if (event.error === "no-speech") return;
        stopListening();
      };

      recognition.onend = () => {
        if (isListening && !isRefining) {
          setIsListening(false);
        }
      };

      recognitionRef.current = recognition;
      recognition.start();
    } catch (err) {
      console.warn("Speech recognition initialization error:", err);
      setIsListening(false);
    }
  };

  const handleVoiceClick = () => {
    onOpenVoiceMode?.();
    if (isListening) {
      stopListening();
    } else {
      startListening();
    }
  };

  // Auto-resize: starts compact (1 line), grows up to MAX_HEIGHT as text increases
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    const nextHeight = Math.min(el.scrollHeight, MAX_HEIGHT);
    el.style.height = `${Math.max(nextHeight, 26)}px`;
  }, [value]);

  // Focus only on explicit actions (new or resumed conversation)
  useEffect(() => {
    if (focusToken > 0) ref.current?.focus();
  }, [focusToken]);

  const submit = async (event?: FormEvent) => {
    event?.preventDefault();
    const text = value.trim();
    if (!text || busy) return;
    if (await onSend(text, ragEnabled, attachedFile?.name)) {
      setValue("");
      setAttachedFile(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
      if (ref.current) ref.current.style.height = "auto";
    }
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      void submit();
    }
  };

  const processFile = (file: File) => {
    setUploading(true);
    setUploadError(null);
    const reader = new FileReader();

    reader.onload = async () => {
      try {
        const base64 = (reader.result as string).split(",")[1];
        if (api?.uploadDocument) {
          await api.uploadDocument(file.name, base64);
        }
        setAttachedFile({ name: file.name, size: file.size });
        if (!value.trim()) {
          setValue(`Please analyze the attached document (${file.name}) and summarize its key findings.`);
        }
      } catch (err) {
        setUploadError(err instanceof Error ? err.message : "Failed to upload document into RAG");
      } finally {
        setUploading(false);
      }
    };

    reader.onerror = () => {
      setUploadError("Could not read local file.");
      setUploading(false);
    };

    reader.readAsDataURL(file);
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    processFile(file);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (!isDragOver) setIsDragOver(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file) {
      processFile(file);
    }
  };

  const nearLimit = value.length >= WARN_AT;

  return (
    <form
      className={`compact-composer ${isDragOver ? "is-drag-over" : ""}`}
      onSubmit={(e) => void submit(e)}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      noValidate
    >
      {/* Hidden file input for RAG document ingestion - supports all enterprise formats */}
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,.doc,.docx,.xls,.xlsx,.xlsm,.xltx,.csv,.tsv,.txt,.text,.md,.markdown,.log,.rtf,.json,.jsonl,.xml,.html,.htm,.ppt,.pptx,.yaml,.yml"
        style={{ display: "none" }}
        onChange={handleFileSelect}
        aria-label="Upload document to RAG"
      />

      {/* Attached file chip if present */}
      {attachedFile && (
        <div className="composer-attached-pill">
          <FileText size={13} aria-hidden="true" />
          <span className="truncate">{attachedFile.name}</span>
          <span className="attach-size">({Math.round(attachedFile.size / 1024)} KB)</span>
          <button
            type="button"
            className="remove-attach-btn"
            onClick={() => {
              setAttachedFile(null);
              if (fileInputRef.current) fileInputRef.current.value = "";
            }}
            aria-label="Remove attached file"
          >
            <X size={12} aria-hidden="true" />
          </button>
        </div>
      )}

      {uploading && (
        <div className="composer-uploading-pill">
          <Loader2 size={13} className="spin" aria-hidden="true" />
          <span>Adding file to company search…</span>
        </div>
      )}

      {uploadError && (
        <div className="composer-error-pill" role="alert">
          {uploadError}
        </div>
      )}

      {/* Spoken Query Clarification Banner if speech was unclear or ambiguous */}
      {clarification && (
        <div className="composer-voice-clarification" role="status">
          <div className="composer-clarification-header">
            <Sparkles size={14} className="clarification-sparkle-icon" />
            <span>{clarification.message}</span>
            <button
              type="button"
              className="clarification-close-btn"
              onClick={() => setClarification(null)}
              aria-label="Dismiss clarification"
            >
              <X size={14} />
            </button>
          </div>
          <div className="composer-clarification-suggestions">
            {clarification.suggestions.map((suggestion, idx) => (
              <button
                key={idx}
                type="button"
                className="clarification-chip"
                onClick={async () => {
                  setClarification(null);
                  setValue(suggestion);
                  await onSend(suggestion, ragEnabled, attachedFile?.name);
                  setValue("");
                }}
              >
                {suggestion}
              </button>
            ))}
            <button
              type="button"
              className="clarification-retry-btn"
              onClick={startListening}
            >
              <Mic size={12} />
              <span>Speak again</span>
            </button>
          </div>
        </div>
      )}

      {/* Auto-resizing Textarea: starts compact, expands when query grows */}
      <div className="composer-input-row">
        <label className="sr-only" htmlFor="nanvi-query">Ask Nanvi</label>
        <textarea
          id="nanvi-query"
          ref={ref}
          value={value}
          maxLength={MAX_LENGTH}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder={
            isListening
              ? "🎙 Listening to your voice... Speak naturally (auto-sends on pause)"
              : isRefining
              ? "✨ Refining and verifying query with AI..."
              : "Ask Nanvi across company documents, data & email..."
          }
          rows={1}
        />
      </div>

      {/* Bottom controls row inside the searchbar */}
      <div className="composer-bottom-bar">
        <div className="composer-bar-left">
          <button
            type="button"
            className="pill-action-btn"
            disabled={busy || uploading}
            onClick={() => fileInputRef.current?.click()}
            title="Attach document to analyze"
          >
            <Paperclip size={13} aria-hidden="true" />
            <span>Attach File</span>
          </button>

          <button
            type="button"
            className={`pill-action-btn ${ragEnabled ? "is-active" : "is-inactive"}`}
            onClick={() => onToggleRag?.(!ragEnabled)}
            title={ragEnabled ? "Company file search is on. Click to turn it off." : "Company file search is off. Click to turn it on."}
          >
            <BookOpen size={13} aria-hidden="true" />
            <span>Company file search: {ragEnabled ? "On" : "Off"}</span>
          </button>

        </div>

        <div className="composer-bar-right">
          <span className="send-key-hint">
            Press <kbd>Enter ↵</kbd> to send
          </span>

          {nearLimit && (
            <span className="char-counter tabular is-warn">
              {value.length}/{MAX_LENGTH}
            </span>
          )}

          <button
            type="submit"
            className={`round-send-btn ${value.trim() && !busy ? "is-ready" : ""}`}
            disabled={!value.trim() || busy || uploading}
            aria-label="Send message"
            title="Send query"
          >
            {busy || uploading ? (
              <Loader2 size={15} className="spin" aria-hidden="true" />
            ) : (
              <ArrowUp size={16} aria-hidden="true" />
            )}
          </button>

          <button
            type="button"
            className={`composer-voice-trigger-btn ${isListening ? "is-listening" : ""} ${isRefining ? "is-refining" : ""}`}
            onClick={handleVoiceClick}
            title={
              isListening
                ? "Listening... (Pause speaking to send hands-free)"
                : isRefining
                ? "Refining query with AI..."
                : "Voice Input (Speak naturally to type hands-free)"
            }
            aria-label="Open Voice Assistant Mode"
          >
            {isListening ? (
              <>
                <span className="voice-pulse-dot" aria-hidden="true" />
                <span>Listening...</span>
              </>
            ) : isRefining ? (
              <>
                <Sparkles size={13} className="spin" aria-hidden="true" />
                <span>Refining...</span>
              </>
            ) : (
              <>
                <Mic size={14} className="composer-voice-mic-icon" aria-hidden="true" />
                <span>Voice</span>
              </>
            )}
          </button>
        </div>
      </div>

    </form>
  );
}
