"""Autenticación básica con dos proveedores intercambiables (AUTH_PROVIDER):

- ``keycloak``: el usuario y la contraseña se validan contra Keycloak con el flujo
  *Resource Owner Password Credentials* (Direct Access Grants). El alta de usuarios y el cambio de
  contraseña/correo se hacen con la API de administración usando la cuenta de servicio del
  cliente ``ct-ranking-app``. En la BD de la app sólo se guarda el perfil (``keycloak_id``).
- ``local``: contraseñas con bcrypt en la tabla ``users`` (útil para tests o sin Docker).
"""

from __future__ import annotations

import base64
import contextlib
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

import bcrypt
import requests
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Role, User

USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.-]{3,30}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
TIMEOUT = 10


class AuthError(Exception):
    """Error con mensaje apto para mostrar al usuario."""


class EmailNotVerifiedError(AuthError):
    """Credenciales correctas, pero la cuenta aún no se activó con el enlace del correo."""

    def __init__(self, login: str) -> None:
        super().__init__(
            "Tu cuenta aún no está activada. Abre el enlace que te enviamos por correo "
            "(revisa también la carpeta de spam)."
        )
        self.login = login


INVALID_LOGIN = "Usuario, contraseña o código de verificación incorrectos."


# --------------------------------------------------------------------------- validaciones


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


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def check_password(password: str, hashed: str | None) -> bool:
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        return False


# --------------------------------------------------------------------------- Keycloak


@dataclass
class Identity:
    external_id: str
    username: str
    email: str
    first_name: str = ""
    last_name: str = ""
    email_verified: bool = True
    roles: set[str] = field(default_factory=set)


def _decode_jwt_payload(token: str) -> dict:
    """Decodifica el payload del JWT. El token llega directamente de Keycloak por el canal
    backend, por lo que no se re-verifica la firma aquí."""
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))


class KeycloakClient:
    def __init__(self) -> None:
        s = get_settings()
        self.base = s.keycloak_url
        self.realm = s.keycloak_realm
        self.client_id = s.keycloak_client_id
        self.client_secret = s.keycloak_client_secret

    @property
    def _token_url(self) -> str:
        return f"{self.base}/realms/{self.realm}/protocol/openid-connect/token"

    @property
    def _admin_url(self) -> str:
        return f"{self.base}/admin/realms/{self.realm}"

    def _post_token(self, data: dict) -> requests.Response:
        try:
            return requests.post(
                self._token_url,
                data={"client_id": self.client_id, "client_secret": self.client_secret, **data},
                timeout=TIMEOUT,
            )
        except requests.RequestException as exc:
            raise AuthError(
                "No fue posible contactar el servidor de autenticación (Keycloak). "
                "¿Ejecutaste `make up`?"
            ) from exc

    def password_login(self, username: str, password: str, otp: str | None = None) -> Identity:
        """Login con usuario y contraseña (flujo "direct grant"). Si el usuario tiene 2FA, el
        flujo del realm exige además el código TOTP en el parámetro ``otp``."""
        data = {"grant_type": "password", "username": username, "password": password}
        if otp:
            data["otp"] = otp.strip().replace(" ", "")
        resp = self._post_token({**data, "scope": "openid"})
        if resp.status_code in (400, 401):
            description = resp.json().get("error_description", "").lower()
            if "disabled" in description:
                raise AuthError("La cuenta está deshabilitada.")
            if "not fully set up" in description:
                # Sólo ocurre con la contraseña correcta: falta una acción requerida.
                if self._pending_email_verification(username):
                    raise EmailNotVerifiedError(username)
                raise AuthError("La cuenta tiene acciones pendientes. Contacta al administrador.")
            # Keycloak responde igual ante contraseña o código incorrecto, código faltante y
            # bloqueo temporal por fuerza bruta; este último sí se puede consultar aparte.
            if self._temporarily_locked(username):
                raise AuthError(
                    "Demasiados intentos fallidos: la cuenta está bloqueada temporalmente. "
                    "Espera un minuto e inténtalo de nuevo."
                )
            raise AuthError(INVALID_LOGIN)
        resp.raise_for_status()
        claims = _decode_jwt_payload(resp.json()["access_token"])
        return Identity(
            external_id=claims["sub"],
            username=claims.get("preferred_username", username),
            email=claims.get("email", ""),
            first_name=claims.get("given_name", ""),
            last_name=claims.get("family_name", ""),
            email_verified=bool(claims.get("email_verified", True)),
            roles=set(claims.get("realm_access", {}).get("roles", [])),
        )

    # ---------------------------------------------------------------- consultas de usuarios

    def find_user(self, login: str) -> dict | None:
        """Busca un usuario por username o correo (coincidencia exacta)."""
        key = "email" if "@" in login else "username"
        resp = self._request("GET", "/users", params={key: login.strip(), "exact": "true"})
        resp.raise_for_status()
        users = resp.json()
        return users[0] if users else None

    def _pending_email_verification(self, login: str) -> bool:
        user = self.find_user(login)
        return bool(user and "VERIFY_EMAIL" in user.get("requiredActions", []))

    def _temporarily_locked(self, login: str) -> bool:
        try:
            user = self.find_user(login)
            if not user:
                return False
            resp = self._request("GET", f"/attack-detection/brute-force/users/{user['id']}")
            return resp.ok and bool(resp.json().get("disabled"))
        except (AuthError, requests.RequestException):
            return False

    # ---------------------------------------------------------------- correos de Keycloak

    def _redirect_params(self) -> dict[str, str]:
        # Tras completar la acción, Keycloak muestra "Volver a la aplicación" hacia la app.
        return {"client_id": self.client_id, "redirect_uri": f"{get_settings().app_url}/"}

    def send_verify_email(self, user_id: str) -> None:
        resp = self._request(
            "PUT", f"/users/{user_id}/send-verify-email", params=self._redirect_params()
        )
        if resp.status_code >= 400:
            raise AuthError("No fue posible enviar el correo de activación. Revisa el SMTP.")

    def send_actions_email(self, user_id: str, actions: list[str], lifespan_s: int) -> None:
        resp = self._request(
            "PUT",
            f"/users/{user_id}/execute-actions-email",
            params={**self._redirect_params(), "lifespan": lifespan_s},
            json=actions,
        )
        if resp.status_code >= 400:
            raise AuthError("No fue posible enviar el correo. Revisa la configuración SMTP.")

    # ---------------------------------------------------------------- credenciales 2FA

    def otp_credentials(self, user_id: str) -> list[dict]:
        resp = self._request("GET", f"/users/{user_id}/credentials")
        resp.raise_for_status()
        return [c for c in resp.json() if c.get("type") == "otp"]

    def delete_credential(self, user_id: str, credential_id: str) -> None:
        self._request("DELETE", f"/users/{user_id}/credentials/{credential_id}").raise_for_status()

    def delete_user(self, user_id: str) -> None:
        resp = self._request("DELETE", f"/users/{user_id}")
        if resp.status_code not in (204, 404):
            resp.raise_for_status()

    def _admin_headers(self) -> dict[str, str]:
        resp = self._post_token({"grant_type": "client_credentials"})
        if resp.status_code != 200:
            raise AuthError("La cuenta de servicio de Keycloak no está configurada correctamente.")
        return {"Authorization": f"Bearer {resp.json()['access_token']}"}

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        try:
            return requests.request(
                method,
                f"{self._admin_url}{path}",
                headers=self._admin_headers(),
                timeout=TIMEOUT,
                **kwargs,
            )
        except requests.RequestException as exc:
            raise AuthError("No fue posible contactar Keycloak.") from exc

    def create_user(
        self,
        username: str,
        email: str,
        password: str,
        first_name: str,
        last_name: str,
        verified: bool = False,
    ) -> str:
        resp = self._request(
            "POST",
            "/users",
            json={
                "username": username,
                "email": email,
                "firstName": first_name,
                "lastName": last_name,
                "enabled": True,
                "emailVerified": verified,
                # Sin verificar, Keycloak rechaza el login hasta abrir el enlace del correo.
                "requiredActions": [] if verified else ["VERIFY_EMAIL"],
                "credentials": [{"type": "password", "value": password, "temporary": False}],
            },
        )
        if resp.status_code == 409:
            raise AuthError("El usuario o el correo ya están registrados.")
        if resp.status_code == 400:
            raise AuthError(resp.json().get("errorMessage", "Datos de registro inválidos."))
        resp.raise_for_status()
        return resp.headers["Location"].rstrip("/").rsplit("/", 1)[-1]

    def reset_password(self, user_id: str, password: str) -> None:
        resp = self._request(
            "PUT",
            f"/users/{user_id}/reset-password",
            json={"type": "password", "value": password, "temporary": False},
        )
        if resp.status_code == 400:
            raise AuthError(resp.json().get("error_description", "Contraseña rechazada."))
        resp.raise_for_status()

    def update_user(self, user_id: str, **fields) -> None:
        # Se envía la representación completa: con el "user profile" de Keycloak un PUT parcial
        # puede borrar atributos que no se incluyan.
        current = self._request("GET", f"/users/{user_id}")
        current.raise_for_status()
        resp = self._request("PUT", f"/users/{user_id}", json={**current.json(), **fields})
        if resp.status_code == 409:
            raise AuthError("Ese correo ya está en uso.")
        resp.raise_for_status()

    def set_enabled(self, user_id: str, enabled: bool) -> None:
        self.update_user(user_id, enabled=enabled)


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
        user = User(
            username=identity.username,
            email=identity.email or f"{identity.username}@sin-correo.local",
        )
        session.add(user)
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
    email = validate_email(email)
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
    email = validate_email(email)
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
