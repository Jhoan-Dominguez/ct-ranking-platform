"""Motor y sesiones de base de datos."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def configure(url: str | None = None) -> Engine:
    """Crea (o reemplaza) el motor global. Los tests lo llaman con una URL de SQLite."""
    global _engine, _session_factory
    _engine = create_engine(url or get_settings().database_url, pool_pre_ping=True)
    _session_factory = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def get_engine() -> Engine:
    return _engine or configure()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Sesión transaccional: hace commit al salir y rollback si ocurre una excepción."""
    if _session_factory is None:
        configure()
    assert _session_factory is not None
    session = _session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
