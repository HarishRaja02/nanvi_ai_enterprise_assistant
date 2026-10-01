# Document Processing Pipeline

Canonical documentation: [`../../docs/13-file-connector.md`](../../docs/13-file-connector.md).

Implemented parsers: PDF, DOCX, XLSX, CSV, TXT/MD and PPTX. `DocumentProcessingService` accepts bytes from `FileService` and validates OOXML archive safety before parsing.

No HTTP upload endpoint or malware/sandbox pipeline is implemented.
