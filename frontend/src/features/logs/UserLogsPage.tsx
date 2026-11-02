import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  Calendar,
  Check,
  ClipboardList,
  Copy,
  Download,
  ExternalLink,
  Eye,
  RefreshCw,
  Search,
  ShieldAlert,
  Sparkles,
  Users,
  X,
} from "lucide-react";
import type { NanviApiClient, UserLogEntry } from "../../api";
import "./UserLogsPage.css";

type Props = {
  api: NanviApiClient;
  onReturn?: () => void;
};

export function UserLogsPage({ api }: Props) {
  const [dates, setDates] = useState<string[]>([]);
  const [todayDate, setTodayDate] = useState<string>("");
  const [selectedDate, setSelectedDate] = useState<string>("");
  const [logs, setLogs] = useState<UserLogEntry[]>([]);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [search, setSearch] = useState<string>("");
  const [userFilter, setUserFilter] = useState<string>("all");
  const [selectedLog, setSelectedLog] = useState<UserLogEntry | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // 1. Fetch available dates partitioned by day
  const fetchDates = useCallback(async () => {
    try {
      const res = await api.getUserLogDates();
      setDates(res.dates || []);
      setTodayDate(res.today || "");
      if (!selectedDate && res.today) {
        setSelectedDate(res.today);
      } else if (!selectedDate && res.dates && res.dates.length > 0) {
        setSelectedDate(res.dates[0]);
      }
    } catch (err: any) {
      console.warn("Could not load log dates:", err);
      // Fallback today date if offline or error
      const now = new Date();
      const dd = String(now.getUTCDate()).padStart(2, "0");
      const mm = String(now.getUTCMonth() + 1).padStart(2, "0");
      const yyyy = now.getUTCFullYear();
      const fallbackToday = `${dd}-${mm}-${yyyy}`;
      setDates([fallbackToday]);
      setTodayDate(fallbackToday);
      if (!selectedDate) setSelectedDate(fallbackToday);
    }
  }, [api, selectedDate]);

  // 2. Fetch logs matching current date, search, and user filter
  const fetchLogs = useCallback(
    async (showRefreshSpinner = false) => {
      if (showRefreshSpinner) setRefreshing(true);
      else setLoading(true);
      setError(null);

      try {
        const res = await api.getUserLogs({
          date: selectedDate || undefined,
          search: search.trim() || undefined,
          user_id: userFilter !== "all" ? userFilter : undefined,
          limit: 200,
        });
        setLogs(res.logs || []);
        setTotalCount(res.total ?? (res.logs ? res.logs.length : 0));
      } catch (err: any) {
        setError(err.message || "Failed to load logs. Ensure your Supabase user_query_logs table is configured.");
        setLogs([]);
        setTotalCount(0);
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [api, selectedDate, search, userFilter]
  );

  // Initial load
  useEffect(() => {
    fetchDates();
  }, [fetchDates]);

  useEffect(() => {
    if (selectedDate) {
      fetchLogs();
    }
  }, [selectedDate, search, userFilter, fetchLogs]);

  // Escape key closes modal
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setSelectedLog(null);
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  // Compute unique users for quick filter
  const uniqueUsers = useMemo(() => {
    const map = new Map<string, string>();
    logs.forEach((l) => {
      if (l.user_id && !map.has(l.user_id)) {
        map.set(l.user_id, l.user_name || l.user_id);
      }
    });
    return Array.from(map.entries()).map(([id, name]) => ({ id, name }));
  }, [logs]);

  // Copy helper
  const handleCopy = (id: string, text: string) => {
    navigator.clipboard?.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  // Export CSV
  const handleExportCSV = () => {
    if (!logs.length) return;
    const headers = ["ID", "User ID", "User Name", "Role", "Date", "Time", "Query", "Answer", "Capability", "Model"];
    const rows = logs.map((l) => [
      l.id,
      l.user_id,
      l.user_name,
      l.user_role,
      l.log_date,
      formatTime(l.created_at),
      `"${(l.query || "").replace(/"/g, '""')}"`,
      `"${(l.answer || "").replace(/"/g, '""')}"`,
      l.capability || "",
      l.model || "",
    ]);
    const csvContent = "data:text/csv;charset=utf-8," + [headers.join(","), ...rows.map((e) => e.join(","))].join("\n");
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `nanvi_user_logs_${selectedDate || "all"}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  function formatDateDisplay(dStr: string) {
    if (!dStr) return "";
    return dStr;
  }

  function formatTime(isoStr: string) {
    if (!isoStr) return "";
    try {
      const d = new Date(isoStr);
      return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    } catch {
      return isoStr;
    }
  }

  function getRoleBadgeClass(role: string) {
    const r = (role || "").toLowerCase();
    if (r.includes("superior") || r.includes("ceo")) return "role-superior-badge";
    if (r.includes("admin")) return "role-admin-badge";
    if (r.includes("supervisor")) return "role-supervisor-badge";
    return "role-employee-badge";
  }

  return (
    <div className="user-logs-page" data-testid="user-logs-page">
      {/* 1. Header Banner */}
      <section className="logs-hero-banner" aria-label="Logs Overview">
        <div className="logs-hero-top">
          <h1 className="logs-hero-title">
            <ClipboardList size={22} className="text-primary" />
            User Activity & Query Logs
          </h1>
          <span className="logs-role-tag">
            <Sparkles size={13} />
            Superior & Admin Console
          </span>
        </div>
        <p className="logs-hero-subtitle">
          Full audit trail of all enterprise employee queries and system-generated answers. Partitioned and split by day.
        </p>
      </section>

      {/* 2. Quick Metrics */}
      <section className="logs-stats-grid" aria-label="Statistics">
        <div className="logs-stat-card">
          <span className="logs-stat-label">Total Queries</span>
          <span className="logs-stat-value">{totalCount}</span>
        </div>
        <div className="logs-stat-card">
          <span className="logs-stat-label">Active Users</span>
          <span className="logs-stat-value">{uniqueUsers.length}</span>
        </div>
        <div className="logs-stat-card">
          <span className="logs-stat-label">Active Date Partition</span>
          <span className="logs-stat-value" style={{ fontSize: "16px" }}>
            {selectedDate === "all" ? "All Dates" : selectedDate === todayDate ? `${selectedDate} (Today)` : selectedDate || "Today"}
          </span>
        </div>
      </section>

      {/* 3. Filter Toolbar */}
      <section className="logs-toolbar" aria-label="Log Filters">
        <div className="logs-toolbar-left">
          {/* Dynamic Daily Dropdown Selector */}
          <div className="logs-date-picker-group">
            <label htmlFor="logs-date-select" className="logs-label">
              <Calendar size={15} style={{ display: "inline", verticalAlign: "text-bottom", marginRight: 4 }} />
              Date:
            </label>
            <select
              id="logs-date-select"
              data-testid="logs-date-select"
              className="logs-select"
              value={selectedDate}
              onChange={(e) => setSelectedDate(e.target.value)}
            >
              {dates.map((d) => (
                <option key={d} value={d}>
                  {d === todayDate ? `${d} (Today)` : d}
                </option>
              ))}
              <option value="all">All Dates</option>
            </select>
          </div>

          {/* User Filter Dropdown */}
          {uniqueUsers.length > 0 && (
            <div className="logs-date-picker-group">
              <label htmlFor="logs-user-select" className="logs-label">
                <Users size={15} style={{ display: "inline", verticalAlign: "text-bottom", marginRight: 4 }} />
                User:
              </label>
              <select
                id="logs-user-select"
                className="logs-select"
                value={userFilter}
                onChange={(e) => setUserFilter(e.target.value)}
              >
                <option value="all">All Users</option>
                {uniqueUsers.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.name} ({u.id})
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* Search Box */}
          <div className="logs-search-wrapper">
            <Search size={15} className="logs-search-icon" />
            <input
              type="text"
              className="logs-search-input"
              placeholder="Search user ID, query, or answer…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            {search && (
              <button
                type="button"
                onClick={() => setSearch("")}
                style={{
                  position: "absolute",
                  right: 10,
                  background: "none",
                  border: "none",
                  cursor: "pointer",
                  color: "var(--text-muted)",
                }}
              >
                <X size={14} />
              </button>
            )}
          </div>
        </div>

        {/* Action Buttons */}
        <div className="logs-toolbar-actions">
          <button
            type="button"
            className="logs-btn"
            onClick={() => void fetchLogs(true)}
            disabled={refreshing || loading}
            title="Refresh logs"
          >
            <RefreshCw size={14} className={refreshing ? "spin-animate" : ""} />
            Refresh
          </button>
          <button
            type="button"
            className="logs-btn logs-btn-primary"
            onClick={handleExportCSV}
            disabled={logs.length === 0}
            title="Download CSV"
          >
            <Download size={14} />
            Export CSV
          </button>
        </div>
      </section>

      {/* Error Notice */}
      {error && (
        <div
          style={{
            padding: "12px 16px",
            background: "#fef2f2",
            border: "1px solid #fecaca",
            borderRadius: "8px",
            color: "#991b1b",
            fontSize: "14px",
            display: "flex",
            alignItems: "center",
            gap: "8px",
          }}
        >
          <ShieldAlert size={18} />
          <span>{error}</span>
        </div>
      )}

      {/* 4. Logs Table Card */}
      <section className="logs-table-card" aria-label="Log Entries">
        {loading ? (
          <div className="logs-empty">
            <RefreshCw size={28} className="spin-animate text-primary" />
            <h3>Loading query logs…</h3>
            <p>Retrieving interaction logs from Supabase for {selectedDate}.</p>
          </div>
        ) : logs.length === 0 ? (
          <div className="logs-empty" data-testid="logs-empty-state">
            <ClipboardList size={36} />
            <h3>No query logs recorded</h3>
            <p>
              {selectedDate === "all"
                ? "No user queries have been logged yet."
                : `No user queries logged for ${selectedDate}. New queries sent by employees will automatically appear here.`}
            </p>
          </div>
        ) : (
          <div className="logs-table-wrapper">
            <table className="logs-table" aria-label="User activity log table">
              <thead>
                <tr>
                  <th style={{ width: "16%" }}>User ID</th>
                  <th style={{ width: "16%" }}>Date & Time</th>
                  <th style={{ width: "32%" }}>User Query</th>
                  <th style={{ width: "30%" }}>System Generated Answer</th>
                  <th style={{ width: "6%", textAlign: "right" }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {logs.map((log) => (
                  <tr key={log.id} data-testid={`log-row-${log.id}`}>
                    {/* 1. User ID */}
                    <td className="logs-user-cell">
                      <span className="logs-user-id">{log.user_id}</span>
                      <span className="logs-user-name">{log.user_name}</span>
                      <span className={`logs-role-badge ${getRoleBadgeClass(log.user_role)}`}>
                        {log.user_role || "User"}
                      </span>
                    </td>

                    {/* 2. Date */}
                    <td className="logs-date-cell">
                      <span className="logs-date-primary">{formatDateDisplay(log.log_date)}</span>
                      <span className="logs-date-time">{formatTime(log.created_at)}</span>
                    </td>

                    {/* 3. Query */}
                    <td className="logs-query-cell">
                      <div
                        className="logs-query-text"
                        title={log.query}
                        onClick={() => setSelectedLog(log)}
                        style={{ cursor: "pointer" }}
                      >
                        {log.query}
                      </div>
                    </td>

                    {/* 4. Answer */}
                    <td className="logs-answer-cell">
                      <div
                        className="logs-answer-text"
                        title={log.answer}
                        onClick={() => setSelectedLog(log)}
                        style={{ cursor: "pointer" }}
                      >
                        {log.answer}
                      </div>
                    </td>

                    {/* 5. Actions */}
                    <td className="logs-actions-cell">
                      <div style={{ display: "inline-flex", gap: "4px" }}>
                        <button
                          type="button"
                          className="logs-btn"
                          style={{ minHeight: "30px", padding: "0 8px" }}
                          onClick={() => handleCopy(log.id, log.answer)}
                          title="Copy Answer"
                        >
                          {copiedId === log.id ? <Check size={13} color="#16a34a" /> : <Copy size={13} />}
                        </button>
                        <button
                          type="button"
                          className="logs-btn"
                          style={{ minHeight: "30px", padding: "0 8px" }}
                          onClick={() => setSelectedLog(log)}
                          title="Inspect Details"
                        >
                          <Eye size={13} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* 5. Detail Modal */}
      {selectedLog && (
        <div className="logs-modal-overlay" onClick={() => setSelectedLog(null)} aria-modal="true" role="dialog">
          <div className="logs-modal-dialog" onClick={(e) => e.stopPropagation()}>
            <div className="logs-modal-header">
              <h2 className="logs-modal-title">Turn Inspection Details</h2>
              <button
                type="button"
                className="logs-btn"
                style={{ minHeight: "30px", padding: "0 8px" }}
                onClick={() => setSelectedLog(null)}
              >
                <X size={16} />
              </button>
            </div>

            <div className="logs-modal-body">
              {/* User info row */}
              <div style={{ display: "flex", flexWrap: "wrap", gap: "16px", fontSize: "13px" }}>
                <div>
                  <strong style={{ color: "var(--text-muted)" }}>User ID: </strong>
                  <code>{selectedLog.user_id}</code>
                </div>
                <div>
                  <strong style={{ color: "var(--text-muted)" }}>Name: </strong>
                  <span>{selectedLog.user_name}</span>
                </div>
                <div>
                  <strong style={{ color: "var(--text-muted)" }}>Role: </strong>
                  <span className={`logs-role-badge ${getRoleBadgeClass(selectedLog.user_role)}`}>
                    {selectedLog.user_role}
                  </span>
                </div>
                <div>
                  <strong style={{ color: "var(--text-muted)" }}>Date: </strong>
                  <span>{selectedLog.log_date} ({formatTime(selectedLog.created_at)})</span>
                </div>
              </div>

              {/* Query Field */}
              <div className="logs-modal-field">
                <div className="logs-modal-field-title">
                  <span>User Query / Prompt</span>
                  <button
                    type="button"
                    className="logs-btn"
                    style={{ minHeight: "26px", padding: "0 8px", fontSize: "11px" }}
                    onClick={() => handleCopy(`q-${selectedLog.id}`, selectedLog.query)}
                  >
                    {copiedId === `q-${selectedLog.id}` ? <Check size={11} color="#16a34a" /> : <Copy size={11} />}
                    Copy Prompt
                  </button>
                </div>
                <div className="logs-modal-field-box">{selectedLog.query}</div>
              </div>

              {/* Answer Field */}
              <div className="logs-modal-field">
                <div className="logs-modal-field-title">
                  <span>System Generated Answer</span>
                  <button
                    type="button"
                    className="logs-btn"
                    style={{ minHeight: "26px", padding: "0 8px", fontSize: "11px" }}
                    onClick={() => handleCopy(`a-${selectedLog.id}`, selectedLog.answer)}
                  >
                    {copiedId === `a-${selectedLog.id}` ? <Check size={11} color="#16a34a" /> : <Copy size={11} />}
                    Copy Answer
                  </button>
                </div>
                <div className="logs-modal-field-box">{selectedLog.answer}</div>
              </div>

              {/* Metadata */}
              {(selectedLog.capability || selectedLog.model) && (
                <div style={{ display: "flex", gap: "16px", fontSize: "12px", color: "var(--text-muted)" }}>
                  {selectedLog.capability && <div>Capability: <code>{selectedLog.capability}</code></div>}
                  {selectedLog.model && <div>Model: <code>{selectedLog.model}</code></div>}
                </div>
              )}
            </div>

            <div className="logs-modal-footer">
              <button
                type="button"
                className="logs-btn logs-btn-primary"
                onClick={() => setSelectedLog(null)}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
