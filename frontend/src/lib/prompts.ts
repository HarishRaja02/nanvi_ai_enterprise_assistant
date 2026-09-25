import type { Permission } from "./access";

export type PromptDef = {
  /** Short name shown in the UI. */
  label: string;
  /** Exact text sent to Nanvi. Shown to the user before they click, so nothing is hidden. */
  prompt: string;
  /** Hidden from roles that would only get a denial. UX hint only; the server decides. */
  permission?: Permission;
  /** Optional small tag, e.g. the requested output format. */
  meta?: string;
};

export const visiblePrompts = <T extends PromptDef>(list: T[], permissions: readonly Permission[]): T[] =>
  list.filter((p) => !p.permission || permissions.includes(p.permission));

/** Starter questions on an empty conversation. Prompt strings are unchanged from the original chips. */
export const STARTERS: Array<PromptDef & { area: "documents" | "email" | "data" }> = [
  { area: "documents", label: "Travel expense policy (RAG)", prompt: "What is our travel expense reimbursement policy in Finance?", permission: "FILE_READ" },
  { area: "documents", label: "Acme Corp contract renewal (RAG)", prompt: "Summarize Acme Corp contract renewal in Customers", permission: "FILE_READ" },
  { area: "documents", label: "Harish R Resume (RAG)", prompt: "What are the skills and experience in Harish's resume?", permission: "FILE_READ" },
  { area: "documents", label: "Sprint 24 deliverables (RAG)", prompt: "What are the deliverables in Sprint 24 for Projects?", permission: "FILE_READ" },
  { area: "data", label: "Overdue invoices", prompt: "Show overdue invoices", permission: "FINANCE_READ" },
  { area: "documents", label: "Browse RAG document vaults", prompt: "Show me all company files and document vaults", permission: "FILE_READ" },
];
