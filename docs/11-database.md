# Database

## Implemented

PostgreSQL support is implemented behind `DatabaseRepository` and `PostgreSQLRepository` using psycopg3/connection pooling.

`DatabaseService` requires an explicit column allowlist and performs:
- `DATABASE_READ` authorization;
- tenant-bound resource authorization;
- tokenized SQL validation;
- explicit table allowlist;
- optional/required column allowlist (required by the service);
- one `SELECT` or `WITH ... SELECT` statement;
- rejection of DML/DDL/admin operations;
- bounded results (explicit LIMIT up to 500, except scalar aggregates without GROUP);
- PostgreSQL `READ ONLY` transaction;
- PostgreSQL statement timeout;
- maximum rows and approximate result bytes;
- separate SQL parameters;
- transient connection retry only for classified connection/interface failures;
- audit records without SQL parameters or credentials.

## Current scope

The application code contains a real PostgreSQL repository, but the default FastAPI app does not instantiate it for chat. `DATABASE_URL` is configuration for integration/deployment, not evidence of a connected production database.

## Partially implemented

The current environment used for local tests does not provide a live PostgreSQL server. The database test suite uses repository fakes for many scenarios. The project also has a migration policy marker but no application schema/automatic startup migration.

## Planned/Future

Use a dedicated least-privilege PostgreSQL role, managed database, schema/RLS policy as required, external versioned migrations and real staging connection/restore tests.
