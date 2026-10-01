import type { Message } from "../types";
import type { UserIdentity } from "../api";

export interface ContextFilter {
  key: string;
  value: string;
  count?: number;
}

export interface ContextMetric {
  id: string;
  label: string;
  value: string;
  subtext?: string;
  tone?: "primary" | "accent" | "warning" | "success" | "danger";
}

export interface ContextSuggestion {
  id: string;
  text: string;
  category?: string;
}

export interface ContextAction {
  id: string;
  label: string;
  query: string;
  tone?: "primary" | "secondary" | "accent";
}

export interface ConversationContext {
  topic: string;
  topicCategory: "finance" | "hr" | "contracts" | "projects" | "email" | "general";
  activeFilters: ContextFilter[];
  metrics: ContextMetric[];
  suggestions: ContextSuggestion[];
  availableActions: ContextAction[];
  relevantFiles: string[];
}

/**
 * Pure contextual reasoning engine that analyzes conversation history and latest turns
 * to extract topics, active conversational filters, key figures, and dynamic next-step suggestions.
 */
export function extractConversationContext(
  messages: Message[],
  identity?: UserIdentity | null,
): ConversationContext {
  if (!messages || messages.length === 0) {
    return getDefaultContext(identity);
  }

  const userMessages = messages.filter((m) => m.role === "user");
  const assistantMessages = messages.filter((m) => m.role === "assistant" && !m.error);
  const latestUser = userMessages[userMessages.length - 1]?.text ?? "";
  const latestAssistant = assistantMessages[assistantMessages.length - 1]?.text ?? "";
  const combinedHistory = messages.map((m) => m.text).join(" \n ");

  const lowerHistory = combinedHistory.toLowerCase();
  const lowerLatestUser = latestUser.toLowerCase();
  const lowerLatestAssistant = latestAssistant.toLowerCase();

  // 1. Topic Identification
  let topic = "General Enterprise Assistant";
  let topicCategory: ConversationContext["topicCategory"] = "general";

  if (
    lowerHistory.includes("invoice") ||
    lowerHistory.includes("overdue") ||
    lowerHistory.includes("budget") ||
    lowerHistory.includes("finance") ||
    lowerHistory.includes("expense") ||
    lowerHistory.includes("payable")
  ) {
    topic = "Financial Invoices & Payables";
    topicCategory = "finance";
  } else if (
    lowerHistory.includes("attendance") ||
    lowerHistory.includes("leave") ||
    lowerHistory.includes("salary") ||
    lowerHistory.includes("headcount") ||
    lowerHistory.includes("handbook") ||
    lowerHistory.includes("employee")
  ) {
    topic = "HR Attendance & People Ops";
    topicCategory = "hr";
  } else if (
    lowerHistory.includes("contract") ||
    lowerHistory.includes("agreement") ||
    lowerHistory.includes("sla") ||
    lowerHistory.includes("acme") ||
    lowerHistory.includes("nda")
  ) {
    topic = "Enterprise Contracts & SLAs";
    topicCategory = "contracts";
  } else if (
    lowerHistory.includes("phoenix") ||
    lowerHistory.includes("sprint") ||
    lowerHistory.includes("project") ||
    lowerHistory.includes("milestone")
  ) {
    topic = "Project Delivery & Milestones";
    topicCategory = "projects";
  } else if (
    lowerHistory.includes("email") ||
    lowerHistory.includes("gmail") ||
    lowerHistory.includes("inbox") ||
    lowerHistory.includes("thread")
  ) {
    topic = "Mailbox & Thread Intelligence";
    topicCategory = "email";
  }

  // 2. Extract Active Filters
  const activeFilters: ContextFilter[] = [];

  // Department filter
  const deptMatch = combinedHistory.match(/\b(HR|Finance|Engineering|Sales|Marketing|IT|Legal|Operations)\b/i);
  if (deptMatch) {
    activeFilters.push({ key: "Department", value: deptMatch[1].toUpperCase() });
  } else if (identity?.department) {
    activeFilters.push({ key: "Department", value: identity.department });
  }

  // Status filter
  if (lowerHistory.includes("overdue")) {
    activeFilters.push({ key: "Status", value: "Overdue" });
  } else if (lowerHistory.includes("active") || lowerHistory.includes("present")) {
    activeFilters.push({ key: "Status", value: "Active" });
  }

  // Timeframe filter
  const timeMatch = combinedHistory.match(/\b(Q[1-4]|202[4-6]|August|September|October|November|December|January|February|March)\b/i);
  if (timeMatch) {
    activeFilters.push({ key: "Period", value: timeMatch[1] });
  }

  // 3. Extract Real Metrics
  const metrics: ContextMetric[] = [];

  // Parse dollar/currency figures from latest assistant response
  const currencyMatches = latestAssistant.match(/(\$|€|£|₹)\s?[\d,]+(\.\d+)?(\s?[MKmk]|\s?million|\s?billion)?/g);
  if (currencyMatches && currencyMatches.length > 0) {
    metrics.push({
      id: "metric-currency",
      label: "Total Value",
      value: currencyMatches[0],
      subtext: "From cited response",
      tone: "primary",
    });
  }

  // Parse percentages
  const percentMatches = latestAssistant.match(/\b\d+(\.\d+)?%/g);
  if (percentMatches && percentMatches.length > 0) {
    metrics.push({
      id: "metric-percent",
      label: "Rate / Variance",
      value: percentMatches[0],
      subtext: "Calculated metric",
      tone: "accent",
    });
  }

  // Total sources cited in conversation
  const uniqueSources = new Set<string>();
  messages.forEach((m) => {
    m.sources?.forEach((s) => uniqueSources.add(s.title || s.id));
  });

  metrics.push({
    id: "metric-sources",
    label: "Sources Cited",
    value: String(uniqueSources.size),
    subtext: uniqueSources.size === 1 ? "Verified document" : "Cross-verified documents",
    tone: uniqueSources.size > 0 ? "success" : "primary",
  });

  metrics.push({
    id: "metric-turns",
    label: "Exchange Turns",
    value: `${userMessages.length}`,
    subtext: "Active session",
    tone: "accent",
  });

  // 4. Extract Relevant Files
  const relevantFiles: string[] = [];
  messages.forEach((m) => {
    m.sources?.forEach((s) => {
      if (s.title && !relevantFiles.includes(s.title)) {
        relevantFiles.push(s.title);
      }
    });
  });

  // 5. Generate Dynamic Contextual Suggestions
  const suggestions = generateSuggestions(topicCategory, lowerLatestUser, lowerLatestAssistant, activeFilters);

  // 6. Generate Smart Contextual Actions
  const availableActions = generateActions(topicCategory, activeFilters);

  return {
    topic,
    topicCategory,
    activeFilters,
    metrics,
    suggestions,
    availableActions,
    relevantFiles,
  };
}

function generateSuggestions(
  category: ConversationContext["topicCategory"],
  latestUserQuery: string,
  latestAnswer: string,
  filters: ContextFilter[],
): ContextSuggestion[] {
  const list: ContextSuggestion[] = [];

  if (category === "finance") {
    if (latestUserQuery.includes("overdue") || latestAnswer.includes("overdue")) {
      list.push(
        { id: "s1", text: "Show overdue breakdown by department", category: "Filter" },
        { id: "s2", text: "Calculate total overdue invoice amount", category: "Calculation" },
        { id: "s3", text: "Generate overdue invoices report in PDF", category: "Report" },
        { id: "s4", text: "Which vendors have outstanding payments?", category: "Analysis" },
      );
    } else {
      list.push(
        { id: "s1", text: "Compare Q1 2026 with prior budget", category: "Comparison" },
        { id: "s2", text: "Show department budgets and managers", category: "Directory" },
        { id: "s3", text: "Summarize travel and expense policy", category: "Policy" },
        { id: "s4", text: "Generate financial summary report in Excel", category: "Report" },
      );
    }
  } else if (category === "hr") {
    if (latestUserQuery.includes("attendance") || latestAnswer.includes("attendance")) {
      list.push(
        { id: "s1", text: "Show only HR department attendance", category: "Filter" },
        { id: "s2", text: "Identify employees with low attendance", category: "Analysis" },
        { id: "s3", text: "Compare with previous month", category: "Comparison" },
        { id: "s4", text: "Generate attendance summary in Excel", category: "Report" },
      );
    } else {
      list.push(
        { id: "s1", text: "What is our leave and vacation policy?", category: "Policy" },
        { id: "s2", text: "What are the healthcare and dental benefits?", category: "Benefits" },
        { id: "s3", text: "Show headcount planning numbers for Q2", category: "Planning" },
        { id: "s4", text: "What is the average salary of employees?", category: "Analysis" },
      );
    }
  } else if (category === "contracts") {
    list.push(
      { id: "s1", text: "What are the customer SLAs and support guarantees?", category: "SLA" },
      { id: "s2", text: "Summarize Acme Corp contract renewal terms", category: "Contract" },
      { id: "s3", text: "List enterprise contracts and annual contract value", category: "Data" },
      { id: "s4", text: "Generate contract renewal schedule in Word", category: "Report" },
    );
  } else if (category === "projects") {
    list.push(
      { id: "s1", text: "What are the deliverables in Sprint 24 for Projects?", category: "Sprint" },
      { id: "s2", text: "What is the status of Project Phoenix?", category: "Status" },
      { id: "s3", text: "Are there any infrastructure blockers?", category: "Blockers" },
      { id: "s4", text: "Generate project milestone report", category: "Report" },
    );
  } else if (category === "email") {
    list.push(
      { id: "s1", text: "Check my Gmail for latest financial updates", category: "Finance" },
      { id: "s2", text: "What emails did Rahul or Priya send regarding Phoenix?", category: "Threads" },
      { id: "s3", text: "Search inbox for contract and SLA notices", category: "Notices" },
      { id: "s4", text: "Summarize unread messages from this week", category: "Summary" },
    );
  } else {
    list.push(
      { id: "s1", text: "Show overdue invoices and vendor payables", category: "Finance" },
      { id: "s2", text: "What are the customer SLAs and support guarantees?", category: "Knowledge" },
      { id: "s3", text: "Summarize employee leave and vacation policies", category: "HR" },
      { id: "s4", text: "What is the status of Project Phoenix?", category: "Projects" },
    );
  }

  return list;
}

function generateActions(
  category: ConversationContext["topicCategory"],
  filters: ContextFilter[],
): ContextAction[] {
  const actions: ContextAction[] = [];

  if (category === "finance") {
    actions.push(
      { id: "a1", label: "Export Invoices", query: "Generate a report on overdue invoices in Excel", tone: "primary" },
      { id: "a2", label: "Filter by Dept", query: "Show invoices broken down by department", tone: "secondary" },
      { id: "a3", label: "Analyze Variance", query: "Analyze financial variance and budget anomalies", tone: "secondary" },
    );
  } else if (category === "hr") {
    actions.push(
      { id: "a1", label: "Generate HR Report", query: "Generate a report on personnel directory in Excel", tone: "primary" },
      { id: "a2", label: "Filter HR Only", query: "Show only HR department details", tone: "secondary" },
      { id: "a3", label: "Summarize Policy", query: "Summarize key employee policy rules", tone: "secondary" },
    );
  } else if (category === "contracts") {
    actions.push(
      { id: "a1", label: "Contract Schedule", query: "Generate a report on contract renewals in Word", tone: "primary" },
      { id: "a2", label: "Review Penalties", query: "What are the SLA failure penalties and credits?", tone: "secondary" },
      { id: "a3", label: "Compare MSAs", query: "Compare standard MSA terms with Acme Corp agreement", tone: "secondary" },
    );
  } else {
    actions.push(
      { id: "a1", label: "Generate Report", query: "Generate an executive summary report in PDF", tone: "primary" },
      { id: "a2", label: "Search Web", query: "Search the web for industry market benchmarks", tone: "secondary" },
      { id: "a3", label: "Deep Dive", query: "Explain in detail with citations and breakdown", tone: "secondary" },
    );
  }

  return actions;
}

function getDefaultContext(identity?: UserIdentity | null): ConversationContext {
  return {
    topic: "Enterprise AI Workspace",
    topicCategory: "general",
    activeFilters: identity?.department ? [{ key: "Department", value: identity.department }] : [],
    metrics: [
      { id: "m-vaults", label: "Knowledge Vaults", value: "6 Vaults", subtext: "Indexed & authorized", tone: "primary" },
      { id: "m-role", label: "Clearance Level", value: identity?.roles[0] || "Authorized", subtext: "Strict RBAC", tone: "accent" },
      { id: "m-data", label: "RAG Engine", value: "Active", subtext: "Hybrid vector & BM25", tone: "success" },
    ],
    suggestions: [
      { id: "s1", text: "Show overdue invoices and vendor payables", category: "Finance" },
      { id: "s2", text: "What are the customer SLAs and support guarantees?", category: "Knowledge" },
      { id: "s3", text: "Summarize employee leave and vacation policies", category: "HR" },
      { id: "s4", text: "What is the status of Project Phoenix in Projects vault?", category: "Projects" },
    ],
    availableActions: [
      { id: "a1", label: "Explore Vaults", query: "Show me all company files and document vaults", tone: "primary" },
      { id: "a2", label: "Overdue Invoices", query: "Show overdue invoices", tone: "secondary" },
      { id: "a3", label: "Search Mailbox", query: "Check my Gmail for latest updates", tone: "secondary" },
    ],
    relevantFiles: [],
  };
}
