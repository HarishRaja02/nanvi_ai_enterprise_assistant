import React, { useState } from "react";
import { ExternalLink, FileText, Check, Loader2, Eye, Copy } from "lucide-react";
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
  const [openingPath, setOpeningPath] = useState<string | null>(null);
  const [previewFile, setPreviewFile] = useState<FileResultItem | null>(null);
  const [copiedPath, setCopiedPath] = useState(false);

  if (!files || files.length === 0) {
    return null;
  }

  // Cap at top 10 results
  const displayedFiles = files.slice(0, 10);

  const getAuthenticatedDownloadUrl = (path: string) => {
    const token = localStorage.getItem("nanvi_token") || localStorage.getItem("nanvi_access_token") || "";
    return `/api/chat/download-file?path=${encodeURIComponent(path)}${token ? `&token=${encodeURIComponent(token)}` : ""}`;
  };

  const handleOpen = async (file: FileResultItem) => {
    if (onOpen) {
      onOpen(file);
      return;
    }

    const openTarget = file.open_url || file.path;

    // Web URL (e.g. Google Drive, Cloud link, web app)
    if (openTarget.startsWith("http://") || openTarget.startsWith("https://")) {
      window.open(openTarget, "_blank", "noopener,noreferrer");
      notify(`Opening ${file.name} in browser...`, "success");
      return;
    }

    // Local / server file path
    setOpeningPath(openTarget);
    try {
      if (api && typeof api.openFile === "function") {
        const res = await api.openFile(openTarget);
        if (res.status === "ok") {
          notify(res.message || `Opening ${file.name} on your computer...`, "success");
          return;
        }
      }
      // If fallback needed, open authenticated preview URL
      const downloadUrl = getAuthenticatedDownloadUrl(openTarget);
      window.open(downloadUrl, "_blank");
      notify(`Opening ${file.name}...`, "info");
    } catch (err: any) {
      // If error occurs, show in-app preview modal
      setPreviewFile(file);
      notify(`Showing preview for ${file.name}`, "info");
    } finally {
      setOpeningPath(null);
    }
  };

  const handleCopyPath = (path: string) => {
    navigator.clipboard.writeText(path);
    setCopiedPath(true);
    notify("Copied file path to clipboard", "success");
    setTimeout(() => setCopiedPath(false), 2000);
  };

  return (
    <div className="file-results-container">
      <div className="file-results-header">
        <span className="file-results-count">
          Showing <strong>{displayedFiles.length}</strong> matching document{displayedFiles.length !== 1 ? "s" : ""}:
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
              const isOpening = openingPath === file.path || openingPath === file.open_url;
              return (
                <tr key={`${file.path}-${idx}`} className="file-results-row">
                  <td className="cell-name">
                    <div
                      className="file-name-wrapper"
                      style={{ cursor: "pointer" }}
                      onClick={() => setPreviewFile(file)}
                      title="Click to preview file content"
                    >
                      <FileText className="file-icon" />
                      <span className="file-name-text" title={file.name}>
                        {file.name}
                      </span>
                    </div>
                  </td>
                  <td className="cell-path">
                    <code className="file-path-code" title={file.path}>
                      {file.path}
                    </code>
                  </td>
                  <td className="cell-action">
                    <div style={{ display: "flex", gap: "6px", alignItems: "center" }}>
                      <button
                        type="button"
                        className="file-open-btn"
                        disabled={isOpening}
                        onClick={() => handleOpen(file)}
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
                      <button
                        type="button"
                        className="file-open-btn"
                        style={{ background: "transparent", border: "1px solid #cbd5e1", color: "#475569" }}
                        onClick={() => setPreviewFile(file)}
                        title={`Preview ${file.name}`}
                      >
                        <Eye className="btn-icon" />
                        <span>Preview</span>
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
                variant="outline"
                size="sm"
                onClick={() => handleCopyPath(previewFile.open_url || previewFile.path)}
              >
                {copiedPath ? <Check className="w-4 h-4 mr-1 text-green-600" /> : <Copy className="w-4 h-4 mr-1" />}
                {copiedPath ? "Copied" : "Copy Path"}
              </Button>
              <div style={{ display: "flex", gap: "8px" }}>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    const url = getAuthenticatedDownloadUrl(previewFile.open_url || previewFile.path);
                    window.open(url, "_blank");
                  }}
                >
                  <ExternalLink className="w-4 h-4 mr-1" />
                  Open in New Tab
                </Button>
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => {
                    handleOpen(previewFile);
                    setPreviewFile(null);
                  }}
                >
                  Open on Computer
                </Button>
              </div>
            </div>
          }
        >
          <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
            <div style={{ background: "#f8fafc", padding: "12px 16px", borderRadius: "8px", border: "1px solid #e2e8f0" }}>
              <div style={{ fontSize: "12px", color: "#64748b", fontWeight: 600, textTransform: "uppercase", marginBottom: "4px" }}>
                Location on your computer
              </div>
              <code style={{ fontSize: "13px", color: "#0f172a", wordBreak: "break-all" }}>
                {previewFile.open_url || previewFile.path}
              </code>
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
                    maxHeight: "360px",
                    overflowY: "auto",
                  }}
                >
                  {previewFile.content_snippet}
                </div>
              </div>
            ) : (
              <div style={{ color: "#64748b", fontSize: "14px", fontStyle: "italic", padding: "12px 0" }}>
                This file is stored on your Windows computer. Click "Open on Computer" to view the complete document in its default application.
              </div>
            )}
          </div>
        </Modal>
      )}
    </div>
  );
}

