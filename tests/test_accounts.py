"""Eliminación diferida de cuentas con doble verificación."""

import re
from datetime import UTC, datetime, timedelta

import pytest

from app import auth
from app.auth import accounts
from app.core import mailer
from app.database.models import Post, User, VerificationCode
from app.services import forum, moderation, users


@pytest.fixture(autouse=True)
def _clear_outbox():
    mailer.OUTBOX.clear()


def _last_code() -> str:
    return re.search(r"\b(\d{6})\b", mailer.OUTBOX[-1].text).group(1)


def test_deletion_requires_password_and_email_code(session, make_user):
    user = make_user(password="Clave1234")
    with pytest.raises(auth.AuthError):
        accounts.request_deletion(session, user, "otra12345")
    assert mailer.OUTBOX == []

    accounts.request_deletion(session, user, "Clave1234")
    assert mailer.OUTBOX[-1].to == user.email
    code = _last_code()

    wrong = "000000" if code != "000000" else "111111"
    with pytest.raises(accounts.AccountError, match="intentos"):
        accounts.confirm_deletion(session, user, wrong)
    assert not user.pending_deletion

    scheduled = accounts.confirm_deletion(session, user, code)
    assert user.pending_deletion
    assert timedelta(days=6, hours=23) < scheduled - datetime.now(UTC) <= timedelta(days=7)
    assert "será eliminada" in mailer.OUTBOX[-1].subject
    with pytest.raises(accounts.AccountError, match="ya está programada"):
        accounts.request_deletion(session, user, "Clave1234")


def test_deletion_code_is_single_use_and_limited(session, make_user, monkeypatch):
    monkeypatch.setattr(accounts, "RESEND_COOLDOWN", timedelta(0))
    user = make_user(password="Clave1234")
    accounts.request_deletion(session, user, "Clave1234")
    first = _last_code()
    accounts.request_deletion(session, user, "Clave1234")  # invalida el código anterior
    second = _last_code()
    if first != second:
        with pytest.raises(accounts.AccountError):
            accounts.confirm_deletion(session, user, first)
    wrong = "000000" if second != "000000" else "111111"
    for _ in range(accounts.MAX_ATTEMPTS - (1 if first != second else 0)):
        with pytest.raises(accounts.AccountError):
            accounts.confirm_deletion(session, user, wrong)
    with pytest.raises(accounts.AccountError, match="Demasiados intentos"):
        accounts.confirm_deletion(session, user, second)


def test_codes_cannot_be_requested_back_to_back(session, make_user):
    user = make_user(password="Clave1234")
    accounts.request_deletion(session, user, "Clave1234")
    with pytest.raises(accounts.AccountError, match="Espera un minuto"):
        accounts.request_deletion(session, user, "Clave1234")
    assert len(mailer.OUTBOX) == 1


def test_expired_code_is_rejected(session, make_user):
    user = make_user(password="Clave1234")
    accounts.request_deletion(session, user, "Clave1234")
    code = _last_code()
    record = session.query(VerificationCode).filter_by(user_id=user.id).one()
    record.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    with pytest.raises(accounts.AccountError, match="expiró"):
        accounts.confirm_deletion(session, user, code)


def test_cancel_and_purge(session, make_user):
    keep, gone = make_user(password="Clave1234"), make_user(password="Clave1234")
    forum.create_post(session, gone.id, title="Post a borrar", body="...", category="General")
    for u in (keep, gone):
        accounts.request_deletion(session, u, "Clave1234")
        accounts.confirm_deletion(session, u, _last_code())

    accounts.cancel_deletion(session, keep)
    assert not keep.pending_deletion
    assert accounts.purge_due_accounts(session) == []  # aún no vence el plazo

    later = datetime.now(UTC) + timedelta(days=8)
    gone_id = gone.id
    assert accounts.purge_due_accounts(session, now=later) == [gone.username]
    assert session.get(User, gone_id) is None
    assert session.query(Post).filter_by(author_id=gone_id).count() == 0
    assert session.get(User, keep.id) is not None


def test_pending_deletion_users_are_hidden(session, make_user):
    viewer, leaving = make_user(), make_user(password="Clave1234")
    accounts.request_deletion(session, leaving, "Clave1234")
    accounts.confirm_deletion(session, leaving, _last_code())
    assert leaving.id in moderation.hidden_user_ids(session, viewer.id)
    assert leaving not in users.search_users(session, exclude_id=viewer.id)
