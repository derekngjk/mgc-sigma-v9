"""Centralized configuration: environment values and filesystem path anchors."""

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR: Path = Path(__file__).resolve().parent.parent
MOCK_DATA_DIR: Path = BACKEND_DIR / "mock_data"
SYNTHEA_DIR: Path = BACKEND_DIR.parent / "SyntheticPatientRecords"

load_dotenv(BACKEND_DIR / ".env")


class Settings:
    """Reads each environment variable live on access."""

    @property
    def supabase_url(self) -> str:
        return os.getenv("SUPABASE_URL", "")

    @property
    def supabase_key(self) -> str:
        return os.getenv("SUPABASE_KEY", "")

    @property
    def supabase_db_url(self) -> str:
        return os.getenv("SUPABASE_DB_URL", "")

    @property
    def frontend_origin(self) -> str:
        return os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")

    @property
    def log_level(self) -> str:
        return os.getenv("LOG_LEVEL", "INFO").upper()

    @property
    def fhir_base_url(self) -> str:
        return os.getenv(
            "FHIR_BASE_URL", "https://api.healthx.sg/fhir/r4b/your-tenant-id"
        )

    @property
    def healthx_api_key(self) -> str:
        return os.getenv("HEALTHX_API_KEY", "")

    @property
    def llm_provider(self) -> str:
        return os.getenv("LLM_PROVIDER", "anthropic")

    @property
    def anthropic_api_key(self) -> str:
        return os.getenv("ANTHROPIC_API_KEY", "")

    @property
    def openai_api_key(self) -> str:
        return os.getenv("OPENAI_API_KEY", "")

    @property
    def gemini_api_key(self) -> str:
        return os.getenv("GEMINI_API_KEY", "")

    @property
    def image_provider(self) -> str:
        return os.getenv("IMAGE_PROVIDER", "openai")


settings = Settings()
