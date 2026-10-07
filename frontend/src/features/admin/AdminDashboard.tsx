import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  Database,
  Eye,
  EyeOff,
  HardDrive,
  KeyRound,
  LifeBuoy,
  LoaderCircle,
  Lock,
  Plus,
  RefreshCw,
  Search,
  Server,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Trash2,
  UserCheck,
  UserPlus,
  Users,
  UserX,
  X,
} from "lucide-react";
import type {
  AdminOverview,
  DatabaseConfig,
  LocalAccount,
  LocalAccountRole,
  NanviApiClient,
  SupportTicket,
  UserIdentity,
} from "../../api";
import { useToast } from "../../components/ui/Toast";

interface Props {
  api: NanviApiClient;
  identity: UserIdentity | null;
  onNavigateHome?: () => void;
}

type Tab = "overview" | "accounts" | "tickets" | "database";

export function AdminDashboard({ api, identity, onNavigateHome }: Props) {
  const notify = useToast();
  const [activeTab, setActiveTab] = useState<Tab>("overview");
  const [loadingOverview, setLoadingOverview] = useState(true);
  const [overview, setOverview] = useState<AdminOverview | null>(null);

  // Accounts State
  const [accounts, setAccounts] = useState<LocalAccount[]>([]);
  const [loadingAccounts, setLoadingAccounts] = useState(false);
  const [accountSearch, setAccountSearch] = useState("");
  const [selectedRoleFilter, setSelectedRoleFilter] = useState("all");

  // Account Modals
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [newUsername, setNewUsername] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newDisplayName, setNewDisplayName] = useState("");
  const [newEmail, setNewEmail] = useState("");
  const [newRole, setNewRole] = useState<LocalAccountRole>("Employee");
  const [newDepartment, setNewDepartment] = useState("Operations");
  const [creatingAccount, setCreatingAccount] = useState(false);

  // Reset Password Modal
  const [resetModalAccount, setResetModalAccount] = useState<LocalAccount | null>(null);
  const [resetPasswordValue, setResetPasswordValue] = useState("");
  const [resettingPassword, setResettingPassword] = useState(false);

  // Tickets State
  const [tickets, setTickets] = useState<SupportTicket[]>([]);
  const [loadingTickets, setLoadingTickets] = useState(false);
  const [ticketStatusFilter, setTicketStatusFilter] = useState("all");
  const [selectedTicket, setSelectedTicket] = useState<SupportTicket | null>(null);
  const [ticketAdminNotes, setTicketAdminNotes] = useState("");
  const [updatingTicket, setUpdatingTicket] = useState(false);

  // Database Connection State
  const [dbConfig, setDbConfig] = useState<DatabaseConfig | null>(null);
  const [loadingDb, setLoadingDb] = useState(false);
  const [dbUrlInput, setDbUrlInput] = useState("");
  const [supabaseDbUrlInput, setSupabaseDbUrlInput] = useState("");
  const [supabaseUrlInput, setSupabaseUrlInput] = useState("");
  const [supabaseKeyInput, setSupabaseKeyInput] = useState("");
  const [poolMin, setPoolMin] = useState(2);
  const [poolMax, setPoolMax] = useState(10);
  const [showDbUrl, setShowDbUrl] = useState(false);
  const [showSupabaseKey, setShowSupabaseKey] = useState(false);
  const [testingDb, setTestingDb] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string; latency_ms?: number } | null>(null);
  const [savingDb, setSavingDb] = useState(false);

  // Check administrative privilege: strictly Admin only; Superior level role cannot use or view Admin Dashboard
  const isAdmin =
    identity?.subject === "admin" ||
    Boolean(identity?.email && identity.email.toLowerCase().includes("admin@company")) ||
    Boolean(identity?.roles.includes("Admin"));

  const loadOverview = useCallback(async () => {
    setLoadingOverview(true);
    try {
      const data = await api.adminOverview();
      setOverview(data);
    } catch (err) {
      notify(err instanceof Error ? err.message : "Failed to load overview data", "danger");
    } finally {
      setLoadingOverview(false);
    }
  }, [api, notify]);

  const loadAccounts = useCallback(async () => {
    setLoadingAccounts(true);
    try {
      const data = await api.adminListAccounts();
      setAccounts(data);
    } catch (err) {
      notify(err instanceof Error ? err.message : "Failed to load accounts", "danger");
    } finally {
      setLoadingAccounts(false);
    }
  }, [api, notify]);

  const loadTickets = useCallback(async () => {
    setLoadingTickets(true);
    try {
      const data = await api.adminListTickets(ticketStatusFilter !== "all" ? ticketStatusFilter : undefined);
      setTickets(data);
    } catch (err) {
      notify(err instanceof Error ? err.message : "Failed to load tickets", "danger");
    } finally {
      setLoadingTickets(false);
    }
  }, [api, notify, ticketStatusFilter]);

  const loadDatabaseConfig = useCallback(async () => {
    setLoadingDb(true);
    try {
      const data = await api.adminGetDatabaseConfig();
      setDbConfig(data);
      setDbUrlInput(data.database_url_masked || "");
      setSupabaseDbUrlInput(data.supabase_database_url_masked || "");
      setSupabaseUrlInput(data.supabase_url || "");
      setSupabaseKeyInput(data.supabase_key_masked || "");
      setPoolMin(data.pool_min_size || 2);
      setPoolMax(data.pool_max_size || 10);
    } catch (err) {
      notify(err instanceof Error ? err.message : "Failed to load database config", "danger");
    } finally {
      setLoadingDb(false);
    }
  }, [api, notify]);

  useEffect(() => {
    void loadOverview();
  }, [loadOverview]);

  useEffect(() => {
    if (activeTab === "accounts") void loadAccounts();
    if (activeTab === "tickets") void loadTickets();
    if (activeTab === "database") void loadDatabaseConfig();
  }, [activeTab, loadAccounts, loadTickets, loadDatabaseConfig]);

  if (!isAdmin) {
    return (
      <div className="admin-page" style={{ alignItems: "center", justifyContent: "center", minHeight: "60vh" }}>
        <div className="admin-stat-card" style={{ maxWidth: "540px", textAlign: "center", padding: "var(--space-8)" }}>
          <div style={{
            width: "56px",
            height: "56px",
            margin: "0 auto var(--space-4)",
            borderRadius: "var(--radius-full)",
            background: "var(--danger-bg)",
            color: "var(--danger-fg)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}>
            <ShieldAlert size={32} />
          </div>
          <h2 style={{ fontSize: "var(--text-xl)", margin: "0 0 var(--space-2)", color: "var(--text)" }}>
            Admin Dashboard Restricted
          </h2>
          <p style={{ color: "var(--text-secondary)", lineHeight: "var(--leading-read)", margin: "0 0 var(--space-6)" }}>
            This administration console is strictly restricted to system developers and Master Administrators [admin / admin@company]. Superior and user roles cannot use or view the Admin Dashboard.
          </p>
          {onNavigateHome && (
            <button type="button" className="btn btn-primary" onClick={onNavigateHome}>
              Return to Assistant
            </button>
          )}
        </div>
      </div>
    );
  }

  // --- Account Actions ---
  const handleCreateAccount = async (e: FormEvent) => {
    e.preventDefault();
    if (!newUsername.trim() || !newPassword.trim() || !newDisplayName.trim()) {
      notify("Please fill in Username, Password, and Display Name", "danger");
      return;
    }
    setCreatingAccount(true);
    try {
      await api.adminCreateAccount({
        username: newUsername.trim(),
        password: newPassword.trim(),
        role: newRole,
        display_name: newDisplayName.trim(),
        email: newEmail.trim() || undefined,
        department: newDepartment.trim() || undefined,
      });
      notify(`Account for '${newDisplayName}' created successfully with isolated storage!`, "success");
      setCreateModalOpen(false);
      setNewUsername("");
      setNewPassword("");
      setNewDisplayName("");
      setNewEmail("");
      void loadAccounts();
      void loadOverview();
    } catch (err) {
      notify(err instanceof Error ? err.message : "Failed to create account", "danger");
    } finally {
      setCreatingAccount(false);
    }
  };

  const handleToggleActive = async (acc: LocalAccount) => {
    try {
      await api.adminUpdateAccount(acc.id, { active: !acc.active });
      notify(`Account '${acc.username}' is now ${!acc.active ? "Active" : "Disabled"}.`, "success");
      void loadAccounts();
      void loadOverview();
    } catch (err) {
      notify(err instanceof Error ? err.message : "Failed to update account status", "danger");
    }
  };

  const handleResetPassword = async (e: FormEvent) => {
    e.preventDefault();
    if (!resetModalAccount) return;
    if (!resetPasswordValue.trim() || resetPasswordValue.length < 6) {
      notify("Password must be at least 6 characters.", "danger");
      return;
    }
    setResettingPassword(true);
    try {
      await api.adminResetPassword(resetModalAccount.id, resetPasswordValue.trim());
      notify(`Password for '${resetModalAccount.display_name}' has been successfully reset!`, "success");
      setResetModalAccount(null);
      setResetPasswordValue("");
      void loadAccounts();
    } catch (err) {
      notify(err instanceof Error ? err.message : "Failed to reset password", "danger");
    } finally {
      setResettingPassword(false);
    }
  };

  const generateRandomPassword = () => {
    const chars = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789!@#$%^&*";
    let pwd = "";
    for (let i = 0; i < 12; i++) {
      pwd += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    setResetPasswordValue(pwd);
  };

  const handleDeleteAccount = async (acc: LocalAccount) => {
    if (!window.confirm(`Are you sure you want to delete user account '${acc.username}' (${acc.display_name})?`)) {
      return;
    }
    try {
      await api.adminDeleteAccount(acc.id);
      notify(`Account '${acc.username}' deleted.`, "success");
      void loadAccounts();
      void loadOverview();
    } catch (err) {
      notify(err instanceof Error ? err.message : "Failed to delete account", "danger");
    }
  };

  // --- Ticket Actions ---
  const handleUpdateTicketStatus = async (ticketId: string, newStatus: string) => {
    setUpdatingTicket(true);
    try {
      const updated = await api.adminUpdateTicket(ticketId, {
        status: newStatus,
        admin_notes: ticketAdminNotes.trim() || undefined,
      });
      notify(`Ticket ${ticketId} updated to ${newStatus}.`, "success");
      setSelectedTicket(updated);
      void loadTickets();
      void loadOverview();
    } catch (err) {
      notify(err instanceof Error ? err.message : "Failed to update ticket", "danger");
    } finally {
      setUpdatingTicket(false);
    }
  };

  // --- Database Actions ---
  const handleTestDatabase = async () => {
    setTestingDb(true);
    setTestResult(null);
    try {
      const payload: { database_url?: string; supabase_database_url?: string } = {};
      if (supabaseDbUrlInput && !supabaseDbUrlInput.includes("********")) {
        payload.supabase_database_url = supabaseDbUrlInput;
      }
      if (dbUrlInput && !dbUrlInput.includes("********")) {
        payload.database_url = dbUrlInput;
      }
      const res = await api.adminTestDatabase(payload);
      setTestResult(res);
      if (res.success) {
        notify(`Database connection verified in ${res.latency_ms}ms!`, "success");
      } else {
        notify(res.message, "danger");
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Connection test failed";
      setTestResult({ success: false, message: msg });
      notify(msg, "danger");
    } finally {
      setTestingDb(false);
    }
  };

  const handleSaveDatabaseConfig = async (e: FormEvent) => {
    e.preventDefault();
    setSavingDb(true);
    try {
      const payload: Record<string, unknown> = {
        pool_min_size: poolMin,
        pool_max_size: poolMax,
      };
      if (supabaseDbUrlInput && !supabaseDbUrlInput.includes("********")) {
        payload.supabase_database_url = supabaseDbUrlInput;
      }
      if (dbUrlInput && !dbUrlInput.includes("********")) {
        payload.database_url = dbUrlInput;
      }
      if (supabaseUrlInput) {
        payload.supabase_url = supabaseUrlInput;
      }
      if (supabaseKeyInput && !supabaseKeyInput.includes("****")) {
        payload.supabase_key = supabaseKeyInput;
      }

      const res = await api.adminUpdateDatabaseConfig(payload);
      notify(res.message, "success");
      void loadDatabaseConfig();
      void loadOverview();
    } catch (err) {
      notify(err instanceof Error ? err.message : "Failed to save database configuration", "danger");
    } finally {
      setSavingDb(false);
    }
  };

  const filteredAccounts = accounts.filter((acc) => {
    const matchesSearch =
      acc.username.toLowerCase().includes(accountSearch.toLowerCase()) ||
      acc.display_name.toLowerCase().includes(accountSearch.toLowerCase()) ||
      (acc.email && acc.email.toLowerCase().includes(accountSearch.toLowerCase())) ||
      (acc.department && acc.department.toLowerCase().includes(accountSearch.toLowerCase()));
    const matchesRole = selectedRoleFilter === "all" || acc.role.toLowerCase() === selectedRoleFilter.toLowerCase();
    return matchesSearch && matchesRole;
  });

  return (
    <div className="admin-page">
      {/* ── Executive Hero Card ────────────────────────────────────────── */}
      <section className="admin-hero-card">
        <div className="admin-hero-left">
          <div className="admin-hero-icon">
            <ShieldCheck size={26} />
          </div>
          <div>
            <div className="admin-hero-title-row">
              <h1 className="admin-hero-title">Platform Admin Console</h1>
              <span className="admin-hero-badge">Break-Glass Ready</span>
            </div>
            <p className="admin-hero-subtitle">
              Centralized developer & management controls: Credentials, trouble tickets, and database connection
            </p>
          </div>
        </div>

        <div className="admin-hero-right">
          <div className="admin-user-pill">
            Logged in as: <strong>{identity?.name || identity?.subject}</strong>
          </div>
          {onNavigateHome && (
            <button type="button" className="btn btn-secondary btn-sm" onClick={onNavigateHome}>
              Return to Assistant
            </button>
          )}
        </div>
      </section>

      {/* ── High-Contrast Nav Tabs ──────────────────────────────────────── */}
      <nav className="admin-nav-bar" aria-label="Admin Navigation Tabs">
        <button
          type="button"
          className={`admin-tab-btn ${activeTab === "overview" ? "is-active" : ""}`}
          onClick={() => setActiveTab("overview")}
        >
          <Activity size={16} />
          <span>System Overview</span>
        </button>

        <button
          type="button"
          className={`admin-tab-btn ${activeTab === "accounts" ? "is-active" : ""}`}
          onClick={() => setActiveTab("accounts")}
        >
          <Users size={16} />
          <span>User Accounts & Credentials</span>
          <span className="admin-badge-count">{accounts.length || overview?.total_users || 0}</span>
        </button>

        <button
          type="button"
          className={`admin-tab-btn ${activeTab === "tickets" ? "is-active" : ""}`}
          onClick={() => setActiveTab("tickets")}
        >
          <LifeBuoy size={16} />
          <span>Trouble Reports & Tickets</span>
          {Boolean(overview?.open_tickets) && (
            <span className="admin-badge-count is-urgent">{overview?.open_tickets}</span>
          )}
        </button>

        <button
          type="button"
          className={`admin-tab-btn ${activeTab === "database" ? "is-active" : ""}`}
          onClick={() => setActiveTab("database")}
        >
          <Database size={16} />
          <span>Backend Database Connection (Admin / CEO)</span>
        </button>
      </nav>

      {/* ── TAB 1: SYSTEM OVERVIEW ───────────────────────────────────────── */}
      {activeTab === "overview" && (
        <div>
          {loadingOverview ? (
            <div style={{ textAlign: "center", padding: "var(--space-10) 0", color: "var(--text-secondary)" }}>
              <LoaderCircle size={32} className="spin" style={{ color: "var(--primary-600)", margin: "0 auto var(--space-3)" }} />
              <div>Loading real-time platform telemetry…</div>
            </div>
          ) : (
            <>
              {/* Stat Cards */}
              <div className="admin-bento-grid">
                <div className="admin-stat-card">
                  <div className="admin-stat-header">
                    <span className="admin-stat-label">User Accounts</span>
                    <div className="admin-stat-icon" style={{ background: "var(--primary-50)", color: "var(--primary-600)" }}>
                      <Users size={18} />
                    </div>
                  </div>
                  <div className="admin-stat-value">{overview?.total_users || 0}</div>
                  <div className="admin-stat-meta">
                    <span style={{ width: "6px", height: "6px", borderRadius: "50%", background: "var(--success-fg)" }} />
                    <span>{overview?.active_users || 0} active credentials</span>
                  </div>
                </div>

                <div className="admin-stat-card">
                  <div className="admin-stat-header">
                    <span className="admin-stat-label">Trouble Reports</span>
                    <div className="admin-stat-icon" style={{
                      background: overview?.open_tickets ? "var(--danger-bg)" : "var(--success-bg)",
                      color: overview?.open_tickets ? "var(--danger-fg)" : "var(--success-fg)"
                    }}>
                      <LifeBuoy size={18} />
                    </div>
                  </div>
                  <div className="admin-stat-value" style={{ color: overview?.open_tickets ? "var(--danger-fg)" : "inherit" }}>
                    {overview?.open_tickets || 0} Open
                  </div>
                  <div className="admin-stat-meta">
                    <span>{overview?.total_tickets || 0} total reported tickets</span>
                  </div>
                </div>

                <div className="admin-stat-card">
                  <div className="admin-stat-header">
                    <span className="admin-stat-label">Database Health</span>
                    <div className="admin-stat-icon" style={{
                      background: overview?.db_connected ? "var(--success-bg)" : "var(--danger-bg)",
                      color: overview?.db_connected ? "var(--success-fg)" : "var(--danger-fg)"
                    }}>
                      <Database size={18} />
                    </div>
                  </div>
                  <div className="admin-stat-value" style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                    <span style={{
                      width: "10px",
                      height: "10px",
                      borderRadius: "50%",
                      background: overview?.db_connected ? "var(--success-fg)" : "var(--danger-fg)",
                    }} />
                    <span>{overview?.db_connected ? "Connected" : "Offline"}</span>
                  </div>
                  <div className="admin-stat-meta">
                    <span>{overview?.db_type} ({overview?.db_latency_ms}ms)</span>
                  </div>
                </div>

                <div className="admin-stat-card">
                  <div className="admin-stat-header">
                    <span className="admin-stat-label">Storage Isolation</span>
                    <div className="admin-stat-icon" style={{ background: "var(--info-bg)", color: "var(--info-fg)" }}>
                      <ShieldCheck size={18} />
                    </div>
                  </div>
                  <div className="admin-stat-value">100% Isolated</div>
                  <div className="admin-stat-meta">
                    <span>Fresh per user (strictly non-shared)</span>
                  </div>
                </div>
              </div>

              {/* Informational Cards */}
              <div className="admin-info-grid">
                <div className="admin-info-card">
                  <h3 className="admin-info-title">
                    <KeyRound size={20} style={{ color: "var(--primary-600)" }} />
                    Emergency Developer Account [admin / admin@company]
                  </h3>
                  <p>
                    This console and application support a direct break-glass administrator login for developers and company management:
                  </p>
                  <div className="admin-code-box">
                    <div>User ID: <strong>admin</strong> (or admin@company.com)</div>
                    <div>Password: <strong>admin@company</strong></div>
                    <div>Access: <strong>Master Administrator (Full System Rights)</strong></div>
                  </div>
                  <div className="alert alert-success" style={{ marginTop: "var(--space-2)" }}>
                    <CheckCircle2 size={18} />
                    <div className="alert-body">
                      <div className="alert-title">UECP Portal Immunity</div>
                      <p style={{ margin: "2px 0 0", fontSize: "var(--text-xs)" }}>
                        Even if the external UECP control plane is unreachable, frozen, revoked, or fails, the admin login automatically activates local break-glass authorization.
                      </p>
                    </div>
                  </div>
                </div>

                <div className="admin-info-card">
                  <h3 className="admin-info-title">
                    <Database size={20} style={{ color: "var(--info-fg)" }} />
                    Shared Database & Per-User Storage Architecture
                  </h3>
                  <p>
                    The backend database connection configured in this dashboard is a <strong>common cluster</strong> shared across the organization.
                  </p>
                  <ul style={{ fontSize: "var(--text-sm)", color: "var(--text-secondary)", lineHeight: "var(--leading-read)", paddingLeft: "var(--space-5)", margin: 0 }}>
                    <li style={{ marginBottom: "var(--space-2)" }}>
                      <strong>Per-User Partitioning</strong>: Every user account is identified by a unique ID and email. Conversations, chat history, uploaded documents, and preferences are strictly partitioned.
                    </li>
                    <li style={{ marginBottom: "var(--space-2)" }}>
                      <strong>Zero Leakage</strong>: When User A logs in with their email, only User A's data is retrieved. When User B logs in, their workspace is completely fresh and isolated.
                    </li>
                    <li>
                      <strong>Confidential DB Credentials</strong>: Database connection strings, passwords, and API keys are only visible to the CEO and Admin Dashboard login. Regular users cannot access DB settings.
                    </li>
                  </ul>
                </div>
              </div>
            </>
          )}
        </div>
      )}

      {/* ── TAB 2: USER ACCOUNTS & CREDENTIALS ───────────────────────────── */}
      {activeTab === "accounts" && (
        <div className="admin-card-container">
          {/* Toolbar */}
          <div className="admin-toolbar">
            <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)", flex: 1, maxWidth: "540px" }}>
              <div style={{ position: "relative", width: "100%" }}>
                <Search size={16} style={{ position: "absolute", left: "12px", top: "50%", transform: "translateY(-50%)", color: "var(--text-muted)" }} />
                <input
                  type="text"
                  className="input"
                  style={{ paddingLeft: "36px" }}
                  placeholder="Search by User ID, Name, Email, or Department..."
                  value={accountSearch}
                  onChange={(e) => setAccountSearch(e.target.value)}
                />
              </div>

              <select
                className="select"
                style={{ width: "160px", flexShrink: 0 }}
                value={selectedRoleFilter}
                onChange={(e) => setSelectedRoleFilter(e.target.value)}
              >
                <option value="all">All Roles</option>
                <option value="Superior">Superior</option>
                <option value="Supervisor">Supervisor</option>
                <option value="Project Engineer">Project Engineer</option>
                <option value="Employee">Employee</option>
              </select>
            </div>

            <div style={{ display: "flex", gap: "var(--space-2)" }}>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => void loadAccounts()}
                disabled={loadingAccounts}
              >
                <RefreshCw size={15} className={loadingAccounts ? "spin" : ""} />
                <span>Refresh</span>
              </button>
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => setCreateModalOpen(true)}
              >
                <UserPlus size={16} />
                <span>Create User Account</span>
              </button>
            </div>
          </div>

          {/* Accounts Table */}
          <div className="admin-table-scroll-wrap">
            <table className="admin-table">
              <thead>
                <tr>
                  <th>User / Name</th>
                  <th>Email Address</th>
                  <th>Role</th>
                  <th>Department</th>
                  <th>Status</th>
                  <th className="actions-col">Developer Actions</th>
                </tr>
              </thead>
              <tbody>
                {loadingAccounts ? (
                  <tr>
                    <td colSpan={6} style={{ padding: "var(--space-10) var(--space-4)", textAlign: "center" }}>
                      <LoaderCircle size={28} className="spin" style={{ color: "var(--primary-600)", margin: "0 auto" }} />
                    </td>
                  </tr>
                ) : filteredAccounts.length === 0 ? (
                  <tr>
                    <td colSpan={6} style={{ padding: "var(--space-10) var(--space-4)", textAlign: "center", color: "var(--text-muted)" }}>
                      No user accounts found matching the filter criteria.
                    </td>
                  </tr>
                ) : (
                  filteredAccounts.map((acc) => (
                    <tr key={acc.id}>
                      <td>
                        <div style={{ fontWeight: "var(--weight-semibold)", color: "var(--text)" }}>{acc.display_name}</div>
                        <div style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
                          ID: {acc.username}
                        </div>
                      </td>
                      <td style={{ color: "var(--text-secondary)" }}>
                        {acc.email || <span style={{ color: "var(--text-muted)" }}>Not set</span>}
                      </td>
                      <td>
                        <span className={`badge ${
                          acc.role === "Superior" || acc.role === "Admin"
                            ? "badge-primary"
                            : acc.role === "Supervisor"
                            ? "badge-accent"
                            : ""
                        }`}>
                          {acc.role}
                        </span>
                      </td>
                      <td style={{ color: "var(--text-secondary)" }}>{acc.department || "General"}</td>
                      <td>
                        <span style={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: "6px",
                          fontSize: "var(--text-xs)",
                          fontWeight: "var(--weight-medium)",
                          color: acc.active ? "var(--success-fg)" : "var(--danger-fg)",
                          background: acc.active ? "var(--success-bg)" : "var(--danger-bg)",
                          border: `1px solid ${acc.active ? "var(--success-border)" : "var(--danger-border)"}`,
                          padding: "2px 8px",
                          borderRadius: "var(--radius-full)",
                        }}>
                          <span style={{
                            width: "6px",
                            height: "6px",
                            borderRadius: "50%",
                            background: acc.active ? "var(--success-fg)" : "var(--danger-fg)",
                          }} />
                          {acc.active ? "Active" : "Locked / Inactive"}
                        </span>
                      </td>
                      <td className="actions-col">
                        <div className="admin-actions-cell">
                          <button
                            type="button"
                            className="btn btn-secondary btn-sm"
                            onClick={() => {
                              setResetModalAccount(acc);
                              setResetPasswordValue("");
                            }}
                            title="Reset password to resolve login lockout"
                          >
                            <KeyRound size={13} />
                            <span>Reset Password</span>
                          </button>

                          <button
                            type="button"
                            className="btn btn-secondary btn-sm"
                            onClick={() => void handleToggleActive(acc)}
                            title={acc.active ? "Deactivate user account" : "Activate user account"}
                            style={{ color: acc.active ? "var(--warning-fg, #d97706)" : "var(--success-fg)" }}
                          >
                            {acc.active ? <Lock size={13} /> : <UserCheck size={13} />}
                            <span>{acc.active ? "Lock" : "Unlock"}</span>
                          </button>

                          {acc.username !== "admin" ? (
                            <button
                              type="button"
                              className="admin-btn-delete"
                              onClick={() => void handleDeleteAccount(acc)}
                              title="Permanently delete user account"
                            >
                              <Trash2 size={13} />
                              <span>Delete</span>
                            </button>
                          ) : (
                            <span
                              className="admin-action-protected"
                              title="System Administrator account cannot be deleted"
                            >
                              <Shield size={12} />
                              <span>Protected</span>
                            </span>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── TAB 3: TROUBLE REPORTS & TICKETS ─────────────────────────────── */}
      {activeTab === "tickets" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
          {/* Header & Filter */}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "var(--space-3)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
              <span style={{ fontSize: "var(--text-sm)", color: "var(--text-secondary)", fontWeight: "var(--weight-medium)" }}>
                Filter Status:
              </span>
              {["all", "Open", "In Progress", "Resolved"].map((st) => (
                <button
                  key={st}
                  type="button"
                  onClick={() => setTicketStatusFilter(st)}
                  className={`btn btn-sm ${ticketStatusFilter === st ? "btn-primary" : "btn-secondary"}`}
                >
                  {st}
                </button>
              ))}
            </div>

            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => void loadTickets()}
              disabled={loadingTickets}
            >
              <RefreshCw size={14} className={loadingTickets ? "spin" : ""} />
              <span>Refresh Tickets</span>
            </button>
          </div>

          {/* Tickets List */}
          {loadingTickets ? (
            <div style={{ textAlign: "center", padding: "var(--space-10) 0" }}>
              <LoaderCircle size={32} className="spin" style={{ color: "var(--primary-600)", margin: "0 auto" }} />
            </div>
          ) : tickets.length === 0 ? (
            <div className="admin-stat-card" style={{ textAlign: "center", padding: "var(--space-10) var(--space-6)" }}>
              <CheckCircle2 size={40} style={{ color: "var(--success-fg)", margin: "0 auto var(--space-3)" }} />
              <h3 style={{ margin: "0 0 var(--space-1)", fontSize: "var(--text-lg)", color: "var(--text)" }}>
                No Trouble Reports
              </h3>
              <p style={{ margin: 0, color: "var(--text-secondary)", fontSize: "var(--text-sm)" }}>
                All user accounts and services are running smoothly. Zero tickets under this filter.
              </p>
            </div>
          ) : (
            <div style={{ display: "grid", gridTemplateColumns: selectedTicket ? "1.2fr 1fr" : "1fr", gap: "var(--space-4)" }}>
              <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
                {tickets.map((t) => {
                  const isSelected = selectedTicket?.id === t.id;
                  const severityBadgeClass =
                    t.severity === "Critical" || t.severity === "High"
                      ? "badge-danger"
                      : t.severity === "Medium"
                      ? "badge-warning"
                      : "badge-primary";

                  return (
                    <div
                      key={t.id}
                      onClick={() => {
                        setSelectedTicket(t);
                        setTicketAdminNotes(t.admin_notes || "");
                      }}
                      style={{
                        background: isSelected ? "var(--primary-50)" : "var(--bg-surface)",
                        border: isSelected ? "2px solid var(--primary-600)" : "1px solid var(--border)",
                        borderRadius: "var(--radius-lg)",
                        padding: "var(--space-4) var(--space-5)",
                        cursor: "pointer",
                        boxShadow: "var(--shadow-card)",
                        transition: "all var(--dur-fast) var(--ease)",
                      }}
                    >
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "var(--space-2)" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
                          <span style={{
                            padding: "2px 6px",
                            borderRadius: "var(--radius-sm)",
                            fontSize: "11px",
                            fontWeight: 700,
                            background: "var(--bg-sunken)",
                            border: "1px solid var(--border)",
                            fontFamily: "var(--font-mono)",
                            color: "var(--text-secondary)",
                          }}>
                            {t.id}
                          </span>
                          <span className={`badge ${severityBadgeClass}`}>
                            {t.severity}
                          </span>
                          <span style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>{t.category}</span>
                        </div>
                        <span className={`badge ${t.status === "Resolved" ? "badge-success" : "badge-danger"}`}>
                          {t.status}
                        </span>
                      </div>

                      <div style={{ fontWeight: "var(--weight-semibold)", fontSize: "var(--text-base)", color: "var(--text)", marginBottom: "var(--space-1)" }}>
                        {t.subject}
                      </div>

                      <div style={{ fontSize: "var(--text-xs)", color: "var(--text-secondary)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <span>Reporter: <strong>{t.reporter_name}</strong> ({t.reporter_email})</span>
                        <span>{new Date(t.created_at).toLocaleString()}</span>
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Ticket Details Panel */}
              {selectedTicket && (
                <div className="admin-stat-card" style={{ gap: "var(--space-3)", height: "fit-content" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid var(--border-subtle)", paddingBottom: "var(--space-3)" }}>
                    <h3 style={{ margin: 0, fontSize: "var(--text-md)", color: "var(--text)" }}>Ticket Resolution</h3>
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      onClick={() => setSelectedTicket(null)}
                      aria-label="Close details"
                    >
                      <X size={16} />
                    </button>
                  </div>

                  <div>
                    <div style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)", marginBottom: "2px" }}>Subject</div>
                    <div style={{ fontWeight: "var(--weight-semibold)", fontSize: "var(--text-base)", color: "var(--text)" }}>
                      {selectedTicket.subject}
                    </div>
                  </div>

                  <div>
                    <div style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)", marginBottom: "4px" }}>User Description</div>
                    <div style={{
                      background: "var(--bg-sunken)",
                      border: "1px solid var(--border)",
                      padding: "var(--space-3)",
                      borderRadius: "var(--radius-md)",
                      fontSize: "var(--text-sm)",
                      lineHeight: "var(--leading-ui)",
                      color: "var(--text)",
                      whiteSpace: "pre-wrap",
                    }}>
                      {selectedTicket.description}
                    </div>
                  </div>

                  {selectedTicket.diagnostic_info && Object.keys(selectedTicket.diagnostic_info).length > 0 && (
                    <div>
                      <div style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)", marginBottom: "4px" }}>System Diagnostics</div>
                      <pre style={{
                        background: "var(--bg-sunken)",
                        border: "1px solid var(--border)",
                        padding: "var(--space-2) var(--space-3)",
                        borderRadius: "var(--radius-sm)",
                        fontSize: "11px",
                        fontFamily: "var(--font-mono)",
                        color: "var(--text-secondary)",
                        overflowX: "auto",
                        margin: 0,
                      }}>
                        {JSON.stringify(selectedTicket.diagnostic_info, null, 2)}
                      </pre>
                    </div>
                  )}

                  {/* Shortcut for Login Issues */}
                  {selectedTicket.category.toLowerCase().includes("login") && (
                    <div className="alert alert-info">
                      <KeyRound size={16} />
                      <div className="alert-body" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <div><strong>Login Issue Detected</strong>: Reset password for this user?</div>
                        <button
                          type="button"
                          className="btn btn-primary btn-sm"
                          onClick={() => {
                            const matching = accounts.find((a) => a.email === selectedTicket.reporter_email || a.id === selectedTicket.reporter_id);
                            if (matching) {
                              setResetModalAccount(matching);
                              setResetPasswordValue("");
                            } else {
                              notify("No registered account found with matching email.", "danger");
                            }
                          }}
                        >
                          Reset Password
                        </button>
                      </div>
                    </div>
                  )}

                  <div className="field">
                    <label className="field-label">Developer / Admin Resolution Notes</label>
                    <textarea
                      rows={3}
                      className="input"
                      style={{ height: "auto", padding: "var(--space-2) var(--space-3)" }}
                      placeholder="Enter notes on how this issue was resolved..."
                      value={ticketAdminNotes}
                      onChange={(e) => setTicketAdminNotes(e.target.value)}
                    />
                  </div>

                  <div style={{ display: "flex", gap: "var(--space-2)", marginTop: "var(--space-2)" }}>
                    <button
                      type="button"
                      className="btn btn-secondary"
                      onClick={() => void handleUpdateTicketStatus(selectedTicket.id, "In Progress")}
                      disabled={updatingTicket}
                      style={{ flex: 1 }}
                    >
                      Mark In Progress
                    </button>
                    <button
                      type="button"
                      className="btn btn-primary"
                      onClick={() => void handleUpdateTicketStatus(selectedTicket.id, "Resolved")}
                      disabled={updatingTicket}
                      style={{ flex: 1, background: "var(--success-fg)", borderColor: "var(--success-fg)" }}
                    >
                      Resolve Ticket
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* ── TAB 4: BACKEND DATABASE CONNECTION (ADMIN / CEO ONLY) ───────── */}
      {activeTab === "database" && (
        <div style={{ maxWidth: "880px", display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
          {/* Security Alert */}
          <div className="alert alert-info">
            <Lock size={18} />
            <div className="alert-body">
              <div className="alert-title">Confidential Infrastructure</div>
              <p style={{ margin: "2px 0 0", fontSize: "var(--text-xs)" }}>
                Database credentials and backend connection parameters are strictly restricted to the <strong>CEO</strong> and <strong>Master Administrator</strong>. Regular users have zero access to database credentials or connection configuration.
              </p>
            </div>
          </div>

          {loadingDb ? (
            <div style={{ textAlign: "center", padding: "var(--space-10) 0" }}>
              <LoaderCircle size={32} className="spin" style={{ color: "var(--primary-600)", margin: "0 auto" }} />
            </div>
          ) : (
            <>
              {/* Current Connection Status Box */}
              <div className="admin-stat-card">
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "var(--space-3)" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
                    <Server size={20} style={{ color: dbConfig?.is_connected ? "var(--success-fg)" : "var(--danger-fg)" }} />
                    <h3 style={{ margin: 0, fontSize: "var(--text-md)", color: "var(--text)" }}>Current Database Target</h3>
                  </div>
                  <span className={`badge ${dbConfig?.is_connected ? "badge-success" : "badge-danger"}`}>
                    {dbConfig?.is_connected ? `Connected (${dbConfig?.latency_ms}ms)` : "Offline"}
                  </span>
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "var(--space-4)", fontSize: "var(--text-sm)" }}>
                  <div>
                    <span style={{ color: "var(--text-muted)" }}>Dialect / Provider:</span>
                    <div style={{ fontWeight: "var(--weight-semibold)", color: "var(--text)", marginTop: "2px" }}>
                      {dbConfig?.database_type}
                    </div>
                  </div>
                  <div>
                    <span style={{ color: "var(--text-muted)" }}>Host / Node:</span>
                    <div style={{ fontWeight: "var(--weight-semibold)", color: "var(--text)", marginTop: "2px" }}>
                      {dbConfig?.host}:{dbConfig?.port}
                    </div>
                  </div>
                  <div>
                    <span style={{ color: "var(--text-muted)" }}>Database Name:</span>
                    <div style={{ fontWeight: "var(--weight-semibold)", color: "var(--text)", marginTop: "2px" }}>
                      {dbConfig?.database_name}
                    </div>
                  </div>
                </div>

                {dbConfig?.server_version && (
                  <div style={{ marginTop: "var(--space-3)", fontSize: "var(--text-xs)", color: "var(--text-secondary)" }}>
                    Server Version: {dbConfig.server_version}
                  </div>
                )}
              </div>

              {/* Database Settings Form */}
              <form onSubmit={handleSaveDatabaseConfig} className="admin-stat-card" style={{ gap: "var(--space-4)" }}>
                <h3 style={{ margin: 0, fontSize: "var(--text-md)", color: "var(--text)" }}>
                  Configure Database Connection
                </h3>

                {/* Supabase PostgreSQL DSN */}
                <div className="field">
                  <label className="field-label">Supabase PostgreSQL Connection URI (SUPABASE_DATABASE_URL)</label>
                  <div className="input-group">
                    <input
                      type={showDbUrl ? "text" : "password"}
                      className="input"
                      placeholder="postgresql://postgres.[ref]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres"
                      value={supabaseDbUrlInput}
                      onChange={(e) => setSupabaseDbUrlInput(e.target.value)}
                      style={{ fontFamily: "var(--font-mono)", fontSize: "var(--text-sm)" }}
                    />
                    <button
                      type="button"
                      className="btn btn-ghost btn-icon"
                      onClick={() => setShowDbUrl((v) => !v)}
                      aria-label={showDbUrl ? "Hide URI" : "Show URI"}
                    >
                      {showDbUrl ? <EyeOff size={16} /> : <Eye size={16} />}
                    </button>
                  </div>
                  <span className="field-hint">Connects Nanvi to your Supabase cloud PostgreSQL pooler.</span>
                </div>

                {/* Supabase REST Credentials */}
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-4)" }}>
                  <div className="field">
                    <label className="field-label">Supabase Project URL (SUPABASE_URL)</label>
                    <input
                      type="text"
                      className="input"
                      placeholder="https://xyz.supabase.co"
                      value={supabaseUrlInput}
                      onChange={(e) => setSupabaseUrlInput(e.target.value)}
                    />
                  </div>

                  <div className="field">
                    <label className="field-label">Supabase Key (SUPABASE_KEY)</label>
                    <div className="input-group">
                      <input
                        type={showSupabaseKey ? "text" : "password"}
                        className="input"
                        placeholder="sb_publishable_..."
                        value={supabaseKeyInput}
                        onChange={(e) => setSupabaseKeyInput(e.target.value)}
                        style={{ fontFamily: "var(--font-mono)", fontSize: "var(--text-sm)" }}
                      />
                      <button
                        type="button"
                        className="btn btn-ghost btn-icon"
                        onClick={() => setShowSupabaseKey((v) => !v)}
                        aria-label={showSupabaseKey ? "Hide key" : "Show key"}
                      >
                        {showSupabaseKey ? <EyeOff size={16} /> : <Eye size={16} />}
                      </button>
                    </div>
                  </div>
                </div>

                {/* Pool min & max */}
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-4)" }}>
                  <div className="field">
                    <label className="field-label">Pool Minimum Connections</label>
                    <input
                      type="number"
                      min={1}
                      max={20}
                      className="input"
                      value={poolMin}
                      onChange={(e) => setPoolMin(Number(e.target.value))}
                    />
                  </div>

                  <div className="field">
                    <label className="field-label">Pool Maximum Connections</label>
                    <input
                      type="number"
                      min={2}
                      max={50}
                      className="input"
                      value={poolMax}
                      onChange={(e) => setPoolMax(Number(e.target.value))}
                    />
                  </div>
                </div>

                {/* Test Output Banner */}
                {testResult && (
                  <div className={`alert ${testResult.success ? "alert-success" : "alert-danger"}`}>
                    {testResult.success ? <CheckCircle2 size={18} /> : <AlertTriangle size={18} />}
                    <div className="alert-body">
                      <span>{testResult.message}</span>
                    </div>
                  </div>
                )}

                {/* Form Buttons */}
                <div style={{ display: "flex", justifyContent: "flex-end", gap: "var(--space-3)", marginTop: "var(--space-2)" }}>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => void handleTestDatabase()}
                    disabled={testingDb || savingDb}
                  >
                    {testingDb ? <LoaderCircle size={15} className="spin" /> : <HardDrive size={15} />}
                    <span>Test Connection</span>
                  </button>

                  <button
                    type="submit"
                    className="btn btn-primary"
                    disabled={testingDb || savingDb}
                  >
                    {savingDb ? <LoaderCircle size={15} className="spin" /> : <CheckCircle2 size={15} />}
                    <span>Save & Apply Connection</span>
                  </button>
                </div>
              </form>
            </>
          )}
        </div>
      )}

      {/* ── CREATE ACCOUNT MODAL ────────────────────────────────────────── */}
      {createModalOpen && (
        <div className="modal-backdrop" role="dialog" aria-modal="true">
          <div className="modal" style={{ width: "min(100%, 520px)" }}>
            <header className="modal-header">
              <h2 className="modal-title">Create New User Account</h2>
              <button type="button" className="btn btn-ghost btn-icon" onClick={() => setCreateModalOpen(false)}>
                <X size={18} />
              </button>
            </header>
            <form onSubmit={handleCreateAccount}>
              <div className="modal-body">
                <div className="field">
                  <label className="field-label">Full Name / Display Name</label>
                  <input
                    type="text"
                    className="input"
                    placeholder="e.g. Maya Nair"
                    value={newDisplayName}
                    onChange={(e) => setNewDisplayName(e.target.value)}
                    required
                  />
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-3)" }}>
                  <div className="field">
                    <label className="field-label">User ID (Username)</label>
                    <input
                      type="text"
                      className="input"
                      placeholder="e.g. maya"
                      value={newUsername}
                      onChange={(e) => setNewUsername(e.target.value)}
                      required
                    />
                  </div>

                  <div className="field">
                    <label className="field-label">Email ID (For Sign In)</label>
                    <input
                      type="email"
                      className="input"
                      placeholder="e.g. maya@nanvi.com"
                      value={newEmail}
                      onChange={(e) => setNewEmail(e.target.value)}
                    />
                  </div>
                </div>

                <div className="field">
                  <label className="field-label">Initial Password</label>
                  <input
                    type="text"
                    className="input"
                    placeholder="Min 6 characters"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    required
                    style={{ fontFamily: "var(--font-mono)" }}
                  />
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-3)" }}>
                  <div className="field">
                    <label className="field-label">Role</label>
                    <select
                      className="select"
                      value={newRole}
                      onChange={(e) => setNewRole(e.target.value as LocalAccountRole)}
                    >
                      <option value="Superior">Superior</option>
                      <option value="Supervisor">Supervisor</option>
                      <option value="Project Engineer">Project Engineer</option>
                      <option value="Employee">Employee</option>
                    </select>
                  </div>

                  <div className="field">
                    <label className="field-label">Department</label>
                    <input
                      type="text"
                      className="input"
                      placeholder="e.g. Engineering"
                      value={newDepartment}
                      onChange={(e) => setNewDepartment(e.target.value)}
                    />
                  </div>
                </div>
              </div>

              <footer className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setCreateModalOpen(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary" disabled={creatingAccount}>
                  {creatingAccount ? "Creating…" : "Create User"}
                </button>
              </footer>
            </form>
          </div>
        </div>
      )}

      {/* ── RESET PASSWORD MODAL ────────────────────────────────────────── */}
      {resetModalAccount && (
        <div className="modal-backdrop" role="dialog" aria-modal="true">
          <div className="modal" style={{ width: "min(100%, 460px)" }}>
            <header className="modal-header">
              <h2 className="modal-title">Reset User Password</h2>
              <button type="button" className="btn btn-ghost btn-icon" onClick={() => setResetModalAccount(null)}>
                <X size={18} />
              </button>
            </header>
            <form onSubmit={handleResetPassword}>
              <div className="modal-body">
                <p style={{ margin: 0, fontSize: "var(--text-sm)", color: "var(--text-secondary)" }}>
                  Set a new password for <strong>{resetModalAccount.display_name}</strong> ({resetModalAccount.username}):
                </p>

                <div className="field">
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <label className="field-label">New Password</label>
                    <button
                      type="button"
                      onClick={generateRandomPassword}
                      style={{
                        background: "none",
                        border: "none",
                        color: "var(--primary-600)",
                        fontSize: "var(--text-xs)",
                        cursor: "pointer",
                        padding: 0,
                        fontWeight: "var(--weight-semibold)",
                      }}
                    >
                      Generate Random
                    </button>
                  </div>
                  <input
                    type="text"
                    className="input"
                    placeholder="Enter new password (min 6 chars)"
                    value={resetPasswordValue}
                    onChange={(e) => setResetPasswordValue(e.target.value)}
                    required
                    style={{ fontFamily: "var(--font-mono)" }}
                  />
                </div>
              </div>

              <footer className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setResetModalAccount(null)}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary" disabled={resettingPassword}>
                  {resettingPassword ? "Saving…" : "Update Password"}
                </button>
              </footer>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
