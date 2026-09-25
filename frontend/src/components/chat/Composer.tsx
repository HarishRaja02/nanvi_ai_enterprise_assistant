import { FormEvent, KeyboardEvent, useEffect, useLayoutEffect, useRef, useState } from "react";
import { ArrowUp, BookOpen, FileText, Info, Loader2, Mic, Paperclip, Plus, X } from "lucide-react";
import { Modal } from "../ui/Modal";
import { Badge } from "../ui/Badge";
import type { NanviApiClient } from "../../api";

const MAX_LENGTH = 4000;
const WARN_AT = 3600;
const MAX_HEIGHT = 180;

const VAULTS = [
  { name: "Contracts", desc: "Enterprise license agreements, NDAs, MSAs", count: "4 files" },
  { name: "Customers", desc: "Customer directories, SLAs, Acme account summaries", count: "4 files" },
  { name: "Finance", desc: "2026 Budget forecast, Q1 summaries, Travel expense policy", count: "4 files" },
  { name: "HR", desc: "Benefits & healthcare plan, Employee handbook, Leave policies", count: "6 files" },
  { name: "Projects", desc: "Sprint deliverables, Infrastructure milestones, Phoenix plan", count: "4 files" },
  { name: "Resumes", desc: "Engineering talent pool & candidate resumes", count: "2 files" },
];

type Props = {
  busy: boolean;
  onSend: (text: string, rag?: boolean) => Promise<boolean>;
  focusToken: number;
  ragEnabled?: boolean;
  onToggleRag?: (enabled: boolean) => void;
  api?: NanviApiClient;
  onClearConversation?: () => void;
  hasMessages?: boolean;
  onOpenVoiceMode?: () => void;
};

export function Composer({
  busy,
  onSend,
  focusToken,
  ragEnabled = true,
  onToggleRag,
  api,
  onClearConversation,
  hasMessages = false,
  onOpenVoiceMode,
}: Props) {
  const [value, setValue] = useState("");
  const [vaultsModalOpen, setVaultsModalOpen] = useState(false);
  const [attachedFile, setAttachedFile] = useState<{ name: string; size: number } | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const [isDragOver, setIsDragOver] = useState(false);

  const ref = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

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
    if (await onSend(text, ragEnabled)) {
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
      {/* Hidden file input for RAG document ingestion */}
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,.docx,.xlsx,.csv,.txt,.md"
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
          <span>Ingesting document into RAG knowledge vault…</span>
        </div>
      )}

      {uploadError && (
        <div className="composer-error-pill" role="alert">
          {uploadError}
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
          placeholder="Ask Nanvi across company documents, data & email..."
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
            title={ragEnabled ? "Knowledge Search is ON (Click to toggle)" : "Knowledge Search is OFF (Click to toggle)"}
          >
            <BookOpen size={13} aria-hidden="true" />
            <span>Knowledge Search: {ragEnabled ? "ON" : "OFF"}</span>
          </button>

          {hasMessages && onClearConversation && (
            <button
              type="button"
              className="pill-action-btn btn-new-chat"
              onClick={onClearConversation}
              title="Start a new chat conversation"
            >
              <Plus size={13} aria-hidden="true" />
              <span>New Chat</span>
            </button>
          )}

          <button
            type="button"
            className="vault-info-trigger"
            onClick={() => setVaultsModalOpen(true)}
            title="6 Knowledge Vaults connected"
          >
            <Info size={13} aria-hidden="true" />
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

          {onOpenVoiceMode && (
            <button
              type="button"
              className="composer-voice-trigger-btn"
              onClick={onOpenVoiceMode}
              title="Voice Assistant Mode"
              aria-label="Open Voice Assistant Mode"
            >
              <Mic size={14} className="composer-voice-mic-icon" aria-hidden="true" />
              <span>Voice</span>
            </button>
          )}
        </div>
      </div>

      {/* Connected Vaults Modal */}
      {vaultsModalOpen && (
        <Modal
          title="Enterprise RAG Knowledge Vaults"
          onClose={() => setVaultsModalOpen(false)}
          footer={<button type="button" className="btn btn-primary" onClick={() => setVaultsModalOpen(false)}>Done</button>}
        >
          <div className="vaults-dialog-content">
            <p className="vaults-intro">
              Nanvi indexes files from <code>C:\CompanyData</code> with hybrid vector embeddings and BM25 lexical search.
            </p>
            <ul className="vault-list">
              {VAULTS.map((v) => (
                <li key={v.name} className="vault-item">
                  <div className="vault-head">
                    <span className="vault-name">📁 {v.name}</span>
                    <Badge tone="primary">{v.count}</Badge>
                  </div>
                  <p className="vault-desc">{v.desc}</p>
                </li>
              ))}
            </ul>
          </div>
        </Modal>
      )}
    </form>
  );
}
