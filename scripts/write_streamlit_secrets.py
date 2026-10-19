"""Genera ``.streamlit/secrets.toml`` con la configuración de ``st.login`` (OIDC con Keycloak).

Streamlit sólo lee la configuración de autenticación desde ``secrets.toml``, así que este
script la arma a partir de ``.env``. Se ejecuta en ``make up`` y ``make run``. El archivo está en
``.gitignore`` porque contiene secretos.

El proveedor ``google`` apunta a Keycloak con ``kc_idp_hint=google``: Keycloak redirige directo
a Google sin mostrar su propia página de login.
"""

from __future__ import annotations

import os
import secrets
import tomllib

from app.core.config import ROOT_DIR, get_settings

SECRETS_FILE = ROOT_DIR / ".streamlit" / "secrets.toml"


def _toml_str(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def main() -> None:
    settings = get_settings()
    cookie_secret = settings.auth_cookie_secret
    if not cookie_secret and SECRETS_FILE.exists():
        # Conserva el secreto ya generado para no invalidar las sesiones existentes.
        current = tomllib.loads(SECRETS_FILE.read_text(encoding="utf-8"))
        cookie_secret = current.get("auth", {}).get("cookie_secret", "")
    cookie_secret = cookie_secret or secrets.token_urlsafe(48)

    realm_url = f"{settings.keycloak_url}/realms/{settings.keycloak_realm}"
    lines = [
        "# Generado por scripts/write_streamlit_secrets.py a partir de .env. No editar a mano.",
        "[auth]",
        f"redirect_uri = {_toml_str(settings.app_url + '/oauth2callback')}",
        f"cookie_secret = {_toml_str(cookie_secret)}",
        "",
    ]
    # Dos proveedores idénticos (Keycloak → Google): el nombre indica la intención y Streamlit lo
    # guarda en st.user["provider"]. "google" = iniciar sesión (la cuenta debe existir);
    # "googlesignup" = crear la cuenta.
    for provider in ("google", "googlesignup"):  # sin "_": Streamlit no lo admite
        lines += [
            f"[auth.{provider}]",
            f"client_id = {_toml_str(settings.keycloak_client_id)}",
            f"client_secret = {_toml_str(settings.keycloak_client_secret)}",
            f"server_metadata_url = {_toml_str(realm_url + '/.well-known/openid-configuration')}",
            'client_kwargs = { scope = "openid email profile", prompt = "login" }',
            'authorize_params = { kc_idp_hint = "google" }',
            "",
        ]
    SECRETS_FILE.parent.mkdir(exist_ok=True)
    # Sólo el dueño puede leerlo: contiene el secreto de la cookie y el del cliente de Keycloak.
    fd = os.open(SECRETS_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    SECRETS_FILE.chmod(0o600)  # por si el archivo ya existía con otros permisos
    print(f"Configuración de st.login escrita en {SECRETS_FILE.relative_to(ROOT_DIR)}")


if __name__ == "__main__":
    main()
