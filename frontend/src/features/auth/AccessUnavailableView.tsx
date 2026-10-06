import { LOGO_URL } from "../../lib/config";

interface AccessUnavailableProps {
  onSignOut: () => void;
}

export function AccessUnavailableView({ onSignOut }: AccessUnavailableProps) {
  return (
    <main className="fullscreen">
      <section className="splash" role="alert" style={{ maxWidth: 440, textAlign: "center" }}>
        <img src={LOGO_URL} alt="Nanvi" className="brand-logo-img splash-logo" style={{ marginBottom: 16 }} />
        <div
          style={{
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            width: 48,
            height: 48,
            borderRadius: "50%",
            background: "rgba(239, 68, 68, 0.15)",
            color: "#ef4444",
            margin: "0 auto 16px auto",
          }}
          aria-hidden="true"
        >
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
            <path d="M7 11V7a5 5 0 0 1 10 0v4" />
          </svg>
        </div>
        <h1 style={{ fontSize: "1.35rem", fontWeight: 600, margin: "0 0 8px 0" }}>Access unavailable</h1>
        <p style={{ color: "var(--color-text-secondary, #94a3b8)", margin: "0 0 24px 0", lineHeight: 1.5 }}>
          Your organization&apos;s Nanvi access is currently unavailable. Please contact your administrator.
        </p>
        <button
          type="button"
          onClick={onSignOut}
          className="btn btn-secondary"
          style={{ minWidth: 120, padding: "8px 16px", cursor: "pointer" }}
        >
          Sign out
        </button>
      </section>
    </main>
  );
}
