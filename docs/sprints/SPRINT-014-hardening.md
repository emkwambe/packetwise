# Sprint 14 — Memos, Auth & Backend Benchmark

- **Date:** 2026-07-29
- **Status:** Complete
- **Repos:** PacketWise (Sprint 14), realitydb-docs (Sprint 3)

## Objective

Six items, run in priority order: replace WeasyPrint with ReportLab, fix the
flagged-scenario DTI margin, repair the broken CLI, replace the client-visible
API key with session auth, produce a clean Supabase-vs-SQLite benchmark, and
document the result.

## 1. Memo generation — ReportLab

`memo_generator.py` rewritten against ReportLab platypus. WeasyPrint and Jinja2
removed from requirements; ReportLab added (it was already a transitive
dependency and is what realitydb-docs uses).

Every memo is now a real PDF. Previously **no memo had ever been a PDF on
Windows** — WeasyPrint's native GTK dependencies are absent, so every call fell
through to an HTML fallback while the database, API and dashboard all reported
it as a memo path. The fallback is gone; there is nothing left to mask a
rendering failure.

Verified: 3 violations + 3 documents → 2-page PDF, 4.5KB, all sections present,
inspected visually. See [ADR-003](../adr/ADR-003-reportlab-over-weasyprint.md).

## 2. ISSUE-005 — flagged scenario margin

`generate_synthetic_bank_statement()` gained `debt_to_income_target`. Loan-bearing
debts (auto + student, 60/40) are now sized to a share of monthly income rather
than drawn at random. Scenarios declare their own target: approved 0.05, flagged
0.07, rejected 0.10.

Flagged DTI now lands at 44.5–46.6% across all ten flagged packets — inside the
43–50% band with margin on both sides.

## 3. cli.py

Repaired imports (`w2_renderer` → `realitydb_docs.w2`,
`bank_statement_renderer` → `realitydb_docs.bank_statement`) and switched to the
batch API. Added `argparse` flags for output dir, counts, seed and
`--annual-income`, which feeds both generators so a produced set is
income-consistent. This file had been broken since before Sprint 13 and could
never have run.

## 4. ISSUE-001 — session auth

The dashboard now contains **zero** occurrences of the API key. It logs in with
`DASHBOARD_PASSWORD` and receives an HttpOnly, `SameSite=Lax`, `Secure`-when-not-
DEBUG cookie holding a stateless HMAC token. The middleware accepts either a
valid `X-API-Key` (machine callers) or a valid session cookie (browsers). CORS
moved from `allow_origins=["*"]` to an explicit allowlist, because a wildcard
origin plus credentials would let any site call the API as a logged-in user.

Ten checks passed against a live server:

| # | Check | Result |
|---|-------|--------|
| 1 | health, no credential | 200 |
| 2 | data endpoint, no credential | 401 |
| 3 | data endpoint, `X-API-Key` | 200 |
| 4 | login, wrong password | 401 |
| 5 | login, correct password | 200, HttpOnly cookie set |
| 6 | data endpoint, cookie only | 200 |
| 7 | dashboard metrics, cookie only | 200 |
| 8 | logout | 200 |
| 9 | data endpoint after logout | 401 |
| 10 | forged cookie signature | 401 |

See [ADR-004](../adr/ADR-004-session-auth-for-dashboard.md). Residual
limitations are filed as ISSUE-007.

## 5. Benchmark — 30 packets, both backends

Same 30 deterministic packets, same host, same code path, same metric.

| | SQLite | Supabase | Delta |
|---|---|---|---|
| Avg | 0.057s | 0.450s | +0.393s (7.9x) |
| Max | 0.101s | 0.634s | +0.533s |
| Min | 0.028s | 0.199s | +0.171s |
| Throughput | 1049 pkt/min | 133 pkt/min | −87% |
| Accuracy | 100% (30/30) | 100% (30/30) | — |
| Confidence | 1.000 | 1.000 | — |

**Both runs produced a clean 10/10/10 with zero errors** — the first runs to hit
the intended distribution exactly.

Two earlier numbers are corrected by this:

- The managed-database cost is **~0.39s per packet**, not the ~0.34s estimated
  in Sprint 12. That estimate compared unlike runs, so its closeness is
  coincidence rather than confirmation.
- **The S-011 SQLite baseline of 0.414s is not a usable reference.** SQLite on
  this host handles a 3-document packet in 0.057s. S-011 ran in Docker against
  different fixtures.

## 6. Documentation

ADR-003 (ReportLab), ADR-004 (session auth), this log, BENCHMARKS with the clean
comparison, and KNOWN-ISSUES updated: 001 and 005 fixed, 003 partially verified,
007 filed.

## Findings

**ISSUE-003 is only partially closed.** Dark mode was verified by stamping
`data-theme="dark"` and rendering — colours resolve correctly. But only the
*login screen* was rendered, and only the `data-theme` path; the
`prefers-color-scheme` media query that fires for most real users is still
untested, as is the signed-in dashboard. Left open rather than claimed.

**ISSUE-006 (housing double-counted in DTI) was not addressed** and remains
open. The extractor-side workaround from Sprint 13 still holds the line.

## Next sprint

Sprint 15 — per-user accounts with a revocable session store and login rate
limiting (ISSUE-007), housing reconciliation in the rule engine (ISSUE-006), and
a full dark-mode pass via CDP (ISSUE-003).
