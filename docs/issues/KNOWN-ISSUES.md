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

- **Severity:** Medium
- **Found:** Sprint 12
- **Fix sprint:** 13

**Description**

Two of the five Sprint 12 integration packets raised `LTV_EXCEEDS_MAX` at 82.6%
while running the `approved` scenario, whose stated figures
(320,000 / 420,000 = 76.2%) are inside the 80% threshold. The extracted values
therefore do not match the values written into the application fixture,
suggesting an extraction or field-mapping defect rather than a rules defect.

This is separate from ISSUE-002: correcting income variance alone will not make
the `approved` scenario approve.

**Workaround**

None. Affects integration fixtures only, not production packets.

**Fix plan**

Sprint 13 — trace `loan_amount` and `property_value` from fixture text through
`OCRExtractor` to the persisted row and reconcile.
