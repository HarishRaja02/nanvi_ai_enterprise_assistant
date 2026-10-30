import React, { useState, useEffect, useRef } from "react";
import { FileText, Check, Copy, Eye, ExternalLink, Loader2, Download, AlertCircle } from "lucide-react";
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

  // In-memory ephemeral preview state
  const [previewFile, setPreviewFile] = useState<FileResultItem | null>(null);
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [blobLoading, setBlobLoading] = useState(false);
  const [blobError, setBlobError] = useState<string | null>(null);
  const [blobMime, setBlobMime] = useState<string | null>(null);
  const activeBlobUrlRef = useRef<string | null>(null);

  // Free in-memory blob when component unmounts or user leaves the page
  useEffect(() => {
    return () => {
      if (activeBlobUrlRef.current) {
        URL.revokeObjectURL(activeBlobUrlRef.current);
        activeBlobUrlRef.current = null;
      }
    };
  }, []);

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

  const openPreview = async (file: FileResultItem) => {
    // Revoke any previous URL from memory
    if (activeBlobUrlRef.current) {
      URL.revokeObjectURL(activeBlobUrlRef.current);
      activeBlobUrlRef.current = null;
    }
    setBlobUrl(null);
    setBlobError(null);
    setPreviewFile(file);
    setBlobLoading(true);

    const exactPath = getExactPath(file);
    try {
      if (api && typeof api.getDocumentBlob === "function") {
        const result = await api.getDocumentBlob(exactPath);
        const objUrl = URL.createObjectURL(result.blob);
        activeBlobUrlRef.current = objUrl;
        setBlobUrl(objUrl);
        setBlobMime(result.mimeType);
      } else {
        const res = await fetch(`/api/local-agent/document-content?path=${encodeURIComponent(exactPath)}`);
        if (!res.ok) throw new Error("Could not load document into browser memory");
        const blob = await res.blob();
        const objUrl = URL.createObjectURL(blob);
        activeBlobUrlRef.current = objUrl;
        setBlobUrl(objUrl);
        setBlobMime(blob.type);
      }
    } catch (err: any) {
      setBlobError(err.message || "Document content not available on cloud server");
    } finally {
      setBlobLoading(false);
    }
  };

  const closePreview = () => {
    if (activeBlobUrlRef.current) {
      URL.revokeObjectURL(activeBlobUrlRef.current);
      activeBlobUrlRef.current = null;
    }
    setBlobUrl(null);
    setBlobError(null);
    setPreviewFile(null);
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

    try {
      // 1. Dispatch remote open command to local agent in background
      if (api && typeof api.openFile === "function") {
        api.openFile(exactPath).catch(() => {});
      }

      // 2. Open interactive ephemeral in-memory document preview in browser
      notify(`Opening ${file.name} in secure browser memory...`, "success");
      await openPreview(file);
    } catch {
      // openPreview catches internally, but guard against any unexpected exception
    } finally {
      setOpeningIdx(null);
    }
  };

  const isPdf = (file: FileResultItem, mime?: string | null) => {
    return (mime && mime.includes("pdf")) || file.name.toLowerCase().endsWith(".pdf") || getExactPath(file).toLowerCase().endsWith(".pdf");
  };

  const isImage = (file: FileResultItem, mime?: string | null) => {
    if (mime && mime.startsWith("image/")) return true;
    const ext = file.name.toLowerCase();
    return ext.endsWith(".png") || ext.endsWith(".jpg") || ext.endsWith(".jpeg") || ext.endsWith(".gif") || ext.endsWith(".webp") || ext.endsWith(".svg");
  };

  return (
    <div className="file-results-container">
      <div className="file-results-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "8px" }}>
        <span className="file-results-count">
          Showing <strong>{displayedFiles.length}</strong> matching document{displayedFiles.length !== 1 ? "s" : ""}:
        </span>
        <span style={{ fontSize: "12px", color: "#64748b" }}>
          💡 Click <strong>Open</strong> to view immediately in browser memory or <strong>Copy Path</strong> for File Explorer
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
                      onClick={() => openPreview(file)}
                      title="Click to view full document in browser memory"
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
                        onClick={() => openPreview(file)}
                        title={`Preview ${file.name} in browser memory`}
                      >
                        <Eye className="btn-icon" />
                        <span>Preview</span>
                      </button>
                      <button
                        type="button"
                        className="file-open-btn"
                        disabled={isOpening}
                        onClick={() => handleOpen(file, idx)}
                        title={`Open ${file.name} in browser memory and local desktop`}
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

      {/* In-app Ephemeral Document Preview Modal */}
      {previewFile && (
        <Modal
          title={previewFile.name}
          onClose={closePreview}
          size="xl"
          footer={
            <div style={{ display: "flex", justifyContent: "space-between", width: "100%", alignItems: "center", flexWrap: "wrap", gap: "8px" }}>
              <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handleCopyPath(getExactPath(previewFile))}
                  title="Copy Windows path"
                >
                  {copiedModal ? <Check className="w-4 h-4 mr-1 text-green-600" /> : <Copy className="w-4 h-4 mr-1" />}
                  {copiedModal ? "Copied!" : "Copy File Path"}
                </Button>
                {blobUrl && (
                  <a
                    href={blobUrl}
                    download={previewFile.name}
                    style={{ textDecoration: "none" }}
                  >
                    <Button variant="outline" size="sm" title="Save a copy to your computer">
                      <Download className="w-4 h-4 mr-1" />
                      Download Copy
                    </Button>
                  </a>
                )}
              </div>
              <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                <Button
                  variant="primary"
                  size="sm"
                  onClick={async () => {
                    const p = getExactPath(previewFile);
                    if (api && typeof api.openFile === "function") {
                      notify(`Sending open command to Nanvi Windows Agent...`, "success");
                      await api.openFile(p);
                    }
                  }}
                  title="Open directly in Windows desktop application (WPS Office / Acrobat / Excel)"
                >
                  <ExternalLink className="w-4 h-4 mr-1" />
                  Open in Desktop App
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={closePreview}
                >
                  Close
                </Button>
              </div>
            </div>
          }
        >
          <div style={{ display: "flex", flexDirection: "column", gap: "12px", minHeight: "450px" }}>
            {/* Ephemeral Memory Notice */}
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", background: "#f0fdf4", border: "1px solid #bbf7d0", padding: "8px 14px", borderRadius: "8px", fontSize: "12.5px", color: "#166534" }}>
              <span>
                🔒 <strong>In-Memory Ephemeral Preview:</strong> Loaded securely into browser RAM. Automatically destroyed when closed or navigating away.
              </span>
              <code style={{ fontSize: "11px", color: "#0369a1", background: "#ffffff", padding: "2px 6px", borderRadius: "4px", border: "1px solid #cbd5e1" }}>
                {previewFile.name}
              </code>
            </div>

            {/* Loading State */}
            {blobLoading && (
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "60px 16px", gap: "12px" }}>
                <Loader2 className="w-9 h-9 animate-spin text-blue-600" />
                <div style={{ fontSize: "14px", color: "#475569", fontWeight: 500 }}>
                  Streaming {previewFile.name} into browser memory...
                </div>
              </div>
            )}

            {/* Render In-Memory PDF Document */}
            {!blobLoading && blobUrl && isPdf(previewFile, blobMime) && (
              <div style={{ width: "100%", height: "66vh", minHeight: "480px", borderRadius: "8px", overflow: "hidden", border: "1px solid #cbd5e1", background: "#f8fafc" }}>
                <iframe
                  src={blobUrl}
                  title={previewFile.name}
                  style={{ width: "100%", height: "100%", border: "none" }}
                />
              </div>
            )}

            {/* Render In-Memory Image */}
            {!blobLoading && blobUrl && isImage(previewFile, blobMime) && (
              <div style={{ display: "flex", justifyContent: "center", alignItems: "center", width: "100%", height: "65vh", background: "#0f172a", borderRadius: "8px", overflow: "hidden" }}>
                <img
                  src={blobUrl}
                  alt={previewFile.name}
                  style={{ maxWidth: "100%", maxHeight: "100%", objectFit: "contain" }}
                />
              </div>
            )}

            {/* Render In-Memory Text / CSV / Code / Fallback */}
            {!blobLoading && blobUrl && !isPdf(previewFile, blobMime) && !isImage(previewFile, blobMime) && (
              <div style={{ width: "100%", height: "65vh", borderRadius: "8px", overflow: "hidden", border: "1px solid #cbd5e1", background: "#ffffff" }}>
                <iframe
                  src={blobUrl}
                  title={previewFile.name}
                  style={{ width: "100%", height: "100%", border: "none" }}
                />
              </div>
            )}

            {/* Fallback if Blob failed: Render Text Snippet and Windows Guide */}
            {!blobLoading && (!blobUrl || blobError) && (
              <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
                <div style={{ background: "#fef2f2", border: "1px solid #fecaca", borderRadius: "8px", padding: "12px 16px", display: "flex", alignItems: "center", gap: "10px", color: "#991b1b", fontSize: "13px" }}>
                  <AlertCircle className="w-5 h-5 flex-shrink-0" />
                  <div>
                    <strong>Direct cloud binary preview unavailable:</strong> {blobError || "File is stored only on your local computer."} You can still open it directly on your desktop or copy the path.
                  </div>
                </div>

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

                {previewFile.content_snippet && (
                  <div>
                    <div style={{ fontSize: "13px", fontWeight: 600, color: "#334155", marginBottom: "8px" }}>
                      Document Excerpt & Indexed Content:
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
                )}
              </div>
            )}
          </div>
        </Modal>
      )}
    </div>
  );
}
