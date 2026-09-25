import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ContextPanel } from "./components/layout/ContextPanel";
import { Sidebar } from "./components/layout/Sidebar";
import { TopBar } from "./components/layout/TopBar";
import { CommandPalette } from "./components/layout/CommandPalette";
import { ChatView } from "./components/chat/ChatView";
import { SourceDialog } from "./components/chat/SourceDialog";
import { useToast } from "./components/ui/Toast";
import { EnterpriseLoginGateway } from "./login/App";
import { SessionSplash } from "./features/auth/SessionSplash";
import { AuditPage } from "./features/workspaces/AuditPage";
import { ReportsPage } from "./features/workspaces/ReportsPage";
import { WorkspacePage } from "./features/workspaces/WorkspacePage";
import { SettingsPage } from "./features/settings/SettingsPage";
import { VoiceAssistantMode } from "./features/voice/VoiceAssistantMode";

import { useChat } from "./hooks/useChat";
import { useHistory } from "./hooks/useHistory";
import { useSession } from "./hooks/useSession";
import { useTheme } from "./hooks/useTheme";
import { NavEntry, View, isRole, permissionsFor, viewLabel, visibleNav } from "./lib/access";
import { conversationTitle } from "./lib/format";
import { STARTERS, visiblePrompts } from "./lib/prompts";
import { MailboxModal } from "./components/email/MailboxModal";
import { FolderPickerModal } from "./components/ui/FolderPickerModal";
import { useCompanyFolder } from "./hooks/useCompanyFolder";
import type { SourceView } from "./lib/sources";
import type { ConversationSummary } from "./types";
import type { EmailStatusResponse } from "./api";

const WIDE = "(min-width: 1100px)";


export function App() {
  const { theme, toggleTheme } = useTheme();
  const notify = useToast();
  const session = useSession();
  const { api, identity } = session;
  const { history, loading: historyLoading, error: historyError, reload: reloadHistory } = useHistory(api, identity);
  const chat = useChat(api, identity, reloadHistory);
  const companyFolder = useCompanyFolder(identity ? api : undefined);

  const [view, setView] = useState<View>("Chat");
  const [navOpen, setNavOpen] = useState(false);
  const [panelOpen, setPanelOpen] = useState(() => window.matchMedia?.(WIDE).matches ?? true);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [focusToken, setFocusToken] = useState(0);
  const [openedSource, setOpenedSource] = useState<SourceView | null>(null);
  const [mailboxOpen, setMailboxOpen] = useState(false);
  const [mailboxStatus, setMailboxStatus] = useState<EmailStatusResponse | null>(null);
  const [folderPickerOpen, setFolderPickerOpen] = useState(false);
  const [voiceModeOpen, setVoiceModeOpen] = useState(false);
  const mainRef = useRef<HTMLElement>(null);
  const previousView = useRef<View>("Chat");


  // UX-only capability set derived from backend-reported roles. Authorization stays server-side.
  const permissions = useMemo(() => permissionsFor(identity?.roles ?? []), [identity]);
  const groups = useMemo(() => visibleNav(permissions), [permissions]);
  const allowedViews = useMemo(() => groups.flatMap((g) => g.items.map((i) => i.id)), [groups]);
  const activeView: View = allowedViews.includes(view) ? view : "Chat";
  const modules: NavEntry[] = useMemo(() => groups.flatMap((g) => g.items).filter((i) => i.id !== "Chat"), [groups]);
  const starters = useMemo(() => visiblePrompts(STARTERS, permissions), [permissions]);

  // Reset navigation when the session ends.
  useEffect(() => {
    if (!identity) {
      setView("Chat");
      setNavOpen(false);
      setPaletteOpen(false);
      setVoiceModeOpen(false);
      setMailboxStatus(null);
    }
  }, [identity]);

  // Fetch mailbox connection status
  useEffect(() => {
    if (identity) {
      api.emailStatus().then(setMailboxStatus).catch(() => {});
    } else {
      setMailboxStatus(null);
    }
  }, [identity, api, mailboxOpen]);

  // Handle Google OAuth callback from URL query param
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const code = params.get("code");
    const state = params.get("state") || undefined;
    const connected = params.get("connected");
    const statusParam = params.get("status");

    if (connected && statusParam) {
      const err = params.get("error");
      window.history.replaceState({}, document.title, window.location.pathname);
      if (statusParam === "success") {
        notify(`Successfully connected ${connected}!`, "success");
        setView("Settings");
      } else {
        notify(`Failed to connect ${connected}: ${err || "Unknown error"}`, "error");
      }
    } else if (code && identity) {
      window.history.replaceState({}, document.title, window.location.pathname);
      api
        .connectGoogleMailbox(code, state, window.location.origin)
        .then((res) => {
          notify(`Mailbox connected: ${res.account.email_address}`, "success");
          api.emailStatus().then(setMailboxStatus).catch(() => {});
        })
        .catch((err) => {
          notify(`Google mailbox connection failed: ${err.message || "Unknown error"}`, "error");
        });
    }
  }, [identity, api, notify]);



  // Keep the details panel from opening as an overlay when the window narrows.
  useEffect(() => {
    const mq = window.matchMedia?.(WIDE);
    if (!mq) return;
    const onChange = (e: MediaQueryListEvent) => {
      if (!e.matches) setPanelOpen(false);
    };
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  // Global Ctrl+K / Cmd+K listener to toggle command palette
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && (e.key === "k" || e.key === "K")) {
        e.preventDefault();
        setPaletteOpen((prev) => !prev);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Escape closes the mobile drawer / overlay panel.
  useEffect(() => {
    if (!navOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setNavOpen(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [navOpen]);

  // Announce and orient on navigation: title for the tab, focus for keyboard and screen-reader users.
  useEffect(() => {
    document.title = identity
      ? `${viewLabel(activeView)} — Nanvi AI Enterprise Assistant`
      : "Nanvi AI Enterprise Assistant";
  }, [activeView, identity]);

  useEffect(() => {
    // Compare with the previous view rather than counting renders: StrictMode runs effects twice on mount.
    if (previousView.current === activeView) return;
    previousView.current = activeView;
    if (activeView === "Chat") setFocusToken((t) => t + 1);
    else mainRef.current?.focus({ preventScroll: true });
  }, [activeView]);

  const goTo = useCallback((next: View) => {
    setView(next);
    setNavOpen(false);
  }, []);

  const newConversation = useCallback(() => {
    chat.reset();
    setView("Chat");
    setNavOpen(false);
    setFocusToken((t) => t + 1);
  }, [chat]);

  const selectConversation = useCallback(
    (c: ConversationSummary) => {
      chat.resume({ id: c.conversation_id, title: conversationTitle(c) });
      setView("Chat");
      setNavOpen(false);
      setFocusToken((t) => t + 1);
    },
    [chat]
  );

  /** Module pages and widgets hand their question to the assistant. */
  const ask = useCallback(
    (prompt: string) => {
      setView("Chat");
      void chat.send(prompt);
    },
    [chat]
  );

  const openSource = useCallback((source: SourceView) => setOpenedSource(source), []);

  const downloadReport = useCallback(
    async (reportId: string) => {
      if (!permissions.includes("REPORT_DOWNLOAD")) {
        notify("Report download is not permitted for this session.", "danger");
        return;
      }
      try {
        const { download_url } = await api.reportDownloadUrl(reportId);
        const parsed = new URL(download_url, window.location.origin);
        if (parsed.origin !== window.location.origin) throw new Error("Secure download destination rejected.");
        const a = document.createElement("a");
        a.href = parsed.toString();
        a.download = "";
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        notify("Document download started.", "success");
      } catch (error) {
        notify(error instanceof Error ? error.message : "Secure report download failed.", "danger");
      }
    },
    [api, notify, permissions]
  );

  if (session.checking) {
    return <SessionSplash title="Securing your session" detail="Checking your Nanvi identity and access policy…" />;
  }

  if (!identity) {
    return (
      <EnterpriseLoginGateway
        error={session.authError}
        loggedOut={session.loggedOut}
        onLogin={session.signIn}
        loading={session.signingIn}
      />
    );
  }

  const displayName = identity.name || identity.email || "User";
  const primaryRole = identity.roles.find(isRole) ?? "Authorized user";
  const isChat = activeView === "Chat";
  const subtitle = isChat
    ? chat.resumed
      ? chat.resumed.title
      : chat.messages.length
      ? "Current conversation"
      : "New conversation"
    : undefined;

  return (
    <div className="app" data-nav-open={navOpen} data-panel-open={isChat && panelOpen}>
      <a className="skip-link" href="#main">
        Skip to main content
      </a>

      <Sidebar
        groups={groups}
        active={activeView}
        onNavigate={goTo}
        onNewConversation={newConversation}
        history={history}
        historyLoading={historyLoading}
        historyError={historyError}
        onRetryHistory={() => void reloadHistory()}
        activeConversationId={chat.conversationId}
        onSelectConversation={selectConversation}
        userName={displayName}
        userRole={primaryRole}
        onSignOut={session.logout}
        onCloseDrawer={() => setNavOpen(false)}
      />
      <div
        className="scrim"
        onClick={() => {
          setNavOpen(false);
          setPanelOpen(window.matchMedia?.(WIDE).matches ?? false);
        }}
        aria-hidden="true"
      />

      <div className="app-main">
        <TopBar
          title={viewLabel(activeView)}
          subtitle={subtitle}
          onOpenNav={() => setNavOpen(true)}
          onOpenPalette={() => setPaletteOpen(true)}
          theme={theme}
          onToggleTheme={toggleTheme}
          panel={isChat ? { open: panelOpen, onToggle: () => setPanelOpen((o) => !o) } : undefined}
        />

        <div className="app-body">
          <main id="main" ref={mainRef} className="content" tabIndex={-1}>
            {activeView === "Chat" && (
              <ChatView
                messages={chat.messages}
                busy={chat.busy}
                resumed={chat.resumed}
                loadingHistory={chat.loadingHistory}
                starters={starters}
                focusToken={focusToken}
                ragEnabled={chat.ragEnabled}
                onToggleRag={chat.setRagEnabled}
                api={api}
                identity={identity}
                onSend={chat.send}
                onRetry={chat.retry}
                onOpenSource={openSource}
                onDownload={(id) => void downloadReport(id)}
                onNewConversation={newConversation}
                onOpenVoiceMode={() => setVoiceModeOpen(true)}
              />
            )}
            {activeView === "Reports" && <ReportsPage onAsk={ask} />}
            {activeView === "Audit" && <AuditPage onReturn={() => goTo("Chat")} />}
            {activeView === "Settings" && <SettingsPage api={api} identity={identity} />}
            {activeView !== "Chat" && activeView !== "Reports" && activeView !== "Audit" && activeView !== "Settings" && (
              <WorkspacePage view={activeView} permissions={permissions} onAsk={ask} api={api} />
            )}

          </main>
          {isChat && panelOpen && (
            <ContextPanel
              identity={identity}
              modules={modules}
              conversationId={chat.conversationId}
              messages={chat.messages}
              onOpenSource={openSource}
              onClose={() => setPanelOpen(false)}
              onAsk={ask}
              folderPath={companyFolder.folderPath}
              folderName={companyFolder.folderName}
              folderFileCount={companyFolder.fileCount}
              onOpenFolderPicker={() => setFolderPickerOpen(true)}
            />
          )}
        </div>
      </div>

      {openedSource && <SourceDialog source={openedSource} api={api} onClose={() => setOpenedSource(null)} />}

      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        onNavigate={goTo}
        onAsk={ask}
        onNewConversation={newConversation}
        ragEnabled={chat.ragEnabled}
        onToggleRag={chat.setRagEnabled}
        theme={theme}
        onToggleTheme={toggleTheme}
      />

      <MailboxModal
        api={api}
        open={mailboxOpen}
        onClose={() => setMailboxOpen(false)}
        onAskPrompt={ask}
      />

      <FolderPickerModal
        api={api}
        open={folderPickerOpen}
        onClose={() => setFolderPickerOpen(false)}
      />

      {voiceModeOpen && (
        <VoiceAssistantMode
          api={api}
          identity={identity}
          conversationId={chat.conversationId}
          ragEnabled={chat.ragEnabled}
          onClose={() => setVoiceModeOpen(false)}
          onOpenSource={openSource}
          onUpdateConversationId={(id) => chat.setConversationId(id)}
          onAddChatMessage={(userText, assistantReply) => {
            chat.appendTurn(userText, assistantReply);
          }}
        />
      )}
    </div>
  );
}

