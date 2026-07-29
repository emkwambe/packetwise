"""JSON schemas and data models for extracted documents."""
from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum

class DocType(str, Enum):
    APPLICATION = "application"
    W2 = "w2"
    TAX_RETURN = "tax_return"
    BANK_STATEMENT = "bank_statement"
    PAY_STUB = "pay_stub"
    UNKNOWN = "unknown"

class ExtractionResult(BaseModel):
    document_type: DocType
    confidence: float = Field(ge=0.0, le=1.0)
    raw_text: str
    extracted_fields: dict
    extraction_errors: List[str] = []

class W2Data(BaseModel):
    employer_name: Optional[str] = None
    employer_ein: Optional[str] = None
    employee_name: Optional[str] = None
    employee_ssn: Optional[str] = None
    wages_box_1: Optional[float] = None
    federal_tax_box_2: Optional[float] = None
    ss_wages_box_3: Optional[float] = None
    ss_tax_box_4: Optional[float] = None
    medicare_wages_box_5: Optional[float] = None
    medicare_tax_box_6: Optional[float] = None
    state_wages_box_16: Optional[float] = None
    state_tax_box_17: Optional[float] = None
    year: Optional[int] = None

class ApplicationData(BaseModel):
    borrower_name: Optional[str] = None
    co_borrower_name: Optional[str] = None
    ssn: Optional[str] = None
    loan_amount: Optional[float] = None
    property_value: Optional[float] = None
    property_address: Optional[str] = None
    stated_income_monthly: Optional[float] = None
    stated_income_annual: Optional[float] = None
    employment_status: Optional[str] = None
    employer_name: Optional[str] = None
    loan_purpose: Optional[str] = None
    credit_score: Optional[int] = None

class BankStatementData(BaseModel):
    bank_name: Optional[str] = None
    account_holder_name: Optional[str] = None
    account_number: Optional[str] = None
    routing_number: Optional[str] = None
    statement_period: Optional[str] = None
    statement_months: Optional[int] = None   # periods covered by the document
    beginning_balance: Optional[float] = None
    ending_balance: Optional[float] = None
    total_deposits: Optional[float] = None
    total_withdrawals: Optional[float] = None
    # Monthly averages. `monthly_recurring_debts` includes housing;
    # `recurring_debits` excludes it, because the loan application already
    # supplies a monthly housing payment and the rule engine adds both.
    monthly_recurring_debts: Optional[float] = None
    monthly_housing_from_statement: Optional[float] = None
    recurring_debits: List[dict] = []  # [{"name": "AUTO LOAN PMT", "amount": 450.00}]

class TaxReturnData(BaseModel):
    taxpayer_name: Optional[str] = None
    ssn: Optional[str] = None
    filing_status: Optional[str] = None
    agi: Optional[float] = None  # Adjusted Gross Income
    taxable_income: Optional[float] = None
    total_tax: Optional[float] = None
    business_income_schedule_c: Optional[float] = None
    year: Optional[int] = None
