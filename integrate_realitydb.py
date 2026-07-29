"""
RealityDB → PacketWise Integration
Generates synthetic W-2s and bank statements
via realitydb-docs and processes them through
PacketWise as complete loan packets.

Usage:
  python integrate_realitydb.py
  python integrate_realitydb.py --count 20
"""
import argparse
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
  from realitydb_docs.w2 import generate_synthetic_w2_batch
  from realitydb_docs.bank_statement import (
    generate_synthetic_bank_statement_batch
  )
except ImportError as e:
  print(f"ERROR: Cannot import realitydb-docs: {e}")
  print("Ensure realitydb-docs is at:")
  print("  C:\\Users\\HP\\Documents\\realitydb-docs")
  sys.exit(1)

PACKETWISE_URL = "http://localhost:8000/api/v1"
API_KEY = "pw_live_packetwise_2026"

SCENARIOS = [
  {
    "name": "approved",
    "ssn": "900-12-3456",
    "loan_amount": 320000,
    "property_value": 420000,
    "gross_monthly_income": 8500,
    "credit_score": 740,
    "monthly_housing_payment": 1900,
  },
  {
    "name": "flagged",
    "ssn": "900-23-4567",
    "loan_amount": 380000,
    "property_value": 460000,
    "gross_monthly_income": 6200,
    "credit_score": 685,
    "monthly_housing_payment": 2400,
  },
  {
    "name": "rejected",
    "ssn": "900-34-5678",
    "loan_amount": 450000,
    "property_value": 500000,
    "gross_monthly_income": 4800,
    "credit_score": 590,
    "monthly_housing_payment": 3100,
  },
]

def make_application_text(scenario: dict, index: int) -> str:
  return f"""Uniform Residential Loan Application
Borrower Name: Test Borrower {index:03d}
SSN: {scenario["ssn"]}
Loan Amount: {scenario["loan_amount"]}
Property Value: {scenario["property_value"]}
Gross Monthly Income: {scenario["gross_monthly_income"]}
Credit Score: {scenario["credit_score"]}
Monthly Housing Payment: {scenario["monthly_housing_payment"]}
"""

def run(count: int = 10):
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

  with tempfile.TemporaryDirectory() as tmpdir:
    # ── Generate supporting documents per scenario ──
    # Scenarios cycle across packets, so documents are generated one group
    # per scenario rather than as a single batch: every W-2 and bank
    # statement is built against its own scenario's income, which is what
    # keeps INCOME_VARIANCE from firing (ISSUE-002).
    print(f"\n[1/3] Generating W-2s per scenario...")
    w2_groups = {}
    bank_groups = {}
    try:
      for s_idx, scenario in enumerate(SCENARIOS):
        n = len([i for i in range(count)
                 if i % len(SCENARIOS) == s_idx])
        if n == 0:
          continue
        annual_income = scenario["gross_monthly_income"] * 12
        print(f"  {scenario['name']}: {n} W-2(s) "
              f"at ${annual_income:,.0f}")
        w2_groups[s_idx] = generate_synthetic_w2_batch(
          count=n,
          output_dir=os.path.join(tmpdir, f"w2_{scenario['name']}"),
          seed=42 + s_idx,
          tax_year=2024,
          target_annual_income=annual_income,
        )
    except Exception as e:
      print(f"  ERROR generating W-2s: {e}")
      sys.exit(1)

    print(f"\n[2/3] Generating bank statements per scenario...")
    try:
      for s_idx, scenario in enumerate(SCENARIOS):
        if s_idx not in w2_groups:
          continue
        n = len(w2_groups[s_idx])
        annual_income = scenario["gross_monthly_income"] * 12
        bank_groups[s_idx] = generate_synthetic_bank_statement_batch(
          count=n,
          output_dir=os.path.join(tmpdir, f"bank_{scenario['name']}"),
          seed_start=100 + s_idx * 50,
          annual_incomes=[annual_income],
        )
    except Exception as e:
      print(f"  ERROR generating bank statements: {e}")
      sys.exit(1)

    total_docs = sum(len(v) for v in w2_groups.values())
    print(f"  ✓ Generated {total_docs} W-2s and "
          f"{sum(len(v) for v in bank_groups.values())} bank statements")

    # Process packets
    print(f"\n[3/3] Sending to PacketWise...")
    results = {
      "approved": 0,
      "flagged": 0,
      "rejected": 0,
      "errors": 0
    }

    for i in range(count):
      s_idx = i % len(SCENARIOS)
      k = i // len(SCENARIOS)
      scenario = SCENARIOS[s_idx]
      w2_path = w2_groups[s_idx][k]
      bank_path = bank_groups[s_idx][k]

      app_path = Path(tmpdir) / f"app_{i:03d}.txt"
      app_path.write_text(
        make_application_text(scenario, i + 1)
      )

      try:
        with open(w2_path, "rb") as w2f, \
             open(bank_path, "rb") as bankf, \
             open(app_path, "rb") as appf:
          r = requests.post(
            f"{PACKETWISE_URL}/process",
            headers={"X-API-Key": API_KEY},
            files=[
              ("files", (Path(w2_path).name,
                w2f, "application/pdf")),
              ("files", (Path(bank_path).name,
                bankf, "application/pdf")),
              ("files", (app_path.name,
                appf, "text/plain")),
            ],
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
            f"| LTV={ltv if ltv is None else f'{ltv*100:.1f}%'}"
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

if __name__ == "__main__":
  parser = argparse.ArgumentParser()
  parser.add_argument(
    "--count", type=int, default=10,
    help="Number of loan packets to process"
  )
  args = parser.parse_args()
  run(count=args.count)
