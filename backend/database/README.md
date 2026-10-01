# Database Infrastructure

Canonical documentation: [`../../docs/11-database.md`](../../docs/11-database.md).

The current `backend/database` package contains a migration-policy marker. The actual PostgreSQL repository/service and SQL validation live under `backend/integrations/database/`.

No application schema or automatic startup DDL is implemented.
