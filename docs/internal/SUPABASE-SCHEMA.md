# PacketWise Supabase Schema

- **Project:** lxzpsrepixlwfnghneem
- **Last updated:** 2026-07-29
- **Source of truth:** `src/core_banking/models.py`

Tables are created by `init_db()` via `Base.metadata.create_all()`. This document
is transcribed from the SQLAlchemy models — see the divergence note at the end
before relying on it.

## Tables (4)

### loan_applications

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER | PK, indexed |
| `application_id` | VARCHAR | unique, indexed, not null |
| `borrower_name` | VARCHAR | not null |
| `borrower_ssn` | VARCHAR | not null |
| `loan_amount` | FLOAT | not null |
| `property_value` | FLOAT | not null |
| `stated_income_annual` | FLOAT | |
| `verified_income_annual` | FLOAT | |
| `dti_ratio` | FLOAT | |
| `ltv_ratio` | FLOAT | |
| `credit_score` | INTEGER | |
| `status` | ENUM `loanstatus` | pending / processing / approved / flagged / rejected / manual_review |
| `decision_reason` | TEXT | |
| `created_at` | TIMESTAMP | default `utcnow` |
| `updated_at` | TIMESTAMP | default `utcnow`, on update |
| `processed_at` | TIMESTAMP | |
| `extraction_confidence_avg` | FLOAT | |
| `processing_time_seconds` | FLOAT | |

### document_records

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER | PK, indexed |
| `application_id` | VARCHAR | indexed, not null |
| `document_type` | ENUM `documenttype` | application / w2 / tax_return / bank_statement / pay_stub / other |
| `filename` | VARCHAR | not null |
| `extracted_data` | TEXT | Python dict serialised with `str()`, not JSON |
| `confidence_score` | FLOAT | |
| `extraction_errors` | TEXT | semicolon-joined |
| `created_at` | TIMESTAMP | default `utcnow` |

### underwriting_exceptions

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER | PK, indexed |
| `application_id` | VARCHAR | indexed, not null |
| `severity` | VARCHAR | critical / warning / info |
| `rule_code` | VARCHAR | not null |
| `rule_description` | TEXT | not null |
| `expected_value` | TEXT | |
| `actual_value` | TEXT | |
| `memo_path` | VARCHAR | |
| `resolved` | BOOLEAN | default false |
| `created_at` | TIMESTAMP | default `utcnow` |

### processing_metrics

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER | PK, indexed |
| `application_id` | VARCHAR | indexed |
| `stage` | VARCHAR | not null |
| `duration_ms` | INTEGER | milliseconds |
| `success` | BOOLEAN | |
| `error_message` | TEXT | |
| `created_at` | TIMESTAMP | default `utcnow` |

## Referential integrity

`application_id` is an **indexed string column on every table, not a declared
foreign key.** No `ForeignKey` constraint exists in the models, so PostgreSQL
enforces nothing: orphaned `document_records` and `underwriting_exceptions` rows
are possible if a `loan_applications` row is deleted. Adding real FK constraints
is a schema migration, not a model annotation, and has not been done.

`processing_metrics` is defined but never written to by the pipeline.

## Divergence from the Sprint 12 specification

The schema originally specified for this document does not match the deployed
tables. The differences below are recorded so the spec is not mistaken for the
database:

| Specified | Actual |
|-----------|--------|
| `id` is UUID | `id` is INTEGER autoincrement, on all four tables |
| `loan_applications.income_variance` | not present — computed at decision time, never persisted |
| `loan_applications.monthly_income` | not present |
| `loan_applications.monthly_debt` | not present |
| `loan_applications.memo_path` | not present — `memo_path` lives on `underwriting_exceptions` |
| `document_records.extraction_confidence` | named `confidence_score` |
| `document_records.extracted_fields` (JSON) | named `extracted_data`, TEXT holding a `str()`-ified dict |
| `underwriting_exceptions.description` | named `rule_description` |
| `processing_metrics.duration_seconds` | named `duration_ms` (integer milliseconds) |
| `application_id` as FK | plain indexed column, no constraint |

Columns present in the database but absent from the spec: `borrower_ssn`,
`decision_reason`, `updated_at`, `processed_at`,
`document_records.extraction_errors`, `processing_metrics.success`,
`processing_metrics.error_message`.

If the specified shape is the intended target, it is a migration to plan — not a
description of what is running now.
