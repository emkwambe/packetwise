import pytest
import shutil
from src.pipeline.worker import LoanPipeline
from src.core_banking.models import (
    init_db, get_db, LoanApplication, DocumentRecord,
    UnderwritingException, LoanStatus
)


TESSERACT_AVAILABLE = shutil.which("tesseract") is not None


@pytest.fixture
def pipeline():
    init_db()
    db = next(get_db())
    # Clean up any records from prior test runs so application_ids stay unique
    for model in (LoanApplication, DocumentRecord, UnderwritingException):
        db.query(model).filter(model.application_id.like("TEST-%")).delete(
            synchronize_session=False
        )
    db.commit()
    db.close()
    return LoanPipeline()


class TestCleanApproval:
    def test_clean_packet_approves(self, pipeline):
        result = pipeline.process_packet([
            "tests/fixtures/sample_w2.txt",
            "tests/fixtures/sample_app.txt",
            "tests/fixtures/sample_bank.txt"
        ], application_id="TEST-001")

        assert result.status == "approved"
        assert result.violations == []
        assert result.metrics["dti_ratio"] < 0.43
        assert result.memo_path is None


class TestFlaggedDTI:
    def test_high_dti_flags(self, pipeline):
        result = pipeline.process_packet([
            "tests/fixtures/sample_w2.txt",
            "tests/fixtures/sample_app_flagged.txt",
            "tests/fixtures/sample_bank_flagged.txt"
        ], application_id="TEST-002")

        assert result.status == "flagged"
        assert any(v["rule_code"] == "DTI_EXCEEDS_QM" for v in result.violations)
        assert result.memo_path is not None


class TestRejected:
    def test_critical_rejects(self, pipeline):
        result = pipeline.process_packet([
            "tests/fixtures/sample_w2.txt",
            "tests/fixtures/sample_app_rejected.txt",
            "tests/fixtures/sample_bank_rejected.txt"
        ], application_id="TEST-003")

        assert result.status == "rejected"
        assert any(v["severity"] == "critical" for v in result.violations)
        assert result.memo_path is not None


class TestMissingDocument:
    def test_missing_w2_rejects(self, pipeline):
        result = pipeline.process_packet([
            "tests/fixtures/sample_app.txt",
            "tests/fixtures/sample_bank.txt"
        ], application_id="TEST-004")

        assert result.status == "rejected"
        assert any(v["rule_code"] == "MISSING_REQUIRED_DOC" for v in result.violations)


class TestOCRImage:
    @pytest.mark.skipif(not TESSERACT_AVAILABLE, reason="Tesseract not installed on host")
    def test_image_w2_extracts(self, pipeline):
        result = pipeline.process_packet([
            "tests/fixtures/sample_w2_image.png",
            "tests/fixtures/sample_app_image.txt",
            "tests/fixtures/sample_bank.txt"
        ], application_id="TEST-005")

        assert result.status == "approved"
        assert result.confidence < 1.0  # Image penalty applied
        assert result.metrics["verified_income_annual"] == 85000.0
