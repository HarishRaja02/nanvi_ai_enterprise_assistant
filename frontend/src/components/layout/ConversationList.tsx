import { RefreshCw } from "lucide-react";
import { Button } from "../ui/Button";
import { Skeleton } from "../ui/Skeleton";
import { conversationTitle, formatDate, groupByRecency } from "../../lib/format";
import type { ConversationSummary } from "../../types";

type Props = {
  history: ConversationSummary[];
  loading: boolean;
  error: string;
  activeId?: string;
  onSelect: (c: ConversationSummary) => void;
  onRetry: () => void;
};

/** Recent conversations with explicit loading, error (with recovery), empty and populated states. */
export function ConversationList({ history, loading, error, activeId, onSelect, onRetry }: Props) {
  if (loading && history.length === 0) {
    return (
      <div className="history-state" role="status" aria-label="Loading conversations">
        <Skeleton width="80%" /><Skeleton width="65%" /><Skeleton width="72%" />
      </div>
    );
  }
  if (error) {
    return (
      <div className="history-state" role="alert">
        <p>{error}</p>
        <Button size="sm" variant="ghost" icon={RefreshCw} onClick={onRetry}>Try again</Button>
      </div>
    );
  }
  if (history.length === 0) {
    return <p className="history-state">Your conversations will appear here after you ask a question.</p>;
  }
  return (
    <div>
      {groupByRecency(history).map((group) => (
        <div key={group.label} className="history-group">
          <h3 className="history-group-label">{group.label}</h3>
          <ul>
            {group.items.map((c) => {
              const title = conversationTitle(c);
              return (
                <li key={c.conversation_id}>
                  <button
                    type="button"
                    className={`history-item${activeId === c.conversation_id ? " is-active" : ""}`}
                    aria-current={activeId === c.conversation_id ? "true" : undefined}
                    title={title}
                    onClick={() => onSelect(c)}
                  >
                    <span className="truncate">{title}</span>
                    <small>{formatDate(c.updated_at)}</small>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </div>
  );
}
