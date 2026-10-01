import React from "react";
import { FileText, Database, Mail, Globe, Sparkles, Loader2 } from "lucide-react";

export interface GlassProgressCardProps {
  stage: string;
  detail?: string;
  elapsedSeconds?: number;
  sourcesFound?: number;
  progressPercent?: number;
}

export const GlassProgressCard: React.FC<GlassProgressCardProps> = ({
  stage,
  detail,
  elapsedSeconds = 0,
  sourcesFound = 0,
  progressPercent = 45,
}) => {
  // Determine appropriate operational icon
  const stageLower = stage.toLowerCase();
  let Icon = Sparkles;
  let categoryLabel = "Operational Processing";

  if (stageLower.includes("file") || stageLower.includes("doc") || stageLower.includes("knowledge")) {
    Icon = FileText;
    categoryLabel = "Enterprise Documents";
  } else if (stageLower.includes("sql") || stageLower.includes("database") || stageLower.includes("table")) {
    Icon = Database;
    categoryLabel = "Database Records";
  } else if (stageLower.includes("email") || stageLower.includes("mail")) {
    Icon = Mail;
    categoryLabel = "Mailbox Verification";
  } else if (stageLower.includes("web") || stageLower.includes("online") || stageLower.includes("search")) {
    Icon = Globe;
    categoryLabel = "Web Sources";
  }

  return (
    <div
      className="glass-progress-card"
      role="status"
      aria-live="polite"
      aria-label={`Progress: ${stage}`}
    >
      <div className="glass-progress-header">
        <div className="glass-progress-badge">
          <Icon size={14} className="text-primary-600 animate-pulse" aria-hidden="true" />
          <span className="glass-progress-category">{categoryLabel}</span>
        </div>

        <div className="glass-progress-meta">
          {sourcesFound > 0 && (
            <span className="glass-sources-badge">
              {sourcesFound} {sourcesFound === 1 ? "source" : "sources"} verified
            </span>
          )}
          <span className="glass-elapsed-badge">{elapsedSeconds}s</span>
        </div>
      </div>

      <div className="glass-progress-body">
        <div className="glass-stage-title-wrap">
          <Loader2 size={13} className="spin text-primary-500" aria-hidden="true" />
          <span className="glass-stage-title">{stage}</span>
        </div>
        {detail && <p className="glass-stage-detail">{detail}</p>}
      </div>

      <div className="glass-progress-bar-track" aria-hidden="true">
        <div
          className="glass-progress-bar-fill"
          style={{ width: `${Math.min(100, Math.max(10, progressPercent))}%` }}
        />
      </div>
    </div>
  );
};
