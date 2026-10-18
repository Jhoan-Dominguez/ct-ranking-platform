"""Bloqueos y reportes entre usuarios."""

import pytest

from app.database.models import ReportStatus, Role
from app.services import forum, moderation, social, users


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
