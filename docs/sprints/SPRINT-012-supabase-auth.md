# Sprint 12 — Supabase + API Key Auth

- **Date:** 2026-07-29
- **Status:** Complete
- **Commits:** `38094ff`, `f5308b7`, `64b080c`

## Objective

Replace SQLite with Supabase PostgreSQL. Add API key middleware to all routes.
Fix the integration script for realitydb-docs.

## What was built

### Change 1 — PostgreSQL connection

- `DATABASE_URL` env-overridable
- psycopg2 sync driver
- Conditional `connect_args`
- `pool_pre_ping` for the Supabase pooler
- SQLite fallback preserved

### Change 2 — API key middleware

- `X-API-Key` header on all routes
- Health / root / docs excluded
- 401 on missing or invalid key
- `API_KEY` from `.env` via pydantic

### Change 3 — Integration script

- W-2 only (bank statements Sprint 13)
- SSNs use the 900-xx-xxxx IRS range
- `X-API-Key` on all requests
- Realistic loan scenarios
- `argparse --count` flag

## Verification results

| Check | Result |
|-------|--------|
| Supabase connected | YES |
| Tables created | 4 (`loan_applications`, `document_records`, `underwriting_exceptions`, `processing_metrics`) |
| Health (no key) | 200 |
| Loans (no key) | 401 |
| Loans (with key) | 200 |
| Integration (5 packets) | 100% success |
| Avg processing on Supabase | 0.754s |
| vs SQLite baseline | 0.414s |
| Delta | +0.340s (Supabase network latency) |

## Issues found during sprint

**ISSUE-001:** `TESSERACT_CMD` typo in `.env` (`TESERACT_CMD`) blocked app
startup. Fixed manually in `.env`.

**ISSUE-002:** API key hardcoded in dashboard HTML (client-visible). Deferred to
Sprint 14.

**ISSUE-003:** Income variance fires on every integration test packet — zero
approvals possible with random W-2 wages vs fixed scenario income. Deferred to
Sprint 13.

> **Numbering note:** these in-sprint IDs are chronological to this sprint and do
> **not** line up with the IDs in `docs/issues/KNOWN-ISSUES.md`, where the
> startup typo is omitted (already fixed) and the remaining items are renumbered.
> Cross-reference by description, not by ID.

## Key decisions made

See [ADR-001](../adr/ADR-001-postgresql-over-sqlite.md) and
[ADR-002](../adr/ADR-002-api-key-auth-mvp.md).

## Next sprint

Sprint 13 — Bank statement generator (realitydb-docs) + bank statement extractor
(PacketWise). Fix the income variance bug.
