"""Aplica al realm de Keycloak la configuración que depende del entorno. Es idempotente y se
ejecuta en cada `make up`.

El JSON del realm sólo se importa la primera vez que arranca Keycloak, así que los cambios
posteriores (SMTP, URLs de la app) se aplican aquí con la API de administración, usando la
cuenta de la consola (KEYCLOAK_ADMIN / KEYCLOAK_ADMIN_PASSWORD del realm master).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings

TIMEOUT = 10


def admin_token(base: str) -> str:
    resp = requests.post(
        f"{base}/realms/master/protocol/openid-connect/token",
        data={
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": os.getenv("KEYCLOAK_ADMIN", "admin"),
            "password": os.getenv("KEYCLOAK_ADMIN_PASSWORD", "admin"),
        },
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def main() -> None:
    settings = get_settings()
    if settings.auth_provider != "keycloak":
        print("AUTH_PROVIDER no es keycloak: no hay nada que configurar.")
        return
    base, realm = settings.keycloak_url, settings.keycloak_realm
    headers = {"Authorization": f"Bearer {admin_token(base)}"}
    api = f"{base}/admin/realms/{realm}"

    # 1. Servidor SMTP del realm: Keycloak envía la verificación de correo y el enlace para
    #    configurar el 2FA (QR).
    smtp = {
        "host": os.getenv("KEYCLOAK_SMTP_HOST", "mailpit"),
        "port": os.getenv("KEYCLOAK_SMTP_PORT", "1025"),
        "from": settings.mail_from,
        "fromDisplayName": settings.mail_from_name,
        "starttls": str(settings.smtp_starttls).lower(),
        "ssl": "false",
        "auth": str(bool(settings.smtp_user)).lower(),
    }
    if settings.smtp_user:
        smtp |= {"user": settings.smtp_user, "password": settings.smtp_password}
    realm_rep = requests.get(api, headers=headers, timeout=TIMEOUT).json()
    realm_rep["smtpServer"] = smtp
    realm_rep["internationalizationEnabled"] = True
    realm_rep["supportedLocales"] = ["es", "en"]
    realm_rep["defaultLocale"] = "es"
    requests.put(api, headers=headers, json=realm_rep, timeout=TIMEOUT).raise_for_status()

    # 2. URLs de la app en el cliente: permiten volver a la plataforma ("Volver a la
    #    aplicación") después de verificar el correo o configurar el 2FA en Keycloak.
    clients = requests.get(
        f"{api}/clients",
        headers=headers,
        params={"clientId": settings.keycloak_client_id},
        timeout=TIMEOUT,
    ).json()
    client = clients[0]
    app_url = settings.app_url.rstrip("/")
    client |= {
        "rootUrl": app_url,
        "baseUrl": app_url,
        "redirectUris": [f"{app_url}/*"],
        "webOrigins": [app_url],
        # Flujo de navegador (Authorization Code) para "Continuar con Google" vía st.login.
        "standardFlowEnabled": True,
    }
    client.setdefault("attributes", {})["post.logout.redirect.uris"] = "+"
    requests.put(
        f"{api}/clients/{client['id']}", headers=headers, json=client, timeout=TIMEOUT
    ).raise_for_status()
    google = configure_google(api, headers, settings)
    print(f"Keycloak configurado: SMTP {smtp['host']}:{smtp['port']}, app {app_url}, {google}")


def configure_google(api: str, headers: dict, settings) -> str:
    """Crea o actualiza el proveedor de identidad "google", o lo quita si no hay credenciales.

    - ``hostedDomain``: Keycloak sólo acepta cuentas de Google del dominio institucional.
    - ``trustEmail``: Google ya verificó el correo, así que no se pide la activación por correo.
    - El usuario local en Keycloak toma como username la parte antes de la @ del correo.
    """
    url = f"{api}/identity-provider/instances/google"
    exists = requests.get(url, headers=headers, timeout=TIMEOUT).status_code == 200
    if not settings.google_client_id:
        if exists:
            requests.delete(url, headers=headers, timeout=TIMEOUT).raise_for_status()
        return "Google: deshabilitado (sin GOOGLE_CLIENT_ID)"
    provider = {
        "alias": "google",
        "displayName": "Google",
        "providerId": "google",
        "enabled": True,
        "trustEmail": True,
        "firstBrokerLoginFlowAlias": "first broker login",
        "config": {
            "clientId": settings.google_client_id,
            "clientSecret": settings.google_client_secret,
            "hostedDomain": settings.student_email_domain,
            "defaultScope": "openid profile email",
            "syncMode": "IMPORT",
        },
    }
    if exists:
        requests.put(url, headers=headers, json=provider, timeout=TIMEOUT).raise_for_status()
    else:
        requests.post(
            f"{api}/identity-provider/instances", headers=headers, json=provider, timeout=TIMEOUT
        ).raise_for_status()
    mappers_url = f"{url}/mappers"
    mappers = requests.get(mappers_url, headers=headers, timeout=TIMEOUT).json()
    if not any(m["name"] == "username-from-email" for m in mappers):
        requests.post(
            mappers_url,
            headers=headers,
            json={
                "name": "username-from-email",
                "identityProviderAlias": "google",
                "identityProviderMapper": "oidc-username-idp-mapper",
                "config": {"syncMode": "IMPORT", "template": "${CLAIM.email | localpart}"},
            },
            timeout=TIMEOUT,
        ).raise_for_status()
    return f"Google: habilitado sólo para @{settings.student_email_domain}"


if __name__ == "__main__":
    main()
