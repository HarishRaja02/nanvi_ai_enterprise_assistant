import { useState, type FormEvent } from "react";
import { AlertCircle, CheckCircle2, LifeBuoy, LoaderCircle, Send, X } from "lucide-react";
import type { NanviApiClient, UserIdentity } from "../../api";

interface Props {
  api: NanviApiClient;
  identity: UserIdentity | null;
  open: boolean;
  onClose: () => void;
  initialCategory?: string;
}

const CATEGORIES = [
  "Login & Authentication",
  "AI Chat & Responses",
  "Document & Knowledge Vault",
  "Database & Connections",
  "Speed & Performance",
  "Feature Request / Feedback",
  "Other",
];

const SEVERITIES = [
  { value: "Low", label: "Low (Minor issue / Question)" },
  { value: "Medium", label: "Medium (Feature not working as expected)" },
  { value: "High", label: "High (Workflow blocked)" },
  { value: "Critical", label: "Critical (System outage or access lost)" },
];

export function ReportIssueModal({ api, identity, open, onClose, initialCategory }: Props) {
  const [category, setCategory] = useState(initialCategory || "Login & Authentication");
  const [severity, setSeverity] = useState("Medium");
  const [subject, setSubject] = useState("");
  const [description, setDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [submittedTicketId, setSubmittedTicketId] = useState<string | null>(null);

  if (!open) return null;

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!subject.trim() || !description.trim()) {
      setError("Please provide both a subject and a description of the issue.");
      return;
    }
    setError("");
    setSubmitting(true);
    try {
      const diag = {
        browser: typeof navigator !== "undefined" ? navigator.userAgent : "unknown",
        platform: typeof navigator !== "undefined" ? navigator.platform : "unknown",
        current_url: typeof window !== "undefined" ? window.location.href : "",
        screen: typeof window !== "undefined" ? `${window.innerWidth}x${window.innerHeight}` : "",
        timestamp: new Date().toISOString(),
      };

      const ticket = await api.submitSupportTicket({
        category,
        severity,
        subject: subject.trim(),
        description: description.trim(),
        diagnostic_info: diag,
      });

      setSubmittedTicketId(ticket.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to submit report. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleResetAndClose = () => {
    setSubmittedTicketId(null);
    setSubject("");
    setDescription("");
    setError("");
    onClose();
  };

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="report-modal-title">
      <div className="modal" style={{ width: "min(100%, 620px)" }}>
        <header className="modal-header">
          <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)" }}>
            <div style={{
              width: "36px",
              height: "36px",
              borderRadius: "var(--radius-md)",
              background: "var(--danger-bg)",
              color: "var(--danger-fg)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              flexShrink: 0,
            }}>
              <LifeBuoy size={20} />
            </div>
            <div>
              <h2 id="report-modal-title" className="modal-title" style={{ fontSize: "var(--text-lg)" }}>
                Report Trouble & Request Support
              </h2>
              <p style={{ margin: 0, fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>
                Direct developer & admin ticketing for quick problem resolution
              </p>
            </div>
          </div>
          <button
            type="button"
            className="btn btn-ghost btn-icon"
            aria-label="Close dialog"
            onClick={handleResetAndClose}
            disabled={submitting}
          >
            <X size={18} />
          </button>
        </header>

        {submittedTicketId ? (
          <div style={{ padding: "var(--space-8) var(--space-6)", textAlign: "center" }}>
            <div style={{
              width: "56px",
              height: "56px",
              margin: "0 auto var(--space-4)",
              borderRadius: "var(--radius-full)",
              background: "var(--success-bg)",
              color: "var(--success-fg)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}>
              <CheckCircle2 size={32} />
            </div>
            <h3 style={{ margin: "0 0 var(--space-2)", fontSize: "var(--text-xl)", fontWeight: "var(--weight-semibold)", color: "var(--text)" }}>
              Report Received Successfully!
            </h3>
            <p style={{ margin: "0 0 var(--space-4)", fontSize: "var(--text-base)", color: "var(--text-secondary)" }}>
              Ticket Reference ID: <strong style={{ color: "var(--primary-600)", fontFamily: "var(--font-mono)" }}>{submittedTicketId}</strong>
            </p>
            <p style={{ margin: "0 auto var(--space-6)", fontSize: "var(--text-sm)", color: "var(--text-muted)", maxWidth: "440px", lineHeight: "var(--leading-ui)" }}>
              Our platform administration team has received your ticket. If this involves credentials, passwords, or database connectivity, our admins can view and resolve it directly from the Admin Dashboard.
            </p>
            <button
              type="button"
              className="btn btn-primary"
              onClick={handleResetAndClose}
              style={{ minWidth: "120px" }}
            >
              Done
            </button>
          </div>
        ) : (
          <form onSubmit={handleSubmit}>
            <div className="modal-body">
              {error && (
                <div className="alert alert-danger">
                  <AlertCircle size={16} />
                  <div className="alert-body">
                    <span>{error}</span>
                  </div>
                </div>
              )}

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-3)" }}>
                <div className="field">
                  <label className="field-label">Category</label>
                  <select
                    className="select"
                    value={category}
                    onChange={(e) => setCategory(e.target.value)}
                    disabled={submitting}
                  >
                    {CATEGORIES.map((c) => (
                      <option key={c} value={c}>
                        {c}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="field">
                  <label className="field-label">Severity Level</label>
                  <select
                    className="select"
                    value={severity}
                    onChange={(e) => setSeverity(e.target.value)}
                    disabled={submitting}
                  >
                    {SEVERITIES.map((s) => (
                      <option key={s.value} value={s.value}>
                        {s.label}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="field">
                <label className="field-label">
                  Summary / Subject <span style={{ color: "var(--danger-fg)" }}>*</span>
                </label>
                <input
                  type="text"
                  className="input"
                  placeholder="e.g. Trouble signing in with corporate email ID, or chat query error"
                  value={subject}
                  onChange={(e) => setSubject(e.target.value)}
                  disabled={submitting}
                  required
                />
              </div>

              <div className="field">
                <label className="field-label">
                  Describe what happened <span style={{ color: "var(--danger-fg)" }}>*</span>
                </label>
                <textarea
                  rows={4}
                  className="input"
                  style={{ height: "auto", minHeight: "90px", padding: "var(--space-3)" }}
                  placeholder="Please describe the steps you took, any error message you saw, and what you expected to happen..."
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  disabled={submitting}
                  required
                />
              </div>

              <div style={{
                background: "var(--bg-sunken)",
                border: "1px solid var(--border)",
                borderRadius: "var(--radius-md)",
                padding: "var(--space-3) var(--space-4)",
                fontSize: "var(--text-xs)",
                color: "var(--text-secondary)",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
              }}>
                <span>
                  Reporter: <strong>{identity?.name || identity?.email || "Current User"}</strong>
                </span>
                <span>
                  Storage: <strong>Isolated workspace</strong>
                </span>
              </div>
            </div>

            <footer className="modal-footer">
              <button
                type="button"
                className="btn btn-secondary"
                onClick={handleResetAndClose}
                disabled={submitting}
              >
                Cancel
              </button>
              <button
                type="submit"
                className="btn btn-primary"
                disabled={submitting}
              >
                {submitting ? (
                  <>
                    <LoaderCircle size={15} className="spin" />
                    <span>Submitting…</span>
                  </>
                ) : (
                  <>
                    <Send size={15} />
                    <span>Submit Ticket</span>
                  </>
                )}
              </button>
            </footer>
          </form>
        )}
      </div>
    </div>
  );
}
