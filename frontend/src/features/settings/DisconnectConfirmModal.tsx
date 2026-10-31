import React, { useState } from "react";
import { Modal } from "../../components/ui/Modal";
import { Button } from "../../components/ui/Button";
import { BrandLogo } from "../../components/brand/BrandLogo";
import { AlertCircleIcon, ShieldCheckIcon, TrashIcon } from "../../icons";
import type { NanviApiClient, ConnectionPublic } from "../../api";
import { useToast } from "../../components/ui/Toast";

type Props = {
  open: boolean;
  connection: ConnectionPublic | null;
  onClose: () => void;
  onSuccess: () => void;
  api: NanviApiClient;
};

export function DisconnectConfirmModal({ open, connection, onClose, onSuccess, api }: Props) {
  const notify = useToast();
  const [revokeProviderOAuth, setRevokeProviderOAuth] = useState(true);
  const [disconnecting, setDisconnecting] = useState(false);

  if (!open || !connection) return null;

  const handleDisconnect = async () => {
    setDisconnecting(true);
    try {
      if (revokeProviderOAuth) {
        // Call provider token revocation endpoint
        await api.revokeConnection(connection.id);
      } else {
        // Invalidate and delete local connection record
        await api.deleteConnection(connection.id);
      }

      notify(`${connection.display_name} has been disconnected safely.`, "success");
      onSuccess();
      onClose();
    } catch (err: any) {
      notify(err.message || "Failed to disconnect account.", "error");
    } finally {
      setDisconnecting(false);
    }
  };

  const isOAuth = connection.credential_type === "oauth2";

  return (
    <Modal onClose={onClose} title={`Disconnect ${connection.display_name}?`}>
      <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem", padding: "0.25rem" }}>
        {/* Connection Header Summary */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "0.875rem",
            padding: "1rem",
            background: "var(--bg-sunken, #f8fafc)",
            borderRadius: "0.5rem",
            border: "1px solid var(--border, #e2e8f0)",
          }}
        >
          <div
            style={{
              width: "2.75rem",
              height: "2.75rem",
              borderRadius: "0.5rem",
              background: "var(--bg-surface, #ffffff)",
              border: "1px solid var(--border, #e2e8f0)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              flexShrink: 0,
            }}
          >
            <BrandLogo name={connection.provider} size={28} />
          </div>
          <div>
            <h4 style={{ margin: 0, fontSize: "0.9375rem", fontWeight: 600, color: "var(--text, #0f172a)" }}>
              {connection.display_name}
            </h4>
            <p style={{ margin: "0.125rem 0 0", fontSize: "0.75rem", color: "var(--text-muted, #64748b)" }}>
              {connection.account_identifier || connection.provider} •{" "}
              {connection.scope_level === "organization" ? "Organization Account" : "Personal Account"}
            </p>
          </div>
        </div>

        {/* Warning callout */}
        <div
          style={{
            padding: "0.875rem 1rem",
            background: "#fef2f2",
            border: "1px solid #fee2e2",
            borderRadius: "0.375rem",
            fontSize: "0.8125rem",
            color: "#991b1b",
            lineHeight: 1.5,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "0.375rem", fontWeight: 600, marginBottom: "0.25rem" }}>
            <AlertCircleIcon size={16} /> Important Disconnect Implications
          </div>
          <ul style={{ margin: "0.375rem 0 0", paddingLeft: "1.25rem", display: "flex", flexDirection: "column", gap: "0.25rem" }}>
            <li>The AI Assistant will immediately lose all search and retrieval access to all connected services.</li>
            <li>All active scheduled background synchronization jobs will be halted.</li>
            <li>Stored API tokens and encrypted credentials will be purged or invalidated.</li>
            <li>Audit history is preserved for enterprise compliance.</li>
          </ul>
        </div>

        {/* Revoke OAuth option */}
        {isOAuth && (
          <div
            style={{
              padding: "0.75rem 1rem",
              background: "var(--bg-sunken, #f8fafc)",
              borderRadius: "0.375rem",
              border: "1px solid var(--border, #e2e8f0)",
            }}
          >
            <label style={{ display: "flex", alignItems: "flex-start", gap: "0.5rem", cursor: "pointer" }}>
              <input
                type="checkbox"
                checked={revokeProviderOAuth}
                onChange={(e) => setRevokeProviderOAuth(e.target.checked)}
                style={{ marginTop: "0.25rem" }}
              />
              <div>
                <span style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--text, #0f172a)" }}>
                  Revoke OAuth token with provider
                </span>
                <p style={{ margin: "0.125rem 0 0", fontSize: "0.75rem", color: "var(--text-muted, #64748b)" }}>
                  Instructs the upstream provider (e.g. Google or Microsoft) to invalidate this application's access grant.
                </p>
              </div>
            </label>
          </div>
        )}

        {/* Action Buttons */}
        <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.75rem", borderTop: "1px solid var(--border, #e2e8f0)", paddingTop: "1rem" }}>
          <Button type="button" variant="secondary" onClick={onClose} disabled={disconnecting}>
            Cancel
          </Button>
          <Button
            type="button"
            variant="danger"
            onClick={handleDisconnect}
            disabled={disconnecting}
            style={{ display: "flex", alignItems: "center", gap: "0.375rem" }}
          >
            <TrashIcon size={14} />
            {disconnecting ? "Disconnecting..." : "Confirm Disconnect"}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
