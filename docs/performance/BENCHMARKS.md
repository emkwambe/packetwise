# PacketWise Performance Benchmarks

| Sprint | Backend  | Avg (s) | Max (s) | Min (s) | Throughput  | Accuracy | Notes |
|--------|----------|---------|---------|---------|-------------|----------|-------|
| S-011  | SQLite   | 0.414   | 2.113   | 0.045   | 145 pkt/min | 100%     | Docker local, text PDFs |
| S-012  | Supabase | 0.754   | TBD     | TBD     | ~79 pkt/min | 100%     | Cloud DB, 5 packet sample |
| S-013  | Supabase | 0.520   | 0.800   | 0.200   | ~115 pkt/min| 88.9%    | 3-doc packets (W-2 + bank stmt + app), 9 packet sample |

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
