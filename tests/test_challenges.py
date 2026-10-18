from datetime import date, timedelta

import pytest

from app.database.models import ChallengeKind, Role, Visibility
from app.services import challenges, forum, social


def _challenge(session, creator, **kw):
    params = {"title": "Reto de prueba", "description": "Hazlo", "points": 10, **kw}
    return challenges.create_challenge(session, creator, **params)


def test_only_admin_creates_global(session, make_user):
    student = make_user()
    with pytest.raises(challenges.ChallengeError):
        _challenge(session, student, kind=ChallengeKind.GLOBAL)
    admin = make_user(role=Role.ADMIN)
    assert _challenge(session, admin, kind=ChallengeKind.GLOBAL).kind == ChallengeKind.GLOBAL


def test_ranking_orders_by_completion_and_first_bonus(session, make_user):
    creator, a, b, c = make_user(), make_user(), make_user(), make_user()
    ch = _challenge(session, creator, points=10)
    for u in (a, b, c):
        challenges.join(session, u, ch.id)
    with pytest.raises(challenges.ChallengeError, match="evidencia"):
        challenges.complete(session, b, ch.id)
    challenges.complete(session, b, ch.id, "link")
    challenges.complete(session, a, ch.id, "link")

    ranking = challenges.ranking(session, ch.id)
    assert [(e.position, e.user.id) for e in ranking] == [(1, b.id), (2, a.id), (None, c.id)]

    stats = challenges.stats(session, ch.id)
    assert (stats.participants, stats.completed, stats.first.user.id) == (3, 2, b.id)

    board = challenges.leaderboard(session)
    assert [(e.user.id, e.score, e.firsts) for e in board] == [(b.id, 15, 1), (a.id, 10, 0)]


def test_followers_only_visibility(session, make_user):
    creator, fan, stranger = make_user(), make_user(), make_user()
    ch = _challenge(session, creator, visibility=Visibility.FOLLOWERS)
    social.follow(session, fan.id, creator.id)
    assert [r.challenge.id for r in challenges.list_challenges(session, fan)] == [ch.id]
    assert challenges.list_challenges(session, stranger) == []
    with pytest.raises(challenges.ChallengeError):
        challenges.join(session, stranger, ch.id)
    rows = challenges.list_challenges(session, fan, scope="following")
    assert [r.challenge.id for r in rows] == [ch.id]


def test_closed_challenge_cannot_be_joined(session, make_user):
    creator, user = make_user(), make_user()
    ch = _challenge(
        session,
        creator,
        starts_at=date.today() - timedelta(days=10),
        ends_at=date.today() - timedelta(days=1),
    )
    with pytest.raises(challenges.ChallengeError, match="abierto"):
        challenges.join(session, user, ch.id)


def test_automatic_rule_challenge(session, make_user):
    admin, user = make_user(role=Role.ADMIN), make_user()
    ch = _challenge(session, admin, kind=ChallengeKind.GLOBAL, rule="first_post")
    part = challenges.join(session, user, ch.id)
    assert part.completed_at is None
    with pytest.raises(challenges.ChallengeError, match="meta"):
        challenges.complete(session, user, ch.id)

    forum.create_post(session, user.id, title="Mi primera duda", body="...", category="General")
    assert challenges.refresh_automatic(session, user) == [ch.title]
    assert part.completed_at is not None


def test_rule_already_met_completes_on_join(session, make_user):
    """Usuarios antiguos que ya cumplen la condición completan el reto global al unirse."""
    admin, veteran = make_user(role=Role.ADMIN), make_user()
    forum.create_post(session, veteran.id, title="Post antiguo", body="...", category="General")
    ch = _challenge(session, admin, kind=ChallengeKind.GLOBAL, rule="first_post")
    assert challenges.join(session, veteran, ch.id).completed_at is not None
