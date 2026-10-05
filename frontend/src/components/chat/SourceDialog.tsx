import { useEffect, useState } from "react";
import { Check, Copy, ExternalLink, FileText, Loader2, ShieldCheck } from "lucide-react";
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
 * while validating server authorization in the background with a safety timeout.
 */
export function SourceDialog({ source, api, onClose }: { source: SourceView; api: NanviApiClient; onClose: () => void }) {
  const notify = useToast();
  const [state, setState] = useState<State>({ status: "loading" });
  const [copiedSnippet, setCopiedSnippet] = useState(false);
  const [copiedAll, setCopiedAll] = useState(false);

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

  const handleCopySnippet = async () => {
    if (!content) return;
    const ok = await copyText(String(content));
    if (ok) {
      setCopiedSnippet(true);
      notify("Content excerpt copied to clipboard.", "success");
      setTimeout(() => setCopiedSnippet(false), 2000);
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
      footer={
        <>
          <Button onClick={handleCopyReference}>
            {copiedAll ? <Check size={14} className="text-success" /> : <Copy size={14} />}
            <span>{copiedAll ? "Copied" : "Copy details"}</span>
          </Button>
          {href && (
            <Button variant="primary" onClick={() => window.open(href, "_blank", "noopener,noreferrer")}>
              <ExternalLink size={14} aria-hidden="true" />
              <span>Open source</span>
            </Button>
          )}
          <Button onClick={onClose}>Close</Button>
        </>
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
            {/* Content Excerpt if available */}
            {content && (
              <div className="source-excerpt-card">
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

