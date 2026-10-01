# Secure Tool Gateway

## Implemented

`SecureToolGateway` is a reusable protected execution boundary.

Execution order:
1. Tool allowlist check.
2. Permission/allowlist consistency check.
3. Tool-call budget.
4. Central authorization.
5. Optional input validation.
6. Optional policy callback.
7. Bounded execution timeout.
8. Optional output validation.
9. Sensitive-output filtering.
10. Audit and structured observability.

Default tool-call budget is 8 calls per tenant/user/request context. Default execution timeout is 10 seconds.

The gateway records tool start, denial, timeout, failure and completion events without logging arbitrary tool inputs or outputs.

## Implemented AI-security helpers

- Prompt-injection heuristic detector.
- Untrusted-data/prompt context envelopes.
- Tool allowlist.
- Tool-call budget and repeated-action loop guard.
- SSRF URL validation for HTTPS hosts resolving to non-private addresses.
- Sensitive output filtering.

## Partially implemented

The gateway exists and is tested, but the default `EnterpriseOrchestrator` capability-agent implementations are not all wired through it. `KnowledgeAgent`, `EmailAgent`, `DataAnalysisAgent` and `ReportAgent` currently remain shells. This means the gateway is a reusable security boundary, not proof that every current orchestration path executes through it.

The timeout uses a worker thread; cancellation cannot forcibly terminate arbitrary Python code already running in that thread.

## Planned/Future

Wire every concrete protected agent/tool invocation through the gateway and use integration-native timeouts as a second layer. Replace the in-memory budget registry with a distributed mechanism when multi-instance enforcement is required.
