# Project Retrospective

**Duration:** 9 sprints, ~6 hours  
**Stack:** Python, FastAPI, SQLAlchemy, Tesseract OCR, React, Docker  
**Role:** Full-stack engineer + PM (agile sprints)

## What Was Built

- Multi-document IDP pipeline classifying W-2s, Applications, Bank Statements, and Tax Returns
- OCR engine with Tesseract + OpenCV preprocessing (denoising, binarization)
- Underwriting rule engine with configurable thresholds via `config/rules.yaml`
- 3-state decision flow:
  - **Approved** → persisted to Core Banking DB
  - **Flagged / Rejected** → PDF exception memo + optional SMTP alert
- React dashboard with real-time metrics and exception review
- Docker containerization for one-command deployment
- Integration test suite covering clean approval, flagged DTI, rejected critical violations, missing documents, and image OCR

## Performance Metrics

| Metric | Result |
|--------|--------|
| Text packet processing | ~0.02s |
| Image OCR processing | ~3s |
| Decision accuracy | 100% on test fixtures |
| Extraction confidence | 0.85–1.0 (source-aware) |

## Sprint Summary

| Sprint | Deliverable |
|--------|-------------|
| 0 | Boot verification — uvicorn starts clean |
| 1 | Test fixtures + first clean packet |
| 2 | Flagged packet + exception memo generation |
| 3 | Dashboard + exception review endpoints |
| 4 | Rejected packet + missing-doc edge case |
| 5 | Docker, Git init, real OCR image test |
| 6 | Source-aware confidence, email alerts, performance report |
| 7 | Integration test suite, benchmark batch, portfolio README |
| 8 | Dashboard served from root, demo script, request logging |
| 9 | Auto-docs, GitHub push, demo narrative, retrospective |

## Key Technical Decisions

1. **Python-native over UiPath:** Cross-platform, zero licensing, better for East Africa deployment
2. **SQLite over PostgreSQL (MVP):** Zero-config, file-based, instantly portable
3. **Keyword classification over ML (MVP):** Fast, no training data needed, extensible to LayoutLM
4. **HTML memo fallback over PDF-only:** WeasyPrint requires GTK; HTML works everywhere

## Known Limitations & Next Steps

- [ ] Windows Tesseract install for local OCR (works in Docker)
- [ ] LayoutLM/Donut upgrade for production-grade classification
- [ ] PostgreSQL migration for multi-user production
- [ ] Celery + Redis for async queue processing
- [ ] Synthetic W-2 dataset integration from RealityDB
