"""Reglas de validación de usuario, correo (dominio institucional), nombres y contraseña."""

from __future__ import annotations

import re

from app.auth.errors import AuthError
from app.core.config import get_settings

USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.-]{3,30}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
LOCAL_PART_RE = re.compile(r"^[a-z0-9](?:[a-z0-9._+-]{0,62}[a-z0-9])?$")


def validate_username(username: str) -> str:
    username = username.strip()
    if not USERNAME_RE.match(username):
        raise AuthError(
            "El usuario debe tener entre 3 y 30 caracteres: letras, números, '.', '-' o '_'."
        )
    return username


def validate_email(email: str) -> str:
    email = email.strip().lower()
    if not EMAIL_RE.match(email):
        raise AuthError("Correo electrónico inválido.")
    return email


def student_domain() -> str:
    return get_settings().student_email_domain


def student_email(local_part: str) -> str:
    """Arma el correo institucional a partir de lo que va antes de la @."""
    local = local_part.strip().lower()
    if "@" in local:
        raise AuthError(f"Escribe sólo la parte antes de @{student_domain()}.")
    if not LOCAL_PART_RE.match(local) or ".." in local:
        raise AuthError(
            "Usuario de correo inválido: usa letras, números, punto, guion o guion bajo."
        )
    return f"{local}@{student_domain()}"


def validate_student_email(email: str) -> str:
    """Los estudiantes deben usar el correo del dominio institucional."""
    email = validate_email(email)
    if not email.endswith("@" + student_domain()):
        raise AuthError(f"Debes usar tu correo institucional @{student_domain()}.")
    student_email(email.split("@", 1)[0])  # valida la parte local
    return email


def validate_names(first_name: str, last_name: str) -> tuple[str, str]:
    first_name, last_name = first_name.strip(), last_name.strip()
    if not first_name or not last_name:
        raise AuthError("Nombre y apellido son obligatorios.")
    return first_name, last_name


def validate_password(password: str) -> str:
    if len(password) < 8:
        raise AuthError("La contraseña debe tener al menos 8 caracteres.")
    if len(password.encode()) > 72:
        raise AuthError("La contraseña es demasiado larga (máx. 72 bytes).")
    if not (re.search(r"[A-Za-z]", password) and re.search(r"\d", password)):
        raise AuthError("La contraseña debe contener letras y números.")
    return password
