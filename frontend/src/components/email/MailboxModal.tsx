import { useState, useEffect } from "react";
import { Mail, CheckCircle2, RefreshCw, Unplug, ExternalLink, Sparkles, ShieldCheck } from "lucide-react";
import { Modal } from "../ui/Modal";
import { Button } from "../ui/Button";
import { Alert } from "../ui/Alert";
import { Badge } from "../ui/Badge";
import { GoogleIcon } from "../../login/components/GoogleIcon";
import type { NanviApiClient, EmailStatusResponse } from "../../api";
import { useToast } from "../ui/Toast";

type Props = {
  api: NanviApiClient;
  open: boolean;
  onClose: () => void;
  onAskPrompt?: (prompt: string) => void;
};

export function MailboxModal({ api, open, onClose, onAskPrompt }: Props) {
  const notify = useToast();
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState<EmailStatusResponse | null>(null);
  const [connecting, setConnecting] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);
  const [showManual, setShowManual] = useState(false);
  const [manualEmail, setManualEmail] = useState("");
  const [manualName, setManualName] = useState("");

  const loadStatus = async () => {
    try {
      setLoading(true);
      const res = await api.emailStatus();
      setStatus(res);
    } catch (err) {
      console.warn("Could not load email status:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open) {
      loadStatus();
    }
  }, [open]);

  if (!open) return null;

  const handleConnectGoogle = async () => {
    try {
      setConnecting(true);
      const { auth_url } = await api.googleAuthUrl();
      window.location.href = auth_url;
    } catch {
      notify("Failed to initiate Google authorization. Please check backend configuration.", "error");
      setConnecting(false);
    }
  };

  const handleDisconnect = async () => {
    if (!window.confirm("Are you sure you want to disconnect this mailbox? Nanvi will no longer be able to search your live emails.")) {
      return;
    }
    try {
      setDisconnecting(true);
      await api.disconnectEmail();
      notify("Mailbox disconnected successfully.", "success");
      await loadStatus();
    } catch {
      notify("Failed to disconnect mailbox.", "error");
    } finally {
      setDisconnecting(false);
    }
  };

  const handleManualConnect = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!manualEmail.trim()) {
      notify("Please enter a valid email address.", "error");
      return;
    }
    try {
      setConnecting(true);
      const res = await api.manualConnectEmail(manualEmail.trim(), manualName.trim() || undefined);
      notify(`Connected mailbox: ${res.account.email_address}`, "success");
      setShowManual(false);
      await loadStatus();
    } catch {
      notify("Failed to link mailbox.", "error");
    } finally {
      setConnecting(false);
    }
  };

  const handleQuickAsk = (prompt: string) => {
    onClose();
    onAskPrompt?.(prompt);
  };

  const isConnected = Boolean(status?.connected && status?.account);

  return (
    <Modal
      title="Enterprise Mailbox Connector"
      onClose={onClose}
      footer={
        <Button variant="ghost" size="sm" onClick={onClose}>
          Close
        </Button>
      }
    >
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
        {loading ? (
          <div style={{ padding: "var(--space-8) 0", textAlign: "center", color: "var(--text-secondary)" }}>
            <RefreshCw size={24} className="animate-spin" style={{ color: "var(--primary-600)", margin: "0 auto var(--space-2)" }} />
            <p style={{ margin: 0, fontSize: "var(--text-sm)" }}>Connecting to mailbox service…</p>
          </div>
        ) : isConnected && status?.account ? (
          /* Active Connected State */
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
            <div
              style={{
                padding: "var(--space-4)",
                backgroundColor: "var(--success-bg)",
                border: "1px solid var(--success-border)",
                borderRadius: "var(--radius-lg)",
                display: "flex",
                alignItems: "flex-start",
                gap: "var(--space-3)",
              }}
            >
              <div
                style={{
                  padding: "var(--space-2)",
                  backgroundColor: "var(--bg-surface)",
                  borderRadius: "var(--radius-md)",
                  color: "var(--success-fg)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <CheckCircle2 size={20} />
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)", flexWrap: "wrap" }}>
                  <span style={{ fontWeight: "var(--weight-semibold)", color: "var(--text)", fontSize: "var(--text-base)" }}>
                    Active Google Mailbox Connected
                  </span>
                  <Badge tone="success">Live Sync</Badge>
                </div>
                <p style={{ margin: "4px 0 0 0", color: "var(--text-secondary)", fontSize: "var(--text-xs)" }}>
                  Enterprise AI queries now search this user's live mailbox in real time.
                </p>
              </div>
            </div>

            {/* Account Card */}
            <div
              style={{
                padding: "var(--space-4)",
                border: "1px solid var(--border)",
                borderRadius: "var(--radius-lg)",
                backgroundColor: "var(--bg-sunken)",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "var(--space-3)" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)" }}>
                  <div
                    style={{
                      width: 40,
                      height: 40,
                      borderRadius: "var(--radius-full)",
                      backgroundColor: "var(--bg-surface)",
                      border: "1px solid var(--border)",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                    }}
                  >
                    <GoogleIcon className="w-5 h-5" />
                  </div>
                  <div>
                    <div style={{ fontWeight: "var(--weight-semibold)", color: "var(--text)", fontSize: "var(--text-base)" }}>
                      {status.account.display_name || "Google Workspace Account"}
                    </div>
                    <div style={{ fontSize: "var(--text-xs)", color: "var(--text-secondary)", fontFamily: "var(--font-mono)" }}>
                      {status.account.email_address}
                    </div>
                  </div>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  icon={Unplug}
                  loading={disconnecting}
                  onClick={handleDisconnect}
                  className="btn-danger"
                >
                  Disconnect
                </Button>
              </div>

              {status.account.connected_at && (
                <div
                  style={{
                    marginTop: "var(--space-3)",
                    paddingTop: "var(--space-3)",
                    borderTop: "1px solid var(--border)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    fontSize: "var(--text-xs)",
                    color: "var(--text-muted)",
                  }}
                >
                  <span>Connected: {new Date(status.account.connected_at).toLocaleDateString()}</span>
                  <a
                    href="https://mail.google.com"
                    target="_blank"
                    rel="noreferrer"
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "4px",
                      color: "var(--primary-600)",
                      fontWeight: "var(--weight-medium)",
                      textDecoration: "none",
                    }}
                  >
                    Open Gmail <ExternalLink size={12} />
                  </a>
                </div>
              )}
            </div>

            {/* Quick Test Actions */}
            <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)", paddingTop: "var(--space-1)" }}>
              <span style={{ fontSize: "var(--text-xs)", fontWeight: "var(--weight-semibold)", textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-muted)" }}>
                Try asking Nanvi about your inbox
              </span>
              <div style={{ display: "grid", gap: "var(--space-2)" }}>
                {[
                  "Check my latest unread emails",
                  "What emails did I receive today?",
                  "Find emails about Q1 financial results",
                ].map((q, idx) => (
                  <button
                    key={idx}
                    type="button"
                    onClick={() => handleQuickAsk(q)}
                    className="btn btn-secondary"
                    style={{
                      justifyContent: "space-between",
                      fontSize: "var(--text-xs)",
                      padding: "var(--space-2) var(--space-3)",
                      textAlign: "left",
                      height: "auto",
                      minHeight: "36px",
                      cursor: "pointer",
                    }}
                  >
                    <span style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
                      <Sparkles size={14} style={{ color: "var(--primary-600)" }} />
                      {q}
                    </span>
                    <span style={{ color: "var(--primary-600)", fontWeight: "var(--weight-medium)" }}>
                      Ask →
                    </span>
                  </button>
                ))}
              </div>
            </div>
          </div>
        ) : (
          /* Disconnected State */
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
            <div style={{ textAlign: "center", padding: "var(--space-2) 0" }}>
              <div
                style={{
                  width: 48,
                  height: 48,
                  borderRadius: "var(--radius-lg)",
                  backgroundColor: "var(--primary-50)",
                  border: "1px solid var(--border)",
                  color: "var(--primary-600)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  margin: "0 auto var(--space-3)",
                }}
              >
                <Mail size={24} />
              </div>
              <h3 style={{ margin: 0, fontSize: "var(--text-lg)", fontWeight: "var(--weight-semibold)", color: "var(--text)" }}>
                Connect your Universal Mailbox
              </h3>
              <p style={{ margin: "6px 0 0 0", fontSize: "var(--text-xs)", color: "var(--text-secondary)", lineHeight: "var(--leading-ui)" }}>
                Link any Google Gmail or Google Workspace account to enable AI email search, thread summarization, and executive briefs.
              </p>
            </div>

            {/* Google OAuth Connect Box */}
            <div
              style={{
                padding: "var(--space-4)",
                backgroundColor: "var(--bg-sunken)",
                border: "1px solid var(--border)",
                borderRadius: "var(--radius-lg)",
                display: "flex",
                flexDirection: "column",
                gap: "var(--space-3)",
              }}
            >
              <button
                type="button"
                onClick={handleConnectGoogle}
                disabled={connecting}
                className="btn btn-secondary btn-block"
                style={{
                  minHeight: "44px",
                  fontSize: "var(--text-base)",
                  fontWeight: "var(--weight-semibold)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: "var(--space-3)",
                  backgroundColor: "var(--bg-surface)",
                  color: "var(--text)",
                  borderColor: "var(--border)",
                  boxShadow: "var(--shadow-card)",
                  cursor: "pointer",
                }}
              >
                {connecting ? (
                  <RefreshCw size={18} className="animate-spin" style={{ color: "var(--primary-600)" }} />
                ) : (
                  <GoogleIcon className="w-5 h-5" />
                )}
                <span>Connect with Google / Gmail</span>
              </button>

              <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)", fontSize: "var(--text-xs)", color: "var(--text-secondary)" }}>
                <ShieldCheck size={16} style={{ color: "var(--success-fg)", flexShrink: 0 }} />
                <span>
                  Read-only permissions (<code>gmail.readonly</code>). Nanvi will never send or delete emails.
                </span>
              </div>
            </div>

            {/* Enterprise Fallback Notice if system token exists */}
            {status?.has_enterprise_fallback && (
              <Alert tone="warning" title="Demo Mode Active">
                A shared system inbox is configured as fallback. Connect your personal Google account above to query your own live inbox.
              </Alert>
            )}

            {/* Manual Email Input Option */}
            <div style={{ paddingTop: "var(--space-1)" }}>
              <button
                type="button"
                onClick={() => setShowManual((p) => !p)}
                style={{
                  background: "none",
                  border: "none",
                  padding: 0,
                  color: "var(--primary-600)",
                  fontSize: "var(--text-xs)",
                  textDecoration: "underline",
                  cursor: "pointer",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "var(--space-1)",
                }}
              >
                {showManual ? "Hide manual email configuration" : "Or link a corporate email address directly →"}
              </button>

              {showManual && (
                <form
                  onSubmit={handleManualConnect}
                  style={{
                    marginTop: "var(--space-3)",
                    padding: "var(--space-4)",
                    border: "1px solid var(--border)",
                    borderRadius: "var(--radius-lg)",
                    backgroundColor: "var(--bg-surface)",
                    display: "flex",
                    flexDirection: "column",
                    gap: "var(--space-3)",
                  }}
                >
                  <div className="field">
                    <label className="field-label" htmlFor="manual-email">
                      Email Address
                    </label>
                    <input
                      id="manual-email"
                      type="email"
                      value={manualEmail}
                      onChange={(e) => setManualEmail(e.target.value)}
                      placeholder="e.g. arjun.mehta@nanvi.com or user@gmail.com"
                      className="input"
                      style={{ fontSize: "var(--text-sm)" }}
                    />
                  </div>
                  <div className="field">
                    <label className="field-label" htmlFor="manual-name">
                      Display Name (Optional)
                    </label>
                    <input
                      id="manual-name"
                      type="text"
                      value={manualName}
                      onChange={(e) => setManualName(e.target.value)}
                      placeholder="e.g. Arjun Mehta (CEO)"
                      className="input"
                      style={{ fontSize: "var(--text-sm)" }}
                    />
                  </div>
                  <Button type="submit" variant="primary" size="sm" loading={connecting} block>
                    Save & Activate Mailbox
                  </Button>
                </form>
              )}
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
}

