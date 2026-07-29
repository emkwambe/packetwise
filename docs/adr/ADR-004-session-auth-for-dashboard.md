# ADR-004: Session cookie auth for the dashboard

- **Date:** 2026-07-29
- **Status:** Accepted
- **Supersedes:** ADR-002 (API key auth for MVP) for browser traffic only

## Context

ADR-002 added `X-API-Key` middleware and accepted, as a listed negative, that the
dashboard would carry the key in its own HTML. That is what shipped: the literal
key appeared four times in `src/dashboard/index.html`, which the server hands to
any client that requests `/`.

The consequence is that the credential was not a secret. Anyone who could load
the dashboard could read it from page source and then call every endpoint
directly — the same access, without the UI. Rotating it meant editing and
redeploying the page. This was tracked as ISSUE-001.

## Decision

Browsers authenticate with a **password exchanged for an HttpOnly session
cookie**. The API key remains, but only for server-to-server callers.

- `POST /api/v1/auth/login` takes a password, compares it to
  `settings.DASHBOARD_PASSWORD` in constant time, and sets a `pw_session` cookie
- The cookie is `HttpOnly` (JavaScript cannot read it), `SameSite=Lax` (not sent
  on cross-site POSTs), and `Secure` whenever `DEBUG` is off
- The token is stateless: `<expiry_epoch>.<hmac_sha256>` signed with
  `settings.SESSION_SECRET`, valid for `SESSION_TTL_HOURS` (default 12)
- The auth middleware accepts **either** a valid `X-API-Key` **or** a valid
  session cookie
- CORS moved from `allow_origins=["*"]` to an explicit allowlist, because a
  wildcard origin combined with credentials would let any site issue
  authenticated requests on a logged-in user's behalf

## Consequences

**Positive**

- No credential is readable from page source
- The dashboard password can be rotated without touching the frontend
- API key usage narrows to machine callers, where a header credential is
  appropriate
- CSRF exposure is reduced by `SameSite=Lax` plus a real CORS allowlist
- Sessions expire on their own

**Negative**

- **Shared password, not identity.** One password for all operators. It gates
  access; it cannot attribute an action to a person, so there is still no audit
  trail — the ADR-002 limitation is unresolved.
- **Logout is client-side only.** Tokens are stateless, so `POST /auth/logout`
  clears the cookie in that browser but an already-issued token stays valid
  until it expires. A stolen token cannot be revoked. Fixing this requires a
  session store or a token blocklist.
- **Rotating `SESSION_SECRET` invalidates every live session** — acceptable, but
  worth knowing before rotating it in production.
- No password complexity policy, lockout, or rate limiting on the login
  endpoint, so the password is brute-forceable at network speed.

## Alternatives considered

- **Per-user accounts with hashed passwords.** The correct destination, and what
  an audit trail requires. Deferred: it needs a users table, a password reset
  path, and session management that this sprint could not carry.
- **Proxying API calls through a server-side session.** Equivalent security, but
  it duplicates every endpoint behind a BFF layer for no gain at this size.
- **Keeping the API key and restricting by network.** Was the standing
  workaround. It does not fix the credential being public to anyone who can
  reach the page.

## Verification

Ten checks were run against a live server: unauthenticated health 200;
unauthenticated data endpoint 401; `X-API-Key` 200; wrong password 401; correct
password 200 with an `HttpOnly` cookie; cookie-only data access 200; logout 200;
post-logout access 401; and a forged cookie signature 401.
