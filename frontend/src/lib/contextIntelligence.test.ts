import { describe, expect, it } from "vitest";
import { extractConversationContext } from "./contextIntelligence";
import type { Message } from "../types";

describe("contextIntelligence", () => {
  it("provides default context when messages are empty", () => {
    const ctx = extractConversationContext([]);
    expect(ctx.topic).toBe("Enterprise AI Workspace");
    expect(ctx.metrics.length).toBeGreaterThan(0);
    expect(ctx.suggestions.length).toBeGreaterThan(0);
  });

  it("detects finance topic and extracts currency figures and filters", () => {
    const messages: Message[] = [
      { id: "1", role: "user", text: "Show overdue invoices for Finance department", createdAt: 1000 },
      { id: "2", role: "assistant", text: "Found 4 overdue invoices totaling $120,450.00 across vendors.", createdAt: 2000 },
    ];
    const ctx = extractConversationContext(messages);
    expect(ctx.topicCategory).toBe("finance");
    expect(ctx.activeFilters.some((f) => f.key === "Department" && f.value === "FINANCE")).toBe(true);
    expect(ctx.activeFilters.some((f) => f.key === "Status" && f.value === "Overdue")).toBe(true);
    expect(ctx.metrics.some((m) => m.value.includes("$120,450"))).toBe(true);
    expect(ctx.suggestions.some((s) => s.text.toLowerCase().includes("overdue") || s.text.toLowerCase().includes("report"))).toBe(true);
  });

  it("detects HR attendance topic and generates appropriate suggestions", () => {
    const messages: Message[] = [
      { id: "1", role: "user", text: "Show employee attendance for September", createdAt: 1000 },
      { id: "2", role: "assistant", text: "Employee attendance rate was 94.2% in September.", createdAt: 2000 },
    ];
    const ctx = extractConversationContext(messages);
    expect(ctx.topicCategory).toBe("hr");
    expect(ctx.activeFilters.some((f) => f.key === "Period" && f.value === "September")).toBe(true);
    expect(ctx.metrics.some((m) => m.value === "94.2%")).toBe(true);
    expect(ctx.suggestions.some((s) => s.text.toLowerCase().includes("attendance") || s.text.toLowerCase().includes("hr"))).toBe(true);
  });
});
