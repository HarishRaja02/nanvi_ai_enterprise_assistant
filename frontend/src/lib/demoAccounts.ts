import { DEMO_MODE } from "./config";
import type { Role } from "./access";

export type DemoAccount = { username: string; password: string; role: Role; department: string; name: string; email: string };

/**
 * Development-only sign-in shortcuts for the backend's /dev/token endpoint.
 * The list is empty unless VITE_DEMO_MODE=true, so with a production build these
 * credentials are compiled out of the bundle entirely.
 */
export const DEMO_ACCOUNTS: DemoAccount[] = DEMO_MODE
  ? [
      { username: "ceo", password: "ceo@nanvi", role: "CEO", department: "Executive", name: "Arjun Mehta", email: "ceo@nanvi.local" },
      { username: "finance", password: "finance@nanvi", role: "Finance", department: "Finance", name: "Priya Sharma", email: "finance@nanvi.local" },
      { username: "hr", password: "hr@nanvi", role: "HR", department: "Human Resources", name: "Kavita Reddy", email: "hr@nanvi.local" },
      { username: "manager", password: "manager@nanvi", role: "Manager", department: "Engineering", name: "Rahul Patel", email: "manager@nanvi.local" },
      { username: "employee", password: "employee@nanvi", role: "Employee", department: "Operations", name: "Ankit Singh", email: "employee@nanvi.local" },
      { username: "itadmin", password: "itadmin@nanvi", role: "IT Admin", department: "IT", name: "Deepak Kumar", email: "itadmin@nanvi.local" },
    ]
  : [];
