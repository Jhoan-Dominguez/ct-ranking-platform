"""Pruebas de regresión de los hallazgos de la auditoría (AUDITORIA.md).

Cada prueba reproduce el escenario que antes demostraba el defecto y verifica que ya está
corregido.
"""

import re
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select

from app import auth
from app.auth import accounts
from app.auth import service as auth_service
from app.core import mailer
from app.database import session as db_session
from app.database.models import (
    Challenge,
    ChallengeKind,
    Difficulty,
    Role,
    SupportMessage,
    User,
    VerificationCode,
)
from app.services import academics, admin, challenges, forum, moderation, social, users
from app.ui.components import formatting, widgets


@pytest.fixture(autouse=True)
def _clear_outbox():
    mailer.OUTBOX.clear()


def _last_code() -> str:
    return re.search(r"\b(\d{6})\b", mailer.OUTBOX[-1].text).group(1)


# --------------------------------------------------------------------------- 2.1 #1


def test_failed_deletion_attempts_survive_rollback(session, make_user):
    """Cada intento fallido se guarda aunque la acción de la UI (session_scope) termine en error,
    así el límite de MAX_ATTEMPTS sí se aplica."""
    u = make_user(username="victima", password="Password123")
    uid = u.id
    accounts.request_deletion(session, u, "Password123")
    session.commit()

    for i in range(1, accounts.MAX_ATTEMPTS + 1):
        with (
            pytest.raises(accounts.AccountError, match="Código incorrecto"),
            db_session.session_scope() as s,
        ):
            accounts.confirm_deletion(s, s.get(User, uid), "000000")
        session.expire_all()
        record = session.scalar(select(VerificationCode).where(VerificationCode.user_id == uid))
        assert record.attempts == i

    # Agotados los intentos, ni siquiera el código correcto sirve.
    with (
        pytest.raises(accounts.AccountError, match="Demasiados intentos"),
        db_session.session_scope() as s,
    ):
        accounts.confirm_deletion(s, s.get(User, uid), _last_code())


def test_other_errors_still_roll_back(session, make_user):
    u = make_user()
    uid = u.id
    session.commit()
    with pytest.raises(ValueError), db_session.session_scope() as s:
        s.get(User, uid).city = "Bogotá"
        raise ValueError("falla")
    session.expire_all()
    assert session.get(User, uid).city == ""


# --------------------------------------------------------------------------- 2.1 #2


def test_google_username_collision_does_not_take_over_account(session, make_user):
    victim = make_user(username="carlos", email="carlos.perez@estudiantes.areandina.edu.co")
    victim.keycloak_id = "kc-victim"
    session.flush()
    claims = {
        "sub": "kc-attacker-999",
        "email": "carlos@estudiantes.areandina.edu.co",
        "email_verified": True,
        "preferred_username": "carlos",
        "given_name": "Carlos",
        "family_name": "Otro",
    }
    user, created = auth.login_with_oidc(session, claims, allow_create=True)

    assert created
    assert user.id != victim.id
    assert user.username == "carlos2"
    assert victim.email == "carlos.perez@estudiantes.areandina.edu.co"
    assert victim.keycloak_id == "kc-victim"


def test_unlinked_local_account_matches_only_by_verified_email(session, make_user):
    """Una cuenta local sin keycloak_id (p. ej. el admin de init_db) se vincula por correo, no
    por username."""
    local = make_user(username="carlos", email="carlos.perez@estudiantes.areandina.edu.co")
    identity = auth.Identity(
        external_id="kc-1", username="carlos", email="otro@estudiantes.areandina.edu.co"
    )
    synced = auth_service._sync_keycloak_user(session, identity)
    assert synced.id != local.id

    identity = auth.Identity(external_id="kc-2", username="x", email=local.email)
    assert auth_service._sync_keycloak_user(session, identity).id == local.id
    assert local.keycloak_id == "kc-2"


def test_google_login_rejects_email_linked_to_another_keycloak_user(session, make_user):
    owner = make_user(email="eva@estudiantes.areandina.edu.co")
    owner.keycloak_id = "kc-owner"
    session.flush()
    claims = {"sub": "kc-other", "email": owner.email, "email_verified": True}
    with pytest.raises(auth.AuthError, match="vinculado"):
        auth.login_with_oidc(session, claims, allow_create=True)


# --------------------------------------------------------------------------- 2.1 #3


def test_email_change_requires_code_sent_to_new_address(session, make_user, monkeypatch):
    u = make_user(username="est1", email="est1@estudiantes.areandina.edu.co")
    u.keycloak_id = "kc-est-1"
    session.flush()
    mock_kc = MagicMock()
    monkeypatch.setattr(auth_service, "_uses_keycloak", lambda: True)
    monkeypatch.setattr(auth_service, "KeycloakClient", lambda: mock_kc)
    new = "otro.estudiante@estudiantes.areandina.edu.co"

    accounts.request_email_change(session, u, new)
    assert mailer.OUTBOX[-1].to == new
    assert u.email == "est1@estudiantes.areandina.edu.co"
    mock_kc.update_user.assert_not_called()

    with pytest.raises(accounts.AccountError, match="incorrecto"):
        accounts.confirm_email_change(session, u, "000000" if _last_code() != "000000" else "1")
    assert u.email == "est1@estudiantes.areandina.edu.co"

    accounts.confirm_email_change(session, u, _last_code())
    assert u.email == new
    mock_kc.update_user.assert_called_once_with("kc-est-1", email=new, emailVerified=True)
    assert mailer.OUTBOX[-1].to == "est1@estudiantes.areandina.edu.co"  # aviso al anterior


def test_email_change_rechecks_availability_on_confirm(session, make_user):
    u = make_user()
    accounts.request_email_change(session, u, "libre@estudiantes.areandina.edu.co")
    code = _last_code()
    make_user(email="libre@estudiantes.areandina.edu.co")  # alguien lo registró mientras tanto
    with pytest.raises(auth.AuthError, match="registrado"):
        accounts.confirm_email_change(session, u, code)


# --------------------------------------------------------------------------- 2.1 #4


def test_admin_with_non_student_email_can_use_google(session, make_user):
    admin_user = make_user(username="admin_inst", email="admin@ctranking.local", role=Role.ADMIN)
    claims = {"sub": "kc-admin-1", "email": admin_user.email, "email_verified": True}
    user, created = auth.login_with_oidc(session, claims)
    assert user.id == admin_user.id
    assert not created


# --------------------------------------------------------------------------- 2.1 #5 y 3.4.4


def test_demoted_admin_stays_demoted_after_keycloak_login(session, make_user):
    boss = make_user(username="boss", role=Role.ADMIN)
    u = make_user(username="mod1", role=Role.ADMIN)
    u.keycloak_id = "kc-mod-1"
    session.flush()

    admin.set_role(session, boss, u.id, Role.STUDENT)
    identity = auth.Identity(
        external_id="kc-mod-1", username="mod1", email=u.email, roles={Role.ADMIN}
    )
    assert auth_service._sync_keycloak_user(session, identity).role == Role.STUDENT


def test_keycloak_admin_role_applies_when_creating_local_account(session):
    identity = auth.Identity(
        external_id="kc-new", username="nuevo", email="n@ctranking.local", roles={Role.ADMIN}
    )
    assert auth_service._sync_keycloak_user(session, identity).role == Role.ADMIN


def test_admin_services_check_the_actor(session, make_user):
    student, other = make_user(), make_user()
    social.send_support(session, other.id, student.id, "¡Ánimo!")
    message_id = session.scalar(select(SupportMessage.id))
    with pytest.raises(admin.AdminError):
        admin.set_role(session, student, student.id, Role.ADMIN)
    with pytest.raises(admin.AdminError):
        admin.delete_message(session, student, message_id)
    boss = make_user(role=Role.ADMIN)
    with pytest.raises(admin.AdminError, match="propio rol"):
        admin.set_role(session, boss, boss.id, Role.STUDENT)
    admin.delete_message(session, boss, message_id)
    session.flush()
    assert session.get(SupportMessage, message_id) is None


# --------------------------------------------------------------------------- 2.1 #6


def test_load_pensum_matches_existing_subject_by_name(session, make_user):
    u = make_user()
    academics.add_subject(
        session, u.id, name="Pensamiento Computacional", code="PC101", credits=3, semester=1
    )
    academics.load_pensum(session, u, "Ingeniería de Software")
    same = [
        s
        for s in academics.list_subjects(session, u.id)
        if s.name.lower() == "pensamiento computacional"
    ]
    assert len(same) == 1


# --------------------------------------------------------------------------- 2.1 #7


def test_zero_grade_is_failing_not_missing(session, make_user):
    u = make_user()
    subj = academics.add_subject(session, u.id, name="Cálculo", credits=3, semester=1)
    academics.add_item(session, u.id, subj.id, name="Parcial 1", grade=0.0, weight=100.0)
    subjects = academics.list_subjects(session, u.id)
    grade = academics.subject_grade(subjects[0].items)
    assert grade == 0.0
    assert formatting.grade_color(grade, 3.0) == "red"
    assert formatting.grade_color(None, 3.0) == "gray"
    assert formatting.grade_color(4.0, 3.0) == "green"
    assert formatting.fmt_grade(academics.summarize(subjects, 1).semesters[0].average) == "0.00"


# --------------------------------------------------------------------------- 2.1 #8


def test_deleting_creator_keeps_global_challenge_and_points(session, make_user):
    creator = make_user(username="creador", role=Role.ADMIN)
    student = make_user(username="alumno")
    ch = challenges.create_challenge(
        session,
        creator,
        title="Reto Global Semestral",
        description="Completa el semestre",
        difficulty=Difficulty.MEDIUM,
        points=50,
        kind=ChallengeKind.GLOBAL,
    )
    ch_id = ch.id
    challenges.join(session, student, ch_id)
    challenges.complete(session, student, ch_id, evidence="Evidencia válida")

    session.delete(creator)
    session.flush()
    session.expire_all()

    assert session.get(Challenge, ch_id).creator_id is None
    board = challenges.leaderboard(session)
    assert [(e.user.id, e.score) for e in board] == [(student.id, 75)]


def test_purge_removes_community_challenges_but_keeps_global_ones(session, make_user):
    leaving = make_user(password="Clave1234", role=Role.ADMIN)
    student = make_user()
    global_ch = challenges.create_challenge(
        session, leaving, title="Reto global", description="d", kind=ChallengeKind.GLOBAL
    )
    community_ch = challenges.create_challenge(
        session, leaving, title="Reto propio", description="d"
    )
    challenges.join(session, student, global_ch.id)
    accounts.request_deletion(session, leaving, "Clave1234")
    accounts.confirm_deletion(session, leaving, _last_code())

    assert accounts.purge_due_accounts(session, now=datetime.now(UTC) + timedelta(days=8))
    session.expire_all()
    assert session.get(Challenge, global_ch.id) is not None
    assert session.get(Challenge, community_ch.id) is None


# --------------------------------------------------------------------------- 2.1 #9


def test_pending_deletion_user_does_not_skew_bonus_or_counts(session, make_user):
    u_leaving = make_user(username="seva", password="Password123")
    u_active = make_user(username="activo", password="Password123")

    social.follow(session, u_leaving.id, u_active.id)
    post = forum.create_post(
        session, u_active.id, title="Pregunta", body="Contenido válido", category="General"
    )
    forum.add_comment(session, post.id, u_leaving.id, "Comentario de usuario que se va")
    forum.toggle_like(session, post.id, u_leaving.id)

    ch = challenges.create_challenge(
        session,
        u_active,
        title="Reto 100",
        description="Desc",
        difficulty=Difficulty.EASY,
        points=20,
    )
    p1 = challenges.join(session, u_leaving, ch.id)
    p1.completed_at = datetime.now(UTC) - timedelta(hours=2)
    p2 = challenges.join(session, u_active, ch.id)
    p2.completed_at = datetime.now(UTC) - timedelta(hours=1)
    session.flush()

    accounts.request_deletion(session, u_leaving, "Password123")
    accounts.confirm_deletion(session, u_leaving, _last_code())
    hidden = moderation.hidden_user_ids(session, u_active.id)
    assert u_leaving.id in hidden

    board = challenges.leaderboard(session, exclude_ids=hidden)
    assert [(e.user.id, e.score, e.firsts) for e in board] == [(u_active.id, 30, 1)]
    standing = challenges.standing(session, u_active.id)
    assert (standing.score, standing.position) == (30, 1)

    row = forum.list_posts(session, exclude_author_ids=hidden)[0]
    assert (row.comments, row.likes) == (0, 0)
    assert social.follow_counts(session, u_active.id, hidden) == (0, 0)


# --------------------------------------------------------------------------- 2.1 #10 y 3.4.1


def test_user_chip_escapes_subtitle(session, make_user, monkeypatch):
    rendered = []
    monkeypatch.setattr(
        widgets.st, "markdown", lambda body, unsafe_allow_html=False: rendered.append(body)
    )
    u = make_user()
    users.update_profile(
        session, u, alias='<img src=x onerror=alert("a")>', program="<script>alert(1)</script>"
    )
    widgets.user_chip(u, 40, u.program)
    assert "<script>" not in rendered[-1]
    assert "&lt;script&gt;" in rendered[-1]
    assert "<img src=x" not in rendered[-1]


def test_account_emails_escape_user_data(session, make_user, monkeypatch):
    sent = []
    monkeypatch.setattr(mailer, "send", lambda to, subject, paragraphs: sent.append(paragraphs))
    u = make_user(password="Password123")
    users.update_profile(session, u, alias="<img src=x onerror=alert(1)>")
    accounts.request_deletion(session, u, "Password123")
    html = "".join(sent[-1])
    assert "<img" not in html
    assert "&lt;img" in html


def test_profile_links_must_be_http(session, make_user):
    u = make_user()
    for bad in ("javascript:alert(1)", "github.com/ana", "https://x.com/a)[b](javascript:1"):
        with pytest.raises(users.ProfileError):
            users.update_profile(session, u, github_url=bad)
    users.update_profile(session, u, github_url="https://github.com/ana")
    assert u.github_url == "https://github.com/ana"


# --------------------------------------------------------------------------- 2.2


def test_unknown_rule_does_not_break_progress(session, make_user):
    from app.services import challenge_rules

    u = make_user()
    assert challenge_rules.progress(session, "regla_renombrada", u.id) == (0.0, 1.0)
    assert not challenge_rules.is_satisfied(session, "regla_renombrada", u.id)


# --------------------------------------------------------------------------- 3.4.2


def test_local_login_locks_after_repeated_failures(session, make_user):
    make_user(username="ana", password="Clave1234")
    for _ in range(auth_service.LOCAL_MAX_FAILURES):
        with pytest.raises(auth.AuthError, match="incorrectos"):
            auth.login(session, "ana", "mala12345")
    with pytest.raises(auth.AuthError, match="Demasiados intentos"):
        auth.login(session, "ana", "Clave1234")


# --------------------------------------------------------------------------- 4.4 y 4.5


def test_alias_and_report_constraints(session, make_user):
    a, b = make_user(), make_user()
    users.update_profile(session, a, alias="Lau")
    with pytest.raises(users.ProfileError, match="alias"):
        users.update_profile(session, b, alias="LAU")
    post = forum.create_post(session, a.id, title="Título", body="x", category="General")
    comment = forum.add_comment(session, post.id, a.id, "comentario")
    with pytest.raises(moderation.ModerationError, match="no ambos"):
        moderation.report(
            session, b.id, a.id, reason="spam", post_id=post.id, comment_id=comment.id
        )


def test_admin_metrics_and_activity_queries(session, make_user):
    u = make_user()
    forum.create_post(session, u.id, title="Hola mundo", body="x", category="General")
    metrics = admin.global_metrics(session)
    assert (metrics.users, metrics.posts, metrics.comments) == (1, 1, 0)
    activity = admin.activity_frame(session, days=7)
    assert activity["publicaciones"].sum() == 1
    assert len(activity) == 7
    assert moderation.reports_against_counts(session) == {}


def test_avatar_is_deferred_and_read_on_demand(session, make_user):
    import io

    from PIL import Image

    u = make_user()
    raw = io.BytesIO()
    Image.new("RGB", (40, 30), "red").save(raw, format="PNG")
    users.set_avatar(u, raw.getvalue())
    session.flush()
    assert u.has_avatar and u.avatar_updated_at is not None
    assert users.avatar_bytes(session, u.id).startswith(b"\x89PNG")
    assert widgets.avatar_src(u).startswith("data:image/png;base64,")
    users.set_avatar(u, None)
    session.flush()
    assert not u.has_avatar
    assert widgets.avatar_src(u).startswith("data:image/svg+xml")
