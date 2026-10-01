import type { LocalAccountRole } from "../api";
import { LOGO_URL } from "../lib/config";
import { RoleLoginForm } from "./components/RoleLoginForm";

export interface LoginGatewayProps {
  error?: string;
  onLogin: (username: string, password: string, role: LocalAccountRole) => Promise<void> | void;
  loading?: boolean;
}

export function EnterpriseLoginGateway({
  error = "",
  onLogin,
  loading = false,
}: LoginGatewayProps) {
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
          <RoleLoginForm onLogin={onLogin} loading={loading} error={error} />
        </div>
      </section>
    </main>
  );
}

export default EnterpriseLoginGateway;
