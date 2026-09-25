import { useState } from "react";
import { ConnectionsHub } from "./ConnectionsHub";
import { AuditLogView } from "./AuditLogView";
import { CompanyFolderPicker } from "../../components/ui/CompanyFolderPicker";
import { PlugIcon, FolderIcon, ShieldCheckIcon } from "../../icons";
import type { NanviApiClient, UserIdentity } from "../../api";

type Props = {
  api: NanviApiClient;
  identity: UserIdentity | null;
};

type Tab = "connections" | "folder" | "audit";

export function SettingsPage({ api, identity }: Props) {
  const [activeTab, setActiveTab] = useState<Tab>(() => {
    const params = new URLSearchParams(window.location.search);
    const tabParam = params.get("tab");
    if (tabParam === "folder" || tabParam === "audit") return tabParam;
    return "connections";
  });

  const roles = identity?.roles || [];
  const canManageOrg = roles.includes("IT Admin") || roles.includes("CEO");
  const canViewAudit = canManageOrg || roles.includes("Audit");

  return (
    <div className="page" style={{ maxWidth: "1280px", margin: "0 auto", padding: "1.5rem" }}>
      {/* Settings Hero Banner */}
      <div className="workspace-hero-banner" style={{ marginBottom: "1.5rem" }}>
        <h1 className="workspace-hero-title">Settings & Connections Hub</h1>
        <p className="page-intro">
          Manage enterprise data connections, credentials, folder paths, and system security.
        </p>
        <span className="workspace-meta-tag">⚡ Universal Integrations Hub</span>
      </div>

      {/* Settings Tabs Navigation */}
      <div style={{
        display: "flex",
        gap: "0.5rem",
        borderBottom: "1px solid var(--border)",
        marginBottom: "1.5rem",
      }}>
        <button
          type="button"
          onClick={() => setActiveTab("connections")}
          style={{
            display: "flex",
            alignItems: "center",
            gap: "0.5rem",
            padding: "0.75rem 1rem",
            background: "none",
            border: "none",
            borderBottom: activeTab === "connections" ? "2px solid var(--primary-600)" : "2px solid transparent",
            color: activeTab === "connections" ? "var(--primary-600)" : "var(--text-muted)",
            fontWeight: activeTab === "connections" ? "var(--weight-semibold)" : "var(--weight-medium)",
            fontSize: "var(--text-sm)",
            cursor: "pointer",
          }}
        >
          <PlugIcon size={16} />
          Connections Hub
        </button>

        <button
          type="button"
          onClick={() => setActiveTab("folder")}
          style={{
            display: "flex",
            alignItems: "center",
            gap: "0.5rem",
            padding: "0.75rem 1rem",
            background: "none",
            border: "none",
            borderBottom: activeTab === "folder" ? "2px solid var(--primary-600)" : "2px solid transparent",
            color: activeTab === "folder" ? "var(--primary-600)" : "var(--text-muted)",
            fontWeight: activeTab === "folder" ? "var(--weight-semibold)" : "var(--weight-medium)",
            fontSize: "var(--text-sm)",
            cursor: "pointer",
          }}
        >
          <FolderIcon size={16} />
          Company Folder
        </button>

        {canViewAudit && (
          <button
            type="button"
            onClick={() => setActiveTab("audit")}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.5rem",
              padding: "0.75rem 1rem",
              background: "none",
              border: "none",
              borderBottom: activeTab === "audit" ? "2px solid var(--primary-600)" : "2px solid transparent",
              color: activeTab === "audit" ? "var(--primary-600)" : "var(--text-muted)",
              fontWeight: activeTab === "audit" ? "var(--weight-semibold)" : "var(--weight-medium)",
              fontSize: "var(--text-sm)",
              cursor: "pointer",
            }}
          >
            <ShieldCheckIcon size={16} />
            Security & Audit
          </button>
        )}
      </div>

      {/* Tab Contents */}
      {activeTab === "connections" && (
        <ConnectionsHub api={api} canManageOrg={canManageOrg} />
      )}

      {activeTab === "folder" && (
        <div style={{ maxWidth: "800px" }}>
          <CompanyFolderPicker api={api} />
        </div>
      )}

      {activeTab === "audit" && canViewAudit && (
        <AuditLogView api={api} />
      )}
    </div>
  );
}
