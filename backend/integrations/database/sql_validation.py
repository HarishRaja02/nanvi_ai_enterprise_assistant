from __future__ import annotations

from dataclasses import dataclass
import re

from .exceptions import SQLValidationError
from .models import TablePolicy


@dataclass(frozen=True)
class SQLToken:
    kind: str
    value: str


class SQLTokenizer:
    """Small lexical scanner that understands strings, quoted identifiers and comments.

    This is deliberately not a regex-only keyword check. The validator works on tokens,
    understands statement boundaries, and ignores keywords inside literals/comments.
    """

    _identifier = re.compile(r"[A-Za-z_][A-Za-z0-9_$]*")
    _number = re.compile(r"(?:\d+(?:\.\d*)?|\.\d+)")

    def tokenize(self, sql: str) -> list[SQLToken]:
        if not isinstance(sql, str) or not sql.strip():
            raise SQLValidationError("SQL must be a non-empty string")

        tokens: list[SQLToken] = []
        i = 0
        n = len(sql)
        while i < n:
            c = sql[i]
            if c.isspace():
                i += 1
                continue
            if sql.startswith("--", i):
                end = sql.find("\n", i + 2)
                i = n if end == -1 else end + 1
                continue
            if sql.startswith("/*", i):
                end = sql.find("*/", i + 2)
                if end == -1:
                    raise SQLValidationError("Unterminated SQL block comment")
                i = end + 2
                continue
            if c == "'":
                i += 1
                while i < n:
                    if sql[i] == "'":
                        if i + 1 < n and sql[i + 1] == "'":
                            i += 2
                            continue
                        i += 1
                        break
                    i += 1
                else:
                    raise SQLValidationError("Unterminated SQL string literal")
                tokens.append(SQLToken("STRING", "<literal>"))
                continue
            if c == '"':
                i += 1
                chars = []
                while i < n:
                    if sql[i] == '"':
                        if i + 1 < n and sql[i + 1] == '"':
                            chars.append('"'); i += 2; continue
                        i += 1; break
                    chars.append(sql[i]); i += 1
                else:
                    raise SQLValidationError("Unterminated quoted identifier")
                tokens.append(SQLToken("IDENT", "".join(chars)))
                continue
            if c == ";":
                tokens.append(SQLToken("SEMICOLON", c)); i += 1; continue
            if c == "%" and i + 1 < n and sql[i + 1] == "s":
                tokens.append(SQLToken("PARAM", "%s")); i += 2; continue
            if c in "(),.*=<>+-/%":
                tokens.append(SQLToken("SYMBOL", c)); i += 1; continue
            if c == "$" and i + 1 < n and sql[i + 1].isdigit():
                j = i + 2
                while j < n and sql[j].isdigit(): j += 1
                tokens.append(SQLToken("PARAM", sql[i:j])); i = j; continue
            m = self._identifier.match(sql, i)
            if m:
                tokens.append(SQLToken("WORD", m.group(0))); i = m.end(); continue
            m = self._number.match(sql, i)
            if m:
                tokens.append(SQLToken("NUMBER", m.group(0))); i = m.end(); continue
            raise SQLValidationError(f"Unsupported SQL character: {c!r}")
        return tokens


class ReadOnlySQLValidator:
    """Defense-in-depth validator for the read-only database capability."""

    FORBIDDEN = frozenset({
        "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE", "CREATE",
        "MERGE", "UPSERT", "GRANT", "REVOKE", "COMMENT", "VACUUM", "ANALYZE",
        "COPY", "CALL", "DO", "EXECUTE", "SET", "RESET", "DISCARD", "LOCK",
        "REFRESH", "REINDEX", "CLUSTER", "PREPARE", "DEALLOCATE",
    })

    def __init__(self, table_policy: TablePolicy, tokenizer: SQLTokenizer | None = None, *, require_column_policy: bool = False):
        self._policy = table_policy
        self._tokenizer = tokenizer or SQLTokenizer()
        self._require_column_policy = require_column_policy

    def validate(self, sql: str, *, require_bounded_result: bool = False) -> list[tuple[str, str]]:
        tokens = self._tokenizer.tokenize(sql)
        meaningful = [t for t in tokens if t.kind != "SEMICOLON"]
        if not meaningful:
            raise SQLValidationError("SQL contains no statement")
        semicolons = sum(t.kind == "SEMICOLON" for t in tokens)
        if semicolons > 1 or (semicolons == 1 and tokens[-1].kind != "SEMICOLON"):
            raise SQLValidationError("Multiple SQL statements are not allowed")

        first = meaningful[0].value.upper()
        if first not in {"SELECT", "WITH"}:
            raise SQLValidationError("Only SELECT queries are permitted")

        words = [t.value.upper() for t in meaningful if t.kind == "WORD"]
        forbidden = sorted(set(words).intersection(self.FORBIDDEN))
        if forbidden:
            raise SQLValidationError(f"Forbidden SQL operation: {forbidden[0]}")

        # WITH ... INSERT/UPDATE/DELETE is caught above. We also require a SELECT
        # somewhere in a WITH statement so a malformed/unsupported CTE cannot pass.
        if first == "WITH" and "SELECT" not in words:
            raise SQLValidationError("WITH statements must contain a SELECT")

        referenced = self._extract_table_references(meaningful)
        for schema, table in referenced:
            if not self._policy.allows(schema, table):
                raise SQLValidationError(f"Table is not allowed: {schema}.{table}")

        if require_bounded_result:
            self._validate_result_bound(meaningful)

        if self._require_column_policy and not self._policy.columns_restricted():
            raise SQLValidationError("Column allowlist is required for database access")
        if self._policy.columns_restricted():
            self._validate_columns(meaningful, referenced)
        return referenced

    @staticmethod
    def _extract_table_references(tokens: list[SQLToken]) -> list[tuple[str, str]]:
        """Extract table identifiers following FROM/JOIN, including schema.table.

        This intentionally rejects dynamic table expressions and database-qualified
        names because the allowlist is explicit and local to one configured database.
        """
        refs: list[tuple[str, str]] = []
        words = [i for i, t in enumerate(tokens) if t.kind in {"WORD", "IDENT"}]
        for pos in words:
            if tokens[pos].value.upper() not in {"FROM", "JOIN"}:
                continue
            j = pos + 1
            if j >= len(tokens) or tokens[j].kind not in {"WORD", "IDENT"}:
                raise SQLValidationError("FROM/JOIN must reference an explicit table")
            first = tokens[j].value
            j += 1
            if j + 1 < len(tokens) and tokens[j].value == "." and tokens[j + 1].kind in {"WORD", "IDENT"}:
                schema, table = first, tokens[j + 1].value
                j += 2
                if j + 1 < len(tokens) and tokens[j].value == ".":
                    raise SQLValidationError("Database-qualified table names are not allowed")
            else:
                schema, table = "public", first
            # Derived tables/subqueries and table functions are not accepted by this
            # minimal policy; explicit allowlisted tables keep the boundary auditable.
            if j < len(tokens) and tokens[j].value == "(":
                raise SQLValidationError("Derived/table-function sources are not allowed")
            refs.append((schema, table))
        return refs


    @staticmethod
    def _validate_result_bound(tokens: list[SQLToken]) -> None:
        words = [t.value.upper() for t in tokens if t.kind == "WORD"]
        has_limit = "LIMIT" in words
        if not has_limit:
            # A scalar aggregate produces one row and is bounded by construction.
            aggregate = any(w in {"COUNT", "SUM", "AVG", "MIN", "MAX"} for w in words)
            if aggregate and "GROUP" not in words:
                return
            raise SQLValidationError("Read query must include an explicit LIMIT")
        for i, token in enumerate(tokens):
            if token.kind == "WORD" and token.value.upper() == "LIMIT":
                if i + 1 >= len(tokens) or tokens[i + 1].kind != "NUMBER":
                    raise SQLValidationError("LIMIT must be a numeric constant")
                value = int(float(tokens[i + 1].value))
                if value <= 0 or value > 500:
                    raise SQLValidationError("LIMIT must be between 1 and 500")
                return

    def _validate_columns(self, tokens: list[SQLToken], referenced: list[tuple[str, str]]) -> None:
        for i, token in enumerate(tokens):
            if token.value == "*":
                # COUNT(*) is a bounded aggregate and does not expose a column.
                prev = tokens[i - 2].value.upper() if i >= 2 and tokens[i - 1].value == "(" else (tokens[i - 1].value.upper() if i > 0 else "")
                if prev not in {"COUNT"}:
                    raise SQLValidationError("Wildcard column selection is not allowed with a column allowlist")
        if len(referenced) != len(set(referenced)):
            # Duplicate table references are legal; aliases are handled below.
            pass
        table_by_name = {table.casefold(): (schema, table) for schema, table in referenced}
        aliases: dict[str, tuple[str, str]] = {}
        keywords = {
            "SELECT", "FROM", "WHERE", "GROUP", "BY", "ORDER", "LIMIT", "OFFSET", "ASC", "DESC",
            "JOIN", "INNER", "LEFT", "RIGHT", "FULL", "OUTER", "ON", "AS", "AND", "OR", "NOT",
            "NULL", "IS", "IN", "LIKE", "BETWEEN", "CASE", "WHEN", "THEN", "ELSE", "END",
            "DISTINCT", "HAVING", "UNION", "ALL", "WITH", "TRUE", "FALSE", "NULLS", "FIRST", "LAST",
            "COUNT", "SUM", "AVG", "MIN", "MAX", "COALESCE", "LOWER", "UPPER", "ROUND", "CAST", "FILTER",
            "ASCENDING", "DESCENDING",
        }
        # Collect aliases after table references and explicit AS aliases.
        for i, token in enumerate(tokens[:-1]):
            if token.value.upper() in {"FROM", "JOIN"}:
                j = i + 1
                if j < len(tokens) and tokens[j].kind in {"WORD", "IDENT"}:
                    first = tokens[j].value
                    if j + 2 < len(tokens) and tokens[j + 1].value == ".":
                        schema, table = first, tokens[j + 2].value
                        j += 3
                    else:
                        schema, table = "public", first
                        j += 1
                    if j < len(tokens) and tokens[j].kind in {"WORD", "IDENT"} and tokens[j].value.upper() != "ON":
                        aliases[tokens[j].value.casefold()] = (schema, table)
            if token.value.upper() == "AS" and i + 1 < len(tokens):
                # SELECT aliases are not columns to validate.
                aliases[tokens[i + 1].value.casefold()] = ("", "")

        for i, token in enumerate(tokens):
            if token.kind not in {"WORD", "IDENT"}:
                continue
            value = token.value
            upper = value.upper()
            if upper == "DATE" and i + 1 < len(tokens) and tokens[i + 1].kind == "STRING":
                continue
            if upper in keywords or upper in self.FORBIDDEN:
                continue
            # Table/schema identifiers and aliases are structural identifiers.
            if value.casefold() in table_by_name or value.casefold() in aliases:
                continue
            # Function names are not columns.
            if i + 1 < len(tokens) and tokens[i + 1].value == "(":
                continue
            # Skip identifiers used as explicit schema/table parts.
            if i + 1 < len(tokens) and tokens[i + 1].value == ".":
                continue
            if i > 0 and tokens[i - 1].value == ".":
                qualifier = tokens[i - 2].value if i >= 2 else ""
                target = aliases.get(qualifier.casefold()) or table_by_name.get(qualifier.casefold())
                if target is None:
                    raise SQLValidationError(f"Unknown column qualifier: {qualifier}")
                schema, table = target
                if not self._policy.allows_column(schema, table, value):
                    raise SQLValidationError(f"Column is not allowed: {schema}.{table}.{value}")
                continue
            # Unqualified column: it must be allowed by at least one referenced table.
            if not referenced:
                raise SQLValidationError(f"Column is not allowed: {value}")
            matches = [(schema, table) for schema, table in referenced
                       if self._policy.allows_column(schema, table, value)]
            if not matches:
                raise SQLValidationError(f"Column is not allowed: {value}")
            if len(referenced) > 1 and len(matches) > 1:
                raise SQLValidationError(f"Ambiguous column must be qualified: {value}")


class SQLValidationPipeline:
    """Named pipeline boundary so validation is not coupled to database drivers."""

    def __init__(self, validator: ReadOnlySQLValidator):
        self._validator = validator

    @property
    def column_policy_enforced(self) -> bool:
        return self._validator._require_column_policy and self._validator._policy.columns_restricted()

    def validate_read(self, sql: str, *, require_bounded_result: bool = False) -> list[tuple[str, str]]:
        return self._validator.validate(sql, require_bounded_result=require_bounded_result)
