# ADR-002: API Key Auth for MVP

- **Date:** 2026-07-29
- **Status:** Accepted
- **Superseded by:** ADR-TBD (session auth, Sprint 14)

## Context

PacketWise had no authentication — any HTTP request could process loans or read
application data. Before any external deployment, at minimum one authentication
layer was required.

## Decision

Implement `X-API-Key` header middleware.

A single API key per deployment is stored in `.env` as `API_KEY`.

Health check, root, and API docs are excluded from authentication.

## Consequences

**Positive**

- Immediate protection against unauthenticated access
- Simple implementation (3 lines)
- No user management complexity

**Negative**

- API key hardcoded in dashboard HTML (client-visible — mitigated by private
  repo and internal use only)
- No per-institution key rotation
- No audit trail per API key
- Must be replaced with session auth before any public deployment

## Excluded paths

| Path | Reason |
|------|--------|
| `/api/v1/health` | Liveness probes must not carry credentials |
| `/` | Serves the dashboard shell |
| `/docs`, `/redoc`, `/openapi.json` | Interactive API documentation |

Every other path returns `401 {"detail": "Invalid or missing API key"}` when the
header is absent or does not match `settings.API_KEY`.

## Related

The client-visible key weakness is tracked as ISSUE-001 in
`docs/issues/KNOWN-ISSUES.md`.
