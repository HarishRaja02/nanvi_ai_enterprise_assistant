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
  const [customLocalFolder, setCustomLocalFolder] = useState("");
  const [addingFolder, setAddingFolder] = useState(false);
  const [addFolderMsg, setAddFolderMsg] = useState<string | null>(null);
  const [downloadingAgent, setDownloadingAgent] = useState(false);
  const [showAdvancedCli, setShowAdvancedCli] = useState(false);

  const rapidPollRef = useRef<number | null>(null);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await api.getLocalAgentStatus();
      setAgentStatus(res);
      // Dispatch update so other components (e.g. useCompanyFolder) update immediately
      const primary = res.connected_folders && res.connected_folders.length > 0 ? res.connected_folders[0] : null;
      window.dispatchEvent(
        new CustomEvent("nanvi:company-folder-updated", {
          detail: {
            path: primary ? primary.folder_path : "",
            exists: Boolean(primary),
            folder_count: res.connected_folders ? res.connected_folders.length : 0,
            file_count: res.total_files || 0,
          },
        })
      );
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

  // Smooth polling: 1500ms when waiting for connection/syncing, 3500ms when online and idle
  useEffect(() => {
    let timer: NodeJS.Timeout;

    const scheduleNext = () => {
      const isOnline = Boolean(agentStatus?.is_online);
      const delay = isOnline ? 3500 : 1500;
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
    try {
      await api.removeLocalFolder(folderId);
      await fetchStatus();
      triggerRapidPoll();
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

  const isOnline = Boolean(agentStatus?.is_online);
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
              Company Data Folder
            </h3>
            <p className="folder-picker-subtitle" style={{ margin: "4px 0 0", color: "#64748b", fontSize: "0.9rem" }}>
              Only folders connected via the Nanvi Windows BAT file agent are accessed. All documents remain securely on your computer.
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
            title="Check live status from local BAT file agent"
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
            className="folder-picker-btn folder-picker-btn-primary"
            onClick={handleDownloadAgent}
            disabled={downloadingAgent}
            style={{
              padding: "10px 20px",
              fontSize: "0.92rem",
              fontWeight: 700,
              background: "#0284c7",
              color: "#ffffff",
              border: "none",
              borderRadius: "8px",
              display: "inline-flex",
              alignItems: "center",
              gap: "10px",
              cursor: "pointer",
              boxShadow: "0 4px 12px rgba(2, 132, 199, 0.25)",
            }}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="7 10 12 15 17 10" />
              <line x1="12" y1="15" x2="12" y2="3" />
            </svg>
            {downloadingAgent ? "Preparing Download..." : "Download Nanvi_Assistant.bat (1-Click)"}
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

      {/* Live Agent Status Banner */}
      <div
        style={{
          marginTop: "20px",
          padding: "18px 22px",
          background: isOnline ? "#f0fdf4" : "#fffbeb",
          border: `1.5px solid ${isOnline ? "#86efac" : "#fcd34d"}`,
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
              background: isOnline ? "#16a34a" : "#d97706",
              boxShadow: isOnline ? "0 0 0 4px rgba(22, 163, 74, 0.2)" : "0 0 0 4px rgba(217, 119, 6, 0.2)",
            }}
          />
          <div>
            <div style={{ fontSize: "1.05rem", fontWeight: 700, color: isOnline ? "#166534" : "#92400e" }}>
              {isOnline ? "Connected to Your Windows Computer" : "Waiting for Nanvi Assistant BAT File"}
            </div>
            <div style={{ fontSize: "0.85rem", color: isOnline ? "#15803d" : "#b45309", marginTop: "2px" }}>
              {isOnline
                ? `Live agent online • Syncing approved folders from your PC • Heartbeat active`
                : `Download and double-click Nanvi_Assistant.bat to automatically connect your computer`}
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
          <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
            {connectedFolders.map((folder, idx) => (
              <div
                key={folder.folder_id || folder.folder_path || idx}
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  padding: "16px 20px",
                  background: "#ffffff",
                  border: "1px solid #e2e8f0",
                  borderRadius: "10px",
                  boxShadow: "0 2px 6px rgba(0, 0, 0, 0.04)",
                  transition: "all 0.2s ease",
                }}
              >
                <div>
                  <div style={{ fontWeight: 700, fontSize: "1rem", color: "#0f172a" }}>
                    📁 {folder.display_name || folder.folder_path}
                  </div>
                  <code style={{ fontSize: "0.82rem", color: "#64748b", marginTop: "3px", display: "inline-block" }}>
                    {folder.folder_path}
                  </code>
                  <div style={{ marginTop: "6px", display: "flex", gap: "12px", alignItems: "center", fontSize: "0.82rem", color: "#16a34a", fontWeight: 600 }}>
                    <span>✓ {folder.file_count ?? 0} files</span>
                    <span>• {folder.chunk_count ?? 0} chunks</span>
                    <span style={{ padding: "2px 8px", background: "#dcfce7", borderRadius: "12px", fontSize: "0.75rem" }}>
                      Ready
                    </span>
                  </div>
                </div>

                <button
                  type="button"
                  className="folder-picker-btn"
                  style={{
                    background: "#fee2e2",
                    color: "#dc2626",
                    border: "1px solid #fca5a5",
                    fontSize: "0.85rem",
                    fontWeight: 600,
                    padding: "7px 16px",
                    borderRadius: "6px",
                    cursor: "pointer",
                  }}
                  onClick={() => folder.folder_id && handleDisconnectFolder(folder.folder_id)}
                >
                  Disconnect
                </button>
              </div>
            ))}
          </div>
        ) : (
          <div
            style={{
              padding: "28px",
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
            <p style={{ margin: "0 auto 16px", maxWidth: "520px", fontSize: "0.9rem", color: "#64748b", lineHeight: 1.5 }}>
              The system is configured to ONLY access folders from your local Windows computer via the BAT file.
              Download and run <strong>Nanvi_Assistant.bat</strong> to connect your documents folder.
            </p>
            <button
              type="button"
              className="folder-picker-btn"
              onClick={handleDownloadAgent}
              disabled={downloadingAgent}
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
              Download Nanvi_Assistant.bat
            </button>
          </div>
        )}
      </div>

      {/* Add Folder Section */}
      <div
        style={{
          marginTop: "24px",
          padding: "22px",
          background: "#f8fafc",
          borderRadius: "12px",
          border: "1px solid #e2e8f0",
        }}
      >
        <div style={{ fontSize: "1.02rem", fontWeight: 700, color: "#0f172a", marginBottom: "6px" }}>
          Select Folders for Nanvi to Search on Your Machine:
        </div>
        <p style={{ margin: "0 0 14px", fontSize: "0.86rem", color: "#64748b" }}>
          Choose a 1-click preset folder or paste any custom folder path from your computer.
        </p>

        {/* 1-Click Quick Presets */}
        <div style={{ display: "flex", flexWrap: "wrap", gap: "10px", marginBottom: "16px" }}>
          <span style={{ fontSize: "0.85rem", fontWeight: 600, color: "#475569", alignSelf: "center", marginRight: "4px" }}>
            1-Click Add:
          </span>
          <button
            type="button"
            className="folder-picker-btn"
            style={{ fontSize: "0.86rem", fontWeight: 600, padding: "8px 16px", background: "#ffffff", color: "#0f172a", border: "1px solid #cbd5e1", borderRadius: "6px", cursor: "pointer" }}
            onClick={() => handleAddLocalFolder("C:\\Users\\%USERNAME%\\Documents")}
            disabled={addingFolder}
            title="Add Documents folder"
          >
            📁 Documents
          </button>
          <button
            type="button"
            className="folder-picker-btn"
            style={{ fontSize: "0.86rem", fontWeight: 600, padding: "8px 16px", background: "#ffffff", color: "#0f172a", border: "1px solid #cbd5e1", borderRadius: "6px", cursor: "pointer" }}
            onClick={() => handleAddLocalFolder("C:\\Users\\%USERNAME%\\Desktop")}
            disabled={addingFolder}
            title="Add Desktop folder"
          >
            📁 Desktop
          </button>
          <button
            type="button"
            className="folder-picker-btn"
            style={{ fontSize: "0.86rem", fontWeight: 600, padding: "8px 16px", background: "#ffffff", color: "#0f172a", border: "1px solid #cbd5e1", borderRadius: "6px", cursor: "pointer" }}
            onClick={() => handleAddLocalFolder("C:\\Users\\%USERNAME%\\Downloads")}
            disabled={addingFolder}
            title="Add Downloads folder"
          >
            📁 Downloads
          </button>
        </div>

        {/* Custom Folder Input Row */}
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
            placeholder="Paste local folder path, e.g. C:\Projects or D:\CompanyData"
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
              padding: "10px 22px",
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

        {addFolderMsg && (
          <div
            style={{
              marginTop: "12px",
              fontSize: "0.88rem",
              fontWeight: 600,
              color: addFolderMsg.startsWith("✓") || addFolderMsg.toLowerCase().includes("added") ? "#16a34a" : "#dc2626",
            }}
          >
            {addFolderMsg}
          </div>
        )}
      </div>

      {/* Clear 3-Step Setup Instructions */}
      <div
        style={{
          marginTop: "24px",
          padding: "20px",
          background: "#ffffff",
          borderRadius: "12px",
          border: "1px solid #e2e8f0",
        }}
      >
        <div style={{ fontSize: "0.98rem", fontWeight: 700, color: "#1e293b", marginBottom: "14px" }}>
          📘 Simple 3-Step Guide to Use Your Company Folders:
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: "16px" }}>
          <div style={{ padding: "14px", background: "#f8fafc", borderRadius: "10px", border: "1px solid #e2e8f0" }}>
            <div style={{ fontWeight: 700, fontSize: "0.9rem", color: "#0369a1", marginBottom: "6px" }}>
              1. Download Nanvi_Assistant.bat
            </div>
            <p style={{ margin: 0, fontSize: "0.84rem", color: "#475569", lineHeight: 1.5 }}>
              Click the blue <strong>&quot;Download Nanvi_Assistant.bat&quot;</strong> button above. It takes only a few seconds.
            </p>
          </div>

          <div style={{ padding: "14px", background: "#f8fafc", borderRadius: "10px", border: "1px solid #e2e8f0" }}>
            <div style={{ fontWeight: 700, fontSize: "0.9rem", color: "#0369a1", marginBottom: "6px" }}>
              2. Double-Click to Run
            </div>
            <p style={{ margin: 0, fontSize: "0.84rem", color: "#475569", lineHeight: 1.5 }}>
              Open your <strong>Downloads</strong> folder and double-click <strong>Nanvi_Assistant.bat</strong>. A clean window will appear.
            </p>
          </div>

          <div style={{ padding: "14px", background: "#f8fafc", borderRadius: "10px", border: "1px solid #e2e8f0" }}>
            <div style={{ fontWeight: 700, fontSize: "0.9rem", color: "#0369a1", marginBottom: "6px" }}>
              3. Pick Your Folder
            </div>
            <p style={{ margin: 0, fontSize: "0.84rem", color: "#475569", lineHeight: 1.5 }}>
              Click <strong>&quot;📂 Select Folder&quot;</strong> in the window or use the 1-click buttons above. The assistant indexes it immediately!
            </p>
          </div>
        </div>
      </div>

      {/* Advanced Technical Details */}
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
  );
}
