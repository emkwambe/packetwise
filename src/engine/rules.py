"""Underwriting rule engine.
Calculates financial metrics and validates against business rules."""
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum
import yaml
from pathlib import Path

class Severity(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"

@dataclass
class RuleViolation:
    rule_code: str
    severity: Severity
    description: str
    expected_value: Optional[str] = None
    actual_value: Optional[str] = None

class UnderwritingEngine:
    """Core underwriting decision engine."""

    def __init__(self, rules_path: str = "config/rules.yaml"):
        self.rules = self._load_rules(rules_path)

    def _load_rules(self, path: str) -> Dict:
        with open(path, "r") as f:
            return yaml.safe_load(f)

    def calculate_dti(self, monthly_debt: float, monthly_income: float) -> Optional[float]:
        """Debt-to-Income ratio."""
        if monthly_income <= 0:
            return None
        return round(monthly_debt / monthly_income, 4)

    def calculate_ltv(self, loan_amount: float, property_value: float) -> Optional[float]:
        """Loan-to-Value ratio."""
        if property_value <= 0:
            return None
        return round(loan_amount / property_value, 4)

    def calculate_monthly_debt(self, recurring_debits: List[Dict[str, Any]], 
                                housing_payment: float = 0) -> float:
        """Sum all recurring monthly debt obligations."""
        total = housing_payment
        for debit in recurring_debits:
            total += debit.get("amount", 0)
        return total

    def verify_income(self, stated_annual: float, verified_annual: float, 
                      tolerance: float = 0.10) -> Dict[str, Any]:
        """Cross-check stated income against verified income."""
        if stated_annual <= 0 or verified_annual <= 0:
            return {"match": False, "variance": None, "within_tolerance": False}

        variance = abs(stated_annual - verified_annual) / stated_annual
        return {
            "match": variance <= tolerance,
            "variance": round(variance, 4),
            "within_tolerance": variance <= tolerance,
            "tolerance": tolerance
        }

    def evaluate(self, application: Dict[str, Any], 
                 documents: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Full underwriting evaluation.
        Returns decision, metrics, and violations.
        """
        violations: List[RuleViolation] = []
        metrics = {}

        # ─── Extract data from documents ───
        app_data = next((d.get("fields", {}) for d in documents if d.get("type") == "application"), {})
        w2_data = next((d.get("fields", {}) for d in documents if d.get("type") == "w2"), {})
        bank_data = next((d.get("fields", {}) for d in documents if d.get("type") == "bank_statement"), {})
        tax_data = next((d.get("fields", {}) for d in documents if d.get("type") == "tax_return"), {})

        stated_income = app_data.get("stated_income_annual", 0)
        loan_amount = app_data.get("loan_amount", 0)
        property_value = app_data.get("property_value", 0)
        credit_score = app_data.get("credit_score", 0)

        # ─── Verified income ───
        verified_income = 0
        if w2_data.get("wages_box_1"):
            verified_income = w2_data["wages_box_1"]
        elif tax_data.get("agi"):
            verified_income = tax_data["agi"]

        metrics["stated_income_annual"] = stated_income
        metrics["verified_income_annual"] = verified_income

        # ─── Income verification ───
        if stated_income > 0 and verified_income > 0:
            income_check = self.verify_income(stated_income, verified_income)
            metrics["income_variance"] = income_check["variance"]
            metrics["income_match"] = income_check["match"]

            if not income_check["within_tolerance"]:
                violations.append(RuleViolation(
                    rule_code="INCOME_VARIANCE",
                    severity=Severity.WARNING,
                    description="Stated income exceeds verified income by more than tolerance",
                    expected_value=f"Within {income_check['tolerance']*100}% of ${stated_income:,.2f}",
                    actual_value=f"${verified_income:,.2f} ({income_check['variance']*100:.1f}% variance)"
                ))

        # ─── DTI Calculation ───
        monthly_income = verified_income / 12 if verified_income > 0 else stated_income / 12
        recurring = bank_data.get("recurring_debits", [])
        housing = app_data.get("monthly_housing_payment", 0)
        monthly_debt = self.calculate_monthly_debt(recurring, housing)

        dti = self.calculate_dti(monthly_debt, monthly_income) if monthly_income > 0 else None
        metrics["monthly_income"] = round(monthly_income, 2)
        metrics["monthly_debt"] = round(monthly_debt, 2)
        metrics["dti_ratio"] = dti

        if dti is not None:
            if dti > self.rules["thresholds"]["dti_absolute_maximum"]:
                violations.append(RuleViolation(
                    rule_code="DTI_EXCEEDS_MAX",
                    severity=Severity.CRITICAL,
                    description=f"DTI ratio ({dti*100:.1f}%) exceeds absolute maximum ({self.rules['thresholds']['dti_absolute_maximum']*100:.0f}%)",
                    expected_value=f"<={self.rules['thresholds']['dti_absolute_maximum']*100:.0f}%",
                    actual_value=f"{dti*100:.1f}%"
                ))
            elif dti > self.rules["thresholds"]["dti_qualified_mortgage"]:
                violations.append(RuleViolation(
                    rule_code="DTI_EXCEEDS_QM",
                    severity=Severity.WARNING,
                    description=f"DTI ratio ({dti*100:.1f}%) exceeds QM threshold ({self.rules['thresholds']['dti_qualified_mortgage']*100:.0f}%)",
                    expected_value=f"<={self.rules['thresholds']['dti_qualified_mortgage']*100:.0f}%",
                    actual_value=f"{dti*100:.1f}%"
                ))

        # ─── LTV Calculation ───
        ltv = self.calculate_ltv(loan_amount, property_value) if property_value > 0 else None
        metrics["ltv_ratio"] = ltv

        if ltv and ltv > self.rules["thresholds"]["max_ltv_ratio"]:
            violations.append(RuleViolation(
                rule_code="LTV_EXCEEDS_MAX",
                severity=Severity.WARNING,
                description=f"LTV ratio ({ltv*100:.1f}%) exceeds maximum",
                expected_value=f"<={self.rules['thresholds']['max_ltv_ratio']*100:.0f}%",
                actual_value=f"{ltv*100:.1f}%"
            ))

        # ─── Credit Score ───
        metrics["credit_score"] = credit_score
        if credit_score > 0 and credit_score < self.rules["thresholds"]["min_credit_score"]:
            violations.append(RuleViolation(
                rule_code="CREDIT_SCORE_LOW",
                severity=Severity.CRITICAL,
                description=f"Credit score ({credit_score}) below minimum requirement",
                expected_value=f">={self.rules['thresholds']['min_credit_score']}",
                actual_value=str(credit_score)
            ))

        # ─── Missing required documents ───
        doc_types = [d.get("type") for d in documents]
        required = self.rules["income_verification"]["required_docs"]
        for req in required:
            if req not in doc_types:
                violations.append(RuleViolation(
                    rule_code="MISSING_REQUIRED_DOC",
                    severity=Severity.CRITICAL,
                    description=f"Required document missing: {req}",
                    expected_value=req,
                    actual_value="Not found"
                ))

        # ─── Decision ───
        critical_count = sum(1 for v in violations if v.severity == Severity.CRITICAL)
        warning_count = sum(1 for v in violations if v.severity == Severity.WARNING)

        if critical_count > 0:
            decision = "rejected"
        elif warning_count > 0:
            decision = "flagged"
        else:
            decision = "approved"

        return {
            "decision": decision,
            "metrics": metrics,
            "violations": [self._violation_to_dict(v) for v in violations],
            "summary": {
                "critical_count": critical_count,
                "warning_count": warning_count,
                "total_violations": len(violations)
            }
        }

    def _violation_to_dict(self, v: RuleViolation) -> Dict[str, Any]:
        return {
            "rule_code": v.rule_code,
            "severity": v.severity.value,
            "description": v.description,
            "expected_value": v.expected_value,
            "actual_value": v.actual_value
        }
