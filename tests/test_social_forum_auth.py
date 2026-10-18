import pytest

from app.services import admin, auth, forum, social, users


def test_register_and_login_local(session, make_user):
    user = make_user(
        username="maria", email="maria@estudiantes.areandina.edu.co", password="Clave1234"
    )
    assert auth.login(session, "maria", "Clave1234").id == user.id
    assert auth.login(session, "MARIA@estudiantes.areandina.edu.co", "Clave1234").id == user.id
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


def test_students_must_use_institutional_domain(session, make_user):
    assert auth.student_email(" Laura.Gomez ") == "laura.gomez@estudiantes.areandina.edu.co"
    for bad in ("laura@gmail.com", "laura gomez", ".laura", "laura..gomez", ""):
        with pytest.raises(auth.AuthError):
            auth.student_email(bad)
    with pytest.raises(auth.AuthError, match="institucional"):
        make_user(email="laura@gmail.com")
    with pytest.raises(auth.AuthError, match="institucional"):
        make_user(email="laura@areandina.edu.co")  # otro subdominio
    student = make_user(email="sofi@estudiantes.areandina.edu.co")
    with pytest.raises(auth.AuthError, match="institucional"):
        auth.change_email(session, student, "sofi@gmail.com")
    auth.change_email(session, student, "sofia.h@estudiantes.areandina.edu.co")
    assert student.email == "sofia.h@estudiantes.areandina.edu.co"


def test_admins_are_exempt_from_student_domain(session, make_user):
    from app.db.models import Role

    admin = make_user(email="soporte@ctranking.local", role=Role.ADMIN)
    auth.change_email(session, admin, "admin2@ctranking.local")
    assert admin.email == "admin2@ctranking.local"


def _google_claims(**overrides):
    claims = {
        "sub": "kc-123",
        "email": "eva.gomez@estudiantes.areandina.edu.co",
        "email_verified": True,
        "preferred_username": "eva.gomez",
        "given_name": "Eva",
        "family_name": "Gómez",
    }
    return claims | overrides


def test_login_with_google_creates_and_links_user(session):
    user = auth.login_with_oidc(session, _google_claims())
    assert (user.username, user.email, user.keycloak_id) == (
        "eva.gomez",
        "eva.gomez@estudiantes.areandina.edu.co",
        "kc-123",
    )
    assert user.email_verified and user.full_name == "Eva Gómez" and user.last_login
    again = auth.login_with_oidc(session, _google_claims(given_name="Otro"))
    assert again.id == user.id  # misma identidad de Keycloak → mismo usuario


def test_login_with_google_rejects_other_domains_and_unverified(session):
    with pytest.raises(auth.AuthError, match="institucional"):
        auth.login_with_oidc(session, _google_claims(email="eva@gmail.com"))
    with pytest.raises(auth.AuthError, match="confirmó"):
        auth.login_with_oidc(session, _google_claims(email_verified=False))
    with pytest.raises(auth.AuthError):
        auth.login_with_oidc(session, _google_claims(sub=None))


def test_login_with_google_respects_disabled_accounts(session):
    user = auth.login_with_oidc(session, _google_claims())
    auth.set_active(session, user, False)
    with pytest.raises(auth.AuthError, match="deshabilitada"):
        auth.login_with_oidc(session, _google_claims())


def test_first_keycloak_login_creates_active_user(session):
    """Regresión: un usuario nuevo tenía is_active=None antes del flush y se rechazaba."""
    identity = auth.Identity(external_id="kc-new", username="nuevo", email="n@x.co")
    user = auth._sync_keycloak_user(session, identity)
    assert user.id is not None and user.is_active is True and user.role == "student"
