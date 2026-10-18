"""Cliente de Keycloak: login por contraseña (direct grant), API de administración y correos
de Keycloak (activación y configuración de 2FA)."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field

import requests

from app.auth.errors import INVALID_LOGIN, AuthError, EmailNotVerifiedError
from app.core.config import get_settings

TIMEOUT = 10


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
        self.pwcheck_client = (s.keycloak_pwcheck_client_id, s.keycloak_pwcheck_client_secret)

    @property
    def _token_url(self) -> str:
        return f"{self.base}/realms/{self.realm}/protocol/openid-connect/token"

    @property
    def _admin_url(self) -> str:
        return f"{self.base}/admin/realms/{self.realm}"

    def _post_token(self, data: dict, client: tuple[str, str] | None = None) -> requests.Response:
        client_id, client_secret = client or (self.client_id, self.client_secret)
        try:
            return requests.post(
                self._token_url,
                data={"client_id": client_id, "client_secret": client_secret, **data},
                timeout=TIMEOUT,
            )
        except requests.RequestException as exc:
            raise AuthError(
                "No fue posible contactar el servidor de autenticación (Keycloak). "
                "¿Ejecutaste `make up`?"
            ) from exc

    def password_login(
        self, username: str, password: str, otp: str | None = None, *, password_only: bool = False
    ) -> Identity:
        """Login con usuario y contraseña (flujo "direct grant"). Si el usuario tiene 2FA, el
        flujo del realm exige además el código TOTP en el parámetro ``otp``.

        Con ``password_only`` se usa el cliente de verificación (``ct-ranking-pwcheck``), cuyo
        flujo no pide OTP: sirve para comprobar la contraseña antes de pedir el código. Su token
        se descarta."""
        data = {"grant_type": "password", "username": username, "password": password}
        if otp:
            data["otp"] = otp.strip().replace(" ", "")
        client = self.pwcheck_client if password_only else None
        resp = self._post_token({**data, "scope": "openid"}, client)
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
