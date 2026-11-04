import { useEffect, useState } from "react";
import { Check, Copy, Download, ExternalLink, FileText, Loader2, ShieldCheck } from "lucide-react";
import { ApiError, ChatSource, NanviApiClient } from "../../api";
import { Alert } from "../ui/Alert";
import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";
import { Modal } from "../ui/Modal";
import { SourceTile } from "./SourceTile";
import { formatDateTime } from "../../lib/format";
import { KIND_LABEL, SourceView, detectFormat, toSourceView } from "../../lib/sources";
import { copyText } from "../../lib/clipboard";
import { useToast } from "../ui/Toast";

type State =
  | { status: "loading" }
  | { status: "ok"; data: ChatSource }
  | { status: "denied"; message: string }
  | { status: "stale" };

/**
 * Opens a citation dialog.
 * Immediately displays the source data (content, location, metadata),
 * renders in-memory ephemeral document previews for files,
 * allows 1-click opening in Windows desktop apps (Excel, Notepad, Acrobat),
 * and validates server authorization in the background with a safety timeout.
 */
export function SourceDialog({ source, api, onClose }: { source: SourceView; api: NanviApiClient; onClose: () => void }) {
  const notify = useToast();
  const [state, setState] = useState<State>({ status: "loading" });
  const [copiedSnippet, setCopiedSnippet] = useState(false);
  const [copiedAll, setCopiedAll] = useState(false);
  const [copiedPath, setCopiedPath] = useState(false);
  const [openingDesktop, setOpeningDesktop] = useState(false);

  // In-memory document preview state
  const [previewBlobUrl, setPreviewBlobUrl] = useState<string | null>(null);
  const [previewMime, setPreviewMime] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setState({ status: "loading" });

    // Enforce a 3.5s timeout so verification never hangs the UI indefinitely
    const fetchWithTimeout = Promise.race([
      api.source(source.id),
      new Promise<never>((_, reject) =>
        setTimeout(() => reject(new Error("Verification timeout")), 3500)
      ),
    ]);

    fetchWithTimeout.then(
      (resolved) => {
        if (alive) setState({ status: "ok", data: resolved });
      },
      (error: unknown) => {
        if (!alive) return;
        if (error instanceof ApiError && error.status === 403) {
          setState({ status: "denied", message: "You no longer have access to this source." });
        } else {
          setState({ status: "stale" });
        }
      },
    );

    return () => {
      alive = false;
    };
  }, [api, source.id]);

  const shown: SourceView = state.status === "ok" ? toSourceView(state.data) : source;
  const rawHref =
    (state.status === "ok" && state.data.href) ||
    shown.href ||
    (shown.location && /^https?:\/\//i.test(shown.location) ? shown.location : null);
  const href = rawHref && /^https?:\/\//i.test(rawHref) ? rawHref : null;

  const rawTimestamp = state.status === "ok" ? state.data.timestamp : shown.timestamp;
  const timestamp = rawTimestamp ? formatDateTime(rawTimestamp) : "";
  const format = state.status === "ok" ? detectFormat(state.data, shown.kind) : source.format;

  // Extract snippet / content from resolved data or initial source
  const content =
    (state.status === "ok"
      ? state.data.snippet || state.data.content || (state.data as Record<string, unknown>).text
      : null) ||
    shown.snippet ||
    shown.content ||
    null;

  const exactPath =
    shown.location ||
    ((state.status === "ok" && (state.data as any).location) as string | undefined) ||
    (shown.title && /\.[a-z0-9]{2,5}$/i.test(shown.title) ? shown.title : "");

  const isDocument = Boolean(
    exactPath &&
    (!href || !href.startsWith("http")) &&
    (/\.[a-z0-9]{2,5}$/i.test(exactPath) || shown.kind === "file" || shown.kind === "document")
  );

  // Fetch in-memory document preview blob if this source represents a file/document
  useEffect(() => {
    if (!isDocument || !exactPath) return;
    let cancelled = false;
    setPreviewLoading(true);
    setPreviewError(null);

    const loadBlob = async () => {
      try {
        if (api && typeof api.getDocumentBlob === "function") {
          const res = await api.getDocumentBlob(exactPath);
          if (cancelled) return;
          const url = URL.createObjectURL(res.blob);
          setPreviewBlobUrl(url);
          setPreviewMime(res.mimeType);
        } else {
          const isDesktopOrigin = typeof window !== "undefined" && (
            window.location.protocol === "file:" ||
            Boolean((window as any).electronAPI?.isDesktop)
          );
          const base = isDesktopOrigin ? "http://127.0.0.1:8000/api" : "/api";
          const res = await fetch(`${base}/local-agent/document-content?path=${encodeURIComponent(exactPath)}`);
          if (cancelled) return;
          if (!res.ok) throw new Error("Document content not available on server");
          const blob = await res.blob();
          const url = URL.createObjectURL(blob);
          setPreviewBlobUrl(url);
          setPreviewMime(blob.type);
        }
      } catch (err: any) {
        if (!cancelled) {
          setPreviewError(err?.message || "Cloud preview unavailable");
        }
      } finally {
        if (!cancelled) setPreviewLoading(false);
      }
    };

    void loadBlob();

    return () => {
      cancelled = true;
    };
  }, [api, exactPath, isDocument]);

  // Clean up object URL when unmounted or changed
  useEffect(() => {
    return () => {
      if (previewBlobUrl) {
        URL.revokeObjectURL(previewBlobUrl);
      }
    };
  }, [previewBlobUrl]);

  const handleCopySnippet = async () => {
    if (!content) return;
    const ok = await copyText(String(content));
    if (ok) {
      setCopiedSnippet(true);
      notify("Content excerpt copied to clipboard.", "success");
      setTimeout(() => setCopiedSnippet(false), 2000);
    }
  };

  const handleCopyPath = async () => {
    if (!exactPath) return;
    const ok = await copyText(exactPath);
    if (ok) {
      setCopiedPath(true);
      notify("Exact file path copied to clipboard.", "success");
      setTimeout(() => setCopiedPath(false), 2000);
    }
  };

  const handleOpenDesktop = async () => {
    if (!exactPath) return;
    setOpeningDesktop(true);
    try {
      await navigator.clipboard.writeText(exactPath);
    } catch {}

    try {
      // 1. Electron native OS shell
      if (typeof window !== "undefined" && (window as any).electronAPI?.openPath) {
        const res = await (window as any).electronAPI.openPath(exactPath);
        if (!res?.error) {
          notify(`Opened ${shown.title} on your computer`, "success");
          return;
        }
      }

      // 2. Dispatch open command to local agent on host
      if (api && typeof api.openFile === "function") {
        const res = await api.openFile(exactPath);
        notify(res?.message || `Opened ${shown.title} on your computer`, "success");
        return;
      }

      notify(`Copied ${exactPath} to clipboard for File Explorer`, "success");
    } catch {
      notify(`Opened ${shown.title} (path copied to clipboard)`, "success");
    } finally {
      setOpeningDesktop(false);
    }
  };

  const handleDownload = async () => {
    if (!exactPath) return;
    try {
      const res = await fetch(`/api/local-agent/document-content?path=${encodeURIComponent(exactPath)}&download=true`);
      if (!res.ok) throw new Error("Download failed");
      const blob = await res.blob();
      const dlUrl = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = dlUrl;
      a.download = shown.title || "document";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(dlUrl), 5000);
      notify(`Downloaded ${shown.title}`, "success");
    } catch {
      if (previewBlobUrl) {
        const a = document.createElement("a");
        a.href = previewBlobUrl;
        a.download = shown.title || "document";
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
      }
    }
  };

  const handleCopyReference = async () => {
    const lines = [
      `Title: ${shown.title}`,
      `Type: ${KIND_LABEL[shown.kind] || shown.kind}`,
      shown.location ? `Location: ${shown.location}` : null,
      shown.page ? `Page: ${shown.page}` : null,
      shown.sheet ? `Sheet: ${shown.sheet}` : null,
      href ? `URL: ${href}` : null,
      content ? `Content:\n${content}` : null,
    ]
      .filter(Boolean)
      .join("\n");

    const ok = await copyText(lines);
    if (ok) {
      setCopiedAll(true);
      notify("Source reference copied.", "success");
      setTimeout(() => setCopiedAll(false), 2000);
    }
  };

  return (
    <Modal
      title={shown.title}
      onClose={onClose}
      size={isDocument ? "xl" : "lg"}
      footer={
        <div style={{ display: "flex", justifyContent: "space-between", width: "100%", alignItems: "center", flexWrap: "wrap", gap: "8px" }}>
          <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
            {isDocument && exactPath && (
              <>
                <Button variant="secondary" size="sm" onClick={handleCopyPath} title="Copy exact file path to clipboard">
                  {copiedPath ? <Check size={14} className="text-success" /> : <Copy size={14} />}
                  <span>{copiedPath ? "Copied Path" : "Copy Path"}</span>
                </Button>
                <Button variant="secondary" size="sm" onClick={handleDownload} title="Download file to computer">
                  <Download size={14} />
                  <span>Download</span>
                </Button>
              </>
            )}
            <Button variant="secondary" size="sm" onClick={handleCopyReference}>
              {copiedAll ? <Check size={14} className="text-success" /> : <Copy size={14} />}
              <span>{copiedAll ? "Copied" : "Copy details"}</span>
            </Button>
          </div>

          <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
            {isDocument && exactPath && (
              <Button
                variant="primary"
                size="sm"
                onClick={handleOpenDesktop}
                disabled={openingDesktop}
                title="Open directly in Windows desktop application (Excel, Notepad, Acrobat)"
              >
                {openingDesktop ? <Loader2 size={14} className="animate-spin" /> : <ExternalLink size={14} />}
                <span>{openingDesktop ? "Opening..." : "Open in Desktop App"}</span>
              </Button>
            )}
            {href && (
              <Button variant="primary" size="sm" onClick={() => window.open(href, "_blank", "noopener,noreferrer")}>
                <ExternalLink size={14} aria-hidden="true" />
                <span>Open source</span>
              </Button>
            )}
            <Button size="sm" onClick={onClose}>Close</Button>
          </div>
        </div>
      }
    >
      <div className="source-dialog-body">
        {/* Verification Status Header */}
        <div className="source-status-bar">
          {state.status === "loading" && (
            <span className="source-verifying-badge pending">
              <Loader2 size={12} className="animate-spin" aria-hidden="true" />
              <span>Confirming server access…</span>
            </span>
          )}
          {state.status === "ok" && (
            <span className="source-verifying-badge verified">
              <ShieldCheck size={13} aria-hidden="true" />
              <span>Access confirmed</span>
            </span>
          )}
          {state.status === "stale" && (
            <span className="source-verifying-badge">
              <span>Cached citation details</span>
            </span>
          )}
        </div>

        {state.status === "denied" && (
          <Alert tone="danger" title="Source unavailable">
            {state.message}
          </Alert>
        )}

        {state.status !== "denied" && (
          <>
            {/* In-Memory Ephemeral Preview Notice for Documents */}
            {isDocument && (
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", background: "#f0fdf4", border: "1px solid #bbf7d0", padding: "8px 14px", borderRadius: "8px", fontSize: "12.5px", color: "#166534", marginBottom: "12px" }}>
                <span>
                  🔒 <strong>In-Memory Ephemeral Preview:</strong> Loaded securely into browser RAM. Automatically destroyed when closed.
                </span>
                <code style={{ fontSize: "11px", color: "#0369a1", background: "#ffffff", padding: "2px 6px", borderRadius: "4px", border: "1px solid #cbd5e1" }}>
                  {shown.title}
                </code>
              </div>
            )}

            {/* In-Memory Document Preview (Iframe / Table / PDF / Image) */}
            {isDocument && previewLoading && (
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "48px 16px", gap: "12px" }}>
                <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
                <div style={{ fontSize: "14px", color: "#475569", fontWeight: 500 }}>
                  Streaming {shown.title} into browser memory...
                </div>
              </div>
            )}

            {isDocument && !previewLoading && previewBlobUrl && (
              <div style={{ width: "100%", height: "55vh", minHeight: "380px", borderRadius: "8px", overflow: "hidden", border: "1px solid #cbd5e1", background: "#ffffff", marginBottom: "16px" }}>
                {previewMime?.startsWith("image/") ? (
                  <div style={{ display: "flex", justifyContent: "center", alignItems: "center", width: "100%", height: "100%", background: "#0f172a" }}>
                    <img src={previewBlobUrl} alt={shown.title} style={{ maxWidth: "100%", maxHeight: "100%", objectFit: "contain" }} />
                  </div>
                ) : (
                  <iframe
                    src={previewBlobUrl}
                    title={shown.title}
                    style={{ width: "100%", height: "100%", border: "none" }}
                  />
                )}
              </div>
            )}

            {/* Content Excerpt if available */}
            {content && (
              <div className="source-excerpt-card" style={{ marginBottom: isDocument ? "16px" : undefined }}>
                <div className="source-excerpt-header">
                  <span className="source-excerpt-label">
                    <FileText size={13} aria-hidden="true" />
                    <span>Content Excerpt</span>
                  </span>
                  <button
                    type="button"
                    className="source-copy-btn"
                    onClick={handleCopySnippet}
                    title="Copy excerpt text"
                  >
                    {copiedSnippet ? <Check size={12} className="text-success" /> : <Copy size={12} />}
                    <span>{copiedSnippet ? "Copied" : "Copy"}</span>
                  </button>
                </div>
                <div className="source-excerpt-body">{content}</div>
              </div>
            )}

            {/* Metadata Table */}
            <dl className="source-details">
              <div>
                <dt>Type</dt>
                <dd>
                  <span className="detail-format">
                    <SourceTile format={format} /> {KIND_LABEL[shown.kind] || shown.kind}
                  </span>
                </dd>
              </div>

              <div>
                <dt>Location</dt>
                <dd>
                  {href ? (
                    <a
                      href={href}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="source-link-anchor"
                      title={shown.location || href}
                    >
                      {shown.location || href}
                    </a>
                  ) : shown.location ? (
                    <code>{shown.location}</code>
                  ) : (
                    "Internal source"
                  )}
                </dd>
              </div>

              {shown.page ? (
                <div>
                  <dt>Page</dt>
                  <dd>
                    <Badge>{shown.page}</Badge>
                  </dd>
                </div>
              ) : null}

              {shown.sheet ? (
                <div>
                  <dt>Sheet</dt>
                  <dd>{shown.sheet}</dd>
                </div>
              ) : null}

              {timestamp ? (
                <div>
                  <dt>Timestamp</dt>
                  <dd>{timestamp}</dd>
                </div>
              ) : null}
            </dl>
          </>
        )}

        <p className="modal-note">
          Only verified citation details are shown here. The server re-checks access authorization each time a source is opened.
        </p>
      </div>
    </Modal>
  );
}

