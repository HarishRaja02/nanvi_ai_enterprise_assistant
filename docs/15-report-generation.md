# Report Generation

## Implemented

`ReportService` generates:
- Excel `.xlsx`
- PDF `.pdf`
- Word `.docx`
- PowerPoint `.pptx`

The service requires `REPORT_CREATE` and independently authorizes every lineage source before generation. Missing provenance, unknown source types, cross-tenant lineage or denied restricted sources fail closed before a report file is persisted.

Generators are formatters only. They do not query protected systems.

Excel output includes a Sources sheet. PDF/Word/PowerPoint include human-readable source/lineage information. Excel formula-like strings are sanitized to reduce formula injection risk while retaining numeric/date values.

`SecureFileReportStorage` uses opaque UUID report IDs, private local storage, 0600 files, atomic writes, metadata files and short-lived one-time download tokens.

## Current API exposure

The repository exposes only report download operations:
- `POST /api/reports/{report_id}/download-url`
- `GET /api/reports/{report_id}/download`

There is **no HTTP report-creation route** in the current API.

## Partially implemented

The default report storage is local filesystem and module-scoped. It is not a multi-instance HA store. The one-time token mechanism is application-level; production deployment should use durable shared metadata/storage.

## Planned/Future

Durable private object storage and a shared metadata store can replace `ReportStorage`. A report-creation API or fully wired ReportAgent would require an explicit application contract; neither is currently present.
