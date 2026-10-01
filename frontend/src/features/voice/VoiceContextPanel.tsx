import React from "react";
import { Sparkles, FileText, Database, Mail, Globe, ArrowUpRight, FolderGit2 } from "lucide-react";
import { SourceTile } from "../../components/chat/SourceTile";
import { KIND_LABEL, SourceView } from "../../lib/sources";
import { cleanDisplayText } from "./speechSynthesisService";

interface VoiceContextPanelProps {
  importantPoints: string[];
  sources: SourceView[];
  capabilities?: string[];
  onOpenSource: (source: SourceView) => void;
  className?: string;
}

export const VoiceContextPanel: React.FC<VoiceContextPanelProps> = ({
  importantPoints,
  sources,
  capabilities = [],
  onOpenSource,
  className = "",
}) => {
  return (
    <aside className={`voice-context-panel ${className}`} aria-label="Voice Context">
      <div className="voice-context-header">
        <div className="voice-context-title-row">
          <div className="voice-context-icon-wrap" aria-hidden="true">
            <Sparkles size={15} className="text-primary-500" />
          </div>
          <div className="voice-context-heading">
            <h2 className="voice-context-title">Voice Context</h2>
            <span className="voice-context-caption">Live Intelligence & Sources</span>
          </div>
        </div>

        {capabilities.length > 0 && (
          <div className="voice-capabilities-row">
            {capabilities.map((cap) => (
              <span key={cap} className="voice-cap-badge">
                {cap.toLowerCase().includes("email") && <Mail size={11} />}
                {cap.toLowerCase().includes("database") && <Database size={11} />}
                {cap.toLowerCase().includes("web") && <Globe size={11} />}
                {cap.toLowerCase().includes("file") && <FolderGit2 size={11} />}
                {cap.toLowerCase().includes("knowledge") && <FileText size={11} />}
                <span>{cap.replace(/_/g, " ")}</span>
              </span>
            ))}
          </div>
        )}
      </div>

      <div className="voice-context-scroll">
        {/* Section 1: Important Points */}
        <section className="voice-context-section" aria-labelledby="heading-important-points">
          <div className="voice-section-head">
            <span className="voice-section-tag">KEY INSIGHTS</span>
            <h3 id="heading-important-points" className="voice-section-title">
              Important Points
            </h3>
          </div>

          {importantPoints.length > 0 ? (
            <ol className="voice-points-list">
              {importantPoints.map((point, index) => {
                const numStr = String(index + 1).padStart(2, "0");
                return (
                  <li key={index} className="voice-point-item">
                    <span className="voice-point-num" aria-hidden="true">
                      {numStr}
                    </span>
                    <p className="voice-point-text">{cleanDisplayText(point)}</p>
                  </li>
                );
              })}
            </ol>
          ) : (
            <div className="voice-empty-box">
              <span className="voice-empty-text">Important points will appear here as we talk.</span>
            </div>
          )}
        </section>

        {/* Section 2: Sources */}
        <section className="voice-context-section" aria-labelledby="heading-sources">
          <div className="voice-section-head">
            <span className="voice-section-tag">PROVENANCE</span>
            <div className="voice-section-title-wrap">
              <h3 id="heading-sources" className="voice-section-title">
                Sources
              </h3>
              {sources.length > 0 && (
                <span className="voice-source-count-badge">
                  {sources.length} {sources.length === 1 ? "source" : "sources"}
                </span>
              )}
            </div>
          </div>

          {sources.length > 0 ? (
            <ul className="voice-sources-list">
              {sources.map((src) => (
                <li key={src.id} className="voice-source-wrapper">
                  <button
                    type="button"
                    className="voice-source-card"
                    onClick={() => onOpenSource(src)}
                    aria-label={`Inspect citation: ${src.title}`}
                    title={`Inspect citation: ${src.title}`}
                  >
                    <div className="voice-source-card-left">
                      <div className="voice-source-tile-box">
                        <SourceTile format={src.format} />
                      </div>
                      <div className="voice-source-info">
                        <span className="voice-source-name truncate">{src.title}</span>
                        <div className="voice-source-meta">
                          <span className="voice-source-kind">{KIND_LABEL[src.kind] || src.kind}</span>
                          {src.page && <span className="voice-source-loc">Page {src.page}</span>}
                          {src.sheet && <span className="voice-source-loc">Sheet: {src.sheet}</span>}
                          {src.location && !src.page && !src.sheet && (
                            <span className="voice-source-loc truncate">{src.location}</span>
                          )}
                        </div>
                      </div>
                    </div>
                    <ArrowUpRight size={14} className="voice-source-arrow" aria-hidden="true" />
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <div className="voice-empty-box">
              <span className="voice-empty-text">No sources used yet.</span>
            </div>
          )}
        </section>
      </div>
    </aside>
  );
};
