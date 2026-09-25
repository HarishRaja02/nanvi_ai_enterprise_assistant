import { FormEvent, useEffect, useRef, useState } from "react";
import { BookOpen, Eye, EyeOff, FileText, KeyRound, ShieldCheck } from "lucide-react";
import { Alert } from "../../components/ui/Alert";
import { Button, IconButton } from "../../components/ui/Button";
import { Field } from "../../components/ui/Field";
import { DEMO_MODE, SSO_LOGIN_URL, LOGO_URL } from "../../lib/config";
import { DEMO_ACCOUNTS } from "../../lib/demoAccounts";
import { initials } from "../../lib/format";

type Props = {
  error: string;
  loggedOut: boolean;
  signingIn: boolean;
  onDemoSignIn: (username: string, password: string) => Promise<void>;
  /** Provided when a stored session could not be verified, e.g. the backend was unreachable. */
  onRetry?: () => void;
};

const POINTS = [
  { icon: ShieldCheck, title: "Role-based access", text: "You only see information your role is allowed to access." },
  { icon: BookOpen, title: "Answers with sources", text: "Every answer shows the documents, emails or data behind it." },
  { icon: FileText, title: "Reports on request", text: "Ask for a report and download it securely." },
];

export function LoginScreen({ error, loggedOut, signingIn, onDemoSignIn, onRetry }: Props) {
  return (
    <div className="login">
      <aside className="login-brand on-ink">
        <div className="brand">
          <img src={LOGO_URL} alt="Nanvi Logo" className="brand-logo-img" />
          <span className="brand-text">
            <small>Enterprise assistant</small>
          </span>
        </div>
        <div className="login-brand-body">
          <p className="login-lead">Ask questions across your company's documents, email and data, and check where every answer came from.</p>
          <ul className="login-points">
            {POINTS.map(({ icon: Icon, title, text }) => (
              <li key={title}>
                <Icon size={18} aria-hidden="true" />
                <span><strong>{title}</strong>{text}</span>
              </li>
            ))}
          </ul>
        </div>
        <p className="login-legal">Sign-in is verified by the server, and access is enforced on every request.</p>
      </aside>

      <main className="login-panel">
        <div className="login-card">
          <h1>Sign in to Nanvi</h1>

          {loggedOut && !error && <Alert tone="success">You've been signed out.</Alert>}
          {error && (
            <Alert
              tone="danger"
              title="Couldn't sign you in"
              actions={onRetry ? <Button size="sm" variant="secondary" onClick={onRetry}>Try again</Button> : undefined}
            >
              {error}
            </Alert>
          )}

          {DEMO_MODE && <DemoSignIn signingIn={signingIn} onSignIn={onDemoSignIn} />}
          {!DEMO_MODE && <SsoSignIn />}
        </div>
      </main>
    </div>
  );
}

function SsoSignIn() {
  if (!SSO_LOGIN_URL) {
    return (
      <Alert tone="info" title="Single sign-on isn't set up">
        This deployment has no company sign-in configured. Contact your administrator.
      </Alert>
    );
  }
  return (
    <>
      <p className="login-sub">Use your company account to continue.</p>
      <Button variant="primary" size="lg" block icon={KeyRound} onClick={() => window.location.assign(SSO_LOGIN_URL!)}>
        Sign in with company SSO
      </Button>
    </>
  );
}

function DemoSignIn({ signingIn, onSignIn }: { signingIn: boolean; onSignIn: (u: string, p: string) => Promise<void> }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [reveal, setReveal] = useState(false);
  const [errors, setErrors] = useState<{ username?: string; password?: string }>({});
  const [pendingUser, setPendingUser] = useState<string | null>(null);
  const usernameRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);

  useEffect(() => { usernameRef.current?.focus(); }, []);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (signingIn) return;
    const next = {
      username: username.trim() ? undefined : "Enter your username.",
      password: password ? undefined : "Enter your password.",
    };
    setErrors(next);
    if (next.username) return usernameRef.current?.focus();
    if (next.password) return passwordRef.current?.focus();
    setPendingUser(null);
    await onSignIn(username, password);
  };

  const quick = async (account: (typeof DEMO_ACCOUNTS)[number]) => {
    setErrors({});
    setPendingUser(account.username);
    await onSignIn(account.username, account.password);
    setPendingUser(null);
  };

  return (
    <>
      <Alert tone="warning" title="Demo mode">
        Development sign-in is enabled. Turn it off (VITE_DEMO_MODE=false) for production.
      </Alert>

      <form className="login-form" onSubmit={(e) => void submit(e)} noValidate>
        <Field
          ref={usernameRef}
          label="Username"
          required
          value={username}
          autoComplete="username"
          disabled={signingIn}
          error={errors.username}
          onChange={(e) => setUsername(e.target.value)}
        />
        <Field
          ref={passwordRef}
          label="Password"
          required
          type={reveal ? "text" : "password"}
          value={password}
          autoComplete="current-password"
          disabled={signingIn}
          error={errors.password}
          onChange={(e) => setPassword(e.target.value)}
          adornment={
            <IconButton
              icon={reveal ? EyeOff : Eye}
              label={reveal ? "Hide password" : "Show password"}
              aria-pressed={reveal}
              size="sm"
              onClick={() => setReveal((r) => !r)}
            />
          }
        />
        <Button type="submit" variant="primary" size="lg" block loading={signingIn && pendingUser === null}>
          {signingIn && pendingUser === null ? "Signing in…" : "Sign in"}
        </Button>
      </form>

      <div className="login-divider"><span>Or choose a demo account</span></div>

      <ul className="accounts" aria-label="Demo accounts">
        {DEMO_ACCOUNTS.map((a) => (
          <li key={a.username}>
            <button type="button" className="account" disabled={signingIn} onClick={() => void quick(a)} aria-label={`Sign in as ${a.name}, ${a.role}`}>
              <span className="avatar" aria-hidden="true">{initials(a.name)}</span>
              <span className="account-copy">
                <span className="account-name truncate">{a.name}</span>
                <span className="account-role truncate">{a.role === a.department ? a.role : `${a.role}, ${a.department}`}</span>
              </span>
              {pendingUser === a.username && <span className="spinner" aria-hidden="true" />}
            </button>
          </li>
        ))}
      </ul>
    </>
  );
}
