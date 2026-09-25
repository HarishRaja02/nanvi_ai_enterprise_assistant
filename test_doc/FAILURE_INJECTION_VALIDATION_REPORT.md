# Nanvi AI Enterprise Assistant — Dependency Failure & Resilience Validation

## Scope
Failure-injection validation was performed against the current Nanvi prototype after measuring existing behavior. The objective was to ensure dependency failures fail safely, produce bounded public errors, leave authorization as the security boundary, avoid partial side effects, record failures, and recover only where retrying is safe.

## Final test result
- Failure-injection tests: **16 passed**
- Full Nanvi regression suite: **255 passed, 2 warnings**
- Existing warnings: test-only PyJWT short HMAC key warnings.

## Scenarios
| Scenario | Expected behavior | Result |
|---|---|---|
| PostgreSQL unavailable | bounded retry for connection failures, then safe failure | PASS |
| Redis unavailable | bounded retry, no secret in public error | PASS |
| LLM unavailable | tool execution timeout/failure remains bounded and audited | PASS |
| Microsoft Graph unavailable | timeout is translated to safe provider error; idempotent GET may retry once | PASS |
| File storage unavailable | exception does not create partial persisted report | PASS |
| Vector search unavailable | fall back to keyword retrieval; authorization still runs before return | PASS |
| Worker failure | non-retryable failure is not retried; retryable failure retries only when declared | PASS |
| Network timeout | bounded HTTP timeout and safe error | PASS |
| API/tool timeout | gateway returns timeout and records audit event | PASS |
| Malformed tool response | typed output validator can reject; public filter removes sensitive strings | PASS |
| Invalid LLM response | typed output validator rejects invalid structured output | PASS |
| Report generation failure | storage save is not called after generator failure; temp workspace is cleaned | PASS |

## Retry policy
Retries are restricted to operations that are safe/idempotent:
- PostgreSQL read-only connection failures: bounded retry.
- Microsoft Graph GET requests: bounded retry for transport/timeouts only; 429 is surfaced with provider retry metadata rather than blindly retried.
- Redis job enqueue: bounded retry combined with an atomic Redis idempotency marker so a lost network response does not create duplicate jobs for the same generated job ID.
- Worker retries occur only when the handler failure is explicitly classified as retryable.

Non-idempotent or unknown failures are not automatically retried.

## Timeout policy
- Database statements retain the configured PostgreSQL `statement_timeout`.
- Graph HTTP requests retain the provider HTTP timeout.
- SecureToolGateway retains its execution timeout and audits timeouts.
- A gateway timeout does not grant additional permissions or bypass authorization.

## Recovery behavior
### Vector search
Vector search is an optimization. A vector outage now falls back to the keyword retriever. Retrieved candidates still pass through the normal authorization stage before reranking or return.

### Email
Transport/timeouts can be retried once because the operation is a read-only GET. Provider throttling (`429`) remains a rate-limit condition rather than an uncontrolled retry loop.

### Database
Only connection/interface failures are retried. SQL validation, permission, syntax, and other application/database errors are not retried.

### Redis
Job enqueue uses an atomic `SETNX + RPUSH` Lua operation keyed by the generated job ID. This makes the bounded retry safe against a successful Redis operation followed by a lost client response.

### Worker
A failed job is never reported as successful. Only explicitly retryable exceptions are retried. The public failure is generic and does not include handler internals.

### Reports
Report generation occurs in a temporary directory. The persistent storage `save()` operation is called only after the generator successfully completes. Generator failure therefore cannot publish a partial report through the storage abstraction.

## Security observations
- Authorization remains before protected tool execution.
- No dependency exception is used to grant access.
- Failure messages exposed by the Redis queue do not include the underlying exception text.
- Tool timeouts are audited.
- Vector fallback does not bypass authorization.
- Report generation failures do not publish partial artifacts.
- The model/LLM does not receive database credentials, Redis credentials, filesystem handles, Graph client secrets, or OAuth secrets.

## Production limitations
The failure suite uses controlled failure injection rather than deliberately taking down a real production PostgreSQL, Redis, Microsoft 365, object/file store, vector database, or LLM provider. Before production launch, chaos testing should be repeated in staging with:
- real PostgreSQL connection loss and pool exhaustion;
- real Redis restart/failover and worker crash;
- real Microsoft Graph 429/5xx/timeout behavior;
- real LLM provider timeout/rate-limit/error payloads;
- real persistent vector-store outage;
- reverse-proxy/API timeout behavior;
- multi-instance concurrent failure tests.

The current suite establishes the application's failure-handling contracts without claiming infrastructure availability that was not tested.
