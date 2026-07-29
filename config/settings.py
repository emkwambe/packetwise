"""Application configuration."""
from pydantic_settings import BaseSettings
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    # App
    APP_NAME: str = "PacketWise"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"

    # Database
    # Local dev defaults to SQLite. Production sets DATABASE_URL in the
    # environment (see .env.example) to a Supabase Postgres DSN. Use the
    # psycopg2 driver — this application is synchronous (create_engine +
    # sqlalchemy.orm.Session), so an asyncpg DSN raises
    # "The asyncio extension requires an async driver to be used".
    DATABASE_URL: str = f"sqlite:///{BASE_DIR}/data/packetwise.db"

    # File Storage
    UPLOAD_DIR: Path = BASE_DIR / "data" / "uploads"
    PROCESSED_DIR: Path = BASE_DIR / "data" / "processed"
    EXCEPTIONS_DIR: Path = BASE_DIR / "data" / "exceptions"

    # OCR
    TESSERACT_CMD: str = "tesseract"
    OCR_DPI: int = 300

    # Underwriting Rules (overridable via rules.yaml)
    DTI_THRESHOLD_QM: float = 0.43          # Qualified Mortgage
    DTI_THRESHOLD_MAX: float = 0.50         # Hard ceiling
    MIN_CREDIT_SCORE: int = 620
    MAX_LTV_RATIO: float = 0.80
    MIN_RESERVE_MONTHS: int = 2

    # Processing
    MAX_FILE_SIZE_MB: int = 25
    ALLOWED_EXTENSIONS: set = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".txt"}

    # Alerting
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASS: str = ""
    UNDERWRITING_EMAIL: str = "underwriting@demo.bank"

    class Config:
        env_file = ".env"

settings = Settings()

# Ensure directories exist
for d in [settings.UPLOAD_DIR, settings.PROCESSED_DIR, settings.EXCEPTIONS_DIR]:
    d.mkdir(parents=True, exist_ok=True)
