import { useCallback, useEffect, useState } from "react";
import type { NanviApiClient, UserIdentity } from "../api";
import type { ConversationSummary } from "../types";

export function useHistory(api: NanviApiClient, identity: UserIdentity | null) {
  const [history, setHistory] = useState<ConversationSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const reload = useCallback(async () => {
    if (!identity) return;
    setLoading(true);
    setError("");
    try {
      const response = await api.history();
      setHistory(response.conversations ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Conversation history is unavailable.");
    } finally {
      setLoading(false);
    }
  }, [api, identity]);

  useEffect(() => {
    if (identity) void reload();
    else { setHistory([]); setError(""); }
  }, [identity, reload]);

  return { history, loading, error, reload };
}
