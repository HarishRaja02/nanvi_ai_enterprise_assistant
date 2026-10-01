# Email Connector

## Implemented

Current provider: Microsoft Graph delegated mailbox access.

Architecture:
`EmailTool -> EmailService -> EmailRepository -> MicrosoftGraphEmailProvider -> Graph /v1.0/me/messages`

The service requires:
- a delegated access token in the provider context;
- `Mail.Read` scope;
- provider context user/tenant matching the authenticated principal;
- `EMAIL_READ` authorization;
- optional application rate limiting.

Search supports query, sender, recipient, subject, date bounds, attachment presence, result limits and opaque pagination. Graph pagination URLs are constrained to HTTPS `graph.microsoft.com` `/v1.0/me/messages` URLs.

Graph 429 responses preserve `Retry-After`; transport/timeouts are retried only when classified as safe. Invalid responses are converted to safe provider errors. External API latency/failure is logged without tokens or email bodies.

## Read-only boundary

`EmailTool` exposes search, pagination, thread and message retrieval. It does not expose send/write operations.

## Partially implemented

The provider/service are implemented and tested, but there is no email API route in `backend/api`. The default capability `EmailAgent` is not concretely implemented. Attachments are represented as metadata only; there is no malware/sandbox content-download pipeline.

## Planned/Future

A real Entra application registration, delegated consent and token lifecycle must be supplied by deployment. A provider-specific write/action capability is not part of the current implementation.
