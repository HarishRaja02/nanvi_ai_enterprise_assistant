# File Connector

## Implemented

`LocalFileRepository` and `FileService` provide controlled local filesystem access.

Production requires exactly these virtual roots:
- Customers
- Finance
- HR
- Projects
- Contracts

Access uses relative virtual paths. The repository rejects absolute, drive-qualified, UNC, traversal, null-byte, control-character, ambiguous Windows components and reserved Windows filenames.

Existing targets are resolved and must remain under the configured root. Directory symlinks are not followed during recursive search; file symlinks resolving outside the root are rejected.

Default allowed document extensions:
`.pdf`, `.docx`, `.xlsx`, `.csv`, `.txt`, `.md`, `.pptx`.

Default maximum file size is 10 MiB.

`FileService` authorizes before returning content and audits access. HR and Finance top-level directories are represented as restricted departments.

## Document processing

`DocumentProcessingService` receives bytes from `FileService`, never resolves OS paths itself. It supports PDF, DOCX, XLSX, CSV, TXT/MD and PPTX parsers. OOXML archives are checked for entry count, uncompressed size, compression ratio and unsafe entries.

## Partially implemented

There is no HTTP file-upload endpoint or upload UI. File access is local filesystem based. There is no malware scanning/sandbox pipeline for uploaded attachments/files.

## Planned/Future

A production upload pipeline should add controlled ingestion, malware/sandbox scanning, durable storage and indexing without bypassing the existing FileService authorization boundary.
