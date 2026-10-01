"""PostgreSQL persistent source reference store for production.

Ensures source references survive process restarts and remain tenant-isolated.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from .models import SourceReference, SourceType
from .store import SourceReferenceStore

logger = logging.getLogger(__name__)


class PostgresSourceReferenceStore(SourceReferenceStore):
    """Production-grade PostgreSQL source reference store."""

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
                raise RuntimeError("PostgresSourceReferenceStore requires psycopg or psycopg2") from exc

    def _ensure_schema(self) -> None:
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS source_references (
                            reference_id VARCHAR(128) PRIMARY KEY,
                            source_id VARCHAR(256) NOT NULL,
                            source_type VARCHAR(64) NOT NULL,
                            owner_id VARCHAR(128) NOT NULL,
                            tenant_id VARCHAR(128) NOT NULL,
                            department VARCHAR(128),
                            restricted_department VARCHAR(128),
                            reference_data JSONB NOT NULL,
                            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                        );
                        CREATE INDEX IF NOT EXISTS idx_source_ref_tenant 
                            ON source_references(tenant_id, source_type);
                    """)
                conn.commit()
        except Exception as exc:
            logger.warning("Could not pre-initialize source references schema: %s", exc)

    def save(
        self,
        reference: SourceReference,
        owner_id: str,
        tenant_id: str,
        source_id: str,
        source_type: str,
        department: str | None = None,
        restricted_department: str | None = None,
    ) -> None:
        ref_dict = {
            "reference_id": reference.reference_id,
            "source_type": reference.source_type.value if hasattr(reference.source_type, "value") else str(reference.source_type),
            "display_name": reference.display_name,
            "title": reference.title,
            "location": reference.location,
            "page": reference.page,
            "sheet": reference.sheet,
            "timestamp": reference.timestamp.isoformat() if reference.timestamp else None,
            "mime_type": reference.mime_type,
            "href": reference.href,
        }

        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO source_references (
                        reference_id, source_id, source_type, owner_id, tenant_id,
                        department, restricted_department, reference_data
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (reference_id) DO UPDATE SET
                        source_id = EXCLUDED.source_id,
                        source_type = EXCLUDED.source_type,
                        owner_id = EXCLUDED.owner_id,
                        tenant_id = EXCLUDED.tenant_id,
                        department = EXCLUDED.department,
                        restricted_department = EXCLUDED.restricted_department,
                        reference_data = EXCLUDED.reference_data
                    """,
                    (
                        reference.reference_id,
                        source_id,
                        source_type,
                        owner_id,
                        tenant_id,
                        department,
                        restricted_department,
                        json.dumps(ref_dict),
                    ),
                )
            conn.commit()

    def get(self, reference_id: str) -> dict[str, Any] | None:
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT reference_data, owner_id, tenant_id, source_id, source_type,
                           department, restricted_department
                    FROM source_references
                    WHERE reference_id = %s
                    """,
                    (reference_id,),
                )
                row = cur.fetchone()
                if not row:
                    return None

                ref_data = row[0] if isinstance(row[0], dict) else json.loads(row[0])
                from .store import _dict_to_ref
                reference = _dict_to_ref(ref_data)

                return {
                    "reference": reference,
                    "owner_id": row[1],
                    "tenant_id": row[2],
                    "source_id": row[3],
                    "source_type": row[4],
                    "department": row[5],
                    "restricted_department": row[6],
                }
