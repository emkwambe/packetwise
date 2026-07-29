# Process Design Document (PDD)
## PacketWise — Commercial Loan Intake Automation

### 1. Process Overview

**Process Name**: Commercial Loan Application Intake & Underwriting  
**Objective**: Automate the ingestion, classification, extraction, and initial underwriting evaluation of loan application packets to reduce manual processing time and improve consistency.  
**Frequency**: On-demand (per loan packet upload)  
**Trigger**: Document upload via API or file system watcher  

### 2. Process Map (Visual Flow)

```
┌─────────────┐    ┌──────────────┐    ┌─────────────┐    ┌──────────────┐
│   START     │───▶│   INGEST     │───▶│   CLASSIFY  │───▶│   EXTRACT   │
│  (Upload)   │    │  (Save files)│    │  (Doc type) │    │  (Fields)   │
└─────────────┘    └──────────────┘    └─────────────┘    └──────────────┘
                                                                  │
                    ┌─────────────────────────────────────────────┘
                    ▼
           ┌─────────────┐    ┌──────────────┐    ┌──────────────┐
           │   DECISION  │◀───│    RULES     │◀───│  CALCULATE   │
           │   ENGINE    │    │  (Validate)  │    │   METRICS    │
           └──────┬──────┘    └──────────────┘    └──────────────┘
                  │
      ┌───────────┼───────────┐
      ▼           ▼           ▼
┌─────────┐ ┌─────────┐ ┌──────────┐
│APPROVED │ │ FLAGGED │ │ REJECTED │
│  Write  │ │  Memo   │ │  Memo    │
│  to DB  │ │  + Alert│ │  + Alert │
└─────────┘ └─────────┘ └──────────┘
```

### 3. Actor Roles

| Role | Responsibility |
|------|---------------|
| Borrower | Submits loan application packet |
| PacketWise Bot | Ingests, classifies, extracts, evaluates |
| Underwriter | Reviews flagged applications and exception memos |
| System Admin | Monitors pipeline health and metrics |

### 4. Input/Output Specifications

**Inputs**:
- Loan Application Form (PDF/image)
- W-2 Form (PDF/image)
- Bank Statements (PDF/image)
- Tax Return 1040 (PDF/image) — optional

**Outputs**:
- Structured JSON with extracted fields
- Underwriting decision (Approved/Flagged/Rejected)
- Exception Memo (PDF) for non-approved cases
- Core Banking DB update
- Dashboard metrics

### 5. Business Rules

See `config/rules.yaml` for full configuration.

**Critical Rules** (auto-reject):
- DTI > 50%
- Missing required document (Application + W-2)
- Credit Score < 620

**Warning Rules** (flag for review):
- DTI > 43% (QM threshold)
- LTV > 80%
- Income variance > 10%

### 6. Exception Handling

| Exception | Handling |
|-----------|----------|
| OCR failure / low confidence | Flag for manual review, log confidence score |
| Missing required doc | Critical violation, auto-reject |
| Income mismatch | Warning, generate discrepancy memo |
| System error | Retry once, then route to manual queue |

### 7. Performance Targets

| Metric | Target |
|--------|--------|
| End-to-end processing | < 30 seconds per packet |
| Document classification accuracy | > 90% |
| Field extraction confidence | > 85% |
| False positive rate (flagged) | < 15% |
