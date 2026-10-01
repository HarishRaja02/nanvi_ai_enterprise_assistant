import { useState, type FormEvent } from "react";
import { Eye, EyeOff, LoaderCircle } from "lucide-react";
import type { LocalAccountRole } from "../../api";

const ROLES: LocalAccountRole[] = ["Superior", "Supervisor", "Project Engineer", "Employee"];

type Props = {
  onLogin: (username: string, password: string, role: LocalAccountRole) => Promise<void> | void;
  loading: boolean;
  error: string;
};

export function RoleLoginForm({ onLogin, loading, error }: Props) {
  const [role, setRole] = useState<LocalAccountRole>("Superior");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [validationError, setValidationError] = useState("");

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setValidationError("");
    if (!username.trim() || !password) {
      setValidationError("Enter your User ID and password.");
      return;
    }
    await onLogin(username.trim(), password, role);
  };

  return (
    <form className="role-login-form" onSubmit={(event) => void submit(event)} noValidate>
      <h1>Sign in to Nanvi</h1>
      <p className="role-login-subtitle">Choose your role and enter your account credentials.</p>

      {(validationError || error) && <p className="role-login-error" role="alert">{validationError || error}</p>}

      <label className="role-login-field">
        <span>Role</span>
        <select value={role} onChange={(event) => setRole(event.target.value as LocalAccountRole)} disabled={loading}>
          {ROLES.map((item) => <option key={item} value={item}>{item}</option>)}
        </select>
      </label>

      <label className="role-login-field">
        <span>User ID</span>
        <input
          type="text"
          autoComplete="username"
          value={username}
          onChange={(event) => setUsername(event.target.value)}
          disabled={loading}
          required
        />
      </label>

      <label className="role-login-field">
        <span>Password</span>
        <span className="role-login-password-wrap">
          <input
            type={showPassword ? "text" : "password"}
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            disabled={loading}
            required
          />
          <button
            className="role-login-password-toggle"
            type="button"
            aria-label={showPassword ? "Hide password" : "Show password"}
            aria-pressed={showPassword}
            onClick={() => setShowPassword((visible) => !visible)}
          >
            {showPassword ? <EyeOff size={18} aria-hidden="true" /> : <Eye size={18} aria-hidden="true" />}
          </button>
        </span>
      </label>

      <button className="role-login-submit" type="submit" disabled={loading}>
        {loading ? <><LoaderCircle size={18} className="role-login-spinner" aria-hidden="true" /> Signing in…</> : "Sign in"}
      </button>
    </form>
  );
}
