# AI Security Layer

Canonical documentation: [`../../../docs/10-tool-gateway.md`](../../../docs/10-tool-gateway.md) and [`../../../docs/21-security.md`](../../../docs/21-security.md).

Implemented: prompt-injection heuristics, untrusted-data envelopes, tool allowlisting, tool-call budgets, loop detection, SSRF validation and sensitive-output filtering.

These are defense-in-depth controls. They do not replace backend authentication/authorization.
