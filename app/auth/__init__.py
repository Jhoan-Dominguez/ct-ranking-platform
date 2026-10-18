"""Autenticación e identidad.

Módulos:
- ``service``: API pública (login, registro, 2FA, Google, cambios de cuenta).
- ``keycloak``: cliente HTTP de Keycloak (tokens y API de administración).
- ``validation``: reglas de usuario, correo institucional, nombres y contraseña.
- ``passwords``: hash bcrypt (proveedor local).
- ``errors``: excepciones con mensajes para el usuario.
- ``accounts``: ciclo de vida de la cuenta (eliminación diferida).

Este paquete reexporta la API pública para usarla como ``from app import auth`` y
``auth.login(...)``.
"""

from app.auth.errors import INVALID_LOGIN, AuthError, EmailNotVerifiedError
from app.auth.keycloak import Identity, KeycloakClient
from app.auth.passwords import check_password, hash_password
from app.auth.service import (
    TOTP_SETUP_LINK_HOURS,
    begin_login,
    change_email,
    change_names,
    change_password,
    disable_two_factor,
    google_login_enabled,
    login,
    login_with_oidc,
    register,
    request_two_factor_setup,
    resend_verification,
    set_active,
    two_factor_enabled,
    two_factor_supported,
    verify_credentials,
)
from app.auth.validation import (
    student_domain,
    student_email,
    validate_email,
    validate_names,
    validate_password,
    validate_student_email,
    validate_username,
)

__all__ = [
    "INVALID_LOGIN",
    "TOTP_SETUP_LINK_HOURS",
    "AuthError",
    "EmailNotVerifiedError",
    "Identity",
    "KeycloakClient",
    "begin_login",
    "change_email",
    "change_names",
    "change_password",
    "check_password",
    "disable_two_factor",
    "google_login_enabled",
    "hash_password",
    "login",
    "login_with_oidc",
    "register",
    "request_two_factor_setup",
    "resend_verification",
    "set_active",
    "student_domain",
    "student_email",
    "two_factor_enabled",
    "two_factor_supported",
    "validate_email",
    "validate_names",
    "validate_password",
    "validate_student_email",
    "validate_username",
    "verify_credentials",
]
