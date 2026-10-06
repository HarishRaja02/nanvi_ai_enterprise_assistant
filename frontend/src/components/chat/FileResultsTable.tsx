import React, { useState } from "react";
import { ExternalLink, FileText, Check, Loader2 } from "lucide-react";
import type { FileResultItem } from "../../types";
import { useToast } from "../ui/Toast";
import { NanviApiClient } from "../../api";

interface Props {
  files: FileResultItem[];
  api?: NanviApiClient;
  onOpen?: (file: FileResultItem) => void;
}

export function FileResultsTable({ files, api, onOpen }: Props) {
  const notify = useToast();
  const [openingPath, setOpeningPath] = useState<string | null>(null);

  if (!files || files.length === 0) {
    return null;
  }

  // Cap at top 10 results
  const displayedFiles = files.slice(0, 10);

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
          notify(`Opened ${file.name} in default application`, "success");
        } else {
          // Web / Vercel fallback: view/download file in browser tab
          const downloadUrl = `/api/chat/download-file?path=${encodeURIComponent(openTarget)}`;
          window.open(downloadUrl, "_blank");
          notify(`Opening ${file.name}...`, "info");
        }
      } else {
        const downloadUrl = `/api/chat/download-file?path=${encodeURIComponent(openTarget)}`;
        window.open(downloadUrl, "_blank");
        notify(`Opening ${file.name}...`, "info");
      }
    } catch (err) {
      // Web / Vercel fallback
      const downloadUrl = `/api/chat/download-file?path=${encodeURIComponent(openTarget)}`;
      window.open(downloadUrl, "_blank");
      notify(`Opening ${file.name}...`, "info");
    } finally {
      setOpeningPath(null);
    }
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
                    <div className="file-name-wrapper">
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
                    <button
                      type="button"
                      className="file-open-btn"
                      disabled={isOpening}
                      onClick={() => handleOpen(file)}
                      title={`Open ${file.name}`}
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
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
