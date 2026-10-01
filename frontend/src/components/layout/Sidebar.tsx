import { useEffect, useRef, useState } from "react";
import { ChevronRight, CircleHelp, LogOut, SquarePen, X } from "lucide-react";
import { Button, IconButton } from "../ui/Button";
import { ConversationList } from "./ConversationList";
import { NAV_ICONS } from "./navIcons";
import { initials } from "../../lib/format";
import { LOGO_URL } from "../../lib/config";
import type { NavGroup, View } from "../../lib/access";
import type { ConversationSummary } from "../../types";

type Props = {
  groups: NavGroup[];
  active: View;
  onNavigate: (view: View) => void;
  onNewConversation: () => void;
  history: ConversationSummary[];
  historyLoading: boolean;
  historyError: string;
  onRetryHistory: () => void;
  onOpenHelp: () => void;
  activeConversationId?: string;
  onSelectConversation: (c: ConversationSummary) => void;
  userName: string;
  userRole: string;
  onSignOut: () => void;
  onCloseDrawer: () => void;
};

export function Sidebar(p: Props) {
  const primaryItems = p.groups
    .flatMap((group) => group.items)
    .filter((item) => item.id === "Chat" || item.id === "Settings");
  const moreGroups = p.groups
    .map((group) => ({ ...group, items: group.items.filter((item) => item.id !== "Chat" && item.id !== "Settings") }))
    .filter((group) => group.items.length > 0);
  const moreToolsActive = moreGroups.some((group) => group.items.some((item) => item.id === p.active));
  const [moreToolsOpen, setMoreToolsOpen] = useState(false);
  const [moreToolsPosition, setMoreToolsPosition] = useState({ left: 0, top: 12 });
  const moreToolsButtonRef = useRef<HTMLButtonElement>(null);
  const moreToolsPanelRef = useRef<HTMLDivElement>(null);

  const positionMoreTools = () => {
    const bounds = moreToolsButtonRef.current?.getBoundingClientRect();
    if (!bounds) return;
    const panelWidth = Math.min(280, window.innerWidth - 24);
    const panelHeight = Math.min(480, window.innerHeight - 24);
    setMoreToolsPosition({
      left: Math.max(12, Math.min(bounds.right + 8, window.innerWidth - panelWidth - 12)),
      top: Math.max(12, Math.min(bounds.top, window.innerHeight - panelHeight - 12)),
    });
  };

  useEffect(() => {
    if (!moreToolsActive) return;
    positionMoreTools();
    setMoreToolsOpen(true);
  }, [moreToolsActive, p.active]);

  useEffect(() => {
    if (!moreToolsOpen) return;
    const closeOnOutsideClick = (event: PointerEvent) => {
      const target = event.target as Node;
      if (!moreToolsButtonRef.current?.contains(target) && !moreToolsPanelRef.current?.contains(target)) {
        setMoreToolsOpen(false);
      }
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setMoreToolsOpen(false);
      moreToolsButtonRef.current?.focus();
    };
    const closeOnScrollOrResize = () => setMoreToolsOpen(false);
    document.addEventListener("pointerdown", closeOnOutsideClick);
    document.addEventListener("keydown", closeOnEscape);
    window.addEventListener("resize", closeOnScrollOrResize);
    window.addEventListener("scroll", closeOnScrollOrResize, true);
    return () => {
      document.removeEventListener("pointerdown", closeOnOutsideClick);
      document.removeEventListener("keydown", closeOnEscape);
      window.removeEventListener("resize", closeOnScrollOrResize);
      window.removeEventListener("scroll", closeOnScrollOrResize, true);
    };
  }, [moreToolsOpen]);

  const toggleMoreTools = () => {
    if (moreToolsOpen) {
      setMoreToolsOpen(false);
      return;
    }
    positionMoreTools();
    setMoreToolsOpen(true);
  };

  return (
    <aside id="primary-nav" className="sidebar" aria-label="Primary">
      <div className="sidebar-head">
        <div className="brand">
          <img src={LOGO_URL} alt="Nanvi Logo" className="brand-logo-img" />
          <span className="brand-text">
            <small>Enterprise assistant</small>
          </span>
        </div>
        <IconButton className="drawer-close" icon={X} label="Close navigation" onClick={p.onCloseDrawer} />
      </div>

      <div className="sidebar-scroll">
        <Button className="new-chat" variant="primary" block icon={SquarePen} onClick={p.onNewConversation}>New chat</Button>

        <nav className="sidebar-primary-nav" aria-label="Main navigation">
          <ul>
            {primaryItems.map((item) => {
              const Icon = NAV_ICONS[item.id];
              const current = p.active === item.id;
              return (
                <li key={item.id}>
                  <button type="button" className={`nav-item${current ? " is-active" : ""}`} aria-current={current ? "page" : undefined} onClick={() => p.onNavigate(item.id)}>
                    <Icon size={18} aria-hidden="true" />
                    {item.label}
                  </button>
                </li>
              );
            })}
          </ul>
        </nav>

        <button type="button" className="nav-item sidebar-help" aria-haspopup="dialog" onClick={p.onOpenHelp}>
          <CircleHelp size={18} aria-hidden="true" />
          Help
        </button>

        {moreGroups.length > 0 && (
          <>
            <button
              ref={moreToolsButtonRef}
              type="button"
              className="sidebar-more-trigger"
              aria-expanded={moreToolsOpen}
              aria-controls="more-tools-menu"
              onClick={toggleMoreTools}
            >
              <ChevronRight size={16} aria-hidden="true" />
              <span>More tools</span>
            </button>
            {moreToolsOpen && (
              <div
                ref={moreToolsPanelRef}
                id="more-tools-menu"
                className="sidebar-more-flyout"
                style={{ left: moreToolsPosition.left, top: moreToolsPosition.top }}
              >
                <nav aria-label="More workspace tools">
                  {moreGroups.map((group) => (
                    <div key={group.id} className="nav-group">
                      {group.label && <h2 className="nav-group-label">{group.label}</h2>}
                      <ul>
                        {group.items.map((item) => {
                          const Icon = NAV_ICONS[item.id];
                          const current = p.active === item.id;
                          return (
                            <li key={item.id}>
                              <button
                                type="button"
                                className={`nav-item${current ? " is-active" : ""}`}
                                aria-current={current ? "page" : undefined}
                                onClick={() => {
                                  setMoreToolsOpen(false);
                                  p.onNavigate(item.id);
                                  p.onCloseDrawer();
                                }}
                              >
                                <Icon size={18} aria-hidden="true" />
                                {item.label}
                              </button>
                            </li>
                          );
                        })}
                      </ul>
                    </div>
                  ))}
                </nav>
              </div>
            )}
          </>
        )}

        <section className="history" aria-label="Conversation history">
          <h2 className="nav-group-label">Recent</h2>
          <ConversationList
            history={p.history}
            loading={p.historyLoading}
            error={p.historyError}
            activeId={p.activeConversationId}
            onSelect={p.onSelectConversation}
            onRetry={p.onRetryHistory}
          />
        </section>
      </div>

      <div className="sidebar-foot">
        <span className="avatar" aria-hidden="true">{initials(p.userName)}</span>
        <div className="user-copy">
          <strong className="truncate">{p.userName}</strong>
          <small className="truncate">{p.userRole}</small>
        </div>
        <IconButton icon={LogOut} label="Sign out" onClick={p.onSignOut} />
      </div>
    </aside>
  );
}
