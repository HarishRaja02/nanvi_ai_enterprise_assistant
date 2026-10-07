import { useState, type FormEvent } from "react";
import { Crown, Eye, EyeOff, LoaderCircle, ShieldCheck } from "lucide-react";
import type { LocalAccountRole } from "../../api";

type RoleOption = {
  id: LocalAccountRole;
  label: string;
  badge?: string;
  description: string;
};

const ROLES: RoleOption[] = [
  {
    id: "Admin",
    label: "Admin Portal",
    badge: "Break-Glass",
    description: "System Developer & Platform Management [admin / admin@company]",
  },
  {
    id: "Superior",
    label: "Superior",
    badge: "Top-Level",
    description: "Executive Leadership & Top-Level Access (CEO / Director)",
  },
  {
    id: "Supervisor",
    label: "Supervisor",
    description: "Department Management & Operations",
  },
  {
    id: "Project Engineer",
    label: "Project Engineer",
    description: "Engineering & Technical Operations",
  },
  {
    id: "Employee",
    label: "Employee",
    description: "Standard Staff & General Workspace",
  },
];

type Props = {
  onLogin: (username: string, password: string, role: LocalAccountRole | string) => Promise<void> | void;
  loading: boolean;
  error: string;
};

export function RoleLoginForm({ onLogin, loading, error }: Props) {
  const [role, setRole] = useState<LocalAccountRole>("Superior");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [validationError, setValidationError] = useState("");

  const handleSelectRole = (newRole: LocalAccountRole) => {
    setRole(newRole);
    setValidationError("");

    if (newRole === "Admin") {
      // Shift credentials to break-glass admin
      setUsername("admin");
      setPassword("admin@company");
    } else {
      // If previous credentials were the admin default, clear so user can enter their own credentials
      if (username === "admin" && password === "admin@company") {
        setUsername("");
        setPassword("");
      }
    }
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setValidationError("");
    if (!username.trim() || !password) {
      setValidationError("Enter your Email ID / User ID and password.");
      return;
    }
    const cleanUser = username.trim();
    // If Admin role is selected or admin credentials entered, effective role is Admin / Superior
    let effectiveRole: string = role;
    if (
      role === "Admin" ||
      cleanUser.toLowerCase() === "admin" ||
      cleanUser.toLowerCase() === "admin@company" ||
      cleanUser.toLowerCase() === "admin@company.com"
    ) {
      effectiveRole = "Admin";
    }
    await onLogin(cleanUser, password, effectiveRole);
  };

  return (
    <form className="role-login-form" onSubmit={(event) => void submit(event)} noValidate>
      <h1>Sign in to Nanvi</h1>
      <p className="role-login-subtitle">Enter your Email ID or User ID and account credentials.</p>

      {(validationError || error) && (
        <p className="role-login-error" role="alert">
          {validationError || error}
        </p>
      )}

      <label className="role-login-field">
        <span>Email ID or User ID</span>
        <input
          type="text"
          autoComplete="username"
          placeholder={role === "Admin" ? "admin" : role === "Superior" ? "ceo@nanvi.local or username" : "e.g. user@company.com"}
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
            placeholder="••••••••••••"
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

      {/* Role Selection Group placed below password */}
      <div className="role-login-field">
        <span id="role-select-label">Account Role</span>
        <div className="role-login-role-group" role="group" aria-labelledby="role-select-label">
          {ROLES.map((item) => {
            const isSelected = role === item.id;
            const isSpecialAdmin = item.id === "Admin";
            const isSpecialSuperior = item.id === "Superior";
            const btnClass = `role-login-role-btn ${
              isSpecialAdmin ? "role-admin" : isSpecialSuperior ? "role-superior" : ""
            } ${isSelected ? "active" : ""}`;

            return (
              <button
                key={item.id}
                type="button"
                className={btnClass}
                aria-pressed={isSelected}
                onClick={() => handleSelectRole(item.id)}
                disabled={loading}
              >
                {isSpecialAdmin && <ShieldCheck size={18} />}
                {isSpecialSuperior && <Crown size={16} />}
                <span>{item.label}</span>
                {item.badge && (
                  <span
                    style={{
                      fontSize: "10px",
                      padding: "1px 6px",
                      borderRadius: "9999px",
                      background: isSelected ? "rgba(255,255,255,0.25)" : "rgba(0,0,0,0.08)",
                      fontWeight: 700,
                      textTransform: "uppercase",
                      letterSpacing: "0.04em",
                      marginLeft: "4px",
                    }}
                  >
                    {item.badge}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {/* Selected Role Context Notice */}
        <div
          style={{
            fontSize: "13px",
            color: role === "Admin" ? "#4338ca" : role === "Superior" ? "#166534" : "#4b5563",
            background: role === "Admin" ? "#f5f3ff" : role === "Superior" ? "#f0fdf4" : "#f9fafb",
            border: `1px solid ${
              role === "Admin" ? "#c7d2fe" : role === "Superior" ? "#bbf7d0" : "#e5e7eb"
            }`,
            borderRadius: "6px",
            padding: "8px 12px",
            marginTop: "6px",
            display: "flex",
            alignItems: "center",
            gap: "8px",
          }}
        >
          {role === "Admin" ? (
            <>
              <ShieldCheck size={16} style={{ flexShrink: 0, color: "#6366f1" }} />
              <span>
                <strong>Admin Mode:</strong> Break-glass developer credentials shifted into place (
                <code>admin / admin@company</code>).
              </span>
            </>
          ) : role === "Superior" ? (
            <>
              <Crown size={16} style={{ flexShrink: 0, color: "#16a34a" }} />
              <span>
                <strong>Superior User:</strong> Dedicated for top-level leadership (CEO, Directors, Executives).
              </span>
            </>
          ) : (
            <span>
              <strong>{role} Account:</strong> Enter your registered corporate credentials to sign in.
            </span>
          )}
        </div>
      </div>

      <button className="role-login-submit" type="submit" disabled={loading}>
        {loading ? (
          <>
            <LoaderCircle size={18} className="role-login-spinner" aria-hidden="true" />
            <span>Signing in…</span>
          </>
        ) : (
          <span>{role === "Admin" ? "Sign in to Admin Console" : "Sign in"}</span>
        )}
      </button>
    </form>
  );
}
