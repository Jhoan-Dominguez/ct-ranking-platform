"""Autenticación básica con dos proveedores intercambiables (AUTH_PROVIDER):

- ``keycloak``: el usuario y la contraseña se validan contra Keycloak con el flujo
  *Resource Owner Password Credentials* (Direct Access Grants). El alta de usuarios y el cambio de
  contraseña/correo se hacen con la API de administración usando la cuenta de servicio del
  cliente ``ct-ranking-app``. En la BD de la app sólo se guarda el perfil (``keycloak_id``).
- ``local``: contraseñas con bcrypt en la tabla ``users`` (útil para tests o sin Docker).
"""

from __future__ import annotations

import base64
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

    def password_login(self, username: str, password: str) -> Identity:
        resp = self._post_token(
            {
                "grant_type": "password",
                "username": username,
                "password": password,
                "scope": "openid",
            }
        )
        if resp.status_code in (400, 401):
            description = resp.json().get("error_description", "")
            if "disabled" in description.lower():
                raise AuthError("La cuenta está deshabilitada.")
            raise AuthError("Usuario o contraseña incorrectos.")
        resp.raise_for_status()
        claims = _decode_jwt_payload(resp.json()["access_token"])
        return Identity(
            external_id=claims["sub"],
            username=claims.get("preferred_username", username),
            email=claims.get("email", ""),
            first_name=claims.get("given_name", ""),
            last_name=claims.get("family_name", ""),
            roles=set(claims.get("realm_access", {}).get("roles", [])),
        )

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
        self, username: str, email: str, password: str, first_name: str, last_name: str
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
                "emailVerified": True,
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
    # Keycloak puede otorgar el rol admin; las promociones hechas desde el panel se conservan.
    if Role.ADMIN in identity.roles:
        user.role = Role.ADMIN
    return user


def login(session: Session, username: str, password: str) -> User:
    if not username.strip() or not password:
        raise AuthError("Ingresa usuario y contraseña.")
    if _uses_keycloak():
        user = _sync_keycloak_user(session, KeycloakClient().password_login(username, password))
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
) -> User:
    username = validate_username(username)
    email = validate_email(email)
    first_name, last_name = validate_names(first_name, last_name)
    validate_password(password)
    _ensure_unique(session, username, email)
    user = User(
        username=username, email=email, first_name=first_name, last_name=last_name, role=role
    )
    if _uses_keycloak():
        user.keycloak_id = KeycloakClient().create_user(
            username, email, password, first_name, last_name
        )
    else:
        user.password_hash = hash_password(password)
    session.add(user)
    session.flush()
    return user


def change_password(session: Session, user: User, current: str, new: str) -> None:
    validate_password(new)
    if _uses_keycloak():
        client = KeycloakClient()
        client.password_login(user.username, current)  # verifica la contraseña actual
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
