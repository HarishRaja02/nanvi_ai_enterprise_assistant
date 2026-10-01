# Frontend Structure

## Implemented

```text
frontend/
├── src/
│   ├── main.tsx      React application and UI state
│   ├── api.ts        typed FastAPI client
│   ├── api.test.ts   API-client unit tests
│   └── styles.css    application styling
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts
├── vitest.config.ts
├── eslint.config.js
└── validate-frontend.mjs   static architecture/UX validation
```

The UI supports login state handling, chat, history, source citation resolution, report download, loading/error/empty states, responsive layout and role-aware navigation. Role visibility is presentation-only; backend authorization remains authoritative.

## Authentication behavior

The frontend checks `/api/auth/me` when a bearer token exists. Tokens are currently stored in browser `sessionStorage` under `nanvi_access_token`. A 401 clears the session. Development demo mode can create a local synthetic identity.

## Partially implemented

- There is no frontend file-upload UI because the backend has no upload route.
- There is no streaming UI because `/api/chat` is JSON, not SSE/WebSocket.
- Production browser SSO callback/session management is not implemented.
- Navigation surfaces for Knowledge, Email, Data, Reports, Finance, HR and Audit are role-aware UI shells; several are empty states rather than dedicated data workspaces.

## Planned/Future

A production deployment can move token/session handling to a backend-managed HttpOnly/Secure/SameSite cookie once the server-side OIDC session flow exists. Rich capability-specific views require corresponding backend APIs.
