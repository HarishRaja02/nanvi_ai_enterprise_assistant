import { useState, useEffect } from "react";
import type { LocalAccountRole } from "../api";
import { LOGO_URL } from "../lib/config";
import { RoleLoginForm } from "./components/RoleLoginForm";
import { ForgotPasswordView } from "./components/ForgotPasswordView";
import { ResetPasswordView } from "./components/ResetPasswordView";
import { RegisterForm } from "./components/RegisterForm";

export type AuthGatewayView = "login" | "forgot" | "reset" | "register";

export interface LoginGatewayProps {
  error?: string;
  onLogin: (username: string, password: string, role: LocalAccountRole | string) => Promise<void> | void;
  loading?: boolean;
  onBackToLanding?: () => void;
}

export function EnterpriseLoginGateway({
  error = "",
  onLogin,
  loading = false,
  onBackToLanding,
}: LoginGatewayProps) {
  const [view, setView] = useState<AuthGatewayView>("login");
  const [resetToken, setResetToken] = useState<string>("");

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const token = params.get("token");
    if (token) {
      setResetToken(token);
      setView("reset");
    }
  }, []);

  const handleBackToSignIn = () => {
    if (window.location.search.includes("token")) {
      window.history.replaceState({}, "", window.location.pathname);
    }
    setView("login");
  };

  const isDesktop = typeof window !== "undefined" && (
    window.location.protocol === "file:" ||
    Boolean((window as any).electronAPI?.isDesktop)
  );
  const loginVideoSrc = isDesktop ? "./assets/login-network-loop.mp4" : "/assets/login-network-loop.mp4";

  return (
    <main className="role-login-page">
      <aside className="role-login-visual" aria-hidden="true">
        <video className="role-login-video" autoPlay muted loop playsInline preload="auto" tabIndex={-1}>
          <source src={loginVideoSrc} type="video/mp4" />
        </video>
        <div className="role-login-overlay" />
      </aside>
      <section className="role-login-content" aria-label="Nanvi sign in">
        <div className="role-login-panel">
          {onBackToLanding && (
            <button
              type="button"
              onClick={onBackToLanding}
              style={{
                alignSelf: "flex-start",
                background: "none",
                border: "none",
                color: "#006583",
                fontSize: "13px",
                fontWeight: 600,
                cursor: "pointer",
                display: "inline-flex",
                alignItems: "center",
                gap: "6px",
                marginBottom: "12px",
                padding: "2px 0",
              }}
            >
              ← Back to Product Overview
            </button>
          )}

          <header className="role-login-brand">
            <img src={LOGO_URL} alt="Nanvi" />
            <span>Enterprise assistant</span>
          </header>

          {view === "login" && (
            <RoleLoginForm
              onLogin={onLogin}
              loading={loading}
              error={error}
              onNavigateToForgot={() => setView("forgot")}
              onNavigateToRegister={() => setView("register")}
            />
          )}

          {view === "forgot" && (
            <ForgotPasswordView
              onBackToSignIn={handleBackToSignIn}
              onOpenResetLink={(token) => {
                setResetToken(token);
                setView("reset");
              }}
            />
          )}

          {view === "reset" && (
            <ResetPasswordView
              token={resetToken}
              onBackToSignIn={handleBackToSignIn}
              onRequestNewLink={() => setView("forgot")}
            />
          )}

          {view === "register" && (
            <RegisterForm
              onNavigateToSignIn={handleBackToSignIn}
              onSuccess={() => setView("login")}
            />
          )}
        </div>
      </section>
    </main>
  );
}

export default EnterpriseLoginGateway;
