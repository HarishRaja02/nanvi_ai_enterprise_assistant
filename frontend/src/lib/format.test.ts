import { describe, expect, it } from "vitest";
import { conversationTitle, groupByRecency, humanize, initials } from "./format";

describe("format helpers", () => {
  it("initials", () => {
    expect(initials("Arjun Mehta")).toBe("AM");
    expect(initials("  ")).toBe("U");
    expect(initials("cher")).toBe("C");
  });
  it("humanize backend capability names", () => {
    expect(humanize("database_query")).toBe("Database query");
    expect(humanize("")).toBe("");
  });
  it("conversation title falls back to a short id", () => {
    expect(conversationTitle({ conversation_id: "abcdef123456", title: "  " })).toBe("Conversation abcdef12");
    expect(conversationTitle({ conversation_id: "x", title: "Budget" })).toBe("Budget");
  });
  it("groups conversations by recency; undated go to Earlier", () => {
    const now = new Date(2026, 8, 21, 12);
    const at = (d: number) => new Date(2026, 8, 21 - d, 9).toISOString();
    const groups = groupByRecency([
      { conversation_id: "old", updated_at: at(30) },
      { conversation_id: "today", updated_at: at(0) },
      { conversation_id: "week", updated_at: at(3) },
      { conversation_id: "undated" },
    ], now);
    expect(groups.map((g) => [g.label, g.items.map((i) => i.conversation_id)])).toEqual([
      ["Today", ["today"]],
      ["Previous 7 days", ["week"]],
      ["Earlier", ["old", "undated"]],
    ]);
  });
});
