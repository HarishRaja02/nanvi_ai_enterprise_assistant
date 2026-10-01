"""Migration policy marker.

Production schema changes must be applied by the deployment migration job,
not automatically at FastAPI startup. The project currently has no required
application schema, so this module intentionally performs no DDL.
"""

MIGRATION_POLICY = "external-versioned-migrations"
