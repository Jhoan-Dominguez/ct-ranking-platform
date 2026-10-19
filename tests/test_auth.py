"""Autenticación: registro, login, contraseñas, dominio institucional y Google."""

import re

import pytest

from app import auth
from app.auth import accounts
from app.auth import service as auth_service
from app.core import mailer


def _last_code() -> str:
    return re.search(r"\b(\d{6})\b", mailer.OUTBOX[-1].text).group(1)


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
        accounts.request_email_change(session, student, "sofi@gmail.com")
    accounts.request_email_change(session, student, "sofia.h@estudiantes.areandina.edu.co")
    accounts.confirm_email_change(session, student, _last_code())
    assert student.email == "sofia.h@estudiantes.areandina.edu.co"


def test_admins_are_exempt_from_student_domain(session, make_user):
    from app.database.models import Role

    admin = make_user(email="soporte@ctranking.local", role=Role.ADMIN)
    accounts.request_email_change(session, admin, "admin2@ctranking.local")
    accounts.confirm_email_change(session, admin, _last_code())
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


def test_google_signup_creates_and_then_logs_in(session):
    user, created = auth.login_with_oidc(session, _google_claims(), allow_create=True)
    assert created
    assert (user.username, user.email, user.keycloak_id) == (
        "eva.gomez",
        "eva.gomez@estudiantes.areandina.edu.co",
        "kc-123",
    )
    assert user.email_verified and user.full_name == "Eva Gómez" and user.last_login
    # Una vez creada, «Iniciar sesión con Google» entra a la misma cuenta.
    again, created = auth.login_with_oidc(session, _google_claims(given_name="Otro"))
    assert again.id == user.id and not created
    # «Crear cuenta con Google» con una cuenta existente sólo inicia sesión.
    _, created = auth.login_with_oidc(session, _google_claims(), allow_create=True)
    assert not created


def test_google_login_requires_an_existing_account(session):
    with pytest.raises(auth.AccountNotFoundError, match="Créala primero"):
        auth.login_with_oidc(session, _google_claims())


def test_google_login_finds_account_registered_with_the_form(session, make_user):
    """Una cuenta creada con el formulario se reconoce por su correo y queda vinculada."""
    user = make_user(email="eva.gomez@estudiantes.areandina.edu.co")
    linked, created = auth.login_with_oidc(session, _google_claims())
    assert linked.id == user.id and not created and linked.keycloak_id == "kc-123"


def test_login_with_google_rejects_other_domains_and_unverified(session):
    with pytest.raises(auth.AuthError, match="institucional"):
        auth.login_with_oidc(session, _google_claims(email="eva@gmail.com"), allow_create=True)
    with pytest.raises(auth.AuthError, match="confirmó"):
        auth.login_with_oidc(session, _google_claims(email_verified=False), allow_create=True)
    with pytest.raises(auth.AuthError):
        auth.login_with_oidc(session, _google_claims(sub=None), allow_create=True)


def test_login_with_google_respects_disabled_accounts(session):
    user, _ = auth.login_with_oidc(session, _google_claims(), allow_create=True)
    auth.set_active(session, user, False)
    with pytest.raises(auth.AuthError, match="deshabilitada"):
        auth.login_with_oidc(session, _google_claims())


def test_first_keycloak_login_creates_active_user(session):
    """Regresión: un usuario nuevo tenía is_active=None antes del flush y se rechazaba."""
    identity = auth.Identity(external_id="kc-new", username="nuevo", email="n@x.co")
    user = auth_service._sync_keycloak_user(session, identity)
    assert user.id is not None and user.is_active is True and user.role == "student"


def test_begin_login_without_two_factor_completes_login(session, make_user):
    """Paso 1 del login: sin 2FA (proveedor local) inicia sesión directamente."""
    user = make_user(username="pedro", password="Clave1234")
    assert auth.begin_login(session, "pedro", "Clave1234").id == user.id
    with pytest.raises(auth.AuthError):
        auth.begin_login(session, "pedro", "mala12345")
    with pytest.raises(auth.AuthError, match="Ingresa"):
        auth.begin_login(session, "pedro", "")
