import { useCallback, useEffect, useState } from "react";
import type { NanviApiClient, BrowseDirectoryEntry } from "../../api";

type Props = {
  api: NanviApiClient;
};

export function CompanyFolderPicker({ api }: Props) {
  const [currentPath, setCurrentPath] = useState("");
  const [folderExists, setFolderExists] = useState(true);
  const [folderCount, setFolderCount] = useState(0);
  const [fileCount, setFileCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ text: string; type: "success" | "error" } | null>(null);

  // Browser state
  const [browserOpen, setBrowserOpen] = useState(false);
  const [browsePath, setBrowsePath] = useState("");
  const [browseEntries, setBrowseEntries] = useState<BrowseDirectoryEntry[]>([]);
  const [browseParent, setBrowseParent] = useState<string | null>(null);
  const [browseLoading, setBrowseLoading] = useState(false);
  const [browseError, setBrowseError] = useState<string | null>(null);

  // Manual input state
  const [inputPath, setInputPath] = useState("");
  const [editMode, setEditMode] = useState(false);

  // Fetch current folder on mount and listen to updates
  useEffect(() => {
    let cancelled = false;
    api
      .getCompanyFolder()
      .then((res) => {
        if (cancelled) return;
        setCurrentPath(res.path);
        setInputPath(res.path);
        setFolderExists(res.exists);
        setFolderCount(res.folder_count);
        setFileCount(res.file_count);
      })
      .catch(() => {
        if (!cancelled) setMessage({ text: "Could not load current folder.", type: "error" });
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    const onExternalUpdate = (e: Event) => {
      const customEvent = e as CustomEvent<{
        path: string;
        exists: boolean;
        folder_count: number;
        file_count: number;
      }>;
      if (customEvent.detail) {
        setCurrentPath(customEvent.detail.path);
        setInputPath(customEvent.detail.path);
        setFolderExists(customEvent.detail.exists);
        setFolderCount(customEvent.detail.folder_count);
        setFileCount(customEvent.detail.file_count);
      }
    };
    window.addEventListener("nanvi:company-folder-updated", onExternalUpdate);

    return () => {
      cancelled = true;
      window.removeEventListener("nanvi:company-folder-updated", onExternalUpdate);
    };
  }, [api]);

  const saveFolder = useCallback(
    async (path: string) => {
      setSaving(true);
      setMessage(null);
      try {
        const res = await api.updateCompanyFolder(path);
        if (res.status === "ok") {
          setCurrentPath(res.path);
          setInputPath(res.path);
          setFolderExists(res.exists);
          setFolderCount(res.folder_count);
          setFileCount(res.file_count);
          setMessage({ text: `${res.indexed_files} files indexed from new location.`, type: "success" });
          setEditMode(false);
          setBrowserOpen(false);
          window.dispatchEvent(new CustomEvent("nanvi:company-folder-updated", { detail: res }));
        } else {
          setMessage({ text: res.message, type: "error" });
        }
      } catch (err) {
        setMessage({ text: err instanceof Error ? err.message : "Failed to update folder.", type: "error" });
      } finally {
        setSaving(false);
      }
    },
    [api]
  );

  const openBrowser = useCallback(
    async (path?: string) => {
      setBrowserOpen(true);
      setBrowseLoading(true);
      setBrowseError(null);
      try {
        const res = await api.browseDirectory(path ?? currentPath);
        setBrowsePath(res.path);
        setBrowseEntries(res.entries);
        setBrowseParent(res.parent ?? null);
        if (res.error) setBrowseError(res.error);
      } catch {
        setBrowseError("Could not browse directory.");
      } finally {
        setBrowseLoading(false);
      }
    },
    [api, currentPath]
  );

  const navigateTo = useCallback(
    async (path: string) => {
      setBrowseLoading(true);
      setBrowseError(null);
      try {
        const res = await api.browseDirectory(path);
        setBrowsePath(res.path);
        setBrowseEntries(res.entries);
        setBrowseParent(res.parent ?? null);
        if (res.error) setBrowseError(res.error);
      } catch {
        setBrowseError("Could not browse directory.");
      } finally {
        setBrowseLoading(false);
      }
    },
    [api]
  );

  if (loading) {
    return (
      <div className="folder-picker">
        <div className="folder-picker-loading">
          <div className="folder-picker-spinner" />
          <span>Loading folder settings…</span>
        </div>
      </div>
    );
  }

  return (
    <div className="folder-picker">
      <div className="folder-picker-header">
        <div className="folder-picker-icon">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
          </svg>
        </div>
        <div className="folder-picker-title-area">
          <h3 className="folder-picker-title">Company Data Folder</h3>
          <p className="folder-picker-subtitle">
            Select where your company documents are stored on your system
          </p>
        </div>
      </div>

      {/* Current Path Display */}
      <div className="folder-picker-current">
        <div className="folder-picker-path-row">
          {!editMode ? (
            <>
              <div className="folder-picker-path-display">
                <span className="folder-picker-path-label">Current location</span>
                <code className="folder-picker-path-value">{currentPath || "Not configured"}</code>
              </div>
              <div className="folder-picker-actions">
                <button
                  className="folder-picker-btn folder-picker-btn-secondary"
                  onClick={() => setEditMode(true)}
                  title="Type a path manually"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                    <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
                  </svg>
                  Edit
                </button>
                <button
                  className="folder-picker-btn folder-picker-btn-primary"
                  onClick={() => void openBrowser()}
                  disabled={saving}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
                    <line x1="12" y1="11" x2="12" y2="17" />
                    <line x1="9" y1="14" x2="15" y2="14" />
                  </svg>
                  Browse
                </button>
              </div>
            </>
          ) : (
            <div className="folder-picker-edit-row">
              <input
                className="folder-picker-input"
                type="text"
                value={inputPath}
                onChange={(e) => setInputPath(e.target.value)}
                placeholder="Enter folder path, e.g. C:\CompanyData"
                autoFocus
                onKeyDown={(e) => {
                  if (e.key === "Enter" && inputPath.trim()) {
                    void saveFolder(inputPath.trim());
                  }
                  if (e.key === "Escape") {
                    setEditMode(false);
                    setInputPath(currentPath);
                  }
                }}
              />
              <button
                className="folder-picker-btn folder-picker-btn-primary"
                onClick={() => void saveFolder(inputPath.trim())}
                disabled={saving || !inputPath.trim()}
              >
                {saving ? "Saving…" : "Apply"}
              </button>
              <button
                className="folder-picker-btn folder-picker-btn-ghost"
                onClick={() => {
                  setEditMode(false);
                  setInputPath(currentPath);
                }}
              >
                Cancel
              </button>
            </div>
          )}
        </div>

        {/* Stats pills */}
        {folderExists && (
          <div className="folder-picker-stats">
            <span className="folder-picker-stat">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
              </svg>
              {folderCount} folders
            </span>
            <span className="folder-picker-stat">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                <polyline points="14 2 14 8 20 8" />
              </svg>
              {fileCount} files
            </span>
            <span className="folder-picker-stat folder-picker-stat-active">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="20 6 9 17 4 12" />
              </svg>
              Active
            </span>
          </div>
        )}
        {!folderExists && currentPath && (
          <div className="folder-picker-warning">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
              <line x1="12" y1="9" x2="12" y2="13" />
              <line x1="12" y1="17" x2="12.01" y2="17" />
            </svg>
            Folder not found at this path
          </div>
        )}
      </div>

      {/* Status message */}
      {message && (
        <div className={`folder-picker-message folder-picker-message-${message.type}`}>
          {message.type === "success" ? (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
              <polyline points="22 4 12 14.01 9 11.01" />
            </svg>
          ) : (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" />
              <line x1="15" y1="9" x2="9" y2="15" />
              <line x1="9" y1="9" x2="15" y2="15" />
            </svg>
          )}
          {message.text}
        </div>
      )}

      {/* Folder Browser Modal */}
      {browserOpen && (
        <div className="folder-browser-overlay" onClick={() => setBrowserOpen(false)}>
          <div className="folder-browser" onClick={(e) => e.stopPropagation()}>
            <div className="folder-browser-header">
              <h4>Select Company Data Folder</h4>
              <button
                className="folder-browser-close"
                onClick={() => setBrowserOpen(false)}
                aria-label="Close browser"
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="18" y1="6" x2="6" y2="18" />
                  <line x1="6" y1="6" x2="18" y2="18" />
                </svg>
              </button>
            </div>

            {/* Breadcrumb path display */}
            <div className="folder-browser-breadcrumb">
              <code>{browsePath || "System Drives"}</code>
            </div>

            {/* Navigation bar */}
            <div className="folder-browser-nav">
              {browseParent !== null && (
                <button
                  className="folder-browser-back"
                  onClick={() => void navigateTo(browseParent ?? "")}
                  disabled={browseLoading}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="15 18 9 12 15 6" />
                  </svg>
                  Go up
                </button>
              )}
            </div>

            {/* Directory listing */}
            <div className="folder-browser-list">
              {browseLoading ? (
                <div className="folder-browser-loading">
                  <div className="folder-picker-spinner" />
                  <span>Loading…</span>
                </div>
              ) : browseError ? (
                <div className="folder-browser-error">{browseError}</div>
              ) : browseEntries.length === 0 ? (
                <div className="folder-browser-empty">No folders found</div>
              ) : (
                browseEntries.map((entry) => (
                  <button
                    key={entry.path}
                    className="folder-browser-entry"
                    onClick={() => void navigateTo(entry.path)}
                    title={entry.path}
                  >
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
                    </svg>
                    <span className="folder-browser-entry-name">{entry.name}</span>
                    <svg className="folder-browser-entry-chevron" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="9 18 15 12 9 6" />
                    </svg>
                  </button>
                ))
              )}
            </div>

            {/* Select this folder button */}
            <div className="folder-browser-footer">
              <button
                className="folder-picker-btn folder-picker-btn-primary folder-browser-select"
                onClick={() => void saveFolder(browsePath)}
                disabled={!browsePath || saving}
              >
                {saving ? (
                  <>
                    <div className="folder-picker-spinner folder-picker-spinner-sm" />
                    Applying…
                  </>
                ) : (
                  <>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="20 6 9 17 4 12" />
                    </svg>
                    Select this folder
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
