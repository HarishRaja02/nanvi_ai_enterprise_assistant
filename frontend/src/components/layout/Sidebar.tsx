import { LogOut, SquarePen, X } from "lucide-react";
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
  activeConversationId?: string;
  onSelectConversation: (c: ConversationSummary) => void;
  userName: string;
  userRole: string;
  onSignOut: () => void;
  onCloseDrawer: () => void;
};

export function Sidebar(p: Props) {
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
        <Button className="new-chat" variant="primary" block icon={SquarePen} onClick={p.onNewConversation}>New conversation</Button>

        <nav aria-label="Workspace">
          {p.groups.map((group) => (
            <div key={group.id} className="nav-group">
              {group.label && <h2 className="nav-group-label">{group.label}</h2>}
              <ul>
                {group.items.map((item) => {
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
            </div>
          ))}
        </nav>

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
