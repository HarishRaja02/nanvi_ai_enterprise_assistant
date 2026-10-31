import React, { useState } from "react";
import { Modal } from "../../components/ui/Modal";
import { Button } from "../../components/ui/Button";
import { Alert } from "../../components/ui/Alert";
import { BrandLogo } from "../../components/brand/BrandLogo";
import {
  ShieldCheckIcon,
  CheckCircleIcon,
  AlertCircleIcon,
  RefreshCwIcon,
  LockIcon,
  DatabaseIcon,
  FolderIcon,
  MailIcon,
  FileTextIcon,
} from "../../icons";
import type { NanviApiClient, ProviderPublic, ConnectionPublic } from "../../api";
import { useToast } from "../../components/ui/Toast";

type Props = {
  open: boolean;
  provider: ProviderPublic | null;
  onClose: () => void;
  onSuccess: (conn: ConnectionPublic) => void;
  api: NanviApiClient;
  canManageOrg: boolean;
};

export function ConnectModal({ open, provider, onClose, onSuccess, api, canManageOrg }: Props) {
  const notify = useToast();
  const [formData, setFormData] = useState<Record<string, any>>({});
  const [displayName, setDisplayName] = useState("");
  const [scopeLevel, setScopeLevel] = useState<"user" | "organization">("user");
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string } | null>(null);

  // Google Workspace requested services checklist state
  const [googleServices, setGoogleServices] = useState({
    gmail: true,
    drive: true,
    docs: true,
    sheets: false,
    calendar: false,
  });

  // Microsoft 365 requested services checklist state
  const [msServices, setMsServices] = useState({
    outlook: true,
    onedrive: true,
    sharepoint: false,
    teams: false,
  });

  if (!open || !provider) return null;

  const pId = provider.id.toLowerCase();
  const isGoogle = pId === "google" || pId === "google_workspace";
  const isMicrosoft = pId === "microsoft365" || pId === "outlook" || pId === "onedrive" || pId === "sharepoint";
  const isYahoo = pId === "yahoo";
  const isImap = pId === "imap";
  const isSmtp = pId === "smtp";
  const isStorage = pId === "box" || pId === "dropbox" || pId === "egnyte";
  const isDatabase = pId === "postgresql" || pId === "mysql" || pId === "mariadb" || pId === "sqlite" || pId === "supabase";
  const isLocalFiles = pId === "local_files";
  const isOAuth = provider.auth_type === "oauth2";

  const handleOAuthConnect = async () => {
    try {
      setSaving(true);
      const res = await api.getOAuthAuthorizeUrl(provider.id, scopeLevel);
      window.location.href = res.authorization_url;
    } catch (err: any) {
      notify(err.message || `Failed to initiate ${provider.name} authorization.`, "error");
      setSaving(false);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const res = await api.validateConnection({
        provider: provider.id,
        config: formData,
      });
      setTestResult(res);
      if (res.ok) {
        notify("Connection test succeeded! Configuration verified.", "success");
      } else {
        notify(res.message || "Test failed. Please verify credentials.", "error");
      }
    } catch (err: any) {
      setTestResult({ ok: false, message: err.message || "Connection test failed." });
      notify(err.message || "Connection test failed.", "error");
    } finally {
      setTesting(false);
    }
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      const name = displayName.trim() || provider.name;
      const conn = await api.createConnection({
        provider: provider.id,
        display_name: name,
        scope_level: scopeLevel,
        config: formData,
      });
      notify(`Connected to ${name} successfully!`, "success");
      onSuccess(conn);
      onClose();
    } catch (err: any) {
      notify(err.message || "Failed to create connection.", "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal onClose={onClose} title={`Connect ${provider.name}`}>
      <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem", padding: "0.25rem" }}>
        {/* Provider Header Banner */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "1rem",
            padding: "1rem",
            background: "var(--bg-sunken, #f8fafc)",
            borderRadius: "0.5rem",
            border: "1px solid var(--border, #e2e8f0)",
          }}
        >
          <div
            style={{
              width: "3rem",
              height: "3rem",
              borderRadius: "0.5rem",
              background: "var(--bg-surface, #ffffff)",
              border: "1px solid var(--border, #e2e8f0)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              flexShrink: 0,
            }}
          >
            <BrandLogo name={provider.id || provider.name} size={32} />
          </div>
          <div>
            <h3 style={{ margin: 0, fontSize: "1.0625rem", fontWeight: 600, color: "var(--text, #0f172a)" }}>
              {provider.name}
            </h3>
            <p style={{ margin: "0.25rem 0 0", fontSize: "0.75rem", color: "var(--text-muted, #64748b)" }}>
              {provider.description}
            </p>
          </div>
        </div>

        {/* Access Scope Level Selector */}
        <div>
          <label style={{ display: "block", fontSize: "0.75rem", fontWeight: 600, marginBottom: "0.375rem" }}>
            Account Scope
          </label>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
            <button
              type="button"
              onClick={() => setScopeLevel("user")}
              style={{
                padding: "0.75rem",
                borderRadius: "0.375rem",
                border: `1.5px solid ${scopeLevel === "user" ? "var(--primary-600, #0f766e)" : "var(--border, #e2e8f0)"}`,
                background: scopeLevel === "user" ? "rgba(15, 118, 110, 0.05)" : "var(--bg-surface, #ffffff)",
                textAlign: "left",
                cursor: "pointer",
              }}
            >
              <div style={{ fontWeight: 600, fontSize: "0.8125rem", color: "var(--text, #0f172a)" }}>Personal Account</div>
              <div style={{ fontSize: "0.6875rem", color: "var(--text-muted, #64748b)", marginTop: "0.125rem" }}>
                Only accessible by you and your personal assistant turns.
              </div>
            </button>
            <button
              type="button"
              disabled={!canManageOrg}
              onClick={() => setScopeLevel("organization")}
              style={{
                padding: "0.75rem",
                borderRadius: "0.375rem",
                border: `1.5px solid ${scopeLevel === "organization" ? "var(--primary-600, #0f766e)" : "var(--border, #e2e8f0)"}`,
                background: scopeLevel === "organization" ? "rgba(15, 118, 110, 0.05)" : "var(--bg-surface, #ffffff)",
                opacity: canManageOrg ? 1 : 0.5,
                textAlign: "left",
                cursor: canManageOrg ? "pointer" : "not-allowed",
              }}
              title={!canManageOrg ? "Requires Administrator privileges" : undefined}
            >
              <div style={{ fontWeight: 600, fontSize: "0.8125rem", color: "var(--text, #0f172a)" }}>
                Organization Account
              </div>
              <div style={{ fontSize: "0.6875rem", color: "var(--text-muted, #64748b)", marginTop: "0.125rem" }}>
                {canManageOrg ? "Shared workspace resource for authorized roles." : "Requires Admin privileges."}
              </div>
            </button>
          </div>
        </div>

        {/* 1. GOOGLE WORKSPACE WIZARD */}
        {isGoogle && (
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            <div
              style={{
                padding: "0.875rem 1rem",
                background: "var(--bg-sunken, #f8fafc)",
                borderRadius: "0.5rem",
                border: "1px solid var(--border, #e2e8f0)",
                fontSize: "0.8125rem",
                color: "var(--text-secondary, #475569)",
                lineHeight: 1.5,
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: "0.375rem", fontWeight: 600, color: "var(--text, #0f172a)", marginBottom: "0.375rem" }}>
                <ShieldCheckIcon size={16} color="var(--primary-600, #0f766e)" /> Least-Privilege OAuth 2.0
              </div>
              You will be redirected to Google to authorize access. Nanvi requests read-only search and retrieval access to authorized files and messages. You can selectively disable any service at any time in the management drawer.
            </div>

            <div>
              <span style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--text, #0f172a)", display: "block", marginBottom: "0.5rem" }}>
                Services to authorize:
              </span>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem" }}>
                {[
                  { id: "gmail", name: "Gmail", desc: "Read & search email" },
                  { id: "drive", name: "Google Drive", desc: "Search & read files" },
                  { id: "docs", name: "Google Docs", desc: "Document analysis" },
                  { id: "sheets", name: "Google Sheets", desc: "Spreadsheet querying" },
                  { id: "calendar", name: "Google Calendar", desc: "Event schedules" },
                ].map((s) => (
                  <label
                    key={s.id}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "0.5rem",
                      padding: "0.5rem 0.625rem",
                      background: "var(--bg-sunken, #f8fafc)",
                      borderRadius: "0.375rem",
                      border: "1px solid var(--border-subtle, #f1f5f9)",
                      fontSize: "0.75rem",
                      cursor: "pointer",
                    }}
                  >
                    <BrandLogo name={s.id} size={16} />
                    <span style={{ fontWeight: 500, color: "var(--text, #0f172a)" }}>{s.name}</span>
                  </label>
                ))}
              </div>
            </div>

            <Button
              type="button"
              variant="primary"
              onClick={handleOAuthConnect}
              disabled={saving}
              style={{
                width: "100%",
                padding: "0.75rem",
                fontSize: "0.9375rem",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: "0.5rem",
                background: "var(--primary-700, #0f766e)",
              }}
            >
              <BrandLogo name="google" size={18} />
              {saving ? "Redirecting to Google..." : "Connect Google Workspace with OAuth"}
            </Button>
          </div>
        )}

        {/* 2. MICROSOFT 365 WIZARD */}
        {isMicrosoft && (
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            <div
              style={{
                padding: "0.875rem 1rem",
                background: "var(--bg-sunken, #f8fafc)",
                borderRadius: "0.5rem",
                border: "1px solid var(--border, #e2e8f0)",
                fontSize: "0.8125rem",
                color: "var(--text-secondary, #475569)",
                lineHeight: 1.5,
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: "0.375rem", fontWeight: 600, color: "var(--text, #0f172a)", marginBottom: "0.375rem" }}>
                <ShieldCheckIcon size={16} color="var(--primary-600, #0f766e)" /> Microsoft Identity Platform
              </div>
              Authorizing requests Microsoft Graph API permissions (Mail.Read, Files.Read.All, Sites.Read.All). Compatible with Azure AD / Entra ID enterprise tenants and Microsoft 365 Business accounts.
            </div>

            <Button
              type="button"
              variant="primary"
              onClick={handleOAuthConnect}
              disabled={saving}
              style={{
                width: "100%",
                padding: "0.75rem",
                fontSize: "0.9375rem",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: "0.5rem",
                background: "var(--primary-700, #0f766e)",
              }}
            >
              <BrandLogo name="microsoft" size={18} />
              {saving ? "Redirecting to Microsoft..." : "Sign in with Microsoft 365"}
            </Button>
          </div>
        )}

        {/* 3. LOCAL FILES & FOLDERS WIZARD */}
        {isLocalFiles && (
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            <div
              style={{
                padding: "1rem",
                background: "#fffbeb",
                border: "1px solid #fef3c7",
                borderRadius: "0.5rem",
                fontSize: "0.8125rem",
                color: "#92400e",
                lineHeight: 1.5,
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontWeight: 600, marginBottom: "0.25rem" }}>
                <FolderIcon size={16} /> Desktop Agent Required for Client Files
              </div>
              Browser web applications cannot directly read private files from your laptop without an installed local agent.
              You have two options:
              <ul style={{ margin: "0.5rem 0 0", paddingLeft: "1.25rem" }}>
                <li><strong>Nanvi Local Windows Agent:</strong> Run the lightweight agent on your machine to pair local folders.</li>
                <li><strong>Server-Side Company Folder:</strong> Connect a mounted folder on this server instance.</li>
              </ul>
            </div>

            <form onSubmit={handleSave} style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
              <div>
                <label style={{ display: "block", fontSize: "0.75rem", fontWeight: 600, marginBottom: "0.375rem" }}>
                  Server-side Folder Path (Optional)
                </label>
                <input
                  type="text"
                  placeholder="e.g. C:\CompanyDocs or /data/documents"
                  value={formData.base_path || ""}
                  onChange={(e) => setFormData({ ...formData, base_path: e.target.value })}
                  style={{
                    width: "100%",
                    padding: "0.5rem 0.75rem",
                    borderRadius: "0.375rem",
                    border: "1px solid var(--border, #e2e8f0)",
                    background: "var(--bg-surface, #ffffff)",
                    fontSize: "0.875rem",
                  }}
                />
              </div>

              <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.75rem" }}>
                <Button type="button" variant="secondary" onClick={handleTest} disabled={testing}>
                  {testing ? "Testing..." : "Verify Path"}
                </Button>
                <Button type="submit" variant="primary" disabled={saving}>
                  {saving ? "Saving..." : "Save Local Files Connection"}
                </Button>
              </div>
            </form>
          </div>
        )}

        {/* 4. GENERIC / DATABASE / API FORMS (FALLBACK) */}
        {!isGoogle && !isMicrosoft && !isLocalFiles && (
          <form onSubmit={handleSave} style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            <div>
              <label style={{ display: "block", fontSize: "0.75rem", fontWeight: 600, marginBottom: "0.375rem" }}>
                Display Name (Optional)
              </label>
              <input
                type="text"
                placeholder={provider.name}
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                style={{
                  width: "100%",
                  padding: "0.5rem 0.75rem",
                  borderRadius: "0.375rem",
                  border: "1px solid var(--border, #e2e8f0)",
                  background: "var(--bg-surface, #ffffff)",
                  fontSize: "0.875rem",
                }}
              />
            </div>

            {/* Dynamic schema inputs */}
            {Object.entries(provider.configuration_schema?.properties || {}).map(([key, prop]: [string, any]) => {
              const isRequired = (provider.configuration_schema?.required || []).includes(key);
              const isPassword = prop.format === "password";
              const isBoolean = prop.type === "boolean";
              const isEnum = Array.isArray(prop.enum);

              if (isBoolean) {
                return (
                  <label key={key} style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.8125rem", cursor: "pointer" }}>
                    <input
                      type="checkbox"
                      checked={formData[key] ?? prop.default ?? false}
                      onChange={(e) => setFormData({ ...formData, [key]: e.target.checked })}
                    />
                    <span>{prop.title || key}</span>
                  </label>
                );
              }

              if (isEnum) {
                return (
                  <div key={key}>
                    <label style={{ display: "block", fontSize: "0.75rem", fontWeight: 600, marginBottom: "0.375rem" }}>
                      {prop.title || key} {isRequired && <span style={{ color: "red" }}>*</span>}
                    </label>
                    <select
                      value={formData[key] ?? prop.default ?? prop.enum[0]}
                      onChange={(e) => setFormData({ ...formData, [key]: e.target.value })}
                      style={{
                        width: "100%",
                        padding: "0.5rem 0.75rem",
                        borderRadius: "0.375rem",
                        border: "1px solid var(--border, #e2e8f0)",
                        background: "var(--bg-surface, #ffffff)",
                        fontSize: "0.875rem",
                      }}
                    >
                      {prop.enum.map((opt: string) => (
                        <option key={opt} value={opt}>{opt}</option>
                      ))}
                    </select>
                  </div>
                );
              }

              return (
                <div key={key}>
                  <label style={{ display: "block", fontSize: "0.75rem", fontWeight: 600, marginBottom: "0.375rem" }}>
                    {prop.title || key} {isRequired && <span style={{ color: "red" }}>*</span>}
                  </label>
                  <input
                    type={isPassword ? "password" : "text"}
                    required={isRequired}
                    placeholder={prop.description || prop.default || ""}
                    value={formData[key] ?? ""}
                    onChange={(e) => setFormData({ ...formData, [key]: e.target.value })}
                    style={{
                      width: "100%",
                      padding: "0.5rem 0.75rem",
                      borderRadius: "0.375rem",
                      border: "1px solid var(--border, #e2e8f0)",
                      background: "var(--bg-surface, #ffffff)",
                      fontSize: "0.875rem",
                    }}
                  />
                  {prop.description && (
                    <span style={{ display: "block", fontSize: "0.6875rem", color: "var(--text-muted, #64748b)", marginTop: "0.25rem" }}>
                      {prop.description}
                    </span>
                  )}
                </div>
              );
            })}

            {/* Test Connection Alert Feedback */}
            {testResult && (
              <Alert tone={testResult.ok ? "success" : "danger"}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                  {testResult.ok ? <CheckCircleIcon size={16} /> : <AlertCircleIcon size={16} />}
                  <span>{testResult.message}</span>
                </div>
              </Alert>
            )}

            {/* Action Buttons */}
            <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.75rem", marginTop: "0.5rem" }}>
              <Button type="button" variant="secondary" onClick={handleTest} disabled={testing || saving}>
                {testing ? "Testing..." : "Test Connectivity"}
              </Button>
              <Button type="submit" variant="primary" disabled={saving || testing}>
                {saving ? "Saving..." : "Save Connection"}
              </Button>
            </div>
          </form>
        )}
      </div>
    </Modal>
  );
}
