# Nanvi Report Agent Validation Report

## Scope

Validated the Report Agent and report service for Excel, PDF, Word, and PowerPoint output, with emphasis on data correctness, source lineage, formatting, filenames, downloads, large/empty datasets, error handling, and authorization.

## Security invariant

`ReportService.create_report` is the report-generation security boundary. It first authenticates the report principal through the supplied `UserAttributes`, checks `REPORT_CREATE`, verifies the principal/tenant match, and then independently authorizes **every declared lineage source** before invoking a generator. Missing provenance, cross-tenant lineage, unknown source types, or a restricted source denied by RBAC/ABAC prevents generation before any report file is written.

The generators are formatters only: they do not access databases/filesystems or decide authorization. `ReportAgent` invokes the service through `SecureToolGateway`.

## Supported formats

| Format | Generator | Actual file reopened and validated |
|---|---|---|
| Excel | openpyxl | PASS |
| PDF | reportlab | PASS |
| Word | python-docx | PASS |
| PowerPoint | python-pptx | PASS |

## Functional validation

- Report creation: PASS
- Correct source data: PASS
- Calculated values preserved exactly: PASS
- Source/lineage information: PASS
- Formatting: PASS
- Safe download filename: PASS
- Download authorization and one-time token: PASS
- Large datasets: PASS
- Empty datasets: PASS
- Special characters: PASS
- Invalid format/error handling: PASS
- Permission handling: PASS

## Authorization scenarios

### User A -> allowed data

Allowed source lineage is authorized and the generated artifact contains the supplied authorized dataset.

### User A -> restricted data

A Projects/Employee user attempting to generate a report from Finance-restricted lineage is rejected before generation. No PDF artifact is created.

### Finance user -> Finance data

A Finance user with the matching department and Finance role is authorized to generate a report from Finance-restricted lineage.

### User B -> User A report

A different user cannot obtain a temporary download URL for User A's owner-bound report.

### Cross-tenant source

A source lineage from another tenant is rejected before generation.

### Mixed authorized + unauthorized sources

A report containing one allowed source and one denied source is rejected atomically; partial report generation does not occur.

### Missing provenance

Reports without lineage are rejected. This prevents callers from presenting arbitrary structured data to the formatter without an authorization/provenance context.

## Data correctness

Excel preserves numeric values as numeric cells rather than converting all values to strings. This keeps generated reports usable for downstream spreadsheet calculations. Formula-like untrusted strings are prefixed with an apostrophe to prevent Excel formula injection.

PDF/Word/PowerPoint render the same normalized display values used by the report layer. Calculated values supplied by the deterministic analysis layer are not recomputed by the report generator, preventing report formatting from changing analytical results.

## Large and empty datasets

- Excel: validated with 1,000 rows and exact worksheet row count.
- Word: validated with 1,000 rows.
- PowerPoint: validated with 1,000 rows split across multiple slides.
- PDF: validated with 500 rows and successfully reopened with pypdf.
- Empty datasets: validated for all four formats and produce a readable no-data representation.

## Source transparency

Reports include safe human-readable lineage fields: source type, source label, source columns, and filters. Raw source IDs and raw SQL are not embedded by the generators.

## Filename handling

Download filenames are derived from the report title through a sanitization function that removes control characters and filesystem/header metacharacters, trims unsafe trailing spaces/dots, caps length, and always applies the server-selected extension.

## Download security

Download access requires `REPORT_DOWNLOAD` authorization. Tokens are short-lived, hashed at rest, and one-time-use. A different user cannot reuse the report owner’s authorization. The service returns the stored file only after authorization and token validation.

## Automated regression coverage

`tests/test_reports.py` and `tests/test_report_validation.py` cover generation, actual file reopening, lineage, authorization, cross-tenant access, mixed-source denial, empty/large datasets, special characters, formula injection, safe filenames, download behavior, and invalid runtime formats.

## Final test result

**237 passed, 2 warnings**.

The warnings are existing test-only PyJWT short-key warnings in authentication tests; they are unrelated to report generation.

## Generated artifact validation

Actual generated files were independently reopened and checked:

- `validated.xlsx`
- `validated.pdf`
- `validated.docx`
- `validated.pptx`

An unauthorized Finance report was also attempted and was blocked before generation.

## Completion status

The Report Agent is **validated for the current prototype scope**. It should not be described as production-complete: production still requires durable/shared report storage, production audit sinks, real deployment integration, and operational load testing. The generated file formats themselves have now been validated by automated tests and by reopening real generated artifacts.
