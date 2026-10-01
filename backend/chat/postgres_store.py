"""PostgreSQL persistent conversation store for production.

Stores conversations and chat messages with strict tenant and owner isolation.
"""
from __future__ import annotations

import json
import logging
from typing import Any
from datetime import datetime, timezone

from .models import ChatMessage, ConversationSummary
from .service import ConversationStore, generate_conversation_title

logger = logging.getLogger(__name__)


class PostgresConversationStore(ConversationStore):
    """Production-grade PostgreSQL conversation repository."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._ensure_schema()

    def _get_connection(self):
        try:
            import psycopg
            return psycopg.connect(self._dsn, connect_timeout=2)
        except ImportError:
            try:
                import psycopg2
                return psycopg2.connect(self._dsn, connect_timeout=2)
            except ImportError as exc:
                raise RuntimeError("PostgreSQL conversation store requires psycopg or psycopg2") from exc

    def _ensure_schema(self) -> None:
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS conversations (
                            conversation_id VARCHAR(128) PRIMARY KEY,
                            owner_id VARCHAR(128) NOT NULL,
                            tenant_id VARCHAR(128) NOT NULL,
                            title VARCHAR(256),
                            active_document VARCHAR(256),
                            context JSONB,
                            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                        );
                        CREATE INDEX IF NOT EXISTS idx_conversations_user 
                            ON conversations(tenant_id, owner_id);

                        CREATE TABLE IF NOT EXISTS conversation_messages (
                            id BIGSERIAL PRIMARY KEY,
                            conversation_id VARCHAR(128) NOT NULL REFERENCES conversations(conversation_id) ON DELETE CASCADE,
                            role VARCHAR(32) NOT NULL,
                            content TEXT NOT NULL,
                            data_source VARCHAR(32) DEFAULT 'live',
                            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                        );
                        CREATE INDEX IF NOT EXISTS idx_conv_messages 
                            ON conversation_messages(conversation_id, id);
                    """)
                conn.commit()
        except Exception as exc:
            logger.warning("Could not pre-initialize conversation schema: %s", exc)

    def bind_owner(self, conversation_id: str, user_id: str, tenant_id: str) -> None:
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT owner_id, tenant_id FROM conversations WHERE conversation_id = %s",
                    (conversation_id,),
                )
                row = cur.fetchone()
                if row:
                    if (row[0], row[1]) != (user_id, tenant_id):
                        raise PermissionError("Conversation does not belong to the authenticated principal")
                else:
                    cur.execute(
                        """
                        INSERT INTO conversations (conversation_id, owner_id, tenant_id, updated_at)
                        VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                        """,
                        (conversation_id, user_id, tenant_id),
                    )
            conn.commit()

    def owner(self, conversation_id: str) -> tuple[str, str] | None:
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT owner_id, tenant_id FROM conversations WHERE conversation_id = %s",
                    (conversation_id,),
                )
                row = cur.fetchone()
                return (row[0], row[1]) if row else None

    def append(self, conversation_id: str, message: ChatMessage) -> None:
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT title FROM conversations WHERE conversation_id = %s",
                    (conversation_id,),
                )
                row = cur.fetchone()
                if not row:
                    raise PermissionError("Conversation is not bound to an authenticated principal")
                existing_title = row[0]

                data_source = getattr(message, "data_source", "live") or "live"
                cur.execute(
                    """
                    INSERT INTO conversation_messages (conversation_id, role, content, data_source)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (conversation_id, message.role, message.content, data_source),
                )

                new_title = existing_title
                if not existing_title and message.role == "user" and message.content:
                    new_title = generate_conversation_title(message.content)

                cur.execute(
                    """
                    UPDATE conversations
                    SET title = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE conversation_id = %s
                    """,
                    (new_title, conversation_id),
                )
            conn.commit()

    def get(self, conversation_id: str) -> tuple[ChatMessage, ...]:
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT role, content, data_source
                    FROM conversation_messages
                    WHERE conversation_id = %s
                    ORDER BY id ASC
                    """,
                    (conversation_id,),
                )
                rows = cur.fetchall()
                messages = []
                for row in rows:
                    msg = ChatMessage(role=row[0], content=row[1])
                    msg.data_source = row[2] or "live"
                    messages.append(msg)
                return tuple(messages)

    def list_for_user(self, user_id: str, tenant_id: str) -> tuple[ConversationSummary, ...]:
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT c.conversation_id, c.title, c.updated_at,
                           (SELECT COUNT(*) FROM conversation_messages m WHERE m.conversation_id = c.conversation_id) AS msg_count
                    FROM conversations c
                    WHERE c.owner_id = %s AND c.tenant_id = %s
                    ORDER BY c.updated_at DESC
                    """,
                    (user_id, tenant_id),
                )
                rows = cur.fetchall()
                summaries = []
                for row in rows:
                    if row[3] > 0:  # Only list non-empty conversations
                        summaries.append(
                            ConversationSummary(
                                conversation_id=row[0],
                                title=row[1] or "New Conversation",
                                message_count=row[3],
                                last_message_at=row[2],
                            )
                        )
                return tuple(summaries)

    def set_active_document(self, conversation_id: str, document_id: str) -> None:
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE conversations SET active_document = %s WHERE conversation_id = %s",
                    (document_id, conversation_id),
                )
            conn.commit()

    def get_active_document(self, conversation_id: str) -> str | None:
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT active_document FROM conversations WHERE conversation_id = %s",
                    (conversation_id,),
                )
                row = cur.fetchone()
                return row[0] if row else None

    def set_context(self, conversation_id: str, context: object) -> None:
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                ctx_json = json.dumps(context) if context is not None else None
                cur.execute(
                    "UPDATE conversations SET context = %s WHERE conversation_id = %s",
                    (ctx_json, conversation_id),
                )
            conn.commit()

    def get_context(self, conversation_id: str) -> object | None:
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT context FROM conversations WHERE conversation_id = %s",
                    (conversation_id,),
                )
                row = cur.fetchone()
                if row and row[0]:
                    return json.loads(row[0]) if isinstance(row[0], str) else row[0]
                return None
