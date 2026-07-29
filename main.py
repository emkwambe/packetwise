"""PacketWise - Commercial Loan Application & Income Verification System.
FastAPI main application entry point."""
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
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
from src.auth.session import (
    SESSION_COOKIE, INSECURE_DEFAULTS,
    create_session_token, verify_session_token, check_password,
)
from config.settings import settings
from datetime import datetime

app = FastAPI(
    title=settings.APP_NAME,
    description="Automated Commercial Loan Intake with IDP, OCR, and Underwriting Rules",
    version="1.0.0"
)

# CORS
# An explicit allowlist, not "*": the dashboard now authenticates with a
# cookie, and a wildcard origin combined with credentials would let any site
# make authenticated calls on a logged-in user's behalf.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def api_key_middleware(request: Request, call_next):
    # Skip auth for health, root and the auth endpoints themselves
    skip_paths = [
        "/api/v1/health",
        "/",
        "/docs",
        "/openapi.json",
        "/redoc",
        "/api/v1/auth/login",
        "/api/v1/auth/logout",
        "/api/v1/auth/status",
    ]
    if request.url.path in skip_paths:
        return await call_next(request)

    # Two accepted credentials, in order of cost:
    #   1. X-API-Key   — server-to-server callers (integration script, jobs)
    #   2. pw_session  — a browser that logged in with the dashboard password
    key = request.headers.get("X-API-Key")
    if key and check_password(key, settings.API_KEY):
        return await call_next(request)

    if verify_session_token(request.cookies.get(SESSION_COOKIE),
                            settings.SESSION_SECRET):
        return await call_next(request)

    return JSONResponse(
        status_code=401,
        content={"detail": "Invalid or missing API key"}
    )

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
    # Shipping the built-in credentials outside development would leave the
    # deployment open to anyone who has read the source.
    if not settings.DEBUG:
        insecure = [
            name for name, value in (
                ("API_KEY", settings.API_KEY),
                ("DASHBOARD_PASSWORD", settings.DASHBOARD_PASSWORD),
                ("SESSION_SECRET", settings.SESSION_SECRET),
            ) if value in INSECURE_DEFAULTS
        ]
        if insecure:
            print(f"WARNING: default credentials still in use with DEBUG off: "
                  f"{', '.join(insecure)}. Set them in .env before deploying.")


# ─── Authentication ──────────────────────────────────────
class LoginRequest(BaseModel):
    password: str


@app.post("/api/v1/auth/login", tags=["Auth"])
def login(payload: LoginRequest, response: Response):
    """Exchange the dashboard password for an HttpOnly session cookie."""
    if not check_password(payload.password, settings.DASHBOARD_PASSWORD):
        return JSONResponse(status_code=401,
                            content={"detail": "Invalid password"})

    token = create_session_token(settings.SESSION_SECRET,
                                 settings.SESSION_TTL_HOURS)
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,          # not readable from JavaScript
        samesite="lax",         # not sent on cross-site POSTs
        secure=not settings.DEBUG,   # HTTPS-only outside local development
        max_age=settings.SESSION_TTL_HOURS * 3600,
        path="/",
    )
    return {"authenticated": True,
            "expires_in_hours": settings.SESSION_TTL_HOURS}


@app.post("/api/v1/auth/logout", tags=["Auth"])
def logout(response: Response):
    """Clear the session cookie on this browser."""
    response.delete_cookie(key=SESSION_COOKIE, path="/")
    return {"authenticated": False}


@app.get("/api/v1/auth/status", tags=["Auth"])
def auth_status(request: Request):
    """Whether the caller currently holds a valid session."""
    return {"authenticated": verify_session_token(
        request.cookies.get(SESSION_COOKIE), settings.SESSION_SECRET)}

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
