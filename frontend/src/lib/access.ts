/**
 * UX-only role → capability map used to decide what to *show*. It is NOT authorization:
 * Backend authorization remains authoritative and every backend request is re-checked server-side.
 */
export type Role =
  | "Superior" | "Supervisor" | "Project Engineer" | "Employee"
  | "CEO" | "Finance" | "HR" | "Manager" | "IT Admin" | "Admin";

export type Permission =
  | "FILE_READ" | "FILE_WRITE" | "EMAIL_READ" | "EMAIL_SEND"
  | "DATABASE_READ" | "DATABASE_WRITE" | "REPORT_CREATE" | "REPORT_DOWNLOAD"
  | "FINANCE_READ" | "HR_READ" | "AUDIT_READ" | "USER_MANAGE" | "ADMIN_ACCESS"
  | "SYSTEM_LOGS_READ";

export type View = "Chat" | "Knowledge" | "Email" | "Data" | "Reports" | "Finance" | "HR" | "Audit" | "Settings" | "AdminDashboard" | "Logs";

export type CanonicalRole = "Admin" | "Superior" | "Supervisor" | "Project Engineer" | "Employee";

export const ROLE_PERMISSIONS: Record<CanonicalRole, Permission[]> = {
  Admin: ["FILE_READ", "FILE_WRITE", "EMAIL_READ", "EMAIL_SEND", "DATABASE_READ", "DATABASE_WRITE", "REPORT_CREATE", "REPORT_DOWNLOAD", "FINANCE_READ", "HR_READ", "AUDIT_READ", "USER_MANAGE", "ADMIN_ACCESS", "SYSTEM_LOGS_READ"],
  Superior: ["FILE_READ", "FILE_WRITE", "EMAIL_READ", "EMAIL_SEND", "DATABASE_READ", "DATABASE_WRITE", "REPORT_CREATE", "REPORT_DOWNLOAD", "FINANCE_READ", "HR_READ", "AUDIT_READ", "USER_MANAGE", "SYSTEM_LOGS_READ"],
  Supervisor: ["FILE_READ", "FILE_WRITE", "EMAIL_READ", "EMAIL_SEND", "DATABASE_READ", "DATABASE_WRITE", "REPORT_CREATE", "REPORT_DOWNLOAD", "FINANCE_READ", "HR_READ", "USER_MANAGE"],
  "Project Engineer": ["FILE_READ"],
  Employee: ["FILE_READ"],
};

const ROLE_ALIASES: Record<string, CanonicalRole> = {
  admin: "Admin",
  Administrator: "Admin",
  CEO: "Superior",
  Finance: "Supervisor",
  Manager: "Supervisor",
  "IT Admin": "Supervisor",
  HR: "Project Engineer",
};

function canonicalRole(value: string): CanonicalRole | undefined {
  if (Object.prototype.hasOwnProperty.call(ROLE_PERMISSIONS, value)) return value as CanonicalRole;
  return Object.prototype.hasOwnProperty.call(ROLE_ALIASES, value) ? ROLE_ALIASES[value] : undefined;
}

export function isRole(value: string): value is Role {
  return canonicalRole(value) !== undefined;
}

/** Union across every recognised role the backend reported (a user may hold several). */
export function permissionsFor(roles: readonly string[]): Permission[] {
  const set = new Set<Permission>();
  for (const role of roles) {
    const canonical = canonicalRole(role);
    if (canonical) for (const permission of ROLE_PERMISSIONS[canonical]) set.add(permission);
  }
  return [...set];
}

export type NavEntry = { id: View; label: string; permission?: Permission; hidden?: boolean };
export type NavGroup = { id: string; label?: string; items: NavEntry[] };

/** Modules hidden from the frontend navigation and entrypoints while preserving their implementation. */
export const HIDDEN_VIEWS: readonly View[] = ["Knowledge", "Finance", "HR", "Audit"];

/** Only modules that exist in the app. Grouped by the job they do for the user. */
export const NAV_GROUPS: NavGroup[] = [
  { id: "assistant", items: [{ id: "Chat", label: "Assistant" }] },
  {
    id: "sources", label: "Sources",
    items: [
      { id: "Knowledge", label: "Knowledge", permission: "FILE_READ", hidden: true },
      { id: "Email", label: "Email", permission: "EMAIL_READ" },
      { id: "Data", label: "Data", permission: "DATABASE_READ" },
    ],
  },
  { id: "outputs", label: "Outputs", items: [{ id: "Reports", label: "Reports", permission: "REPORT_DOWNLOAD" }] },
  {
    id: "departments", label: "Departments",
    items: [
      { id: "Finance", label: "Finance", permission: "FINANCE_READ", hidden: true },
      { id: "HR", label: "HR", permission: "HR_READ", hidden: true },
    ],
  },
  {
    id: "administration", label: "Administration",
    items: [
      { id: "AdminDashboard", label: "Admin Console", permission: "ADMIN_ACCESS" },
    ],
  },
  {
    id: "governance", label: "Governance",
    items: [
      { id: "Audit", label: "Audit", permission: "AUDIT_READ", hidden: true },
      { id: "Settings", label: "Settings", permission: "USER_MANAGE" },
      { id: "Logs", label: "Logs", permission: "SYSTEM_LOGS_READ" },
    ],
  },
];


export function visibleNav(
  permissions: readonly Permission[],
  canAccessAdmin: boolean = false,
  includeHidden: boolean = false,
): NavGroup[] {
  return NAV_GROUPS
    .map((g) => ({
      ...g,
      items: g.items.filter((i) => {
        if (!includeHidden && (i.hidden || HIDDEN_VIEWS.includes(i.id))) {
          return false;
        }
        if (i.id === "AdminDashboard") {
          return canAccessAdmin || permissions.includes("ADMIN_ACCESS");
        }
        return !i.permission || permissions.includes(i.permission);
      }),
    }))
    .filter((g) => g.items.length > 0);
}

export function viewLabel(view: View): string {
  for (const g of NAV_GROUPS) for (const i of g.items) if (i.id === view) return i.label;
  return view;
}
