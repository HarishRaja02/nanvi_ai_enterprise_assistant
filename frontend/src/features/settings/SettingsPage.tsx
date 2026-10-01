import { useState, type ReactNode } from "react";
import { ConnectionsHub } from "./ConnectionsHub";
import { AuditLogView } from "./AuditLogView";
import { AccountManagement } from "./AccountManagement";
import { DisplaySettings } from "./DisplaySettings";
import { CompanyFolderPicker } from "../../components/ui/CompanyFolderPicker";
import { PlugIcon, FolderIcon, ShieldCheckIcon } from "../../icons";
import type { NanviApiClient, UserIdentity } from "../../api";
import type { FontScale } from "../../hooks/useFontScale";

type Props = {
  api: NanviApiClient;
  identity: UserIdentity | null;
  fontScale: FontScale;
  onFontScaleChange: (scale: FontScale) => void;
};

type Tab = "display" | "accounts" | "connections" | "folder" | "audit";

export function SettingsPage({ api, identity, fontScale, onFontScaleChange }: Props) {
  const roles = identity?.roles || [];
  const canManageUsers = roles.some((role) => ["Superior", "Supervisor", "CEO", "Finance"].includes(role));
  const canManageOrg = roles.some((role) => ["Superior", "Supervisor", "CEO", "IT Admin"].includes(role));
  const canViewAudit = roles.some((role) => ["Superior", "CEO", "IT Admin"].includes(role));

  const availableTabs: Tab[] = ["display"];
  if (canManageUsers) availableTabs.push("accounts");
  if (canManageOrg) availableTabs.push("connections", "folder");
  if (canViewAudit) availableTabs.push("audit");

  const [activeTab, setActiveTab] = useState<Tab>(() => {
    const tabParam = new URLSearchParams(window.location.search).get("tab") as Tab | null;
    if (tabParam && availableTabs.includes(tabParam)) return tabParam;
    return canManageUsers ? "accounts" : "display";
  });

  const tabs: { id: Tab; label: string; icon?: ReactNode }[] = [
    { id: "display", label: "Text size" },
    ...(canManageUsers ? [{ id: "accounts" as const, label: "User accounts" }] : []),
    ...(canManageOrg ? [
      { id: "connections" as const, label: "Connections Hub", icon: <PlugIcon size={16} /> },
      { id: "folder" as const, label: "Company Folder", icon: <FolderIcon size={16} /> },
    ] : []),
    ...(canViewAudit ? [{ id: "audit" as const, label: "Security & Audit", icon: <ShieldCheckIcon size={16} /> }] : []),
  ];

  return (
    <div className="page" style={{ width: "100%", minWidth: 0, boxSizing: "border-box", maxWidth: "1280px", margin: "0 auto", padding: "1.5rem" }}>
      <div className="workspace-hero-banner" style={{ marginBottom: "1.5rem" }}>
        <h1 className="workspace-hero-title">Settings</h1>
        <p className="page-intro">Adjust your reading experience and access the tools available to your role.</p>
      </div>

      <div role="tablist" aria-label="Settings" className="settings-tabs">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={activeTab === tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`settings-tab${activeTab === tab.id ? " is-active" : ""}`}
          >
            {tab.icon}
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === "display" && <DisplaySettings fontScale={fontScale} onChange={onFontScaleChange} />}
      {activeTab === "accounts" && canManageUsers && identity && <AccountManagement api={api} identity={identity} />}
      {activeTab === "connections" && canManageOrg && <ConnectionsHub api={api} canManageOrg={canManageOrg} />}
      {activeTab === "folder" && canManageOrg && (
        <div style={{ maxWidth: "800px" }}>
          <CompanyFolderPicker api={api} />
        </div>
      )}
      {activeTab === "audit" && canViewAudit && <AuditLogView api={api} />}
    </div>
  );
}
