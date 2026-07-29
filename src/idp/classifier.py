"""Document type classifier using heuristics + keyword matching.
Extensible to LayoutLM/Donut for production."""
import re
from typing import Tuple
from src.idp.schemas import DocType

# Keyword signatures for classification
DOC_SIGNATURES = {
    DocType.W2: {
        "required": ["w-2", "wage and tax"],
        "strong": ["box 1", "box 2", "employer", "employee", "federal income tax", "social security"],
        "score_threshold": 2
    },
    DocType.APPLICATION: {
        "required": ["loan application", "mortgage application", "uniform residential"],
        "strong": ["borrower", "loan amount", "property value", "credit score", "monthly income"],
        "score_threshold": 2
    },
    DocType.BANK_STATEMENT: {
        "required": ["account statement", "statement", "account summary"],
        "strong": [
            "beginning balance", "ending balance", "total deposits",
            "total withdrawals", "routing number", "direct dep",
            "member fdic", "member ncua", "deposits", "withdrawals",
            "transactions", "statement period",
        ],
        "score_threshold": 2
    },
    DocType.TAX_RETURN: {
        "required": ["form 1040", "tax return", "adjusted gross income"],
        "strong": ["agi", "taxable income", "filing status", "schedule c", "irs"],
        "score_threshold": 2
    },
    DocType.PAY_STUB: {
        "required": ["pay stub", "pay statement", "earnings statement"],
        "strong": ["gross pay", "net pay", "ytd", "deductions", "pay period"],
        "score_threshold": 2
    }
}

def classify_document(text: str) -> Tuple[DocType, float]:
    """
    Classify document type from extracted text.
    Returns (doc_type, confidence_score).
    """
    text_lower = text.lower()
    scores = {}

    for doc_type, sig in DOC_SIGNATURES.items():
        score = 0
        required_hits = sum(1 for kw in sig["required"] if kw in text_lower)
        strong_hits = sum(1 for kw in sig["strong"] if kw in text_lower)

        # Weighted scoring
        score = (required_hits * 3) + (strong_hits * 1)

        # Boost if required keywords found
        if required_hits > 0:
            score += 2

        scores[doc_type] = score

    if not scores:
        return DocType.UNKNOWN, 0.0

    best_type = max(scores, key=scores.get)
    best_score = scores[best_type]
    max_possible = max(len(s["required"]) * 3 + len(s["strong"]) * 1 + 2 for s in DOC_SIGNATURES.values())
    confidence = min(best_score / max(max_possible * 0.3, 1), 1.0)

    # If best score is too low, mark unknown
    if best_score < DOC_SIGNATURES[best_type]["score_threshold"]:
        return DocType.UNKNOWN, confidence * 0.5

    return best_type, confidence
