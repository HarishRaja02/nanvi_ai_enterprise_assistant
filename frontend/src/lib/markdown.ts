import { Marked } from "marked";
import DOMPurify from "dompurify";

/**
 * Model output is untrusted: it can be steered by document or email content (prompt injection).
 * Rendering therefore runs through a strict allow-list. Notably we drop:
 *   - images/media  → a markdown image is a zero-click data-exfiltration channel (?q=<secret>)
 *   - form controls → an answer must not be able to draw a fake login form
 *   - style attrs   → no overlaying the real UI (UI redress)
 * and force every link to open safely in a new tab.
 */
const markdown = new Marked({ gfm: true, breaks: true });

const PURIFY_CONFIG = {
  USE_PROFILES: { html: true },
  FORBID_TAGS: [
    "style", "form", "input", "button", "select", "textarea", "option",
    "img", "picture", "source", "video", "audio", "track", "iframe", "frame", "object", "embed",
    "link", "meta", "base", "svg", "math",
  ],
  FORBID_ATTR: ["style", "srcset", "src", "action", "formaction"],
};

let hooked = false;
function ensureHooks() {
  if (hooked) return;
  hooked = true;
  DOMPurify.addHook("afterSanitizeAttributes", (node) => {
    if (node.tagName === "A") {
      node.setAttribute("target", "_blank");
      node.setAttribute("rel", "noopener noreferrer");
    }
  });
}

function escapeHtml(text: string): string {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

/**
 * Presentation wrappers are added AFTER sanitising, from static strings only:
 * scrollable tables (keyboard-focusable) and code blocks with a language label and copy button.
 */
function decorate(safeHtml: string): string {
  return safeHtml
    .replace(/<table(\s|>)/g, '<div class="table-scroll" role="region" aria-label="Table" tabindex="0"><table$1')
    .replace(/<\/table>/g, "</table></div>")
    .replace(
      /<pre>(<code(?: class="language-([\w+#.-]+)")?>)/g,
      (_m, codeOpen: string, lang?: string) =>
        `<div class="code-block"><div class="code-head"><span class="code-lang">${lang ?? "text"}</span><button type="button" class="code-copy" aria-label="Copy code">Copy</button></div><pre>${codeOpen}`,
    )
    .replace(/<\/pre>/g, "</pre></div>");
}

export function renderMarkdown(text: string): string {
  ensureHooks();
  let raw: string;
  try {
    raw = markdown.parse(text, { async: false }) as string;
  } catch {
    return `<p>${escapeHtml(text)}</p>`;
  }
  const safe = DOMPurify.sanitize(raw, PURIFY_CONFIG) as unknown as string;
  return decorate(safe);
}

export function renderInlineMarkdown(text: string): string {
  ensureHooks();
  let raw: string;
  try {
    raw = (markdown.parseInline(text) as string) ?? "";
  } catch {
    raw = escapeHtml(text);
  }
  const safe = DOMPurify.sanitize(raw, PURIFY_CONFIG) as unknown as string;
  return safe;
}

