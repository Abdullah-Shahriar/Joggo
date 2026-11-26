from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "JOGGO"
    ENV: Literal["dev", "prod", "test"] = "dev"
    DATABASE_URL: str = "postgresql+psycopg://clinicshield:clinicshield@localhost:5432/clinicshield"
    JWT_SECRET: str = "dev-only-change-me-32-chars-minimum"
    FRONTEND_ORIGIN: str = "http://localhost:3000"
    BACKEND_URL: str = "http://localhost:8000"
    GOOGLE_CLIENT_ID: str = ""
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = ""
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = ""
    LLM_PROVIDER_ORDER: str = "gemini,groq"
    SPACY_MODEL: str = "en_core_web_sm"
    OCR_LANGS: str = "eng"
    DATE_ORDER: Literal["DMY", "MDY"] = "DMY"
    MAX_UPLOAD_MB: int = 10
    MAX_PDF_PAGES: int = 30
    VAULT_IDLE_MINUTES: int = 30
    VAULT_ABSOLUTE_HOURS: int = 8
    VAULT_MAX_MB: int = 300
    ADMIN_SEED_EMAIL: str = ""
    ADMIN_SEED_PASSWORD: str = ""
    AUDITOR_SEED_EMAIL: str = ""
    AUDITOR_SEED_PASSWORD: str = ""
    DOCTOR_SEED_EMAIL: str = ""
    DOCTOR_SEED_PASSWORD: str = ""

    @property
    def llm_providers(self) -> list[str]:
        return [p.strip() for p in self.LLM_PROVIDER_ORDER.split(",") if p.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
