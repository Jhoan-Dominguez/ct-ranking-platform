import os

# Los tests usan autenticación local, SQLite en memoria y correo en memoria: no requieren Docker.
os.environ["AUTH_PROVIDER"] = "local"
os.environ["MAIL_BACKEND"] = "memory"  # los correos se guardan en mailer.OUTBOX

import pytest
from sqlalchemy import event
from sqlalchemy.pool import StaticPool

from app import auth
from app.core import ratelimit
from app.core.config import get_settings
from app.database import session as db_session
from app.database.models import Base

get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    ratelimit.reset()


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
            email=kwargs.pop("email", f"user{n}@{auth.student_domain()}"),
            password=kwargs.pop("password", "Secret123"),
            first_name="Test",
            last_name=f"User{n}",
            **kwargs,
        )

    return _make
