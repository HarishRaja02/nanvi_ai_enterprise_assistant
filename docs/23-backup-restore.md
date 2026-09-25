# Backup and Restore

## Implemented

A non-production DR exercise exists at `scripts/dr_nonprod_restore.py`.

It creates synthetic state for:
- non-secret configuration;
- documents;
- generated-report artifact;
- vector/index marker;
- audit log marker.

It builds a tar.gz snapshot with a SHA-256/size manifest, restores it to an isolated target, verifies checksums and required state, and confirms secret-bearing configuration is not restored.

The last recorded exercise verified 5 files and `production_data_touched=false`.

## What is not a production backup implementation

The DR script is a validation harness. It does not configure PostgreSQL managed backups, Redis backups, object-storage versioning, SIEM retention or scheduled backup jobs.

The current application still contains in-memory stores for audit, conversations, source references and vector retrieval. Those stores are not durable disaster-recovery stores.

## RPO/RTO targets

The previous DR validation documented engineering targets, not approved SLAs:
- PostgreSQL: RPO 15 min / RTO 60 min
- documents: RPO 15 min / RTO 60 min
- vector index: RPO 60 min / RTO 120 min
- reports: RPO 60 min / RTO 120 min
- audit: RPO 5 min / RTO 60 min
- configuration: RPO 24 h / RTO 60 min

These require business/operations approval before being treated as commitments.

## Partially implemented

A real PostgreSQL backup -> isolated PostgreSQL restore -> application verification has not been executed in this local environment. Durable audit/report/source/conversation storage is not present. Therefore the project does not claim fully validated production DR.

## Planned/Future

Implement provider-native encrypted backups, immutable retention as required, cross-zone/region strategy where required, and recurring restore drills in a non-production environment.
