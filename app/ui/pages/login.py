"""Inicio de sesión, registro y activación de la cuenta."""

from __future__ import annotations

import time

import streamlit as st

from app import auth
from app.core.config import get_settings
from app.database.session import session_scope
from app.ui.components import actions, session, widgets

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


OTP_PENDING = "_otp_pending"
OTP_WINDOW_S = 300  # tiempo máximo entre el paso 1 (contraseña) y el paso 2 (código)


def _finish_login(user_id: int, name: str, pending_deletion: bool) -> None:
    st.session_state.pop(OTP_PENDING, None)
    st.session_state.pop(REGISTERED_EMAIL, None)
    session.start_session(user_id)
    if not pending_deletion:  # una cuenta en eliminación sólo ve la pantalla de cancelación
        actions.flash(f"¡Bienvenido, {name}!", "👋")
    st.rerun()


def _password_step() -> None:
    """Paso 1: usuario/correo y contraseña. El código 2FA se pide después, sólo si hace falta."""
    with st.form("login"):
        username = st.text_input("Usuario o correo")
        password = st.text_input("Contraseña", type="password")
        if st.form_submit_button("Ingresar", type="primary", width="stretch"):
            st.session_state.pop(UNVERIFIED_LOGIN, None)
            try:
                with session_scope() as s:
                    user = auth.begin_login(s, username, password)
                    done = (user.id, user.display_name, user.pending_deletion) if user else None
            except auth.EmailNotVerifiedError as exc:
                st.session_state[UNVERIFIED_LOGIN] = exc.login
            except auth.AuthError as exc:
                st.error(str(exc))
            else:
                if done:
                    _finish_login(*done)
                # Contraseña correcta y la cuenta tiene 2FA: pasar al paso 2. La contraseña se
                # guarda sólo en la memoria de esta sesión y por un máximo de 5 minutos.
                st.session_state[OTP_PENDING] = {
                    "login": username.strip(),
                    "password": password,
                    "expires": time.time() + OTP_WINDOW_S,
                }
                st.rerun()


def _otp_step(pending: dict) -> None:
    """Paso 2: código de la app autenticadora (sólo para cuentas con 2FA)."""
    st.markdown("#### 🔐 Verificación en dos pasos")
    st.write(
        f"Hola **{pending['login']}**, tu cuenta tiene la verificación en dos pasos activada. "
        "Escribe el código de 6 dígitos que muestra tu app autenticadora."
    )
    with st.form("otp"):
        code = st.text_input(
            "Código de verificación",
            max_chars=6,
            placeholder="123456",
            help="Google Authenticator, Microsoft Authenticator, FreeOTP…",
        )
        if st.form_submit_button("Verificar", type="primary", width="stretch"):
            if not code.strip():
                st.error("Escribe el código de verificación.")
                return
            try:
                with session_scope() as s:
                    user = auth.login(s, pending["login"], pending["password"], code)
                    done = (user.id, user.display_name, user.pending_deletion)
            except auth.AuthError as exc:
                message = str(exc)
                if message == auth.INVALID_LOGIN:
                    message = "El código no es correcto o ya venció. Escribe el código actual."
                st.error(message)
            else:
                _finish_login(*done)
    if st.button("← Volver", key="otp_back"):
        st.session_state.pop(OTP_PENDING, None)
        st.rerun()


def _login_tab() -> None:
    pending = st.session_state.get(OTP_PENDING)
    if pending and pending["expires"] < time.time():
        st.session_state.pop(OTP_PENDING, None)
        st.warning("Pasó demasiado tiempo. Ingresa de nuevo tu usuario y contraseña.")
        pending = None
    if pending:
        _otp_step(pending)
        return

    _password_step()

    if auth.google_login_enabled():
        _google_button(
            session.GOOGLE_LOGIN,
            "Iniciar sesión con Google",
            "Sólo si ya tienes cuenta. ¿Aún no? Usa «Crear cuenta con Google» en la pestaña "
            "«Crear cuenta».",
        )

    unverified = st.session_state.get(UNVERIFIED_LOGIN)
    if unverified:
        st.warning(str(auth.EmailNotVerifiedError(unverified)), icon="📧")
        if st.button("Reenviar correo de activación", icon="🔁"):
            _resend(unverified)

    if auth.two_factor_supported():
        with st.expander("¿No recibiste el correo de activación?"):
            login = st.text_input("Tu usuario o correo", key="resend_login")
            if st.button("Reenviar enlace", key="resend_btn"):
                _resend(login)


def _google_button(provider: str, label: str, caption: str) -> None:
    st.markdown(
        "<div style='text-align:center;opacity:.6;margin:.3rem 0'>— o —</div>",
        unsafe_allow_html=True,
    )
    if st.button(label, icon=":material/account_circle:", width="stretch", key=provider):
        st.login(provider)
    st.caption(caption)


def _google_error() -> None:
    """Resultado fallido al volver de Google (p. ej. «iniciar sesión» sin tener cuenta)."""
    error = st.session_state.get(session.OIDC_ERROR)
    if not error:
        return
    st.error(error["message"], icon="⚠️")
    c1, c2 = st.columns(2)
    if error["not_found"] and c1.button(
        "Crear cuenta con Google", type="primary", width="stretch", key="google_signup_retry"
    ):
        st.session_state.pop(session.OIDC_ERROR, None)
        st.login(session.GOOGLE_SIGNUP)
    if c2.button("Usar otra cuenta de Google", width="stretch", key="google_other"):
        session.logout()


def _register_tab() -> None:
    with st.form("register", clear_on_submit=False):
        c1, c2 = st.columns(2)
        first_name = c1.text_input("Nombre")
        last_name = c2.text_input("Apellido")
        new_username = st.text_input("Usuario", help="3 a 30 caracteres: letras, números, . - _")
        email_local = widgets.institutional_email_input("Correo institucional")
        c3, c4 = st.columns(2)
        pwd = c3.text_input("Contraseña", type="password", help="Mín. 8 con letras y números")
        pwd2 = c4.text_input("Repite la contraseña", type="password")
        if st.form_submit_button("Crear cuenta", type="primary", width="stretch"):
            if pwd != pwd2:
                st.error("Las contraseñas no coinciden.")
                return
            try:
                email = auth.student_email(email_local)
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
                actions.flash("Cuenta creada. Ya puedes iniciar sesión.", "🎉")
            else:
                st.session_state[REGISTERED_EMAIL] = address
            st.rerun()


def render() -> None:
    settings = get_settings()
    _, center, _ = st.columns([1, 1.4, 1])
    with center:
        st.title("🎓 CT Ranking")
        st.caption("Foros, plan académico, retos y una comunidad que te impulsa.")
        actions.show_flashes()
        if address := st.session_state.get(REGISTERED_EMAIL):
            st.success(
                f"¡Cuenta creada! Te enviamos un enlace de activación a **{address}**. "
                "Ábrelo para activar tu cuenta y luego inicia sesión.",
                icon="📧",
            )
        _google_error()
        tab_login, tab_register = st.tabs(["Iniciar sesión", "Crear cuenta"])
        with tab_login:
            _login_tab()
        with tab_register:
            _register_tab()
            if auth.google_login_enabled():
                _google_button(
                    session.GOOGLE_SIGNUP,
                    "Crear cuenta con Google",
                    f"Con tu cuenta institucional @{auth.student_domain()}: se usan tu nombre y tu "
                    "correo de Google, y la cuenta queda activada de inmediato.",
                )

        provider = "Keycloak" if settings.auth_provider == "keycloak" else "base de datos local"
        st.caption(f"🔒 Autenticación mediante {provider}.")
