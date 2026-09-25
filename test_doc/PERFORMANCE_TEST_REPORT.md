# Nanvi AI Enterprise Assistant — Performance Validation Report

Date: 2026-09-18

## Scope

Measured API health latency, authentication service overhead, retrieval, document parsing, report generation, tool execution, concurrency, memory, CPU, queue behavior, and a synthetic LLM latency placeholder. Large documents, large Excel, large SQL-result shaping, repeated questions, and simultaneous users were exercised.

The benchmark intentionally preserves Nanvi's security boundaries. Authorization, tenant checks, SQL validation, row/result limits, parser safety limits, and tool policies were not disabled for performance measurements.

## Environment limitations

This runtime does not provide a live PostgreSQL server, Redis server, or production LLM provider. Therefore:

- PostgreSQL query latency was not represented as a real network/database measurement.
- Redis queue latency, Redis contention, and Redis-backed worker throughput were not claimed as production measurements.
- LLM latency is represented only by a transparent 50 ms synthetic sleep to show its relative contribution; no production-model SLA is claimed.
- The reference worker measurement is only an in-process no-op benchmark and is not a production worker throughput number.

A production staging run must repeat the same harness against real PostgreSQL, Redis, the selected LLM provider, and production-like workers.

## Baseline → optimized measurement

The only code optimization was applied after measuring the baseline. Retrieval was the measured hot path.

| Component | Baseline mean | After mean | Change |
|---|---:|---:|---:|
| API health | 1.526 ms | 1.577 ms | +3.4% |
| Retrieval, 5,000 chunks | 47.37 ms | 17.19 ms | **-63.7%** |
| Repeated retrieval question | 45.98 ms | 16.30 ms* | **~62.6%** |
| XLSX parse, 10k rows | 230.94 ms | 246.08 ms | +6.6% |
| DOCX parse, 1k paragraphs | 51.98 ms | 54.05 ms | +4.0% |
| PPTX parse, 100 slides | 21.51 ms | 28.87 ms | +34.2% |
| PDF parse, 50 pages | 45.71 ms | 54.16 ms | +18.5% |
| CSV parse, 10k rows | 6.34 ms | 6.46 ms | +2.0% |
| TXT parse | 0.0147 ms | 0.0161 ms | +9.1% |
| XLSX report, 1k rows | 20.04 ms | 21.78 ms | +8.7% |
| PDF report, 1k rows | 97.30 ms | 101.78 ms | +4.6% |
| DOCX report, 1k rows | 353.45 ms | 346.91 ms | -1.9% |
| PPTX report, 1k rows | 304.72 ms | 298.45 ms | -2.1% |
| Secure tool execution | 0.161 ms | 0.119 ms | -26.1% |
| In-memory enqueue | 0.0207 ms | 0.00340 ms | -83.6% |

\* The final standalone benchmark was 17.19 ms for the same 5k-chunk workload. The baseline repeated-query run was 45.98 ms. The difference is attributable to the same retrieval optimization; no correctness/security behavior was removed.

### Retrieval optimization

The measured bottleneck was repeated tokenization and full sorting in the in-memory lexical/vector reference stores.

Optimizations:

1. Cache normalized keyword token sets at index time.
2. Remove stale token-index entries on chunk upsert.
3. Use bounded top-k selection rather than sorting every candidate.
4. Normalize vectors at index time.
5. Use dot product on normalized vectors during search.
6. Use bounded top-k selection for vector candidates.

Authorization still happens before reranking/return. No ACL or tenant filtering was moved later or removed.

## Current performance measurements

### API and authentication

- API health: mean 1.271 ms, p50 1.193 ms, p95 1.786 ms, p99 4.689 ms over 100 calls.
- Authentication service delegation overhead with a fake validator: ~0.000108 ms mean over 1,000 calls. This isolates application-service overhead only; real JWT signature/JWKS/network latency must be measured with the real IdP/JWKS path.

### Retrieval

5,000 indexed chunks:

- mean 16.30 ms
- p50 14.01 ms
- p95 18.77 ms
- p99 115.36 ms

The p99 outlier is consistent with process/runtime scheduling/GC variability in this local benchmark and should be rechecked in a production-like worker process.

### Document processing

- XLSX 10k rows: 246.1 ms mean
- DOCX 1k paragraphs: 54.0 ms mean
- PPTX 100 slides: 28.9 ms mean
- PDF 50 pages: 54.2 ms mean
- CSV 10k rows: 6.46 ms mean
- TXT: 0.016 ms mean

The main document-processing hotspot in this controlled workload is XLSX parsing.

### Database

A controlled reference benchmark covering SQL validation plus shaping of the bounded 500-row result measured 0.0201 ms mean (p95 0.0223 ms). This excludes real PostgreSQL network, planning, disk/cache, lock, and execution time because PostgreSQL is unavailable in this runtime. The production SQL path retains its read-only transaction, statement timeout, row/result limits, and authorization checks.

### Report generation

1,000 rows:

- XLSX: 21.8 ms
- PDF: 101.8 ms
- DOCX: 346.9 ms
- PPTX: 298.4 ms

DOCX and PPTX generation are materially slower than XLSX and are candidates for background-job execution for larger reports.

### LLM

No production LLM provider is configured in this runtime. A 50 ms synthetic delay measured 50.15 ms mean. This is not an LLM benchmark; it only demonstrates that model/network latency is expected to dominate sub-100 ms local component operations when the model takes tens or hundreds of milliseconds.

### Tool execution

SecureToolGateway fast-path overhead measured 0.119 ms mean for a trivial operation. This measurement includes the gateway's allowlist, authorization, budget, execution wrapper, output validation and audit path. Real tool latency will be dominated by the underlying database, Graph, retrieval, or report operation.

### Concurrency / simultaneous users

The optimized 5k-chunk retrieval workload was run with 1, 10, 25 and 50 concurrent workers, 10 requests per worker:

| Workers | Requests | RPS | CPU time | CPU utilization of one core | RSS delta |
|---:|---:|---:|---:|---:|---:|
| 1 | 10 | 63.2 | 0.170 s | 107% | +0.75 MB |
| 10 | 100 | 56.3 | 1.80 s | 101% | +8.50 MB |
| 25 | 250 | 53.1 | 4.82 s | 102% | +15.60 MB |
| 50 | 500 | 57.4 | 8.93 s | 103% | +23.71 MB |

The reference retrieval implementation is CPU-bound around one core. Increasing concurrency does not scale RPS linearly, which is expected for the in-memory Python implementation.

### Process memory

The benchmark process RSS increased by about 139.5 MB while constructing and exercising the 5,000-chunk corpus plus large parser/report fixtures. This is a synthetic aggregate measurement, not a production steady-state memory baseline.

### Queue / worker

Redis is not available in the test environment. The Redis queue implementation therefore was not falsely benchmarked.

The local in-memory queue enqueue operation was measured, but it is only a development reference. The code currently provides enqueue behavior; a production worker/acknowledgement loop is not implemented in this prototype. Consequently, no production Redis worker throughput number is claimed.

## Bottlenecks identified

1. **Retrieval CPU cost** — addressed with measured indexing/search optimizations.
2. **XLSX parsing** — currently the slowest large-document parser in the tested workload.
3. **DOCX/PPTX report generation** — relatively expensive and should be treated as background work for larger outputs.
4. **Production LLM** — expected to dominate end-to-end answer latency once connected, but not measurable here without the real provider.
5. **Real PostgreSQL/Redis/network calls** — unavailable here and therefore require staging measurements.
6. **In-memory retrieval scalability** — linear scans remain a prototype limitation; production should use the planned persistent/vector search infrastructure for larger corpora.

## Correctness and security preservation

The optimization did not weaken:

- authorization filtering
- tenant isolation
- permission checks
- source-level access control
- SQL read-only controls
- query/result limits
- tool-call budgets
- output validation
- parser safety limits
- report lineage authorization

Regression tests after optimization:

- Security/integration suite: **163 passed, 2 warnings**
- Functional/integration suite: **46 passed**
- Full Nanvi suite: **239 passed, 2 warnings**
- Performance regression suite: **2 passed**

## Release assessment

The measured prototype performance is healthy for the tested local workloads, with retrieval showing a substantial improvement. It is **not** a production capacity/SLA certification because PostgreSQL, Redis, production LLM, production workers, and production network infrastructure were unavailable in this environment.

The next staging performance gate should measure real:

- PostgreSQL connection-pool saturation and query latency
- Redis enqueue/dequeue/claim/ack latency
- worker throughput and queue depth under sustained load
- actual LLM first-token and full-response latency
- multi-process/container CPU and RSS
- persistent vector database latency
- 95th/99th percentile end-to-end chat latency
- failure behavior under dependency saturation
