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

class PayStubData(BaseModel):
    # ── Identity ──
    employee_name: Optional[str] = None
    employer_name: Optional[str] = None
    employee_id: Optional[str] = None
    ssn_last4: Optional[str] = None
    # ── Pay period ──
    pay_period_start: Optional[str] = None
    pay_period_end: Optional[str] = None
    pay_date: Optional[str] = None
    pay_period_number: Optional[int] = None
    pay_periods_per_year: Optional[int] = None   # "Period 22 of 26" -> 26
    pay_frequency: Optional[str] = None
    # ── Current period ──
    gross_pay: Optional[float] = None
    federal_tax_withheld: Optional[float] = None
    state_tax_withheld: Optional[float] = None
    ss_tax_withheld: Optional[float] = None
    medicare_tax_withheld: Optional[float] = None
    retirement_deduction: Optional[float] = None
    total_deductions: Optional[float] = None
    net_pay: Optional[float] = None
    # ── Year to date ──
    ytd_gross: Optional[float] = None
    ytd_federal_tax: Optional[float] = None
    ytd_net_pay: Optional[float] = None
    # These four are not in the original field list but are what make a
    # cross-check against the W-2 exact rather than approximate: a pre-tax
    # deferral is exempt from income tax and not from FICA, so YTD gross
    # cannot be compared to W-2 box 1 directly. ytd_taxable is gross less
    # deferrals and is the figure that ties to box 1.
    ytd_state_tax: Optional[float] = None
    ytd_ss_tax: Optional[float] = None
    ytd_medicare_tax: Optional[float] = None
    ytd_retirement: Optional[float] = None
    ytd_taxable: Optional[float] = None
    # ── Payment ──
    direct_deposit_last4: Optional[str] = None


class TaxReturnData(BaseModel):
    taxpayer_name: Optional[str] = None
    ssn: Optional[str] = None
    filing_status: Optional[str] = None
    agi: Optional[float] = None  # Adjusted Gross Income
    taxable_income: Optional[float] = None
    total_tax: Optional[float] = None
    business_income_schedule_c: Optional[float] = None
    year: Optional[int] = None
