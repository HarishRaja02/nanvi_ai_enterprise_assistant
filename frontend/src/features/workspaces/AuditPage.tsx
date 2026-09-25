import { ScrollText } from "lucide-react";
import { Button } from "../../components/ui/Button";
import { EmptyState } from "../../components/ui/EmptyState";

/**
 * There is no audit endpoint in the frontend API client, so this page deliberately shows no events.
 * (The previous version rendered a hard-coded table styled as a "real-time" audit trail.)
 * When the backend exposes one, add it to api.ts and render it here.
 */
export function AuditPage({ onReturn }: { onReturn: () => void }) {
  return (
    <div className="page">
      <EmptyState
        icon={ScrollText}
        title="The audit log isn't available in this interface yet"
        action={<Button variant="secondary" onClick={onReturn}>Back to the assistant</Button>}
      >
        No audit events are shown here because this interface isn't connected to an audit endpoint. The steps behind each answer are available in the assistant under “How this answer was made”.
      </EmptyState>
    </div>
  );
}
