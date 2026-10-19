"""Espera a que PostgreSQL y Keycloak (realm importado) estén listos. Usado por `make up`."""

from __future__ import annotations

import sys
import time

import requests
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from app.core.config import get_settings

TIMEOUT_S = 180


def wait(name: str, check) -> None:
    deadline = time.monotonic() + TIMEOUT_S
    print(f"Esperando {name}…", end="", flush=True)
    while time.monotonic() < deadline:
        try:
            if check():
                print(" listo ✔")
                return
        except (OperationalError, requests.RequestException):
            pass
        print(".", end="", flush=True)
        time.sleep(2)
    print(f"\n✘ {name} no respondió en {TIMEOUT_S}s. Revisa `make logs`.")
    sys.exit(1)


def main() -> None:
    settings = get_settings()

    def db_ready() -> bool:
        engine = create_engine(settings.database_url)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        return True

    wait("PostgreSQL", db_ready)
    if settings.auth_provider == "keycloak":
        realm_url = f"{settings.keycloak_url}/realms/{settings.keycloak_realm}"
        url = f"{realm_url}/.well-known/openid-configuration"
        wait("Keycloak", lambda: requests.get(url, timeout=3).status_code == 200)


if __name__ == "__main__":
    main()
