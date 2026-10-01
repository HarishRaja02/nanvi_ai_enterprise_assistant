import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Trash2, UserPlus } from "lucide-react";
import type { LocalAccount, LocalAccountCreate, LocalAccountRole, NanviApiClient, UserIdentity } from "../../api";

type Props = { api: NanviApiClient; identity: UserIdentity };

const ALL_ROLES: LocalAccountRole[] = ["Superior", "Supervisor", "Project Engineer", "Employee"];
const SUPERVISOR_ROLES: LocalAccountRole[] = ["Project Engineer", "Employee"];

export function AccountManagement({ api, identity }: Props) {
  const isSuperior = identity.roles.includes("Superior");
  const allowedRoles = isSuperior ? ALL_ROLES : SUPERVISOR_ROLES;
  const [accounts, setAccounts] = useState<LocalAccount[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [confirmingRemoval, setConfirmingRemoval] = useState<string | null>(null);
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [email, setEmail] = useState("");
  const [department, setDepartment] = useState("");
  const [role, setRole] = useState<LocalAccountRole>(isSuperior ? "Supervisor" : "Employee");

  const loadAccounts = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setAccounts(await api.listLocalAccounts());
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Couldn't load user accounts.");
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => { void loadAccounts(); }, [loadAccounts]);

  const createAccount = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSaving(true);
    setError("");
    const account: LocalAccountCreate = {
      username: username.trim(),
      display_name: displayName.trim(),
      password,
      role,
      email: email.trim() || null,
      department: department.trim() || null,
    };
    try {
      await api.createLocalAccount(account);
      setUsername("");
      setDisplayName("");
      setPassword("");
      setEmail("");
      setDepartment("");
      await loadAccounts();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Couldn't create the account.");
    } finally {
      setSaving(false);
    }
  };

  const removeAccount = async (account: LocalAccount) => {
    if (confirmingRemoval !== account.id) {
      setConfirmingRemoval(account.id);
      return;
    }
    setError("");
    try {
      await api.deleteLocalAccount(account.id);
      setConfirmingRemoval(null);
      await loadAccounts();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Couldn't remove the account.");
    }
  };

  return (
    <div className="account-management">
      <section className="account-management-section" aria-labelledby="account-create-title">
        <div className="account-management-heading">
          <div>
            <h2 id="account-create-title">Create an account</h2>
            <p>{isSuperior ? "Create an account for any role." : "Supervisors can create Project Engineer and Employee accounts."}</p>
          </div>
          <UserPlus size={20} aria-hidden="true" />
        </div>

        {error && <p className="account-management-error" role="alert">{error}</p>}

        <form className="account-create-form" onSubmit={(event) => void createAccount(event)}>
          <label><span>User ID</span><input required maxLength={50} autoComplete="off" value={username} onChange={(event) => setUsername(event.target.value)} /></label>
          <label><span>Name</span><input required maxLength={200} value={displayName} onChange={(event) => setDisplayName(event.target.value)} /></label>
          <label><span>Temporary password</span><input required minLength={12} maxLength={200} type="password" autoComplete="new-password" value={password} onChange={(event) => setPassword(event.target.value)} /></label>
          <label><span>Role</span><select value={role} onChange={(event) => setRole(event.target.value as LocalAccountRole)}>{allowedRoles.map((item) => <option key={item}>{item}</option>)}</select></label>
          <label><span>Department</span><input maxLength={100} value={department} onChange={(event) => setDepartment(event.target.value)} /></label>
          <label><span>Email (optional)</span><input type="email" maxLength={255} autoComplete="off" value={email} onChange={(event) => setEmail(event.target.value)} /></label>
          <button className="account-primary-action" type="submit" disabled={saving}>
            <UserPlus size={16} aria-hidden="true" /> {saving ? "Creating…" : "Create account"}
          </button>
        </form>
      </section>

      <section className="account-management-section" aria-labelledby="account-list-title">
        <div className="account-management-heading">
          <div>
            <h2 id="account-list-title">User accounts</h2>
            <p>{loading ? "Loading accounts…" : `${accounts.length} ${accounts.length === 1 ? "account" : "accounts"}`}</p>
          </div>
          <button className="account-secondary-action" type="button" onClick={() => void loadAccounts()} disabled={loading}>Refresh</button>
        </div>

        {!loading && accounts.length === 0 ? (
          <p className="account-list-empty">No accounts are available for management.</p>
        ) : (
          <ul className="account-list">
            {accounts.map((account) => (
              <li key={account.id} className="account-list-row">
                <div className="account-list-details">
                  <strong>{account.display_name}</strong>
                  <span>{account.username} · {account.role}</span>
                  {account.department && <small>{account.department}</small>}
                </div>
                {confirmingRemoval === account.id ? (
                  <div className="account-remove-confirm">
                    <span>Remove this account?</span>
                    <button type="button" onClick={() => void removeAccount(account)}>Confirm</button>
                    <button type="button" onClick={() => setConfirmingRemoval(null)}>Cancel</button>
                  </div>
                ) : (
                  <button className="account-remove-action" type="button" aria-label={`Remove ${account.username}`} onClick={() => void removeAccount(account)}>
                    <Trash2 size={16} aria-hidden="true" />
                    <span>Remove</span>
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}