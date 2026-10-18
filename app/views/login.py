"""Inicio de sesión, registro y activación de la cuenta."""

from __future__ import annotations

import streamlit as st

from app.config import get_settings
from app.db.session import session_scope
from app.services import auth
from app.ui import common

UNVERIFIED_LOGIN = "_unverified_login"
REGISTERED_EMAIL = "_registered_email"


def _resend(login: str) -> None:
    try:
        auth.resend_verification(login)
    except auth.AuthError as exc:
        st.error(str(exc))
    else:
        st.success(
            "Si la cuenta existe y no está activada, te enviamos un nuevo enlace de activación."
        )


def _login_tab() -> None:
    with st.form("login"):
        username = st.text_input("Usuario o correo")
        password = st.text_input("Contraseña", type="password")
        otp = ""
        if auth.two_factor_supported():
            otp = st.text_input(
                "Código de verificación (2FA)",
                max_chars=6,
                placeholder="Sólo si activaste la verificación en dos pasos",
                help="Código de 6 dígitos de tu app autenticadora "
                "(Google Authenticator, Microsoft Authenticator, FreeOTP…).",
            )
        if st.form_submit_button("Ingresar", type="primary", width="stretch"):
            st.session_state.pop(UNVERIFIED_LOGIN, None)
            try:
                with session_scope() as s:
                    user = auth.login(s, username, password, otp or None)
                    user_id, name, pending = user.id, user.display_name, user.pending_deletion
            except auth.EmailNotVerifiedError as exc:
                st.session_state[UNVERIFIED_LOGIN] = exc.login
            except auth.AuthError as exc:
                st.error(str(exc))
            else:
                st.session_state.pop(REGISTERED_EMAIL, None)
                st.session_state["user_id"] = user_id
                if not pending:  # una cuenta en eliminación sólo ve la pantalla de cancelación
                    common.flash(f"¡Bienvenido, {name}!", "👋")
                st.rerun()

    pending = st.session_state.get(UNVERIFIED_LOGIN)
    if pending:
        st.warning(str(auth.EmailNotVerifiedError(pending)), icon="📧")
        if st.button("Reenviar correo de activación", icon="🔁"):
            _resend(pending)

    if auth.two_factor_supported():
        with st.expander("¿No recibiste el correo de activación?"):
            login = st.text_input("Tu usuario o correo", key="resend_login")
            if st.button("Reenviar enlace", key="resend_btn"):
                _resend(login)


def _register_tab() -> None:
    with st.form("register", clear_on_submit=False):
        c1, c2 = st.columns(2)
        first_name = c1.text_input("Nombre")
        last_name = c2.text_input("Apellido")
        new_username = st.text_input("Usuario", help="3 a 30 caracteres: letras, números, . - _")
        email = st.text_input("Correo")
        c3, c4 = st.columns(2)
        pwd = c3.text_input("Contraseña", type="password", help="Mín. 8 con letras y números")
        pwd2 = c4.text_input("Repite la contraseña", type="password")
        if st.form_submit_button("Crear cuenta", type="primary", width="stretch"):
            if pwd != pwd2:
                st.error("Las contraseñas no coinciden.")
                return
            try:
                with session_scope() as s:
                    user = auth.register(
                        s,
                        username=new_username,
                        email=email,
                        password=pwd,
                        first_name=first_name,
                        last_name=last_name,
                    )
                    verified, address = user.email_verified, user.email
            except auth.AuthError as exc:
                st.error(str(exc))
                return
            if verified:
                common.flash("Cuenta creada. Ya puedes iniciar sesión.", "🎉")
            else:
                st.session_state[REGISTERED_EMAIL] = address
            st.rerun()


def render() -> None:
    settings = get_settings()
    _, center, _ = st.columns([1, 1.4, 1])
    with center:
        st.title("🎓 CT Ranking")
        st.caption("Foros, plan académico, retos y una comunidad que te impulsa.")
        common.show_flashes()
        if address := st.session_state.get(REGISTERED_EMAIL):
            st.success(
                f"¡Cuenta creada! Te enviamos un enlace de activación a **{address}**. "
                "Ábrelo para activar tu cuenta y luego inicia sesión.",
                icon="📧",
            )
        tab_login, tab_register = st.tabs(["Iniciar sesión", "Crear cuenta"])
        with tab_login:
            _login_tab()
        with tab_register:
            _register_tab()

        provider = "Keycloak" if settings.auth_provider == "keycloak" else "base de datos local"
        st.caption(f"🔒 Autenticación mediante {provider}.")
