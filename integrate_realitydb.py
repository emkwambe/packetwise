"""
RealityDB → PacketWise Integration
Generates synthetic W-2s via realitydb-docs
and processes them through PacketWise.

Usage:
  python integrate_realitydb.py
  python integrate_realitydb.py --count 20
"""
import argparse
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
    # Generate W-2s
    print(f"\n[1/2] Generating {count} synthetic W-2s...")
    try:
      w2_files = generate_synthetic_w2_batch(
        count=count, output_dir=tmpdir
      )
      print(f"  ✓ Generated {len(w2_files)} W-2 PDFs")
    except Exception as e:
      print(f"  ERROR generating W-2s: {e}")
      sys.exit(1)

    # Process packets
    print(f"\n[2/2] Sending to PacketWise...")
    results = {
      "approved": 0,
      "flagged": 0,
      "rejected": 0,
      "errors": 0
    }

    for i, w2_path in enumerate(w2_files):
      scenario = SCENARIOS[i % len(SCENARIOS)]
      app_path = Path(tmpdir) / f"app_{i:03d}.txt"
      app_path.write_text(
        make_application_text(scenario, i + 1)
      )

      try:
        with open(w2_path, "rb") as w2f, \
             open(app_path, "rb") as appf:
          r = requests.post(
            f"{PACKETWISE_URL}/process",
            headers={"X-API-Key": API_KEY},
            files=[
              ("files", (Path(w2_path).name,
                w2f, "application/pdf")),
              ("files", (app_path.name,
                appf, "text/plain")),
            ],
            timeout=30,
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
          print(
            f"  [{i+1:02d}] {status:10s} | "
            f"{time_s:.3f}s | conf={conf:.2f}"
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
