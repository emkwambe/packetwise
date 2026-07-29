# Sprint 11 — Complete Packet Stress Test

- **Date:** 2026-07-29
- **Status:** Complete
- **Commits:** `7125e35`

## Objective

Validate end-to-end pipeline accuracy against complete loan packets
(W-2 + bank statement + application).

## What was built

Application fixtures for three decision scenarios:

| Fixture | Profile | Expected decision |
|---------|---------|-------------------|
| `app_clean.txt` | DTI ~35%, LTV 80%, credit 720 | Approved |
| `app_flagged.txt` | DTI ~46%, LTV 80%, credit 680 | Flagged |
| `app_rejected.txt` | DTI >50%, credit 580 | Rejected |

Stress test: 30 complete packets (10 per scenario) against the Docker API.

## Results

| Metric | Value |
|--------|-------|
| Decision accuracy | 100% (30/30) |
| Throughput | 145 packets/minute |
| Avg processing time | 0.414s |
| Max processing time | 2.113s |
| Min processing time | 0.045s |
| Errors | 0 |
| Extraction confidence | 1.0 (text PDFs) |

**Decision distribution**

| Decision | Count | Share |
|----------|-------|-------|
| Approved | 10 | 33.3% |
| Flagged | 10 | 33.3% |
| Rejected | 10 | 33.3% |

**Backend:** SQLite (local Docker)

## Key findings

- Pipeline is deterministic and accurate
- Text PDF extraction at 1.0 confidence
- Performance degrades on the first packet (model warmup) — 2.1s vs 0.05s
- No errors across 30 complete packets

## Next sprint implications

- Baseline established for PostgreSQL performance comparison
- Integration with the realitydb-docs W-2 generator validated in principle
- Income variance bug identified when using random W-2 wages vs fixed
  application fixtures
