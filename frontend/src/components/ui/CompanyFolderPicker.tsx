import { useCallback, useEffect, useState } from "react";
import type { NanviApiClient, BrowseDirectoryEntry, LocalAgentStatusResponse } from "../../api";

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

  // Local Agent state
  const [agentStatus, setAgentStatus] = useState<LocalAgentStatusResponse | null>(null);
  const [agentLoading, setAgentLoading] = useState(false);
  const [pairingToken, setPairingToken] = useState<string | null>(null);
  const [tokenCopied, setTokenCopied] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<any[] | null>(null);
  const [searchLoading, setSearchLoading] = useState(false);

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

  // Poll Local Agent status periodically
  useEffect(() => {
    let cancelled = false;
    const checkStatus = () => {
      api.getLocalAgentStatus()
        .then((res) => {
          if (!cancelled) setAgentStatus(res);
        })
        .catch(() => {});
    };
    checkStatus();
    const timer = setInterval(checkStatus, 6000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [api]);

  const fetchPairingToken = async () => {
    setAgentLoading(true);
    try {
      const res = await api.getLocalAgentToken();
      setPairingToken(res.token);
    } catch (err) {
      setMessage({
        text: err instanceof Error ? err.message : "Failed to generate pairing token.",
        type: "error",
      });
    } finally {
      setAgentLoading(false);
    }
  };

  const handleDisconnectFolder = async (folderId: string) => {
    try {
      await api.removeLocalFolder(folderId);
      const updated = await api.getLocalAgentStatus();
      setAgentStatus(updated);
      setMessage({ text: "Folder disconnected successfully.", type: "success" });
    } catch (err) {
      setMessage({
        text: err instanceof Error ? err.message : "Failed to disconnect folder.",
        type: "error",
      });
    }
  };

  const handleSearchLocal = async () => {
    if (!searchQuery.trim()) return;
    setSearchLoading(true);
    try {
      const res = await api.testSearchLocalAgent(searchQuery.trim());
      setSearchResults(res.chunks);
    } catch (err) {
      setMessage({
        text: err instanceof Error ? err.message : "Search failed.",
        type: "error",
      });
    } finally {
      setSearchLoading(false);
    }
  };

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
            Select a folder that the machine running Nanvi can access
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
                className="folder-picker-btn folder-picker-btn-secondary"
                onClick={() => void saveFolder("CompanyData")}
                disabled={saving}
                title="Use repository bundled CompanyData folder (recommended on Vercel/cloud)"
              >
                Use Bundled Data
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
          {editMode && inputPath.match(/^[a-zA-Z]:[\\/]/) &&
            typeof window !== "undefined" &&
            window.location.hostname !== "localhost" &&
            window.location.hostname !== "127.0.0.1" && (
              <div style={{ fontSize: "0.78rem", color: "#38bdf8", marginTop: "6px", padding: "4px 8px", background: "rgba(56, 189, 248, 0.08)", borderRadius: "6px" }}>
                ℹ️ You are accessing a cloud deployment ({window.location.hostname}). Cloud servers cannot read your personal computer&apos;s C:\ drive. Click <strong>&quot;Use Bundled Data&quot;</strong> to index the repository&apos;s company documents.
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
          <div className="folder-picker-warning" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "8px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
                <line x1="12" y1="9" x2="12" y2="13" />
                <line x1="12" y1="17" x2="12.01" y2="17" />
              </svg>
              Folder not found at this path
            </div>
            <button
              className="folder-picker-btn folder-picker-btn-secondary"
              style={{ padding: "3px 10px", fontSize: "0.75rem" }}
              onClick={() => void saveFolder("CompanyData")}
              disabled={saving}
            >
              Use Bundled CompanyData
            </button>
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

      {/* ------------------------------------------------------------- */}
      {/* Local File Agent Section (Windows / Local Machine Folders)    */}
      {/* ------------------------------------------------------------- */}
      <div className="local-agent-card" style={{ marginTop: "24px", padding: "20px", background: "rgba(15, 23, 42, 0.6)", border: "1px solid rgba(56, 189, 248, 0.25)", borderRadius: "12px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "12px" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
              <h4 style={{ margin: 0, fontSize: "1.05rem", fontWeight: 600, color: "#f8fafc" }}>
                My Computer Local Agent (Windows)
              </h4>
              <span
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "6px",
                  padding: "2px 10px",
                  borderRadius: "20px",
                  fontSize: "0.75rem",
                  fontWeight: 600,
                  background: agentStatus?.is_online ? "rgba(34, 197, 94, 0.15)" : "rgba(148, 163, 184, 0.15)",
                  color: agentStatus?.is_online ? "#4ade80" : "#94a3b8",
                  border: `1px solid ${agentStatus?.is_online ? "rgba(34, 197, 94, 0.3)" : "rgba(148, 163, 184, 0.3)"}`,
                }}
              >
                <span
                  style={{
                    width: "8px",
                    height: "8px",
                    borderRadius: "50%",
                    background: agentStatus?.is_online ? "#22c55e" : "#94a3b8",
                    boxShadow: agentStatus?.is_online ? "0 0 8px #22c55e" : "none",
                  }}
                />
                {agentStatus?.is_online ? "Agent Online" : "Agent Offline"}
              </span>
            </div>
            <p style={{ margin: "6px 0 0", fontSize: "0.85rem", color: "#94a3b8" }}>
              Search any folder from your Windows computer (e.g. <code>C:\Projects</code>, <code>C:\abc</code>, <code>C:\CompanyData</code>) directly through Nanvi.
            </p>
          </div>

          <button
            className="folder-picker-btn folder-picker-btn-primary"
            onClick={fetchPairingToken}
            disabled={agentLoading}
          >
            {pairingToken ? "Regenerate Token" : "Connect Local Folders"}
          </button>
        </div>

        {/* Pairing Token & Setup Instructions */}
        {pairingToken && (
          <div style={{ marginTop: "16px", padding: "14px", background: "rgba(30, 41, 59, 0.7)", borderRadius: "8px", border: "1px solid rgba(148, 163, 184, 0.2)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
              <span style={{ fontSize: "0.85rem", fontWeight: 600, color: "#e2e8f0" }}>Your Local Agent Pairing Token:</span>
              <button
                className="folder-picker-btn folder-picker-btn-secondary"
                style={{ padding: "3px 10px", fontSize: "0.75rem" }}
                onClick={() => {
                  navigator.clipboard.writeText(pairingToken);
                  setTokenCopied(true);
                  setTimeout(() => setTokenCopied(false), 2500);
                }}
              >
                {tokenCopied ? "✓ Copied!" : "Copy Token"}
              </button>
            </div>
            <code style={{ display: "block", padding: "8px 12px", background: "rgba(15, 23, 42, 0.8)", borderRadius: "6px", fontSize: "0.75rem", wordBreak: "break-all", color: "#38bdf8" }}>
              {pairingToken}
            </code>
            <div style={{ marginTop: "12px", fontSize: "0.8rem", color: "#94a3b8" }}>
              <strong>How to connect your folders:</strong>
              <div style={{ marginTop: "8px", display: "flex", gap: "8px", alignItems: "center" }}>
                <button
                  className="folder-picker-btn folder-picker-btn-primary"
                  style={{ padding: "4px 12px", fontSize: "0.8rem" }}
                  onClick={() => {
                    const server = typeof window !== "undefined" ? window.location.origin : "https://nanviaienterpriseassistant.vercel.app";
                    const cmd = `cd /d "%USERPROFILE%\\Desktop\\nanvi_ai_enterprise_assistant" && python local_agent/nanvi_local_agent.py --server ${server} --token ${pairingToken}`;
                    navigator.clipboard.writeText(cmd);
                    setTokenCopied(true);
                    setTimeout(() => setTokenCopied(false), 2500);
                  }}
                >
                  {tokenCopied ? "✓ Command Copied!" : "📋 Copy Terminal Command"}
                </button>
                <span style={{ fontSize: "0.75rem", color: "#64748b" }}>
                  (or double-click <code>local_agent\run_local_agent.bat</code>)
                </span>
              </div>
              <ol style={{ margin: "8px 0 0 16px", padding: 0, lineHeight: 1.6 }}>
                <li>Navigate to your project directory and run the agent:
                  <pre style={{ margin: "4px 0", padding: "6px 10px", background: "rgba(0,0,0,0.3)", borderRadius: "4px", color: "#f1f5f9", fontSize: "0.75rem", whiteSpace: "pre-wrap" }}>
                    cd /d &quot;%USERPROFILE%\Desktop\nanvi_ai_enterprise_assistant&quot; && python local_agent/nanvi_local_agent.py --server {typeof window !== "undefined" ? window.location.origin : "https://nanviaienterpriseassistant.vercel.app"} --token {pairingToken.slice(0, 16)}...
                  </pre>
                </li>
                <li>In the agent console, approve any folder on your PC:
                  <pre style={{ margin: "4px 0", padding: "6px 10px", background: "rgba(0,0,0,0.3)", borderRadius: "4px", color: "#f1f5f9" }}>
                    add C:\CompanyData
                  </pre>
                  (e.g. <code>add D:\Projects</code>, <code>add C:\abc</code>, etc.)
                </li>
              </ol>
            </div>
          </div>
        )}

        {/* Connected Folders List */}
        <div style={{ marginTop: "18px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
            <span style={{ fontSize: "0.85rem", fontWeight: 600, color: "#cbd5e1" }}>
              Connected Folders on Your Machine ({agentStatus?.connected_folders?.length || 0}):
            </span>
            {agentStatus && agentStatus.total_files > 0 && (
              <span style={{ fontSize: "0.78rem", color: "#38bdf8" }}>
                {agentStatus.total_files} files ({agentStatus.total_chunks} chunks indexed)
              </span>
            )}
          </div>

          {agentStatus?.connected_folders && agentStatus.connected_folders.length > 0 ? (
            <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
              {agentStatus.connected_folders.map((folder) => (
                <div
                  key={folder.folder_id}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    padding: "10px 14px",
                    background: "rgba(30, 41, 59, 0.5)",
                    border: "1px solid rgba(148, 163, 184, 0.15)",
                    borderRadius: "8px",
                  }}
                >
                  <div>
                    <div style={{ fontWeight: 600, fontSize: "0.88rem", color: "#f8fafc" }}>
                      📁 {folder.display_name}
                    </div>
                    <code style={{ fontSize: "0.75rem", color: "#94a3b8" }}>{folder.folder_path}</code>
                    <div style={{ marginTop: "4px", fontSize: "0.72rem", color: "#64748b" }}>
                      {folder.file_count} files • {folder.chunk_count} chunks • Status: <span style={{ color: "#4ade80" }}>{folder.status}</span>
                    </div>
                  </div>
                  <button
                    className="folder-picker-btn folder-picker-btn-ghost"
                    style={{ color: "#f87171", fontSize: "0.78rem" }}
                    onClick={() => handleDisconnectFolder(folder.folder_id)}
                  >
                    Disconnect
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ padding: "14px", textAlign: "center", color: "#64748b", background: "rgba(30, 41, 59, 0.3)", borderRadius: "8px", fontSize: "0.82rem" }}>
              No local folders connected. Run the Nanvi Local Agent on your machine to attach any folder.
            </div>
          )}
        </div>

        {/* Live Search Test Box */}
        {agentStatus?.connected_folders && agentStatus.connected_folders.length > 0 && (
          <div style={{ marginTop: "18px", paddingTop: "14px", borderTop: "1px solid rgba(148, 163, 184, 0.15)" }}>
            <span style={{ fontSize: "0.85rem", fontWeight: 600, color: "#cbd5e1" }}>Quick Local Search Test:</span>
            <div style={{ display: "flex", gap: "8px", marginTop: "8px" }}>
              <input
                className="folder-picker-input"
                type="text"
                placeholder="Search across your local files (e.g. bridge, contract, invoice)..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") void handleSearchLocal(); }}
              />
              <button
                className="folder-picker-btn folder-picker-btn-primary"
                onClick={handleSearchLocal}
                disabled={searchLoading || !searchQuery.trim()}
              >
                {searchLoading ? "Searching…" : "Search"}
              </button>
            </div>

            {searchResults && (
              <div style={{ marginTop: "10px", display: "flex", flexDirection: "column", gap: "6px" }}>
                <span style={{ fontSize: "0.75rem", color: "#94a3b8" }}>Found {searchResults.length} relevant excerpts:</span>
                {searchResults.map((hit, i) => (
                  <div key={i} style={{ padding: "8px 12px", background: "rgba(15, 23, 42, 0.7)", borderRadius: "6px", fontSize: "0.78rem" }}>
                    <div style={{ fontWeight: 600, color: "#38bdf8", marginBottom: "4px" }}>
                      📄 {hit.citation} (Score: {hit.score})
                    </div>
                    <div style={{ color: "#cbd5e1", lineHeight: 1.4 }}>{hit.text.slice(0, 200)}…</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

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
              <button
                className="folder-browser-back"
                onClick={() => void navigateTo("")}
                disabled={browseLoading}
              >
                All drives and locations
              </button>
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
