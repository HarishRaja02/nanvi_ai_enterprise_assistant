import { useState } from "react";
import { Modal } from "../../components/ui/Modal";
import { Button } from "../../components/ui/Button";
import { Alert } from "../../components/ui/Alert";
import { ShieldCheckIcon, PlugIcon, CheckCircleIcon, AlertCircleIcon, RefreshCwIcon } from "../../icons";
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

  if (!open || !provider) return null;

  const isOAuth = provider.auth_type === "oauth2";
  const schema = provider.configuration_schema?.properties || {};
  const requiredFields: string[] = provider.configuration_schema?.required || [];

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
        notify("Configuration test succeeded!", "success");
      } else {
        notify(res.message || "Test failed. Check your credentials.", "error");
      }
    } catch (err: any) {
      setTestResult({ ok: false, message: err.message || "Connection test failed." });
      notify(err.message || "Test failed.", "error");
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
        <div style={{
          display: "flex",
          alignItems: "center",
          gap: "1rem",
          padding: "1rem",
          background: "var(--bg-sunken)",
          borderRadius: "0.5rem",
          border: "1px solid var(--border)",
        }}>
          <div style={{
            width: "2.75rem",
            height: "2.75rem",
            borderRadius: "0.5rem",
            background: "var(--bg-surface)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            border: "1px solid var(--border)",
            color: "var(--primary-600)",
          }}>
            <PlugIcon size={24} />
          </div>
          <div>
            <h3 style={{ margin: 0, fontSize: "var(--text-lg)", fontWeight: "var(--weight-semibold)" }}>{provider.name}</h3>
            <p style={{ margin: "0.25rem 0 0", fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>{provider.description}</p>
          </div>
        </div>

        {/* Scope Level Selector */}
        <div>
          <label style={{ display: "block", fontSize: "var(--text-xs)", fontWeight: "var(--weight-semibold)", marginBottom: "0.5rem" }}>
            Access Scope
          </label>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
            <button
              type="button"
              onClick={() => setScopeLevel("user")}
              style={{
                padding: "0.75rem",
                borderRadius: "0.375rem",
                border: `1.5px solid ${scopeLevel === "user" ? "var(--primary-500)" : "var(--border)"}`,
                background: scopeLevel === "user" ? "var(--primary-50)" : "var(--bg-surface)",
                textAlign: "left",
                cursor: "pointer",
              }}
            >
              <div style={{ fontWeight: "var(--weight-semibold)", fontSize: "var(--text-sm)", color: "var(--text)" }}>Personal</div>
              <div style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)", marginTop: "0.25rem" }}>Only accessible by you</div>
            </button>
            <button
              type="button"
              disabled={!canManageOrg}
              onClick={() => setScopeLevel("organization")}
              style={{
                padding: "0.75rem",
                borderRadius: "0.375rem",
                border: `1.5px solid ${scopeLevel === "organization" ? "var(--primary-500)" : "var(--border)"}`,
                background: scopeLevel === "organization" ? "var(--primary-50)" : "var(--bg-surface)",
                opacity: canManageOrg ? 1 : 0.5,
                textAlign: "left",
                cursor: canManageOrg ? "pointer" : "not-allowed",
              }}
              title={!canManageOrg ? "Requires Administrator privileges" : undefined}
            >
              <div style={{ fontWeight: "var(--weight-semibold)", fontSize: "var(--text-sm)", color: "var(--text)" }}>Organization</div>
              <div style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)", marginTop: "0.25rem" }}>
                {canManageOrg ? "Shared with workspace" : "Requires Admin"}
              </div>
            </button>
          </div>
        </div>

        {/* OAuth Flow */}
        {isOAuth ? (
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            <div style={{
              padding: "0.875rem",
              background: "var(--bg-sunken)",
              borderRadius: "0.375rem",
              fontSize: "var(--text-sm)",
              color: "var(--text-secondary)",
              lineHeight: 1.5,
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.5rem", fontWeight: "var(--weight-semibold)", color: "var(--text)" }}>
                <ShieldCheckIcon size={16} /> Secure Authentication
              </div>
              Authorizing will securely redirect you to {provider.name}. Credentials are encrypted at rest using AES-128-CBC and rotated automatically.
            </div>

            <Button
              type="button"
              variant="primary"
              onClick={handleOAuthConnect}
              disabled={saving}
              style={{ width: "100%", padding: "0.75rem", fontSize: "var(--text-base)" }}
            >
              {saving ? "Redirecting..." : `Authorize with ${provider.name}`}
            </Button>
          </div>
        ) : (
          /* Form Credentials Flow */
          <form onSubmit={handleSave} style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            <div>
              <label style={{ display: "block", fontSize: "var(--text-xs)", fontWeight: "var(--weight-semibold)", marginBottom: "0.375rem" }}>
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
                  border: "1px solid var(--border)",
                  background: "var(--bg-surface)",
                  color: "var(--text)",
                  fontSize: "var(--text-sm)",
                }}
              />
            </div>

            {/* Dynamic fields from configuration_schema */}
            {Object.entries(schema).map(([key, prop]: [string, any]) => {
              const isRequired = requiredFields.includes(key);
              const isPassword = prop.format === "password";
              const isBoolean = prop.type === "boolean";
              const isEnum = Array.isArray(prop.enum);

              if (isBoolean) {
                return (
                  <div key={key} style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                    <input
                      type="checkbox"
                      id={`field-${key}`}
                      checked={formData[key] ?? prop.default ?? false}
                      onChange={(e) => setFormData({ ...formData, [key]: e.target.checked })}
                    />
                    <label htmlFor={`field-${key}`} style={{ fontSize: "var(--text-sm)", fontWeight: "var(--weight-medium)", cursor: "pointer" }}>
                      {prop.title || key}
                    </label>
                  </div>
                );
              }

              if (isEnum) {
                return (
                  <div key={key}>
                    <label style={{ display: "block", fontSize: "var(--text-xs)", fontWeight: "var(--weight-semibold)", marginBottom: "0.375rem" }}>
                      {prop.title || key} {isRequired && <span style={{ color: "var(--error-500)" }}>*</span>}
                    </label>
                    <select
                      value={formData[key] ?? prop.default ?? prop.enum[0]}
                      onChange={(e) => setFormData({ ...formData, [key]: e.target.value })}
                      style={{
                        width: "100%",
                        padding: "0.5rem 0.75rem",
                        borderRadius: "0.375rem",
                        border: "1px solid var(--border)",
                        background: "var(--bg-surface)",
                        color: "var(--text)",
                        fontSize: "var(--text-sm)",
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
                  <label style={{ display: "block", fontSize: "var(--text-xs)", fontWeight: "var(--weight-semibold)", marginBottom: "0.375rem" }}>
                    {prop.title || key} {isRequired && <span style={{ color: "var(--error-500)" }}>*</span>}
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
                      border: "1px solid var(--border)",
                      background: "var(--bg-surface)",
                      color: "var(--text)",
                      fontSize: "var(--text-sm)",
                    }}
                  />
                  {prop.description && (
                    <span style={{ display: "block", fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>
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
              <Button
                type="button"
                variant="secondary"
                onClick={handleTest}
                disabled={testing || saving}
              >
                {testing ? "Testing..." : "Test Connection"}
              </Button>
              <Button
                type="submit"
                variant="primary"
                disabled={saving || testing}
              >
                {saving ? "Saving..." : "Save Connection"}
              </Button>
            </div>
          </form>
        )}
      </div>
    </Modal>
  );
}
