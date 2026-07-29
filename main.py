"""PacketWise - Commercial Loan Application & Income Verification System.
FastAPI main application entry point."""
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
import shutil
from pathlib import Path
import uuid
import time

from src.core_banking.models import init_db, get_db, LoanApplication, LoanStatus, UnderwritingException
from src.core_banking.api import router as core_router
from src.pipeline.worker import LoanPipeline, PipelineResult
from config.settings import settings
from datetime import datetime

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

@app.middleware("http")
async def api_key_middleware(request: Request, call_next):
    # Skip auth for health and root
    skip_paths = [
        "/api/v1/health",
        "/",
        "/docs",
        "/openapi.json",
        "/redoc"
    ]
    if request.url.path in skip_paths:
        return await call_next(request)

    key = request.headers.get("X-API-Key")
    if not key or key != settings.API_KEY:
        return JSONResponse(
            status_code=401,
            content={"detail": "Invalid or missing API key"}
        )
    return await call_next(request)

# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    print(f"[{request.method}] {request.url.path} | {response.status_code} | {duration:.3f}s")
    return response

# Initialize DB on startup
@app.on_event("startup")
def startup():
    init_db()

@app.get("/", response_class=HTMLResponse)
def serve_dashboard():
    """Serve the React dashboard at the root URL."""
    dashboard_path = Path(__file__).parent / "src" / "dashboard" / "index.html"
    return dashboard_path.read_text(encoding="utf-8")

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

@app.get("/api/v1/report/performance", tags=["Reports"])
def performance_report(db: Session = Depends(get_db)):
    """Aggregated performance and quality report for processed loans."""
    total = db.query(LoanApplication).count()
    if total == 0:
        return {"message": "No data available"}

    # Decision distribution
    approved = db.query(LoanApplication).filter(LoanApplication.status == LoanStatus.APPROVED).count()
    flagged = db.query(LoanApplication).filter(LoanApplication.status == LoanStatus.FLAGGED).count()
    rejected = db.query(LoanApplication).filter(LoanApplication.status == LoanStatus.REJECTED).count()

    # Timing stats
    times = [l.processing_time_seconds for l in db.query(LoanApplication).all() if l.processing_time_seconds]
    avg_time = sum(times) / len(times) if times else 0
    max_time = max(times) if times else 0
    min_time = min(times) if times else 0

    # Confidence stats
    confs = [l.extraction_confidence_avg for l in db.query(LoanApplication).all() if l.extraction_confidence_avg]
    avg_conf = sum(confs) / len(confs) if confs else 0

    # Top 5 most frequent violations
    top_violations = (
        db.query(
            UnderwritingException.rule_code,
            func.count(UnderwritingException.id).label("count")
        )
        .group_by(UnderwritingException.rule_code)
        .order_by(func.count(UnderwritingException.id).desc())
        .limit(5)
        .all()
    )

    return {
        "generated_at": datetime.utcnow().isoformat(),
        "total_applications": total,
        "decisions": {
            "approved": approved,
            "flagged": flagged,
            "rejected": rejected,
            "approval_rate": round(approved / total, 3)
        },
        "performance": {
            "avg_processing_time_sec": round(avg_time, 3),
            "max_processing_time_sec": round(max_time, 3),
            "min_processing_time_sec": round(min_time, 3),
            "avg_extraction_confidence": round(avg_conf, 3)
        },
        "top_violations": [
            {"rule_code": code, "count": count} for code, count in top_violations
        ]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
