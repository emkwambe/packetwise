# Sprint 13 — Bank Statements & Income Consistency

- **Date:** 2026-07-29
- **Status:** Complete (one target missed — see Results)
- **Repos:** realitydb-docs (Sprint 2), PacketWise (Sprint 13)

## Objective

Generate synthetic bank statements in realitydb-docs, extract them in
PacketWise, and fix the income variance defect that made approvals impossible
(ISSUE-002).

## What was built

### realitydb-docs — bank statement generator

`realitydb_docs/bank_statement.py` rewritten (209 → 445 lines):

- Three bank style templates: **corporate** (navy `#1a3a6b`, First National
  Bank, Helvetica, zebra rows), **regional** (green `#2d6a4f`, Community Bank &
  Trust, Times serif, compact), **digital** (dark `#1a1a2e`, Apex Digital Bank,
  large balance display, colour-coded credits/debits)
- Two months per document, one page each
- Deterministic: `random.Random(seed)` throughout — the same seed always
  reproduces the same borrower, transactions and balances
- `annual_income` parameter drives monthly deposits to `annual_income/12` (±3%),
  keeping a statement consistent with a matching W-2
- Running balance recomputed per transaction and never allowed to go negative —
  a debit that would overdraw is skipped
- Recurring debits (4–7 of 8 categories), irregular debits (5–15/month)
- `SYNTHETIC - NOT VALID` diagonal watermark on every page
- Batch function with `bank_stmt_NNN_style.pdf` naming

### realitydb-docs — W-2 generator

- `target_annual_income` parameter: Box 1 wages land within ±3% of target
- `tax_year` parameter, printed as `{year} W-2 Wage and Tax Statement` plus
  `For calendar year {year}`
- `seed` parameter; generation is now deterministic (previously module-level
  `random`)
- Test SSNs moved into the IRS 900-xx-xxxx range

### PacketWise — bank statement extraction

`_parse_bank_statement()` rewritten. Now extracts `beginning_balance`,
`ending_balance`, `total_deposits`, `total_withdrawals`,
`monthly_recurring_debts`, `account_holder_name`, `statement_period`,
`bank_name`, plus `account_number`, `routing_number` and `statement_months`.

Multi-month aware: the opening balance is the first occurrence, the closing
balance the last, totals are summed across periods, and recurring debts are
divided by the period count to give a genuine monthly figure.

Classifier gained the specified bank keywords; `BankStatementData` gained the
new fields.

### PacketWise — integration script

Documents are generated one group per scenario, each against that scenario's own
annual income, and each packet now carries three documents. Per-packet output
shows expected vs actual decision, DTI and LTV, and prints the firing rules
whenever a decision misses.

## Results

**Integration test — 9 packets, 3 documents each**

| Decision | Count | Target |
|----------|-------|--------|
| approved | 3 | 3 |
| flagged | 2 | 3 |
| rejected | 4 | 3 |
| errors | 0 | 0 |

8 of 9 packets matched their intended scenario. Extraction confidence 1.0 on
every packet; avg 0.520s, max 0.800s, min 0.200s.

**ISSUE-002 — fixed.** Zero new `INCOME_VARIANCE` violations across the run
(the four in the database are Sprint 12 rows). Approved packets went 0 → 3.

**The one miss.** Packet 08 (flagged scenario) computed DTI 51.7%, crossing the
50% critical ceiling, and was rejected rather than flagged:

```
[08] MISS want=flagged got=rejected | DTI=51.7% | LTV=82.6%
     - [critical] DTI_EXCEEDS_MAX: expected <=50%, got 51.7%
     - [warning]  LTV_EXCEEDS_MAX: expected <=80%, got 82.6%
```

Nothing was mis-extracted. The flagged scenario has only ~11 points of headroom
between its base DTI (38.7%) and the 50% ceiling, while bank statements
contribute $0–$1,450/month of randomly drawn recurring debt. Filed as ISSUE-005.

## Findings

**ISSUE-004 was invalid and is closed.** The Sprint 12 report claimed the
approved scenario extracted LTV 82.6% against a stated 76.2%. It did not: 82.6%
is the *flagged* scenario's own ratio (380,000/460,000), and the two packets
involved were flagged-scenario packets. Direct verification gives approved
0.7619, flagged 0.8261, rejected 0.9000 — every value matching its fixture. The
original report mis-mapped borrower numbering to scenario index. No code was
changed.

**Housing is double-counted in DTI (ISSUE-006).** The rule engine adds the
application's housing payment to every bank statement recurring debit, including
the statement's own rent/mortgage line — the same obligation twice. The Sprint 13
extractor works around this by excluding housing from the DTI-facing list, but
the reconciliation belongs in the engine.

**The brief's recurring-debt regex could not work.** Transaction rows in these
PDFs extract as separate lines — description and amount are never on the same
line — so the specified same-line `[^\n]*` pattern matches nothing. The
implemented patterns step over the line break.

**File sizes are ~5KB, not the 30–150KB the brief expected.** ReportLab uses
standard Type-1 fonts and embeds no raster data. Content was verified directly
instead: 2 pages, 132–180 text lines, and all required markers present in each
of the three styles.

## Corrections to the sprint brief

- `pyproject.toml` does not exist; packaging is `setup.py`
- `bank_statement.py` already existed (209 lines) — Part A was a rewrite
- Bank statement extraction, classification and `BankStatementData` already
  existed — Part C was an enhancement
- `generate_synthetic_bank_statement()` changed signature
  (`output_dir` → `output_path`-first); `cli.py` was already broken beforehand,
  importing modules (`w2_renderer`, `bank_statement_renderer`) that do not exist

## Next sprint

Sprint 14 — income-proportional debt profiles in the statement generator
(ISSUE-005), housing reconciliation in the rule engine (ISSUE-006), session auth
to replace the client-visible API key (ISSUE-001), and a manual dark-mode
browser check (ISSUE-003).
