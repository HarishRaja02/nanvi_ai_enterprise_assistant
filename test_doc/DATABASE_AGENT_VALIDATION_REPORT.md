# Nanvi Database Agent Validation Report

Date: 2026-09-18

## Scope

Validated the database capability as a security-first, read-only path:

User -> authenticated identity -> RBAC/ABAC -> DatabaseAgent -> DatabaseTool -> DatabaseService -> SQL validation -> repository -> structured result -> source reference.

The real PostgreSQL service is an integration boundary and was not connected to a live enterprise database in this environment. Controlled repository doubles were used for deterministic tests.

## Results

| Capability / Attack | Result |
|---|---|
| Natural-language planning boundary | PASS |
| SELECT | PASS |
| WHERE | PASS |
| GROUP BY | PASS |
| ORDER BY | PASS |
| JOIN | PASS |
| COUNT | PASS |
| SUM | PASS |
| AVG | PASS |
| Date filtering | PASS |
| Comparisons | PASS |
| Aggregations | PASS |
| Result bounding | PASS |
| Unauthorized table | PASS - blocked |
| Unauthorized column | PASS - blocked |
| Wildcard column exposure | PASS - blocked |
| INSERT | PASS - blocked |
| UPDATE | PASS - blocked |
| DELETE | PASS - blocked |
| DROP | PASS - blocked |
| ALTER | PASS - blocked |
| TRUNCATE | PASS - blocked |
| Multi-statement injection | PASS - blocked |
| Parameter injection | PASS - parameter remains separate |
| Missing database permission | PASS - repository not called |
| Cross-tenant access | PASS - repository not called |
| Agent planner emits destructive SQL | PASS - tool validation blocks it |
| Structured query result | PASS |
| Source information | PASS |

## Findings and fixes

### HIGH - Explicit column allowlist was not previously mandatory at the DatabaseService boundary

A table allowlist alone does not prevent an approved table from exposing sensitive columns. The service could be constructed with a validator that only enforced tables.

Fix: `DatabaseService` now fails closed unless its `SQLValidationPipeline` has an explicit column allowlist enabled. The validator checks referenced columns, qualified columns, aliases, JOIN conditions, ORDER/GROUP expressions, and rejects wildcard projection when a column allowlist is active.

Regression: `test_unauthorized_column_is_rejected`, `test_wildcard_is_rejected_with_column_allowlist`, and service-construction coverage.

### HIGH - Unbounded result sets were possible through the normal service path

A plain `SELECT` without LIMIT could return an arbitrarily large result. The repository had a client-side maximum, but that does not sufficiently control database work or network transfer.

Fix: the normal `DatabaseService` path requires an explicit LIMIT for non-scalar queries and caps LIMIT at 500. Scalar aggregates such as COUNT/SUM/AVG/MIN/MAX without GROUP BY are allowed without LIMIT because they produce a single output row; database statement timeout remains a separate execution safeguard.

Regression: `test_unrestricted_nonaggregate_select_is_rejected`, `test_limit_cannot_exceed_service_cap`.

### MEDIUM - Tokenizer mishandled `%s` parameter placeholders when column validation was enabled

The tokenizer recognized `%` before `%s`, turning the placeholder into `%` + `s`. This became visible only after strict column validation was introduced.

Fix: `%s` is tokenized as a parameter before generic symbol handling.

Regression: parameterized query and injection tests.

### MEDIUM - Date column name could be mistaken for SQL type keyword

`DATE` was treated as a generic keyword, which could bypass column checking when a real column was named `date`.

Fix: `DATE` is only treated as a type literal when followed by a string token; otherwise it participates in normal column validation.

Regression: date-filtering coverage.

## SQL security model

The normal read-only path now enforces:

1. backend authorization before repository execution;
2. explicit tenant binding;
3. explicit table allowlist;
4. explicit column allowlist;
5. SELECT/WITH-only statements;
6. destructive/admin operation rejection;
7. one-statement rule;
8. bounded result policy;
9. parameterized values;
10. PostgreSQL read-only transaction and statement timeout;
11. result-size and row limits;
12. audit logging;
13. controlled source references.

The LLM/planner is not trusted. It can propose SQL, but it cannot grant itself database permissions, bypass the allowlists, or directly access a repository/credential.

## Natural-language question handling

`DatabaseAgent` now provides a clean planner boundary:

Natural-language question -> planner -> parameterized SQL -> DatabaseTool -> DatabaseService -> policy/validation -> repository.

A production LLM planner can implement the existing `DatabaseQueryPlanner` contract. The planner does not receive database credentials and its output is always revalidated by the backend.

## Source information

Successful DatabaseAgent responses can create a frontend-safe database source reference. The source reference is reauthorized when resolved and does not expose SQL text, credentials, raw database identifiers, or connection details.

## Test execution

Dedicated Database Agent tests: **15 passed**.

Complete project test suite after fixes: **192 passed, 2 warnings**.

The warnings are the existing test-only PyJWT short-key warnings.

## Remaining enterprise validation

Before production, run the same suite against:

- real PostgreSQL with a dedicated least-privilege login;
- production schema/view/column allowlists;
- PostgreSQL Row-Level Security where tenant isolation requires it;
- real LLM SQL planner;
- real LangGraph execution path;
- representative production-scale datasets;
- query performance/load tests;
- database audit/SIEM integration.

The application validator is defense-in-depth and must not replace database-level privileges.
