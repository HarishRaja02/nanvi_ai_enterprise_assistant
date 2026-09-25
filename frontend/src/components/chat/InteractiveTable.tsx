import { useState, useMemo } from "react";
import {
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  Copy,
  Search,
  Check,
  FileSpreadsheet,
  Mail,
  Info,
} from "lucide-react";
import { copyText } from "../../lib/clipboard";
import { renderInlineMarkdown } from "../../lib/markdown";
import { useToast } from "../ui/Toast";

export interface TableMetadata {
  filename?: string;
  sheet?: string;
  folder?: string;
  isTruncated?: boolean;
}

interface Props {
  headers: string[];
  rows: string[][];
  metadata?: TableMetadata;
}

function cleanText(text: string): string {
  return text.trim();
}

function renderCellContent(cell: string, _colIndex: number, _headerName: string) {
  const trimmed = cleanText(cell);
  if (!trimmed || trimmed === "None" || trimmed === "null" || trimmed === "—") {
    return <span className="text-muted">—</span>;
  }

  // 1. Email check
  if (/^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$/.test(trimmed)) {
    return (
      <a href={`mailto:${trimmed}`} className="table-email-link" title={`Send email to ${trimmed}`}>
        <Mail size={12} className="email-icon" aria-hidden="true" />
        <span>{trimmed}</span>
      </a>
    );
  }

  // 2. ID / Code check (e.g. TX-01-0000, ACC-4122, REQ-101, C-001-000, EMP-402, INV-0012, CTR-01-005)
  if (/^[A-Za-z0-9]{1,6}(?:-[A-Za-z0-9]{2,8})+$/.test(trimmed)) {
    return <code className="table-id-chip">{trimmed}</code>;
  }

  // 3. Priority / Status / Type badges (only if plain single/two-word token without prose)
  const lower = trimmed.toLowerCase().replace(/\*\*/g, "").replace(/\*/g, "").trim();
  if (lower === "critical" || lower === "urgent") {
    return <span className="table-badge badge-critical">{trimmed.replace(/\*\*/g, "")}</span>;
  }
  if (lower === "high") {
    return <span className="table-badge badge-high">{trimmed.replace(/\*\*/g, "")}</span>;
  }
  if (lower === "medium") {
    return <span className="table-badge badge-medium">{trimmed.replace(/\*\*/g, "")}</span>;
  }
  if (lower === "low") {
    return <span className="table-badge badge-low">{trimmed.replace(/\*\*/g, "")}</span>;
  }
  if (["active", "open", "paid", "completed", "approved", "success"].includes(lower)) {
    return <span className="table-badge badge-success">{trimmed.replace(/\*\*/g, "")}</span>;
  }
  if (["pending", "in review", "draft", "in progress", "processing"].includes(lower)) {
    return <span className="table-badge badge-warning">{trimmed.replace(/\*\*/g, "")}</span>;
  }
  if (["overdue", "rejected", "closed", "terminated", "cancelled", "failed"].includes(lower)) {
    return <span className="table-badge badge-critical">{trimmed.replace(/\*\*/g, "")}</span>;
  }
  if (lower === "credit") {
    return <span className="table-badge badge-credit">{trimmed.replace(/\*\*/g, "")}</span>;
  }
  if (lower === "debit") {
    return <span className="table-badge badge-debit">{trimmed.replace(/\*\*/g, "")}</span>;
  }
  if (["inr", "usd", "eur", "gbp", "cad", "aud", "sgd", "jpy", "chf"].includes(lower)) {
    return <span className="table-currency-code">{trimmed.toUpperCase()}</span>;
  }

  // 4. Currency / Salary amounts (e.g. 175,000 - 210,000, $130,000 + OTE, ₹14,549.73)
  if (
    /^[$₹€£]\s*[\d,]+(?:\.\d+)?/.test(trimmed) ||
    trimmed.includes("+ OTE") ||
    /^\d{2,3},\d{3}\s*-\s*\d{2,3},\d{3}/.test(trimmed)
  ) {
    return <span className="table-currency-cell">{trimmed.replace(/\*\*/g, "")}</span>;
  }

  // Pure numeric values (e.g. 14549.73 or 34053.54)
  if (/^-?\d+(?:\.\d+)?$/.test(trimmed)) {
    const num = Number(trimmed);
    const formatted = num.toLocaleString(undefined, {
      minimumFractionDigits: trimmed.includes(".") ? 2 : 0,
      maximumFractionDigits: trimmed.includes(".") ? 2 : 0,
    });
    return <span className="table-number-cell">{formatted}</span>;
  }

  // 5. Date check (YYYY-MM-DD)
  if (/^\d{4}-\d{2}-\d{2}$/.test(trimmed)) {
    return <span className="table-date-cell">{trimmed}</span>;
  }

  // 6. Inline markdown for text cells (renders bold, inline code, links with no raw asterisks)
  const html = renderInlineMarkdown(trimmed);
  return <span className="table-cell-prose" dangerouslySetInnerHTML={{ __html: html }} />;
}


export function InteractiveTable({ headers, rows, metadata }: Props) {
  const notify = useToast();
  const [sortCol, setSortCol] = useState<number | null>(null);
  const [sortAsc, setSortAsc] = useState<boolean>(true);
  const [filterQuery, setFilterQuery] = useState("");
  const [copied, setCopied] = useState(false);

  // Filter rows based on search
  const filteredRows = useMemo(() => {
    if (!filterQuery.trim()) return rows;
    const q = filterQuery.toLowerCase();
    return rows.filter((row) => row.some((cell) => cell.toLowerCase().includes(q)));
  }, [rows, filterQuery]);

  // Sort rows
  const sortedRows = useMemo(() => {
    if (sortCol === null) return filteredRows;
    return [...filteredRows].sort((a, b) => {
      const cellA = a[sortCol] ?? "";
      const cellB = b[sortCol] ?? "";
      // Check if numeric
      const numA = Number(cellA.replace(/[^0-9.-]+/g, ""));
      const numB = Number(cellB.replace(/[^0-9.-]+/g, ""));
      if (!Number.isNaN(numA) && !Number.isNaN(numB) && cellA.match(/\d/) && cellB.match(/\d/)) {
        return sortAsc ? numA - numB : numB - numA;
      }
      return sortAsc ? cellA.localeCompare(cellB) : cellB.localeCompare(cellA);
    });
  }, [filteredRows, sortCol, sortAsc]);

  const toggleSort = (colIndex: number) => {
    if (sortCol === colIndex) {
      if (sortAsc) {
        setSortAsc(false);
      } else {
        setSortCol(null);
        setSortAsc(true);
      }
    } else {
      setSortCol(colIndex);
      setSortAsc(true);
    }
  };

  const handleCopyCsv = async () => {
    const csvContent = [
      headers.map((h) => `"${h.replace(/"/g, '""')}"`).join(","),
      ...sortedRows.map((r) => r.map((c) => `"${c.replace(/"/g, '""')}"`).join(",")),
    ].join("\n");

    const ok = await copyText(csvContent);
    if (ok) {
      setCopied(true);
      notify("Table copied as CSV.", "success");
      setTimeout(() => setCopied(false), 2000);
    } else {
      notify("Couldn't copy table.", "danger");
    }
  };

  const hasFileMeta = Boolean(
    metadata && (metadata.filename || metadata.sheet || metadata.folder)
  );

  return (
    <div className="interactive-table-container">
      {/* Table File / Sheet Header Banner */}
      {hasFileMeta && (
        <div className="table-file-banner">
          <div className="table-file-info">
            <div className="table-file-icon-box" aria-hidden="true">
              <FileSpreadsheet size={15} className="table-file-icon" />
            </div>
            {metadata?.folder && (
              <span className="table-folder-chip">{metadata.folder}</span>
            )}
            {metadata?.filename && (
              <span className="table-filename">{metadata.filename}</span>
            )}
            {metadata?.sheet && (
              <span className="table-sheet-badge">Sheet: {metadata.sheet}</span>
            )}
          </div>
        </div>
      )}

      {/* Table Toolbar */}
      <div className="table-toolbar">
        <div className="table-meta">
          <span className="table-rows-badge">
            {sortedRows.length} {sortedRows.length === 1 ? "record" : "records"}
            {filterQuery && ` (filtered from ${rows.length})`}
          </span>
        </div>

        <div className="table-actions">
          {rows.length > 2 && (
            <div className="table-search-box">
              <Search size={13} className="search-icon" aria-hidden="true" />
              <input
                type="text"
                className="table-search-input"
                placeholder="Filter table…"
                value={filterQuery}
                onChange={(e) => setFilterQuery(e.target.value)}
                aria-label="Filter table records"
              />
            </div>
          )}

          <button
            type="button"
            className="table-btn"
            onClick={handleCopyCsv}
            title="Copy table contents as CSV"
            aria-label="Copy table as CSV"
          >
            {copied ? <Check size={13} className="text-success" /> : <Copy size={13} />}
            <span>{copied ? "Copied" : "CSV"}</span>
          </button>
        </div>
      </div>

      {/* Scrollable Table Area */}
      <div className="table-scroll" role="region" aria-label="Interactive Table" tabIndex={0}>
        <table className="interactive-table">
          <thead>
            <tr>
              {headers.map((h, i) => {
                const headerText = cleanText(h).replace(/\*\*/g, "").replace(/^\*+|\*+$/g, "").trim();
                return (
                  <th key={i} scope="col">
                    <button
                      type="button"
                      className="th-sort-btn"
                      onClick={() => toggleSort(i)}
                      title={`Sort by ${headerText}`}
                    >
                      <span>{headerText}</span>
                      {sortCol === i ? (
                        sortAsc ? (
                          <ArrowUp size={12} className="sort-icon is-active" />
                        ) : (
                          <ArrowDown size={12} className="sort-icon is-active" />
                        )
                      ) : (
                        <ArrowUpDown size={11} className="sort-icon" />
                      )}
                    </button>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {sortedRows.length > 0 ? (
              sortedRows.map((row, rIdx) => (
                <tr key={rIdx}>
                  {headers.map((header, cIdx) => (
                    <td key={cIdx}>
                      {renderCellContent(row[cIdx] ?? "", cIdx, header)}
                    </td>
                  ))}
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={headers.length} className="table-empty-cell">
                  No matching records found.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Truncated Notice Footer */}
      {metadata?.isTruncated && (
        <div className="table-truncated-notice">
          <Info size={12} className="notice-icon" aria-hidden="true" />
          <span>Showing top records (data truncated for brevity in source view)</span>
        </div>
      )}
    </div>
  );
}
