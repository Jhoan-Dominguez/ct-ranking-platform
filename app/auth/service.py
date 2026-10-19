"""Autenticación básica con dos proveedores intercambiables (AUTH_PROVIDER):

- ``keycloak``: el usuario y la contraseña se validan contra Keycloak con el flujo
  *Resource Owner Password Credentials* (Direct Access Grants). El alta de usuarios y el cambio de
  contraseña/correo se hacen con la API de administración usando la cuenta de servicio del
  cliente ``ct-ranking-app``. En la BD de la app sólo se guarda el perfil (``keycloak_id``).
- ``local``: contraseñas con bcrypt en la tabla ``users`` (útil para tests o sin Docker).
"""

from __future__ import annotations

import contextlib
import re
from collections.abc import Mapping
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.auth.errors import INVALID_LOGIN, AccountNotFoundError, AuthError
from app.auth.keycloak import Identity, KeycloakClient
from app.auth.passwords import check_password, hash_password
from app.auth.validation import (
    validate_email,
    validate_names,
    validate_password,
    validate_student_email,
    validate_username,
)
from app.core import ratelimit
from app.core.config import get_settings
from app.database.models import Role, User

# Proveedor local: intentos fallidos permitidos por usuario antes de bloquear un rato.
LOCAL_MAX_FAILURES = 5
LOCAL_LOCK_S = 300
# Espera mínima entre dos correos de Keycloak (activación o configuración del 2FA).
EMAIL_COOLDOWN_S = 60


def _uses_keycloak() -> bool:
    return get_settings().auth_provider == "keycloak"


# --------------------------------------------------------------------------- API pública


def _find_by_login(session: Session, login: str) -> User | None:
    login = login.strip().lower()
    return session.scalar(
        select(User).where(or_(func.lower(User.username) == login, User.email == login))
    )


def _ensure_unique(session: Session, username: str, email: str) -> None:
    stmt = select(User).where(
        or_(func.lower(User.username) == username.lower(), User.email == email)
    )
    if session.scalar(stmt) is not None:
        raise AuthError("El usuario o el correo ya están registrados.")


def _available_username(session: Session, wanted: str) -> str:
    """Un username libre a partir de ``wanted`` (agrega un número si ya existe)."""
    base = re.sub(r"[^a-zA-Z0-9_.-]", "", wanted)[:30]
    base = base if len(base) >= 3 else f"usuario{base}"
    candidate, n = base, 2
    while session.scalar(select(User.id).where(func.lower(User.username) == candidate.lower())):
        suffix = str(n)
        candidate, n = base[: 30 - len(suffix)] + suffix, n + 1
    return candidate


def _sync_keycloak_user(session: Session, identity: Identity, user: User | None = None) -> User:
    """Busca (o crea) la fila local del usuario de Keycloak y sincroniza sus datos.

    - Se busca por ``keycloak_id``. Si no aparece, sólo se vincula una cuenta local **sin**
      ``keycloak_id`` y con el mismo correo verificado (p. ej. el admin que crea ``init_db``).
      Nunca se vincula por username: con Google se deriva del correo y no prueba identidad.
    - El rol se administra en la app (*Panel → Usuarios*). El rol ``admin`` de Keycloak sólo se
      toma al crear la fila, así una degradación hecha desde el panel no se revierte.
    """
    if user is None:
        user = session.scalar(select(User).where(User.keycloak_id == identity.external_id))
    if user is None and identity.email and identity.email_verified:
        user = session.scalar(
            select(User).where(User.keycloak_id.is_(None), User.email == identity.email.lower())
        )
    if user is None:
        # Primer login de un usuario que sólo existe en Keycloak (creado en su consola o con
        # Google). Los defaults de SQLAlchemy se aplican al insertar, así que se fijan aquí y se
        # hace flush para que el resto de la función (p. ej. is_active) vea valores reales.
        user = User(
            username=_available_username(session, identity.username),
            email=identity.email.lower() or f"{identity.username}@sin-correo.local",
            role=Role.ADMIN if Role.ADMIN in identity.roles else Role.STUDENT,
            is_active=True,
        )
        session.add(user)
        session.flush()
    user.keycloak_id = identity.external_id
    if identity.email:
        user.email = identity.email.lower()
    if not user.full_name:
        user.first_name, user.last_name = identity.first_name, identity.last_name
    user.email_verified = identity.email_verified
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
        key = f"local-login:{username.strip().lower()}"
        ratelimit.check(
            key,
            limit=LOCAL_MAX_FAILURES,
            window_s=LOCAL_LOCK_S,
            message="Demasiados intentos fallidos. Espera unos minutos e inténtalo de nuevo.",
            error=AuthError,
        )
        user = _find_by_login(session, username)
        if user is None or not check_password(password, user.password_hash):
            ratelimit.record(key)
            raise AuthError("Usuario o contraseña incorrectos.")
        ratelimit.reset(key)
    if not user.is_active:
        raise AuthError("La cuenta está deshabilitada. Contacta al administrador.")
    user.last_login = datetime.now(UTC)
    session.flush()
    return user


def begin_login(session: Session, username: str, password: str) -> User | None:
    """Paso 1 del login: verifica usuario y contraseña.

    - Si la contraseña es incorrecta (o la cuenta no está activada), lanza ``AuthError``.
    - Si es correcta y la cuenta **no** tiene 2FA, completa el login y devuelve el usuario.
    - Si es correcta y la cuenta tiene 2FA, devuelve ``None``: la UI debe pedir el código y
      llamar a ``login(session, username, password, otp)`` (paso 2).
    """
    if not username.strip() or not password:
        raise AuthError("Ingresa usuario y contraseña.")
    if not _uses_keycloak():
        return login(session, username, password)
    client = KeycloakClient()
    try:
        identity = client.password_login(username, password, password_only=True)
    except AuthError as exc:
        if str(exc) == INVALID_LOGIN:  # en este paso no interviene ningún código
            raise AuthError("Usuario o contraseña incorrectos.") from exc
        raise
    if client.otp_credentials(identity.external_id):
        return None
    return login(session, username, password)


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
    if not _uses_keycloak():
        user.password_hash = hash_password(password)
        session.add(user)
        session.flush()
        return user
    client = KeycloakClient()
    user.keycloak_id = client.create_user(
        username, email, password, first_name, last_name, verified=not require_verification
    )
    user.email_verified = not require_verification
    session.add(user)
    try:
        session.flush()
    except Exception:
        # La fila local no se pudo crear: se deshace también el usuario de Keycloak para no
        # dejar una cuenta huérfana que bloquee el username o el correo.
        with contextlib.suppress(AuthError):
            client.delete_user(user.keycloak_id)
        raise
    if require_verification:
        # Si el correo falla la cuenta no se revierte: el enlace se puede reenviar desde
        # la pantalla de login.
        with contextlib.suppress(AuthError):
            client.send_verify_email(user.keycloak_id)
    return user


def google_login_enabled() -> bool:
    """«Continuar con Google» sólo se ofrece con Keycloak y credenciales de Google."""
    return _uses_keycloak() and bool(get_settings().google_client_id)


def login_with_oidc(
    session: Session, claims: Mapping[str, object], *, allow_create: bool = False
) -> tuple[User, bool]:
    """Inicia sesión (o crea la cuenta) con los datos del token OIDC de Keycloak (``st.user``)
    tras volver de Google. Devuelve ``(usuario, creado)``.

    - ``allow_create=False`` («Iniciar sesión con Google»): la cuenta debe existir en la
      plataforma, buscada por su identificador de Keycloak o por su correo. Si no existe, lanza
      ``AccountNotFoundError`` y borra el usuario que Keycloak creó automáticamente al volver de
      Google, para no dejar cuentas huérfanas.
    - ``allow_create=True`` («Crear cuenta con Google»): crea la cuenta si no existe. Si ya
      existía, simplemente inicia sesión.

    Keycloak ya restringe las cuentas al dominio institucional (``hostedDomain``); aquí se vuelve
    a validar como segunda capa."""
    email = str(claims.get("email") or "").strip().lower()
    if not claims.get("sub") or not email:
        raise AuthError("La respuesta de inicio de sesión no incluye un correo.")
    if not claims.get("email_verified"):
        raise AuthError("Google no confirmó tu correo electrónico.")
    external_id = str(claims["sub"])
    existing = session.scalar(select(User).where(User.keycloak_id == external_id))
    if existing is None:
        existing = session.scalar(select(User).where(User.email == email))
        if existing is not None and existing.keycloak_id not in (None, external_id):
            raise AuthError(
                "Ese correo ya está vinculado a otra cuenta de la plataforma. "
                "Contacta al administrador."
            )
    # Los administradores están exentos del dominio institucional, igual que en register().
    if existing is None or not existing.is_admin:
        validate_student_email(email)
    if existing is None and not allow_create:
        if _uses_keycloak():
            with contextlib.suppress(AuthError):
                KeycloakClient().delete_broker_only_user(external_id)
        raise AccountNotFoundError(email)
    identity = Identity(
        external_id=external_id,
        username=str(claims.get("preferred_username") or email.split("@", 1)[0]),
        email=email,
        first_name=str(claims.get("given_name") or ""),
        last_name=str(claims.get("family_name") or ""),
        email_verified=True,
    )
    user = _sync_keycloak_user(session, identity, existing)
    if not user.is_active:
        raise AuthError("La cuenta está deshabilitada. Contacta al administrador.")
    user.last_login = datetime.now(UTC)
    session.flush()
    return user, existing is None


def resend_verification(login: str) -> None:
    """Reenvía el enlace de activación. No revela si la cuenta existe."""
    if not _uses_keycloak() or not login.strip():
        return
    ratelimit.hit(
        f"resend:{login.strip().lower()}",
        limit=1,
        window_s=EMAIL_COOLDOWN_S,
        message="Ya enviamos un enlace hace un momento. Espera un minuto antes de pedir otro.",
        error=AuthError,
    )
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
    ratelimit.hit(
        f"totp-setup:{user.id}",
        limit=1,
        window_s=EMAIL_COOLDOWN_S,
        message="Ya te enviamos el enlace hace un momento. Espera un minuto antes de pedir otro.",
        error=AuthError,
    )
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


def validate_new_email(session: Session, user: User, email: str) -> str:
    """Valida un correo nuevo para ``user`` (formato, dominio institucional salvo admins, distinto
    del actual y libre). Devuelve el correo normalizado. No cambia nada: el cambio lo hace
    ``accounts.request_email_change`` / ``confirm_email_change`` tras verificar el correo."""
    email = validate_email(email) if user.is_admin else validate_student_email(email)
    if email == user.email:
        raise AuthError("Ese ya es tu correo actual.")
    if session.scalar(select(User.id).where(User.email == email, User.id != user.id)):
        raise AuthError("Ese correo ya está registrado.")
    return email


def apply_verified_email(session: Session, user: User, email: str) -> None:
    """Guarda un correo **cuya posesión ya se comprobó** (código enviado a ese correo) y lo marca
    como verificado en Keycloak y en la app. No llamar sin esa verificación."""
    if _uses_keycloak() and user.keycloak_id:
        KeycloakClient().update_user(user.keycloak_id, email=email, emailVerified=True)
    user.email = email
    user.email_verified = True


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
