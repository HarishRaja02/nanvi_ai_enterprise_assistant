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
  const [customLocalFolder, setCustomLocalFolder] = useState("");
  const [addingFolder, setAddingFolder] = useState(false);
  const [addFolderMsg, setAddFolderMsg] = useState<string | null>(null);
  const [downloadingAgent, setDownloadingAgent] = useState(false);
  const [showAdvancedCli, setShowAdvancedCli] = useState(false);

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

  const handleAddLocalFolder = async (pathToAdd?: string) => {
    let raw = (pathToAdd || customLocalFolder).trim();
    if (!raw) return;

    // Sanitize accidental prefixes like "add ", "add folder ", or surrounding quotes
    let clean = raw.replace(/^['"“”`]|['"“”`]$/g, "").trim();
    for (const prefix of [
      "nanvi-agent add",
      "nanvi local agent add",
      "nanvi add",
      "python nanvi_local_agent.py add",
      "python nanvi_gui_agent.py add",
      "python local_agent.py add",
      "python add",
      "add folder",
      "add path",
      "add:",
      "add",
    ]) {
      if (clean.toLowerCase().startsWith(prefix + " ") || clean.toLowerCase() === prefix) {
        clean = clean.slice(prefix.length).trim().replace(/^['"“”`]|['"“”`]$/g, "").trim();
        break;
      }
    }
    clean = clean.replace(/^['"“”`:]|['"“”`:]$/g, "").trim();
    if (!clean) return;

    setAddingFolder(true);
    setAddFolderMsg(null);
    try {
      const res = await api.addLocalFolder(clean);
      setAddFolderMsg(res.message || `✓ Folder '${clean}' registered for indexing.`);
      setCustomLocalFolder("");
      setTimeout(() => {
        api.getLocalAgentStatus().then((s) => setAgentStatus(s)).catch(() => {});
      }, 1500);
    } catch (err: any) {
      setAddFolderMsg(`Error: ${err?.message || "Failed to add folder"}`);
    } finally {
      setAddingFolder(false);
    }
  };

  const handleQuickAdd = async (folderPath: string) => {
    return handleAddLocalFolder(folderPath);
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
      {/* ------------------------------------------------------------- */}
      {/* Local File Agent Section (Windows / Local Machine Folders)    */}
      {/* ------------------------------------------------------------- */}
      <div
        className="local-agent-card"
        style={{
          marginTop: "28px",
          padding: "28px",
          background: "#ffffff",
          color: "#0f172a",
          border: "2px solid #e2e8f0",
          borderRadius: "16px",
          boxShadow: "0 10px 30px rgba(0, 0, 0, 0.08)",
        }}
      >
        {/* Top Header with Status */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "16px" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "12px", flexWrap: "wrap" }}>
              <h3 style={{ margin: 0, fontSize: "1.25rem", fontWeight: 700, color: "#0f172a" }}>
                Search Files on My Computer (Windows)
              </h3>
              <span
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "8px",
                  padding: "4px 14px",
                  borderRadius: "20px",
                  fontSize: "0.85rem",
                  fontWeight: 600,
                  background: agentStatus?.is_online ? "#dcfce7" : "#f1f5f9",
                  color: agentStatus?.is_online ? "#166534" : "#475569",
                  border: `1px solid ${agentStatus?.is_online ? "#86efac" : "#cbd5e1"}`,
                }}
              >
                <span
                  style={{
                    width: "10px",
                    height: "10px",
                    borderRadius: "50%",
                    background: agentStatus?.is_online ? "#16a34a" : "#94a3b8",
                  }}
                />
                {agentStatus?.is_online ? "✓ Connected to Your Computer" : "○ Not Connected Yet"}
              </span>
            </div>
            <p style={{ margin: "8px 0 0", fontSize: "0.95rem", color: "#475569", lineHeight: 1.5, maxWidth: "680px" }}>
              Search documents from folders on your own Windows computer (PDF, Word, Excel, CSV, text). Your documents stay safe on your computer.
            </p>
          </div>

          {/* 1-Click .bat Download Button */}
          <button
            className="folder-picker-btn"
            style={{
              padding: "12px 22px",
              fontSize: "0.98rem",
              fontWeight: 700,
              background: "#0284c7",
              color: "#ffffff",
              border: "none",
              display: "inline-flex",
              alignItems: "center",
              gap: "10px",
              borderRadius: "8px",
              cursor: "pointer",
              boxShadow: "0 4px 12px rgba(2, 132, 199, 0.3)",
            }}
            onClick={handleDownloadAgent}
            disabled={downloadingAgent}
          >
            {downloadingAgent ? (
              "Preparing Download..."
            ) : (
              <>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                  <polyline points="7 10 12 15 17 10" />
                  <line x1="12" y1="15" x2="12" y2="3" />
                </svg>
                Download Nanvi_Assistant.bat (1-Click)
              </>
            )}
          </button>
        </div>

        {/* Clear Explanations & Setup Guide for 50-60 Year Old Users */}
        <div
          style={{
            marginTop: "20px",
            padding: "20px",
            background: "#f8fafc",
            borderRadius: "12px",
            border: "1px solid #e2e8f0",
          }}
        >
          <div style={{ fontSize: "1rem", fontWeight: 700, color: "#1e293b", marginBottom: "14px" }}>
            📘 Clear Guide & Instructions (Simple 3 Steps):
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "16px" }}>
            {/* Box 1: Why download */}
            <div style={{ padding: "14px", background: "#ffffff", borderRadius: "10px", border: "1px solid #cbd5e1" }}>
              <div style={{ fontWeight: 700, fontSize: "0.92rem", color: "#0369a1", marginBottom: "6px" }}>
                1. Why do I need to download this file?
              </div>
              <p style={{ margin: 0, fontSize: "0.86rem", color: "#475569", lineHeight: 1.5 }}>
                <strong>Privacy &amp; Security:</strong> Web browsers are built to protect you and are strictly blocked from reading your personal C:\ or D:\ drive without permission. This small helper runs on your PC and acts as a safe, private bridge, reading only the folders you approve.
              </p>
            </div>

            {/* Box 2: Why and how to open */}
            <div style={{ padding: "14px", background: "#ffffff", borderRadius: "10px", border: "1px solid #cbd5e1" }}>
              <div style={{ fontWeight: 700, fontSize: "0.92rem", color: "#0369a1", marginBottom: "6px" }}>
                2. How do I open it?
              </div>
              <p style={{ margin: 0, fontSize: "0.86rem", color: "#475569", lineHeight: 1.5 }}>
                Click the blue <strong>&quot;Download Nanvi_Assistant.bat&quot;</strong> button above. When it finishes downloading, double-click it in your <strong>Downloads</strong> folder. If Windows shows a blue alert (<em>&quot;Windows protected your PC&quot;</em>), simply click <strong>&quot;More info&quot;</strong> and then <strong>&quot;Run anyway&quot;</strong>.
              </p>
            </div>

            {/* Box 3: What happens & how to put folder */}
            <div style={{ padding: "14px", background: "#ffffff", borderRadius: "10px", border: "1px solid #cbd5e1" }}>
              <div style={{ fontWeight: 700, fontSize: "0.92rem", color: "#0369a1", marginBottom: "6px" }}>
                3. How do I select my folder?
              </div>
              <p style={{ margin: 0, fontSize: "0.86rem", color: "#475569", lineHeight: 1.5 }}>
                A clean white window will open on your screen with a big button: <strong>&quot;📂 Click Here to Select a Folder to Search...&quot;</strong>. Click it and pick any folder from your computer. You can also pick folders directly from this webpage below!
              </p>
            </div>
          </div>
        </div>

        {/* Folder Selection Section */}
        <div style={{ marginTop: "22px", padding: "20px", background: "#f8fafc", borderRadius: "12px", border: "1px solid #e2e8f0" }}>
          <div style={{ fontSize: "1rem", fontWeight: 700, color: "#0f172a", marginBottom: "6px" }}>
            Select Folders for Nanvi to Search:
          </div>
          <p style={{ margin: "0 0 14px", fontSize: "0.88rem", color: "#475569" }}>
            Choose a common folder below or paste any specific folder path from your computer.
          </p>

          {/* Preset Buttons for Easy 1-Click Adding */}
          <div style={{ display: "flex", flexWrap: "wrap", gap: "10px", marginBottom: "14px" }}>
            <span style={{ fontSize: "0.86rem", fontWeight: 600, color: "#475569", alignSelf: "center", marginRight: "4px" }}>1-Click Add:</span>
            <button
              className="folder-picker-btn"
              style={{ fontSize: "0.88rem", fontWeight: 600, padding: "7px 14px", background: "#ffffff", color: "#0f172a", border: "1px solid #cbd5e1", borderRadius: "6px", cursor: "pointer" }}
              onClick={() => handleQuickAdd("C:\\Users\\%USERNAME%\\Documents")}
              disabled={addingFolder}
              title="Add Documents folder"
            >
              📁 Documents
            </button>
            <button
              className="folder-picker-btn"
              style={{ fontSize: "0.88rem", fontWeight: 600, padding: "7px 14px", background: "#ffffff", color: "#0f172a", border: "1px solid #cbd5e1", borderRadius: "6px", cursor: "pointer" }}
              onClick={() => handleQuickAdd("C:\\Users\\%USERNAME%\\Desktop")}
              disabled={addingFolder}
              title="Add Desktop folder"
            >
              📁 Desktop
            </button>
            <button
              className="folder-picker-btn"
              style={{ fontSize: "0.88rem", fontWeight: 600, padding: "7px 14px", background: "#ffffff", color: "#0f172a", border: "1px solid #cbd5e1", borderRadius: "6px", cursor: "pointer" }}
              onClick={() => handleQuickAdd("C:\\Users\\%USERNAME%\\Downloads")}
              disabled={addingFolder}
              title="Add Downloads folder"
            >
              📁 Downloads
            </button>
            <button
              className="folder-picker-btn"
              style={{ fontSize: "0.88rem", fontWeight: 600, padding: "7px 14px", background: "#ffffff", color: "#0f172a", border: "1px solid #cbd5e1", borderRadius: "6px", cursor: "pointer" }}
              onClick={() => handleQuickAdd("CompanyData")}
              disabled={addingFolder}
              title="Add CompanyData folder"
            >
              📁 CompanyData
            </button>
          </div>

          {/* Custom Path Input Row */}
          <div style={{ display: "flex", gap: "10px", flexWrap: "wrap" }}>
            <input
              type="text"
              className="folder-picker-input"
              style={{
                flex: 1,
                minWidth: "280px",
                fontSize: "0.92rem",
                padding: "10px 14px",
                background: "#ffffff",
                color: "#0f172a",
                border: "1px solid #cbd5e1",
                borderRadius: "6px",
              }}
              placeholder="Paste folder path here, e.g. C:\CompanyData or C:\Users\haris\Documents"
              value={customLocalFolder}
              onChange={(e) => setCustomLocalFolder(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") void handleAddLocalFolder();
              }}
            />
            <button
              className="folder-picker-btn"
              onClick={() => void handleAddLocalFolder()}
              disabled={addingFolder || !customLocalFolder.trim()}
              style={{
                padding: "10px 20px",
                fontSize: "0.92rem",
                fontWeight: 700,
                background: "#0284c7",
                color: "#ffffff",
                border: "none",
                borderRadius: "6px",
                whiteSpace: "nowrap",
                cursor: "pointer",
              }}
            >
              {addingFolder ? "Adding..." : "+ Add Folder"}
            </button>
          </div>

          <div style={{ marginTop: "6px", fontSize: "0.82rem", color: "#64748b" }}>
            💡 Tip: You only need the folder path itself. No need to type &quot;add&quot;.
          </div>

          {addFolderMsg && (
            <div
              style={{
                marginTop: "12px",
                fontSize: "0.9rem",
                fontWeight: 600,
                color:
                  addFolderMsg.startsWith("✓") ||
                  addFolderMsg.toLowerCase().includes("added") ||
                  addFolderMsg.toLowerCase().includes("registered")
                    ? "#16a34a"
                    : "#dc2626",
              }}
            >
              {addFolderMsg}
            </div>
          )}
        </div>

        {/* Connected Folders List */}
        <div style={{ marginTop: "22px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "10px" }}>
            <span style={{ fontSize: "0.95rem", fontWeight: 700, color: "#1e293b" }}>
              Connected Folders on Your Machine ({agentStatus?.connected_folders?.length || 0}):
            </span>
            {agentStatus && agentStatus.total_files > 0 && (
              <span style={{ fontSize: "0.85rem", fontWeight: 600, color: "#0284c7" }}>
                {agentStatus.total_files} files ({agentStatus.total_chunks} chunks ready)
              </span>
            )}
          </div>

          {agentStatus?.connected_folders && agentStatus.connected_folders.length > 0 ? (
            <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
              {agentStatus.connected_folders.map((folder) => (
                <div
                  key={folder.folder_id}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    padding: "14px 18px",
                    background: "#f8fafc",
                    border: "1px solid #cbd5e1",
                    borderRadius: "10px",
                  }}
                >
                  <div>
                    <div style={{ fontWeight: 700, fontSize: "0.95rem", color: "#0f172a" }}>
                      📁 {folder.display_name}
                    </div>
                    <code style={{ fontSize: "0.8rem", color: "#475569" }}>{folder.folder_path}</code>
                    <div style={{ marginTop: "4px", fontSize: "0.8rem", color: "#16a34a", fontWeight: 600 }}>
                      {folder.file_count} files • {folder.chunk_count} chunks • Status: {folder.status}
                    </div>
                  </div>
                  <button
                    className="folder-picker-btn"
                    style={{
                      background: "#fee2e2",
                      color: "#dc2626",
                      border: "1px solid #fca5a5",
                      fontSize: "0.85rem",
                      fontWeight: 600,
                      padding: "6px 14px",
                      borderRadius: "6px",
                      cursor: "pointer",
                    }}
                    onClick={() => handleDisconnectFolder(folder.folder_id)}
                  >
                    Disconnect
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ padding: "18px", textAlign: "center", color: "#64748b", background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: "10px", fontSize: "0.9rem" }}>
              No local folders connected yet. Download and run <strong>Nanvi_Assistant.bat</strong> above to connect any folder.
            </div>
          )}
        </div>

        {/* Collapsible Advanced Command-Line Details */}
        <div style={{ marginTop: "16px", textAlign: "right" }}>
          <button
            type="button"
            style={{
              background: "none",
              border: "none",
              color: "#64748b",
              fontSize: "0.82rem",
              cursor: "pointer",
              textDecoration: "underline",
              padding: 0,
            }}
            onClick={() => {
              setShowAdvancedCli(!showAdvancedCli);
              if (!pairingToken) fetchPairingToken();
            }}
          >
            {showAdvancedCli ? "Hide Technical Details" : "⚙️ Advanced Technical Details (For IT Admins)"}
          </button>
        </div>

        {showAdvancedCli && pairingToken && (
          <div style={{ marginTop: "10px", padding: "14px", background: "#f8fafc", borderRadius: "8px", border: "1px solid #cbd5e1" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
              <span style={{ fontSize: "0.82rem", fontWeight: 600, color: "#334155" }}>Personal Pairing Token:</span>
              <button
                className="folder-picker-btn"
                style={{ padding: "4px 10px", fontSize: "0.75rem", background: "#ffffff", border: "1px solid #cbd5e1", borderRadius: "4px", cursor: "pointer" }}
                onClick={() => {
                  navigator.clipboard.writeText(pairingToken);
                  setTokenCopied(true);
                  setTimeout(() => setTokenCopied(false), 2500);
                }}
              >
                {tokenCopied ? "✓ Copied!" : "Copy Token"}
              </button>
            </div>
            <code style={{ display: "block", padding: "8px 10px", background: "#ffffff", border: "1px solid #e2e8f0", borderRadius: "4px", fontSize: "0.75rem", wordBreak: "break-all", color: "#0369a1" }}>
              {pairingToken}
            </code>
          </div>
        )}

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
