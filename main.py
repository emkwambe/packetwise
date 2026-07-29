"""PacketWise - Commercial Loan Application & Income Verification System.
FastAPI main application entry point."""
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List, Optional
import shutil
from pathlib import Path
import uuid

from src.core_banking.models import init_db, get_db
from src.core_banking.api import router as core_router
from src.pipeline.worker import LoanPipeline, PipelineResult
from config.settings import settings

app = FastAPI(
    title=settings.APP_NAME,
    description="Automated Commercial Loan Intake with IDP, OCR, and Underwriting Rules",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize DB on startup
@app.on_event("startup")
def startup():
    init_db()

# Include routers
app.include_router(core_router, prefix=settings.API_V1_PREFIX)

# ─── Upload & Process ────────────────────────────────────
@app.post("/api/v1/process", tags=["Pipeline"])
async def process_loan_packet(
    files: List[UploadFile] = File(...),
    application_id: Optional[str] = None
):
    """
    Upload a loan packet (multiple documents) for processing.
    Returns decision, metrics, and exception memo if flagged.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")

    # Validate files
    for f in files:
        ext = Path(f.filename).suffix.lower()
        if ext not in settings.ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")

    # Save uploads
    upload_paths = []
    for f in files:
        file_id = f"{uuid.uuid4().hex}{Path(f.filename).suffix}"
        save_path = settings.UPLOAD_DIR / file_id
        with open(save_path, "wb") as buffer:
            shutil.copyfileobj(f.file, buffer)
        upload_paths.append(str(save_path))

    # Process
    pipeline = LoanPipeline()
    result = pipeline.process_packet(upload_paths, application_id)

    return {
        "application_id": result.application_id,
        "status": result.status,
        "metrics": result.metrics,
        "violations": result.violations,
        "memo_path": result.memo_path,
        "processing_time_seconds": round(result.processing_time, 2),
        "extraction_confidence": round(result.confidence, 3),
        "documents_processed": len(files)
    }

@app.get("/api/v1/health", tags=["System"])
def health_check():
    return {"status": "healthy", "version": "1.0.0", "service": settings.APP_NAME}

@app.get("/api/v1/metrics/dashboard", tags=["Dashboard"])
def dashboard_metrics(db: Session = Depends(get_db)):
    """Aggregated metrics for the monitoring dashboard."""
    from src.core_banking.models import LoanApplication, LoanStatus, UnderwritingException

    total = db.query(LoanApplication).count()
    approved = db.query(LoanApplication).filter(LoanApplication.status == LoanStatus.APPROVED).count()
    flagged = db.query(LoanApplication).filter(LoanApplication.status == LoanStatus.FLAGGED).count()
    rejected = db.query(LoanApplication).filter(LoanApplication.status == LoanStatus.REJECTED).count()
    pending = db.query(LoanApplication).filter(LoanApplication.status == LoanStatus.PENDING).count()
    manual = db.query(LoanApplication).filter(LoanApplication.status == LoanStatus.MANUAL_REVIEW).count()

    open_exceptions = db.query(UnderwritingException).filter(UnderwritingException.resolved == False).count()

    # Recent applications
    recent = db.query(LoanApplication).order_by(LoanApplication.created_at.desc()).limit(10).all()

    return {
        "counts": {
            "total": total,
            "approved": approved,
            "flagged": flagged,
            "rejected": rejected,
            "pending": pending,
            "manual_review": manual
        },
        "rates": {
            "approval_rate": round(approved / max(total, 1), 3),
            "flag_rate": round(flagged / max(total, 1), 3),
            "rejection_rate": round(rejected / max(total, 1), 3)
        },
        "exceptions": {
            "open": open_exceptions
        },
        "recent_applications": [
            {
                "id": r.application_id,
                "borrower": r.borrower_name,
                "status": r.status.value,
                "loan_amount": r.loan_amount,
                "dti": r.dti_ratio,
                "created_at": r.created_at.isoformat() if r.created_at else None
            }
            for r in recent
        ]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
