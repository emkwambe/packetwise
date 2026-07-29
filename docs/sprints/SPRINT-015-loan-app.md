# Sprint 15 — Loan Application (Form 1003) Generator

- **Date:** 2026-07-29
- **Status:** Complete (9/9 packets on target)
- **Repos:** realitydb-docs (Sprint 4), PacketWise (Sprint 15)

## Objective

Generate synthetic Fannie Mae 1003 loan applications in realitydb-docs, extract
them in PacketWise, and replace the plain-text application stub with a real PDF
so every document in a packet is a generated artefact.

## What was built

### realitydb-docs — `realitydb_docs/loan_app.py` (new, 471 lines)

A two-page Uniform Residential Loan Application summary — not the full ten-page
form — carrying every field the underwriting engine reads.

- Seven sections: loan, property, borrower, employment, assets, liabilities,
  declarations
- Deterministic: `random.Random(seed)` throughout; the same inputs always
  produce the same document
- Weighted distributions per the brief (purchase 80/refinance 20, conventional
  70/FHA 20/VA 10, single family 70/condo 20/multi 10, and so on)
- Test SSNs are 900-xx-xxxx only — the 900 range is never issued by the SSA, so
  a synthetic form cannot collide with a real number
- `SYNTHETIC - NOT VALID` diagonal watermark at 40% opacity on both pages
- Section header bands `#1a3a6b`, labels `#6b7280` 7.5pt, values `#111827` 9pt,
  alternating row shade `#f8fafc`
- DTI colour-coded: green under 43%, amber 43–50%, red above 50%
- Signature block and footer on page 2
- `generate_loan_application_batch()` with `loan_app_NNN.pdf` naming; list
  parameters cycle when shorter than `count`, so one value can apply to all

**Parameters**

| Parameter | Effect |
|---|---|
| `annual_income` | monthly income = `annual_income/12` ±2%, matching a W-2 built for the same income |
| `loan_amount` + `property_value` | used directly; LTV = loan / value |
| `debt_to_income_target` | non-housing liabilities sized so the printed DTI hits the target |
| `credit_score` | optional; printed when supplied |
| `monthly_housing_payment` | optional; printed and counted toward the printed DTI |

`credit_score` and `monthly_housing_payment` are additions to the brief's
signature. The real 1003 carries neither, but PacketWise reads both off the
application — DTI is `(housing + statement debits) / income` — so a 1003 without
them silently changes every scenario's outcome. Both default to `None` and are
omitted from the form when not supplied.

### realitydb-docs — `cli.py`

Added subcommand dispatch: `w2`, `bank-statement`, `loan-app`. The flat-flag
form the file shipped with (`--w2-count`, `--bank-count`) still works — an
unrecognised first argument falls through to it — and gained `--loan-app-count`.

```
python -m realitydb_docs.cli loan-app --count 3 --output output/ --seed 42 \
  --annual-income 87000 --loan-amount 320000 --property-value 420000 \
  --dti-target 0.36
```

### PacketWise — 1003 extraction

`_parse_application()` extended. Pre-existing fields (`borrower_name`,
`loan_amount`, `property_value`, `ssn`, `stated_income_*`, `credit_score`,
`monthly_housing_payment`) are untouched because the rule engine reads them.
Added: `gross_monthly_income`, `monthly_debt`, `ssn_last4`, `loan_purpose`,
`property_type`, `employment_type`, `estimated_dti`, and `ltv_ratio` — taken
from the form when stated, otherwise computed from loan ÷ value.

The classifier gained the 1003 keywords from the brief. It already detected
these PDFs at confidence 1.0 before the change, since
`UNIFORM RESIDENTIAL LOAN APPLICATION` matches two of its existing required
keywords; the additions raise the margin rather than fix a miss.

### PacketWise — integration script

Each packet now carries a generated 1003 PDF in place of the text stub: W-2 PDF
+ two-month bank statement PDF + two-page 1003 PDF. The stub is retained behind
`--text-application`, which isolates a PDF-extraction problem from an
underwriting one when debugging.

## Results

**Integration test — 9 packets, 3 generated PDFs each, Supabase backend**

| Decision | Count | Target |
|----------|-------|--------|
| approved | 3 | 3 |
| flagged | 3 | 3 |
| rejected | 3 | 3 |
| errors | 0 | 0 |

9/9 on target. Extraction confidence 1.0 on every packet.

```
[01] ok want=approved got=approved | 0.370s | DTI=27.8% | LTV=76.2%
[02] ok want=flagged  got=flagged  | 0.570s | DTI=44.5% | LTV=82.6%
[03] ok want=rejected got=rejected | 0.600s | DTI=75.1% | LTV=90.0%
```

Avg 0.472s, max 0.600s, min 0.230s across the nine (127 pkt/min).

**Generator output**

| File | Size | Header |
|---|---|---|
| loan_app_001.pdf | 4,910 B | `%PDF` |
| loan_app_002.pdf | 4,924 B | `%PDF` |
| loan_app_003.pdf | 4,905 B | `%PDF` |

**DTI targeting verified.** A form built with `debt_to_income_target=0.36`
prints `Estimated DTI: 36.0%`.

## Findings

**The brief's `borrower_name` regex over-matches.** `([A-Za-z\s]+)` includes
`\n`, so against the generated PDF it captures `Michael Davis\nSSN`. The
extractor keeps its existing `([^\n]+)` form, which was already correct.

**`Employment Type:\s*(\w+)` truncates `Self-Employed` to `Self`**, because
`\w` excludes the hyphen. Implemented as `([A-Za-z\-]+)`.

**File sizes are ~4.9KB, below the brief's 5KB "content missing" floor.** The
files are complete: 2 pages, 61 text lines, all seven section banners, and every
field extractable. ReportLab embeds no raster data and uses standard Type-1
fonts, so a text-only form compresses to about this size — the same finding as
Sprint 13. Size is not a usable completeness check for these documents; text
extraction is.

**Label/value pairs had to share a baseline.** Sprint 13 found that widely
separated columns extract as separate lines in PyMuPDF, which would break every
`Label: value` regex. Each pair is drawn as two adjacent `drawString` calls on
one baseline, and extraction was verified field-by-field rather than assumed.

**The 1003's own DTI is informational.** The engine recomputes DTI from the
application's housing payment plus bank statement debits and ignores the form's
`Total Monthly Debt` / `Estimated DTI`. So `loan_app_dti_target` changes what
the document *states*, not what decides the file — the two can disagree. For the
rejected scenario they must: housing alone is $3,100 against $4,800 income
(64.6%), so a 0.55 target cannot be met from below.

**Two meanings of `debt_to_income_target`.** The bank statement generator reads
it as the share of income going to loan payments (0.05/0.07/0.10); the 1003
reads it as the whole ratio (0.36/0.45/0.55). The scenarios keep them in
separate keys — passing the 1003 values to the statement generator would push
the approved packet past 50% DTI and reject it.

## Corrections to the sprint brief

- `cli.py` was not subcommand-based; it was a single flat parser. Subcommand
  dispatch was added with the legacy form preserved.
- Each packet already carried three documents; the third was a text stub, so
  Part D was a substitution rather than an addition.
- The classifier already detected the 1003 (confidence 1.0), and
  `_parse_application()` already extracted five of the required fields — Part C
  was an extension.
- Part D's scenario incomes match the existing fixtures ($102k/$74.4k/$57.6k =
  $8,500/$6,200/$4,800 monthly), so no fixture retuning was needed.

## Next sprint

Housing reconciliation in the rule engine (ISSUE-006) is still open. Candidates:
consume the 1003's own `monthly_debt` in the DTI calculation instead of summing
statement debits, which would make the form and the decision agree; and the full
ten-page 1003.
