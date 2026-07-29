<div align="center">

# 🏦 PacketWise

**Automated Commercial Loan Intake with Intelligent Document Processing**

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green)](https://fastapi.tiangolo.com)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker)](https://docker.com)
[![Proprietary](https://img.shields.io/badge/License-Proprietary-lightgrey)](#license)

</div>

---

## What It Does

PacketWise automates the commercial loan underwriting pipeline:

| Stage | What Happens |
|-------|-------------|
| **Ingest** | Upload mixed document packets (W-2, Application, Bank Statement, Tax Return) |
| **Classify** | Document type detection via keyword classifier (extensible to ML models) |
| **Extract** | OCR + regex field extraction (Tesseract, PyMuPDF, OpenCV) |
| **Validate** | Cross-document consistency checks (stated vs. verified income) |
| **Decide** | Underwriting rule engine (DTI, LTV, credit score thresholds) |
| **Alert** | Auto-generated exception memos (PDF) + optional SMTP email alerts |
| **Monitor** | Real-time dashboard + performance report endpoint |

## Architecture

```
┌─────────────┐    ┌──────────────┐    ┌─────────────┐    ┌──────────────┐
│   Upload    │───▶│   Classify   │───▶│   Extract   │───▶│   Validate   │
│  (Drag/Drop)│    │  (Doc Type)  │    │  (OCR/AI)   │    │  (Rules)     │
└─────────────┘    └──────────────┘    └─────────────┘    └──────┬───────┘
                                                                  │
                       ┌──────────────────────────────────────────┘
                       ▼
              ┌─────────────┐    ┌──────────────┐    ┌──────────────┐
              │   DECISION  │◀───│   METRICS    │◀───│   ENGINE     │
              │   (API)     │    │  (DTI/LTV)   │    │  (Underwrite)│
              └──────┬──────┘    └──────────────┘    └──────────────┘
                     │
        ┌────────────┼────────────┐
        ▼            ▼            ▼
   ┌─────────┐  ┌─────────┐  ┌──────────┐
   │APPROVED │  │ FLAGGED │  │ REJECTED │
   │  to DB  │  │  Memo   │  │  Memo    │
   │         │  │  + Alert│  │  + Alert │
   └─────────┘  └─────────┘  └──────────┘
```

## Quick Start

```bash
# Clone
git clone <your-repo>
cd packetwise

# Docker (recommended)
docker-compose up --build

# Or local
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/process` | POST | Upload loan packet, get decision |
| `/api/v1/core-banking/loans` | GET | List all applications |
| `/api/v1/core-banking/exceptions` | GET | Underwriting exceptions |
| `/api/v1/metrics/dashboard` | GET | Real-time dashboard data |
| `/api/v1/report/performance` | GET | Performance benchmark report |
| `/api/v1/health` | GET | Health check |

## Test Results

| Scenario | Decision | Avg Time | Confidence |
|----------|----------|----------|------------|
| Clean file (text) | Approved | ~0.15s | 1.00 |
| High DTI | Flagged | ~1.1s | 1.00 |
| Critical violations | Rejected | ~1.4s | 1.00 |
| Image OCR (W-2) | Approved | ~2.0s | 0.95 |

Run the integration suite:

```bash
pytest tests/integration/test_pipeline.py -v
```

## Underwriting Rules

| Rule | Threshold | Severity |
|------|-----------|----------|
| DTI Qualified Mortgage | ≤ 43% | Warning |
| DTI Absolute Maximum | ≤ 50% | Critical |
| Min Credit Score | ≥ 620 | Critical |
| Max LTV | ≤ 80% | Warning |
| Income Variance | ≤ 10% | Warning |
| Missing Required Doc | W-2 / tax / bank | Critical |

## Tech Stack

- **Backend:** Python 3.11, FastAPI, SQLAlchemy
- **OCR/IDP:** Tesseract, PyMuPDF, OpenCV
- **Rules:** YAML-configurable engine
- **Database:** SQLite (dev) → PostgreSQL (prod path)
- **PDF Memos:** Jinja2 + WeasyPrint (with HTML fallback)
- **Frontend:** React 18 via CDN (no build)
- **Container:** Docker + docker-compose

## Project Structure

```
packetwise/
├── src/
│   ├── idp/           # Document classification & OCR
│   ├── engine/        # Underwriting rule engine
│   ├── core_banking/  # Mock core banking API
│   ├── exceptions/    # Exception memo generator
│   ├── pipeline/      # End-to-end orchestrator
│   └── dashboard/     # React monitoring UI
├── config/            # Settings & business rules
├── tests/             # Unit & integration tests
├── docs/              # PDD, SDD
└── data/              # Uploads, DB, memos
```

## 2-Minute Demo

```bash
# 1. Start the server
docker-compose up --build

# 2. Run the automated demo
python demo.py

# 3. Open the dashboard
open http://localhost:8000/
```

What you'll see:
- **Dashboard:** Real-time stats on loan decisions (approved/flagged/rejected)
- **Upload:** Drag-and-drop a loan packet (W-2 + Application + Bank Statement)
- **Processing:** ~0.02s for text, ~3s for scanned images
- **Decision:** Instant underwriting with DTI/LTV calculations
- **Exceptions:** Professional memo generated for flagged/rejected loans
- **API Docs:** Interactive Swagger at `/docs`

## Capabilities

- Multi-document IDP pipeline classifying W-2s, Applications, Bank Statements, Tax Returns
- OCR engine with Tesseract + OpenCV preprocessing (denoising, binarization)
- Underwriting rule engine with configurable thresholds (YAML)
- 3-state decision flow: Approved → Core Banking DB, Flagged/Rejected → Exception Memo
- React dashboard with real-time metrics and exception review
- Docker containerization for one-command deployment
- Integration test suite (4/5 pass, 1 skipped pending Windows Tesseract install)

## Performance Metrics

| Metric | Result |
|--------|--------|
| Text packet processing | ~0.02s |
| Image OCR processing | ~3s |
| Decision accuracy | 100% on test fixtures |
| Extraction confidence | 0.85–1.0 (source-aware) |

## Key Technical Decisions
1. **Python-native over UiPath:** Cross-platform, zero licensing, better for East Africa deployment
2. **SQLite for development, PostgreSQL for production:** zero-config locally, managed Postgres under load
3. **Keyword classification before ML:** no training data required, extensible to LayoutLM
4. **HTML memo fallback over PDF-only:** WeasyPrint requires GTK; HTML works everywhere

## Roadmap
- [ ] Windows Tesseract install for local OCR (works in Docker)
- [ ] LayoutLM/Donut upgrade for production-grade classification
- [ ] PostgreSQL migration for multi-user production
- [ ] Celery + Redis for async queue processing
- [ ] Synthetic W-2 dataset integration from RealityDB

## License

Copyright 2026 Mpingo Systems LLC. All rights reserved.

This software is proprietary and confidential. No license, express or implied,
is granted to any person to use, copy, modify, merge, publish, distribute,
sublicense, or sell copies of this software or any portion of it. Unauthorized
use, reproduction, or distribution is prohibited.
