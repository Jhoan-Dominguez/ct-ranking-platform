"""Sesión del usuario en la UI: usuario actual, cierre de sesión y sesión OIDC (Google)."""

from __future__ import annotations

import time

import streamlit as st

from app import auth
from app.core.config import get_settings
from app.database.models import User
from app.database.session import session_scope
from app.services import users
from app.ui.components.actions import flash

# Claves de st.session_state.
LOGIN_AT = "_login_at"  # momento del login con contraseña (para SESSION_TTL_HOURS)
CURRENT_USER = "_current_user"  # usuario cargado en esta ejecución (lo fija main.py)


def start_session(user_id: int) -> None:
    """Marca al usuario como autenticado en esta sesión de Streamlit."""
    st.session_state["user_id"] = user_id
    st.session_state[LOGIN_AT] = time.time()


def _expired() -> bool:
    ttl_h = get_settings().session_ttl_hours
    login_at = st.session_state.get(LOGIN_AT)
    return bool(ttl_h and login_at and time.time() - login_at > ttl_h * 3600)


def current_user() -> User | None:
    """Recarga el usuario autenticado desde la BD (objeto desacoplado). ``main.py`` la llama una
    vez por ejecución y guarda el resultado; las páginas lo obtienen con ``require_user``."""
    st.session_state.pop(CURRENT_USER, None)
    user_id = st.session_state.get("user_id")
    if user_id is None:
        return None
    if _expired():
        logout()
        flash("Tu sesión venció. Inicia sesión de nuevo.", "⏰")
        return None
    with session_scope() as s:
        user = users.get_user(s, user_id)
    if user is None or not user.is_active:
        # Cuenta borrada o deshabilitada: también se cierra la sesión de Google (si la hay), para
        # que la cookie no vuelva a intentar el ingreso en cada recarga.
        logout()
        return None
    st.session_state[CURRENT_USER] = user
    return user


def require_user() -> User:
    """Usuario de esta ejecución (sin volver a consultar la BD si ``main.py`` ya lo cargó)."""
    user = st.session_state.get(CURRENT_USER) or current_user()
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
    # Si el último intento ya falló (p. ej. cuenta deshabilitada) no se reintenta en cada rerun:
    # el aviso queda en pantalla hasta que se use «Usar otra cuenta de Google».
    if "user_id" in st.session_state or OIDC_ERROR in st.session_state or not oidc_logged_in():
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
    st.session_state["user_id"] = user_id  # la cookie OIDC controla la duración de la sesión
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
    flashes = st.session_state.get("_flash", [])
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    if oidc:
        st.logout()
    st.session_state["_flash"] = flashes
