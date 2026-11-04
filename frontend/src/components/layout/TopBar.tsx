import { LifeBuoy, Menu, Moon, PanelRight, Search, ShieldCheck, Sun } from "lucide-react";
import { Button, IconButton } from "../ui/Button";

type Props = {
  title: string;
  subtitle?: string;
  onOpenNav: () => void;
  onOpenPalette?: () => void;
  theme?: "light" | "dark";
  onToggleTheme?: () => void;
  environmentMode?: { label: string; description: string };
  onOpenReportIssue?: () => void;
  onOpenAdmin?: () => void;
  canAccessAdmin?: boolean;
  connectedFolder?: { path: string; name: string; fileCount: number };
  onOpenFolderPicker?: () => void;
  /** Present only on views that have a details panel. */
  panel?: { open: boolean; onToggle: () => void };
};

export function TopBar({
  title,
  subtitle,
  onOpenNav,
  onOpenPalette,
  theme = "light",
  onToggleTheme,
  environmentMode,
  onOpenReportIssue,
  onOpenAdmin,
  canAccessAdmin,
  connectedFolder,
  onOpenFolderPicker,
  panel,
}: Props) {

  return (
    <header className="topbar">
      <IconButton className="menu-button" icon={Menu} label="Open navigation" aria-controls="primary-nav" onClick={onOpenNav} />
      <div className="topbar-title">
        <h1>{title}</h1>
        {subtitle && <p className="truncate">{subtitle}</p>}
      </div>

      <div className="topbar-actions">
        {connectedFolder && Boolean(connectedFolder.path) && (
          <button
            type="button"
            className="topbar-folder-pill"
            onClick={onOpenFolderPicker}
            title={`Connected local folder: ${connectedFolder.path} (${connectedFolder.fileCount} files). Click to manage.`}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "6px",
              padding: "5px 12px",
              background: "#ecfdf5",
              border: "1px solid #86efac",
              color: "#166534",
              borderRadius: "20px",
              fontSize: "0.82rem",
              fontWeight: 700,
              cursor: onOpenFolderPicker ? "pointer" : "default",
              boxShadow: "0 1px 3px rgba(22, 163, 74, 0.1)",
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
            <span>📁 {connectedFolder.name || "Folder"} ({connectedFolder.fileCount} files)</span>
          </button>
        )}

        {environmentMode && (
          <span
            className="environment-mode-indicator"
            role="status"
            tabIndex={0}
            title={environmentMode.description}
            aria-label={`${environmentMode.label}. ${environmentMode.description}`}
          >
            {environmentMode.label}
          </span>
        )}

        {onOpenReportIssue && (
          <button
            type="button"
            className="topbar-support-btn"
            onClick={onOpenReportIssue}
            title="Report an issue or request developer support"
            aria-label="Report trouble or request support"
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.375rem",
              padding: "0.4rem 0.75rem",
              borderRadius: "0.5rem",
              border: "1px solid rgba(239, 68, 68, 0.3)",
              background: "rgba(239, 68, 68, 0.08)",
              color: "#fca5a5",
              fontSize: "0.8125rem",
              fontWeight: 500,
              cursor: "pointer",
            }}
          >
            <LifeBuoy size={14} style={{ color: "#ef4444" }} />
            <span>Need Help?</span>
          </button>
        )}

        {canAccessAdmin && onOpenAdmin && (
          <button
            type="button"
            className="topbar-admin-btn"
            onClick={onOpenAdmin}
            title="Open Platform Administration Console"
            aria-label="Open Platform Administration Console"
          >
            <ShieldCheck size={14} style={{ color: "#818cf8" }} />
            <span>Admin Console</span>
          </button>
        )}

        {onOpenPalette && (
          <button
            type="button"
            className="topbar-palette-btn"
            onClick={onOpenPalette}
            title="Open command palette (Ctrl+K / Cmd+K)"
            aria-label="Open command palette"
          >
            <Search size={14} aria-hidden="true" />
            <span className="palette-btn-text">Commands & Search…</span>
            <kbd className="palette-kbd">Ctrl K</kbd>
          </button>
        )}

        {onToggleTheme && (
          <button
            type="button"
            className="theme-toggle-btn"
            onClick={onToggleTheme}
            title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
            aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
          >
            {theme === "dark" ? <Sun size={15} aria-hidden="true" /> : <Moon size={15} aria-hidden="true" />}
          </button>
        )}

        {panel && (
          <Button
            variant="ghost"
            icon={PanelRight}
            aria-label="Toggle workspace details"
            aria-expanded={panel.open}
            aria-controls="context-panel"
            onClick={panel.onToggle}
          >
            <span className="panel-toggle-label">Workspace details</span>
          </Button>
        )}
      </div>
    </header>
  );
}
