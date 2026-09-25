import { useMemo } from "react";
import { renderMarkdown } from "../../lib/markdown";
import { copyText } from "../../lib/clipboard";
import { useToast } from "../ui/Toast";
import { InteractiveTable, type TableMetadata } from "./InteractiveTable";

type ContentSegment =
  | { type: "markdown"; html: string }
  | { type: "table"; headers: string[]; rows: string[][]; metadata?: TableMetadata };

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

const FILE_HEADER_REGEX = /^\[(?:([a-zA-Z0-9_\-\s]+)\s*\/\s*)?([a-zA-Z0-9_\-\.\s]+\.[a-zA-Z0-9]+)(?:\s*\((?:Sheet:\s*)?([^\)]+)\))?\]$/i;
const SHEET_HEADER_REGEX = /^\[Sheet(?::|\s+)\s*([^\]]+)\]$/i;

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
  const segments = useMemo(() => parseSegments(text), [text]);
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
