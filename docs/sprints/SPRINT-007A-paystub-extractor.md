# Sprint 7A — Pay stub extractor

**Date:** 2026-07-29
**Repo:** PacketWise (realitydb-docs unchanged)
**Type:** IDP extraction + cross-document validation
**Closes:** ISSUE-009

---

## Problem — ISSUE-009

realitydb-docs Sprint 6 added two pay stubs to every packet. `DocType.PAY_STUB`
existed in `schemas.py` and `classifier.py` carried a full signature for it, so
a stub classified as `pay_stub` at confidence **1.000**.

`OCRExtractor.extract_fields()` then branched on document type across `W2`,
`APPLICATION`, `BANK_STATEMENT` and `TAX_RETURN` only. A correctly-classified
pay stub fell through to the `else`:

```python
else:
    errors.append("Could not classify document type")
    confidence *= 0.5
```

Two consequences. Packet `extraction_confidence` fell from 1.00 to **0.80** —
`(1 + 1 + 1 + 0.5 + 0.5) / 5` — and the error message asserted the opposite of
what happened: the document *was* classified, it just had no parser.

The deeper cost was that income verification rested on a single source. The pay
stub is the only document in a packet that evidences income without the W-2, and
it was the one document the pipeline did not read.

---

## Solution

### 1. Classifier keywords (`src/idp/classifier.py`)

`PAY_STUB` grew from 3 required + 5 strong keywords to **4 required + 12
strong**, covering the banner title, both section labels, every deduction row
label, both totals rows, and the direct-deposit footer.

Added `matched_keywords(text, doc_type)` for explaining a classification. It is
a separate function rather than a third tuple element because every caller
unpacks `classify_document()` positionally.

Verified: a generated stub matches `pay stub` plus **all 12** strong keywords
and classifies at confidence **1.000**.

Checked for collateral damage. A W-2 contains `federal income tax`,
`social security tax` and `medicare tax`, so it now scores 3 against the
`PAY_STUB` signature — but 12 against `W2`, which still wins comfortably. The
new keyword count does not raise `max_possible` either: `APPLICATION` already
set it at 31, and `PAY_STUB` reaches 26, so no other document type's confidence
moved.

### 2. `PayStubData` schema (`src/idp/schemas.py`)

Pydantic model following the existing `W2Data` / `BankStatementData` pattern —
28 optional fields across identity, pay period, current period, YTD, and
payment.

### 3. Extraction branch (`src/idp/extractor.py`)

`_parse_pay_stub()` plus `_score_pay_stub()`.

Patterns were written against the **actual** extracted text, dumped first
rather than assumed. Two properties of that text drove the implementation:

- **Every value sits on the line after its label.** The panels are two-column,
  so reportlab emits both labels and then both values. `\s+` spans the newline,
  so a table row reads as `LABEL <current> <ytd>` and one pattern yields both
  the current-period and YTD figures.
- **Amounts and dates need different views of the text.** Sibling parsers strip
  commas so a single numeric pattern works everywhere; doing that would turn
  `October 23, 2024` into `October 23 2024`. Amounts are read from a
  comma-stripped copy, dates and names from the raw text.

Two traps avoided, both already solved elsewhere in this file for bank
statements:

- The employer is taken as the line immediately above `EIN:`. The plan's
  "first large uppercase block" would have returned the diagonal
  `SYNTHETIC — NOT VALID` watermark, which extracts ahead of the header.
- The state tax row is labelled with the state code (`NC State Income Tax`), so
  the pattern matches on the substring.

**Confidence:** 0.85 once `gross_pay`, `net_pay` and `ytd_gross` are all
present, +0.05 per optional field, capped at 1.0. A stub missing a required
field scores proportionally to what was found, so a partial parse is visibly
worse rather than silently equal to a full one. The score is multiplied by the
same media penalty every other type carries, so a scanned stub is still
penalised for being a scan.

### Fields extracted

All 27 populate on a generated stub:

| Group | Fields |
|-------|--------|
| Identity | `employee_name`, `employer_name`, `employee_id`, `ssn_last4` |
| Pay period | `pay_period_start`, `pay_period_end`, `pay_date`, `pay_period_number`, `pay_periods_per_year`, `pay_frequency` |
| Current | `gross_pay`, `federal_tax_withheld`, `state_tax_withheld`, `ss_tax_withheld`, `medicare_tax_withheld`, `retirement_deduction`, `total_deductions`, `net_pay` |
| YTD | `ytd_gross`, `ytd_federal_tax`, `ytd_state_tax`, `ytd_ss_tax`, `ytd_medicare_tax`, `ytd_retirement`, `ytd_net_pay`, `ytd_taxable` |
| Payment | `direct_deposit_last4` |

### 4. A pre-existing W-2 bug this uncovered

Checking the employer on a stub against the employer on the W-2 requires the
W-2's employer. It was wrong — and had always been wrong.

The W-2's identity block is two columns, so the text extracts as:

```
c Employer name and address
e/f Employee name and address
Graphic Design Institute      <- employer
Andrew Myers                  <- employee
```

`_parse_w2` used a same-line pattern, `Employer name[,:]?\s*([^\n]+)`, which
captured the remainder of the **label**. Every W-2 PacketWise had ever
processed stored `employer_name = 'and address'` and
`employee_name = 'and address'`. Confidence was unaffected — neither field is
scored — so nothing surfaced it.

Fixed with `_parse_w2_identity_block()`, which locates the adjacent label pair
and reads the following two lines in the same left-to-right order, with a
`_looks_like_label()` guard and a same-line fallback for plain-text fixtures
that do put the value on the label's line.

### 5. Cross-validation (`src/engine/rules.py`)

`cross_validate_pay_stub()` runs inside `evaluate()`, writes findings into
`metrics`, and returns violations. When a packet carries several stubs — the
integration sends the two most recent — the **latest period** is checked,
because that is the one a lender would annualize.

Thresholds live in `config/rules.yaml` alongside the existing ones rather than
being hardcoded.

**CHECK 1 — YTD annualization vs W-2 box 1** → `PAY_STUB_INCOME_MISMATCH`
(warning, tolerance 15%).

This is compared against **YTD taxable** wages — gross less pre-tax deferrals —
not YTD gross. A 401(k) deferral is exempt from income tax but not from FICA, so
YTD gross legitimately exceeds box 1 by the deferral rate, and comparing it
directly flags an honest file. The stub states the taxable figure on its own
line; it is also derivable as `ytd_gross - ytd_retirement`.

The magnitude of the difference, measured across five seeds:

| Seed | 401(k) | Annualized **gross** vs box 1 | Annualized **taxable** vs box 1 |
|------|--------|------------------------------|--------------------------------|
| 42 | 3% | 3.1% | **0.0%** |
| 99 | 0% | 0.0% | **0.0%** |
| 156 | 6% | 6.4% | **0.0%** |
| 7 | 5% | 5.3% | **0.0%** |
| 13 | 0% | 0.0% | **0.0%** |

Both figures are recorded (`paystub_income_variance`,
`paystub_gross_annualized`) so the distinction is visible in the metrics rather
than buried in code. When the pay period number cannot be extracted the check is
skipped and `paystub_income_check` records why, rather than passing silently.

**CHECK 2 — net-to-gross ratio** → `UNUSUAL_DEDUCTION_RATE` (warning, plausible
band 50–95%). Catches a fabricated stub whose deductions do not fit its stated
gross. Observed range on generated stubs: 0.651–0.692, comfortably inside.

**CHECK 3 — employer consistency** → `EMPLOYER_MISMATCH_STUB_VS_W2` (warning,
max edit distance 5). Levenshtein, implemented inline rather than added as a
dependency.

Names are normalised — casefolded, punctuation collapsed, corporate suffixes
dropped — **before** the distance is taken. Without that the check would flag
every honest file: a stub banner prints `GRAPHIC DESIGN INSTITUTE` while a W-2
prints `Graphic Design Institute`, and a case-sensitive comparison of the same
employer scores an edit distance equal to its letter count.

---

## Confidence restored

| | Sprint 6 | Sprint 7A |
|--|----------|-----------|
| Pay stub extraction confidence | 0.500 | **1.000** |
| Packet `extraction_confidence` | 0.80 | **1.00** |
| Fields extracted per stub | 0 | **27** |

Target was > 0.90.

---

## Integration test results

`integrate_realitydb.py --count 9`, 45 documents:

```
approved: 3   flagged: 3   rejected: 3   errors: 0
conf=1.00 on all 9 packets
```

Every DTI and LTV is unchanged from Sprint 6 to one decimal place, so adding
extraction and three new rules moved no decision. Avg processing time 0.552s vs
0.522s (+5.7%) for the extra parse and cross-validation on two documents per
packet.

### The checks were verified to fire

Three checks that have never been observed detecting anything are not a
feature. Each was driven against a deliberately inconsistent stub:

| Scenario | Result |
|----------|--------|
| clean stub (control) | none |
| stub claims 40% more income than W-2 | `PAY_STUB_INCOME_MISMATCH` |
| stub claims 30% less income than W-2 | `PAY_STUB_INCOME_MISMATCH` |
| net = 98% of gross | `UNUSUAL_DEDUCTION_RATE` |
| net = 35% of gross | `UNUSUAL_DEDUCTION_RATE` |
| stub employer is a different company | `EMPLOYER_MISMATCH_STUB_VS_W2` |
| same employer, upper vs title case + ", INC." | none (correctly quiet) |
| pay period number missing | none, check recorded as skipped |
| all three defects at once | all three fired |

These were run as a script, not committed as tests — see remaining issues.

---

## Remaining issue: bank deposits vs net pay

Filed as **ISSUE-010**, deferred.

The bank statement deposits `monthly_gross_income ± 3%`. The pay stub's net pay
is materially lower — 65–69% of gross on generated files. Real payroll deposits
are net, so a lender reconciling stub net pay against statement deposits would
find a discrepancy on **every** packet.

Not fixed here deliberately. PacketWise derives verified income from statement
deposits, so switching the generator to deposit net pay would move every DTI and
every decision in the suite. It needs the generator change and the engine change
in one coordinated sprint.

## Other remaining issues

1. **No committed tests for any of this.** The extraction accuracy checks and
   the nine negative cases above ran as scripts. PacketWise has
   `tests/integration/test_pipeline.py`; the pay stub parser, the W-2 identity
   fix and the three rules all belong there. The W-2 bug is the argument: it
   survived indefinitely because nothing asserted on the field.
2. **The pay stub cannot yet serve as verified income.** `verified_income` still
   comes from W-2 box 1 or tax return AGI. A packet with a stub but no W-2 gets
   no verified income at all, even though the stub carries YTD wages. Making the
   stub a fallback source is a small change with real value.
3. **`_parse_w2_identity_block` depends on extraction order.** It assumes the
   two labels are adjacent and their values follow in the same left-to-right
   order. That holds for this generator's layout and is guarded by
   `_looks_like_label()`, but a differently-laid-out W-2 would need a
   position-aware approach reading coordinates rather than line order.
4. **Employer normalisation drops `co`**, which also strips the word "Co" from
   a legitimate name like "Fourth Coffee Co" — harmless for the distance
   comparison since both sides are normalised identically, but it would be wrong
   if the normalised form were ever displayed.
