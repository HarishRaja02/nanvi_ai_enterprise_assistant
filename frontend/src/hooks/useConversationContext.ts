import { useCallback, useEffect, useRef, useState } from "react";
import type {
  ConversationContext,
  DocumentContext,
  EntityContext,
  NanviApiClient,
  PageContext,
  UserIdentity,
} from "../api";

interface UseConversationContextOptions {
  api: NanviApiClient;
  identity: UserIdentity | null;
  conversationId?: string;
  activeRoute?: string;
  pageTitle?: string;
}

export function useConversationContext({
  api,
  identity,
  conversationId,
  activeRoute = "/chat",
  pageTitle = "Enterprise Assistant",
}: UseConversationContextOptions) {
  const [context, setContext] = useState<ConversationContext | null>(null);
  const [activeEntity, setActiveEntityState] = useState<EntityContext | null>(null);
  const [activeDocument, setActiveDocumentState] = useState<DocumentContext | null>(null);
  const entityIndexRef = useRef<Record<string, unknown>>({});

  // Fetch or initialize context whenever conversationId changes
  useEffect(() => {
    if (!conversationId || !identity) {
      setContext(null);
      return;
    }

    let isMounted = true;
    api
      .getContext(conversationId)
      .then((ctx) => {
        if (isMounted && ctx) {
          setContext(ctx);
          if (ctx.active_entity) setActiveEntityState(ctx.active_entity);
          if (ctx.active_document) setActiveDocumentState(ctx.active_document);
          if (ctx.ui_entity_index) entityIndexRef.current = ctx.ui_entity_index;
        }
      })
      .catch(() => {
        // Safe initial fallback
      });

    return () => {
      isMounted = false;
    };
  }, [api, conversationId, identity]);

  // Synchronize route and page changes with backend
  useEffect(() => {
    if (!conversationId || !identity) return;

    const pageUpdate: PageContext = {
      route: activeRoute,
      page_type: activeRoute.replace(/^\//, "") || "chat",
      title: pageTitle,
    };

    api
      .updateContext(conversationId, { active_page: pageUpdate })
      .then((updated) => setContext(updated))
      .catch(() => {});
  }, [api, conversationId, identity, activeRoute, pageTitle]);

  const setActiveEntity = useCallback(
    (entity: EntityContext | null) => {
      setActiveEntityState(entity);
      if (conversationId && identity) {
        api
          .updateContext(conversationId, { active_entity: entity })
          .then((updated) => setContext(updated))
          .catch(() => {});
      }
    },
    [api, conversationId, identity]
  );

  const setActiveDocument = useCallback(
    (doc: DocumentContext | null) => {
      setActiveDocumentState(doc);
      if (conversationId && identity) {
        api
          .updateContext(conversationId, { active_document: doc })
          .then((updated) => setContext(updated))
          .catch(() => {});
      }
    },
    [api, conversationId, identity]
  );

  const updateEntityIndex = useCallback(
    (newIndex: Record<string, unknown>) => {
      entityIndexRef.current = { ...entityIndexRef.current, ...newIndex };
      if (conversationId && identity) {
        api
          .updateContext(conversationId, { ui_entity_index: entityIndexRef.current })
          .then((updated) => setContext(updated))
          .catch(() => {});
      }
    },
    [api, conversationId, identity]
  );

  return {
    context,
    activeEntity,
    activeDocument,
    setActiveEntity,
    setActiveDocument,
    updateEntityIndex,
    uiEntityIndex: entityIndexRef.current,
  };
}
