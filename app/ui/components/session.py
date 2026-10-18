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


def sync_oidc_session() -> None:
    """Si el usuario volvió de «Continuar con Google» (o recargó la página con la cookie de
    sesión vigente), vincula esa identidad con su usuario de la app."""
    if "user_id" in st.session_state or not oidc_logged_in():
        return
    try:
        with session_scope() as s:
            user = auth.login_with_oidc(s, dict(st.user))
            user_id, name, pending = user.id, user.display_name, user.pending_deletion
    except auth.AuthError as exc:
        st.session_state[OIDC_ERROR] = str(exc)
        return
    st.session_state.pop(OIDC_ERROR, None)
    st.session_state["user_id"] = user_id
    if not pending:
        flash(f"¡Bienvenido, {name}!", "👋")


def logout() -> None:
    """Cierra la sesión de la app y, si se entró con Google, también la de st.login/Keycloak
    (``st.logout`` redirige y crea una sesión nueva)."""
    oidc = oidc_logged_in()
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    if oidc:
        st.logout()
