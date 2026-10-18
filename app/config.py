"""Configuración central leída de variables de entorno (.env)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")


def _float(name: str, default: float) -> float:
    return float(os.getenv(name, default))


@dataclass(frozen=True)
class Settings:
    database_url: str
    auth_provider: str
    keycloak_url: str
    keycloak_realm: str
    keycloak_client_id: str
    keycloak_client_secret: str
    admin_username: str
    admin_email: str
    admin_password: str
    grade_min: float
    grade_max: float
    grade_passing: float
    app_url: str
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    smtp_starttls: bool
    mail_from: str
    mail_from_name: str
    # "smtp" envía correos reales; "memory" los guarda en memoria (pruebas).
    mail_backend: str
    account_deletion_days: int


def _database_url() -> str:
    if url := os.getenv("DATABASE_URL"):
        return url
    user = os.getenv("POSTGRES_USER", "ctranking")
    password = os.getenv("POSTGRES_PASSWORD", "ctranking")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    name = os.getenv("POSTGRES_DB", "ctranking")
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{name}"


@lru_cache
def get_settings() -> Settings:
    return Settings(
        database_url=_database_url(),
        auth_provider=os.getenv("AUTH_PROVIDER", "keycloak").lower(),
        keycloak_url=os.getenv("KEYCLOAK_URL", "http://localhost:8180").rstrip("/"),
        keycloak_realm=os.getenv("KEYCLOAK_REALM", "ct-ranking"),
        keycloak_client_id=os.getenv("KEYCLOAK_CLIENT_ID", "ct-ranking-app"),
        keycloak_client_secret=os.getenv("KEYCLOAK_CLIENT_SECRET", "ct-ranking-dev-secret"),
        admin_username=os.getenv("APP_ADMIN_USERNAME", "admin"),
        admin_email=os.getenv("APP_ADMIN_EMAIL", "admin@ctranking.local"),
        admin_password=os.getenv("APP_ADMIN_PASSWORD", "Admin123!"),
        grade_min=_float("GRADE_MIN", 0.0),
        grade_max=_float("GRADE_MAX", 5.0),
        grade_passing=_float("GRADE_PASSING", 3.0),
        app_url=os.getenv("APP_URL", "http://localhost:8501").rstrip("/"),
        smtp_host=os.getenv("SMTP_HOST", "localhost"),
        smtp_port=int(os.getenv("SMTP_PORT", "1025")),
        smtp_user=os.getenv("SMTP_USER", ""),
        smtp_password=os.getenv("SMTP_PASSWORD", ""),
        smtp_starttls=os.getenv("SMTP_STARTTLS", "false").lower() == "true",
        mail_from=os.getenv("MAIL_FROM", "no-reply@ctranking.local"),
        mail_from_name=os.getenv("MAIL_FROM_NAME", "CT Ranking"),
        mail_backend=os.getenv("MAIL_BACKEND", "smtp").lower(),
        account_deletion_days=int(os.getenv("ACCOUNT_DELETION_DAYS", "7")),
    )
