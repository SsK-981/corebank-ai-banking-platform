"""Centralized, environment-driven application configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_env: str
    database_url: str
    cors_origins: tuple[str, ...]
    auth_mode: str
    jwt_secret: str
    jwt_algorithm: str
    jwt_issuer: str | None
    jwt_audience: str | None
    jwt_jwks_url: str | None
    access_token_minutes: int
    banking_data_source: str
    corebank_base_url: str
    corebank_timeout_seconds: float
    corebank_fallback_to_local: bool
    corebank_service_token: str
    corebank_customer_emails: dict[str, str]
    llm_provider: str
    llm_model: str
    llm_base_url: str | None
    llm_api_key: str
    llm_timeout_seconds: float
    llm_polish_responses: bool
    seed_demo_data: bool

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    def validate(self) -> None:
        if self.auth_mode not in {"disabled", "development", "jwt"}:
            raise RuntimeError("AUTH_MODE must be disabled, development, or jwt")
        if self.is_production and self.auth_mode != "jwt":
            raise RuntimeError("Production requires AUTH_MODE=jwt")
        if self.is_production and self.seed_demo_data:
            raise RuntimeError("Production cannot enable SEED_DEMO_DATA")
        if self.auth_mode in {"development", "jwt"} and not self.jwt_jwks_url:
            if len(self.jwt_secret) < 32:
                raise RuntimeError("JWT_SECRET must contain at least 32 characters")
        if self.banking_data_source not in {"local", "corebank"}:
            raise RuntimeError("BANKING_DATA_SOURCE must be local or corebank")
        if self.banking_data_source == "corebank" and len(self.corebank_service_token) < 32:
            raise RuntimeError("COREBANK_SERVICE_TOKEN must contain at least 32 characters")

    def corebank_email_for(self, user_id: str | None) -> str | None:
        if not user_id:
            return None
        return self.corebank_customer_emails.get(user_id.upper())


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    from backend.database_path import default_sqlite_url

    origins = os.getenv("CORS_ORIGINS", "http://localhost:8501,http://127.0.0.1:8501")
    settings = Settings(
        app_name=os.getenv("APP_NAME", "Fintech AI Agent API"),
        app_env=os.getenv("APP_ENV", "development").strip().lower(),
        database_url=os.getenv("DATABASE_URL", default_sqlite_url()),
        cors_origins=tuple(origin.strip() for origin in origins.split(",") if origin.strip()),
        auth_mode=os.getenv("AUTH_MODE", "development").strip().lower(),
        jwt_secret=os.getenv("JWT_SECRET", "local-development-secret-change-before-production"),
        jwt_algorithm=os.getenv("JWT_ALGORITHM", "HS256"),
        jwt_issuer=os.getenv("JWT_ISSUER") or None,
        jwt_audience=os.getenv("JWT_AUDIENCE") or None,
        jwt_jwks_url=os.getenv("JWT_JWKS_URL") or None,
        access_token_minutes=int(os.getenv("ACCESS_TOKEN_MINUTES", "60")),
        banking_data_source=os.getenv("BANKING_DATA_SOURCE", "local").strip().lower(),
        corebank_base_url=os.getenv("COREBANK_BASE_URL", "http://127.0.0.1:8080").rstrip("/"),
        corebank_timeout_seconds=float(os.getenv("COREBANK_TIMEOUT_SECONDS", "8")),
        corebank_fallback_to_local=_as_bool(os.getenv("COREBANK_FALLBACK_TO_LOCAL"), default=True),
        corebank_service_token=os.getenv(
            "COREBANK_SERVICE_TOKEN", "local-corebank-service-token-change-me"
        ),
        corebank_customer_emails={
            user_id: email
            for user_id, email in (
                (
                    "U001",
                    os.getenv("COREBANK_USER_U001_EMAIL", "rahul@example.com"),
                ),
                (
                    "U002",
                    os.getenv("COREBANK_USER_U002_EMAIL", "amit@example.com"),
                ),
                (
                    "U003",
                    os.getenv("COREBANK_USER_U003_EMAIL", "neha@example.com"),
                ),
            )
            if email
        },
        llm_provider=os.getenv("LLM_PROVIDER", "local").strip().lower(),
        llm_model=os.getenv("LLM_MODEL", os.getenv("OPENAI_MODEL", "deepseek-v4-flash")),
        llm_base_url=os.getenv("LLM_BASE_URL") or None,
        llm_api_key=os.getenv("LLM_API_KEY", os.getenv("OPENAI_API_KEY", "")).strip(),
        llm_timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS", "12")),
        llm_polish_responses=_as_bool(os.getenv("LLM_POLISH_RESPONSES"), default=True),
        seed_demo_data=_as_bool(os.getenv("SEED_DEMO_DATA"), default=True),
    )
    settings.validate()
    return settings
