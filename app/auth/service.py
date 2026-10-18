"""Autenticación básica con dos proveedores intercambiables (AUTH_PROVIDER):

- ``keycloak``: el usuario y la contraseña se validan contra Keycloak con el flujo
  *Resource Owner Password Credentials* (Direct Access Grants). El alta de usuarios y el cambio de
  contraseña/correo se hacen con la API de administración usando la cuenta de servicio del
  cliente ``ct-ranking-app``. En la BD de la app sólo se guarda el perfil (``keycloak_id``).
- ``local``: contraseñas con bcrypt en la tabla ``users`` (útil para tests o sin Docker).
"""

from __future__ import annotations

import contextlib
from collections.abc import Mapping
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.auth.errors import AuthError
from app.auth.keycloak import Identity, KeycloakClient
from app.auth.passwords import check_password, hash_password
from app.auth.validation import (
    validate_email,
    validate_names,
    validate_password,
    validate_student_email,
    validate_username,
)
from app.core.config import get_settings
from app.database.models import Role, User


def _uses_keycloak() -> bool:
    return get_settings().auth_provider == "keycloak"


# --------------------------------------------------------------------------- API pública


def _find_by_login(session: Session, login: str) -> User | None:
    login = login.strip().lower()
    return session.scalar(
        select(User).where(or_(func.lower(User.username) == login, User.email == login))
    )


def _ensure_unique(session: Session, username: str, email: str, exclude_id: int | None = None):
    stmt = select(User).where(
        or_(func.lower(User.username) == username.lower(), User.email == email)
    )
    if exclude_id is not None:
        stmt = stmt.where(User.id != exclude_id)
    if session.scalar(stmt) is not None:
        raise AuthError("El usuario o el correo ya están registrados.")


def _sync_keycloak_user(session: Session, identity: Identity) -> User:
    user = session.scalar(select(User).where(User.keycloak_id == identity.external_id))
    if user is None:
        user = session.scalar(
            select(User).where(func.lower(User.username) == identity.username.lower())
        )
    if user is None:
        # Primer login de un usuario que sólo existe en Keycloak (creado en su consola o con
        # Google). Los defaults de SQLAlchemy se aplican al insertar, así que se fijan aquí y se
        # hace flush para que el resto de la función (p. ej. is_active) vea valores reales.
        user = User(
            username=identity.username,
            email=identity.email or f"{identity.username}@sin-correo.local",
            role=Role.STUDENT,
            is_active=True,
        )
        session.add(user)
        session.flush()
    user.keycloak_id = identity.external_id
    if identity.email:
        user.email = identity.email
    if not user.full_name:
        user.first_name, user.last_name = identity.first_name, identity.last_name
    user.email_verified = identity.email_verified
    # Keycloak puede otorgar el rol admin; las promociones hechas desde el panel se conservan.
    if Role.ADMIN in identity.roles:
        user.role = Role.ADMIN
    return user


def login(session: Session, username: str, password: str, otp: str | None = None) -> User:
    """Inicia sesión. ``otp`` es el código de la app autenticadora si el usuario tiene 2FA.

    Una cuenta con eliminación programada sí puede iniciar sesión (para poder cancelarla); la
    interfaz se encarga de restringir lo que ve."""
    if not username.strip() or not password:
        raise AuthError("Ingresa usuario y contraseña.")
    if _uses_keycloak():
        identity = KeycloakClient().password_login(username, password, otp)
        user = _sync_keycloak_user(session, identity)
    else:
        user = _find_by_login(session, username)
        if user is None or not check_password(password, user.password_hash):
            raise AuthError("Usuario o contraseña incorrectos.")
    if not user.is_active:
        raise AuthError("La cuenta está deshabilitada. Contacta al administrador.")
    user.last_login = datetime.now(UTC)
    session.flush()
    return user


def register(
    session: Session,
    *,
    username: str,
    email: str,
    password: str,
    first_name: str,
    last_name: str,
    role: Role = Role.STUDENT,
    require_verification: bool = True,
) -> User:
    """Crea la cuenta. Con Keycloak y ``require_verification`` (por defecto) la cuenta queda
    pendiente de activación y Keycloak envía el enlace de verificación al correo. Con el
    proveedor local la cuenta queda activa de inmediato."""
    username = validate_username(username)
    email = validate_email(email) if role == Role.ADMIN else validate_student_email(email)
    first_name, last_name = validate_names(first_name, last_name)
    validate_password(password)
    _ensure_unique(session, username, email)
    user = User(
        username=username, email=email, first_name=first_name, last_name=last_name, role=role
    )
    if _uses_keycloak():
        client = KeycloakClient()
        user.keycloak_id = client.create_user(
            username, email, password, first_name, last_name, verified=not require_verification
        )
        user.email_verified = not require_verification
        if require_verification:
            # Si el correo falla la cuenta no se revierte: el enlace se puede reenviar desde
            # la pantalla de login.
            with contextlib.suppress(AuthError):
                client.send_verify_email(user.keycloak_id)
    else:
        user.password_hash = hash_password(password)
    session.add(user)
    session.flush()
    return user


def google_login_enabled() -> bool:
    """«Continuar con Google» sólo se ofrece con Keycloak y credenciales de Google."""
    return _uses_keycloak() and bool(get_settings().google_client_id)


def login_with_oidc(session: Session, claims: Mapping[str, object]) -> User:
    """Inicia sesión con los datos del token OIDC de Keycloak (``st.user``) tras volver de
    Google. Keycloak ya restringe las cuentas al dominio institucional (``hostedDomain``); aquí se
    vuelve a validar como segunda capa."""
    email = str(claims.get("email") or "").strip().lower()
    if not claims.get("sub") or not email:
        raise AuthError("La respuesta de inicio de sesión no incluye un correo.")
    if not claims.get("email_verified"):
        raise AuthError("Google no confirmó tu correo electrónico.")
    validate_student_email(email)
    identity = Identity(
        external_id=str(claims["sub"]),
        username=str(claims.get("preferred_username") or email.split("@", 1)[0]),
        email=email,
        first_name=str(claims.get("given_name") or ""),
        last_name=str(claims.get("family_name") or ""),
        email_verified=True,
    )
    user = _sync_keycloak_user(session, identity)
    if not user.is_active:
        raise AuthError("La cuenta está deshabilitada. Contacta al administrador.")
    user.last_login = datetime.now(UTC)
    session.flush()
    return user


def resend_verification(login: str) -> None:
    """Reenvía el enlace de activación. No revela si la cuenta existe."""
    if not _uses_keycloak() or not login.strip():
        return
    client = KeycloakClient()
    user = client.find_user(login)
    if user and "VERIFY_EMAIL" in user.get("requiredActions", []):
        client.send_verify_email(user["id"])


def verify_credentials(user: User, password: str, otp: str | None = None) -> None:
    """Re-autenticación para acciones sensibles (eliminar la cuenta, desactivar 2FA…)."""
    if _uses_keycloak():
        KeycloakClient().password_login(user.username, password, otp)
    elif not check_password(password, user.password_hash):
        raise AuthError("La contraseña no es correcta.")


# --------------------------------------------------------------------------- 2FA (TOTP)

TOTP_SETUP_LINK_HOURS = 12


def two_factor_supported() -> bool:
    return _uses_keycloak()


def two_factor_enabled(user: User) -> bool:
    if not _uses_keycloak() or not user.keycloak_id:
        return False
    return bool(KeycloakClient().otp_credentials(user.keycloak_id))


def request_two_factor_setup(user: User) -> None:
    """Keycloak envía al correo un enlace a su página de configuración, que muestra el QR para
    escanear con Google Authenticator, Microsoft Authenticator o FreeOTP."""
    if not _uses_keycloak() or not user.keycloak_id:
        raise AuthError("El 2FA sólo está disponible con Keycloak (AUTH_PROVIDER=keycloak).")
    KeycloakClient().send_actions_email(
        user.keycloak_id, ["CONFIGURE_TOTP"], TOTP_SETUP_LINK_HOURS * 3600
    )


def disable_two_factor(user: User, password: str, otp: str) -> None:
    if not _uses_keycloak() or not user.keycloak_id:
        raise AuthError("El 2FA sólo está disponible con Keycloak.")
    if not otp.strip():
        raise AuthError("Escribe el código actual de tu app autenticadora.")
    verify_credentials(user, password, otp)
    client = KeycloakClient()
    for credential in client.otp_credentials(user.keycloak_id):
        client.delete_credential(user.keycloak_id, credential["id"])


def change_password(
    session: Session, user: User, current: str, new: str, otp: str | None = None
) -> None:
    validate_password(new)
    if _uses_keycloak():
        client = KeycloakClient()
        client.password_login(user.username, current, otp)  # verifica la contraseña actual
        if user.keycloak_id is None:
            raise AuthError("El usuario no está vinculado a Keycloak.")
        client.reset_password(user.keycloak_id, new)
    else:
        if not check_password(current, user.password_hash):
            raise AuthError("La contraseña actual no es correcta.")
        user.password_hash = hash_password(new)


def change_email(session: Session, user: User, email: str) -> None:
    email = validate_email(email) if user.is_admin else validate_student_email(email)
    if email == user.email:
        return
    _ensure_unique(session, user.username, email, exclude_id=user.id)
    if _uses_keycloak() and user.keycloak_id:
        KeycloakClient().update_user(user.keycloak_id, email=email, emailVerified=True)
    user.email = email


def change_names(session: Session, user: User, first_name: str, last_name: str) -> None:
    first_name, last_name = validate_names(first_name, last_name)
    if (first_name, last_name) == (user.first_name, user.last_name):
        return
    if _uses_keycloak() and user.keycloak_id:
        KeycloakClient().update_user(user.keycloak_id, firstName=first_name, lastName=last_name)
    user.first_name, user.last_name = first_name, last_name


def set_active(session: Session, user: User, active: bool) -> None:
    if _uses_keycloak() and user.keycloak_id:
        KeycloakClient().set_enabled(user.keycloak_id, active)
    user.is_active = active
