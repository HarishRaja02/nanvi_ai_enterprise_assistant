import { useState, useRef, useEffect, type FormEvent } from "react";
import { ChevronDown, Crown, Eye, EyeOff, LoaderCircle, ShieldCheck } from "lucide-react";
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
  onNavigateToForgot?: () => void;
  onNavigateToRegister?: () => void;
};

export function RoleLoginForm({ onLogin, loading, error, onNavigateToForgot, onNavigateToRegister }: Props) {
  const [role, setRole] = useState<LocalAccountRole>("Superior");
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [validationError, setValidationError] = useState("");

  const selectedRoleObj = ROLES.find((r) => r.id === role);

  useEffect(() => {
    if (!isDropdownOpen) return;
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsDropdownOpen(false);
      }
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setIsDropdownOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isDropdownOpen]);

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

      {onNavigateToForgot && (
        <div style={{ display: "flex", justifyContent: "flex-end", marginTop: "-8px", marginBottom: "4px" }}>
          <button
            id="forgot-password-link"
            type="button"
            onClick={onNavigateToForgot}
            style={{
              background: "none",
              border: "none",
              padding: 0,
              fontSize: "13px",
              fontWeight: 500,
              color: "#4f46e5",
              cursor: "pointer",
              textDecoration: "underline",
            }}
          >
            Forgot Password?
          </button>
        </div>
      )}

      {/* Role Selection Dropdown Field */}
      <div className="role-login-field" ref={dropdownRef} style={{ position: "relative" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
          <span id="role-select-label" style={{ fontSize: "14px", fontWeight: 500, color: "#374151" }}>
            Account Role
          </span>
          <span style={{ fontSize: "12px", color: "#64748b" }}>
            {isDropdownOpen ? "Select a role below" : "Click to switch role"}
          </span>
        </div>

        {/* Dropdown Toggle Button */}
        <button
          id="role-dropdown-btn"
          type="button"
          aria-haspopup="listbox"
          aria-expanded={isDropdownOpen}
          aria-controls="role-dropdown-panel"
          className={`role-dropdown-trigger ${isDropdownOpen ? "open" : ""}`}
          onClick={() => setIsDropdownOpen((prev) => !prev)}
          disabled={loading}
          style={{
            width: "100%",
            minHeight: "46px",
            padding: "9px 14px",
            borderRadius: "8px",
            border: isDropdownOpen ? "1.5px solid #006583" : "1.5px solid #cbd2dc",
            background: "#ffffff",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            cursor: "pointer",
            transition: "all 140ms ease-in-out",
            boxShadow: isDropdownOpen ? "0 0 0 3px rgba(0, 101, 131, 0.12)" : "0 1px 2px rgba(0,0,0,0.04)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "8px", color: "#1e293b", fontWeight: 500, fontSize: "14px" }}>
            {role === "Admin" && <ShieldCheck size={18} style={{ color: "#4338ca" }} />}
            {role === "Superior" && <Crown size={16} style={{ color: "#16a34a" }} />}
            <span>{selectedRoleObj?.label || role}</span>
            {selectedRoleObj?.badge && (
              <span
                style={{
                  fontSize: "10px",
                  padding: "2px 7px",
                  borderRadius: "9999px",
                  background: role === "Admin" ? "#ede9fe" : role === "Superior" ? "#dcfce7" : "#f1f5f9",
                  color: role === "Admin" ? "#4338ca" : role === "Superior" ? "#166534" : "#475569",
                  fontWeight: 700,
                  textTransform: "uppercase",
                  letterSpacing: "0.04em",
                }}
              >
                {selectedRoleObj.badge}
              </span>
            )}
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "6px", color: "#64748b" }}>
            <span style={{ fontSize: "12px", color: "#64748b" }}>{isDropdownOpen ? "Close" : "Change"}</span>
            <ChevronDown
              size={18}
              style={{
                transform: isDropdownOpen ? "rotate(180deg)" : "rotate(0deg)",
                transition: "transform 180ms ease-in-out",
              }}
            />
          </div>
        </button>

        {/* Roles List - Displayed ONLY when dropdown button is clicked */}
        {isDropdownOpen && (
          <div
            id="role-dropdown-panel"
            className="role-dropdown-menu"
            style={{
              marginTop: "8px",
              background: "#ffffff",
              border: "1px solid #e2e8f0",
              borderRadius: "8px",
              padding: "10px",
              boxShadow: "0 10px 25px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.05)",
              display: "flex",
              flexDirection: "column",
              gap: "8px",
              animation: "role-dropdown-slide 150ms ease-out",
            }}
          >
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
                    onClick={() => {
                      handleSelectRole(item.id);
                      setIsDropdownOpen(false);
                    }}
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
          </div>
        )}

        {/* Selected Role Context Notice */}
        <div
          style={{
            fontSize: "12px",
            color: role === "Admin" ? "#4338ca" : role === "Superior" ? "#166534" : "#4b5563",
            background: role === "Admin" ? "#f5f3ff" : role === "Superior" ? "#f0fdf4" : "#f9fafb",
            border: `1px solid ${
              role === "Admin" ? "#c7d2fe" : role === "Superior" ? "#bbf7d0" : "#e5e7eb"
            }`,
            borderRadius: "6px",
            padding: "6px 10px",
            marginTop: "6px",
            display: "flex",
            alignItems: "center",
            gap: "8px",
          }}
        >
          {role === "Admin" ? (
            <>
              <ShieldCheck size={15} style={{ flexShrink: 0, color: "#6366f1" }} />
              <span>
                <strong>Admin Mode:</strong> Break-glass developer credentials (<code>admin / admin@company</code>).
              </span>
            </>
          ) : role === "Superior" ? (
            <>
              <Crown size={15} style={{ flexShrink: 0, color: "#16a34a" }} />
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

      {onNavigateToRegister && (
        <div style={{ textAlign: "center", marginTop: "12px", fontSize: "13px", color: "#64748b" }}>
          Need an account?{" "}
          <button
            id="register-link"
            type="button"
            onClick={onNavigateToRegister}
            style={{
              background: "none",
              border: "none",
              padding: 0,
              fontSize: "13px",
              fontWeight: 600,
              color: "#0f172a",
              cursor: "pointer",
              textDecoration: "underline",
            }}
          >
            Create Account
          </button>
        </div>
      )}
    </form>
  );
}
