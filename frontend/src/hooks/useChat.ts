import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, NanviApiClient, UserIdentity } from "../api";
import { uid } from "../lib/id";
import { toSourceView } from "../lib/sources";
import type { Message, ResumedConversation } from "../types";

/**
 * Conversation state and the request lifecycle. Behaviour preserved from the original:
 * the same POST /chat contract, conversation_id continuity, and safe error text from ApiError.
 * Additions: answers keep backend `trace`/`capability`; retry re-sends without duplicating the
 * user turn; a reply that lands after the conversation was reset is discarded.
 */
export function useChat(api: NanviApiClient, identity: UserIdentity | null, onAnswered?: () => void) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [busy, setBusy] = useState(false);
  const [conversationId, setConversationId] = useState<string | undefined>();
  const [resumed, setResumed] = useState<ResumedConversation | null>(null);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [ragEnabled, setRagEnabled] = useState(true);

  const busyRef = useRef(false);
  const idRef = useRef<string | undefined>(undefined);
  const epochRef = useRef(0);

  const setConversation = useCallback((id: string | undefined) => { idRef.current = id; setConversationId(id); }, []);

  const request = useCallback(async (query: string, rag: boolean = true) => {
    const epoch = epochRef.current;
    busyRef.current = true;
    setBusy(true);
    try {
      const response = rag !== false ? await api.chat(query, idRef.current) : await api.chat(query, idRef.current, false);
      if (epoch !== epochRef.current) return;
      setConversation(response.conversation_id);
      setMessages((m) => [...m, {
        id: uid(),
        role: "assistant",
        text: response.answer,
        createdAt: Date.now(),
        sources: response.sources.map(toSourceView),
        trace: response.trace,
        capability: response.capability,
        reportId: response.report_id,
      }]);
      onAnswered?.();
    } catch (error) {
      if (epoch !== epochRef.current) return;
      setMessages((m) => [...m, {
        id: uid(),
        role: "assistant",
        text: error instanceof Error ? error.message : "Nanvi could not complete the request.",
        createdAt: Date.now(),
        error: true,
        retryAfter: error instanceof ApiError ? error.retryAfter : undefined,
      }]);
    } finally {
      if (epoch === epochRef.current) { busyRef.current = false; setBusy(false); }
    }
  }, [api, onAnswered, setConversation]);

  /** Returns false when nothing was sent (empty, busy, or signed out) so callers keep the draft. */
  const send = useCallback(async (text: string, rag?: boolean): Promise<boolean> => {
    const clean = text.trim();
    if (!clean || busyRef.current || !identity) return false;
    setMessages((m) => [...m, { id: uid(), role: "user", text: clean, createdAt: Date.now() }]);
    void request(clean, rag ?? ragEnabled);
    return true;
  }, [identity, ragEnabled, request]);

  const retry = useCallback((errorMessageId: string) => {
    if (busyRef.current) return;
    const index = messages.findIndex((m) => m.id === errorMessageId);
    const userTurn = index > 0 ? [...messages.slice(0, index)].reverse().find((m) => m.role === "user") : undefined;
    if (!userTurn) return;
    // Side effects stay outside state updaters: React StrictMode double-invokes updaters in dev.
    setMessages((current) => current.filter((m) => m.id !== errorMessageId));
    void request(userTurn.text);
  }, [messages, request]);

  const reset = useCallback(() => {
    epochRef.current += 1;
    busyRef.current = false;
    setBusy(false);
    setLoadingHistory(false);
    setMessages([]);
    setConversation(undefined);
    setResumed(null);
  }, [setConversation]);

  const resume = useCallback(async (target: ResumedConversation) => {
    epochRef.current += 1;
    const currentEpoch = epochRef.current;
    busyRef.current = false;
    setBusy(false);
    setMessages([]);
    setConversation(target.id);
    setResumed(target);
    setLoadingHistory(true);

    try {
      if (typeof api.conversation === "function") {
        const data = await api.conversation(target.id);
        if (currentEpoch !== epochRef.current) return;
        if (data && Array.isArray(data.messages) && data.messages.length > 0) {
          setMessages(
            data.messages.map((m) => ({
              id: uid(),
              role: m.role as "user" | "assistant",
              text: m.content,
              createdAt: m.created_at ? new Date(m.created_at).getTime() : Date.now(),
            }))
          );
        }
      }
    } catch {
      // Gracefully continue session with target.id even if message list retrieval fails
    } finally {
      if (currentEpoch === epochRef.current) {
        setLoadingHistory(false);
      }
    }
  }, [api, setConversation]);

  const appendTurn = useCallback((userText: string, assistantReply: { text: string; sources?: any[] }, newConvId?: string) => {
    if (newConvId) setConversation(newConvId);
    setMessages((m) => [
      ...m,
      { id: uid(), role: "user", text: userText, createdAt: Date.now() },
      { id: uid(), role: "assistant", text: assistantReply.text, sources: assistantReply.sources || [], createdAt: Date.now() },
    ]);
    onAnswered?.();
  }, [setConversation, onAnswered]);

  // Signing out (or a 401) must never leave the previous user's conversation on screen.
  useEffect(() => { if (!identity) reset(); }, [identity, reset]);

  return { messages, busy, conversationId, setConversationId: setConversation, resumed, loadingHistory, ragEnabled, setRagEnabled, send, retry, reset, resume, appendTurn };
}
