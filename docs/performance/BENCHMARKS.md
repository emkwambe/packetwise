# PacketWise Performance Benchmarks

| Sprint | Backend  | Avg (s) | Max (s) | Min (s) | Throughput  | Accuracy | Notes |
|--------|----------|---------|---------|---------|-------------|----------|-------|
| S-011  | SQLite   | 0.414   | 2.113   | 0.045   | 145 pkt/min | 100%     | Docker local, text PDFs |
| S-012  | Supabase | 0.754   | TBD     | TBD     | ~79 pkt/min | 100%     | Cloud DB, 5 packet sample |
| S-013  | Supabase | 0.520   | 0.800   | 0.200   | ~115 pkt/min| 88.9%    | 3-doc packets (W-2 + bank stmt + app), 9 packet sample |
| S-014  | Supabase | 0.450   | 0.634   | 0.199   | 133 pkt/min | 100%     | 30 packets, 3 docs each, 10/10/10 |
| S-014  | SQLite   | 0.057   | 0.101   | 0.028   | 1049 pkt/min| 100%     | Same 30 packets, same host, same run |

## Sprint 14 — clean backend comparison

Earlier rows could not isolate the database cost: they differed in sample size,
host and document mix. S-014 removes those variables. Both runs used the **same
30 deterministic packets**, on the **same Windows host**, through the **same
code path**, measuring the **same field** (`processing_time_seconds`, server-side
pipeline time) over the last 30 rows of each database.

| | SQLite (local file) | Supabase (cloud) | Delta |
|---|---|---|---|
| Avg | 0.057s | 0.450s | **+0.393s (7.9x)** |
| Max | 0.101s | 0.634s | +0.533s |
| Min | 0.028s | 0.199s | +0.171s |
| Throughput | 1049 pkt/min | 133 pkt/min | -87% |
| Decision accuracy | 100% (30/30) | 100% (30/30) | — |
| Extraction confidence | 1.000 | 1.000 | — |

**The real cost of the managed database is ~0.39s per packet, not the ~0.34s
estimated in Sprint 12** — and the earlier figure was measured against a
different baseline, so the agreement is closer to coincidence than
confirmation. Each packet performs several round trips (document records, loan
row, exception rows, two commits), so the per-round-trip latency is a fraction
of that total.

This also corrects the S-011 baseline: SQLite on this host processes a 3-document
packet in **0.057s**, not the 0.414s recorded in Sprint 11. That S-011 number was
measured in Docker against different fixtures and should not be read as a
SQLite-vs-Supabase reference point.

**Accuracy note.** S-014 is the first run to hit 10/10/10. The fix was
ISSUE-005 — bank statement debts are now sized as a share of income
(`debt_to_income_target`) rather than drawn at random, so the flagged scenario
lands at DTI 44.5–46.6%, inside the 43–50% band on every packet instead of
occasionally crossing the 50% critical ceiling.

## Notes

- S-011 run against Docker with SQLite
- S-012 run against Supabase PostgreSQL us-east-1 region from Windows host
- +340ms latency attributed to Supabase network round trip
- Text PDFs: `extraction_confidence` = 1.0
- Image PDFs (OCR): confidence ~0.85
- Throughput calculated as `60 / avg_time`

## Sprint 13 notes

- S-013 packets carry **three** documents (W-2 PDF + 2-page bank statement PDF +
  text application) versus two in S-012, yet averaged faster — 0.520s vs 0.754s.
  The larger sample (9 vs 5) spreads first-packet warmup more thinly, which is
  the likeliest explanation; per-document cost did not fall.
- Averages are computed over the 9 packets of the run. The
  `/report/performance` endpoint reported 0.603s at the same moment because it
  averages every row in the database, including Sprint 12's.
- Accuracy is measured against the *scenario* each packet was built for, not
  against extraction correctness. Extraction confidence was 1.0 on all 9. The
  single miss (flagged → rejected, DTI 51.7%) is ISSUE-005, a fixture-margin
  problem rather than a pipeline error.

## Caveats

The two rows are not a like-for-like comparison and the +340ms should be read as
an upper bound on the database cost, not a measurement of it:

- **Different sample sizes.** S-011 is 30 packets; S-012 is 5. A 5-packet sample
  carries the first-packet warmup cost (up to ~2.1s in S-011) across a fifth as
  many runs, so it inflates the average independently of the backend.
- **Different hosts.** S-011 ran inside Docker; S-012 ran from the Windows host.
- **Different documents.** S-011 used fixed text fixtures; S-012 used randomly
  generated W-2 PDFs from realitydb-docs.

Isolating the database cost requires running both backends over the same packet
set on the same host. Until then, treat the delta as indicative.
