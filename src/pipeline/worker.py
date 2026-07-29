"""End-to-end loan processing pipeline.
Orchestrates document ingestion -> IDP -> Rules -> Decision -> Output."""
import time
import uuid
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from src.idp.extractor import OCRExtractor
from src.idp.schemas import DocType
from src.engine.rules import UnderwritingEngine
from src.exceptions.memo_generator import MemoGenerator
from src.core_banking.models import (
    get_db, LoanApplication, DocumentRecord, UnderwritingException,
    LoanStatus, init_db
)
from config.settings import settings

@dataclass
class PipelineResult:
    application_id: str
    status: str
    metrics: Dict[str, Any]
    violations: List[Dict[str, Any]]
    memo_path: Optional[str]
    processing_time: float
    confidence: float

class LoanPipeline:
    """Main processing pipeline."""

    def __init__(self):
        self.extractor = OCRExtractor(tesseract_cmd=settings.TESSERACT_CMD)
        self.engine = UnderwritingEngine()
        self.memo_gen = MemoGenerator(output_dir=str(settings.EXCEPTIONS_DIR))
        init_db()

    def process_packet(self, file_paths: List[str], 
                       application_id: Optional[str] = None) -> PipelineResult:
        """
        Process a loan packet (multiple documents).

        Args:
            file_paths: List of document file paths
            application_id: Optional pre-defined ID (generated if None)

        Returns:
            PipelineResult with decision, metrics, and outputs
        """
        start_time = time.time()
        application_id = application_id or f"LOAN-{uuid.uuid4().hex[:8].upper()}"

        db = next(get_db())

        try:
            # ─── Step 1: Document Ingestion & OCR ───
            extracted_docs = []
            confidences = []

            for fp in file_paths:
                result = self.extractor.extract_fields(fp)
                confidences.append(result.confidence)

                doc_record = DocumentRecord(
                    application_id=application_id,
                    document_type=result.document_type.value,
                    filename=Path(fp).name,
                    extracted_data=str(result.extracted_fields),
                    confidence_score=result.confidence,
                    extraction_errors="; ".join(result.extraction_errors)
                )
                db.add(doc_record)

                extracted_docs.append({
                    "type": result.document_type.value,
                    "confidence": result.confidence,
                    "fields": result.extracted_fields,
                    "errors": result.extraction_errors,
                    "filename": Path(fp).name
                })

            avg_confidence = sum(confidences) / len(confidences) if confidences else 0

            # ─── Step 2: Underwriting Evaluation ───
            evaluation = self.engine.evaluate({}, extracted_docs)
            decision = evaluation["decision"]
            metrics = evaluation["metrics"]
            violations = evaluation["violations"]

            # ─── Step 3: Map to Loan Status ───
            status_map = {
                "approved": LoanStatus.APPROVED,
                "flagged": LoanStatus.FLAGGED,
                "rejected": LoanStatus.REJECTED
            }
            loan_status = status_map.get(decision, LoanStatus.MANUAL_REVIEW)

            # ─── Step 4: Persist to Core Banking ───
            app_data = next((d for d in extracted_docs if d["type"] == "application"), {})
            fields = app_data.get("fields", {})

            loan = LoanApplication(
                application_id=application_id,
                borrower_name=fields.get("borrower_name", "Unknown"),
                borrower_ssn=fields.get("ssn", ""),
                loan_amount=fields.get("loan_amount", 0) or 0,
                property_value=fields.get("property_value", 0) or 0,
                stated_income_annual=fields.get("stated_income_annual"),
                verified_income_annual=metrics.get("verified_income_annual"),
                dti_ratio=metrics.get("dti_ratio"),
                ltv_ratio=metrics.get("ltv_ratio"),
                credit_score=fields.get("credit_score"),
                status=loan_status,
                decision_reason="; ".join([v["description"] for v in violations]) if violations else "Clean file",
                extraction_confidence_avg=avg_confidence
            )
            db.add(loan)

            # Persist violations
            for v in violations:
                exc = UnderwritingException(
                    application_id=application_id,
                    severity=v["severity"],
                    rule_code=v["rule_code"],
                    rule_description=v["description"],
                    expected_value=v.get("expected_value"),
                    actual_value=v.get("actual_value")
                )
                db.add(exc)

            db.commit()

            # ─── Step 5: Generate Exception Memo (if needed) ───
            memo_path = None
            if decision in ("flagged", "rejected"):
                memo_path = self.memo_gen.generate(
                    application_id=application_id,
                    borrower_name=fields.get("borrower_name", "Unknown"),
                    decision=decision,
                    metrics=metrics,
                    violations=violations,
                    documents=extracted_docs,
                    processing_time=time.time() - start_time,
                    confidence=avg_confidence
                )

                # Update memo path on exceptions
                for exc in db.query(UnderwritingException).filter(
                    UnderwritingException.application_id == application_id
                ).all():
                    exc.memo_path = memo_path
                db.commit()

                # Email alert for exceptions
                if settings.SMTP_HOST:
                    self._send_alert_email(
                        application_id,
                        fields.get("borrower_name", "Unknown"),
                        decision,
                        violations
                    )

            processing_time = time.time() - start_time
            loan.processing_time_seconds = processing_time
            loan.processed_at = datetime.utcnow()
            db.commit()

            return PipelineResult(
                application_id=application_id,
                status=decision,
                metrics=metrics,
                violations=violations,
                memo_path=memo_path,
                processing_time=processing_time,
                confidence=avg_confidence
            )

        except Exception as e:
            db.rollback()
            raise
        finally:
            db.close()

    def _send_alert_email(self, app_id: str, borrower: str, decision: str, violations: List[Dict[str, Any]]):
        """Send SMTP alert to underwriting team for flagged/rejected loans."""
        import smtplib
        from email.mime.text import MIMEText

        subject = f"[PacketWise] {decision.upper()} — Loan {app_id} requires review"
        body = f"""Borrower: {borrower}
Application ID: {app_id}
Decision: {decision.upper()}

Violations:
"""
        for v in violations:
            body += f"\n- [{v['severity'].upper()}] {v['rule_code']}: {v['description']}"

        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = settings.SMTP_USER
        msg['To'] = settings.UNDERWRITING_EMAIL

        try:
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
                server.starttls()
                server.login(settings.SMTP_USER, settings.SMTP_PASS)
                server.send_message(msg)
            print(f"Email alert sent for {app_id}")
        except Exception as e:
            print(f"Email alert failed: {e}")

from datetime import datetime
