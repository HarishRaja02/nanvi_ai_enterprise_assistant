import type { View } from "../../lib/access";
import type { PromptDef } from "../../lib/prompts";

export type WorkspaceSection = { title: string; prompts: PromptDef[] };
export type WorkspaceDef = { intro: string; sections: WorkspaceSection[] };

/**
 * Module landing pages. These are guided entry points into the assistant, NOT live dashboards:
 * the backend exposes no per-module data endpoints, so no figures or file lists are shown here.
 * Prompt strings are identical to the original app because the backend may route on phrasing.
 */
export const WORKSPACES: Partial<Record<View, WorkspaceDef>> = {
  Knowledge: {
    intro: "Ask questions about company documents. Answers cite the documents they come from and include only files your role can access.",
    sections: [
      { title: "Customers and contracts", prompts: [
        { label: "Customer SLAs and support guarantees", prompt: "What are the customer SLAs and support guarantees?" },
        { label: "Acme Corp contract renewal", prompt: "Summarize Acme Corp contract renewal in Customers" },
      ] },
      { title: "Projects", prompts: [
        { label: "Project Phoenix status", prompt: "What is the status of Project Phoenix in Projects vault?" },
        { label: "Sprint 24 deliverables", prompt: "What are the deliverables in Sprint 24 for Projects?" },
      ] },
      { title: "Policies", prompts: [
        { label: "Travel and expense policy", prompt: "Summarize travel and expense policy from Finance" },
      ] },
      { title: "Browse", prompts: [
        { label: "Browse document areas", prompt: "Show me all company files and document vaults" },
      ] },
    ],
  },
  Email: {
    intro: "Search your mailbox through Nanvi. Answers cite the email threads they come from.",
    sections: [{ title: "Suggested searches", prompts: [
      { label: "Latest financial and project updates", prompt: "Check my Gmail for latest financial and project updates" },
      { label: "Project Phoenix threads", prompt: "What emails did Rahul or Priya send regarding Project Phoenix?" },
      { label: "Contract and SLA notices", prompt: "Search inbox for customer contract and SLA notices" },
    ] }],
  },
  Data: {
    intro: "Ask questions about business data in plain language. Results come back in the conversation.",
    sections: [{ title: "Suggested questions", prompts: [
      { label: "Overdue invoices", prompt: "Show overdue invoices", permission: "FINANCE_READ" },
      { label: "Average employee salary", prompt: "What is the average salary of employees?", permission: "HR_READ" },
      { label: "Department budgets and managers", prompt: "Show all department budgets and managers" },
      { label: "Enterprise contracts and annual value", prompt: "List enterprise contracts and annual contract value" },
    ] }],
  },
  Finance: {
    intro: "Ask about financial documents, budgets, payables and expense policy.",
    sections: [
      { title: "Reports and forecasts", prompts: [
        { label: "Q1 2026 financial summary", prompt: "Summarize Q1 2026 financial summary in Finance" },
        { label: "Annual budget forecast 2026", prompt: "What is the annual budget forecast for 2026?" },
        { label: "Q1 budget forecast report", prompt: "Generate a report on Q1 budget forecast in Excel", meta: "Excel" },
      ] },
      { title: "Payables and receivables", prompts: [
        { label: "Vendor payment schedule", prompt: "Show vendor payment schedule and obligations" },
        { label: "Total overdue invoice amount", prompt: "Calculate total overdue invoice amount" },
      ] },
      { title: "Policy", prompts: [
        { label: "Travel reimbursement limits", prompt: "What is our travel expense reimbursement policy in Finance?" },
      ] },
    ],
  },
  HR: {
    intro: "Ask about people policies, benefits and headcount planning.",
    sections: [
      { title: "Policies and benefits", prompts: [
        { label: "Healthcare and dental benefits", prompt: "What are the healthcare and dental benefits in HR?" },
        { label: "Leave and vacation policy", prompt: "What is our leave and vacation policy in HR?" },
        { label: "Employee handbook rules", prompt: "Summarize the employee handbook rules in HR" },
      ] },
      { title: "People and planning", prompts: [
        { label: "Headcount planning for Q2", prompt: "Show headcount planning numbers for Q2" },
        { label: "Engineering staff directory", prompt: "Show employee directory in Engineering" },
      ] },
    ],
  },
};

export const REPORT_FORMATS = ["Excel", "PDF", "Word", "PowerPoint"] as const;

export const REPORT_TEMPLATES: PromptDef[] = [
  { label: "Overdue invoices summary", prompt: "Generate a report on overdue invoices in PDF", meta: "PDF" },
  { label: "Enterprise staff directory", prompt: "Generate a report on personnel directory in Excel", meta: "Excel" },
  { label: "Contract renewal schedule", prompt: "Generate a report on contract renewals in Word", meta: "Word" },
  { label: "Department budget presentation", prompt: "Generate a report on department budgets in PowerPoint", meta: "PowerPoint" },
];
