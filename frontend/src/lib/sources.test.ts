import { describe, expect, it } from "vitest";
import type { ChatSource } from "../api";
import { toSourceView } from "./sources";

const src = (over: Partial<ChatSource>): ChatSource => ({ reference_id: "r1", source_type: "file", display_name: "x", ...over });

describe("toSourceView", () => {
  it("detects format from file extension", () => {
    expect(toSourceView(src({ title: "Policy.PDF" })).format).toBe("PDF");
    expect(toSourceView(src({ title: "Budget.xlsx" })).format).toBe("XLSX");
    expect(toSourceView(src({ title: "Handbook.docx" })).format).toBe("DOCX");
    expect(toSourceView(src({ title: "rows.csv" })).format).toBe("CSV");
  });
  it("uses source type for email and database", () => {
    expect(toSourceView(src({ source_type: "email", title: "Re: plan" })).format).toBe("MAIL");
    expect(toSourceView(src({ source_type: "database", title: "public.invoices" })).format).toBe("SQL");
  });
  it("falls back to mime type, then page/sheet hints, then a neutral FILE", () => {
    expect(toSourceView(src({ title: "download", mime_type: "application/pdf" })).format).toBe("PDF");
    expect(toSourceView(src({ title: "a", sheet: "Summary" })).format).toBe("XLSX");
    expect(toSourceView(src({ title: "a", page: 3 })).format).toBe("PDF");
    expect(toSourceView(src({ title: "unknown" })).format).toBe("FILE");
  });
  it("keeps sheet and page (sheet was silently dropped before)", () => {
    const v = toSourceView(src({ title: "Q1.xlsx", sheet: "Summary", page: 2 }));
    expect(v.sheet).toBe("Summary");
    expect(v.page).toBe(2);
  });
});
