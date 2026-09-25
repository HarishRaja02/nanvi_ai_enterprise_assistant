/**
 * UX-only role → capability map used to decide what to *show*. It is NOT authorization:
 * Backend authorization remains authoritative and every backend request is re-checked server-side.
 */
export type Role = "CEO" | "Finance" | "HR" | "Manager" | "Employee" | "IT Admin";

export type Permission =
  | "FILE_READ" | "FILE_WRITE" | "EMAIL_READ" | "EMAIL_SEND"
  | "DATABASE_READ" | "DATABASE_WRITE" | "REPORT_CREATE" | "REPORT_DOWNLOAD"
  | "FINANCE_READ" | "HR_READ" | "AUDIT_READ";

export type View = "Chat" | "Knowledge" | "Email" | "Data" | "Reports" | "Finance" | "HR" | "Audit" | "Settings";

export const ROLE_PERMISSIONS: Record<Role, Permission[]> = {
  CEO: ["FILE_READ", "FILE_WRITE", "EMAIL_READ", "EMAIL_SEND", "DATABASE_READ", "DATABASE_WRITE", "REPORT_CREATE", "REPORT_DOWNLOAD", "FINANCE_READ", "HR_READ", "AUDIT_READ"],
  Finance: ["FILE_READ", "FILE_WRITE", "EMAIL_READ", "EMAIL_SEND", "DATABASE_READ", "DATABASE_WRITE", "REPORT_CREATE", "REPORT_DOWNLOAD", "FINANCE_READ"],
  HR: ["FILE_READ", "FILE_WRITE", "EMAIL_READ", "EMAIL_SEND", "DATABASE_READ", "REPORT_CREATE", "REPORT_DOWNLOAD", "HR_READ"],
  Manager: ["FILE_READ", "FILE_WRITE", "EMAIL_READ", "EMAIL_SEND", "DATABASE_READ", "REPORT_CREATE", "REPORT_DOWNLOAD"],
  Employee: ["FILE_READ", "EMAIL_READ", "DATABASE_READ", "REPORT_CREATE", "REPORT_DOWNLOAD"],
  "IT Admin": ["FILE_READ", "FILE_WRITE", "EMAIL_READ", "EMAIL_SEND", "DATABASE_READ", "DATABASE_WRITE", "AUDIT_READ", "REPORT_DOWNLOAD"],
};

export function isRole(value: string): value is Role {
  return Object.prototype.hasOwnProperty.call(ROLE_PERMISSIONS, value);
}

/** Union across every recognised role the backend reported (a user may hold several). */
export function permissionsFor(roles: readonly string[]): Permission[] {
  const set = new Set<Permission>();
  for (const role of roles) if (isRole(role)) for (const p of ROLE_PERMISSIONS[role]) set.add(p);
  return [...set];
}

export type NavEntry = { id: View; label: string; permission?: Permission };
export type NavGroup = { id: string; label?: string; items: NavEntry[] };

/** Only modules that exist in the app. Grouped by the job they do for the user. */
export const NAV_GROUPS: NavGroup[] = [
  { id: "assistant", items: [{ id: "Chat", label: "Assistant" }] },
  {
    id: "sources", label: "Sources",
    items: [
      { id: "Knowledge", label: "Knowledge", permission: "FILE_READ" },
      { id: "Email", label: "Email", permission: "EMAIL_READ" },
      { id: "Data", label: "Data", permission: "DATABASE_READ" },
    ],
  },
  { id: "outputs", label: "Outputs", items: [{ id: "Reports", label: "Reports", permission: "REPORT_DOWNLOAD" }] },
  {
    id: "departments", label: "Departments",
    items: [
      { id: "Finance", label: "Finance", permission: "FINANCE_READ" },
      { id: "HR", label: "HR", permission: "HR_READ" },
    ],
  },
  {
    id: "governance", label: "Governance",
    items: [
      { id: "Audit", label: "Audit", permission: "AUDIT_READ" },
      { id: "Settings", label: "Settings" },
    ],
  },
];


export function visibleNav(permissions: readonly Permission[]): NavGroup[] {
  return NAV_GROUPS
    .map((g) => ({ ...g, items: g.items.filter((i) => !i.permission || permissions.includes(i.permission)) }))
    .filter((g) => g.items.length > 0);
}

export function viewLabel(view: View): string {
  for (const g of NAV_GROUPS) for (const i of g.items) if (i.id === view) return i.label;
  return view;
}
