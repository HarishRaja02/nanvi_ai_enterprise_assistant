import { Menu, Moon, PanelRight, Search, Sun } from "lucide-react";
import { Button, IconButton } from "../ui/Button";

type Props = {
  title: string;
  subtitle?: string;
  onOpenNav: () => void;
  onOpenPalette?: () => void;
  theme?: "light" | "dark";
  onToggleTheme?: () => void;
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
            aria-label="Toggle Workspace HUD"
            aria-expanded={panel.open}
            aria-controls="context-panel"
            onClick={panel.onToggle}
          >
            <span className="panel-toggle-label">Workspace HUD</span>
          </Button>
        )}
      </div>
    </header>
  );
}
