<div align="center">

# 🏦 PacketWise

**Automated Commercial Loan Intake with Intelligent Document Processing**

[![Python](https://img.shields.io/badge/Python-3.11-blue)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-green)](https://fastapi.tiangolo.com)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker)](https://docker.com)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

</div>

---

An automated loan intake solution using Intelligent Document Processing (IDP), OCR, and underwriting rule engines. Built 100% open-source, containerized, and demo-ready.

## Features

- **Multi-Document IDP**: Classifies and extracts data from W-2s, Bank Statements, Tax Returns, and Loan Applications
- **OCR Engine**: Tesseract + PyMuPDF with preprocessing (denoising, binarization)
- **Underwriting Rules**: DTI, LTV, Income Verification, Credit Score thresholds
- **Exception Memos**: Auto-generated professional PDF memos for flagged/rejected files
- **Mock Core Banking**: SQLite-based ledger with FastAPI REST API
- **Dashboard**: Real-time React monitoring dashboard
- **Dockerized**: One-command deployment

## Quick Start

```bash
# Clone and enter
cd packetwise

# Option 1: Docker (recommended)
docker-compose up --build

# Option 2: Local Python
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/process` | POST | Upload loan packet, get decision |
| `/api/v1/core-banking/loans` | GET | List all loan applications |
| `/api/v1/core-banking/loans/{id}` | GET | Get specific loan |
| `/api/v1/core-banking/exceptions` | GET | List underwriting exceptions |
| `/api/v1/metrics/dashboard` | GET | Dashboard metrics |
| `/api/v1/health` | GET | Health check |

## Dashboard

Open `src/dashboard/index.html` in a browser (or serve via any static server) while the API runs on `localhost:8000`.

## Project Structure

```
packetwise/
├── src/
│   ├── idp/              # Document classification & OCR extraction
│   ├── engine/           # Underwriting rule engine
│   ├── core_banking/     # Mock core banking API & models
│   ├── exceptions/       # Exception memo generator
│   ├── pipeline/         # End-to-end processing orchestrator
│   └── dashboard/        # React monitoring dashboard
├── config/               # Settings & business rules
├── data/                 # Uploads, processed files, DB
├── docs/                 # PDD, SDD, test plans
└── tests/                # Unit & integration tests
```

## Underwriting Rules (config/rules.yaml)

| Rule | Threshold | Severity |
|------|-----------|----------|
| DTI Qualified Mortgage | ≤ 43% | Warning |
| DTI Absolute Maximum | ≤ 50% | Critical |
| Min Credit Score | ≥ 620 | Critical |
| Max LTV | ≤ 80% | Warning |
| Income Variance | ≤ 10% | Warning |

## Synthetic Data

Request synthetic W-2, Application, and Bank Statement datasets from RealityDB using the specs in `docs/Synthetic_Data_Specs.md`.

## License

MIT — Built for demonstration and educational purposes.
