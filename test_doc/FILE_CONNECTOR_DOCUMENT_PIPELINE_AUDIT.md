# Nanvi File Connector & Document-Processing Security Audit

**Date:** 2026-09-18  
**Scope:** filesystem connector, document ingestion/parsing, source metadata, authorization boundary, adversarial filesystem/document inputs.

## Executive result

The audit found and corrected several architecture/security gaps. The final regression suite is **206 passed, 2 warnings**. The dedicated file/document security suite is **28 passed**.

The production design now requires an explicit five-root allowlist:

- `C:\\CompanyData\\Customers\\`
- `C:\\CompanyData\\Finance\\`
- `C:\\CompanyData\\HR\\`
- `C:\\CompanyData\\Projects\\`
- `C:\\CompanyData\\Contracts\\`

These are configured through `COMPANY_FILE_ROOTS` as named virtual roots. Production has no broad `C:\\CompanyData` fallback.

## Main architecture change

Before, document parsers accepted filesystem `Path` objects directly. That meant a parser could read an arbitrary path if some caller bypassed `FileService`.

The processing boundary is now:

`User/Agent -> FileService -> ConfiguredLocalFileRepository -> authorized bytes + safe metadata -> DocumentProcessingService -> parser`

`DocumentProcessingService` has no filesystem-path parsing API. Parsers receive bytes and a logical relative source path. This makes the controlled file service the filesystem access boundary.

The LLM/agent layer does not receive filesystem handles, absolute paths, repository objects, or credentials.

## Supported ingestion formats

| Format | Status | Source locations |
|---|---|---|
| PDF | PASS | Page N |
| DOCX | PASS | Table N |
| XLSX | PASS | Sheet name |
| CSV | PASS | CSV |
| TXT | PASS | TXT |
| PPTX | PASS | Slide N |

`python-pptx` was added to the dependency set.

## Security tests

### Path controls

- `../../etc/passwd` — blocked
- `Projects/../../HR/...` — blocked
- Unix absolute paths — blocked
- Windows drive-qualified paths — blocked
- Windows UNC paths — blocked
- leading backslash paths — blocked
- null bytes — blocked
- control characters — blocked
- Windows-reserved device names — blocked
- ambiguous trailing dot/space path components — blocked
- symlink escape outside an approved root — blocked
- symlink crossing from one approved root into another — rejected by resolved-root containment

All access is canonicalized and checked against the exact configured root before a file is exposed.

### File controls

- unsupported extensions — rejected
- oversized files — rejected before content is exposed
- metadata/read access — authorized by `FileService`
- unauthorized HR/Finance access — denied
- safe virtual source paths returned instead of absolute OS paths

### Document controls

Malformed PDF/DOCX/XLSX/PPTX inputs are converted to controlled processing errors rather than exposing library internals.

DOCX/XLSX/PPTX are OOXML ZIP containers. Before parser execution the pipeline checks:

- maximum archive entry count
- maximum total uncompressed size
- maximum compression ratio
- archive member traversal paths
- absolute/drive-qualified archive paths
- archive symlink entries

Standalone ZIP files remain unsupported.

## Metadata and source tracking

Normalized documents retain:

- filename
- logical relative source path
- file type
- byte size
- modification timestamp
- format-specific locations
- PDF document metadata where available

Absolute filesystem paths are no longer required in the normalized document source model.

## Authorization

`FileService` authorizes the resolved file resource before returning file content. Restricted `HR` and `Finance` roots continue to map to department-aware authorization resources.

Document parsing itself does not make authorization decisions; it only processes already-authorized bytes. This separation prevents a parser or LLM from becoming an authorization boundary.

## Findings fixed

### HIGH — direct filesystem path processing in document layer

**Problem:** parsers and `DocumentProcessingService` accepted arbitrary `Path` values.

**Fix:** parsers now expose `parse_bytes`; `DocumentProcessingService.parse_file()` obtains bytes only through the controlled `FileService`.

### HIGH — broad production filesystem root configuration

**Problem:** configuration previously allowed a single broad `COMPANY_FILE_ROOT` default.

**Fix:** production requires exactly five explicitly named roots through `COMPANY_FILE_ROOTS`.

### HIGH — missing PPTX pipeline

**Problem:** the product requirement included PPTX but the parser set did not.

**Fix:** added `PPTXParser`, dependency, extraction and slide source locations.

### HIGH — OOXML archive bomb exposure

**Problem:** DOCX/XLSX/PPTX are ZIP-based and could contain dangerous archive characteristics.

**Fix:** pre-parse archive validation with entry, uncompressed-size, compression-ratio, path and symlink controls.

### MEDIUM — parser exceptions could expose implementation details

**Problem:** raw third-party parser errors could propagate.

**Fix:** malformed document failures are normalized to controlled `DocumentProcessingError` messages while retaining the original exception only as an internal cause.

### MEDIUM — unsafe filename/path components

**Problem:** cross-platform path normalization did not explicitly reject all Windows-ambiguous/reserved components.

**Fix:** added control-character, reserved-device-name and trailing-dot/space checks.

## Regression coverage

Added `tests/test_file_document_security.py` covering:

- exact configured roots
- virtual root paths
- traversal
- absolute paths
- UNC paths
- drive paths
- symlink escape
- malicious filename components
- file size limits
- extension allowlist
- permission filtering
- byte-only document processing
- controlled `FileService -> DocumentProcessingService` flow
- malformed documents
- OOXML archive bomb behavior
- unsupported ZIP files

Existing document tests were updated to the byte-based processing boundary, and end-to-end/adversarial tests were updated accordingly.

## Remaining production requirements

This audit validates the application architecture and controlled test environment. Production deployment still needs operational controls outside this codebase:

1. Run the service account with filesystem permissions limited to the five configured directories.
2. Make the configured directories read-only for the assistant where business requirements allow it.
3. Keep upload/ingestion processing isolated from the API process for untrusted external files.
4. Add malware/antivirus scanning before enterprise files are indexed if files can originate outside trusted company storage.
5. Use a sandboxed worker for high-risk document formats when threat requirements justify it.
6. Run the full security suite against a real Windows staging environment because Linux CI cannot reproduce every Windows filesystem behavior.
7. Add operational quotas/worker concurrency limits for large document batches.

## Test result

`206 passed, 2 warnings`.

The warnings are existing test-only PyJWT short-key warnings and are unrelated to the file/document pipeline.
