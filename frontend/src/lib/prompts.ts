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

const questionPrompts = (permission: Permission, questions: string[]): PromptDef[] =>
  questions.map((prompt) => ({ label: prompt, prompt, permission }));

/** Role-filtered question bank for the rotating empty-chat suggestions. */
export const ROTATING_STARTERS: PromptDef[] = [
  ...questionPrompts("FINANCE_READ", [
    "What invoices are overdue?",
    "What invoices are pending?",
    "What invoices have been paid?",
    "Which invoices are due this month?",
    "Which invoices are overdue by more than 30 days?",
    "What is the total value of overdue invoices?",
    "What is the total value of pending invoices?",
    "What is the total value of all invoices?",
    "Which customer has the highest invoice amount?",
    "Which customer has unpaid invoices?",
    "Show me the latest invoices.",
    "Show me all invoices from this month.",
    "Show me invoices that are due soon.",
    "Which invoices need immediate attention?",
    "Give me a summary of the current invoices.",
  ]),
  ...questionPrompts("FILE_READ", [
    "Which contracts are expiring soon?",
    "Which contracts have already expired?",
    "Which contracts need renewal?",
    "What contracts are active?",
    "What contracts are ending this month?",
    "What contracts are ending next month?",
    "Which customers have contracts expiring soon?",
    "What is the total value of our active contracts?",
    "Which contract has the highest annual value?",
    "Which contracts need renewal action?",
    "Show me the upcoming contract renewals.",
    "Give me a summary of all active contracts.",
    "Which contracts have the closest renewal dates?",
    "Which customers have multiple contracts?",
    "What contracts are currently inactive?",
  ]),
  ...questionPrompts("HR_READ", [
    "Who are the employees in the company?",
    "How many employees are currently active?",
    "How many employees are in each department?",
    "Who joined the company recently?",
    "Who has been with the company the longest?",
    "Which employees are in Engineering?",
    "Which employees are in Finance?",
    "Which employees are in HR?",
    "Which employees are in Sales?",
    "Which employees are in Operations?",
    "What is the average employee salary?",
    "What is the average salary by department?",
    "Which department has the highest average salary?",
    "Who are the highest-paid employees?",
    "Who are the lowest-paid employees?",
    "Which employees joined this year?",
    "Which employees joined last year?",
    "Who are the department managers?",
    "How many employees does each manager have?",
    "Give me an employee summary.",
  ]),
  ...questionPrompts("DATABASE_READ", [
    "What departments does the company have?",
    "Which department has the largest budget?",
    "Which department has the smallest budget?",
    "What is the budget for each department?",
    "Who manages each department?",
    "How many employees are in each department?",
    "Compare the Engineering and Finance budgets.",
    "Compare the Sales and Marketing budgets.",
    "Which department has the most employees?",
    "Give me a summary of all departments.",
  ]),
  ...questionPrompts("FINANCE_READ", [
    "What transactions happened recently?",
    "What are the latest transactions?",
    "What transactions are pending?",
    "What transactions have been completed?",
    "What is the total transaction amount?",
    "Which transactions are the largest?",
    "Which accounts have the most transactions?",
    "What transactions happened this month?",
    "What transactions happened last month?",
    "Which transactions need attention?",
    "Give me a summary of recent transactions.",
    "Show me the company's recent financial activity.",
  ]),
  ...questionPrompts("FILE_READ", [
    "What information do we have about the company?",
    "What documents are available?",
    "Find the latest company documents.",
    "Find documents related to finance.",
    "Find documents related to employees.",
    "Find documents related to contracts.",
    "Find documents related to projects.",
    "Search the company files for financial information.",
    "Search the company files for HR information.",
    "Search the company files for contract information.",
  ]),
  ...questionPrompts("EMAIL_READ", [
    "Find my recent emails.",
    "Show me unread emails.",
    "Find emails about invoices.",
    "Find emails about contracts.",
    "Find emails about employees.",
    "Find emails from my manager.",
    "Find emails that need a reply.",
    "Find the latest email about a project.",
    "Show me recent important emails.",
    "Summarize my recent emails.",
  ]),
  ...questionPrompts("FINANCE_READ", [
    "Give me a financial summary.",
    "Give me a summary of the company's invoices and contracts.",
    "Compare this month's invoices with last month's.",
    "Show me the departments with the highest expenses.",
    "What are the biggest financial items I should know about?",
    "Give me the most important things that need attention.",
  ]),
  ...questionPrompts("REPORT_CREATE", [
    "Create a report of overdue invoices.",
    "Create a report of upcoming contract renewals.",
  ]),
];
