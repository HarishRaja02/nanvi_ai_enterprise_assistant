import { useState } from "react";
import { Modal } from "../../components/ui/Modal";
import { Button } from "../../components/ui/Button";
import { Badge } from "../../components/ui/Badge";
import { Alert } from "../../components/ui/Alert";
import { PlugIcon, TrashIcon, CheckCircleIcon, AlertCircleIcon } from "../../icons";
import type { NanviApiClient, ConnectionPublic } from "../../api";
import { useToast } from "../../components/ui/Toast";

type Props = {
  open: boolean;
  connection: ConnectionPublic | null;
  onClose: () => void;
  onUpdated: () => void;
  api: NanviApiClient;
};

export function ManageConnectionModal({ open, connection, onClose, onUpdated, api }: Props) {
  const notify = useToast();
  const [displayName, setDisplayName] = useState("");
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string } | null>(null);

  if (!open || !connection) return null;

  const currentName = displayName !== "" ? displayName : connection.display_name;

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const res = await api.testConnection(connection.id);
      setTestResult(res);
      if (res.ok) {
        notify("Connection test succeeded!", "success");
      } else {
        notify(res.message || "Test failed.", "error");
      }
      onUpdated();
    } catch (err: any) {
      setTestResult({ ok: false, message: err.message || "Test failed." });
      notify(err.message || "Test failed.", "error");
    } finally {
      setTesting(false);
    }
  };

  const handleUpdate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!currentName.trim()) return;
    setSaving(true);
    try {
      await api.updateConnection(connection.id, { display_name: currentName.trim() });
      notify("Connection updated successfully.", "success");
      onUpdated();
      onClose();
    } catch (err: any) {
      notify(err.message || "Failed to update connection.", "error");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!window.confirm(`Disconnect and remove ${connection.display_name}? This cannot be undone.`)) {
      return;
    }
    setDeleting(true);
    try {
      await api.deleteConnection(connection.id);
      notify("Connection removed.", "success");
      onUpdated();
      onClose();
    } catch (err: any) {
      notify(err.message || "Failed to remove connection.", "error");
    } finally {
      setDeleting(false);
    }
  };

  const statusColor = connection.status === "CONNECTED" ? "success" : connection.status === "ERROR" ? "danger" : "neutral";

  return (
    <Modal onClose={onClose} title="Manage Connection">
      <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem", padding: "0.25rem" }}>
        {/* Connection Header */}
        <div style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "1rem",
          background: "var(--bg-sunken)",
          borderRadius: "0.5rem",
          border: "1px solid var(--border)",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
            <div style={{
              width: "2.5rem",
              height: "2.5rem",
              borderRadius: "0.5rem",
              background: "var(--bg-surface)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              border: "1px solid var(--border)",
              color: "var(--primary-600)",
            }}>
              <PlugIcon size={20} />
            </div>
            <div>
              <div style={{ fontWeight: "var(--weight-semibold)", fontSize: "var(--text-base)" }}>{connection.display_name}</div>
              <div style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>
                {connection.account_identifier || connection.provider}
              </div>
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <Badge tone={connection.scope_level === "organization" ? "primary" : "neutral"}>
              {connection.scope_level === "organization" ? "Org" : "Personal"}
            </Badge>
            <Badge tone={statusColor as any}>
              {connection.status}
            </Badge>
          </div>
        </div>

        {/* Update Name Form */}
        <form onSubmit={handleUpdate} style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          <div>
            <label style={{ display: "block", fontSize: "var(--text-xs)", fontWeight: "var(--weight-semibold)", marginBottom: "0.375rem" }}>
              Connection Name
            </label>
            <input
              type="text"
              value={currentName}
              onChange={(e) => setDisplayName(e.target.value)}
              style={{
                width: "100%",
                padding: "0.5rem 0.75rem",
                borderRadius: "0.375rem",
                border: "1px solid var(--border)",
                background: "var(--bg-surface)",
                color: "var(--text)",
                fontSize: "var(--text-sm)",
              }}
            />
          </div>

          <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.5rem" }}>
            <Button type="submit" variant="secondary" disabled={saving}>
              {saving ? "Saving..." : "Rename"}
            </Button>
          </div>
        </form>

        {/* Diagnostic Metadata */}
        <div style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: "0.75rem",
          padding: "0.875rem",
          background: "var(--bg-sunken)",
          borderRadius: "0.375rem",
          fontSize: "var(--text-xs)",
        }}>
          <div>
            <span style={{ color: "var(--text-muted)" }}>Provider:</span>{" "}
            <strong>{connection.provider}</strong>
          </div>
          <div>
            <span style={{ color: "var(--text-muted)" }}>Auth Type:</span>{" "}
            <strong>{connection.credential_type || "Standard"}</strong>
          </div>
          <div>
            <span style={{ color: "var(--text-muted)" }}>Last Tested:</span>{" "}
            <span>{connection.last_tested_at ? new Date(connection.last_tested_at).toLocaleString() : "Never"}</span>
          </div>
          <div>
            <span style={{ color: "var(--text-muted)" }}>Last Used:</span>{" "}
            <span>{connection.last_used_at ? new Date(connection.last_used_at).toLocaleString() : "Never"}</span>
          </div>
          {connection.granted_scopes && connection.granted_scopes.length > 0 && (
            <div style={{ gridColumn: "span 2" }}>
              <span style={{ color: "var(--text-muted)" }}>Scopes:</span>{" "}
              <span>{connection.granted_scopes.join(", ")}</span>
            </div>
          )}
        </div>

        {/* Test Result Alert */}
        {testResult && (
          <Alert tone={testResult.ok ? "success" : "danger"}>
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
              {testResult.ok ? <CheckCircleIcon size={16} /> : <AlertCircleIcon size={16} />}
              <span>{testResult.message}</span>
            </div>
          </Alert>
        )}

        {/* Danger zone & Test Action */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderTop: "1px solid var(--border)", paddingTop: "1rem" }}>
          <Button
            type="button"
            variant="danger"
            onClick={handleDelete}
            disabled={deleting}
            style={{ display: "flex", alignItems: "center", gap: "0.375rem" }}
          >
            <TrashIcon size={14} />
            {deleting ? "Disconnecting..." : "Disconnect"}
          </Button>

          <Button
            type="button"
            variant="primary"
            onClick={handleTest}
            disabled={testing}
          >
            {testing ? "Testing..." : "Test Connection"}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
