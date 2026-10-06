import React, { useState } from "react";
import { FileText, Check, Copy, Eye, ExternalLink, Loader2 } from "lucide-react";
import type { FileResultItem } from "../../types";
import { useToast } from "../ui/Toast";
import { NanviApiClient } from "../../api";
import { Modal } from "../ui/Modal";
import { Button } from "../ui/Button";

interface Props {
  files: FileResultItem[];
  api?: NanviApiClient;
  onOpen?: (file: FileResultItem) => void;
}

export function FileResultsTable({ files, api, onOpen }: Props) {
  const notify = useToast();
  const [copiedIdx, setCopiedIdx] = useState<number | null>(null);
  const [copiedModal, setCopiedModal] = useState(false);
  const [openingIdx, setOpeningIdx] = useState<number | null>(null);
  const [previewFile, setPreviewFile] = useState<FileResultItem | null>(null);

  if (!files || files.length === 0) {
    return null;
  }

  // Cap at top 10 results
  const displayedFiles = files.slice(0, 10);

  const getExactPath = (file: FileResultItem): string => {
    return file.full_path || file.open_url || file.path;
  };

  const handleCopyPath = async (path: string, idx?: number) => {
    try {
      await navigator.clipboard.writeText(path);
      if (idx !== undefined) {
        setCopiedIdx(idx);
        setTimeout(() => setCopiedIdx(null), 2000);
      } else {
        setCopiedModal(true);
        setTimeout(() => setCopiedModal(false), 2000);
      }
      notify(`Copied exact file path to clipboard`, "success");
    } catch {
      notify("Could not copy automatically. Please copy the path manually.", "danger");
    }
  };

  const handleOpen = async (file: FileResultItem, idx: number) => {
    const exactPath = getExactPath(file);

    // If web URL (e.g. Google Drive, Cloud link)
    if (exactPath.startsWith("http://") || exactPath.startsWith("https://")) {
      window.open(exactPath, "_blank", "noopener,noreferrer");
      notify(`Opening ${file.name} in browser...`, "success");
      return;
    }

    if (onOpen) {
      onOpen(file);
      return;
    }

    // Always copy the exact path to clipboard immediately so the user is never stuck
    try {
      await navigator.clipboard.writeText(exactPath);
    } catch {
      // ignore clipboard error
    }

    setOpeningIdx(idx);
    notify(`Copied path to clipboard! Requesting open on computer...`, "success");

    try {
      if (api && typeof api.openFile === "function") {
        await Promise.race([
          api.openFile(exactPath),
          new Promise((resolve) => setTimeout(resolve, 1500)),
        ]);
      }
    } catch {
      // Handled silently since path is already copied to clipboard
    } finally {
      setTimeout(() => setOpeningIdx(null), 1000);
    }
  };

  return (
    <div className="file-results-container">
      <div className="file-results-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "8px" }}>
        <span className="file-results-count">
          Showing <strong>{displayedFiles.length}</strong> matching document{displayedFiles.length !== 1 ? "s" : ""}:
        </span>
        <span style={{ fontSize: "12px", color: "#64748b" }}>
          💡 Click <strong>Copy Path</strong> to open via File Explorer or Run (Win + R)
        </span>
      </div>
      <div className="file-results-table-wrapper">
        <table className="file-results-table">
          <thead>
            <tr>
              <th className="col-name">File Name</th>
              <th className="col-path">File Path</th>
              <th className="col-action">Action</th>
            </tr>
          </thead>
          <tbody>
            {displayedFiles.map((file, idx) => {
              const exactPath = getExactPath(file);
              const isCopied = copiedIdx === idx;
              const isOpening = openingIdx === idx;

              return (
                <tr key={`${exactPath}-${idx}`} className="file-results-row">
                  <td className="cell-name">
                    <div
                      className="file-name-wrapper"
                      style={{ cursor: "pointer" }}
                      onClick={() => setPreviewFile(file)}
                      title="Click to view file content and details"
                    >
                      <FileText className="file-icon" />
                      <span className="file-name-text" title={file.name}>
                        {file.name}
                      </span>
                    </div>
                  </td>
                  <td className="cell-path">
                    <div
                      className="file-path-interactive"
                      onClick={() => handleCopyPath(exactPath, idx)}
                      title="Click to copy exact path"
                    >
                      <code className="file-path-code">
                        {exactPath}
                      </code>
                      <Copy className="file-copy-icon-subtle" />
                    </div>
                  </td>
                  <td className="cell-action">
                    <div style={{ display: "flex", gap: "6px", justifyContent: "flex-end", alignItems: "center" }}>
                      <button
                        type="button"
                        className={`file-copy-btn ${isCopied ? "is-copied" : ""}`}
                        onClick={() => handleCopyPath(exactPath, idx)}
                        title="Copy exact file path to clipboard"
                      >
                        {isCopied ? <Check className="btn-icon" /> : <Copy className="btn-icon" />}
                        <span>{isCopied ? "Copied!" : "Copy Path"}</span>
                      </button>
                      <button
                        type="button"
                        className="file-preview-btn"
                        onClick={() => setPreviewFile(file)}
                        title={`Preview ${file.name}`}
                      >
                        <Eye className="btn-icon" />
                        <span>Preview</span>
                      </button>
                      <button
                        type="button"
                        className="file-open-btn"
                        disabled={isOpening}
                        onClick={() => handleOpen(file, idx)}
                        title={`Open ${file.name} on your computer`}
                      >
                        {isOpening ? (
                          <>
                            <Loader2 className="btn-icon animate-spin" />
                            <span>Opening...</span>
                          </>
                        ) : (
                          <>
                            <ExternalLink className="btn-icon" />
                            <span>Open</span>
                          </>
                        )}
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* In-app Document Preview Modal */}
      {previewFile && (
        <Modal
          title={previewFile.name}
          onClose={() => setPreviewFile(null)}
          footer={
            <div style={{ display: "flex", justifyContent: "space-between", width: "100%", alignItems: "center" }}>
              <Button
                variant="primary"
                size="sm"
                onClick={() => handleCopyPath(getExactPath(previewFile))}
              >
                {copiedModal ? <Check className="w-4 h-4 mr-1 text-white" /> : <Copy className="w-4 h-4 mr-1" />}
                {copiedModal ? "Copied!" : "Copy File Path"}
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPreviewFile(null)}
              >
                Close
              </Button>
            </div>
          }
        >
          <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
            <div style={{ background: "#f8fafc", padding: "14px 16px", borderRadius: "8px", border: "1px solid #e2e8f0" }}>
              <div style={{ fontSize: "11px", color: "#64748b", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: "6px" }}>
                Exact File Path on Your Computer
              </div>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "12px", background: "#ffffff", padding: "8px 12px", borderRadius: "6px", border: "1px solid #cbd5e1" }}>
                <code style={{ fontSize: "12.5px", color: "#0284c7", wordBreak: "break-all", fontFamily: "monospace" }}>
                  {getExactPath(previewFile)}
                </code>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handleCopyPath(getExactPath(previewFile))}
                  title="Copy path"
                >
                  {copiedModal ? <Check className="w-3.5 h-3.5 text-green-600" /> : <Copy className="w-3.5 h-3.5" />}
                  <span style={{ fontSize: "12px", marginLeft: "4px" }}>{copiedModal ? "Copied" : "Copy"}</span>
                </Button>
              </div>
            </div>

            <div style={{ background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: "8px", padding: "12px 16px", fontSize: "13px", color: "#166534", lineHeight: "1.5" }}>
              <strong>💡 How to open on Windows:</strong> Click <strong>"Copy File Path"</strong>, press <kbd style={{ background: "#ffffff", border: "1px solid #cbd5e1", borderRadius: "3px", padding: "1px 5px" }}>Win</kbd> + <kbd style={{ background: "#ffffff", border: "1px solid #cbd5e1", borderRadius: "3px", padding: "1px 5px" }}>R</kbd>, paste the path, and hit <kbd style={{ background: "#ffffff", border: "1px solid #cbd5e1", borderRadius: "3px", padding: "1px 5px" }}>Enter</kbd>.
            </div>

            {previewFile.content_snippet ? (
              <div>
                <div style={{ fontSize: "13px", fontWeight: 600, color: "#334155", marginBottom: "8px" }}>
                  Document Excerpt & Content:
                </div>
                <div
                  style={{
                    background: "#ffffff",
                    border: "1px solid #e2e8f0",
                    borderRadius: "8px",
                    padding: "16px",
                    fontSize: "14px",
                    lineHeight: "1.6",
                    color: "#1e293b",
                    whiteSpace: "pre-wrap",
                    maxHeight: "340px",
                    overflowY: "auto",
                  }}
                >
                  {previewFile.content_snippet}
                </div>
              </div>
            ) : (
              <div style={{ color: "#64748b", fontSize: "13.5px", fontStyle: "italic", padding: "8px 0" }}>
                This file is stored on your local Windows PC. Use the copied path above to open it in its default application.
              </div>
            )}
          </div>
        </Modal>
      )}
    </div>
  );
}
