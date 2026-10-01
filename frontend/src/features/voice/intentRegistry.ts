export interface FrontendIntentDef {
  intentId: string;
  label: string;
  description: string;
  category: "finance" | "crm" | "invoices" | "team" | "email" | "search" | "report";
  riskLevel: "low" | "medium" | "high";
  icon: string;
  variant?: "primary" | "secondary";
}

export const FRONTEND_INTENTS: Record<string, FrontendIntentDef> = {
  compare_previous_quarter: {
    intentId: "compare_previous_quarter",
    label: "Compare with Last Quarter",
    description: "Compare revenue and key financial metrics against the previous fiscal quarter.",
    category: "finance",
    riskLevel: "low",
    icon: "bar-chart",
    variant: "primary",
  },
  revenue_drivers: {
    intentId: "revenue_drivers",
    label: "Show Revenue Drivers",
    description: "Breakdown key product lines and contracts driving revenue.",
    category: "finance",
    riskLevel: "low",
    icon: "trending-up",
  },
  top_customers: {
    intentId: "top_customers",
    label: "Top Customers",
    description: "List top enterprise customers ranked by total spend and volume.",
    category: "finance",
    riskLevel: "low",
    icon: "users",
  },
  customer_invoices: {
    intentId: "customer_invoices",
    label: "View Invoices",
    description: "Retrieve all active and historical invoices for the account.",
    category: "crm",
    riskLevel: "low",
    icon: "file-text",
  },
  contact_details: {
    intentId: "contact_details",
    label: "Contact Details",
    description: "Display authorized contact information.",
    category: "crm",
    riskLevel: "low",
    icon: "phone",
  },
  compare_accounts: {
    intentId: "compare_accounts",
    label: "Compare Accounts",
    description: "Compare performance across peer accounts.",
    category: "crm",
    riskLevel: "low",
    icon: "layers",
  },
  download_invoice: {
    intentId: "download_invoice",
    label: "Download Invoice",
    description: "Prepare and export invoice file for download.",
    category: "invoices",
    riskLevel: "low",
    icon: "download",
  },
  view_line_items: {
    intentId: "view_line_items",
    label: "View Line Items",
    description: "Show itemized breakdown of products and services billed.",
    category: "invoices",
    riskLevel: "low",
    icon: "list",
  },
  payment_status: {
    intentId: "payment_status",
    label: "Payment Status",
    description: "Check transaction clearance and overdue status.",
    category: "invoices",
    riskLevel: "low",
    icon: "check-circle",
  },
  view_org_chart: {
    intentId: "view_org_chart",
    label: "View Org Chart",
    description: "Display managerial reporting hierarchy.",
    category: "team",
    riskLevel: "low",
    icon: "network",
  },
  contact_info: {
    intentId: "contact_info",
    label: "Contact Info",
    description: "Display enterprise directory contact information.",
    category: "team",
    riskLevel: "low",
    icon: "mail",
  },
  team_projects: {
    intentId: "team_projects",
    label: "Team Projects",
    description: "Show current active project allocations.",
    category: "team",
    riskLevel: "low",
    icon: "briefcase",
  },
  review_draft: {
    intentId: "review_draft",
    label: "Review Draft",
    description: "Preview generated email draft before sending.",
    category: "email",
    riskLevel: "low",
    icon: "edit-3",
  },
  send_confirmation: {
    intentId: "send_confirmation",
    label: "Confirm & Send Email",
    description: "High-risk action: Send outbound email. Requires explicit user confirmation.",
    category: "email",
    riskLevel: "high",
    icon: "send",
    variant: "primary",
  },
  find_replies: {
    intentId: "find_replies",
    label: "Find Replies",
    description: "Search for subsequent replies in the thread.",
    category: "email",
    riskLevel: "low",
    icon: "message-square",
  },
  show_more_detail: {
    intentId: "show_more_detail",
    label: "Show More Detail",
    description: "Expand on the verified figures with full context.",
    category: "search",
    riskLevel: "low",
    icon: "plus-circle",
  },
  verify_sources: {
    intentId: "verify_sources",
    label: "Verify Sources",
    description: "Inspect the verified citations and documents.",
    category: "search",
    riskLevel: "low",
    icon: "shield-check",
  },
  export_summary: {
    intentId: "export_summary",
    label: "Export Summary",
    description: "Export structured summary of current answer.",
    category: "report",
    riskLevel: "low",
    icon: "download",
  },
  search_again: {
    intentId: "search_again",
    label: "Search Again",
    description: "Run an expanded search across authorized files.",
    category: "search",
    riskLevel: "low",
    icon: "search",
  },
  browse_documents: {
    intentId: "browse_documents",
    label: "Browse Documents",
    description: "Open company document repository browser.",
    category: "search",
    riskLevel: "low",
    icon: "folder-open",
  },
};

export function isHighRiskIntent(intentId: string): boolean {
  return FRONTEND_INTENTS[intentId]?.riskLevel === "high";
}

export function getIntentMetadata(intentId: string): FrontendIntentDef {
  return (
    FRONTEND_INTENTS[intentId] || {
      intentId,
      label: intentId.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
      description: "Enterprise action",
      category: "search",
      riskLevel: "low",
      icon: "arrow-right",
    }
  );
}
