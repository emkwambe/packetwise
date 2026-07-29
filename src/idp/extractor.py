"""OCR field extraction engine.
Uses Tesseract + regex heuristics. Extensible to ML models."""
import re
import json
from typing import Dict, Any, Optional, List
import pytesseract
from PIL import Image
import fitz  # PyMuPDF
import cv2
import numpy as np

from src.idp.schemas import (
    DocType, ExtractionResult, W2Data, ApplicationData,
    BankStatementData, TaxReturnData
)
from src.idp.classifier import classify_document

class OCRExtractor:
    """Extracts text and structured fields from documents."""
    
    def __init__(self, tesseract_cmd: str = "tesseract"):
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
    
    def extract_text(self, file_path: str) -> str:
        """Extract raw text from PDF, image, or plain text file."""
        ext = file_path.lower().split(".")[-1]
        
        if ext == "txt":
            return self._extract_from_text(file_path)
        if ext == "pdf":
            return self._extract_from_pdf(file_path)
        else:
            return self._extract_from_image(file_path)
    
    def _extract_from_text(self, text_path: str) -> str:
        """Read raw text from a plain text file."""
        with open(text_path, "r", encoding="utf-8") as f:
            return f.read()
    
    def _extract_from_pdf(self, pdf_path: str) -> str:
        """Extract text from PDF using PyMuPDF + OCR fallback."""
        text = ""
        doc = fitz.open(pdf_path)
        
        for page in doc:
            page_text = page.get_text()
            if page_text.strip():
                text += page_text + "\n"
            else:
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                text += pytesseract.image_to_string(img) + "\n"
        
        doc.close()
        return text
    
    def _extract_from_image(self, image_path: str) -> str:
        """Extract text from image using Tesseract."""
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(f"Could not load image: {image_path}")
        
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        denoised = cv2.fastNlMeansDenoising(binary, None, 10, 7, 21)
        text = pytesseract.image_to_string(denoised)
        return text
    
    def extract_fields(self, file_path: str) -> ExtractionResult:
        """Full pipeline: text extraction -> classification -> field parsing."""
        from pathlib import Path

        raw_text = self.extract_text(file_path)
        doc_type, base_confidence = classify_document(raw_text)

        # Confidence modifiers
        confidence = base_confidence
        ext = Path(file_path).suffix.lower().lstrip(".")

        # Reduce if file is image (OCR less reliable than native text)
        if ext in ("png", "jpg", "jpeg", "tiff"):
            confidence *= 0.85  # OCR penalty

        # Reduce if PDF required OCR fallback (no native text extracted)
        if ext == "pdf" and not raw_text.strip():
            confidence *= 0.80  # Scanned PDF penalty

        errors = []
        extracted = {}

        try:
            if doc_type == DocType.W2:
                extracted = self._parse_w2(raw_text)
            elif doc_type == DocType.APPLICATION:
                extracted = self._parse_application(raw_text)
            elif doc_type == DocType.BANK_STATEMENT:
                extracted = self._parse_bank_statement(raw_text)
            elif doc_type == DocType.TAX_RETURN:
                extracted = self._parse_tax_return(raw_text)
            else:
                errors.append("Could not classify document type")
                confidence *= 0.5
        except Exception as e:
            errors.append(f"Field extraction error: {str(e)}")
            confidence *= 0.6

        # Penalize for missing critical fields
        if doc_type == DocType.W2 and not extracted.get("wages_box_1"):
            confidence *= 0.7
            errors.append("Could not extract Box 1 wages")

        return ExtractionResult(
            document_type=doc_type,
            confidence=round(confidence, 3),
            raw_text=raw_text,
            extracted_fields=extracted,
            extraction_errors=errors
        )
    
    def _parse_w2(self, text: str) -> Dict[str, Any]:
        data = {}
        text = text.replace(",", "").replace("$", "")
        
        patterns_box1 = [
            r"(?:Wages,\s*tips[,:]?\s*)?(?:Box\s*1[,:]?\s*)([\d,]+\.?\d*)",
            r"(?:Wages,?\s*tips,?\s*other\s*comp(?:ensation)?[,:]?\s*)([\d,]+\.?\d*)",
        ]
        data["wages_box_1"] = self._extract_amount(text, patterns_box1)
        
        patterns_box2 = [
            r"(?:Federal\s*income\s*tax\s*withheld[,:]?\s*)([\d,]+\.?\d*)",
            r"(?:Box\s*2[,:]?\s*)([\d,]+\.?\d*)",
        ]
        data["federal_tax_box_2"] = self._extract_amount(text, patterns_box2)
        
        patterns_box3 = [
            r"(?:Social\s*security\s*wages[,:]?\s*)([\d,]+\.?\d*)",
            r"(?:Box\s*3[,:]?\s*)([\d,]+\.?\d*)",
        ]
        data["ss_wages_box_3"] = self._extract_amount(text, patterns_box3)
        
        patterns_box5 = [
            r"(?:Medicare\s*wages[,:]?\s*)([\d,]+\.?\d*)",
            r"(?:Box\s*5[,:]?\s*)([\d,]+\.?\d*)",
        ]
        data["medicare_wages_box_5"] = self._extract_amount(text, patterns_box5)
        
        emp_match = re.search(r"(?:Employer\s*\(?.?\)?\s*name[,:]?\s*)([^\n]+)", text, re.IGNORECASE)
        if emp_match:
            data["employer_name"] = emp_match.group(1).strip()
        
        emp_match2 = re.search(r"(?:Employee\s*\(?.?\)?\s*name[,:]?\s*)([^\n]+)", text, re.IGNORECASE)
        if emp_match2:
            data["employee_name"] = emp_match2.group(1).strip()
        
        ssn_match = re.search(r"(\d{3}-\d{2}-\d{4})", text)
        if ssn_match:
            data["employee_ssn"] = ssn_match.group(1)
        
        year_match = re.search(r"20\d{2}", text)
        if year_match:
            data["year"] = int(year_match.group())
        
        return data
    
    def _parse_application(self, text: str) -> Dict[str, Any]:
        data = {}
        text = text.replace(",", "").replace("$", "")
        
        name_match = re.search(r"(?:Borrower\s*Name[,:]?\s*)([^\n]+)", text, re.IGNORECASE)
        if name_match:
            data["borrower_name"] = name_match.group(1).strip()
        
        patterns_loan = [
            r"(?:Loan\s*Amount[,:]?\s*)([\d,]+\.?\d*)",
            r"(?:Amount\s*requested[,:]?\s*)([\d,]+\.?\d*)",
        ]
        data["loan_amount"] = self._extract_amount(text, patterns_loan)
        
        patterns_prop = [
            r"(?:Property\s*Value[,:]?\s*)([\d,]+\.?\d*)",
            r"(?:Purchase\s*Price[,:]?\s*)([\d,]+\.?\d*)",
            r"(?:Appraised\s*Value[,:]?\s*)([\d,]+\.?\d*)",
        ]
        data["property_value"] = self._extract_amount(text, patterns_prop)
        
        patterns_income = [
            r"(?:Monthly\s*Income[,:]?\s*)([\d,]+\.?\d*)",
            r"(?:Gross\s*Monthly\s*Income[,:]?\s*)([\d,]+\.?\d*)",
        ]
        monthly = self._extract_amount(text, patterns_income)
        if monthly:
            data["stated_income_monthly"] = monthly
            data["stated_income_annual"] = monthly * 12
        
        score_match = re.search(r"(?:Credit\s*Score[,:]?\s*)(\d{3})", text, re.IGNORECASE)
        if score_match:
            data["credit_score"] = int(score_match.group(1))
        
        ssn_match = re.search(r"(\d{3}-\d{2}-\d{4})", text)
        if ssn_match:
            data["ssn"] = ssn_match.group(1)
        
        patterns_housing = [
            r"(?:Monthly\s*Housing\s*Payment[,:]?\s*)([\d,]+\.?\d*)",
            r"(?:Housing\s*Payment[,:]?\s*)([\d,]+\.?\d*)",
            r"(?:Monthly\s*Mortgage\s*Payment[,:]?\s*)([\d,]+\.?\d*)",
        ]
        data["monthly_housing_payment"] = self._extract_amount(text, patterns_housing)

        # ── Fannie Mae 1003 fields (realitydb-docs loan_app.py) ──
        # The plain-text fixtures carry only the handful of fields above; a
        # generated 1003 PDF also states purpose, property type, employment,
        # the liability total, and its own LTV/DTI. Every pattern below is
        # optional, so a fixture that omits them still parses.

        # `gross_monthly_income` is the 1003's own label. The stated_income_*
        # keys are kept as-is because the rule engine reads them.
        if data.get("stated_income_monthly") is not None:
            data["gross_monthly_income"] = data["stated_income_monthly"]

        # Sum of the borrower's monthly liabilities as printed on the form.
        data["monthly_debt"] = self._extract_amount(text, [
            r"(?:Total\s*Monthly\s*Debt[,:]?\s*)([\d,]+\.?\d*)",
        ])

        # Last four SSN digits only — the full number is never persisted.
        if data.get("ssn"):
            data["ssn_last4"] = data["ssn"][-4:]

        purpose = re.search(r"Loan\s*Purpose[,:]?\s*(Purchase|Refinance)",
                            text, re.IGNORECASE)
        if purpose:
            data["loan_purpose"] = purpose.group(1).strip().title()

        # Property type is a free-text label ("Single Family",
        # "Multi-Family (2-4 units)"), so it is read to end of line.
        prop_type = re.search(r"Property\s*Type[,:]?\s*([^\n]+)", text, re.IGNORECASE)
        if prop_type:
            data["property_type"] = prop_type.group(1).strip()

        # Hyphen is intentional: "Self-Employed" would otherwise truncate to
        # "Self" under a \w+ match.
        emp_type = re.search(r"Employment\s*Type[,:]?\s*([A-Za-z\-]+)",
                             text, re.IGNORECASE)
        if emp_type:
            data["employment_type"] = emp_type.group(1).strip()

        dti = re.search(r"Estimated\s*DTI[,:]?\s*([\d.]+)\s*%", text, re.IGNORECASE)
        if dti:
            try:
                # Stored as a ratio to match dti_ratio elsewhere in the app.
                data["estimated_dti"] = round(float(dti.group(1)) / 100, 4)
            except ValueError:
                pass

        # Prefer the LTV the form states; otherwise derive it, so downstream
        # underwriting always has a value when both amounts are present.
        ltv = re.search(r"LTV\s*Ratio[,:]?\s*([\d.]+)\s*%", text, re.IGNORECASE)
        if ltv:
            try:
                data["ltv_ratio"] = round(float(ltv.group(1)) / 100, 4)
            except ValueError:
                pass
        if data.get("ltv_ratio") is None:
            loan, prop = data.get("loan_amount"), data.get("property_value")
            if loan and prop:
                data["ltv_ratio"] = round(loan / prop, 4)

        return data
    
    # Recurring obligations that belong in a debt-to-income calculation.
    # Housing is tracked separately because the loan application already
    # states a monthly housing payment — counting both double-counts it.
    _HOUSING_DEBT_RE = r"RENT\s+PAYMENT|MORTGAGE\s+PMT"
    _NON_HOUSING_DEBT_RE = r"AUTO\s+LOAN(?:\s+PMT)?|STUDENT\s+LOAN(?:\s+PMT)?|CAR\s+PAYMENT|CREDIT\s+CARD"

    def _parse_bank_statement(self, text: str) -> Dict[str, Any]:
        """Parse a bank statement, including the multi-month statements
        produced by realitydb-docs.

        Transaction rows in those PDFs extract as separate lines — the
        description and its amount are never on the same line — so the debt
        patterns below deliberately step over a newline rather than using
        the same-line `[^\\n]*` form.
        """
        data = {}
        # Amounts are rendered as "$1,234.56"; strip the separators so a
        # single numeric pattern works everywhere.
        text = text.replace(",", "").replace("$", "")

        # ── Balances and totals ──
        # A statement may cover several months, so each label appears once
        # per period: the opening balance is the FIRST occurrence, the
        # closing balance the LAST, and the totals are summed.
        begin_hits = self._extract_all_amounts(text, [
            r"(?:Beginning|Starting|Opening)\s*Balance[:\s]+([\d,]+\.?\d*)",
        ])
        end_hits = self._extract_all_amounts(text, [
            r"(?:Ending|Closing)\s*Balance[:\s]+([\d,]+\.?\d*)",
        ])
        deposit_hits = self._extract_all_amounts(text, [
            r"Total\s*Deposits[:\s]+([\d,]+\.?\d*)",
        ])
        withdrawal_hits = self._extract_all_amounts(text, [
            r"Total\s*Withdrawals[:\s]+([\d,]+\.?\d*)",
        ])

        data["beginning_balance"] = begin_hits[0] if begin_hits else None
        data["ending_balance"] = end_hits[-1] if end_hits else None
        data["total_deposits"] = round(sum(deposit_hits), 2) if deposit_hits else None
        data["total_withdrawals"] = round(sum(withdrawal_hits), 2) if withdrawal_hits else None

        # Number of statement periods, used to turn multi-month totals into
        # monthly figures. Falls back to 1 so a single-month statement is
        # never divided away.
        months = max(len(begin_hits), 1)
        data["statement_months"] = months

        # ── Recurring obligations ──
        housing_items = self._find_debits(text, self._HOUSING_DEBT_RE)
        other_items = self._find_debits(text, self._NON_HOUSING_DEBT_RE)

        monthly_housing = round(sum(i["amount"] for i in housing_items) / months, 2)
        monthly_other = round(sum(i["amount"] for i in other_items) / months, 2)

        data["monthly_housing_from_statement"] = monthly_housing
        data["monthly_recurring_debts"] = round(monthly_housing + monthly_other, 2)

        # `recurring_debits` feeds the DTI calculation in the rule engine,
        # which already adds the application's housing payment — so housing
        # is excluded here and the remainder is averaged to one month.
        data["recurring_debits"] = [
            {"name": name, "amount": round(total / months, 2)}
            for name, total in self._group_debits(other_items).items()
        ]

        # ── Identity fields ──
        holder = re.search(r"Account\s*Holder[:\s]+([^\n]+)", text, re.IGNORECASE)
        if holder:
            data["account_holder_name"] = holder.group(1).strip()

        # A multi-month statement carries one period label per page; report
        # the full span rather than only the first month.
        periods = [m.group(1).strip() for m in
                   re.finditer(r"Statement\s*period[:\s]+([^\n]+)", text, re.IGNORECASE)]
        if periods:
            data["statement_period"] = periods[0] if len(periods) == 1 else f"{periods[0]} to {periods[-1]}"

        account = re.search(r"Account\s*Number[:\s]+(\*{0,4}\d{4})", text, re.IGNORECASE)
        if account:
            data["account_number"] = account.group(1).strip()

        routing = re.search(r"Routing\s*Number[:\s]+(\d{9})", text, re.IGNORECASE)
        if routing:
            data["routing_number"] = routing.group(1).strip()

        bank = self._extract_bank_name(text)
        if bank:
            data["bank_name"] = bank

        return data

    def _find_debits(self, text: str, label_pattern: str) -> List[Dict[str, Any]]:
        """Find debit rows whose amount may sit on the following line.

        Matches `DESCRIPTION` then the first number after it, allowing the
        trailing words of a description (e.g. "MORTGAGE PMT PENNYMAC") and a
        line break to intervene.
        """
        pattern = rf"({label_pattern})[^\d\n]*[\s\n]*([\d,]+\.?\d*)"
        items = []
        for match in re.finditer(pattern, text, re.IGNORECASE):
            try:
                amount = float(match.group(2).replace(",", ""))
            except ValueError:
                continue
            items.append({"name": match.group(1).strip().upper(), "amount": amount})
        return items

    def _group_debits(self, items: List[Dict[str, Any]]) -> Dict[str, float]:
        grouped: Dict[str, float] = {}
        for item in items:
            grouped[item["name"]] = grouped.get(item["name"], 0.0) + item["amount"]
        return grouped

    def _extract_bank_name(self, text: str) -> Optional[str]:
        """The bank name is the line immediately above 'ACCOUNT STATEMENT'."""
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        for i, line in enumerate(lines):
            if line.upper().startswith("ACCOUNT STATEMENT") and i > 0:
                candidate = lines[i - 1]
                # Skip the diagonal watermark, which extracts before the header.
                if "SYNTHETIC" in candidate.upper() and i > 1:
                    candidate = lines[i - 2]
                return candidate
        return None

    def _extract_all_amounts(self, text: str, patterns: List[str]) -> List[float]:
        """Every match for the given patterns, in document order."""
        found: List[float] = []
        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                try:
                    found.append(float(match.group(1).replace(",", "")))
                except ValueError:
                    continue
        return found
    
    def _parse_tax_return(self, text: str) -> Dict[str, Any]:
        data = {}
        text = text.replace(",", "").replace("$", "")
        
        patterns_agi = [
            r"(?:Adjusted\s*Gross\s*Income[,:]?\s*)([\d,]+\.?\d*)",
            r"(?:AGI[,:]?\s*)([\d,]+\.?\d*)",
        ]
        data["agi"] = self._extract_amount(text, patterns_agi)
        
        patterns_taxable = [
            r"(?:Taxable\s*income[,:]?\s*)([\d,]+\.?\d*)",
        ]
        data["taxable_income"] = self._extract_amount(text, patterns_taxable)
        
        patterns_schedc = [
            r"(?:Schedule\s*C[,:]?\s*)([\d,]+\.?\d*)",
            r"(?:Business\s*income[,:]?\s*)([\d,]+\.?\d*)",
        ]
        data["business_income_schedule_c"] = self._extract_amount(text, patterns_schedc)
        
        year_match = re.search(r"20\d{2}", text)
        if year_match:
            data["year"] = int(year_match.group())
        
        return data
    
    def _extract_amount(self, text: str, patterns: List[str]) -> Optional[float]:
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    return float(match.group(1).replace(",", ""))
                except ValueError:
                    continue
        return None
