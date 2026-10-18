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
    }
    requests.put(
        f"{api}/clients/{client['id']}", headers=headers, json=client, timeout=TIMEOUT
    ).raise_for_status()
    print(f"Keycloak configurado: SMTP {smtp['host']}:{smtp['port']}, app {app_url}")


if __name__ == "__main__":
    main()
