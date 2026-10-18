"""Sesión del usuario en la UI: usuario actual, cierre de sesión y sesión OIDC (Google)."""

from __future__ import annotations

import streamlit as st

from app import auth
from app.database.models import User
from app.database.session import session_scope
from app.ui.components.actions import flash


def current_user() -> User | None:
    """Recarga el usuario autenticado desde la BD en cada ejecución (objeto desacoplado)."""
    user_id = st.session_state.get("user_id")
    if user_id is None:
        return None
    with session_scope() as s:
        user = s.get(User, user_id)
    if user is None or not user.is_active:
        st.session_state.pop("user_id", None)
        return None
    return user


def require_user() -> User:
    user = current_user()
    if user is None:
        st.stop()
    return user  # type: ignore[return-value]


OIDC_ERROR = "_oidc_error"


def oidc_logged_in() -> bool:
    """¿Hay una sesión de st.login (cookie OIDC) activa?"""
    return auth.google_login_enabled() and bool(st.user.get("is_logged_in"))


# Proveedores de st.login (ver scripts/write_streamlit_secrets.py). Ambos van a Google a través
# de Keycloak; el nombre indica la intención y Streamlit lo guarda en st.user["provider"].
GOOGLE_LOGIN = "google"
GOOGLE_SIGNUP = "googlesignup"  # Streamlit no admite "_" en el nombre


def sync_oidc_session() -> None:
    """Al volver de Google (o al recargar con la cookie de sesión vigente), inicia sesión o crea
    la cuenta según el botón que se usó: «Iniciar sesión con Google» sólo entra si la cuenta ya
    existe; «Crear cuenta con Google» la crea si hace falta."""
    if "user_id" in st.session_state or not oidc_logged_in():
        return
    allow_create = st.user.get("provider") == GOOGLE_SIGNUP
    try:
        with session_scope() as s:
            user, created = auth.login_with_oidc(s, dict(st.user), allow_create=allow_create)
            user_id, name, pending = user.id, user.display_name, user.pending_deletion
    except auth.AuthError as exc:
        st.session_state[OIDC_ERROR] = {
            "message": str(exc),
            "not_found": isinstance(exc, auth.AccountNotFoundError),
        }
        return
    st.session_state.pop(OIDC_ERROR, None)
    st.session_state["user_id"] = user_id
    if pending:
        return
    if created:
        flash(f"¡Cuenta creada con Google! Bienvenido, {name}.", "🎉")
    elif allow_create:
        flash(f"Ya tenías una cuenta, {name}: iniciaste sesión.", "👋")
    else:
        flash(f"¡Bienvenido, {name}!", "👋")


def logout() -> None:
    """Cierra la sesión de la app y, si se entró con Google, también la de st.login/Keycloak
    (``st.logout`` redirige y crea una sesión nueva)."""
    oidc = oidc_logged_in()
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    if oidc:
        st.logout()
