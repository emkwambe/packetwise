<div align="center">

# 🏦 PacketWise

**Automated Commercial Loan Intake with Intelligent Document Processing**

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green)](https://fastapi.tiangolo.com)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker)](https://docker.com)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

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

## License

MIT — Built for demonstration and educational purposes.
