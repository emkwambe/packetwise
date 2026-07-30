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
    BankStatementData, TaxReturnData, PayStubData
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

        # Confidence modifiers. Held as a separate multiplier so a document
        # type that scores itself from extracted fields (pay stubs) is still
        # penalised for coming in as a scan.
        media_penalty = 1.0
        ext = Path(file_path).suffix.lower().lstrip(".")

        # Reduce if file is image (OCR less reliable than native text)
        if ext in ("png", "jpg", "jpeg", "tiff"):
            media_penalty *= 0.85  # OCR penalty

        # Reduce if PDF required OCR fallback (no native text extracted)
        if ext == "pdf" and not raw_text.strip():
            media_penalty *= 0.80  # Scanned PDF penalty

        confidence = base_confidence * media_penalty

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
            elif doc_type == DocType.PAY_STUB:
                extracted = self._parse_pay_stub(raw_text)
            else:
                # Reached only when classification itself failed. A document
                # that classified but has no parser used to land here too,
                # which reported "could not classify" for a document that had
                # been classified perfectly well (ISSUE-009).
                errors.append("Could not classify document type")
                confidence *= 0.5
        except Exception as e:
            errors.append(f"Field extraction error: {str(e)}")
            confidence *= 0.6

        # Penalize for missing critical fields
        if doc_type == DocType.W2 and not extracted.get("wages_box_1"):
            confidence *= 0.7
            errors.append("Could not extract Box 1 wages")

        # A pay stub's confidence is earned from the fields actually parsed
        # rather than from keyword density, then carries the same media
        # penalty as every other document type.
        if doc_type == DocType.PAY_STUB:
            stub_score, stub_errors = self._score_pay_stub(extracted)
            confidence = stub_score * media_penalty
            errors.extend(stub_errors)

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
        
        # The W-2's identity block is two columns, so the employer and
        # employee labels are emitted as one pair of lines and their values as
        # the next pair:
        #
        #   c Employer name and address
        #   e/f Employee name and address
        #   Graphic Design Institute      <- employer
        #   Andrew Myers                  <- employee
        #
        # A same-line `Employer name[:,]?\s*([^\n]+)` therefore captured the
        # remainder of the LABEL — every W-2 processed before this fix stored
        # "and address" as both the employer and the employee name.
        names = self._parse_w2_identity_block(text)
        data.update(names)

        # Single-column fallback for fixtures that do put the value on the
        # label's line ("Employer name: Acme Corporation").
        if not data.get("employer_name"):
            m = re.search(r"Employer\s*name[,:]\s*([^\n]+)", text, re.IGNORECASE)
            if m:
                data["employer_name"] = m.group(1).strip()
        if not data.get("employee_name"):
            m = re.search(r"Employee\s*name[,:]\s*([^\n]+)", text, re.IGNORECASE)
            if m:
                data["employee_name"] = m.group(1).strip()
        
        ssn_match = re.search(r"(\d{3}-\d{2}-\d{4})", text)
        if ssn_match:
            data["employee_ssn"] = ssn_match.group(1)
        
        year_match = re.search(r"20\d{2}", text)
        if year_match:
            data["year"] = int(year_match.group())
        
        return data
    
    def _parse_w2_identity_block(self, text: str) -> Dict[str, Any]:
        """Employer and employee names from the two-column identity block.

        Locates the employer-name label, then the employee-name label that
        follows it, then reads the next two non-blank lines as the two values
        in the same left-to-right order the labels appeared in.
        """
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        out: Dict[str, Any] = {}

        employer_idx = employee_idx = None
        for i, line in enumerate(lines):
            if employer_idx is None and re.search(
                r"Employer\s*name", line, re.IGNORECASE
            ):
                employer_idx = i
            elif employer_idx is not None and employee_idx is None and re.search(
                r"Employee\s*name", line, re.IGNORECASE
            ):
                employee_idx = i
                break

        if employer_idx is None or employee_idx != employer_idx + 1:
            return out

        values = lines[employee_idx + 1: employee_idx + 3]
        if len(values) >= 1 and not self._looks_like_label(values[0]):
            out["employer_name"] = values[0]
        if len(values) >= 2 and not self._looks_like_label(values[1]):
            out["employee_name"] = values[1]
        return out

    @staticmethod
    def _looks_like_label(line: str) -> bool:
        """Guard against reading a form label as if it were a value."""
        return bool(re.search(
            r"name\s+and\s+address|^\d+\s|wages|withheld|social security",
            line, re.IGNORECASE,
        ))

    # Every value on a realitydb-docs pay stub sits on the line AFTER its
    # label — the panels are two-column, so reportlab emits both labels then
    # both values. `\s+` spans the newline, so a label followed by one or two
    # amounts reads as "LABEL <current> <ytd>".
    _STUB_MONEY = r"([\d,]*\.?\d+)"

    def _parse_pay_stub(self, text: str) -> Dict[str, Any]:
        """Parse a bi-weekly pay stub (realitydb-docs paystub.py layout).

        Two views of the text are needed: amounts are read from a
        comma-stripped copy so a single numeric pattern works, but the pay
        period dates are rendered "October 23, 2024" and stripping commas
        would destroy them.
        """
        data: Dict[str, Any] = {}
        raw = text
        stripped = text.replace(",", "").replace("$", "")

        def pair(label: str) -> tuple:
            """Current and YTD amounts for one table row."""
            m = re.search(
                rf"{label}[^\n]*\s+{self._STUB_MONEY}\s+{self._STUB_MONEY}",
                stripped, re.IGNORECASE,
            )
            if not m:
                return (None, None)
            try:
                return (float(m.group(1)), float(m.group(2)))
            except ValueError:
                return (None, None)

        def line_after(label: str) -> Optional[str]:
            m = re.search(rf"{label}\s*\n\s*([^\n]+)", raw, re.IGNORECASE)
            return m.group(1).strip() if m else None

        # ── Earnings and deductions ──
        data["gross_pay"], data["ytd_gross"] = pair(r"GROSS\s+PAY")
        if data["gross_pay"] is None:
            data["gross_pay"], data["ytd_gross"] = pair(r"Regular\s+Pay")
        data["net_pay"], data["ytd_net_pay"] = pair(r"NET\s+PAY")
        data["federal_tax_withheld"], data["ytd_federal_tax"] = pair(
            r"Federal\s+Income\s+Tax")
        # The row is labelled with the state code, e.g. "NC State Income Tax".
        data["state_tax_withheld"], data["ytd_state_tax"] = pair(
            r"State\s+Income\s+Tax")
        data["ss_tax_withheld"], data["ytd_ss_tax"] = pair(
            r"Social\s+Security\s+Tax")
        data["medicare_tax_withheld"], data["ytd_medicare_tax"] = pair(
            r"Medicare\s+Tax")
        # Absent entirely when the borrower defers nothing.
        data["retirement_deduction"], data["ytd_retirement"] = pair(
            r"401\(k\)")
        data["total_deductions"], _ = pair(r"TOTAL\s+DEDUCTIONS")

        # Taxable YTD is stated on the stub. Fall back to deriving it, so the
        # W-2 cross-check still has a figure if the line is ever dropped.
        data["ytd_taxable"] = self._extract_amount(stripped, [
            r"Taxable\s+wages\s+YTD[^:]*:\s*" + self._STUB_MONEY,
        ])
        if data["ytd_taxable"] is None and data.get("ytd_gross") is not None:
            data["ytd_taxable"] = round(
                data["ytd_gross"] - (data.get("ytd_retirement") or 0.0), 2
            )

        # ── Pay period ──
        period = re.search(r"Period\s+(\d+)\s+of\s+(\d+)", raw, re.IGNORECASE)
        if period:
            data["pay_period_number"] = int(period.group(1))
            data["pay_periods_per_year"] = int(period.group(2))

        for key, label in (
            ("pay_period_start", r"PAY\s+PERIOD\s+START"),
            ("pay_period_end", r"PAY\s+PERIOD\s+END"),
            ("pay_date", r"PAY\s+DATE"),
        ):
            m = re.search(
                rf"{label}\s*\n\s*([A-Za-z]+\s+\d+,?\s+\d{{4}})",
                raw, re.IGNORECASE,
            )
            if m:
                data[key] = m.group(1).strip()

        freq = line_after(r"PAY\s+FREQUENCY")
        if freq:
            data["pay_frequency"] = freq

        # ── Identity ──
        name = line_after(r"EMPLOYEE\s+NAME")
        if name:
            data["employee_name"] = name

        emp_id = line_after(r"EMPLOYEE\s+ID")
        if emp_id:
            data["employee_id"] = emp_id

        # The employer is the banner line immediately above "EIN:". Taking the
        # first uppercase block instead would return the diagonal
        # "SYNTHETIC — NOT VALID" watermark, which extracts ahead of the header.
        employer = self._line_before(raw, r"^EIN:")
        if employer:
            data["employer_name"] = employer

        ssn = re.search(r"\*{2,3}-\*{2}-(\d{4})", raw)
        if ssn:
            data["ssn_last4"] = ssn.group(1)

        dd = re.search(r"account\s+ending\s+\*{2,4}(\d{4})", raw, re.IGNORECASE)
        if dd:
            data["direct_deposit_last4"] = dd.group(1)

        return {k: v for k, v in data.items() if v is not None}

    # Fields beyond the three required ones. Each present field lifts
    # confidence, so a stub that parses fully scores 1.0 and a partial parse
    # is visibly worse rather than silently equal.
    _STUB_OPTIONAL_FIELDS = (
        "employee_name", "employer_name", "employee_id", "ssn_last4",
        "pay_period_start", "pay_period_end", "pay_date",
        "pay_period_number", "pay_frequency",
        "federal_tax_withheld", "state_tax_withheld", "ss_tax_withheld",
        "medicare_tax_withheld", "total_deductions", "ytd_federal_tax",
        "ytd_net_pay", "ytd_taxable", "direct_deposit_last4",
    )

    def _score_pay_stub(self, data: Dict[str, Any]) -> tuple:
        """Confidence for a pay stub: 0.85 for the three required fields,
        +0.05 per optional field, capped at 1.0."""
        errors: List[str] = []
        required = ("gross_pay", "net_pay", "ytd_gross")
        missing = [f for f in required if data.get(f) is None]
        if missing:
            errors.append(
                "Could not extract required pay stub fields: "
                + ", ".join(missing)
            )
            # Proportional to what was found, so a stub missing one field is
            # not scored the same as one that parsed nothing.
            found = len(required) - len(missing)
            return round(0.85 * found / len(required), 3), errors

        confidence = 0.85
        for field in self._STUB_OPTIONAL_FIELDS:
            if data.get(field) is not None:
                confidence += 0.05
        return round(min(confidence, 1.0), 3), errors

    def _line_before(self, text: str, marker_pattern: str) -> Optional[str]:
        """The non-blank line immediately preceding a marker line."""
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        for i, line in enumerate(lines):
            if re.search(marker_pattern, line, re.IGNORECASE) and i > 0:
                return lines[i - 1]
        return None

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
