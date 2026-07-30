"""
RealityDB → PacketWise Integration
Generates complete synthetic loan packets via
realitydb-docs and processes them through
PacketWise.

Since Sprint 5 every packet is built from one
BorrowerProfile, so the W-2, the bank statement
and the Form 1003 in a packet describe the SAME
borrower with the same employer and the same
income. Before Sprint 5 the three generators drew
identity independently and a single packet could
name three different people.

Usage:
  python integrate_realitydb.py
  python integrate_realitydb.py --count 20
"""
import argparse
import contextlib
import os
import sys
import tempfile
import requests
from pathlib import Path

# Add realitydb-docs to path
sys.path.insert(0, str(
  Path(__file__).parent.parent / "realitydb-docs"
))

try:
  from realitydb_docs.profile import FinancialCaseGenerator
  from realitydb_docs.w2 import W2Renderer
  from realitydb_docs.bank_statement import BankStatementRenderer
  from realitydb_docs.loan_app import LoanAppRenderer
except ImportError as e:
  print(f"ERROR: Cannot import realitydb-docs: {e}")
  print("Ensure realitydb-docs is at:")
  print("  C:\\Users\\HP\\Documents\\realitydb-docs")
  sys.exit(1)

PACKETWISE_URL = "http://localhost:8000/api/v1"
API_KEY = "pw_live_packetwise_2026"

# One entry per expected decision. dti_target sizes the profile's
# liabilities; the engine recomputes DTI from the 1003's housing payment plus
# the statement's non-housing recurring debits, so the target is what drives
# the outcome rather than a figure printed on the form.
#
# credit_score is not part of the plan's scenario table but is retained: the
# engine reads it off the application and a score under 620 is a violation in
# its own right, so dropping it would silently change every outcome.
SCENARIOS = [
  {
    "name": "approved",
    "annual_income": 102000,
    "loan_amount": 320000,
    "property_value": 420000,
    "dti_target": 0.36,
    "credit_score": 740,
  },
  {
    "name": "flagged",
    "annual_income": 74400,
    "loan_amount": 380000,
    "property_value": 460000,
    "dti_target": 0.45,
    "credit_score": 685,
  },
  {
    "name": "rejected",
    "annual_income": 57600,
    "loan_amount": 450000,
    "property_value": 500000,
    "dti_target": 0.55,
    "credit_score": 590,
  },
]


def make_application_text(profile, scenario: dict) -> str:
  """Plain-text 1003 stub, rendered from the same profile as the PDFs.

  Superseded by the generated Form 1003 PDF and kept only for
  --text-application, which is useful when isolating a PDF-extraction
  problem from an underwriting one.
  """
  return f"""Uniform Residential Loan Application
Borrower Name: {profile.full_name}
SSN: {profile.ssn}
Loan Amount: {profile.loan_amount:.0f}
Property Value: {profile.property_value:.0f}
Gross Monthly Income: {profile.monthly_gross_income:.2f}
Credit Score: {profile.credit_score}
Monthly Housing Payment: {profile.monthly_rent_mortgage:.2f}
"""


def run(count: int = 10, text_application: bool = False,
        seed_start: int = 42):
  print("=" * 60)
  print("REALITYDB → PACKETWISE INTEGRATION")
  print(f"Processing {count} loan packets")
  print("=" * 60)

  # Check PacketWise is running
  try:
    r = requests.get(
      f"{PACKETWISE_URL}/health", timeout=5
    )
    if r.status_code != 200:
      print("ERROR: PacketWise not healthy")
      sys.exit(1)
    print(f"\n✓ PacketWise online: {r.json()}")
  except requests.ConnectionError:
    print("ERROR: PacketWise not running.")
    print("Start with: uvicorn main:app --port 8000")
    sys.exit(1)

  gen = FinancialCaseGenerator()

  results = {
    "approved": 0,
    "flagged": 0,
    "rejected": 0,
    "errors": 0
  }

  with tempfile.TemporaryDirectory() as tmpdir:
    print(f"\n[1/2] Building {count} borrower profiles and their documents...")

    packets = []
    for i in range(count):
      scenario = SCENARIOS[i % len(SCENARIOS)]

      # ── One profile per packet: the single source of truth ──
      profile = gen.generate(
        seed=seed_start + i,
        annual_income=scenario["annual_income"],
        loan_amount=scenario["loan_amount"],
        property_value=scenario["property_value"],
        dti_target=scenario["dti_target"],
        scenario=scenario["name"],
        credit_score=scenario["credit_score"],
      )

      # ── All three documents rendered from that one profile ──
      w2_path = W2Renderer(profile).render(
        f"{tmpdir}/w2_{i:03d}.pdf"
      )
      bank_path = BankStatementRenderer(
        profile, month=10
      ).render(
        f"{tmpdir}/bank_{i:03d}.pdf"
      )

      if text_application:
        loan_path = f"{tmpdir}/loan_{i:03d}.txt"
        Path(loan_path).write_text(
          make_application_text(profile, scenario)
        )
        app_mime = "text/plain"
      else:
        loan_path = LoanAppRenderer(profile).render(
          f"{tmpdir}/loan_{i:03d}.pdf"
        )
        app_mime = "application/pdf"

      packets.append({
        "profile": profile,
        "scenario": scenario,
        "w2": w2_path,
        "bank": bank_path,
        "loan": loan_path,
        "app_mime": app_mime,
      })

    print(f"  ✓ {len(packets)} packets, {len(packets) * 3} documents")
    print(f"  Borrower of packet 1: {packets[0]['profile'].full_name} "
          f"({packets[0]['profile'].employer_name})")

    # Process packets
    print(f"\n[2/2] Sending to PacketWise...")

    for i, pkt in enumerate(packets):
      profile = pkt["profile"]
      scenario = pkt["scenario"]

      try:
        # Send all three documents as one packet.
        with contextlib.ExitStack() as stack:
          w2f = stack.enter_context(open(pkt["w2"], "rb"))
          bankf = stack.enter_context(open(pkt["bank"], "rb"))
          appf = stack.enter_context(open(pkt["loan"], "rb"))
          files = [
            ("files", (Path(pkt["w2"]).name,
              w2f, "application/pdf")),
            ("files", (Path(pkt["bank"]).name,
              bankf, "application/pdf")),
            ("files", (Path(pkt["loan"]).name,
              appf, pkt["app_mime"])),
          ]
          r = requests.post(
            f"{PACKETWISE_URL}/process",
            headers={"X-API-Key": API_KEY},
            files=files,
            timeout=60,
          )

        if r.status_code == 200:
          data = r.json()
          status = data.get("status", "unknown")
          time_s = data.get(
            "processing_time_seconds", 0
          )
          conf = data.get(
            "extraction_confidence", 0
          )
          results[status] = \
            results.get(status, 0) + 1
          expected = scenario["name"]
          mark = "ok " if status == expected else "MISS"
          metrics = data.get("metrics", {}) or {}
          dti = metrics.get("dti_ratio")
          ltv = metrics.get("ltv_ratio")
          print(
            f"  [{i+1:02d}] {mark} want={expected:9s} "
            f"got={status:9s} | {time_s:.3f}s "
            f"| conf={conf:.2f} "
            f"| DTI={dti if dti is None else f'{dti*100:.1f}%'} "
            f"| LTV={ltv if ltv is None else f'{ltv*100:.1f}%'} "
            f"| {profile.full_name}"
          )
          # Show what actually fired when the decision misses, so a
          # failing run explains itself without a second pass.
          if status != expected:
            for v in data.get("violations", []):
              print(
                f"       - [{v.get('severity')}] "
                f"{v.get('rule_code')}: "
                f"expected {v.get('expected_value')}, "
                f"got {v.get('actual_value')}"
              )
        else:
          results["errors"] += 1
          print(
            f"  [{i+1:02d}] ERROR "
            f"{r.status_code}: {r.text[:80]}"
          )

      except Exception as e:
        results["errors"] += 1
        print(f"  [{i+1:02d}] EXCEPTION: {e}")

  print("\n" + "=" * 60)
  print("RESULTS")
  print("=" * 60)
  for k, v in results.items():
    bar = "█" * v
    print(f"  {k:12s}: {v:3d} {bar}")

  total = sum(results.values())
  errors = results.get("errors", 0)
  success_rate = (
    (total - errors) / max(total, 1) * 100
  )
  print(f"\n  Success rate: {success_rate:.1f}%")

  # Fetch performance report
  print("\n[Bonus] Performance report...")
  try:
    r = requests.get(
      f"{PACKETWISE_URL}/report/performance",
      headers={"X-API-Key": API_KEY},
      timeout=10,
    )
    if r.status_code == 200:
      report = r.json()
      total_apps = report.get(
        "total_applications", 0
      )
      perf = report.get("performance", {})
      avg_time = perf.get(
        "avg_processing_time_sec", 0
      )
      print(f"  Total in DB: {total_apps}")
      print(f"  Avg time: {avg_time:.3f}s")
  except Exception as e:
    print(f"  Could not fetch report: {e}")

  return results


if __name__ == "__main__":
  parser = argparse.ArgumentParser()
  parser.add_argument(
    "--count", type=int, default=10,
    help="Number of loan packets to process"
  )
  parser.add_argument(
    "--seed", type=int, default=42,
    help="Base seed; packet i uses seed+i"
  )
  parser.add_argument(
    "--text-application", action="store_true",
    help="Send the plain-text 1003 stub instead of the generated PDF "
         "(isolates PDF extraction from underwriting when debugging)"
  )
  args = parser.parse_args()
  run(count=args.count, text_application=args.text_application,
      seed_start=args.seed)
