import { useMemo } from "react";
import { ArrowRight, ChevronDown, Folder, Zap, X } from "lucide-react";
import { IconButton } from "../ui/Button";
import { SourceTile } from "../chat/SourceTile";
import { extractConversationContext } from "../../lib/contextIntelligence";
import type { UserIdentity } from "../../api";
import type { Message } from "../../types";
import type { SourceView } from "../../lib/sources";

type Props = {
  identity: UserIdentity;
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
    <aside id="context-panel" className="context-panel" aria-label="Workspace details">
      <div className="panel-head">
        <div className="panel-title-group">
          <h2>Workspace details</h2>
        </div>
        <IconButton className="panel-close" icon={X} label="Close workspace details" size="sm" onClick={onClose} />
      </div>

      {sources.length > 0 && (
        <section className="panel-section">
          <details className="context-citations">
            <summary className="context-citations-summary">
              <span>Cited documents</span>
              <span className="count">{sources.length}</span>
              <ChevronDown size={17} aria-hidden="true" />
            </summary>
            <ul className="ctx-sources">
              {sources.map((s) => (
                <li key={s.id}>
                  <button type="button" className="ctx-source" onClick={() => onOpenSource(s)} title={`Open source: ${s.title}`}>
                    <SourceTile format={s.format} />
                    <div className="ctx-source-meta">
                      <span className="truncate">{s.title}</span>
                      {s.location && <small className="truncate">{s.location}</small>}
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          </details>
        </section>
      )}

      {context.availableActions.length > 0 && onAsk && (
        <section className="panel-section" aria-labelledby="ctx-actions">
          <div className="section-head-row">
            <h3 id="ctx-actions">Suggested actions</h3>
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

      <details className="context-extra">
        <summary><Folder size={16} aria-hidden="true" /> Company files</summary>
        <div className="context-extra-content">
          <p className="context-folder-name">{folderName || "CompanyData"}{folderFileCount !== undefined ? ` · ${folderFileCount} files` : ""}</p>
          <p className="context-folder-path">{folderPath || "No local folder selected"}</p>
          {onOpenFolderPicker && <button type="button" className="context-secondary-action" onClick={onOpenFolderPicker}>Change folder</button>}
        </div>
      </details>

      <details className="context-extra">
        <summary><Zap size={16} aria-hidden="true" /> Conversation insights</summary>
        <div className="context-extra-content">
          <p className="context-folder-name">{context.topic}</p>
          {context.activeFilters.length > 0 && (
            <div className="hud-filter-chips">
              {context.activeFilters.map((filter, index) => (
                <button
                  key={`${filter.key}-${index}`}
                  type="button"
                  className="hud-filter-chip"
                  title={`Ask for more details about ${filter.key}: ${filter.value}`}
                  onClick={() => onAsk?.(`Show more details specifically for ${filter.key} = ${filter.value}`)}
                >
                  <span className="filter-key">{filter.key}:</span>
                  <span className="filter-val">{filter.value}</span>
                </button>
              ))}
            </div>
          )}
          {context.metrics.length > 0 && (
            <div className="context-metrics-list">
              {context.metrics.map((metric) => <p key={metric.id}>{metric.label}: <strong>{metric.value}</strong></p>)}
            </div>
          )}
        </div>
      </details>
    </aside>
  );
}
