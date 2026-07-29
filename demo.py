"""PacketWise Demo Script — Run this to see the full pipeline in action."""
import httpx
import json
from pathlib import Path

BASE = "http://localhost:8000/api/v1"
TIMEOUT = 60.0


def demo():
    print("=" * 60)
    print("PACKETWISE DEMO")
    print("=" * 60)

    # Health check
    r = httpx.get(f"{BASE}/health", timeout=TIMEOUT)
    print(f"\n1. Health: {r.json()}")

    # Scenario 1: Clean approval
    print("\n2. CLEAN APPROVAL PACKET")
    r = httpx.post(
        f"{BASE}/process",
        timeout=TIMEOUT,
        files=[
            ("files", ("sample_w2.txt", open("tests/fixtures/sample_w2.txt", "rb"), "text/plain")),
            ("files", ("sample_app.txt", open("tests/fixtures/sample_app.txt", "rb"), "text/plain")),
            ("files", ("sample_bank.txt", open("tests/fixtures/sample_bank.txt", "rb"), "text/plain")),
        ]
    )
    print(json.dumps(r.json(), indent=2))

    # Scenario 2: Flagged
    print("\n3. FLAGGED PACKET (High DTI)")
    r = httpx.post(
        f"{BASE}/process",
        timeout=TIMEOUT,
        files=[
            ("files", ("sample_w2.txt", open("tests/fixtures/sample_w2.txt", "rb"), "text/plain")),
            ("files", ("sample_app_flagged.txt", open("tests/fixtures/sample_app_flagged.txt", "rb"), "text/plain")),
            ("files", ("sample_bank_flagged.txt", open("tests/fixtures/sample_bank_flagged.txt", "rb"), "text/plain")),
        ]
    )
    print(json.dumps(r.json(), indent=2))

    # Scenario 3: Rejected
    print("\n4. REJECTED PACKET (Critical violations)")
    r = httpx.post(
        f"{BASE}/process",
        timeout=TIMEOUT,
        files=[
            ("files", ("sample_w2.txt", open("tests/fixtures/sample_w2.txt", "rb"), "text/plain")),
            ("files", ("sample_app_rejected.txt", open("tests/fixtures/sample_app_rejected.txt", "rb"), "text/plain")),
            ("files", ("sample_bank_rejected.txt", open("tests/fixtures/sample_bank_rejected.txt", "rb"), "text/plain")),
        ]
    )
    print(json.dumps(r.json(), indent=2))

    # Metrics
    print("\n5. PERFORMANCE REPORT")
    r = httpx.get(f"{BASE}/report/performance", timeout=TIMEOUT)
    print(json.dumps(r.json(), indent=2))

    print("\n" + "=" * 60)
    print("DEMO COMPLETE")
    print("Dashboard: http://localhost:8000/")
    print("=" * 60)


if __name__ == "__main__":
    demo()
