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
}

export function EnterpriseLoginGateway({
  error = "",
  onLogin,
  loading = false,
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

  return (
    <main className="role-login-page">
      <aside className="role-login-visual" aria-hidden="true">
        <video className="role-login-video" autoPlay muted loop playsInline preload="auto" tabIndex={-1}>
          <source src="/assets/login-network-loop.mp4" type="video/mp4" />
        </video>
        <div className="role-login-overlay" />
      </aside>
      <section className="role-login-content" aria-label="Nanvi sign in">
        <div className="role-login-panel">
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
