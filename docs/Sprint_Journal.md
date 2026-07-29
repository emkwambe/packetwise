# PacketWise Sprint Journal

This document records the work completed across Sprints 0–11. It is a narrative record of what was built, verified, and committed at each stage. No active code changes are described beyond what was already merged.

---

## Sprint 0: Boot Verification

**Goal:** Confirm the FastAPI application starts cleanly on `localhost:8000`.

**What was done:**
- Started uvicorn locally and via Docker.
- Verified `GET /api/v1/health` returned `{"status":"healthy","version":"1.0.0","service":"PacketWise"}`.
- Fixed several startup blockers discovered during boot (lazy WeasyPrint import, `.txt` file support, housing payment parser).

**Result:** Application booted with no red errors.

---

## Sprint 1: Test Fixtures & First Pipeline Test

**Goal:** Create a clean loan packet and verify end-to-end approval.

**What was done:**
- Created `tests/fixtures/sample_w2.txt`, `tests/fixtures/sample_app.txt`, and `tests/fixtures/sample_bank.txt`.
- Sent the 3-document packet to `POST /api/v1/process`.

**Result:** JSON response showed `status: "approved"`, DTI ≈ 0.35, no violations, `memo_path: null`.

---

## Sprint 2: Flagged Packet + Exception Memo

**Goal:** Trigger a `flagged` decision with DTI > 43% and verify PDF memo generation.

**What was done:**
- Created `tests/fixtures/sample_app_flagged.txt` and `tests/fixtures/sample_bank_flagged.txt`.
- Tuned debts and income so DTI landed in the flagged zone (~47%).
- Sent the flagged packet to `/process`.
- Verified `data/exceptions/` contained a PDF memo.

**Result:** `status: "flagged"`, DTI ≈ 0.475, `DTI_EXCEEDS_QM` violation, memo generated successfully.

---

## Sprint 3: Dashboard + Exception Review

**Goal:** Verify the React dashboard and core-banking exception endpoints.

**What was done:**
- Opened `src/dashboard/index.html` in the browser.
- Called `/api/v1/core-banking/exceptions` and `/api/v1/metrics/dashboard`.

**Result:** Dashboard rendered live metrics; exceptions endpoint returned the flagged loan and memo path.

---

## Sprint 4: Rejected Packet + Edge Cases

**Goal:** Trigger `rejected` with critical violations and test missing-document rejection.

**What was done:**
- Created `tests/fixtures/sample_app_rejected.txt` and `tests/fixtures/sample_bank_rejected.txt` with DTI > 50% and credit score < 620.
- Sent the rejected packet to `/process`.
- Sent an application-only packet (no W-2) to test missing-doc rejection.
- Verified dashboard metrics showed approved=1, flagged=1, rejected=2.

**Result:** Rejected packet returned `DTI_EXCEEDS_MAX`, `CREDIT_SCORE_LOW`, `LTV_EXCEEDS_MAX`, and memo generated. Missing-doc packet returned `MISSING_REQUIRED_DOC`.

---

## Sprint 5: Docker + Git + Real OCR Test

**Goal:** Fix Docker, initialize Git, and verify real OCR on a PNG W-2.

**What was done:**
- Rewrote `Dockerfile` to use `libgl1` instead of `libgl1-mesa-glx` and removed `--reload` from `CMD`.
- Created `.dockerignore`.
- Created `tests/fixtures/sample_w2_image.png` and `tests/fixtures/sample_app_image.txt`.
- Built and ran the container; health check passed.
- Initialized Git repo and made first commit.
- Ran the image packet through the Docker API.

**Result:**
- Docker: healthy.
- Git commit: `84d27d2`.
- OCR JSON: `status: "approved"`, `verified_income_annual: 85000.0`, confidence 0.95 (image penalty averaged across 3 docs).

---

## Sprint 6: Real Confidence Scoring + Email Alerts + Performance Report

**Goal:** Replace flat confidence, add SMTP alerts for exceptions, and add a performance report endpoint.

**What was done:**
- Modified `src/idp/extractor.py` to apply source-aware confidence penalties:
  - Images: ×0.85
  - Empty scanned PDFs: ×0.80
  - Extraction exceptions: ×0.6
  - Missing W-2 Box 1 wages: ×0.7
- Added `_send_alert_email()` in `src/pipeline/worker.py` for flagged/rejected loans, gated by `SMTP_HOST`.
- Added `GET /api/v1/report/performance` in `main.py` with decision distribution, timing stats, confidence stats, and top 5 violations.
- Verified image packet confidence dropped from 1.0 to 0.95.
- Verified email alert function logged a failure with a dummy SMTP host.
- Verified performance report returned full stats.

**Result:** Confidence scoring, alerts, and reporting all working.

---

## Sprint 7: Test Suite + Benchmarking + Final Docs

**Goal:** Build an integration test suite, run a benchmark batch, and polish README.

**What was done:**
- Created `tests/integration/test_pipeline.py` with 5 test classes.
- Adjusted `tests/fixtures/sample_app_flagged.txt` so the flagged scenario reliably triggers `DTI_EXCEEDS_QM`.
- Added fixture cleanup to avoid unique-constraint failures on reruns.
- Skipped the OCR test when Tesseract is not installed on the Windows host.
- Ran the suite: 4 passed, 1 skipped.
- Ran a 10-packet benchmark through the Docker API.
- Rewrote `README.md` with architecture diagram, API reference, test results, rules table, tech stack, and project structure.

**Result:**
- Pytest: `4 passed, 1 skipped`.
- Benchmark throughput: ~70 packets/minute.
- Portfolio README committed.

---

## Sprint 8: Serve Dashboard + Demo Script + Final Polish

**Goal:** Serve dashboard from root URL, add request logging, create demo script, and add package `__init__.py` files.

**What was done:**
- Replaced the root JSON endpoint in `main.py` with `HTMLResponse` serving `src/dashboard/index.html`.
- Added HTTP request logging middleware.
- Created `demo.py` using `httpx` (already in dependencies) to run 3 scenarios and print the performance report.
- Added `__init__.py` to `src/`, `src/idp/`, `src/engine/`, `src/core_banking/`, `src/exceptions/`, `src/pipeline/`.
- Updated `.env.example` with all config options.
- Verified `http://localhost:8000/` serves the dashboard and `python demo.py` runs all scenarios.

**Result:** Single-URL dashboard experience working; demo script runs cleanly.

---

## Sprint 9: Portfolio Polish — GitHub + Auto-Docs + Demo Narrative

**Goal:** Make PacketWise a public portfolio asset.

**What was done:**
- Verified `/docs` (Swagger UI) and `/redoc` (ReDoc) auto-docs are live and list all endpoints.
- Added a `## 2-Minute Demo` section and `## Project Retrospective` section to `README.md`.
- Created `RETROSPECTIVE.md` with sprint summary, metrics, key decisions, and next steps.
- Pushed the repository to `https://github.com/emkwambe/packetwise.git` on the `main` branch.

**Result:** Public GitHub repo live with full documentation.

---

## Sprint 10: Full Dataset Generation + Stress Test

**Goal:** Generate 50 synthetic W-2s and 20 bank statements, then stress test PDF processing throughput.

**What was done:**
- Used `realitydb-docs` package to generate 50 synthetic W-2 PDFs (clean + noisy mix) and 20 synthetic bank statement PDFs.
- Worked around `generate_synthetic_bank_statement()` hardcoded filename by generating into temp folders and renaming.
- Copied all 70 PDFs to `data/synthetic/w2/` and `data/synthetic/bank/`.
- Ran `stress_test.py` against the Docker API, sending each W-2 with a random bank statement.
- Verified the performance report.
- Removed `stress_test.py` and committed the synthetic dataset.

**Result:**
- 50/50 PDFs processed successfully.
- Average processing time: 0.844s.
- Max: 6.287s, Min: 0.429s.
- 0 errors/exceptions.
- All decisions were `rejected` because no application file was included (`MISSING_REQUIRED_DOC`).

---

## Sprint 11: Realistic Complete-Packet Stress Test

**Goal:** Generate complete loan packets (W-2 + Application + Bank Statement) and test all 3 decision states at scale.

**What was done:**
- Created `tests/fixtures/app_clean.txt`, `tests/fixtures/app_flagged.txt`, and `tests/fixtures/app_rejected.txt`.
- Tuned `app_flagged.txt` income to `$6,500/month` so DTI lands in the 43–50% flagged range with `sample_bank_flagged.txt`.
- Built `stress_test_complete.py` that:
  - Pre-matched synthetic W-2s to each application's stated annual income.
  - Used known bank-statement fixtures for deterministic recurring-debt extraction.
  - Fired 30 complete packets (10 per scenario) against the Docker API.
- Reset the SQLite database before the run for clean stats.
- Verified dashboard and performance report.
- Removed the temporary stress test script and committed the application fixtures.

**Result:**
- Decision accuracy: 100% (0 mismatches).
- Throughput: 145 packets/minute.
- Average processing time: 0.414s.
- Dashboard: approved=10, flagged=10, rejected=10.

---

## Cumulative Project State

- **Language / Framework:** Python 3.11, FastAPI, SQLAlchemy
- **OCR / IDP:** Tesseract, PyMuPDF, OpenCV
- **Frontend:** React 18 via CDN
- **Container:** Docker + docker-compose
- **Tests:** `tests/integration/test_pipeline.py` (4 passed, 1 OCR test skipped on Windows host)
- **Repo:** https://github.com/emkwambe/packetwise.git
- **Verified throughput:** 145 complete packets/minute
- **Verified decisions:** approved / flagged / rejected flows all working with PDF memos and dashboard reporting.
