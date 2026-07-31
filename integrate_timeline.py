"""
Timeline Case Integration Test
================================
Generates timeline cases via realitydb-docs
and processes them through PacketWise.

Tests:
  1. Decision accuracy: does PacketWise
     reach the same decision as ground truth?
  2. Fraud detection: does PacketWise flag
     INCOME_VARIANCE on fraud cases?
  3. Cross-document validation: does
     PacketWise catch the 1003 vs W-2 mismatch?

Two metrics, reported separately
--------------------------------
These measure different things and must not be
added together.

METRIC 1 — decision accuracy. Ground truth comes
from realitydb-docs' derive_decision(), which
grades the DTI and LTV bands of the borrower's
WORLD state. PacketWise decides on violation
severity: any critical -> rejected, any warning
-> flagged, otherwise approved.

Those are different functions and they diverge on
a fraud case by construction. An income
overstatement raises INCOME_VARIANCE, a WARNING,
so PacketWise says "flagged" while the borrower's
real DTI is already past the ceiling and ground
truth says "rejected". That disagreement is
expected. It is reported, not counted as failure.

METRIC 2 — fraud detection. Did INCOME_VARIANCE
fire on the cases that carry an overstatement, and
stay quiet on the ones that do not? This is the
metric that matters. A fraud case where PacketWise
says "flagged" AND INCOME_VARIANCE fired is a
SUCCESS: the violation is the finding, the label
is a downstream policy choice.

Usage:
  python integrate_timeline.py
  python integrate_timeline.py --count 9
"""
import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

import requests

# Add realitydb-docs to path
sys.path.insert(
    0,
    str(Path(__file__).parent.parent / "realitydb-docs")
)

try:
    from realitydb_docs.profile import (
        FinancialCaseGenerator
    )
    from realitydb_docs.timeline import (
        career_growth_timeline,
        financial_stress_timeline,
        income_inflation_fraud_timeline,
        TimelineCaseBundler,
        derive_decision,
    )
except ImportError as e:
    print(f"ERROR: Cannot import realitydb-docs: {e}")
    print(
        "Ensure realitydb-docs is at: "
        "C:\\Users\\HP\\Documents\\realitydb-docs"
    )
    sys.exit(1)

PACKETWISE_URL = "http://localhost:8000/api/v1"
API_KEY = os.environ.get(
    "PACKETWISE_API_KEY", "pw_live_packetwise_2026"
)

# The six documents a timeline case ships. The engine reads only the FIRST
# bank statement it finds (`next(...)` in UnderwritingEngine.evaluate), so
# November is extracted and then unused. Not a defect for this test — both
# statements carry the same recurring debts — but it is why sending two does
# not change the DTI. Tracked as a Sprint 11 item.
CASE_DOCUMENTS = (
    "w2_2024.pdf",
    "bank_oct_2024.pdf",
    "bank_nov_2024.pdf",
    "loan_app_1003.pdf",
    "paystub_period22.pdf",
    "paystub_period21.pdf",
)

TIMELINE_SCENARIOS = [
    {
        "name": "career_growth",
        "timeline_fn": career_growth_timeline,
        "profile_params": {
            "annual_income": 72000,
            "loan_amount": 320000,
            "property_value": 420000,
            "dti_target": 0.36,
            "scenario": "approved",
        },
        "expect_fraud": False,
    },
    {
        "name": "financial_stress",
        "timeline_fn": financial_stress_timeline,
        "profile_params": {
            "annual_income": 74400,
            "loan_amount": 380000,
            "property_value": 460000,
            "dti_target": 0.45,
            "scenario": "flagged",
        },
        "expect_fraud": False,
    },
    {
        "name": "income_inflation_fraud",
        "timeline_fn": income_inflation_fraud_timeline,
        "profile_params": {
            "annual_income": 57600,
            "loan_amount": 450000,
            "property_value": 500000,
            "dti_target": 0.55,
            "scenario": "rejected",
        },
        "expect_fraud": True,
    },
]


def send_case_to_packetwise(
    case_dir: str,
    headers: dict,
) -> dict:
    """
    Send all documents from a timeline case
    to PacketWise for processing.
    Returns the API response.
    """
    docs_dir = os.path.join(case_dir, "documents")

    files = []
    handles = []

    for doc_name in CASE_DOCUMENTS:
        doc_path = os.path.join(docs_dir, doc_name)
        if os.path.exists(doc_path):
            fh = open(doc_path, "rb")
            handles.append(fh)
            files.append(
                ("files", (doc_name, fh, "application/pdf"))
            )

    try:
        r = requests.post(
            f"{PACKETWISE_URL}/process",
            headers=headers,
            files=files,
            timeout=120,
        )
        if r.status_code == 200:
            return r.json()
        return {
            "error": r.status_code,
            "text": r.text[:200],
        }
    finally:
        for fh in handles:
            fh.close()


def _violation_codes(violations) -> list:
    """Rule codes from the API's violation list."""
    codes = []
    for v in violations or []:
        if isinstance(v, dict):
            codes.append(v.get("rule_code", str(v)))
        else:
            codes.append(str(v))
    return codes


def run(count: int = 9):
    print("=" * 72)
    print("TIMELINE CASE INTEGRATION TEST")
    print("realitydb-docs -> PacketWise")
    print("=" * 72)

    # Check PacketWise is running
    try:
        r = requests.get(
            f"{PACKETWISE_URL}/health", timeout=5
        )
        if r.status_code != 200:
            print("ERROR: PacketWise not healthy")
            sys.exit(1)
        print("\n[ok] PacketWise online")
    except requests.ConnectionError:
        print("ERROR: PacketWise not running.")
        print(
            "Start with: "
            ".\\venv\\Scripts\\python.exe -m uvicorn "
            "main:app --port 8000"
        )
        sys.exit(1)

    gen = FinancialCaseGenerator()
    bundler = TimelineCaseBundler()
    headers = {"X-API-Key": API_KEY}

    results = []
    cases_per_type = max(1, count // 3)

    with tempfile.TemporaryDirectory() as tmpdir:

        case_num = 0

        for scenario in TIMELINE_SCENARIOS:
            for _ in range(cases_per_type):
                seed = case_num * 37 + 1000  # spread seeds
                case_num += 1

                # Generate profile and timeline
                profile = gen.generate(
                    seed=seed,
                    **scenario["profile_params"],
                )
                timeline = scenario["timeline_fn"](
                    profile, months=18
                )

                # Generate case folder
                case_id = f"tc-{seed:05d}"
                case_dir = bundler.generate_timeline_case(
                    timeline=timeline,
                    output_dir=tmpdir,
                    case_id=case_id,
                )

                # Read ground truth. This is derive_decision() over the
                # WORLD state, not the scenario label the timeline
                # started from.
                with open(
                    os.path.join(
                        case_dir,
                        "evaluation",
                        "expected_decision.json",
                    ),
                    encoding="utf-8",
                ) as f:
                    ground_truth = json.load(f)

                gt_decision = ground_truth.get(
                    "expected_decision", "unknown"
                )
                gt_fraud = ground_truth.get(
                    "fraud_present", False
                )
                gt_dti = ground_truth.get("dti_ratio")
                world = timeline.world_state_at(18)

                try:
                    response = send_case_to_packetwise(
                        case_dir, headers
                    )

                    if "error" in response:
                        raise RuntimeError(
                            f"HTTP {response['error']}: "
                            f"{response.get('text', '')}"
                        )

                    pw_decision = response.get(
                        "status", "error"
                    )
                    pw_violations = _violation_codes(
                        response.get("violations", [])
                    )
                    pw_metrics = response.get(
                        "metrics", {}
                    ) or {}
                    pw_confidence = response.get(
                        "extraction_confidence", 0
                    )
                    pw_time = response.get(
                        "processing_time_seconds", 0
                    )

                    income_variance_flagged = (
                        "INCOME_VARIANCE" in pw_violations
                    )

                    decision_match = (
                        pw_decision == gt_decision
                    )

                    result = {
                        "case_id": case_id,
                        "type": scenario["name"],
                        "seed": seed,
                        "ground_truth_decision": gt_decision,
                        "packetwise_decision": pw_decision,
                        "decision_match": decision_match,
                        "world_dti": gt_dti,
                        "pw_dti": pw_metrics.get("dti_ratio"),
                        "pw_income_variance": pw_metrics.get(
                            "income_variance"
                        ),
                        "stated_income": pw_metrics.get(
                            "stated_income_annual"
                        ),
                        "verified_income": pw_metrics.get(
                            "verified_income_annual"
                        ),
                        "fraud_expected": gt_fraud,
                        "income_variance_fired": (
                            income_variance_flagged
                        ),
                        "violations": pw_violations,
                        "confidence": pw_confidence,
                        "time_s": round(pw_time, 3),
                        "world_income": round(
                            world.annual_gross_income, 2
                        ),
                    }
                    results.append(result)

                    match_icon = (
                        "MATCH " if decision_match
                        else "DIFFER"
                    )
                    if gt_fraud:
                        fraud_icon = (
                            "  [FRAUD DETECTED]"
                            if income_variance_flagged
                            else "  [FRAUD MISSED]"
                        )
                    else:
                        fraud_icon = (
                            "  [FALSE POSITIVE]"
                            if income_variance_flagged
                            else ""
                        )

                    print(
                        f"  [{case_num:02d}] {case_id} | "
                        f"{scenario['name']:22s} | "
                        f"GT:{gt_decision:8s} "
                        f"PW:{pw_decision:8s} "
                        f"{match_icon}"
                        f"{fraud_icon}"
                    )

                except Exception as e:
                    print(
                        f"  [{case_num:02d}] {case_id} | "
                        f"ERROR: {e}"
                    )
                    results.append({
                        "case_id": case_id,
                        "type": scenario["name"],
                        "seed": seed,
                        "error": str(e),
                        "decision_match": False,
                        "fraud_expected": scenario[
                            "expect_fraud"
                        ],
                        "income_variance_fired": False,
                    })

    # ── Summary ──────────────────────────────────────────
    print()
    print("=" * 72)
    print("RESULTS")
    print("=" * 72)

    total = len(results)
    errors = [r for r in results if "error" in r]
    fraud_cases = [
        r for r in results
        if r.get("fraud_expected", False)
    ]
    clean_cases = [
        r for r in results
        if not r.get("fraud_expected", False)
        and "error" not in r
    ]

    decision_matches = sum(
        1 for r in results
        if r.get("decision_match", False)
    )
    # Fraud cases are expected to differ: an overstatement is a WARNING to
    # PacketWise, so it says "flagged" while ground truth grades the real
    # DTI as "rejected". Scored separately so the expected divergence does
    # not read as a failure.
    clean_matches = sum(
        1 for r in clean_cases
        if r.get("decision_match", False)
    )
    fraud_detected = sum(
        1 for r in fraud_cases
        if r.get("income_variance_fired", False)
    )
    false_positives = sum(
        1 for r in clean_cases
        if r.get("income_variance_fired", False)
    )

    print()
    print("METRIC 1 - DECISION ACCURACY")
    print(
        f"  Overall:            {decision_matches}/{total} "
        f"({decision_matches/max(total,1):.0%})"
    )
    print(
        f"  Clean cases only:   {clean_matches}/"
        f"{len(clean_cases)} "
        f"({clean_matches/max(len(clean_cases),1):.0%})"
    )
    if fraud_cases:
        fraud_matches = sum(
            1 for r in fraud_cases
            if r.get("decision_match", False)
        )
        print(
            f"  Fraud cases:        {fraud_matches}/"
            f"{len(fraud_cases)}  "
            f"(divergence here is EXPECTED - see module docstring)"
        )

    print()
    print("METRIC 2 - FRAUD DETECTION (the key metric)")
    if fraud_cases:
        print(
            f"  INCOME_VARIANCE fired: {fraud_detected}/"
            f"{len(fraud_cases)} "
            f"({fraud_detected/max(len(fraud_cases),1):.0%})"
        )
    print(
        f"  False positives on clean cases: "
        f"{false_positives}/{len(clean_cases)}"
    )

    if errors:
        print()
        print(f"  ERRORS: {len(errors)}")
        for r in errors:
            print(f"    {r['case_id']}: {r['error'][:100]}")

    print()
    print("BY TYPE:")
    for tl_type in [
        "career_growth",
        "financial_stress",
        "income_inflation_fraud",
    ]:
        type_results = [
            r for r in results
            if r.get("type") == tl_type
        ]
        if not type_results:
            continue
        matches = sum(
            1 for r in type_results
            if r.get("decision_match", False)
        )
        print(
            f"  {tl_type:24s}: "
            f"{matches}/{len(type_results)} decisions match"
        )

    # Income comparison — the arithmetic the fraud check rests on
    if fraud_cases:
        print()
        print("FRAUD CASES - income as PacketWise read it:")
        for r in fraud_cases:
            if "error" in r:
                continue
            stated = r.get("stated_income") or 0
            verified = r.get("verified_income") or 0
            var = r.get("pw_income_variance")
            print(
                f"  {r['case_id']}: 1003 states "
                f"${stated:,.0f}/yr vs W-2 box 1 "
                f"${verified:,.0f} "
                f"= {var*100:.1f}% variance"
                if var is not None else
                f"  {r['case_id']}: variance not computed"
            )

        print()
        print("FRAUD CASE VIOLATIONS:")
        for r in fraud_cases:
            if "violations" not in r:
                continue
            print(f"  {r['case_id']}:")
            for code in r["violations"]:
                print(f"    - {code}")

        print()
        print("CLEAN CASE VIOLATIONS:")
        for r in clean_cases:
            codes = r.get("violations", [])
            print(
                f"  {r['case_id']} ({r['type']}): "
                f"{', '.join(codes) if codes else 'none'}"
            )

    # Performance
    times = [
        r["time_s"] for r in results if "time_s" in r
    ]
    if times:
        avg_time = sum(times) / len(times)
        print()
        print(
            f"PERFORMANCE: avg {avg_time:.3f}s "
            f"({60/max(avg_time, 0.001):.0f} cases/min)"
        )

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--count", type=int, default=9,
        help="Total cases (divisible by 3)"
    )
    args = parser.parse_args()
    run(count=args.count)
