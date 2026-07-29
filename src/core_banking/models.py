"""SQLAlchemy models for mock Core Banking System."""
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text, Boolean, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import enum

from config.settings import settings

engine = create_engine(settings.DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class LoanStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    APPROVED = "approved"
    FLAGGED = "flagged"
    REJECTED = "rejected"
    MANUAL_REVIEW = "manual_review"

class DocumentType(str, enum.Enum):
    APPLICATION = "application"
    W2 = "w2"
    TAX_RETURN = "tax_return"
    BANK_STATEMENT = "bank_statement"
    PAY_STUB = "pay_stub"
    OTHER = "other"

class LoanApplication(Base):
    __tablename__ = "loan_applications"

    id = Column(Integer, primary_key=True, index=True)
    application_id = Column(String, unique=True, index=True, nullable=False)
    borrower_name = Column(String, nullable=False)
    borrower_ssn = Column(String, nullable=False)
    loan_amount = Column(Float, nullable=False)
    property_value = Column(Float, nullable=False)
    stated_income_annual = Column(Float)
    verified_income_annual = Column(Float)

    # Underwriting metrics
    dti_ratio = Column(Float)
    ltv_ratio = Column(Float)
    credit_score = Column(Integer)

    # Status
    status = Column(Enum(LoanStatus), default=LoanStatus.PENDING)
    decision_reason = Column(Text)

    # Audit
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    processed_at = Column(DateTime)

    # Performance
    extraction_confidence_avg = Column(Float)
    processing_time_seconds = Column(Float)

class DocumentRecord(Base):
    __tablename__ = "document_records"

    id = Column(Integer, primary_key=True, index=True)
    application_id = Column(String, index=True, nullable=False)
    document_type = Column(Enum(DocumentType), nullable=False)
    filename = Column(String, nullable=False)
    extracted_data = Column(Text)  # JSON string
    confidence_score = Column(Float)
    extraction_errors = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

class UnderwritingException(Base):
    __tablename__ = "underwriting_exceptions"

    id = Column(Integer, primary_key=True, index=True)
    application_id = Column(String, index=True, nullable=False)
    severity = Column(String, nullable=False)  # critical, warning, info
    rule_code = Column(String, nullable=False)
    rule_description = Column(Text, nullable=False)
    expected_value = Column(Text)
    actual_value = Column(Text)
    memo_path = Column(String)
    resolved = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class ProcessingMetric(Base):
    __tablename__ = "processing_metrics"

    id = Column(Integer, primary_key=True, index=True)
    application_id = Column(String, index=True)
    stage = Column(String, nullable=False)
    duration_ms = Column(Integer)
    success = Column(Boolean)
    error_message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

# Create tables
def init_db():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
