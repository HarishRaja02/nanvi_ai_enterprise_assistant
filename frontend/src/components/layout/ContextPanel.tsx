import { useMemo } from "react";
import { ArrowRight, CheckCircle2, FileText, Filter, Folder, Sparkles, X, Zap } from "lucide-react";
import { Badge } from "../ui/Badge";
import { IconButton } from "../ui/Button";
import { SourceTile } from "../chat/SourceTile";
import { extractConversationContext } from "../../lib/contextIntelligence";
import type { UserIdentity } from "../../api";
import type { NavEntry } from "../../lib/access";
import type { Message } from "../../types";
import type { SourceView } from "../../lib/sources";

type Props = {
  identity: UserIdentity;
  modules: NavEntry[];
  conversationId?: string;
  messages: Message[];
  onOpenSource: (s: SourceView) => void;
  onClose: () => void;
  onAsk?: (prompt: string) => void;
  folderPath?: string;
  folderName?: string;
  folderFileCount?: number;
  onOpenFolderPicker?: () => void;
};

/**
 * Dynamic Live Context HUD.
 * Reacts continuously to the active conversation, extracting topic, active filters,
 * Bento metrics, cited files, and contextual smart actions.
 */
export function ContextPanel({
  identity,
  modules,
  conversationId,
  messages,
  onOpenSource,
  onClose,
  onAsk,
  folderPath,
  folderName,
  folderFileCount,
  onOpenFolderPicker,
}: Props) {
  const context = useMemo(() => extractConversationContext(messages, identity), [messages, identity]);

  const sources = useMemo(() => {
    const map = new Map<string, SourceView>();
    for (const m of messages) {
      for (const s of m.sources ?? []) {
        if (!map.has(s.id)) map.set(s.id, s);
      }
    }
    return Array.from(map.values());
  }, [messages]);

  return (
    <aside id="context-panel" className="context-panel" aria-label="Dynamic Workspace HUD">
      {/* Panel Header */}
      <div className="panel-head">
        <div className="panel-title-group">
          <h2>Workspace HUD</h2>
          <span className="live-pulse-badge">
            <span className="rag-pulse-dot" aria-hidden="true" />
            <span>Live Context</span>
          </span>
        </div>
        <IconButton className="panel-close" icon={X} label="Close HUD" size="sm" onClick={onClose} />
      </div>

      {/* Bento Section 0: Local Data Folder */}
      <section className="panel-section bento-hud-section" aria-labelledby="ctx-folder">
        <div className="section-head-row">
          <h3 id="ctx-folder">
            <Folder size={14} className="hud-icon" aria-hidden="true" />
            <span>Local Data Folder</span>
          </h3>
          {onOpenFolderPicker && (
            <button
              type="button"
              className="text-xs text-indigo-600 dark:text-indigo-400 hover:underline font-medium"
              onClick={onOpenFolderPicker}
            >
              Change
            </button>
          )}
        </div>

        <div className="topic-card">
          <div className="topic-name truncate" title={folderPath || "Not configured"}>
            📁 {folderName || "CompanyData"}
          </div>
          <div className="topic-sub truncate">
            {folderPath
              ? `${folderPath} • ${folderFileCount ?? 0} files`
              : "Click Change to select local data folder"}
          </div>
        </div>
      </section>

      {/* Bento Section 1: Active Topic & Focus */}
      <section className="panel-section bento-hud-section" aria-labelledby="ctx-topic">
        <div className="section-head-row">
          <h3 id="ctx-topic">
            <Sparkles size={14} className="hud-icon" aria-hidden="true" />
            <span>Active Topic</span>
          </h3>
          <Badge tone="accent">{context.topicCategory.toUpperCase()}</Badge>
        </div>

        <div className="topic-card">
          <div className="topic-name">{context.topic}</div>
          <div className="topic-sub">
            {messages.length === 0
              ? "Ready for exploration across enterprise vaults"
              : `Context updated from ${messages.length} conversational turns`}
          </div>
        </div>
      </section>

      {/* Bento Section 2: Active Filters */}
      {context.activeFilters.length > 0 && (
        <section className="panel-section bento-hud-section" aria-labelledby="ctx-filters">
          <div className="section-head-row">
            <h3 id="ctx-filters">
              <Filter size={14} className="hud-icon" aria-hidden="true" />
              <span>Active Filters</span>
            </h3>
          </div>

          <div className="hud-filter-chips">
            {context.activeFilters.map((f, i) => (
              <button
                key={i}
                type="button"
                className="hud-filter-chip"
                title={`Filter applied: ${f.key}: ${f.value}`}
                onClick={() => onAsk?.(`Show more details specifically for ${f.key} = ${f.value}`)}
              >
                <span className="filter-key">{f.key}:</span>
                <span className="filter-val">{f.value}</span>
              </button>
            ))}
          </div>
        </section>
      )}

      {/* Bento Section 3: Live Bento Metrics Grid */}
      <section className="panel-section bento-hud-section" aria-labelledby="ctx-metrics">
        <div className="section-head-row">
          <h3 id="ctx-metrics">
            <Zap size={14} className="hud-icon" aria-hidden="true" />
            <span>Context Metrics</span>
          </h3>
        </div>

        <div className="hud-bento-grid">
          {context.metrics.map((m) => (
            <div key={m.id} className={`hud-bento-tile tone-${m.tone || "primary"}`}>
              <span className="tile-label truncate">{m.label}</span>
              <span className="tile-value tabular truncate">{m.value}</span>
              {m.subtext && <span className="tile-sub truncate">{m.subtext}</span>}
            </div>
          ))}
        </div>
      </section>

      {/* Bento Section 4: Smart Actions */}
      {context.availableActions.length > 0 && onAsk && (
        <section className="panel-section bento-hud-section" aria-labelledby="ctx-actions">
          <div className="section-head-row">
            <h3 id="ctx-actions">
              <Sparkles size={14} className="hud-icon" aria-hidden="true" />
              <span>Smart Actions</span>
            </h3>
          </div>

          <div className="hud-actions-list">
            {context.availableActions.map((act) => (
              <button
                key={act.id}
                type="button"
                className={`hud-action-btn tone-${act.tone || "primary"}`}
                onClick={() => onAsk(act.query)}
                title={`Execute: "${act.query}"`}
              >
                <span>{act.label}</span>
                <ArrowRight size={13} className="hud-action-arrow" aria-hidden="true" />
              </button>
            ))}
          </div>
        </section>
      )}

      {/* Bento Section 5: Sources Cited */}
      <section className="panel-section bento-hud-section" aria-labelledby="ctx-sources">
        <div className="section-head-row">
          <h3 id="ctx-sources">
            <FileText size={14} className="hud-icon" aria-hidden="true" />
            <span>Cited Documents</span>
          </h3>
          <span className="count">{sources.length}</span>
        </div>

        {sources.length > 0 ? (
          <ul className="ctx-sources">
            {sources.map((s) => (
              <li key={s.id}>
                <button
                  type="button"
                  className="ctx-source"
                  onClick={() => onOpenSource(s)}
                  title={`Open provenance: ${s.title}`}
                >
                  <SourceTile format={s.format} />
                  <div className="ctx-source-meta">
                    <span className="truncate">{s.title}</span>
                    {s.location && <small className="truncate">{s.location}</small>}
                  </div>
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="ctx-note">
            When Nanvi cites company documents, financial records, or emails, they appear here.
          </p>
        )}
      </section>

      {/* Bento Section 6: Security & Identity */}
      <section className="panel-section bento-hud-section" aria-labelledby="ctx-identity">
        <div className="section-head-row">
          <h3 id="ctx-identity">
            <CheckCircle2 size={14} className="hud-icon" aria-hidden="true" />
            <span>Session Identity</span>
          </h3>
        </div>

        <div className="hud-identity-card">
          <p className="ctx-name">{identity.name || identity.email || "Authorized user"}</p>
          {identity.email && identity.name && <p className="ctx-sub truncate">{identity.email}</p>}
          <div className="ctx-badges">
            {identity.roles.map((r) => (
              <Badge key={r} tone="primary">
                {r}
              </Badge>
            ))}
            {identity.department && <Badge tone="accent">{identity.department}</Badge>}
          </div>
        </div>
      </section>
    </aside>
  );
}
