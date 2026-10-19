"""Borra definitivamente las cuentas cuyo plazo de eliminación venció.

- Desde la app: ``start_background_purge()`` lanza un hilo que lo ejecuta cada hora.
- A mano o con cron: ``python -m app.jobs.purge_accounts`` (``make purge-accounts``).
"""

from __future__ import annotations

import atexit
import logging
import threading

from app.auth import accounts
from app.database.session import session_scope

log = logging.getLogger(__name__)
INTERVAL_S = 3600
_started = threading.Event()
_stop = threading.Event()


def run_once() -> list[str]:
    with session_scope() as session:
        deleted = accounts.purge_due_accounts(session)
    if deleted:
        log.info("Cuentas eliminadas definitivamente: %s", ", ".join(deleted))
    return deleted


def _loop(stop: threading.Event) -> None:
    while not stop.is_set():
        try:
            run_once()
        except Exception:  # la tarea no debe detener la app
            log.exception("Error purgando cuentas")
        stop.wait(INTERVAL_S)


def stop_background_purge() -> None:
    """Pide al hilo que termine (se registra con atexit al iniciarlo)."""
    _stop.set()


def start_background_purge() -> None:
    """Inicia (una sola vez por proceso) el hilo que purga cuentas vencidas cada hora."""
    if _started.is_set():
        return
    _started.set()
    threading.Thread(target=_loop, args=(_stop,), daemon=True, name="purge").start()
    atexit.register(stop_background_purge)


if __name__ == "__main__":
    removed = run_once()
    print(f"Cuentas eliminadas: {', '.join(removed) if removed else 'ninguna'}")
