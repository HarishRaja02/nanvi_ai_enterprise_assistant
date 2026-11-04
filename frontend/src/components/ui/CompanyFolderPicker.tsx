import { useCallback, useEffect, useRef, useState } from "react";
import type { NanviApiClient, LocalAgentStatusResponse } from "../../api";

type Props = {
  api: NanviApiClient;
};

export function CompanyFolderPicker({ api }: Props) {
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [message, setMessage] = useState<{ text: string; type: "success" | "error" } | null>(null);

  // Local Agent state
  const [agentStatus, setAgentStatus] = useState<LocalAgentStatusResponse | null>(null);
  const [pairingToken, setPairingToken] = useState<string | null>(null);
  const isDesktop = typeof window !== "undefined" && Boolean(window.electronAPI?.isDesktop);
  const [connectMethod, setConnectMethod] = useState<"browse" | "manual" | "bat">(
    isDesktop ? "browse" : "manual"
  );
  const [customLocalFolder, setCustomLocalFolder] = useState("");
  const [addingFolder, setAddingFolder] = useState(false);
  const [browsingFolder, setBrowsingFolder] = useState(false);
  const [disconnectingId, setDisconnectingId] = useState<string | null>(null);
  const [addFolderMsg, setAddFolderMsg] = useState<string | null>(null);
  const [downloadingAgent, setDownloadingAgent] = useState(false);
  const [showAdvancedCli, setShowAdvancedCli] = useState(false);

  const rapidPollRef = useRef<number | null>(null);
  const lastDispatchedRef = useRef<string>("");

  const fetchStatus = useCallback(async () => {
    try {
      const res = await api.getLocalAgentStatus();
      setAgentStatus(res);
      // Only dispatch update if folder state actually changed to avoid constant root App re-renders
      const primary = res.connected_folders && res.connected_folders.length > 0 ? res.connected_folders[0] : null;
      const path = primary ? primary.folder_path : "";
      const exists = Boolean(primary);
      const folder_count = res.connected_folders ? res.connected_folders.length : 0;
      const file_count = res.total_files || 0;
      const signature = `${path}|${exists}|${folder_count}|${file_count}`;

      if (lastDispatchedRef.current !== signature) {
        lastDispatchedRef.current = signature;
        window.dispatchEvent(
          new CustomEvent("nanvi:company-folder-updated", {
            detail: { path, exists, folder_count, file_count },
          })
        );
      }
      return res;
    } catch {
      return null;
    }
  }, [api]);

  // Initial load
  useEffect(() => {
    let cancelled = false;
    fetchStatus().finally(() => {
      if (!cancelled) setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [fetchStatus]);

  // Polling: 4000ms when waiting for connection/syncing, 8000ms when online and idle
  useEffect(() => {
    let timer: NodeJS.Timeout;

    const scheduleNext = () => {
      const isOnline = Boolean(agentStatus?.is_online);
      const delay = isOnline ? 8000 : 4000;
      timer = setTimeout(() => {
        void fetchStatus().then(() => {
          scheduleNext();
        });
      }, delay);
    };

    scheduleNext();

    // Re-check immediately on window focus or tab visibility
    const onVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        void fetchStatus();
      }
    };
    window.addEventListener("focus", onVisibilityChange);
    document.addEventListener("visibilitychange", onVisibilityChange);

    return () => {
      clearTimeout(timer);
      window.removeEventListener("focus", onVisibilityChange);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [fetchStatus, agentStatus?.is_online]);

  // Start temporary rapid polling (1s interval) for 8 seconds after an action
  const triggerRapidPoll = useCallback(() => {
    if (rapidPollRef.current) clearInterval(rapidPollRef.current);
    let count = 0;
    const interval = window.setInterval(() => {
      count++;
      void fetchStatus();
      if (count >= 8) {
        clearInterval(interval);
        rapidPollRef.current = null;
      }
    }, 1000);
    rapidPollRef.current = interval;
  }, [fetchStatus]);

  const handleManualRefresh = async () => {
    setRefreshing(true);
    setMessage(null);
    try {
      await fetchStatus();
      setMessage({ text: "Status refreshed.", type: "success" });
    } catch {
      setMessage({ text: "Could not refresh status.", type: "error" });
    } finally {
      setRefreshing(false);
    }
  };

  const fetchPairingToken = async () => {
    try {
      const res = await api.getLocalAgentToken();
      setPairingToken(res.token);
    } catch (err) {
      setMessage({
        text: err instanceof Error ? err.message : "Failed to generate pairing token.",
        type: "error",
      });
    }
  };

  const handleDisconnectFolder = async (folderId: string) => {
    if (!folderId) return;
    setDisconnectingId(folderId);
    setMessage(null);

    // Optimistically update local UI state immediately
    const norm = folderId.replace(/\\/g, "/").toLowerCase();
    const baseNorm = norm.split("/").pop() || norm;
    setAgentStatus((prev) => {
      if (!prev) return prev;
      const updated = (prev.connected_folders || []).filter((f) => {
        const fId = (f.folder_id || "").replace(/\\/g, "/").toLowerCase();
        const fPath = (f.folder_path || "").replace(/\\/g, "/").toLowerCase();
        const fBase = fPath.split("/").pop() || fPath;
        if (fId === norm || fPath === norm || fBase === baseNorm || fId === baseNorm) return false;
        if (norm && (fId.includes(norm) || fPath.includes(norm) || norm.includes(fId) || norm.includes(fPath))) return false;
        return true;
      });
      return {
        ...prev,
        connected_folders: updated,
        total_files: updated.length === 0 ? 0 : updated.reduce((acc, x) => acc + (x.file_count || 0), 0),
        total_chunks: updated.length === 0 ? 0 : updated.reduce((acc, x) => acc + (x.chunk_count || 0), 0),
      };
    });

    // Notify the rest of the application (TopBar, ContextPanel, Sidebar)
    window.dispatchEvent(
      new CustomEvent("nanvi:company-folder-updated", {
        detail: { path: "", exists: false, folder_count: 0, file_count: 0 },
      })
    );

    try {
      await api.removeLocalFolder(folderId);
      await fetchStatus();
      triggerRapidPoll();
      setMessage({ text: "✓ Folder removed and disconnected successfully.", type: "success" });
    } catch (err: any) {
      await fetchStatus();
      setMessage({
        text: err?.message || "Failed to disconnect folder.",
        type: "error",
      });
    } finally {
      setDisconnectingId(null);
    }
  };

  const handleAddLocalFolder = async (pathToAdd?: string) => {
    let raw = (pathToAdd || customLocalFolder).trim();
    if (!raw) return;

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

    // Block any accidental server-side paths
    if (clean.toLowerCase().includes("/var/task") || clean.toLowerCase().includes("var/task")) {
      setAddFolderMsg("Server path /var/task/CompanyData is disabled. Please select a local folder from your computer.");
      return;
    }

    setAddingFolder(true);
    setAddFolderMsg(null);
    try {
      const res = await api.addLocalFolder(clean);
      setAddFolderMsg(res.message || `✓ Folder '${clean}' added. Starting indexing...`);
      setCustomLocalFolder("");
      triggerRapidPoll();
    } catch (err: any) {
      setAddFolderMsg(`Error: ${err?.message || "Failed to add folder"}`);
    } finally {
      setAddingFolder(false);
    }
  };

  const handleBrowseFolder = async () => {
    // 1. Native Desktop File Picker (when running in the Desktop Application)
    if (typeof window !== "undefined" && window.electronAPI?.selectFolder) {
      setBrowsingFolder(true);
      setAddFolderMsg(null);
      try {
        const selected = await window.electronAPI.selectFolder();
        if (selected) {
          setCustomLocalFolder(selected);
          setAddingFolder(true);
          const res = await api.addLocalFolder(selected);
          setAddFolderMsg(res.message || `✓ Folder '${selected}' linked to Nanvi Assistant.`);
          triggerRapidPoll();
        }
      } catch (err: any) {
        setAddFolderMsg(`Error selecting folder: ${err?.message || "Failed to select folder"}`);
      } finally {
        setBrowsingFolder(false);
        setAddingFolder(false);
      }
      return;
    }

    // 2. Web Browser Fallback (requires local agent script)
    if (!agentStatus?.is_online) {
      setMessage({
        text: "The Nanvi Assistant agent is not currently connected. Please download and double-click Nanvi_Assistant.bat first so it can launch the Windows Explorer dialog.",
        type: "error",
      });
      return;
    }
    setBrowsingFolder(true);
    setAddFolderMsg(null);
    try {
      const res = await api.browseLocalFolder();
      setAddFolderMsg(res.message || "✓ Windows Explorer Folder Picker launched! Please select any folder on your computer screen.");
      triggerRapidPoll();
    } catch (err: any) {
      setAddFolderMsg(`Error opening folder browser: ${err?.message || "Failed to trigger folder browser"}`);
    } finally {
      setTimeout(() => setBrowsingFolder(false), 5000);
    }
  };

  const handleDownloadAgent = async () => {
    setDownloadingAgent(true);
    try {
      await api.downloadLocalAgentPackage(pairingToken || undefined);
      setMessage({
        text: "✓ Nanvi_Assistant.bat downloaded! Double-click it on your Windows computer to start.",
        type: "success",
      });
      triggerRapidPoll();
    } catch (err: any) {
      setMessage({
        text: `Download failed: ${err?.message || "Please try again."}`,
        type: "error",
      });
    } finally {
      setDownloadingAgent(false);
    }
  };

  if (loading) {
    return (
      <div className="folder-picker">
        <div className="folder-picker-loading">
          <div className="folder-picker-spinner" />
          <span>Connecting to company folder agent…</span>
        </div>
      </div>
    );
  }

  const isOnline = Boolean(agentStatus?.is_online) || isDesktop || (agentStatus?.connected_folders?.length || 0) > 0;
  const connectedFolders = agentStatus?.connected_folders || [];
  const totalFiles = agentStatus?.total_files || 0;
  const totalChunks = agentStatus?.total_chunks || 0;

  return (
    <div className="folder-picker" style={{ maxWidth: "100%", padding: 0 }}>
      {/* Main Header */}
      <div
        className="folder-picker-header"
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "16px",
          paddingBottom: "18px",
          borderBottom: "1px solid #e2e8f0",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "14px" }}>
          <div className="folder-picker-icon" style={{ background: "#0284c7", color: "#ffffff" }}>
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
            </svg>
          </div>
          <div>
            <h3 className="folder-picker-title" style={{ fontSize: "1.3rem", fontWeight: 700, margin: 0, color: "#0f172a" }}>
              Company Data Folders
            </h3>
            <p className="folder-picker-subtitle" style={{ margin: "4px 0 0", color: "#64748b", fontSize: "0.9rem" }}>
              Connect local computer folders for Nanvi AI Assistant to search and reference. All documents stay securely on your computer.
            </p>
          </div>
        </div>

        {/* Top Header Actions */}
        <div style={{ display: "flex", gap: "10px", alignItems: "center", flexWrap: "wrap" }}>
          <button
            type="button"
            className="folder-picker-btn folder-picker-btn-secondary"
            onClick={handleManualRefresh}
            disabled={refreshing}
            style={{
              padding: "9px 16px",
              fontSize: "0.88rem",
              fontWeight: 600,
              display: "inline-flex",
              alignItems: "center",
              gap: "8px",
              cursor: "pointer",
            }}
            title="Check live status from local connection"
          >
            <svg
              width="15"
              height="15"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              style={{ animation: refreshing ? "spin 1s linear infinite" : "none" }}
            >
              <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67" />
            </svg>
            {refreshing ? "Refreshing..." : "Refresh Status"}
          </button>

          <button
            type="button"
            className="folder-picker-btn"
            onClick={handleDownloadAgent}
            disabled={downloadingAgent}
            style={{
              padding: "9px 18px",
              fontSize: "0.88rem",
              fontWeight: 600,
              background: "#ffffff",
              color: "#0369a1",
              border: "1.5px solid #bae6fd",
              borderRadius: "8px",
              display: "inline-flex",
              alignItems: "center",
              gap: "8px",
              cursor: "pointer",
            }}
            title="Download BAT file for background sync or web use"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="7 10 12 15 17 10" />
              <line x1="12" y1="15" x2="12" y2="3" />
            </svg>
            {downloadingAgent ? "Downloading..." : "Nanvi_Assistant.bat"}
          </button>
        </div>
      </div>

      {/* Status Messages */}
      {message && (
        <div
          className={`folder-picker-message folder-picker-message-${message.type}`}
          style={{ marginTop: "16px", padding: "12px 16px", borderRadius: "8px" }}
        >
          {message.type === "success" ? (
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
              <polyline points="22 4 12 14.01 9 11.01" />
            </svg>
          ) : (
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" />
              <line x1="15" y1="9" x2="9" y2="15" />
              <line x1="9" y1="9" x2="15" y2="15" />
            </svg>
          )}
          {message.text}
        </div>
      )}

      {/* Connection Status Banner */}
      <div
        style={{
          marginTop: "20px",
          padding: "18px 22px",
          background: isOnline ? "#f0fdf4" : "#f8fafc",
          border: `1.5px solid ${isOnline ? "#86efac" : "#cbd5e1"}`,
          borderRadius: "12px",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "14px",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <span
            style={{
              width: "14px",
              height: "14px",
              borderRadius: "50%",
              background: isDesktop ? "#0284c7" : isOnline ? "#16a34a" : "#64748b",
              boxShadow: isDesktop
                ? "0 0 0 4px rgba(2, 132, 199, 0.2)"
                : isOnline
                ? "0 0 0 4px rgba(22, 163, 74, 0.2)"
                : "0 0 0 4px rgba(100, 116, 139, 0.2)",
            }}
          />
          <div>
            <div style={{ fontSize: "1.05rem", fontWeight: 700, color: isDesktop ? "#0369a1" : isOnline ? "#166534" : "#1e293b" }}>
              {isDesktop
                ? "🖥️ Nanvi Desktop Mode: Local Computer Access Active"
                : isOnline
                ? "Connected to Your Windows Computer"
                : "Ready to Connect Folders"}
            </div>
            <div style={{ fontSize: "0.85rem", color: isDesktop ? "#0284c7" : isOnline ? "#15803d" : "#64748b", marginTop: "2px" }}>
              {isDesktop
                ? "Standard Windows Explorer folder picker and direct path entry ready. Zero complex BAT files needed."
                : isOnline
                ? "Agent online • Syncing approved folders from your PC • Heartbeat active"
                : "Choose 1-Click Browse, Manual Path entry, or run Nanvi_Assistant.bat to connect folders."}
            </div>
          </div>
        </div>

        {/* Live Counters */}
        <div style={{ display: "flex", gap: "10px", flexWrap: "wrap" }}>
          <div style={{ padding: "6px 14px", background: "#ffffff", border: "1px solid #cbd5e1", borderRadius: "8px", fontSize: "0.85rem", fontWeight: 600, color: "#334155" }}>
            📁 {connectedFolders.length} Folders
          </div>
          <div style={{ padding: "6px 14px", background: "#ffffff", border: "1px solid #cbd5e1", borderRadius: "8px", fontSize: "0.85rem", fontWeight: 600, color: "#334155" }}>
            📄 {totalFiles} Files
          </div>
          <div style={{ padding: "6px 14px", background: "#ffffff", border: "1px solid #cbd5e1", borderRadius: "8px", fontSize: "0.85rem", fontWeight: 600, color: "#0284c7" }}>
            ⚡ {totalChunks} Searchable Chunks
          </div>
        </div>
      </div>

      {/* Connected Folders List */}
      <div style={{ marginTop: "24px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
          <h4 style={{ margin: 0, fontSize: "1.05rem", fontWeight: 700, color: "#0f172a" }}>
            Connected Folders ({connectedFolders.length}):
          </h4>
          <span style={{ fontSize: "0.82rem", color: "#64748b" }}>
            Only files in these folders are searched by Nanvi AI Assistant
          </span>
        </div>

        {connectedFolders.length > 0 ? (
          <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
            {connectedFolders.map((folder, idx) => {
              const targetId = folder.folder_id || folder.folder_path || "";
              const isRemoving = disconnectingId === targetId;
              return (
                <div
                  key={targetId || idx}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    flexWrap: "wrap",
                    gap: "14px",
                    padding: "18px 22px",
                    background: "#f0fdf4",
                    border: "1.5px solid #86efac",
                    borderLeft: "6px solid #16a34a",
                    borderRadius: "12px",
                    boxShadow: "0 2px 8px rgba(22, 163, 74, 0.08)",
                    transition: "all 0.2s ease",
                  }}
                >
                  <div>
                    <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "4px" }}>
                      <span
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: "6px",
                          padding: "3px 10px",
                          background: "#dcfce7",
                          border: "1px solid #86efac",
                          borderRadius: "20px",
                          color: "#166534",
                          fontSize: "0.78rem",
                          fontWeight: 700,
                          letterSpacing: "0.02em",
                        }}
                      >
                        <span
                          style={{
                            width: "8px",
                            height: "8px",
                            borderRadius: "50%",
                            background: "#16a34a",
                            boxShadow: "0 0 0 2px rgba(22, 163, 74, 0.3)",
                          }}
                        />
                        CONNECTED & ACTIVE
                      </span>
                      <span style={{ fontSize: "0.8rem", color: "#15803d", fontWeight: 500 }}>
                        Searched by Nanvi AI Assistant
                      </span>
                    </div>

                    <div style={{ fontWeight: 700, fontSize: "1.08rem", color: "#0f172a" }}>
                      📁 {folder.display_name || folder.folder_path}
                    </div>
                    <code style={{ fontSize: "0.85rem", color: "#475569", marginTop: "4px", display: "inline-block", background: "#ffffff", padding: "2px 8px", borderRadius: "4px", border: "1px solid #e2e8f0" }}>
                      {folder.folder_path}
                    </code>
                    <div style={{ marginTop: "8px", display: "flex", gap: "12px", alignItems: "center", fontSize: "0.84rem", color: "#166534", fontWeight: 600 }}>
                      <span>✓ {folder.file_count ?? 0} files indexed</span>
                      <span>•</span>
                      <span>⚡ {folder.chunk_count ?? 0} searchable chunks</span>
                    </div>
                  </div>

                  <button
                    type="button"
                    className="folder-picker-btn"
                    style={{
                      background: "#fee2e2",
                      color: "#b91c1c",
                      border: "1.5px solid #fca5a5",
                      fontSize: "0.86rem",
                      fontWeight: 700,
                      padding: "9px 18px",
                      borderRadius: "8px",
                      cursor: isRemoving ? "wait" : "pointer",
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "6px",
                      boxShadow: "0 1px 4px rgba(220, 38, 38, 0.12)",
                      transition: "all 0.15s ease",
                    }}
                    onClick={() => handleDisconnectFolder(targetId)}
                    disabled={isRemoving}
                    title="Disconnect this folder from Nanvi Assistant"
                  >
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="3 6 5 6 21 6" />
                      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                    </svg>
                    {isRemoving ? "Removing..." : "Remove / Disconnect"}
                  </button>
                </div>
              );
            })}
          </div>
        ) : (
          <div
            style={{
              padding: "26px",
              textAlign: "center",
              background: "#f8fafc",
              border: "2px dashed #cbd5e1",
              borderRadius: "12px",
              color: "#475569",
            }}
          >
            <div style={{ fontSize: "2rem", marginBottom: "8px" }}>📂</div>
            <div style={{ fontSize: "1.05rem", fontWeight: 700, color: "#1e293b", marginBottom: "6px" }}>
              No Folders Connected Yet
            </div>
            <p style={{ margin: "0 auto 16px", maxWidth: "560px", fontSize: "0.9rem", color: "#64748b", lineHeight: 1.5 }}>
              Choose any of the 3 easy methods below to connect your local company folder:
            </p>
            <div style={{ display: "flex", justifyContent: "center", gap: "10px", flexWrap: "wrap" }}>
              <button
                type="button"
                className="folder-picker-btn"
                onClick={() => {
                  setConnectMethod("browse");
                  void handleBrowseFolder();
                }}
                disabled={browsingFolder}
                style={{
                  padding: "9px 20px",
                  fontSize: "0.9rem",
                  fontWeight: 700,
                  background: "#0284c7",
                  color: "#ffffff",
                  border: "none",
                  borderRadius: "8px",
                  cursor: "pointer",
                }}
              >
                📁 1-Click Browse (Windows Explorer)
              </button>
              <button
                type="button"
                className="folder-picker-btn"
                onClick={() => setConnectMethod("manual")}
                style={{
                  padding: "9px 20px",
                  fontSize: "0.9rem",
                  fontWeight: 700,
                  background: "#ffffff",
                  color: "#1e293b",
                  border: "1.5px solid #cbd5e1",
                  borderRadius: "8px",
                  cursor: "pointer",
                }}
              >
                ✍️ Enter Path Manually
              </button>
              <button
                type="button"
                className="folder-picker-btn"
                onClick={() => setConnectMethod("bat")}
                style={{
                  padding: "9px 20px",
                  fontSize: "0.9rem",
                  fontWeight: 700,
                  background: "#ffffff",
                  color: "#0369a1",
                  border: "1.5px solid #bae6fd",
                  borderRadius: "8px",
                  cursor: "pointer",
                }}
              >
                ⚡ Background Agent (.bat)
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Choose Connection Method Section */}
      <div
        style={{
          marginTop: "28px",
          padding: "24px",
          background: "#ffffff",
          borderRadius: "14px",
          border: "1px solid #e2e8f0",
          boxShadow: "0 2px 8px rgba(0, 0, 0, 0.04)",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "12px", marginBottom: "18px" }}>
          <div>
            <div style={{ fontSize: "1.08rem", fontWeight: 700, color: "#0f172a" }}>
              Connect a Local Folder
            </div>
            <div style={{ fontSize: "0.85rem", color: "#64748b", marginTop: "2px" }}>
              Select your preferred folder connection method below:
            </div>
          </div>

          {/* 3 Dedicated Method Selector Tabs */}
          <div style={{ display: "inline-flex", background: "#f1f5f9", padding: "4px", borderRadius: "10px", gap: "4px" }}>
            <button
              type="button"
              onClick={() => setConnectMethod("browse")}
              style={{
                padding: "8px 16px",
                fontSize: "0.86rem",
                fontWeight: 700,
                border: "none",
                borderRadius: "8px",
                cursor: "pointer",
                background: connectMethod === "browse" ? "#ffffff" : "transparent",
                color: connectMethod === "browse" ? "#0284c7" : "#475569",
                boxShadow: connectMethod === "browse" ? "0 2px 6px rgba(0, 0, 0, 0.08)" : "none",
                transition: "all 0.15s ease",
              }}
            >
              📁 Method 1: Windows Explorer (1-Click)
            </button>
            <button
              type="button"
              onClick={() => setConnectMethod("manual")}
              style={{
                padding: "8px 16px",
                fontSize: "0.86rem",
                fontWeight: 700,
                border: "none",
                borderRadius: "8px",
                cursor: "pointer",
                background: connectMethod === "manual" ? "#ffffff" : "transparent",
                color: connectMethod === "manual" ? "#2563eb" : "#475569",
                boxShadow: connectMethod === "manual" ? "0 2px 6px rgba(0, 0, 0, 0.08)" : "none",
                transition: "all 0.15s ease",
              }}
            >
              ✍️ Method 2: Manual Path Input
            </button>
            <button
              type="button"
              onClick={() => setConnectMethod("bat")}
              style={{
                padding: "8px 16px",
                fontSize: "0.86rem",
                fontWeight: 700,
                border: "none",
                borderRadius: "8px",
                cursor: "pointer",
                background: connectMethod === "bat" ? "#ffffff" : "transparent",
                color: connectMethod === "bat" ? "#0369a1" : "#475569",
                boxShadow: connectMethod === "bat" ? "0 2px 6px rgba(0, 0, 0, 0.08)" : "none",
                transition: "all 0.15s ease",
              }}
            >
              ⚡ Method 3: Background Agent (.bat)
            </button>
          </div>
        </div>

        {/* Tab 1: 📁 Windows Explorer (1-Click Easy Way) */}
        {connectMethod === "browse" && (
          <div
            style={{
              padding: "24px",
              background: "#f0f9ff",
              border: "1.5px solid #bae6fd",
              borderRadius: "12px",
              textAlign: "center",
            }}
          >
            <div style={{ fontSize: "1.1rem", fontWeight: 700, color: "#0369a1", marginBottom: "6px" }}>
              📁 1-Click Folder Picker (Easy Way)
            </div>
            <p style={{ margin: "0 auto 20px", maxWidth: "580px", fontSize: "0.9rem", color: "#0284c7", lineHeight: 1.5 }}>
              Click the button below to launch the native Windows Explorer dialog. Simply pick any folder on your PC and Nanvi Assistant links it immediately — no command line or script required!
            </p>

            <button
              type="button"
              className="folder-picker-btn"
              onClick={handleBrowseFolder}
              disabled={browsingFolder}
              style={{
                padding: "14px 32px",
                fontSize: "1.05rem",
                fontWeight: 700,
                background: "#0284c7",
                color: "#ffffff",
                border: "none",
                borderRadius: "10px",
                cursor: browsingFolder ? "wait" : "pointer",
                boxShadow: "0 4px 16px rgba(2, 132, 199, 0.3)",
                display: "inline-flex",
                alignItems: "center",
                gap: "10px",
                transition: "all 0.2s ease",
              }}
            >
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
              </svg>
              {browsingFolder ? "Opening Windows Explorer on your PC..." : "Open Windows Explorer & Select Folder"}
            </button>

            <div style={{ marginTop: "12px", fontSize: "0.82rem", color: "#64748b" }}>
              {isDesktop
                ? "✓ Running in Nanvi Desktop App: Folder dialog opens directly on your computer."
                : isOnline
                ? "✓ Local agent online: Explorer dialog opens on your computer screen."
                : "💡 Running in web browser? Double-click Nanvi_Assistant.bat or use Tab 2 (Manual Path) if browse does not open."}
            </div>
          </div>
        )}

        {/* Tab 2: ✍️ Manual Folder Path Input */}
        {connectMethod === "manual" && (
          <div
            style={{
              padding: "24px",
              background: "#f8fafc",
              border: "1.5px solid #e2e8f0",
              borderRadius: "12px",
            }}
          >
            <div style={{ fontSize: "1.1rem", fontWeight: 700, color: "#1e293b", marginBottom: "6px" }}>
              ✍️ Enter or Paste Folder Path Manually
            </div>
            <p style={{ margin: "0 0 18px", fontSize: "0.88rem", color: "#64748b", lineHeight: 1.5 }}>
              Type or paste any directory path on your computer (e.g. <code>C:\CompanyData</code> or <code>D:\Projects\Invoices</code>), or pick a 1-click preset.
            </p>

            {/* Custom Path Input Row */}
            <div style={{ display: "flex", gap: "10px", flexWrap: "wrap", marginBottom: "16px" }}>
              <input
                type="text"
                className="folder-picker-input"
                style={{
                  flex: 1,
                  minWidth: "300px",
                  fontSize: "0.95rem",
                  padding: "12px 16px",
                  background: "#ffffff",
                  color: "#0f172a",
                  border: "1.5px solid #cbd5e1",
                  borderRadius: "8px",
                }}
                placeholder="Paste or type path, e.g. C:\CompanyData or C:\Users\Username\Documents"
                value={customLocalFolder}
                onChange={(e) => setCustomLocalFolder(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") void handleAddLocalFolder();
                }}
              />
              <button
                type="button"
                className="folder-picker-btn"
                onClick={() => void handleAddLocalFolder()}
                disabled={addingFolder || !customLocalFolder.trim()}
                style={{
                  padding: "12px 26px",
                  fontSize: "0.95rem",
                  fontWeight: 700,
                  background: "#2563eb",
                  color: "#ffffff",
                  border: "none",
                  borderRadius: "8px",
                  cursor: addingFolder || !customLocalFolder.trim() ? "not-allowed" : "pointer",
                  whiteSpace: "nowrap",
                  boxShadow: "0 2px 8px rgba(37, 99, 235, 0.25)",
                }}
              >
                {addingFolder ? "Connecting & Indexing..." : "+ Connect Folder Path"}
              </button>
            </div>

            {/* 1-Click Quick Presets */}
            <div style={{ display: "flex", flexWrap: "wrap", gap: "10px", alignItems: "center" }}>
              <span style={{ fontSize: "0.86rem", fontWeight: 700, color: "#475569", marginRight: "4px" }}>
                1-Click Presets:
              </span>
              <button
                type="button"
                className="folder-picker-btn"
                style={{ fontSize: "0.86rem", fontWeight: 600, padding: "8px 16px", background: "#ffffff", color: "#0f172a", border: "1px solid #cbd5e1", borderRadius: "6px", cursor: "pointer" }}
                onClick={() => handleAddLocalFolder("C:\\Users\\%USERNAME%\\Documents")}
                disabled={addingFolder}
                title="Connect Documents folder"
              >
                📁 Documents
              </button>
              <button
                type="button"
                className="folder-picker-btn"
                style={{ fontSize: "0.86rem", fontWeight: 600, padding: "8px 16px", background: "#ffffff", color: "#0f172a", border: "1px solid #cbd5e1", borderRadius: "6px", cursor: "pointer" }}
                onClick={() => handleAddLocalFolder("C:\\Users\\%USERNAME%\\Desktop")}
                disabled={addingFolder}
                title="Connect Desktop folder"
              >
                📁 Desktop
              </button>
              <button
                type="button"
                className="folder-picker-btn"
                style={{ fontSize: "0.86rem", fontWeight: 600, padding: "8px 16px", background: "#ffffff", color: "#0f172a", border: "1px solid #cbd5e1", borderRadius: "6px", cursor: "pointer" }}
                onClick={() => handleAddLocalFolder("C:\\Users\\%USERNAME%\\Downloads")}
                disabled={addingFolder}
                title="Connect Downloads folder"
              >
                📁 Downloads
              </button>
              <button
                type="button"
                className="folder-picker-btn"
                style={{ fontSize: "0.86rem", fontWeight: 600, padding: "8px 16px", background: "#ffffff", color: "#0f172a", border: "1px solid #cbd5e1", borderRadius: "6px", cursor: "pointer" }}
                onClick={() => handleAddLocalFolder("D:\\")}
                disabled={addingFolder}
                title="Connect D:\ Drive"
              >
                💾 D:\ Drive
              </button>
            </div>
          </div>
        )}

        {/* Tab 3: ⚡ Background Sync Agent (.bat file way) */}
        {connectMethod === "bat" && (
          <div
            style={{
              padding: "24px",
              background: "#fffbeb",
              border: "1.5px solid #fde68a",
              borderRadius: "12px",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "16px", marginBottom: "18px" }}>
              <div>
                <div style={{ fontSize: "1.1rem", fontWeight: 700, color: "#92400e", marginBottom: "4px" }}>
                  ⚡ Background Sync Agent (Nanvi_Assistant.bat)
                </div>
                <p style={{ margin: 0, fontSize: "0.88rem", color: "#b45309", maxWidth: "600px", lineHeight: 1.5 }}>
                  The BAT file connector runs as a lightweight background service on Windows. It keeps your files continuously synchronized with Nanvi and enables Windows Explorer dialogs from the web browser.
                </p>
              </div>

              <button
                type="button"
                className="folder-picker-btn"
                onClick={handleDownloadAgent}
                disabled={downloadingAgent}
                style={{
                  padding: "11px 22px",
                  fontSize: "0.92rem",
                  fontWeight: 700,
                  background: "#d97706",
                  color: "#ffffff",
                  border: "none",
                  borderRadius: "8px",
                  cursor: "pointer",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "8px",
                  boxShadow: "0 2px 8px rgba(217, 119, 6, 0.3)",
                }}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                  <polyline points="7 10 12 15 17 10" />
                  <line x1="12" y1="15" x2="12" y2="3" />
                </svg>
                {downloadingAgent ? "Preparing Download..." : "Download Nanvi_Assistant.bat"}
              </button>
            </div>

            {/* 3-Step Setup Cards */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: "14px", marginTop: "14px" }}>
              <div style={{ padding: "14px", background: "#ffffff", borderRadius: "8px", border: "1px solid #fef3c7" }}>
                <div style={{ fontWeight: 700, fontSize: "0.88rem", color: "#92400e", marginBottom: "4px" }}>
                  1. Download Script
                </div>
                <p style={{ margin: 0, fontSize: "0.82rem", color: "#78350f", lineHeight: 1.45 }}>
                  Click <strong>&quot;Download Nanvi_Assistant.bat&quot;</strong>. The file will save directly into your Downloads folder.
                </p>
              </div>

              <div style={{ padding: "14px", background: "#ffffff", borderRadius: "8px", border: "1px solid #fef3c7" }}>
                <div style={{ fontWeight: 700, fontSize: "0.88rem", color: "#92400e", marginBottom: "4px" }}>
                  2. Double-Click to Start
                </div>
                <p style={{ margin: 0, fontSize: "0.82rem", color: "#78350f", lineHeight: 1.45 }}>
                  Double-click <strong>Nanvi_Assistant.bat</strong>. It connects to Nanvi and displays live status in a clean window.
                </p>
              </div>

              <div style={{ padding: "14px", background: "#ffffff", borderRadius: "8px", border: "1px solid #fef3c7" }}>
                <div style={{ fontWeight: 700, fontSize: "0.88rem", color: "#92400e", marginBottom: "4px" }}>
                  3. Select & Sync Folders
                </div>
                <p style={{ margin: 0, fontSize: "0.82rem", color: "#78350f", lineHeight: 1.45 }}>
                  Pick folders from Windows Explorer or enter paths above. The agent continuously monitors for file changes!
                </p>
              </div>
            </div>

            {/* Advanced Technical Details */}
            <div style={{ marginTop: "16px", textAlign: "right" }}>
              <button
                type="button"
                style={{
                  background: "none",
                  border: "none",
                  color: "#92400e",
                  fontSize: "0.82rem",
                  cursor: "pointer",
                  textDecoration: "underline",
                  padding: 0,
                }}
                onClick={() => {
                  setShowAdvancedCli(!showAdvancedCli);
                  if (!pairingToken) void fetchPairingToken();
                }}
              >
                {showAdvancedCli ? "Hide Technical Details" : "⚙️ Advanced Technical Details (For IT Admins)"}
              </button>

              {showAdvancedCli && (
                <div
                  style={{
                    marginTop: "12px",
                    padding: "16px",
                    background: "#0f172a",
                    color: "#f8fafc",
                    borderRadius: "8px",
                    textAlign: "left",
                    fontSize: "0.82rem",
                    fontFamily: "Consolas, monospace",
                  }}
                >
                  <div style={{ color: "#38bdf8", fontWeight: 700, marginBottom: "8px" }}>
                    Manual CLI Connection Command:
                  </div>
                  <div style={{ background: "#1e293b", padding: "10px", borderRadius: "6px", wordBreak: "break-all" }}>
                    python nanvi_local_agent.py --server {window.location.origin} --token {pairingToken || "..."}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Global Action Feedback Message */}
        {addFolderMsg && (
          <div
            style={{
              marginTop: "16px",
              padding: "12px 16px",
              borderRadius: "8px",
              fontSize: "0.9rem",
              fontWeight: 600,
              background: addFolderMsg.startsWith("✓") || addFolderMsg.toLowerCase().includes("added") || addFolderMsg.toLowerCase().includes("found") ? "#f0fdf4" : "#fef2f2",
              border: `1px solid ${addFolderMsg.startsWith("✓") || addFolderMsg.toLowerCase().includes("added") || addFolderMsg.toLowerCase().includes("found") ? "#bbf7d0" : "#fecaca"}`,
              color: addFolderMsg.startsWith("✓") || addFolderMsg.toLowerCase().includes("added") || addFolderMsg.toLowerCase().includes("found") ? "#15803d" : "#b91c1c",
            }}
          >
            {addFolderMsg}
          </div>
        )}
      </div>
    </div>
  );
}
