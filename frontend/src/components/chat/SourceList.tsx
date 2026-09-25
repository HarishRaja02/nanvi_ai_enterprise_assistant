import { useState } from "react";
import { ExternalLink, Eye, FileText, Check, Copy } from "lucide-react";
import { Badge } from "../ui/Badge";
import { SourceTile } from "./SourceTile";
import { copyText } from "../../lib/clipboard";
import { useToast } from "../ui/Toast";
import type { SourceView } from "../../lib/sources";

type Props = { sources: SourceView[]; onOpen: (source: SourceView) => void };

/** Interactive source cards for verified document provenance */
export function SourceList({ sources, onOpen }: Props) {
  const notify = useToast();
  const [copiedId, setCopiedId] = useState<string | null>(null);

  if (!sources || sources.length === 0) return null;

  const handleCopyRef = async (s: SourceView) => {
    const text = `${s.title} ${s.location ? `(${s.location})` : ""}`;
    const ok = await copyText(text);
    if (ok) {
      setCopiedId(s.id);
      notify("Source reference copied.", "success");
      setTimeout(() => setCopiedId(null), 1500);
    }
  };

  return (
    <section className="interactive-sources-section" aria-label={`Sources, ${sources.length}`}>
      <div className="sources-header">
        <span className="sources-title">
          <FileText size={14} className="sources-icon" aria-hidden="true" />
          <span>Verified Sources</span>
          <span className="count">{sources.length}</span>
        </span>
        <span className="sources-subtitle">Authorized documents & records cited for this answer</span>
      </div>

      <div className="source-cards-grid">
        {sources.map((s) => (
          <div key={s.id} className="source-card">
            <div className="source-card-head">
              <SourceTile format={s.format} />
              <div className="source-card-titles">
                <span className="source-card-name truncate" title={s.title}>
                  {s.title}
                </span>
                {s.location && (
                  <span className="source-card-loc truncate" title={s.location}>
                    {s.location}
                  </span>
                )}
              </div>
            </div>

            <div className="source-card-tags">
              {s.page && <Badge tone="accent">Page {s.page}</Badge>}
              {s.sheet && <Badge tone="primary">Sheet: {s.sheet}</Badge>}
              <Badge tone="neutral">✓ Verified access</Badge>
            </div>

            <div className="source-card-actions">
              <button
                type="button"
                className="source-action-btn primary"
                onClick={() => onOpen(s)}
                title={`Open and inspect ${s.title}`}
              >
                <Eye size={12} aria-hidden="true" />
                <span>View Source</span>
              </button>

              <button
                type="button"
                className="source-action-btn secondary"
                onClick={() => onOpen(s)}
                title={`Inspect citation location in ${s.title}`}
              >
                <ExternalLink size={12} aria-hidden="true" />
                <span>Open File</span>
              </button>

              <button
                type="button"
                className="source-action-btn ghost"
                onClick={() => handleCopyRef(s)}
                title="Copy reference info"
                aria-label="Copy reference"
              >
                {copiedId === s.id ? <Check size={12} className="text-success" /> : <Copy size={12} />}
              </button>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
