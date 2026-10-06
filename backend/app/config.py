import json
from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://exam:exam@localhost:5432/exam"
    jwt_secret: str = "change-me-in-production-use-32+-random-bytes"
    jwt_expiry_minutes: int = 60 * 24 * 7
    storage_dir: str = "./storage"
    # NoDecode: take the raw env string so `_split_origins` can accept a plain comma-separated list.
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]
    # Run an extraction worker thread inside the API process (local dev). Use `python -m app.worker` in prod.
    embedded_worker: bool = False

    # AI extraction
    extraction_provider: str = "gemini"  # "gemini" | "heuristic"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    # A stronger model used to re-check questions the first pass flagged as doubtful.
    gemini_verify_model: str = "gemini-2.5-pro"
    # Tried in order when a model is rate-limited or overloaded (429/503). Free-tier quotas are
    # per model, so a chain of models multiplies the daily request budget.
    gemini_fallback_models: list[str] = []
    gemini_timeout_seconds: int = 240
    pages_per_chunk: int = 2
    extraction_concurrency: int = 4
    max_verify_calls: int = 40
    # Targeted re-reads of pages where the numbering shows questions are missing.
    max_recover_calls: int = 6
    # For bilingual papers, which language version of each question to keep.
    extraction_language: str = "English"
    review_confidence_threshold: float = 0.8
    max_upload_mb: int = 80

    # Bootstrap admin, created on startup if no admin exists.
    admin_email: str = "admin@example.com"
    admin_password: str = "admin12345"

    @field_validator("database_url")
    @classmethod
    def _use_psycopg3(cls, value: str) -> str:
        """Managed hosts (Render, Heroku, Neon…) hand out `postgres://` / `postgresql://` URLs.
        SQLAlchemy reads those as psycopg2, which this project does not install: pin them to psycopg 3."""
        for prefix in ("postgres://", "postgresql://"):
            if value.startswith(prefix):
                return "postgresql+psycopg://" + value[len(prefix) :]
        return value

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value):
        """Accept a comma-separated list as well as JSON, so a hosting dashboard can take
        `https://app.vercel.app,https://www.example.com` without the JSON brackets."""
        if not isinstance(value, str):
            return value
        value = value.strip()
        if value.startswith("["):
            return json.loads(value)
        return [origin.strip() for origin in value.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
