from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class DatabaseTarget:
    """Logical database target; contains no credentials."""
    name: str
    engine: str
    tenant_id: str


@dataclass(frozen=True)
class QueryRequest:
    sql: str
    parameters: tuple[Any, ...] = ()


@dataclass(frozen=True)
class QueryResult:
    columns: tuple[str, ...]
    rows: tuple[tuple[Any, ...], ...]
    truncated: bool = False

    def to_markdown(self) -> str:
        if not self.columns:
            return "No data returned."
        header_row = "| " + " | ".join(str(c) for c in self.columns) + " |"
        sep_row = "| " + " | ".join("---" for _ in self.columns) + " |"
        if not self.rows:
            return f"{header_row}\n{sep_row}\n| " + " | ".join("—" for _ in self.columns) + " |"
        lines = [header_row, sep_row]
        for row in self.rows:
            cells = []
            for item in row:
                if item is None:
                    cells.append("—")
                else:
                    cells.append(str(item).replace("\n", " ").replace("|", "\\|"))
            lines.append("| " + " | ".join(cells) + " |")
        md = "\n".join(lines)
        if self.truncated:
            md += "\n\n*(Data truncated for brevity)*"
        return md

    def __str__(self) -> str:
        return self.to_markdown()


@dataclass(frozen=True)
class TablePolicy:
    """Allowlist of database objects and, optionally, exposed columns.

    ``allowed_columns`` is keyed by ``(schema, table, column)``. When supplied,
    column access is fail-closed: every referenced column must be listed.
    """
    allowed_tables: frozenset[tuple[str, str]] = field(default_factory=frozenset)
    allowed_columns: frozenset[tuple[str, str, str]] | None = None

    def allows(self, schema: str, table: str) -> bool:
        return (schema.casefold(), table.casefold()) in self.allowed_tables

    def columns_restricted(self) -> bool:
        return self.allowed_columns is not None

    def allows_column(self, schema: str, table: str, column: str) -> bool:
        if self.allowed_columns is None:
            return True
        return (schema.casefold(), table.casefold(), column.casefold()) in self.allowed_columns
