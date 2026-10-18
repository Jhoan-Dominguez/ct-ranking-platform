import re
from datetime import UTC, datetime, timedelta

import pytest

from app.db.models import Post, ReportStatus, Role, User, VerificationCode
from app.services import accounts, auth, forum, mailer, moderation, social, users


@pytest.fixture(autouse=True)
def _clear_outbox():
    mailer.OUTBOX.clear()


def _last_code() -> str:
    return re.search(r"\b(\d{6})\b", mailer.OUTBOX[-1].text).group(1)


# --------------------------------------------------------------------------- eliminación


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


def test_deletion_code_is_single_use_and_limited(session, make_user):
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


# --------------------------------------------------------------------------- bloqueos


def test_block_removes_follows_and_prevents_contact(session, make_user):
    a, b = make_user(), make_user()
    social.follow(session, a.id, b.id)
    social.follow(session, b.id, a.id)
    social.send_support(session, b.id, a.id, "¡Ánimo!")

    moderation.block(session, a.id, b.id)
    assert social.follow_counts(session, a.id) == (0, 0)
    assert social.inbox(session, a.id) == []  # se ocultan los mensajes del bloqueado
    assert social.unread_count(session, a.id) == 0
    for actor, target in ((a, b), (b, a)):
        with pytest.raises(social.SocialError):
            social.follow(session, actor.id, target.id)
        with pytest.raises(social.SocialError):
            social.send_support(session, actor.id, target.id, "hola")
    assert b not in users.search_users(session, exclude_id=a.id, hidden_ids={b.id})
    assert moderation.blocked_ids(session, b.id) == {a.id}  # el efecto es bidireccional

    moderation.unblock(session, a.id, b.id)
    social.follow(session, a.id, b.id)
    assert moderation.blocked_users(session, a.id) == []


def test_blocked_author_posts_are_excluded(session, make_user):
    viewer, blocked = make_user(), make_user()
    forum.create_post(session, blocked.id, title="No me verás", body="...", category="General")
    moderation.block(session, viewer.id, blocked.id)
    hidden = moderation.hidden_user_ids(session, viewer.id)
    assert forum.list_posts(session, exclude_author_ids=hidden) == []


def test_cannot_block_or_report_self(session, make_user):
    a = make_user()
    with pytest.raises(moderation.ModerationError):
        moderation.block(session, a.id, a.id)
    with pytest.raises(moderation.ModerationError):
        moderation.report(session, a.id, a.id, reason="spam")


# --------------------------------------------------------------------------- reportes


def test_report_flow_and_admin_resolution(session, make_user):
    reporter, offender = make_user(), make_user()
    admin = make_user(role=Role.ADMIN)
    post = forum.create_post(session, offender.id, title="Publicidad", body="…", category="General")

    with pytest.raises(moderation.ModerationError, match="Describe"):
        moderation.report(session, reporter.id, offender.id, reason="otro")
    rep = moderation.report(session, reporter.id, offender.id, reason="spam", post_id=post.id)
    with pytest.raises(moderation.ModerationError, match="Ya enviaste"):
        moderation.report(session, reporter.id, offender.id, reason="spam", post_id=post.id)
    # Un reporte distinto (sin publicación) sí se permite.
    moderation.report(session, reporter.id, offender.id, reason="acoso", description="insultos")
    assert moderation.pending_reports_count(session) == 2
    assert moderation.reports_against_count(session, offender.id) == 2

    with pytest.raises(moderation.ModerationError):
        moderation.close_report(session, reporter, rep.id, ReportStatus.RESOLVED)
    moderation.close_report(session, admin, rep.id, ReportStatus.RESOLVED, "Publicación eliminada")
    assert rep.status == ReportStatus.RESOLVED and rep.resolved_by_id == admin.id
    assert moderation.pending_reports_count(session) == 1
    assert [r.id for r in moderation.list_reports(session, ReportStatus.RESOLVED)] == [rep.id]

    forum.delete_post(session, admin, post.id)  # el reporte se conserva (post_id → NULL)
    session.expire_all()
    assert moderation.list_reports(session, ReportStatus.RESOLVED)[0].post_id is None
