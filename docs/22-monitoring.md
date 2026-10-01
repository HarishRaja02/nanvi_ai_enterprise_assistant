# Monitoring and Observability

## Implemented

Structured JSON logging is configured by `backend/observability/logging.py`.

Every request gets:
- `request_id`
- `correlation_id`
- application `trace_id`

The middleware returns these as response headers and records request latency.

Important events include:
- authentication success/failure;
- authorization allow/deny;
- security/prompt-injection events;
- API chat start/completion/failure;
- orchestrator routing/completion/failure;
- tool start/deny/timeout/error/completion;
- database success/failure/latency;
- email external API success/failure/latency;
- file connector success/failure/latency;
- retrieval result/denial/fallback/latency;
- report generation success/failure;
- worker job success/failure/retry;
- Redis enqueue success/failure.

Raw prompts, SQL parameters, email bodies, file contents and credentials are intentionally not logged by these events.

Optional OpenTelemetry configuration is available through `OTEL_ENABLED`, service name and OTLP endpoint.

## Audit

Audit events reuse the same request/correlation/trace context and sanitized metadata. This enables a security investigation to correlate a denied authorization decision with the request and downstream operation.

## Partially implemented

The trace ID is application-generated. Automatic W3C trace-context propagation and full external dependency instrumentation are not implemented. Audit storage is in-memory in the current source-reference/report route wiring.

## Planned/Future

Connect JSON logs/audit events to the enterprise SIEM/log platform, configure retention/alerts, and validate end-to-end distributed tracing across real infrastructure.
