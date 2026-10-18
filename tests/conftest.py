import os

# Los tests usan autenticación local y SQLite en memoria: no requieren Docker.
os.environ["AUTH_PROVIDER"] = "local"

import pytest
from sqlalchemy import event
from sqlalchemy.pool import StaticPool

from app.config import get_settings
from app.db import session as db_session
from app.db.models import Base
from app.services import auth

get_settings.cache_clear()


@pytest.fixture
def session():
    engine = db_session.configure("sqlite://")
    engine.pool = StaticPool(engine.pool._creator)  # una sola conexión para la BD en memoria
    event.listen(engine, "connect", lambda conn, _: conn.execute("PRAGMA foreign_keys=ON"))
    Base.metadata.create_all(engine)
    with db_session.session_scope() as s:
        yield s


@pytest.fixture
def make_user(session):
    counter = iter(range(1, 1000))

    def _make(**kwargs):
        n = next(counter)
        return auth.register(
            session,
            username=kwargs.pop("username", f"user{n}"),
            email=kwargs.pop("email", f"user{n}@test.co"),
            password=kwargs.pop("password", "Secret123"),
            first_name="Test",
            last_name=f"User{n}",
            **kwargs,
        )

    return _make
