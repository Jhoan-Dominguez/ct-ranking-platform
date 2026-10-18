"""Seguidores y mensajes de apoyo."""

import pytest

from app.services import social


def test_follow_and_support_messages(session, make_user):
    a, b = make_user(), make_user()
    social.follow(session, a.id, b.id)
    social.follow(session, a.id, b.id)  # idempotente
    assert social.follow_counts(session, b.id) == (1, 0)
    with pytest.raises(social.SocialError):
        social.follow(session, a.id, a.id)

    social.send_support(session, a.id, b.id, "¡Vamos, tú puedes!")
    assert social.unread_count(session, b.id) == 1
    social.mark_all_read(session, b.id)
    assert social.unread_count(session, b.id) == 0
    social.unfollow(session, a.id, b.id)
    assert social.follow_counts(session, b.id) == (0, 0)
