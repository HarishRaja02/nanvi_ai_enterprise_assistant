# RAG / Knowledge Retrieval

## Implemented

`backend/retrieval` provides a provider-neutral retrieval pipeline:

`source metadata -> chunking -> keyword/vector candidate retrieval -> reciprocal-rank fusion -> authorization -> reranking -> result`

### Implemented components
- `DocumentChunker`: default 1200-character chunks with 150-character overlap.
- `KeywordRetriever`: in-memory lexical index.
- `EmbeddingProvider`: provider-neutral interface.
- `InMemoryVectorStore`: development/test cosine-style normalized vector search.
- `NoOpReranker`: explicit placeholder that preserves top-k order.
- `RetrievalAuthorizer`: converts source access metadata into central authorization decisions.
- `KnowledgeRetrievalService`: hybrid fusion, lexical tie-break, vector-failure fallback and authorization before reranking.

Zero-similarity vector results are excluded. A vector-store failure falls back to keyword retrieval and records an audit event.

## Source types represented

PDF, DOCX, XLSX, CSV and email are normalized into `SourceMetadata`; generic file/document/database source types are also represented by the source model.

PDF page and XLSX sheet locations are preserved by the document processing pipeline.

## Partially implemented

There is no durable vector database in the repository. `VectorStore` is an extension point; the current concrete implementation is in-memory. There is no complete production ingestion scheduler/index lifecycle. No embedding vendor is wired into the repository.

`NoOpReranker` does not perform semantic reranking.

## Planned/Future

A durable vector backend and production embedding provider can implement the existing interfaces. A production ingestion/index lifecycle must preserve the existing authorization metadata and re-run retrieval evaluation with representative enterprise data.
