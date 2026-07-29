"""FastAPI routes for mock Core Banking System."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

from src.core_banking.models import (
    get_db, LoanApplication, DocumentRecord, 
    UnderwritingException, ProcessingMetric,
    LoanStatus, DocumentType
)

router = APIRouter(prefix="/core-banking", tags=["Core Banking"])

# ─── Schemas ─────────────────────────────────────────────
class LoanCreate(BaseModel):
    application_id: str
    borrower_name: str
    borrower_ssn: str
    loan_amount: float
    property_value: float
    stated_income_annual: Optional[float] = None
    credit_score: Optional[int] = None

class LoanResponse(BaseModel):
    id: int
    application_id: str
    borrower_name: str
    loan_amount: float
    property_value: float
    dti_ratio: Optional[float]
    ltv_ratio: Optional[float]
    status: str
    decision_reason: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True

class ExceptionResponse(BaseModel):
    id: int
    application_id: str
    severity: str
    rule_code: str
    rule_description: str
    expected_value: Optional[str]
    actual_value: Optional[str]
    resolved: bool
    created_at: datetime

    class Config:
        from_attributes = True

# ─── Routes ──────────────────────────────────────────────
@router.post("/loans", response_model=LoanResponse)
def create_loan(loan: LoanCreate, db: Session = Depends(get_db)):
    existing = db.query(LoanApplication).filter(
        LoanApplication.application_id == loan.application_id
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Application ID already exists")

    db_loan = LoanApplication(**loan.dict(), status=LoanStatus.PENDING)
    db.add(db_loan)
    db.commit()
    db.refresh(db_loan)
    return db_loan

@router.get("/loans", response_model=List[LoanResponse])
def list_loans(status: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(LoanApplication)
    if status:
        query = query.filter(LoanApplication.status == status)
    return query.order_by(LoanApplication.created_at.desc()).all()

@router.get("/loans/{application_id}", response_model=LoanResponse)
def get_loan(application_id: str, db: Session = Depends(get_db)):
    loan = db.query(LoanApplication).filter(
        LoanApplication.application_id == application_id
    ).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    return loan

@router.get("/loans/{application_id}/exceptions", response_model=List[ExceptionResponse])
def get_exceptions(application_id: str, db: Session = Depends(get_db)):
    return db.query(UnderwritingException).filter(
        UnderwritingException.application_id == application_id
    ).order_by(UnderwritingException.created_at.desc()).all()

@router.get("/exceptions", response_model=List[ExceptionResponse])
def list_all_exceptions(
    severity: Optional[str] = None, 
    resolved: Optional[bool] = None,
    db: Session = Depends(get_db)
):
    query = db.query(UnderwritingException)
    if severity:
        query = query.filter(UnderwritingException.severity == severity)
    if resolved is not None:
        query = query.filter(UnderwritingException.resolved == resolved)
    return query.order_by(UnderwritingException.created_at.desc()).all()

@router.post("/exceptions/{exception_id}/resolve")
def resolve_exception(exception_id: int, db: Session = Depends(get_db)):
    exc = db.query(UnderwritingException).filter(UnderwritingException.id == exception_id).first()
    if not exc:
        raise HTTPException(status_code=404, detail="Exception not found")
    exc.resolved = True
    db.commit()
    return {"message": "Exception resolved", "exception_id": exception_id}

@router.get("/metrics/summary")
def get_metrics_summary(db: Session = Depends(get_db)):
    total = db.query(LoanApplication).count()
    approved = db.query(LoanApplication).filter(LoanApplication.status == LoanStatus.APPROVED).count()
    flagged = db.query(LoanApplication).filter(LoanApplication.status == LoanStatus.FLAGGED).count()
    rejected = db.query(LoanApplication).filter(LoanApplication.status == LoanStatus.REJECTED).count()
    pending = db.query(LoanApplication).filter(LoanApplication.status == LoanStatus.PENDING).count()

    avg_confidence = db.query(LoanApplication).filter(
        LoanApplication.extraction_confidence_avg.isnot(None)
    )
    avg_conf = sum([l.extraction_confidence_avg or 0 for l in avg_confidence.all()]) / max(avg_confidence.count(), 1)

    avg_proc_time = db.query(LoanApplication).filter(
        LoanApplication.processing_time_seconds.isnot(None)
    )
    avg_time = sum([l.processing_time_seconds or 0 for l in avg_proc_time.all()]) / max(avg_proc_time.count(), 1)

    return {
        "total_applications": total,
        "approved": approved,
        "flagged": flagged,
        "rejected": rejected,
        "pending": pending,
        "approval_rate": round(approved / max(total, 1), 3),
        "avg_extraction_confidence": round(avg_conf, 3),
        "avg_processing_time_sec": round(avg_time, 2)
    }
