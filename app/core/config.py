"""Configuración central leída de variables de entorno (.env)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[2]  # app/core/config.py → raíz del proyecto
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
    # Cliente que sólo verifica usuario y contraseña (paso 1 del login con 2FA).
    keycloak_pwcheck_client_id: str
    keycloak_pwcheck_client_secret: str
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
    # Dominio obligatorio del correo de los estudiantes (los administradores están exentos).
    student_email_domain: str
    # Inicio de sesión con Google (vía Keycloak). Vacío = deshabilitado.
    google_client_id: str
    google_client_secret: str
    # Secreto para firmar la cookie de sesión de st.login (OIDC).
    auth_cookie_secret: str
    # Clave HMAC de los códigos enviados por correo. Vacía = se deriva de los secretos de Keycloak
    # (sólo aceptable en desarrollo).
    app_secret_key: str
    # Horas que dura una sesión iniciada con usuario y contraseña (0 = sin límite).
    session_ttl_hours: float


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
        keycloak_pwcheck_client_id=os.getenv("KEYCLOAK_PWCHECK_CLIENT_ID", "ct-ranking-pwcheck"),
        keycloak_pwcheck_client_secret=os.getenv(
            "KEYCLOAK_PWCHECK_CLIENT_SECRET", "ct-ranking-pwcheck-dev-secret"
        ),
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
        student_email_domain=os.getenv("STUDENT_EMAIL_DOMAIN", "estudiantes.areandina.edu.co")
        .strip()
        .lstrip("@")
        .lower(),
        google_client_id=os.getenv("GOOGLE_CLIENT_ID", "").strip(),
        google_client_secret=os.getenv("GOOGLE_CLIENT_SECRET", "").strip(),
        auth_cookie_secret=os.getenv("AUTH_COOKIE_SECRET", "").strip(),
        app_secret_key=os.getenv("APP_SECRET_KEY", "").strip(),
        session_ttl_hours=_float("SESSION_TTL_HOURS", 12.0),
    )
