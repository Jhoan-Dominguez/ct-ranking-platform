"""Límite de intentos en memoria del proceso (anti fuerza bruta y anti *email bombing*).

Es deliberadamente simple: Streamlit corre en un solo proceso, así que un diccionario protegido
con un lock basta. Los contadores se pierden al reiniciar la app, lo cual es aceptable para
ventanas de segundos o minutos.
"""

from __future__ import annotations

import threading
import time

_lock = threading.Lock()
_events: dict[str, list[float]] = {}


class RateLimitError(Exception):
    """Se superó el límite de intentos. El mensaje es apto para mostrar al usuario."""


def _recent(key: str, window_s: float, now: float) -> list[float]:
    events = [t for t in _events.get(key, []) if now - t < window_s]
    _events[key] = events
    return events


def hit(
    key: str,
    *,
    limit: int,
    window_s: float,
    message: str,
    error: type[Exception] = RateLimitError,
) -> None:
    """Registra un intento y lanza ``error(message)`` si ya hubo ``limit`` en la ventana."""
    now = time.monotonic()
    with _lock:
        events = _recent(key, window_s, now)
        if len(events) >= limit:
            raise error(message)
        events.append(now)


def check(
    key: str,
    *,
    limit: int,
    window_s: float,
    message: str,
    error: type[Exception] = RateLimitError,
) -> None:
    """Como ``hit`` pero sin registrar el intento (p. ej. para contar sólo los fallidos)."""
    with _lock:
        if len(_recent(key, window_s, time.monotonic())) >= limit:
            raise error(message)


def record(key: str) -> None:
    with _lock:
        _events.setdefault(key, []).append(time.monotonic())


def reset(key: str | None = None) -> None:
    with _lock:
        if key is None:
            _events.clear()
        else:
            _events.pop(key, None)
