# Nanvi AI Enterprise Assistant — Final Observability Validation

**Validation date:** 2026-09-18  
**Environment:** isolated local/test environment  
**Production data modified:** No

## 1. Objective

Make important Nanvi requests traceable across the application path:

`User → API → Orchestrator → Tool Gateway → Connector → Result → Response`

The implementation uses request-scoped context variables and structured JSON logs. Audit events receive the same request/correlation/trace identifiers and are scrubbed before persistence.

## 2. Implemented controls

### Structured logs

`backend/observability/logging.py` now provides:

- JSON log records.
- Event name, timestamp, severity and logger name.
- Request, correlation and trace identifiers.
- Recursive sensitive-value redaction.
- Bearer-token and secret-assignment redaction.
- Windows path redaction as defense-in-depth.
- Bounded string log fields.

The formatter performs a final scrub so accidental sensitive values are not emitted as plain log fields.

### Request IDs

`RequestContextMiddleware`:

- Accepts a validated `X-Request-ID` or generates a 32-character ID.
- Returns `X-Request-ID` on the response.
- Rejects malformed/oversized supplied IDs by replacing them with a generated value.

### Correlation IDs

- Accepts a validated `X-Correlation-ID`.
- Defaults correlation ID to the request ID when none is supplied.
- Returns `X-Correlation-ID` to the caller.
- Preserves the value through synchronous application layers.

### Trace IDs

- Each request receives an application trace ID.
- `X-Trace-ID` is returned to clients.
- Trace ID is included in structured logs and audit events.
- OpenTelemetry remains available through the existing telemetry configuration.

**Important limitation:** the current trace ID is application-generated; full W3C trace-context propagation and automatic instrumentation of every external dependency still require staging/infrastructure integration.

### API observability

Chat requests now log:

- API request start/completion.
- Actor and tenant context.
- Capability count.
- Source count.
- Response latency.
- Controlled failure type/outcome.

Raw user queries are not logged; only query length is recorded.

### Orchestrator observability

The orchestrator logs:

- Graph invocation start/completion/failure.
- Routing decision.
- Capability.
- Agent execution latency.
- Trace-step count.
- Result source count.

No credentials or prompt contents are included.

### Tool Gateway observability

The security gateway logs:

- Tool execution start.
- Authorization/policy denials.
- Tool-call budget failures.
- Timeout failures.
- Execution errors.
- Successful execution latency.

The tool operation itself is never logged as arbitrary content.

### Connector observability

Database, email, file and retrieval paths now emit bounded operational events.

Database:

- query success/failure
- latency
- result row count
- truncation status
- exception type only

Email/external API:

- provider/operation
- success/failure
- rate-limit failure
- latency
- exception type

File connector:

- operation
- success/failure
- byte count
- latency
- exception type

Retrieval:

- returned count
- denied candidate count
- vector fallback status
- latency

No SQL text, email contents, access tokens or file contents are logged by these observability additions.

### Authentication events

Authentication now emits structured success/failure events.

Failures record only a safe reason such as exception type; the bearer token is deliberately never logged.

### Authorization failures

Authorization decisions now emit structured allow/deny events containing:

- actor
- tenant
- permission
- resource ID/type
- policy reason for denial

This supports security investigation without recording the underlying business payload.

### Security events

Prompt-injection rejection emits a security event containing reason codes and input length, not the submitted prompt.

Tool policy and authorization denials are also recorded.

### Worker jobs

Jobs now carry optional request/correlation identifiers when created in a request context.

Worker logs contain:

- job ID
- job name
- attempt number
- retry decision
- success/failure
- request/correlation identifiers when available
- exception type

Job payloads are not logged.

### Errors and latency

Important failures use structured exception types rather than raw exception messages. Request and connector/tool/worker latency is measured in milliseconds.

The HTTP response also exposes `X-Response-Time-Ms`.

## 3. Audit record validation

`AuditEvent` now contains:

- event type
- outcome
- actor ID
- tenant ID
- resource ID
- timestamp
- request ID
- correlation ID
- trace ID
- sanitized investigation metadata

`AuditLogger` applies the same sensitive-data sanitizer before sending metadata to the sink.

This provides enough context to answer:

- Who performed the action?
- Which tenant was involved?
- What resource was targeted?
- What permission/capability was involved?
- Was it allowed, denied, timed out or failed?
- Which request/correlation/trace chain did it belong to?
- When did it happen?
- How long did the relevant operation take?

## 4. Secret logging verification

Explicit tests cover:

- `password`
- `api_key`
- bearer authorization values
- access-token assignments
- nested sensitive fields

The sample log test confirms the secret values are absent and replaced with `[REDACTED]`.

The implementation does not intentionally log:

- passwords
- OAuth access/refresh tokens
- API keys
- client secrets
- private keys
- cookies
- database credentials
- raw email bodies
- raw user prompts
- raw SQL statements
- document contents

## 5. End-to-end sample log inspection

`OBSERVABILITY_SAMPLE_LOG.jsonl` was generated from the existing multi-source chat test.

The same request/correlation/trace identifiers can be followed through:

1. `api_chat_started`
2. `chat_service_started`
3. `orchestrator_started`
4. authorization events
5. email connector completion
6. retrieval completion
7. audit events/source references
8. `orchestrator_completed`
9. `chat_service_completed`
10. `api_chat_completed`
11. `request_completed`

`OBSERVABILITY_GATEWAY_SAMPLE_LOG.jsonl` separately verifies the Tool Gateway path with the same identifiers.

## 6. Tests

Final full backend suite:

**261 passed, 2 warnings**

Additional final observability tests:

**5 passed**

The two warnings are existing PyJWT test warnings concerning a deliberately short test-only HMAC key. They are not production credentials.

## 7. Files changed/added

- `backend/observability/logging.py`
- `backend/observability/middleware.py`
- `backend/observability/__init__.py`
- `backend/security/audit/logger.py`
- `backend/security/authorization/authorization_service.py`
- `backend/security/dependencies.py`
- `backend/security/ai/input_guard.py`
- `backend/agents/security_gateway.py`
- `backend/agents/orchestrator.py`
- `backend/chat/service.py`
- `backend/api/chat_routes.py`
- `backend/integrations/database/postgres.py`
- `backend/integrations/email/service.py`
- `backend/integrations/email/graph.py`
- `backend/integrations/files/service.py`
- `backend/retrieval/service.py`
- `backend/reports/service.py`
- `backend/jobs/queue.py`
- `backend/jobs/worker.py`
- `tests/test_observability_final.py`

## 8. Remaining production hardening

This implementation is validated in the local/test environment but should not be described as a complete enterprise observability deployment until staging infrastructure is connected.

Remaining items:

1. Export logs to the organization's centralized logging/SIEM platform.
2. Use a durable, access-controlled audit store instead of the in-memory test sink.
3. Configure centralized retention and deletion policies.
4. Configure OpenTelemetry exporters and verify trace propagation across API, worker, database, Redis and external API boundaries.
5. Add production log-volume/PII redaction review with the security team.
6. Verify alert rules for authentication failures, authorization denials, tool abuse, dependency failures and elevated latency.
7. Validate worker request/correlation propagation through the actual production queue implementation.
8. Perform a staging test with real PostgreSQL/Redis/Graph/LLM infrastructure without using production data.

## 9. Final assessment

**Observability implementation: VALIDATED for application-level structured logging and correlation in the current test architecture.**

**Production observability certification: NOT YET CLAIMED.**

The important security property is preserved: observability adds investigative context without making secrets, raw business payloads, or credentials part of normal logs or audit metadata.
