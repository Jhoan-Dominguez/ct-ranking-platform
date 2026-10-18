"""Foros: publicaciones, comentarios, "me gusta" y permisos."""

import pytest

from app.services import forum


def test_forum_flow_and_permissions(session, make_user):
    author, other = make_user(), make_user()
    post = forum.create_post(
        session, author.id, title="Duda de álgebra", body="¿Cómo?", category="Duda académica"
    )
    forum.add_comment(session, post.id, other.id, "Así se hace")
    assert forum.toggle_like(session, post.id, other.id) is True
    rows = forum.list_posts(session, search="álgebra")
    assert (rows[0].comments, rows[0].likes) == (1, 1)

    with pytest.raises(forum.ForumError):
        forum.delete_post(session, other, post.id)
    forum.set_solved(session, author, post.id, True)
    assert forum.list_posts(session, solved=True)[0].post.id == post.id
