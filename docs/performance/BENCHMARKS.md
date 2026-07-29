# PacketWise Performance Benchmarks

| Sprint | Backend  | Avg (s) | Max (s) | Min (s) | Throughput  | Accuracy | Notes |
|--------|----------|---------|---------|---------|-------------|----------|-------|
| S-011  | SQLite   | 0.414   | 2.113   | 0.045   | 145 pkt/min | 100%     | Docker local, text PDFs |
| S-012  | Supabase | 0.754   | TBD     | TBD     | ~79 pkt/min | 100%     | Cloud DB, 5 packet sample |

## Notes

- S-011 run against Docker with SQLite
- S-012 run against Supabase PostgreSQL us-east-1 region from Windows host
- +340ms latency attributed to Supabase network round trip
- Text PDFs: `extraction_confidence` = 1.0
- Image PDFs (OCR): confidence ~0.85
- Throughput calculated as `60 / avg_time`

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
