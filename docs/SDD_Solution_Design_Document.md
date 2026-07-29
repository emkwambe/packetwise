# Solution Design Document (SDD)
## PacketWise v1.0 — Technical Architecture

### 1. System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         PRESENTATION LAYER                          │
│  React Dashboard (src/dashboard/index.html) — Static SPA            │
│  Upload drag-and-drop | Metrics | Exception review | Loan list      │
├─────────────────────────────────────────────────────────────────────┤
│                          API LAYER                                  │
│  FastAPI (main.py) — Async REST API                                 │
│  /process | /core-banking/* | /metrics/dashboard | /health         │
├─────────────────────────────────────────────────────────────────────┤
│                        ORCHESTRATION LAYER                          │
│  LoanPipeline (src/pipeline/worker.py)                              │
│  Ingest → Classify → Extract → Evaluate → Persist → Output         │
├─────────────────────────────────────────────────────────────────────┤
│                        BUSINESS LOGIC LAYER                         │
│  IDP: OCRExtractor + Classifier (src/idp/)                         │
│  Rules: UnderwritingEngine (src/engine/rules.py)                    │
│  Memos: MemoGenerator (src/exceptions/memo_generator.py)            │
├─────────────────────────────────────────────────────────────────────┤
│                        DATA LAYER                                   │
│  SQLite (dev) → PostgreSQL (prod path)                              │
│  SQLAlchemy ORM | Alembic migrations (future)                       │
└─────────────────────────────────────────────────────────────────────┘
```

### 2. Technology Stack

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| Backend | Python 3.11 + FastAPI | Async, auto-docs, type-safe |
| OCR | Tesseract + PyMuPDF | Free, proven, handles scanned PDFs |
| Document Classification | Heuristic keyword matching | Fast, no model training needed for MVP |
| Rule Engine | Custom Python + YAML config | Flexible, auditable, no vendor lock-in |
| Database | SQLite (dev) | Zero-config, file-based, portable |
| PDF Generation | WeasyPrint + Jinja2 | HTML-to-PDF, professional output |
| Frontend | React 18 (CDN) | No build step, instant deployment |
| Container | Docker + docker-compose | One-command setup, shareable |

### 3. Data Model

**LoanApplication** — Central entity tracking each loan through the pipeline.
**DocumentRecord** — Audit trail of every document processed.
**UnderwritingException** — Individual rule violations with severity.
**ProcessingMetric** — Performance telemetry per pipeline stage.

### 4. Security Considerations

- SSNs stored in SQLite (demo only — production requires encryption at rest)
- File uploads validated by extension and size
- CORS configured for dashboard integration
- No PII in logs (sanitized)

### 5. Scalability Path

| Phase | Change |
|-------|--------|
| v1.0 (Current) | SQLite, single-process, local files |
| v1.5 | PostgreSQL, Redis queue, Celery workers |
| v2.0 | LayoutLM/Donut for classification, cloud OCR (AWS Textract) |
| v2.5 | Microservices, Kubernetes, event-driven architecture |

### 6. Testing Strategy

- **Unit**: Individual extractors, rule engine calculations
- **Integration**: Full pipeline with synthetic data packets
- **Performance**: Benchmark extraction speed and accuracy
- **Edge Cases**: Missing docs, poor scans, income mismatch

### 7. Deployment

```bash
# Development
docker-compose up --build

# Production (future)
docker build -t packetwise:latest .
docker run -p 8000:8000 -e DATABASE_URL=postgresql://... packetwise:latest
```
