# PacketWise Known Issues

> IDs here are the canonical tracker. The in-sprint numbering in
> `docs/sprints/SPRINT-012-supabase-auth.md` differs — cross-reference by
> description.

## ISSUE-001: API key visible in dashboard

- **Severity:** Medium
- **Found:** Sprint 12
- **Status:** **Fixed in Sprint 14**
- **Fix sprint:** 14

**Description**

`pw_live_packetwise_2026` is hardcoded in `src/dashboard/index.html`, which is
served publicly. Anyone loading the dashboard can read the key from page source
and make authenticated API calls.

**Workaround**

Keep the dashboard on an internal network only. Do not expose port 8000
publicly.

**Fix plan**

Sprint 14 — add a login page with a session cookie. API key reserved for
server-to-server calls only.

**Resolution (Sprint 14)**

Implemented as planned. The dashboard now contains **zero** occurrences of the
API key; it logs in with `DASHBOARD_PASSWORD` and holds an HttpOnly,
`SameSite=Lax` session cookie it cannot read. CORS moved off the `*` wildcard to
an explicit allowlist. See [ADR-004](../adr/ADR-004-session-auth-for-dashboard.md).

Two limitations remain and are **not** closed by this fix: the password is
shared rather than per-user (so there is still no audit trail), and logout is
client-side only because tokens are stateless — an issued token cannot be
revoked before it expires. Tracked as ISSUE-007.

---

## ISSUE-002: Income variance always fires

- **Severity:** High
- **Found:** Sprint 12
- **Status:** **Fixed in Sprint 13**
- **Fix sprint:** 13

**Description**

`generate_synthetic_w2_batch()` picks wages randomly ($28K–$180K) regardless of
the integration scenario's stated income. The `INCOME_VARIANCE` rule fires
whenever W-2 wages differ from application income by >10%. Result: zero approved
packets in integration tests using random W-2s.

Observed in the Sprint 12 5-packet run: variances of 41.3%, 75.8%, 78.5% and
162.5% against a 10% tolerance.

**Workaround**

Use fixed application fixtures (Sprint 11 approach) instead of random W-2s.

**Fix plan**

Sprint 13 — add a `target_annual_income` parameter to the W-2 generator. The
generator matches within ±5% of target.

**Resolution (Sprint 13)**

`generate_synthetic_w2_batch()` gained `target_annual_income`; wages now land
within ±3% of target. `integrate_realitydb.py` generates documents one group per
scenario, each against that scenario's own annual income, instead of one batch
at random wages.

Verified over a 9-packet run: **zero new `INCOME_VARIANCE` violations** (the four
in the database are Sprint 12 rows), and approved packets went from 0 to 3.

---

## ISSUE-003: Dashboard dark mode unverified

- **Severity:** Low
- **Found:** Sprint 12
- **Status:** **Partially verified in Sprint 14** — still open
- **Fix sprint:** 15

**Description**

Dark mode CSS was added in the Sprint 12 dashboard redesign but not verified in
a real browser (headless Chrome cannot set `prefers-color-scheme`).

**Progress (Sprint 14)**

Verified by rendering a copy of the page with `data-theme="dark"` stamped on the
root element. The dark plane, dark card surface and light ink all resolve
correctly, so the custom-property overrides work.

Two gaps keep this open:

- Only the **login screen** was rendered this way. The signed-in dashboard —
  stat tiles, tables, badges, upload zone — has still never been seen in dark
  mode.
- Only the **`data-theme` path** was exercised. The
  `@media (prefers-color-scheme: dark)` block remains untested, and it is the
  one that fires for most real users.

**Fix plan**

Sprint 15 — drive a signed-in session through Chrome DevTools Protocol
(`Emulation.setEmulatedMedia`) to exercise the media query, and screenshot all
four tabs.

---

## ISSUE-004: LTV exceeds max on the "approved" scenario

- **Severity:** ~~Medium~~
- **Found:** Sprint 12
- **Status:** **Closed — not a defect (invalid report)**
- **Closed:** Sprint 13

**Original description**

Two of the five Sprint 12 integration packets raised `LTV_EXCEEDS_MAX` at 82.6%
while running the `approved` scenario, whose stated figures
(320,000 / 420,000 = 76.2%) are inside the 80% threshold.

**Why it was wrong**

The two packets were not running the `approved` scenario. Scenarios cycle by
packet index, and "Test Borrower 005" is index 4 → scenario 1 (`flagged`), whose
own figures are 380,000 / 460,000 = **82.6%** — correctly over the 80% threshold.
The original report mis-mapped borrower numbering to scenario index.

**Verification (Sprint 13)**

Extraction was run directly against all three fixtures:

| Scenario | Extracted loan | Extracted property | LTV |
|----------|---------------|--------------------|-----|
| approved | 320,000 | 420,000 | **0.7619** |
| flagged | 380,000 | 460,000 | 0.8261 |
| rejected | 450,000 | 500,000 | 0.9000 |

Every value matches its fixture exactly. No extraction or regex defect exists,
and no code was changed for this issue.

---

## ISSUE-005: Flagged scenario sits too close to the DTI cliff

- **Severity:** Medium
- **Found:** Sprint 13
- **Status:** **Fixed in Sprint 14**
- **Fix sprint:** 14

**Description**

With bank statements now in the packet, the rule engine adds the statement's
recurring debts (auto loan, student loan) to the application's housing payment.
The `flagged` scenario has a base DTI of 2,400 / 6,200 = 38.7% against a
**critical** ceiling of 50% — about 11 points of headroom — while
`generate_synthetic_bank_statement()` draws recurring debts at random
($0–$1,450/month depending on seed).

In the Sprint 13 9-packet run, one of three flagged packets crossed the ceiling
(DTI 51.7%) and was rejected instead of flagged, giving 3/2/4 rather than the
target 3/3/3. Nothing is mis-extracted — the packet genuinely carries that debt
load. It is the fixture design that is fragile, not the engine.

**Workaround**

Judge integration runs on the `approved` count and the absence of
`INCOME_VARIANCE`, not on an exact 3/3/3 split.

**Fix plan**

Sprint 14 — give the bank statement generator an income-proportional debt
profile (e.g. a `debt_to_income_target` parameter) so recurring debts scale with
`annual_income` instead of being drawn independently. Widening the gap between
the flagged scenario's base DTI and the 50% ceiling would also work.

**Resolution (Sprint 14)**

`generate_synthetic_bank_statement()` gained `debt_to_income_target`. When set,
the loan-bearing debts (auto + student, split 60/40) are sized to that share of
monthly income instead of drawn at random; other recurring items stay random
because they do not affect DTI. Each scenario now declares its own target
(approved 0.05, flagged 0.07, rejected 0.10).

Verified over 30 packets: flagged DTI landed at **44.5–46.6%** on all ten —
inside the 43–50% band with margin on both sides — and the run produced a clean
**10/10/10** with zero errors.

**Superseded (realitydb-docs Sprint 5)**

The `debt_to_income_target` mechanism still works but is no longer how packets
are built. Liabilities are now sized on `BorrowerProfile` from a single
`dti_target`, and realised DTI equals that target exactly on every seed rather
than approximately. The first Sprint 5 integration run re-opened this failure
mode from the other direction — see ISSUE-008.

---

## ISSUE-007: Session auth is shared-password with no revocation

- **Severity:** Medium
- **Found:** Sprint 14
- **Fix sprint:** 15

**Description**

The Sprint 14 session auth (ADR-004) closes the credential-in-page-source hole,
but two properties of the design are worth tracking explicitly:

1. **One shared password for all operators.** Access is gated, but no action can
   be attributed to a person — the audit-trail gap first noted in ADR-002 is
   still open.
2. **Logout does not revoke.** Tokens are stateless HMAC signatures, so
   `POST /auth/logout` clears the cookie in that browser while the token itself
   stays valid until expiry (default 12h). A leaked token cannot be cancelled
   short of rotating `SESSION_SECRET`, which signs every operator out.

There is also no rate limiting or lockout on `/auth/login`, so the password can
be attacked at network speed.

**Workaround**

Keep `SESSION_TTL_HOURS` short. Use a high-entropy `DASHBOARD_PASSWORD`. Keep
the deployment off the public internet until this is addressed.

**Fix plan**

Sprint 15 — per-user accounts with hashed passwords and a server-side session
store (revocable), plus rate limiting on the login endpoint.

---

## ISSUE-006: Housing payment double-counted in DTI

- **Severity:** Medium
- **Found:** Sprint 13
- **Fix sprint:** 14

**Description**

`UnderwritingEngine.calculate_monthly_debt()` sums the application's
`monthly_housing_payment` **plus** every entry in the bank statement's
`recurring_debits`. A statement's `RENT PAYMENT` / `MORTGAGE PMT` line is the
same obligation the application already declares, so including both counts
housing twice and inflates DTI.

**Workaround (in place)**

The Sprint 13 extractor deliberately excludes housing from the `recurring_debits`
list that feeds DTI, exposing it separately as
`monthly_housing_from_statement`. This prevents the double count today, but the
protection lives in the extractor rather than the engine.

**Fix plan**

Sprint 14 — move the reconciliation into `UnderwritingEngine`: take housing from
whichever source is authoritative, and treat the other as corroboration rather
than an additional debt.

---

## ISSUE-008: Packet documents describe three different borrowers

- **Severity:** Critical
- **Found:** review of the generated packs
- **Status:** **Fixed in realitydb-docs Sprint 5**
- **Fix sprint:** realitydb-docs 5

> Sprint number is in the `realitydb-docs` sequence, not PacketWise's.

**Description**

`w2.py`, `bank_statement.py` and `loan_app.py` each drew identity, employer and
income from their own private name pools. Every generator was deterministic on
its own seed, so the suite looked reproducible, but nothing tied the three
documents in a packet to one person:

```
Loan application: Robert Miller
Bank statement:   Susan Johnson
W-2:              James Jones
```

This made the packs unusable for their stated purpose. PacketWise exists to
test whether identity, employment, income, assets and liabilities reconcile
*across* sources; a packet naming three people cannot exercise that at all.

It also silently weakened every earlier result in this tracker. ISSUE-002 and
ISSUE-005 were closed by threading `target_annual_income` and
`debt_to_income_target` through the generators one parameter at a time — which
aligned the *numbers* across documents while the *people* stayed unrelated.

**Resolution (realitydb-docs Sprint 5)**

Introduced `realitydb_docs/profile.py`: a `BorrowerProfile` dataclass plus a
`FinancialCaseGenerator`. Every document is now a view of one profile — no
renderer generates identity, employer or income independently. Eight
independent RNG streams keep fields from correlating with each other.

`integrate_realitydb.py` builds one profile per packet and renders all three
documents from it.

Verified:

- Seeds 1–25, 11 assertions each (275 checks) — name, employer, SSN and address
  consistent across W-2, bank statement and 1003. All pass.
- Statement recurring debits carry the profile's exact liability amounts;
  ending balance equals the checking assets declared on the 1003.
- 9-packet integration run: **3 approved / 3 flagged / 3 rejected / 0 errors**.
  Stable at 18 packets / seed 500 → 6 / 6 / 6 / 0.

Two profile defects were found *by* that run and fixed before closing:
`dti_target` was overshot by 1.5–3.5% because the credit-card and other-debt
lines were added outside the budget (this pushed two `flagged` packets over the
50% ceiling — the ISSUE-005 failure mode again), and a 10% 401k deferral sat
exactly on the 10% `INCOME_VARIANCE` tolerance, so form rounding decided
whether the rule fired. Deferral now caps at 8%.

**Not closed by this fix**

The deprecated independent generators (`_build_statement_data`, `_build_data`)
are unreachable from any public entry point but still importable. Full detail
in
`../../../realitydb-docs/docs/sprints/SPRINT-005-borrower-profile.md`.

---

## ISSUE-009: Pay stubs classify but cannot be parsed

- **Severity:** Medium
- **Found:** realitydb-docs Sprint 6
- **Status:** **Fixed in Sprint 7A**
- **Fix sprint:** 7A

> Sprint number is in the `realitydb-docs` sequence, not PacketWise's.

**Description**

Packets now carry two pay stubs (periods 22 and 21). `DocType.PAY_STUB` exists
in `src/idp/schemas.py` and `classifier.py` has a full signature for it — a
generated stub classifies as `pay_stub` at confidence **1.000**.

But `OCRExtractor.extract_fields()` in `src/idp/extractor.py` branches on doc
type across `W2`, `APPLICATION`, `BANK_STATEMENT` and `TAX_RETURN` only. A
correctly-classified pay stub falls through to the `else`:

```python
else:
    errors.append("Could not classify document type")
    confidence *= 0.5
```

Two consequences:

1. **Packet `extraction_confidence` fell from 1.00 to 0.80** —
   `(1 + 1 + 1 + 0.5 + 0.5) / 5`. The BENCHMARKS note "Text PDFs:
   `extraction_confidence` = 1.0" no longer holds for any packet with a stub.
2. **The error message is wrong.** The document *was* classified; what is
   missing is a parser. Anyone reading the extraction errors is told the
   opposite of what happened.

Underwriting is unaffected — every DTI and LTV in the 9-packet run is identical
to the 3-document run to one decimal place. The stub is simply inert.

**Why it matters beyond the metric**

The pay stub is the only document in the packet that could verify income
*independently of the W-2*. Right now income verification rests on a single
source, and the document added to corroborate it is the one document the
pipeline does not read.

**Workaround**

Judge runs on the decision split and the violation list, not on
`extraction_confidence`, until a parser exists.

**Fix plan**

Add `_parse_pay_stub()` extracting gross pay, net pay, the YTD columns, pay
period dates and employer, then a rule comparing stub YTD gross against W-2
box 1. The generator guarantees the relationship: at period 26,
`gross YTD − 401k YTD == W-2 box 1` to within $0.01, verified across 25 seeds.
See `../../../realitydb-docs/docs/sprints/SPRINT-006-paystub.md`.

Also correct the `else`-branch message to distinguish "unclassified" from
"classified, no parser".

**Resolution (Sprint 7A)**

Pay stub extractor added. `_parse_pay_stub()` + `_score_pay_stub()` in
`src/idp/extractor.py`, `PayStubData` in `src/idp/schemas.py`, and the
`PAY_STUB` classifier signature widened to 4 required + 12 strong keywords.

**27 fields extracted:** `employee_name`, `employer_name`, `employee_id`,
`ssn_last4`, `pay_period_start`, `pay_period_end`, `pay_date`,
`pay_period_number`, `pay_periods_per_year`, `pay_frequency`, `gross_pay`,
`federal_tax_withheld`, `state_tax_withheld`, `ss_tax_withheld`,
`medicare_tax_withheld`, `retirement_deduction`, `total_deductions`, `net_pay`,
`ytd_gross`, `ytd_federal_tax`, `ytd_state_tax`, `ytd_ss_tax`,
`ytd_medicare_tax`, `ytd_retirement`, `ytd_net_pay`, `ytd_taxable`,
`direct_deposit_last4`.

**Cross-validation** in `UnderwritingEngine.cross_validate_pay_stub()`, with
thresholds in `config/rules.yaml`:

- `PAY_STUB_INCOME_MISMATCH` — annualized YTD **taxable** wages vs W-2 box 1,
  15% tolerance. Taxable, not gross: a 401k deferral is exempt from income tax
  but not FICA, so YTD gross legitimately exceeds box 1 by the deferral rate.
  Measured across five seeds, comparing gross would have shown 0–6.4% variance
  on honest files; comparing taxable shows 0.0%.
- `UNUSUAL_DEDUCTION_RATE` — net-to-gross outside 50–95%.
- `EMPLOYER_MISMATCH_STUB_VS_W2` — Levenshtein distance > 5 after casefolding
  and dropping corporate suffixes. Normalisation is essential: a stub prints the
  employer upper-cased and a W-2 in title case.

Verified: pay stub extraction confidence 0.500 → **1.000**, packet
`extraction_confidence` 0.80 → **1.00**, 9-packet run 3/3/3 with 0 errors and
every DTI unchanged. Each of the three checks was also driven against a
deliberately inconsistent stub and confirmed to fire, and to stay quiet on
benign case/suffix variation.

**Uncovered a pre-existing bug while fixing this.** Checking the stub's employer
against the W-2's required the W-2's employer, which was wrong and always had
been: the W-2 identity block is two columns, so `Employer name[,:]?\s*([^\n]+)`
captured the remainder of the *label*. Every W-2 ever processed stored
`employer_name = 'and address'` and `employee_name = 'and address'`. Confidence
never moved because neither field is scored. Fixed via
`_parse_w2_identity_block()`. Rows written before Sprint 7A still carry the bad
value.

**Not closed by this fix.** None of the above is covered by a committed test —
see ISSUE-011.

---

## ISSUE-010: Bank deposits are gross, pay stub is net

- **Severity:** Medium
- **Found:** realitydb-docs Sprint 6
- **Status:** Deferred to Sprint 8B
- **Fix sprint:** 8B

**Description**

The generated bank statement deposits `monthly_gross_income ± 3%`. The pay stub
reports net pay, which is 65–69% of gross on generated files.

Real payroll deposits are **net**. A lender reconciling the stub's net pay
against the statement's payroll deposit would therefore find a discrepancy on
every packet — the two documents disagree by the entire deduction total.

This is the last remaining cross-document inconsistency in the generated packet
now that ISSUE-009 is closed.

**Why it is deferred rather than fixed**

PacketWise derives verified income from statement deposits. Changing
`BankStatementRenderer` to deposit net pay would change the income figure the
engine reads, and therefore every DTI and every decision in the suite. The
generator change and the engine change have to land together, with the scenario
thresholds re-tuned against the new income basis.

Doing it inside Sprint 7A would have conflated a contained extractor addition
with a change that moves every number in the test suite.

**Workaround**

Do not reconcile stub net pay against statement deposits. Income verification
currently runs off W-2 box 1 and, since Sprint 7A, the stub's YTD taxable wages
— neither of which touches the deposit figure.

**Fix plan**

Sprint 8B — coordinated change:

1. `BankStatementRenderer` deposits net pay, taken from the same profile the
   stub reads, so deposit == stub net exactly.
2. The engine learns that a payroll deposit is net and grosses it up (or reads
   gross from the stub / W-2 instead) before computing DTI.
3. Re-tune the approved/flagged/rejected scenario targets against the new
   income basis and confirm 3/3/3 still holds.

---

## ISSUE-011: No committed tests for IDP extraction

- **Severity:** Medium
- **Found:** Sprint 7A
- **Fix sprint:** unassigned

**Description**

Extraction correctness is verified by ad-hoc scripts at the end of each sprint,
not by anything that runs on its own. `tests/integration/test_pipeline.py`
exercises the pipeline end to end but asserts on decisions, not on extracted
field values.

The W-2 employer bug closed under ISSUE-009 is the argument for this issue
existing. `employer_name` was the literal string `'and address'` for every W-2
the system ever processed. It survived indefinitely because no test asserted on
the field and confidence does not score it — the packet still reported 1.00.

realitydb-docs solved the equivalent problem in its Sprint 6 by committing 400
checks across 25 seeds that assert against text extracted from rendered PDFs.
PacketWise has no counterpart.

**Fix plan**

Add field-level extraction tests per document type, asserting extracted values
against known generator values across several seeds:

- W-2: employer, employee, box 1/2/3/4/5/6
- pay stub: all 27 fields, plus the confidence floor
- bank statement: balances, recurring debits, housing split
- 1003: borrower, loan, property, DTI, LTV, credit score

Plus rule-level tests for the three Sprint 7A checks, including the negative
cases that were run manually.
