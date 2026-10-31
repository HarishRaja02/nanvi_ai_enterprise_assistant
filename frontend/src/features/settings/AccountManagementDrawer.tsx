import React, { useState, useEffect } from "react";
import { BrandLogo } from "../../components/brand/BrandLogo";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Alert } from "../../components/ui/Alert";
import { useToast } from "../../components/ui/Toast";
import {
  CheckCircleIcon,
  AlertCircleIcon,
  RefreshCwIcon,
  ShieldCheckIcon,
  LockIcon,
  CheckIcon,
  DownloadIcon,
  FileTextIcon,
  MailIcon,
  TrashIcon,
} from "../../icons";
import type {
  NanviApiClient,
  ConnectionPublic,
  ServiceState,
  ConnectionAuditEvent,
  SyncConfig,
} from "../../api";

type Props = {
  open: boolean;
  connection: ConnectionPublic | null;
  onClose: () => void;
  onUpdated: () => void;
  onRequestDisconnect: (conn: ConnectionPublic) => void;
  api: NanviApiClient;
};

type TabType = "overview" | "services" | "sync" | "security";

export function AccountManagementDrawer({
  open,
  connection,
  onClose,
  onUpdated,
  onRequestDisconnect,
  api,
}: Props) {
  const notify = useToast();
  const [activeTab, setActiveTab] = useState<TabType>("services");
  const [services, setServices] = useState<ServiceState[]>([]);
  const [loadingServices, setLoadingServices] = useState(false);
  const [updatingServiceId, setUpdatingServiceId] = useState<string | null>(null);

  // Sync settings state
  const [autoSync, setAutoSync] = useState(true);
  const [syncFreq, setSyncFreq] = useState("1h");
  const [savingSync, setSavingSync] = useState(false);
  const [syncingNow, setSyncingNow] = useState(false);

  // Diagnostics & testing
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string } | null>(null);

  // Security audit trail
  const [auditLogs, setAuditLogs] = useState<ConnectionAuditEvent[]>([]);
  const [loadingAudit, setLoadingAudit] = useState(false);

  // Rename connection
  const [displayName, setDisplayName] = useState("");
  const [savingName, setSavingName] = useState(false);

  // Sync connection state on open or change
  useEffect(() => {
    if (connection) {
      setDisplayName(connection.display_name || "");
      setAutoSync(connection.auto_sync ?? connection.sync_config?.auto_sync ?? true);
      setSyncFreq(connection.sync_frequency ?? connection.sync_config?.frequency ?? "1h");
      setServices(connection.services || []);
      setTestResult(null);

      // Fetch fresh services and audit logs
      loadServices();
      loadAudit();
    }
  }, [connection?.id]);

  const loadServices = async () => {
    if (!connection) return;
    try {
      setLoadingServices(true);
      const res = await api.getConnectionServices(connection.id);
      if (res?.services) {
        setServices(res.services);
      }
    } catch {
      // Fallback to connection.services
      if (connection.services) setServices(connection.services);
    } finally {
      setLoadingServices(false);
    }
  };

  const loadAudit = async () => {
    if (!connection) return;
    try {
      setLoadingAudit(true);
      const logs = await api.listConnectionAudit(connection.id);
      setAuditLogs(Array.isArray(logs) ? logs : []);
    } catch {
      setAuditLogs([]);
    } finally {
      setLoadingAudit(false);
    }
  };

  if (!open || !connection) return null;

  // Toggle individual service enabled / disabled
  const handleToggleService = async (service: ServiceState) => {
    if (service.status === "UNAUTHORIZED") {
      notify(
        `Cannot enable ${service.name}: missing required OAuth scope (${service.requires_scopes.join(", ")}). Please re-authorize the account.`,
        "error"
      );
      return;
    }

    const nextEnabled = !service.enabled;
    try {
      setUpdatingServiceId(service.id);
      const res = await api.updateConnectionService(connection.id, service.id, {
        enabled: nextEnabled,
      });

      if (res?.service) {
        setServices((prev) =>
          prev.map((s) => (s.id === service.id ? res.service : s))
        );
        notify(
          `${service.name} is now ${nextEnabled ? "Enabled" : "Disabled"}. AI Assistant will ${nextEnabled ? "now access" : "no longer access"} this service.`,
          nextEnabled ? "success" : "info"
        );
        onUpdated();
        loadAudit();
      }
    } catch (err: any) {
      notify(err.message || `Failed to update ${service.name}.`, "error");
    } finally {
      setUpdatingServiceId(null);
    }
  };

  // Toggle granular permission checkbox for a service
  const handleTogglePermission = async (service: ServiceState, permId: string, currentEnabled: boolean) => {
    const updatedPerms = service.permissions.map((p) =>
      p.id === permId ? p.id : (p.enabled ? p.id : null)
    ).filter(Boolean) as string[];

    const finalPerms = currentEnabled
      ? updatedPerms.filter((id) => id !== permId)
      : [...updatedPerms, permId];

    try {
      setUpdatingServiceId(service.id);
      const res = await api.updateConnectionService(connection.id, service.id, {
        permissions: finalPerms,
      });
      if (res?.service) {
        setServices((prev) =>
          prev.map((s) => (s.id === service.id ? res.service : s))
        );
        notify(`Updated permissions for ${service.name}.`, "success");
        onUpdated();
      }
    } catch (err: any) {
      notify(err.message || "Failed to update permissions.", "error");
    } finally {
      setUpdatingServiceId(null);
    }
  };

  // Test connection
  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const res = await api.testConnection(connection.id);
      setTestResult(res);
      if (res.ok) {
        notify("Connection test succeeded! All credentials are verified.", "success");
      } else {
        notify(res.message || "Connection test failed.", "error");
      }
      onUpdated();
      loadAudit();
    } catch (err: any) {
      setTestResult({ ok: false, message: err.message || "Test failed." });
      notify(err.message || "Test failed.", "error");
    } finally {
      setTesting(false);
    }
  };

  // Save sync config
  const handleSaveSync = async () => {
    setSavingSync(true);
    try {
      await api.updateConnectionSyncConfig(connection.id, {
        auto_sync: autoSync,
        frequency: syncFreq,
      });
      notify("Synchronization settings saved successfully.", "success");
      onUpdated();
      loadAudit();
    } catch (err: any) {
      notify(err.message || "Failed to save sync settings.", "error");
    } finally {
      setSavingSync(false);
    }
  };

  // Trigger sync now
  const handleSyncNow = async () => {
    setSyncingNow(true);
    try {
      const res = await api.syncConnection(connection.id);
      notify(
        `Sync completed: ${res.items_checked ?? 0} resources checked at ${new Date(res.synced_at).toLocaleTimeString()}`,
        "success"
      );
      onUpdated();
      loadAudit();
    } catch (err: any) {
      notify(err.message || "Sync failed.", "error");
    } finally {
      setSyncingNow(false);
    }
  };

  // Rename connection
  const handleRename = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!displayName.trim()) return;
    setSavingName(true);
    try {
      await api.updateConnection(connection.id, { display_name: displayName.trim() });
      notify("Connection display name updated.", "success");
      onUpdated();
    } catch (err: any) {
      notify(err.message || "Failed to rename connection.", "error");
    } finally {
      setSavingName(false);
    }
  };

  const enabledCount = services.filter((s) => s.enabled).length;
  const isHealthy = connection.status === "CONNECTED";
  const isError = connection.status === "ERROR";

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 100,
        display: "flex",
        justifyContent: "flex-end",
        backgroundColor: "rgba(15, 23, 42, 0.45)",
        backdropFilter: "blur(2px)",
        animation: "fadeIn 0.2s ease-out",
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        role="dialog"
        aria-label={`Manage ${connection.display_name}`}
        style={{
          width: "100%",
          maxWidth: "680px",
          height: "100%",
          background: "var(--bg-surface, #ffffff)",
          boxShadow: "-8px 0 24px rgba(0,0,0,0.12)",
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
          borderLeft: "1px solid var(--border, #e2e8f0)",
          fontFamily: "var(--font-sans, 'IBM Plex Sans', -apple-system, sans-serif)",
        }}
      >
        {/* Drawer Header */}
        <div
          style={{
            padding: "1.25rem 1.5rem",
            borderBottom: "1px solid var(--border, #e2e8f0)",
            background: "var(--bg-surface, #ffffff)",
            display: "flex",
            flexDirection: "column",
            gap: "0.875rem",
          }}
        >
          <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "1rem" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "0.875rem" }}>
              <div
                style={{
                  width: "3rem",
                  height: "3rem",
                  borderRadius: "0.625rem",
                  background: "var(--bg-sunken, #f8fafc)",
                  border: "1px solid var(--border, #e2e8f0)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  flexShrink: 0,
                }}
              >
                <BrandLogo name={connection.provider} size={32} />
              </div>
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                  <h3
                    style={{
                      margin: 0,
                      fontSize: "1.125rem",
                      fontWeight: 600,
                      color: "var(--text, #0f172a)",
                    }}
                  >
                    {connection.display_name}
                  </h3>
                  <Badge tone={connection.scope_level === "organization" ? "primary" : "neutral"}>
                    {connection.account_type || (connection.scope_level === "organization" ? "Organization" : "Personal")}
                  </Badge>
                  <Badge tone={isHealthy ? "success" : isError ? "danger" : "neutral"}>
                    {connection.status}
                  </Badge>
                </div>
                <p style={{ margin: "0.25rem 0 0", fontSize: "0.8125rem", color: "var(--text-muted, #64748b)" }}>
                  {connection.account_identifier || connection.provider}
                </p>
              </div>
            </div>

            <button
              type="button"
              onClick={onClose}
              aria-label="Close drawer"
              style={{
                background: "none",
                border: "none",
                fontSize: "1.5rem",
                lineHeight: 1,
                cursor: "pointer",
                color: "var(--text-muted, #64748b)",
                padding: "0.375rem",
                borderRadius: "0.375rem",
              }}
            >
              ×
            </button>
          </div>

          {/* Quick Metrics Bar */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "1.5rem",
              padding: "0.625rem 0.875rem",
              background: "var(--bg-sunken, #f8fafc)",
              borderRadius: "0.375rem",
              fontSize: "0.75rem",
              color: "var(--text-secondary, #475569)",
            }}
          >
            <div>
              <span style={{ color: "var(--text-muted, #64748b)" }}>Active Services: </span>
              <strong>{enabledCount} of {services.length} enabled</strong>
            </div>
            <div>
              <span style={{ color: "var(--text-muted, #64748b)" }}>Last Sync: </span>
              <span>{connection.last_synced_at ? new Date(connection.last_synced_at).toLocaleTimeString() : "Never"}</span>
            </div>
            <div>
              <span style={{ color: "var(--text-muted, #64748b)" }}>Auth Method: </span>
              <span style={{ textTransform: "capitalize" }}>{connection.credential_type || "OAuth 2.0"}</span>
            </div>
          </div>

          {/* Tabs Navigation */}
          <div style={{ display: "flex", gap: "0.5rem", borderBottom: "1px solid var(--border-subtle, #f1f5f9)", marginTop: "0.25rem" }}>
            {[
              { id: "services", label: `Services & Permissions (${enabledCount}/${services.length})` },
              { id: "overview", label: "Overview & Diagnostics" },
              { id: "sync", label: "Sync Settings" },
              { id: "security", label: "Security & Audit" },
            ].map((tab) => {
              const active = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => setActiveTab(tab.id as TabType)}
                  style={{
                    padding: "0.5rem 0.75rem",
                    border: "none",
                    background: "none",
                    fontSize: "0.8125rem",
                    fontWeight: active ? 600 : 500,
                    color: active ? "var(--primary-700, #0f766e)" : "var(--text-muted, #64748b)",
                    borderBottom: active ? "2px solid var(--primary-600, #0f766e)" : "2px solid transparent",
                    cursor: "pointer",
                    transition: "color 0.15s, border-color 0.15s",
                    whiteSpace: "nowrap",
                  }}
                >
                  {tab.label}
                </button>
              );
            })}
          </div>
        </div>

        {/* Drawer Body */}
        <div style={{ flex: 1, overflowY: "auto", padding: "1.5rem", display: "flex", flexDirection: "column", gap: "1.25rem" }}>
          {/* TAB 1: SERVICES & PERMISSIONS */}
          {activeTab === "services" && (
            <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
              <div
                style={{
                  padding: "0.875rem 1rem",
                  background: "var(--bg-sunken, #f8fafc)",
                  borderRadius: "0.5rem",
                  border: "1px solid var(--border, #e2e8f0)",
                  fontSize: "0.8125rem",
                  lineHeight: 1.5,
                  color: "var(--text-secondary, #475569)",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontWeight: 600, color: "var(--text, #0f172a)", marginBottom: "0.25rem" }}>
                  <ShieldCheckIcon size={16} color="var(--primary-600, #0f766e)" />
                  Backend-Enforced Service Authorization
                </div>
                Toggle individual services below. If a service is disabled, the AI Assistant is strictly prohibited by backend authorization from searching or retrieving any documents, emails, or data from that service.
              </div>

              {loadingServices ? (
                <div style={{ textAlign: "center", padding: "2rem", color: "var(--text-muted, #64748b)" }}>
                  <RefreshCwIcon size={20} className="animate-spin" style={{ margin: "0 auto 0.5rem" }} />
                  Loading services...
                </div>
              ) : services.length === 0 ? (
                <div style={{ textAlign: "center", padding: "2rem", color: "var(--text-muted, #64748b)" }}>
                  No individual services defined for this integration provider.
                </div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: "0.875rem" }}>
                  {services.map((service) => {
                    const isUpdating = updatingServiceId === service.id;
                    const isUnauthorized = service.status === "UNAUTHORIZED";

                    return (
                      <div
                        key={service.id}
                        style={{
                          background: "var(--bg-surface, #ffffff)",
                          border: `1px solid ${service.enabled ? "var(--primary-200, #99f6e4)" : "var(--border, #e2e8f0)"}`,
                          borderRadius: "0.5rem",
                          padding: "1rem",
                          display: "flex",
                          flexDirection: "column",
                          gap: "0.75rem",
                          boxShadow: service.enabled ? "0 1px 3px rgba(15, 118, 110, 0.05)" : "none",
                          transition: "border-color 0.2s, background-color 0.2s",
                        }}
                      >
                        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "1rem" }}>
                          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                            <div
                              style={{
                                width: "2.5rem",
                                height: "2.5rem",
                                borderRadius: "0.375rem",
                                background: "var(--bg-sunken, #f8fafc)",
                                border: "1px solid var(--border, #e2e8f0)",
                                display: "flex",
                                alignItems: "center",
                                justifyContent: "center",
                                flexShrink: 0,
                              }}
                            >
                              <BrandLogo name={service.id} size={22} />
                            </div>
                            <div>
                              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                                <h4 style={{ margin: 0, fontSize: "0.9375rem", fontWeight: 600, color: "var(--text, #0f172a)" }}>
                                  {service.name}
                                </h4>
                                {service.enabled ? (
                                  <Badge tone="success">Enabled</Badge>
                                ) : isUnauthorized ? (
                                  <Badge tone="danger">Re-Auth Required</Badge>
                                ) : (
                                  <Badge tone="neutral">Disabled</Badge>
                                )}
                              </div>
                              <p style={{ margin: "0.25rem 0 0", fontSize: "0.75rem", color: "var(--text-muted, #64748b)" }}>
                                {service.description}
                              </p>
                            </div>
                          </div>

                          {/* Toggle Switch */}
                          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                            <label
                              style={{
                                position: "relative",
                                display: "inline-block",
                                width: "42px",
                                height: "24px",
                                opacity: isUnauthorized ? 0.5 : 1,
                                cursor: isUnauthorized ? "not-allowed" : "pointer",
                              }}
                              title={isUnauthorized ? "Requires broader OAuth re-authorization" : undefined}
                            >
                              <input
                                type="checkbox"
                                checked={service.enabled}
                                disabled={isUpdating || isUnauthorized}
                                onChange={() => handleToggleService(service)}
                                style={{ opacity: 0, width: 0, height: 0 }}
                              />
                              <span
                                style={{
                                  position: "absolute",
                                  cursor: isUnauthorized ? "not-allowed" : "pointer",
                                  inset: 0,
                                  backgroundColor: service.enabled ? "var(--primary-600, #0f766e)" : "#cbd5e1",
                                  transition: "0.2s",
                                  borderRadius: "24px",
                                }}
                              >
                                <span
                                  style={{
                                    position: "absolute",
                                    height: "18px",
                                    width: "18px",
                                    left: service.enabled ? "20px" : "3px",
                                    bottom: "3px",
                                    backgroundColor: "#ffffff",
                                    transition: "0.2s",
                                    borderRadius: "50%",
                                    boxShadow: "0 1px 2px rgba(0,0,0,0.2)",
                                  }}
                                />
                              </span>
                            </label>
                          </div>
                        </div>

                        {/* Unauthorized warning banner */}
                        {isUnauthorized && (
                          <div
                            style={{
                              padding: "0.5rem 0.75rem",
                              background: "#fef2f2",
                              borderRadius: "0.375rem",
                              fontSize: "0.75rem",
                              color: "#b91c1c",
                              display: "flex",
                              alignItems: "center",
                              gap: "0.375rem",
                            }}
                          >
                            <AlertCircleIcon size={14} />
                            <span>
                              Scope <code>{service.requires_scopes.join(", ")}</code> not granted. Reconnect this account to authorize this service.
                            </span>
                          </div>
                        )}

                        {/* Granular Permissions Section */}
                        {service.permissions && service.permissions.length > 0 && (
                          <div
                            style={{
                              borderTop: "1px solid var(--border-subtle, #f1f5f9)",
                              paddingTop: "0.625rem",
                              marginTop: "0.25rem",
                              display: "flex",
                              flexDirection: "column",
                              gap: "0.5rem",
                            }}
                          >
                            <span style={{ fontSize: "0.6875rem", fontWeight: 600, color: "var(--text-muted, #64748b)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                              Granular Permissions
                            </span>
                            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem" }}>
                              {service.permissions.map((perm) => (
                                <label
                                  key={perm.id}
                                  style={{
                                    display: "flex",
                                    alignItems: "center",
                                    gap: "0.375rem",
                                    fontSize: "0.75rem",
                                    color: "var(--text-secondary, #475569)",
                                    cursor: service.enabled ? "pointer" : "not-allowed",
                                    opacity: service.enabled ? 1 : 0.6,
                                  }}
                                >
                                  <input
                                    type="checkbox"
                                    checked={perm.enabled}
                                    disabled={!service.enabled || isUpdating}
                                    onChange={() => handleTogglePermission(service, perm.id, perm.enabled)}
                                  />
                                  <span>{perm.name}</span>
                                </label>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* TAB 2: OVERVIEW & DIAGNOSTICS */}
          {activeTab === "overview" && (
            <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
              {/* Rename Form */}
              <form
                onSubmit={handleRename}
                style={{
                  background: "var(--bg-sunken, #f8fafc)",
                  padding: "1rem",
                  borderRadius: "0.5rem",
                  border: "1px solid var(--border, #e2e8f0)",
                  display: "flex",
                  flexDirection: "column",
                  gap: "0.75rem",
                }}
              >
                <label style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--text, #0f172a)" }}>
                  Connection Display Name
                </label>
                <div style={{ display: "flex", gap: "0.5rem" }}>
                  <input
                    type="text"
                    value={displayName}
                    onChange={(e) => setDisplayName(e.target.value)}
                    style={{
                      flex: 1,
                      padding: "0.5rem 0.75rem",
                      borderRadius: "0.375rem",
                      border: "1px solid var(--border, #e2e8f0)",
                      background: "var(--bg-surface, #ffffff)",
                      color: "var(--text, #0f172a)",
                      fontSize: "0.875rem",
                    }}
                  />
                  <Button type="submit" variant="secondary" size="sm" disabled={savingName}>
                    {savingName ? "Saving..." : "Rename"}
                  </Button>
                </div>
              </form>

              {/* Technical Diagnostics */}
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr",
                  gap: "0.875rem",
                  padding: "1rem",
                  background: "var(--bg-sunken, #f8fafc)",
                  borderRadius: "0.5rem",
                  border: "1px solid var(--border, #e2e8f0)",
                  fontSize: "0.8125rem",
                }}
              >
                <div>
                  <span style={{ color: "var(--text-muted, #64748b)" }}>Provider ID: </span>
                  <strong>{connection.provider}</strong>
                </div>
                <div>
                  <span style={{ color: "var(--text-muted, #64748b)" }}>Account Type: </span>
                  <strong>{connection.account_type || (connection.scope_level === "organization" ? "Organization" : "Personal")}</strong>
                </div>
                <div>
                  <span style={{ color: "var(--text-muted, #64748b)" }}>Connected At: </span>
                  <span>{connection.created_at ? new Date(connection.created_at).toLocaleDateString() : "Unknown"}</span>
                </div>
                <div>
                  <span style={{ color: "var(--text-muted, #64748b)" }}>Last Tested: </span>
                  <span>{connection.last_tested_at ? new Date(connection.last_tested_at).toLocaleString() : "Never"}</span>
                </div>
                <div>
                  <span style={{ color: "var(--text-muted, #64748b)" }}>Last Sync: </span>
                  <span>{connection.last_synced_at ? new Date(connection.last_synced_at).toLocaleString() : "Never"}</span>
                </div>
                <div>
                  <span style={{ color: "var(--text-muted, #64748b)" }}>Last Used: </span>
                  <span>{connection.last_used_at ? new Date(connection.last_used_at).toLocaleString() : "Never"}</span>
                </div>
              </div>

              {/* Test Connection Result */}
              {testResult && (
                <Alert tone={testResult.ok ? "success" : "danger"}>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                    {testResult.ok ? <CheckCircleIcon size={16} /> : <AlertCircleIcon size={16} />}
                    <span>{testResult.message}</span>
                  </div>
                </Alert>
              )}

              {/* Test Action */}
              <div style={{ display: "flex", justifyContent: "flex-end" }}>
                <Button
                  type="button"
                  variant="primary"
                  onClick={handleTest}
                  disabled={testing}
                  style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}
                >
                  <RefreshCwIcon size={14} className={testing ? "animate-spin" : ""} />
                  {testing ? "Testing Connectivity..." : "Run Connection Test"}
                </Button>
              </div>
            </div>
          )}

          {/* TAB 3: SYNC SETTINGS */}
          {activeTab === "sync" && (
            <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
              <div
                style={{
                  background: "var(--bg-sunken, #f8fafc)",
                  padding: "1.25rem",
                  borderRadius: "0.5rem",
                  border: "1px solid var(--border, #e2e8f0)",
                  display: "flex",
                  flexDirection: "column",
                  gap: "1.25rem",
                }}
              >
                {/* Auto Sync Toggle */}
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                  <div>
                    <h4 style={{ margin: 0, fontSize: "0.9375rem", fontWeight: 600, color: "var(--text, #0f172a)" }}>
                      Automatic Synchronization
                    </h4>
                    <p style={{ margin: "0.25rem 0 0", fontSize: "0.75rem", color: "var(--text-muted, #64748b)" }}>
                      Periodically pull and index new emails, documents, or records from enabled services.
                    </p>
                  </div>
                  <label
                    style={{
                      position: "relative",
                      display: "inline-block",
                      width: "42px",
                      height: "24px",
                      cursor: "pointer",
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={autoSync}
                      onChange={(e) => setAutoSync(e.target.checked)}
                      style={{ opacity: 0, width: 0, height: 0 }}
                    />
                    <span
                      style={{
                        position: "absolute",
                        inset: 0,
                        backgroundColor: autoSync ? "var(--primary-600, #0f766e)" : "#cbd5e1",
                        transition: "0.2s",
                        borderRadius: "24px",
                      }}
                    >
                      <span
                        style={{
                          position: "absolute",
                          height: "18px",
                          width: "18px",
                          left: autoSync ? "20px" : "3px",
                          bottom: "3px",
                          backgroundColor: "#ffffff",
                          transition: "0.2s",
                          borderRadius: "50%",
                          boxShadow: "0 1px 2px rgba(0,0,0,0.2)",
                        }}
                      />
                    </span>
                  </label>
                </div>

                {/* Frequency selector */}
                <div>
                  <label style={{ display: "block", fontSize: "0.8125rem", fontWeight: 600, color: "var(--text, #0f172a)", marginBottom: "0.375rem" }}>
                    Synchronization Interval
                  </label>
                  <select
                    value={syncFreq}
                    disabled={!autoSync}
                    onChange={(e) => setSyncFreq(e.target.value)}
                    style={{
                      width: "100%",
                      padding: "0.5rem 0.75rem",
                      borderRadius: "0.375rem",
                      border: "1px solid var(--border, #e2e8f0)",
                      background: "var(--bg-surface, #ffffff)",
                      color: "var(--text, #0f172a)",
                      fontSize: "0.875rem",
                    }}
                  >
                    <option value="15m">Every 15 minutes (High activity)</option>
                    <option value="1h">Every 1 hour (Recommended)</option>
                    <option value="6h">Every 6 hours</option>
                    <option value="24h">Daily (Low activity)</option>
                    <option value="manual">Manual only</option>
                  </select>
                </div>

                <div style={{ display: "flex", justifyContent: "flex-end" }}>
                  <Button type="button" variant="primary" size="sm" onClick={handleSaveSync} disabled={savingSync}>
                    {savingSync ? "Saving..." : "Save Sync Settings"}
                  </Button>
                </div>
              </div>

              {/* On-Demand Sync Now */}
              <div
                style={{
                  background: "var(--bg-surface, #ffffff)",
                  padding: "1.25rem",
                  borderRadius: "0.5rem",
                  border: "1px solid var(--border, #e2e8f0)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                }}
              >
                <div>
                  <h4 style={{ margin: 0, fontSize: "0.9375rem", fontWeight: 600, color: "var(--text, #0f172a)" }}>
                    On-Demand Synchronization
                  </h4>
                  <p style={{ margin: "0.25rem 0 0", fontSize: "0.75rem", color: "var(--text-muted, #64748b)" }}>
                    Trigger an immediate background synchronization across all authorized services.
                  </p>
                </div>
                <Button
                  type="button"
                  variant="secondary"
                  onClick={handleSyncNow}
                  disabled={syncingNow}
                  style={{ display: "flex", alignItems: "center", gap: "0.375rem" }}
                >
                  <RefreshCwIcon size={14} className={syncingNow ? "animate-spin" : ""} />
                  {syncingNow ? "Syncing..." : "Sync Now"}
                </Button>
              </div>
            </div>
          )}

          {/* TAB 4: SECURITY & AUDIT */}
          {activeTab === "security" && (
            <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
              {/* Security info banner */}
              <div
                style={{
                  padding: "1rem",
                  background: "var(--bg-sunken, #f8fafc)",
                  borderRadius: "0.5rem",
                  border: "1px solid var(--border, #e2e8f0)",
                  display: "flex",
                  flexDirection: "column",
                  gap: "0.5rem",
                  fontSize: "0.8125rem",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontWeight: 600, color: "var(--text, #0f172a)" }}>
                  <LockIcon size={16} /> Credential & Token Encryption
                </div>
                <p style={{ margin: 0, color: "var(--text-secondary, #475569)", lineHeight: 1.45 }}>
                  Access tokens, refresh tokens, and credentials are encrypted at rest using AES-128-CBC with a secure tenant-isolated key. Tokens are automatically refreshed prior to expiration.
                </p>
              </div>

              {/* Granted OAuth Scopes */}
              <div>
                <h4 style={{ margin: "0 0 0.5rem", fontSize: "0.875rem", fontWeight: 600, color: "var(--text, #0f172a)" }}>
                  Granted OAuth Scopes
                </h4>
                {connection.granted_scopes && connection.granted_scopes.length > 0 ? (
                  <div style={{ display: "flex", flexWrap: "wrap", gap: "0.375rem" }}>
                    {connection.granted_scopes.map((scope) => (
                      <span
                        key={scope}
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: "0.25rem",
                          padding: "0.25rem 0.5rem",
                          background: "var(--bg-sunken, #f8fafc)",
                          borderRadius: "0.25rem",
                          border: "1px solid var(--border, #e2e8f0)",
                          fontSize: "0.75rem",
                          fontFamily: "monospace",
                          color: "var(--text-secondary, #475569)",
                        }}
                      >
                        <CheckIcon size={12} color="var(--primary-600, #0f766e)" />
                        {scope}
                      </span>
                    ))}
                  </div>
                ) : (
                  <p style={{ margin: 0, fontSize: "0.75rem", color: "var(--text-muted, #64748b)" }}>
                    No explicit OAuth scopes recorded (API Key or Direct Database Authentication).
                  </p>
                )}
              </div>

              {/* Connection Audit History */}
              <div>
                <h4 style={{ margin: "0 0 0.5rem", fontSize: "0.875rem", fontWeight: 600, color: "var(--text, #0f172a)" }}>
                  Integration Audit Trail
                </h4>
                {loadingAudit ? (
                  <div style={{ textAlign: "center", padding: "1rem", color: "var(--text-muted, #64748b)", fontSize: "0.8125rem" }}>
                    Loading audit trail...
                  </div>
                ) : auditLogs.length === 0 ? (
                  <div style={{ padding: "1rem", background: "var(--bg-sunken, #f8fafc)", borderRadius: "0.375rem", fontSize: "0.75rem", color: "var(--text-muted, #64748b)" }}>
                    No recent audit events recorded for this connection.
                  </div>
                ) : (
                  <div
                    style={{
                      border: "1px solid var(--border, #e2e8f0)",
                      borderRadius: "0.375rem",
                      overflow: "hidden",
                      fontSize: "0.75rem",
                    }}
                  >
                    <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left" }}>
                      <thead style={{ background: "var(--bg-sunken, #f8fafc)", borderBottom: "1px solid var(--border, #e2e8f0)" }}>
                        <tr>
                          <th style={{ padding: "0.5rem 0.75rem", fontWeight: 600, color: "var(--text-muted, #64748b)" }}>Timestamp</th>
                          <th style={{ padding: "0.5rem 0.75rem", fontWeight: 600, color: "var(--text-muted, #64748b)" }}>Event</th>
                          <th style={{ padding: "0.5rem 0.75rem", fontWeight: 600, color: "var(--text-muted, #64748b)" }}>Details</th>
                        </tr>
                      </thead>
                      <tbody>
                        {auditLogs.slice(0, 15).map((log, i) => (
                          <tr key={log.id || i} style={{ borderBottom: "1px solid var(--border-subtle, #f1f5f9)" }}>
                            <td style={{ padding: "0.5rem 0.75rem", whiteSpace: "nowrap", color: "var(--text-muted, #64748b)" }}>
                              {new Date(log.created_at).toLocaleTimeString()}
                            </td>
                            <td style={{ padding: "0.5rem 0.75rem", fontWeight: 500, color: "var(--text, #0f172a)" }}>
                              {log.event_type}
                            </td>
                            <td style={{ padding: "0.5rem 0.75rem", color: "var(--text-secondary, #475569)" }}>
                              {JSON.stringify(log.details)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Drawer Footer with Disconnect Option */}
        <div
          style={{
            padding: "1rem 1.5rem",
            borderTop: "1px solid var(--border, #e2e8f0)",
            background: "var(--bg-sunken, #f8fafc)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <Button
            type="button"
            variant="danger"
            size="sm"
            onClick={() => onRequestDisconnect(connection)}
            style={{ display: "flex", alignItems: "center", gap: "0.375rem" }}
          >
            <TrashIcon size={14} />
            Disconnect Account
          </Button>

          <Button type="button" variant="secondary" size="sm" onClick={onClose}>
            Done
          </Button>
        </div>
      </div>
    </div>
  );
}
