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
        raw_text = self.extract_text(file_path)
        doc_type, confidence = classify_document(raw_text)
        
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
        except Exception as e:
            errors.append(f"Field extraction error: {str(e)}")
        
        return ExtractionResult(
            document_type=doc_type,
            confidence=confidence,
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
        
        return data
    
    def _parse_bank_statement(self, text: str) -> Dict[str, Any]:
        data = {}
        text = text.replace(",", "").replace("$", "")
        
        patterns_end = [
            r"(?:Ending\s*balance[,:]?\s*)([\d,]+\.?\d*)",
            r"(?:Closing\s*balance[,:]?\s*)([\d,]+\.?\d*)",
        ]
        data["ending_balance"] = self._extract_amount(text, patterns_end)
        
        patterns_begin = [
            r"(?:Beginning\s*balance[,:]?\s*)([\d,]+\.?\d*)",
            r"(?:Opening\s*balance[,:]?\s*)([\d,]+\.?\d*)",
        ]
        data["beginning_balance"] = self._extract_amount(text, patterns_begin)
        
        patterns_dep = [
            r"(?:Total\s*deposits[,:]?\s*)([\d,]+\.?\d*)",
        ]
        data["total_deposits"] = self._extract_amount(text, patterns_dep)
        
        patterns_with = [
            r"(?:Total\s*withdrawals[,:]?\s*)([\d,]+\.?\d*)",
        ]
        data["total_withdrawals"] = self._extract_amount(text, patterns_with)
        
        recurring = []
        debit_lines = re.findall(r"(Auto\s*Loan|Student\s*Loan|Mortgage|Credit\s*Card).*?([\d,]+\.?\d*)", text, re.IGNORECASE)
        for name, amount in debit_lines:
            recurring.append({"name": name.strip(), "amount": float(amount.replace(",", ""))})
        data["recurring_debits"] = recurring
        
        return data
    
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
