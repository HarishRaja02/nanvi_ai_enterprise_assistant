import { useMemo, useState } from "react";
import { renderMarkdown } from "../../lib/markdown";
import { copyText } from "../../lib/clipboard";
import { useToast } from "../ui/Toast";
import { InteractiveTable, type TableMetadata } from "./InteractiveTable";

type ContentSegment =
  | { type: "markdown"; html: string }
  | { type: "table"; headers: string[]; rows: string[][]; metadata?: TableMetadata }
  | { type: "document"; document: DocumentExcerptData };

type DocumentExcerptData = {
  folder?: string;
  filename: string;
  location?: string;
  content: string;
};

type DocumentContentItem =
  | { type: "field"; label: string; value: string }
  | { type: "heading"; text: string }
  | { type: "text"; text: string };

function parseRow(line: string): string[] {
  let trimmed = line.trim();
  if (trimmed.startsWith("|") && trimmed.endsWith("|") && trimmed.length > 1) {
    trimmed = trimmed.substring(1, trimmed.length - 1);
  } else if (trimmed.startsWith("|")) {
    trimmed = trimmed.substring(1);
  } else if (trimmed.endsWith("|")) {
    trimmed = trimmed.substring(0, trimmed.length - 1);
  }
  return trimmed.split("|").map((c) => c.trim());
}

function isSeparatorRow(line: string): boolean {
  return /^\|?(\s*:?-{2,}:?\s*\|?)+$/.test(line.trim());
}

const FILE_HEADER_REGEX = /^\[(?:(.*?)\s*\/\s*)?(.+?\.[a-z0-9]+)(?:\s*\((?:Sheet:\s*)?([^\)]+)\))?\]$/i;
const SHEET_HEADER_REGEX = /^\[Sheet(?::|\s+)\s*([^\]]+)\]$/i;
const NUMBER_TOKEN_REGEX = /(\b[A-Z]{2,}(?:-[A-Z0-9]+)*-\d[A-Z0-9-]*\b|(?:₹|INR|USD|EUR|GBP|\$|€|£)\s*[\d,]+(?:\.\d+)?(?:\s*(?:million|billion|crore|lakh|[kmb]))?|\b\d[\d,]*(?:\.\d+)?%?)/gi;
const NUMBER_TOKEN_CHECK_REGEX = new RegExp(`^(?:${NUMBER_TOKEN_REGEX.source.slice(1, -1)})$`, "i");

function parseDocumentContent(content: string): { title?: string; items: DocumentContentItem[] } {
  const lines = content.split("\n").map((line) => line.trim()).filter(Boolean);
  let title: string | undefined;
  if (lines.length > 0 && lines[0].length <= 120 && !/^[^:]{2,48}:\s*.+$/.test(lines[0])) {
    title = lines.shift();
  }

  const items: DocumentContentItem[] = [];
  for (const line of lines) {
    const field = line.match(/^([^:]{2,48}):\s*(.+)$/);
    if (field) {
      items.push({ type: "field", label: field[1].trim(), value: field[2].trim() });
    } else if (line.length <= 36 && !/[.!?]$/.test(line)) {
      items.push({ type: "heading", text: line });
    } else {
      items.push({ type: "text", text: line });
    }
  }

  return { title, items };
}

function HighlightedText({ text }: { text: string }) {
  const parts = text.split(NUMBER_TOKEN_REGEX);
  return <>{parts.map((part, index) => NUMBER_TOKEN_CHECK_REGEX.test(part)
    ? <strong className="document-number" key={index}>{part}</strong>
    : part)}</>;
}

function DocumentResultCard({ document }: { document: DocumentExcerptData }) {
  const [expanded, setExpanded] = useState(false);
  const { title, items } = parseDocumentContent(document.content);
  const metadata = [document.folder, document.location].filter(Boolean).join(" · ");
  const previewIndexes = new Set(items.slice(0, 5).map((_, index) => index));
  items.forEach((item, index) => {
    if (item.type === "field" && /(value|amount|progress|status|budget|cost|total|revenue|date|percent|rate|balance)/i.test(item.label)) {
      previewIndexes.add(index);
    }
  });
  const visibleItems = expanded ? items : items.filter((_, index) => previewIndexes.has(index));
  const hasToggle = previewIndexes.size < items.length || items.some((item) => item.type === "text" && item.text.length > 280);

  return (
    <article className="document-result-card">
      <header className="document-result-header">
        <div className="document-result-title-wrap">
          <span className="document-result-filename">{document.filename}</span>
          {metadata && <span className="document-result-meta">{metadata}</span>}
        </div>
      </header>

      {title && <h4 className="document-result-heading">{title}</h4>}

      <div className="document-result-content">
        {visibleItems.map((item, index) => {
          if (item.type === "field") {
            return (
              <div className="document-result-field" key={`${item.label}-${index}`}>
                <span className="document-result-label">{item.label}</span>
                <strong className="document-result-value"><HighlightedText text={item.value} /></strong>
              </div>
            );
          }
          if (item.type === "heading") {
            return <h5 className="document-result-subheading" key={`${item.text}-${index}`}>{item.text}</h5>;
          }
          const text = !expanded && item.text.length > 280 ? `${item.text.slice(0, 280).trimEnd()}…` : item.text;
          return <p className="document-result-text" key={`${item.text}-${index}`}><HighlightedText text={text} /></p>;
        })}
      </div>

      {hasToggle && (
        <button
          type="button"
          className="document-result-toggle"
          aria-expanded={expanded}
          onClick={() => setExpanded((value) => !value)}
        >
          {expanded ? "Show less" : "Show full details"}
        </button>
      )}
    </article>
  );
}

interface ParsedQueryResult {
  headers: string[];
  rows: string[][];
  metadata: TableMetadata;
  fullMatch: string;
  startIndex: number;
}

function formatHeaderName(header: string): string {
  const clean = header.trim().replace(/^['"]+|['"]+$/g, "");
  if (!clean.includes("_")) return clean;
  return clean
    .split("_")
    .map((word) => {
      if (word.toLowerCase() === "id") return "ID";
      if (word.toLowerCase() === "sql") return "SQL";
      return word.charAt(0).toUpperCase() + word.slice(1);
    })
    .join(" ");
}

function findQueryResultInText(text: string): ParsedQueryResult | null {
  const queryResultIdx = text.indexOf("QueryResult(");
  if (queryResultIdx === -1) return null;

  // Match from QueryResult( to its balanced closing parenthesis
  let depth = 0;
  let endIndex = -1;
  for (let i = queryResultIdx; i < text.length; i++) {
    if (text[i] === "(") {
      depth++;
    } else if (text[i] === ")") {
      depth--;
      if (depth === 0) {
        endIndex = i + 1;
        break;
      }
    }
  }

  if (endIndex === -1) return null;
  const rawBlock = text.substring(queryResultIdx, endIndex);

  // Extract columns=(...)
  const colMatch = rawBlock.match(/columns\s*=\s*\(([\s\S]*?)\)\s*,/i);
  if (!colMatch) return null;

  const colStr = colMatch[1];
  const headerMatches = Array.from(colStr.matchAll(/(?:'([^']*)'|"([^"]*)")/g));
  const headers = headerMatches
    .map((m) => (m[1] ?? m[2] ?? "").trim())
    .filter(Boolean)
    .map(formatHeaderName);
  if (headers.length === 0) return null;

  // Extract rows=(...)
  const rowsIdx = rawBlock.indexOf("rows=(");
  if (rowsIdx === -1) return null;

  let rDepth = 0;
  let rowsEnd = -1;
  const rowsStart = rowsIdx + "rows=".length;
  for (let j = rowsStart; j < rawBlock.length; j++) {
    if (rawBlock[j] === "(") {
      rDepth++;
    } else if (rawBlock[j] === ")") {
      rDepth--;
      if (rDepth === 0) {
        rowsEnd = j;
        break;
      }
    }
  }
  if (rowsEnd === -1) return null;

  const rowsStr = rawBlock.substring(rowsStart + 1, rowsEnd);
  const isTruncated = /truncated\s*=\s*True/i.test(rawBlock);

  // Parse each inner row tuple: (..., ...)
  const rows: string[][] = [];
  let innerDepth = 0;
  let curRowStart = -1;

  for (let k = 0; k < rowsStr.length; k++) {
    const char = rowsStr[k];
    if (char === "(") {
      if (innerDepth === 0) {
        curRowStart = k + 1;
      }
      innerDepth++;
    } else if (char === ")") {
      innerDepth--;
      if (innerDepth === 0 && curRowStart !== -1) {
        const rowTuple = rowsStr.substring(curRowStart, k);
        const items: string[] = [];
        const itemRegex = /(?:Decimal\s*\(\s*['"]?([^'"]+)['"]?\s*\)|'([^']*)'|"([^"]*)"|(\b(?:None|True|False|-?\d+(?:\.\d+)?)\b))/g;
        let itemMatch: RegExpExecArray | null;
        while ((itemMatch = itemRegex.exec(rowTuple)) !== null) {
          const val = itemMatch[1] ?? itemMatch[2] ?? itemMatch[3] ?? (itemMatch[4] === "None" ? "—" : itemMatch[4]) ?? "";
          items.push(val);
        }
        if (items.length > 0) {
          rows.push(items);
        }
        curRowStart = -1;
      }
    }
  }

  if (rows.length === 0) return null;

  return {
    headers,
    rows,
    metadata: {
      filename: "Database Records",
      folder: "SQL Query",
      isTruncated,
    },
    fullMatch: rawBlock,
    startIndex: queryResultIdx,
  };
}

function parseMarkdownSegments(text: string): ContentSegment[] {
  const lines = text.split("\n");
  const segments: ContentSegment[] = [];
  let proseBuffer: string[] = [];
  let inCodeBlock = false;
  let i = 0;

  const flushProse = () => {
    const proseText = proseBuffer.join("\n").trim();
    if (proseText) {
      segments.push({ type: "markdown", html: renderMarkdown(proseText) });
    }
    proseBuffer = [];
  };

  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trim();

    // Check code blocks
    if (trimmed.startsWith("```")) {
      inCodeBlock = !inCodeBlock;
      proseBuffer.push(line);
      i++;
      continue;
    }

    if (inCodeBlock) {
      proseBuffer.push(line);
      i++;
      continue;
    }

    // 1. Check for file / sheet header annotation right above a table
    const cleanLine = trimmed.replace(/^#+\s*/, "");
    const fileMatch = FILE_HEADER_REGEX.exec(cleanLine);
    const sheetMatch = !fileMatch ? SHEET_HEADER_REGEX.exec(cleanLine) : null;

    if (fileMatch || sheetMatch) {
      // Lookahead: is the next non-empty line a table row?
      let nextIdx = i + 1;
      while (nextIdx < lines.length && !lines[nextIdx].trim()) {
        nextIdx++;
      }

      if (
        nextIdx < lines.length &&
        lines[nextIdx].includes("|") &&
        !isSeparatorRow(lines[nextIdx])
      ) {
        flushProse();

        const metadata: TableMetadata = {
          folder: fileMatch ? fileMatch[1]?.trim() : undefined,
          filename: fileMatch ? fileMatch[2]?.trim() : undefined,
          sheet: fileMatch ? fileMatch[3]?.trim() : sheetMatch ? sheetMatch[1]?.trim() : undefined,
          isTruncated: false,
        };

        i = nextIdx;
        const tableLines: string[] = [];
        while (i < lines.length) {
          const tLine = lines[i].trim();
          if (!tLine) {
            break;
          }
          if (tLine.includes("|") || isSeparatorRow(tLine)) {
            tableLines.push(tLine);
            i++;
          } else if (tLine.includes("[truncated for brevity]") || tLine.startsWith("...")) {
            metadata.isTruncated = true;
            i++;
            break;
          } else {
            break;
          }
        }

        if (tableLines.length >= 2 || (tableLines.length === 1 && metadata.filename)) {
          const headers = parseRow(tableLines[0]);
          let rowStart = 1;
          if (tableLines.length > 1 && isSeparatorRow(tableLines[1])) {
            rowStart = 2;
          }

          const rows: string[][] = [];
          for (let r = rowStart; r < tableLines.length; r++) {
            let rowLine = tableLines[r];
            if (rowLine.includes("[truncated for brevity]")) {
              metadata.isTruncated = true;
              rowLine = rowLine.replace(/\.\.\.\s*\[truncated for brevity\]/i, "").trim();
            }
            const cells = parseRow(rowLine);
            if (cells.some((c) => c.length > 0)) {
              rows.push(cells);
            }
          }

          segments.push({ type: "table", headers, rows, metadata });
          continue;
        } else {
          for (const tl of tableLines) {
            proseBuffer.push(tl);
          }
          continue;
        }
      }
    }

    // Turn retrieved file annotations into separate, readable document cards.
    if (fileMatch) {
      flushProse();
      let end = i + 1;
      while (end < lines.length) {
        const nextLine = lines[end].trim();
        if (FILE_HEADER_REGEX.test(nextLine) || /^#{1,4}\s/.test(nextLine)) break;
        end++;
      }

      segments.push({
        type: "document",
        document: {
          folder: fileMatch[1]?.trim(),
          filename: fileMatch[2].trim(),
          location: fileMatch[3]?.trim(),
          content: lines.slice(i + 1, end).join("\n").trim(),
        },
      });
      i = end;
      continue;
    }

    // 2. Check for standard markdown or pipe-separated table without file header
    if (trimmed.includes("|") && !isSeparatorRow(trimmed)) {
      const nextLine = i + 1 < lines.length ? lines[i + 1].trim() : "";
      const isNextSep = isSeparatorRow(nextLine);
      const isNextPipe = nextLine.includes("|");

      if (isNextSep || isNextPipe) {
        flushProse();

        const metadata: TableMetadata = { isTruncated: false };
        const tableLines: string[] = [];
        while (i < lines.length) {
          const tLine = lines[i].trim();
          if (!tLine) break;
          if (tLine.includes("|") || isSeparatorRow(tLine)) {
            tableLines.push(tLine);
            i++;
          } else if (tLine.includes("[truncated for brevity]") || tLine.startsWith("...")) {
            metadata.isTruncated = true;
            i++;
            break;
          } else {
            break;
          }
        }

        if (tableLines.length >= 2) {
          const headers = parseRow(tableLines[0]);
          let rowStart = 1;
          if (isSeparatorRow(tableLines[1])) {
            rowStart = 2;
          }

          const rows: string[][] = [];
          for (let r = rowStart; r < tableLines.length; r++) {
            let rowLine = tableLines[r];
            if (rowLine.includes("[truncated for brevity]")) {
              metadata.isTruncated = true;
              rowLine = rowLine.replace(/\.\.\.\s*\[truncated for brevity\]/i, "").trim();
            }
            const cells = parseRow(rowLine);
            if (cells.some((c) => c.length > 0)) {
              rows.push(cells);
            }
          }

          if (headers.length >= 2 && rows.length >= 1) {
            segments.push({ type: "table", headers, rows, metadata });
            continue;
          }
        }

        for (const tl of tableLines) {
          proseBuffer.push(tl);
        }
        continue;
      }
    }

    proseBuffer.push(line);
    i++;
  }

  flushProse();

  return segments.length > 0 ? segments : [{ type: "markdown", html: renderMarkdown(text) }];
}

function parseSegments(text: string): ContentSegment[] {
  if (text.includes("QueryResult(")) {
    const segments: ContentSegment[] = [];
    let remaining = text;

    while (remaining.includes("QueryResult(")) {
      const parsed = findQueryResultInText(remaining);
      if (!parsed) break;

      const before = remaining.substring(0, parsed.startIndex).trim();
      if (before) {
        segments.push(...parseMarkdownSegments(before));
      }

      segments.push({
        type: "table",
        headers: parsed.headers,
        rows: parsed.rows,
        metadata: parsed.metadata,
      });

      remaining = remaining.substring(parsed.startIndex + parsed.fullMatch.length).trim();
    }

    if (remaining) {
      segments.push(...parseMarkdownSegments(remaining));
    }

    if (segments.length > 0) {
      return segments;
    }
  }

  return parseMarkdownSegments(text);
}

/** Renders sanitised markdown with interactive data tables and code-block copy buttons. */
export function MarkdownContent({ text }: { text: string }) {
  const displayText = useMemo(
    () => text
      .replace(/^I found relevant information across \*\*multiple sources\*\*:\s*$/mi, "Here’s what I found:")
      .replace(/^###\s*.*Local Files\s*\/\s*Documents\s*$/gmi, "### Company documents"),
    [text],
  );
  const segments = useMemo(() => parseSegments(displayText), [displayText]);
  const notify = useToast();

  const onCodeCopyClick = async (event: React.MouseEvent<HTMLDivElement>) => {
    const button = (event.target as HTMLElement).closest<HTMLButtonElement>(".code-copy");
    if (!button) return;
    const code = button.closest(".code-block")?.querySelector("pre")?.textContent ?? "";
    if (await copyText(code)) {
      button.textContent = "Copied";
      window.setTimeout(() => {
        button.textContent = "Copy";
      }, 1500);
    } else {
      notify("Couldn't copy automatically. Select the code and copy it manually.", "danger");
    }
  };

  return (
    <div className="prose-wrapper" onClick={onCodeCopyClick}>
      {segments.map((seg, idx) => {
        if (seg.type === "table") {
          return (
            <InteractiveTable
              key={idx}
              headers={seg.headers}
              rows={seg.rows}
              metadata={seg.metadata}
            />
          );
        }
        if (seg.type === "document") {
          return <DocumentResultCard key={idx} document={seg.document} />;
        }
        return (
          <div
            key={idx}
            className="prose"
            dangerouslySetInnerHTML={{ __html: seg.html }}
          />
        );
      })}
    </div>
  );
}
