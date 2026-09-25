# API Documentation

## Implemented routes

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/health` | No | Basic health response `{"status":"ok"}` |
| GET | `/api/health/live` | No | Liveness response |
| GET | `/api/health/ready` | No | Current static readiness response |
| GET | `/api/auth/me` | Bearer JWT | Return validated `UserIdentity` |
| POST | `/api/chat` | Bearer JWT + role/tenant context | Submit a chat query |
| GET | `/api/chat/history` | Bearer JWT + role/tenant context | Return user/tenant conversation summaries |
| GET | `/api/sources/{reference_id}` | Bearer JWT | Re-authorize and return safe source metadata |
| POST | `/api/reports/{report_id}/download-url` | Bearer JWT | Issue a temporary one-time download URL |
| GET | `/api/reports/{report_id}/download` | Bearer JWT + token | Download an authorized report |

## Chat request

```json
{
  "query": "string, 1-4000 chars",
  "conversation_id": "optional, 1-128 chars"
}
```

The response contains `conversation_id`, `answer`, `capability`, `sources`, `trace` and `history`.

## Error behavior

- 401 for missing/invalid bearer authentication.
- 403 when the authentication context lacks tenant/role information.
- 404 for unauthorized/missing conversations or sources where enumeration should be prevented.
- 422 for chat input validation errors.
- 429 for rate limiting.
- 502 for chat orchestration runtime failures.
- 503 when the default chat dependency is not configured.

## Partially implemented

`/api/health/ready` is currently static and does not test PostgreSQL/Redis/other dependency readiness. Report creation, email search, database query, file upload and general admin APIs are not exposed as HTTP routes in this repository.

## Planned/Future

Additional API endpoints should be added only together with service-layer authorization, validation, audit and tests.
