import pytest

from app.services import admin, auth, forum, social, users


def test_register_and_login_local(session, make_user):
    user = make_user(username="maria", email="maria@test.co", password="Clave1234")
    assert auth.login(session, "maria", "Clave1234").id == user.id
    assert auth.login(session, "MARIA@test.co", "Clave1234").id == user.id
    with pytest.raises(auth.AuthError):
        auth.login(session, "maria", "otra12345")
    with pytest.raises(auth.AuthError, match="registrados"):
        make_user(username="maria")


def test_password_rules_and_change(session, make_user):
    with pytest.raises(auth.AuthError, match="8"):
        make_user(password="a1")
    user = make_user(password="Clave1234")
    with pytest.raises(auth.AuthError, match="actual"):
        auth.change_password(session, user, "mala12345", "Nueva1234")
    auth.change_password(session, user, "Clave1234", "Nueva1234")
    assert auth.login(session, user.username, "Nueva1234").id == user.id


def test_disabled_user_cannot_login(session, make_user):
    user = make_user(password="Clave1234")
    auth.set_active(session, user, False)
    with pytest.raises(auth.AuthError, match="deshabilitada"):
        auth.login(session, user.username, "Clave1234")


def test_profile_alias_unique_and_semester_bounds(session, make_user):
    a, b = make_user(), make_user()
    users.update_profile(session, a, alias="Lau")
    with pytest.raises(users.ProfileError, match="alias"):
        users.update_profile(session, b, alias="lau")
    with pytest.raises(users.ProfileError, match="semestre"):
        users.update_profile(session, a, current_semester=12, total_semesters=10)


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


def test_admin_students_frame_flags_risk(session, make_user):
    from app.services import academics

    user = make_user()
    subj = academics.add_subject(session, user.id, name="Física", semester=1)
    academics.add_item(session, user.id, subj.id, name="Parcial", grade=2.0)
    df = admin.students_frame(session)
    row = df[df["id"] == user.id].iloc[0]
    assert row["promedio_general"] == pytest.approx(2.0)
    assert bool(row["en_riesgo"]) is True
    assert admin.global_metrics(session).users == 1
