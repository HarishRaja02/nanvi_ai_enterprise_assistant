import { useEffect, useMemo, useRef } from "react";
import { Alert } from "../ui/Alert";
import { Button } from "../ui/Button";
import { Composer } from "./Composer";
import { MessageItem } from "./MessageItem";
import { EmptyStateBento } from "./EmptyStateBento";
import { AiActivityIndicator } from "./AiActivityIndicator";
import { ContextualSuggestions } from "./ContextualSuggestions";
import { extractConversationContext } from "../../lib/contextIntelligence";
import type { PromptDef } from "../../lib/prompts";
import type { SourceView } from "../../lib/sources";
import type { Message, ResumedConversation } from "../../types";
import type { NanviApiClient, UserIdentity } from "../../api";

type Props = {
  messages: Message[];
  busy: boolean;
  resumed: ResumedConversation | null;
  loadingHistory?: boolean;
  starters: Array<PromptDef & { area: string }>;
  focusToken: number;
  ragEnabled?: boolean;
  onToggleRag?: (enabled: boolean) => void;
  api?: NanviApiClient;
  identity?: UserIdentity | null;
  onSend: (text: string, rag?: boolean) => Promise<boolean>;
  onRetry: (messageId: string) => void;
  onOpenSource: (source: SourceView) => void;
  onDownload: (reportId: string) => void;
  onNewConversation: () => void;
  onOpenVoiceMode?: () => void;
};

export function ChatView({
  messages,
  busy,
  resumed,
  loadingHistory = false,
  starters,
  focusToken,
  ragEnabled = true,
  onToggleRag,
  api,
  identity,
  onSend,
  onRetry,
  onOpenSource,
  onDownload,
  onNewConversation,
  onOpenVoiceMode,
}: Props) {
  const endRef = useRef<HTMLDivElement>(null);
  const empty = messages.length === 0 && !busy && !loadingHistory;

  // Extract dynamic context intelligence & suggestions from messages
  const context = useMemo(() => extractConversationContext(messages, identity), [messages, identity]);

  useEffect(() => {
    if (messages.length === 0 && !busy) return; // keep empty state anchored at the top
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    endRef.current?.scrollIntoView?.({ block: "end", behavior: reduce ? "auto" : "smooth" });
  }, [messages.length, busy]);

  return (
    <div className="chat">
      <div className="chat-scroll">
        <div className="thread">
          {loadingHistory && (
            <div
              className="history-loading"
              role="status"
              style={{
                padding: "var(--space-6) 0",
                color: "var(--text-secondary)",
                display: "flex",
                alignItems: "center",
                gap: "var(--space-3)",
              }}
            >
              <span className="dots" aria-hidden="true">
                <i /><i /><i />
              </span>
              <span>Loading conversation history…</span>
            </div>
          )}

          {resumed && !loadingHistory && messages.length === 0 && (
            <Alert
              tone="info"
              title={`Continuing “${resumed.title}”`}
              actions={
                <Button size="sm" variant="secondary" onClick={onNewConversation}>
                  Start a new conversation
                </Button>
              }
            >
              Earlier messages in this conversation aren't available. Your next message is added to it.
            </Alert>
          )}

          {resumed && !loadingHistory && messages.length > 0 && (
            <Alert
              tone="info"
              title={`Continuing “${resumed.title}”`}
              actions={
                <Button size="sm" variant="secondary" onClick={onNewConversation}>
                  Start new conversation
                </Button>
              }
            >
              Showing earlier messages from this conversation. Your next message continues here.
            </Alert>
          )}

          {/* Minimalist SaaS Bento Grid Empty State */}
          {empty && (
            <EmptyStateBento identity={identity} onPick={(p) => void onSend(p)} disabled={busy} />
          )}

          {/* Messages list */}
          <div className="messages" role="log" aria-live="polite" aria-label="Conversation messages">
            {messages.map((m) => (
              <MessageItem
                key={m.id}
                message={m}
                onOpenSource={onOpenSource}
                onDownload={onDownload}
                onRetry={onRetry}
                onFollowup={(p) => void onSend(p)}
              />
            ))}

            {/* Progressive Multi-Stage AI Activity Stepper */}
            {busy && (
              <div className="msg msg-assistant" role="status">
                <AiActivityIndicator ragEnabled={ragEnabled} />
              </div>
            )}
          </div>

          <div ref={endRef} />
        </div>
      </div>

      {/* Floating searchbar dock with no heavy gray background */}
      <div className="floating-composer-dock">
        <div className="floating-composer-inner">
          {messages.length > 0 && !busy && context.suggestions.length > 0 && (
            <ContextualSuggestions
              suggestions={context.suggestions}
              onSelect={(p) => void onSend(p)}
              disabled={busy}
            />
          )}

          <Composer
            busy={busy}
            onSend={onSend}
            focusToken={focusToken}
            ragEnabled={ragEnabled}
            onToggleRag={onToggleRag}
            api={api}
            onClearConversation={onNewConversation}
            hasMessages={messages.length > 0}
            onOpenVoiceMode={onOpenVoiceMode}
          />
        </div>
      </div>
    </div>
  );
}
