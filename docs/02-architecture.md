# Architecture

## Implemented

Nanvi is split into a React presentation layer and a Python/FastAPI backend. Backend concerns are separated into API, security, orchestration, integrations, retrieval, analysis, reports, source transparency, jobs and observability.

The main security principle is that AI routing is not an authorization boundary. Protected operations must cross the security/service boundary where authentication context, RBAC/ABAC policy, input validation, execution limits and audit are applied.

### Runtime flow

1. Browser calls the FastAPI API.
2. `RequestContextMiddleware` establishes request, correlation and trace IDs.
3. Protected routes resolve the authenticated `UserIdentity` from a bearer JWT.
4. Application services convert identity to `UserAttributes` and call central authorization.
5. Chat can invoke `EnterpriseOrchestrator`; the graph routes to a capability.
6. Protected connectors/services perform their own authorization and validation.
7. Sources are converted to opaque, permission-checked references.
8. Results return through the API and are rendered by React.

## Data boundaries

- LLM/agent state contains user/tenant/role context and request data, not passwords, API keys, OAuth tokens or database credentials.
- File access is performed by `FileService`/`LocalFileRepository`, not by agents.
- Database access is performed by `DatabaseService`/`PostgreSQLRepository`.
- Email access is performed by `EmailService`/provider adapters.
- Report generators receive structured data and lineage; they do not fetch protected data themselves.

## Partially implemented

The orchestration shell is present, but only the database capability agent has a concrete `run()` implementation. The other capability-agent classes currently inherit the base `NotImplementedError` behavior. The default FastAPI chat dependency is intentionally unconfigured and returns HTTP 503 unless an application composition layer injects a `ChatService`.

## Planned/Future

The interfaces are designed for durable repositories, production identity/session handling, concrete capability agents, managed storage, distributed observability and additional connectors. These are extension points, not current runtime guarantees.
