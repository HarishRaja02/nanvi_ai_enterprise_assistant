import { useState, useEffect } from "react";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { RefreshCwIcon, ShieldCheckIcon } from "../../icons";
import type { NanviApiClient } from "../../api";

type Props = {
  api: NanviApiClient;
};

export function AuditLogView({ api }: Props) {
  const [events, setEvents] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const loadAudit = async () => {
    try {
      setLoading(true);
      const data = await api.listConnectionAuditEvents();
      setEvents(data || []);
    } catch {
      setEvents([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAudit();
  }, []);

  const getEventBadgeVariant = (event: string) => {
    if (event.includes("CREATED") || event.includes("OAUTH_CONNECTED")) return "success";
    if (event.includes("TESTED")) return "primary";
    if (event.includes("DISCONNECTED") || event.includes("DENIED")) return "danger";
    return "neutral";
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <h3 style={{ margin: 0, fontSize: "var(--text-lg)", fontWeight: "var(--weight-semibold)" }}>
            Security & Connection Audit Log
          </h3>
          <p style={{ margin: "0.25rem 0 0", fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>
            Append-only, immutable record of connection lifecycle events and agent access.
          </p>
        </div>
        <Button variant="secondary" size="sm" onClick={loadAudit} disabled={loading}>
          <RefreshCwIcon size={14} className={loading ? "animate-spin" : ""} />
          Refresh
        </Button>
      </div>

      {events.length === 0 ? (
        <div style={{
          padding: "2rem",
          textAlign: "center",
          background: "var(--bg-surface)",
          borderRadius: "0.5rem",
          border: "1px dashed var(--border)",
          color: "var(--text-muted)",
        }}>
          <ShieldCheckIcon size={32} style={{ margin: "0 auto 0.75rem", opacity: 0.5 }} />
          <p style={{ margin: 0, fontSize: "var(--text-sm)", fontWeight: "var(--weight-medium)" }}>
            No connection audit events recorded yet
          </p>
        </div>
      ) : (
        <div style={{
          background: "var(--bg-surface)",
          border: "1px solid var(--border)",
          borderRadius: "0.5rem",
          overflowX: "auto",
        }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "var(--text-xs)" }}>
            <thead>
              <tr style={{ background: "var(--bg-sunken)", borderBottom: "1px solid var(--border)", textAlign: "left" }}>
                <th style={{ padding: "0.75rem 1rem", fontWeight: "var(--weight-semibold)" }}>Event</th>
                <th style={{ padding: "0.75rem 1rem", fontWeight: "var(--weight-semibold)" }}>Provider</th>
                <th style={{ padding: "0.75rem 1rem", fontWeight: "var(--weight-semibold)" }}>Actor</th>
                <th style={{ padding: "0.75rem 1rem", fontWeight: "var(--weight-semibold)" }}>Details</th>
                <th style={{ padding: "0.75rem 1rem", fontWeight: "var(--weight-semibold)" }}>Timestamp</th>
              </tr>
            </thead>
            <tbody>
              {events.map((evt) => (
                <tr key={evt.id} style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                  <td style={{ padding: "0.75rem 1rem" }}>
                    <Badge tone={getEventBadgeVariant(evt.event) as any}>
                      {evt.event.replace("CONNECTION_", "")}
                    </Badge>
                  </td>
                  <td style={{ padding: "0.75rem 1rem", fontWeight: "var(--weight-medium)" }}>
                    {evt.provider || "—"}
                  </td>
                  <td style={{ padding: "0.75rem 1rem", color: "var(--text-secondary)" }}>
                    {evt.actor_user_id || "System"}
                  </td>
                  <td style={{ padding: "0.75rem 1rem", color: "var(--text-muted)", maxWidth: "240px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {typeof evt.safe_metadata === "object" ? JSON.stringify(evt.safe_metadata) : evt.safe_metadata || "—"}
                  </td>
                  <td style={{ padding: "0.75rem 1rem", color: "var(--text-muted)", whiteSpace: "nowrap" }}>
                    {evt.created_at ? new Date(evt.created_at).toLocaleString() : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
