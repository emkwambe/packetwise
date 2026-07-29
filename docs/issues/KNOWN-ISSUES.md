# PacketWise Known Issues

> IDs here are the canonical tracker. The in-sprint numbering in
> `docs/sprints/SPRINT-012-supabase-auth.md` differs — cross-reference by
> description.

## ISSUE-001: API key visible in dashboard

- **Severity:** Medium
- **Found:** Sprint 12
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
- **Fix sprint:** 14

**Description**

Dark mode CSS was added in the Sprint 12 dashboard redesign but not verified in
a real browser (headless Chrome cannot set `prefers-color-scheme`).

**Workaround**

None needed for production.

**Fix plan**

Manual browser test in Sprint 14.

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
